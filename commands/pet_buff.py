import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import load_timers, upsert_timer, delete_timer, load_rally_leaders
from utils import parse_mentions

BUFF_DURATION = 2 * 3600   # 2 hours in seconds
WARNING_BEFORE = 20 * 60   # warn 20 min before expiry

# for testing:
BUFF_DURATION = 2 * 60
WARNING_BEFORE = 20

NO_PING = discord.AllowedMentions(users=False, roles=False, everyone=False)
EVERYONE_PING = discord.AllowedMentions(everyone=True, users=False, roles=False)

BATCH_WINDOW = 1.0  # seconds to wait before flushing a batch


async def _resolve_targets(
    targets_str: str | None,
    ctx: discord.ApplicationContext,
) -> tuple[list[tuple[str, str]], str | None]:
    """
    Returns (targets, error).
    Accepts: empty (→ self), @mentions, or the keyword "rally-leaders".
    """
    if targets_str and targets_str.strip().lower() == "rally-leaders":
        leaders = await load_rally_leaders(str(ctx.guild.id))
        if not leaders:
            return [], "No rally leaders set yet. Use `/set-rally-leaders` first."
        return [(l["user_id"], l["username"]) for l in leaders], None

    if targets_str:
        mentions = parse_mentions(targets_str, ctx.guild)
        if mentions:
            return mentions, None

    return [(str(ctx.author.id), ctx.author.display_name)], None



def _mention(user_id: str) -> str:
    return f"<@{user_id}>"

def _mention_list(targets: list[tuple[str, str]]) -> str:
    return ", ".join(_mention(uid) for uid, _ in targets)


class PetBuff(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_tasks: dict[str, asyncio.Task] = {}
        self._recovered = False
        # batch buffers: channel_id -> list of user_ids waiting to be flushed
        self._pending_warnings: dict[int, list[str]] = {}
        self._pending_expiries: dict[int, list[str]] = {}
        self._batch_tasks: dict[str, asyncio.Task] = {}

    # --- batch helpers ---

    async def _queue_warning(self, user_id: str, channel: discord.TextChannel) -> None:
        cid = channel.id
        self._pending_warnings.setdefault(cid, []).append(user_id)
        key = f"w:{cid}"
        if key not in self._batch_tasks or self._batch_tasks[key].done():
            self._batch_tasks[key] = asyncio.create_task(self._flush_warnings(cid, channel))

    async def _flush_warnings(self, channel_id: int, channel: discord.TextChannel) -> None:
        await asyncio.sleep(BATCH_WINDOW)
        user_ids = self._pending_warnings.pop(channel_id, [])
        if not user_ids:
            return
        mentions = ", ".join(_mention(uid) for uid in user_ids)
        verb = "expire" if len(user_ids) > 1 else "expires"
        await channel.send(
            f"⚠️ @everyone {mentions} pet buff 🐯💥 {verb} in 20 minutes!",
            allowed_mentions=EVERYONE_PING,
        )

    async def _queue_expiry(self, user_id: str, channel: discord.TextChannel) -> None:
        cid = channel.id
        self._pending_expiries.setdefault(cid, []).append(user_id)
        key = f"e:{cid}"
        if key not in self._batch_tasks or self._batch_tasks[key].done():
            self._batch_tasks[key] = asyncio.create_task(self._flush_expiries(cid, channel))

    async def _flush_expiries(self, channel_id: int, channel: discord.TextChannel) -> None:
        await asyncio.sleep(BATCH_WINDOW)
        user_ids = self._pending_expiries.pop(channel_id, [])
        if not user_ids:
            return
        mentions = ", ".join(_mention(uid) for uid in user_ids)
        verb = "have" if len(user_ids) > 1 else "has"
        await channel.send(
            f"❌ {mentions} pet buff 🐯💥 {verb} deactivated.",
            allowed_mentions=NO_PING,
        )

    # --- timer helpers ---

    def _task_key(self, guild_id: str, user_id: str) -> str:
        return f"{guild_id}:{user_id}"

    def _cancel(self, guild_id: str, user_id: str) -> None:
        task = self.active_tasks.pop(self._task_key(guild_id, user_id), None)
        if task:
            task.cancel()

    async def _schedule(
        self, guild_id: str, user_id: str, end_ts: float, channel: discord.TextChannel
    ) -> None:
        self._cancel(guild_id, user_id)
        key = self._task_key(guild_id, user_id)
        self.active_tasks[key] = asyncio.create_task(
            self._run_timer(guild_id, user_id, end_ts, channel)
        )

    async def _run_timer(
        self, guild_id: str, user_id: str, end_ts: float, channel: discord.TextChannel
    ) -> None:
        now = datetime.now(timezone.utc).timestamp()
        remaining = end_ts - now
        warning_in = remaining - WARNING_BEFORE

        try:
            if warning_in > 0:
                await asyncio.sleep(warning_in)
                await self._queue_warning(user_id, channel)
                await asyncio.sleep(WARNING_BEFORE)
            elif remaining > 0:
                await asyncio.sleep(remaining)
        except asyncio.CancelledError:
            return

        await delete_timer(guild_id, user_id)
        self.active_tasks.pop(self._task_key(guild_id, user_id), None)
        await self._queue_expiry(user_id, channel)

    # --- crash recovery on startup ---

    @commands.Cog.listener()
    async def on_ready(self):
        if self._recovered:
            return
        self._recovered = True

        now = datetime.now(timezone.utc).timestamp()

        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            timers = await load_timers(guild_id)
            expired = []

            for user_id, data in timers.items():
                channel = self.bot.get_channel(data["channel_id"])
                if channel is None:
                    print(f"[pet_buff] Channel for {data['username']} in guild {guild_id} not found, skipping.")
                    expired.append(user_id)
                    continue
                if data["end_ts"] <= now:
                    await self._queue_expiry(user_id, channel)
                    expired.append(user_id)
                else:
                    await self._schedule(guild_id, user_id, data["end_ts"], channel)

            for user_id in expired:
                await delete_timer(guild_id, user_id)

        print(f"[pet_buff] Recovery done — active tasks: {len(self.active_tasks)}")

    # --- commands ---

    @discord.slash_command(
        name="pet-buff",
        description="Activate pet buff timer. Leave empty for yourself, @mention players, or type 'rally-leaders'.",
    )
    @discord.option(
        "targets",
        description="@Mention players, or type 'rally-leaders'. Leave empty for yourself.",
        required=False,
        autocomplete=discord.utils.basic_autocomplete(["rally-leaders"]),
    )
    async def pet_buff(self, ctx: discord.ApplicationContext, targets: str = None):
        resolved, error = await _resolve_targets(targets, ctx)
        if error:
            await ctx.respond(error, ephemeral=True)
            return

        guild_id = str(ctx.guild.id)
        channel = ctx.channel
        timers = await load_timers(guild_id)
        end_ts = datetime.now(timezone.utc).timestamp() + BUFF_DURATION

        activated: list[tuple[str, str]] = []
        already_active: list[tuple[str, str]] = []

        for user_id, username in resolved:
            if user_id in timers:
                already_active.append((user_id, username))
            else:
                await upsert_timer(guild_id, user_id, username, end_ts, channel.id)
                await self._schedule(guild_id, user_id, end_ts, channel)
                activated.append((user_id, username))

        reply_parts = []
        if activated:
            reply_parts.append(f"✅ Timer started for: {_mention_list(activated)}")
        if already_active:
            reply_parts.append(
                f"⚠️ Already has an active timer: {_mention_list(already_active)} — use `/pet-buff-cancel` first."
            )
        await ctx.respond("\n".join(reply_parts), ephemeral=True, allowed_mentions=NO_PING)

        if activated:
            await channel.send(
                f"✅ {_mention_list(activated)} activated pet buff 🐯💥",
                allowed_mentions=NO_PING,
            )

    @discord.slash_command(
        name="pet-buff-cancel",
        description="Cancel pet buff timer. Leave empty for yourself, @mention players, or type 'rally-leaders'.",
    )
    @discord.option(
        "targets",
        description="@Mention players, or type 'rally-leaders'. Leave empty for yourself.",
        required=False,
        autocomplete=discord.utils.basic_autocomplete(["rally-leaders"]),
    )
    async def pet_buff_cancel(self, ctx: discord.ApplicationContext, targets: str = None):
        resolved, error = await _resolve_targets(targets, ctx)
        if error:
            await ctx.respond(error, ephemeral=True)
            return

        guild_id = str(ctx.guild.id)
        timers = await load_timers(guild_id)

        cancelled: list[tuple[str, str, int | None]] = []
        not_found: list[tuple[str, str]] = []

        for user_id, username in resolved:
            key = self._task_key(guild_id, user_id)
            if user_id not in timers and key not in self.active_tasks:
                not_found.append((user_id, username))
            else:
                channel_id = timers.get(user_id, {}).get("channel_id")
                self._cancel(guild_id, user_id)
                await delete_timer(guild_id, user_id)
                cancelled.append((user_id, username, channel_id))

        reply_parts = []
        if cancelled:
            reply_parts.append(f"🚫 Cancelled: {_mention_list([(uid, n) for uid, n, _ in cancelled])}")
        if not_found:
            reply_parts.append(f"ℹ️ No active timer: {_mention_list(not_found)}")
        await ctx.respond("\n".join(reply_parts), ephemeral=True, allowed_mentions=NO_PING)

        channel_groups: dict[int, list[str]] = {}
        for user_id, username, channel_id in cancelled:
            if channel_id:
                channel_groups.setdefault(channel_id, []).append(user_id)

        for channel_id, user_ids in channel_groups.items():
            ch = self.bot.get_channel(channel_id)
            if ch:
                mentions = ", ".join(_mention(uid) for uid in user_ids)
                await ch.send(f"🚫 {mentions} cancelled their pet buff 🐯💥 timer.", allowed_mentions=NO_PING)


def setup(bot: commands.Bot):
    bot.add_cog(PetBuff(bot))
