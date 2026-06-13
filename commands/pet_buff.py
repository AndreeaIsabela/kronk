import os
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils import load_timers, save_timers

BUFF_DURATION = 2 * 3600   # 2 hours in seconds
WARNING_BEFORE = 20 * 60   # warn 20 min before expiry

#for testing
# BUFF_DURATION = 2 * 60   # 2 minutes
# WARNING_BEFORE = 20     # 20 seconds

class PetBuff(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_tasks: dict[str, asyncio.Task] = {}
        self._recovered = False

    # --- internal helpers ---

    def _cancel(self, user_id: str) -> None:
        task = self.active_tasks.pop(user_id, None)
        if task:
            task.cancel()

    async def _schedule(self, user_id: str, username: str, end_ts: float, channel: discord.TextChannel) -> None:
        self._cancel(user_id)
        self.active_tasks[user_id] = asyncio.create_task(
            self._run_timer(user_id, username, end_ts, channel)
        )

    async def _run_timer(self, user_id: str, username: str, end_ts: float, channel: discord.TextChannel) -> None:
        now = datetime.now(timezone.utc).timestamp()
        remaining = end_ts - now
        warning_in = remaining - WARNING_BEFORE

        try:
            if warning_in > 0:
                await asyncio.sleep(warning_in)
                await channel.send(
                    f"@everyone **{username}**'s pet buff expires in 20 minutes!",
                    allowed_mentions=discord.AllowedMentions(everyone=True),
                )
                await asyncio.sleep(WARNING_BEFORE)
            elif remaining > 0:
                # warning window already passed, just wait for expiry
                await asyncio.sleep(remaining)
        except asyncio.CancelledError:
            return

        await channel.send(f"❌ **{username}**'s pet buff has deactivated.")
        timers = load_timers()
        timers.pop(user_id, None)
        save_timers(timers)
        self.active_tasks.pop(user_id, None)

    # --- crash recovery on startup ---

    @commands.Cog.listener()
    async def on_ready(self):
        if self._recovered:
            return
        self._recovered = True

        timers = load_timers()
        now = datetime.now(timezone.utc).timestamp()
        expired = []

        for user_id, data in timers.items():
            end_ts = data["end_ts"]
            username = data["username"]
            channel = self.bot.get_channel(data["channel_id"])

            if channel is None:
                print(f"[pet_buff] Channel for {username} not found, skipping.")
                expired.append(user_id)
                continue

            if end_ts <= now:
                await channel.send(f"❌ **{username}**'s pet buff has deactivated.")
                expired.append(user_id)
            else:
                await self._schedule(user_id, username, end_ts, channel)

        for user_id in expired:
            timers.pop(user_id)
        if expired:
            save_timers(timers)

        print(f"[pet_buff] Recovery done — active: {len(self.active_tasks)}, expired: {len(expired)}")

    # --- slash command ---

    @discord.slash_command(
        name="pet-buff",
        description="Activate your 2-hour pet buff timer",
    )
    async def pet_buff(self, ctx: discord.ApplicationContext):
        channel = ctx.channel
        user_id = str(ctx.author.id)
        username = ctx.author.display_name
        end_ts = datetime.now(timezone.utc).timestamp() + BUFF_DURATION

        # persist before scheduling so a crash mid-sleep still recovers
        timers = load_timers()
        timers[user_id] = {"username": username, "end_ts": end_ts, "channel_id": channel.id}
        save_timers(timers)

        await self._schedule(user_id, username, end_ts, channel)

        await ctx.respond("✅ Pet buff timer started!", ephemeral=True)
        await channel.send(f"✅ **{username}** activated pet buff!")

    @discord.slash_command(
        name="pet-buff-cancel",
        description="Cancel your active pet buff timer",
    )
    async def pet_buff_cancel(self, ctx: discord.ApplicationContext):
        user_id = str(ctx.author.id)
        username = ctx.author.display_name

        timers = load_timers()
        if user_id not in timers and user_id not in self.active_tasks:
            await ctx.respond("You don't have an active pet buff timer.", ephemeral=True)
            return

        channel = self.bot.get_channel(timers[user_id]["channel_id"]) if user_id in timers else ctx.channel

        self._cancel(user_id)
        timers.pop(user_id, None)
        save_timers(timers)

        await ctx.respond("✅ Pet buff timer cancelled.", ephemeral=True)
        if channel:
            await channel.send(f"🚫 **{username}** cancelled their pet buff timer.")


def setup(bot: commands.Bot):
    bot.add_cog(PetBuff(bot))
