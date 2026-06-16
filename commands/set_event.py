import asyncio
import calendar
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

from db import upsert_event, load_events, get_event, delete_event
from utils import parse_mentions

FREQUENCY_CHOICES = ["once", "daily", "bi-daily", "weekly", "monthly"]

FREQ_LABELS = {
    "once": "once",
    "daily": "every day",
    "bi-daily": "every 2 days",
    "weekly": "every week",
    "monthly": "every month",
}

NO_PING = discord.AllowedMentions(users=False, roles=False, everyone=False)
EVERYONE_PING = discord.AllowedMentions(everyone=True, users=False, roles=False)
USERS_PING = discord.AllowedMentions(users=True, roles=False, everyone=False)


def _parse_datetime(dt_str: str) -> datetime | None:
    """
    Parse a UTC datetime from user input.
    Accepted formats:
      - 'YYYY-MM-DD HH:MM'  → exact UTC date+time
      - 'DD/MM/YYYY HH:MM'  → exact UTC date+time
      - 'HH:MM'             → today UTC, or tomorrow if that time has already passed
    """
    dt_str = dt_str.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    # Time-only: use today, push to tomorrow if already past
    try:
        t = datetime.strptime(dt_str, "%H:%M")
        now = datetime.now(timezone.utc)
        candidate = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    except ValueError:
        pass
    return None


def _add_one_month(dt: datetime) -> datetime:
    """Advance dt by one calendar month, clamping to the last valid day if needed."""
    month = dt.month % 12 + 1
    year = dt.year + (dt.month // 12)
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _next_occurrence(dt: datetime, frequency: str) -> datetime | None:
    """Return the next occurrence datetime after dt, or None for 'once'."""
    if frequency == "daily":
        return dt + timedelta(days=1)
    if frequency == "bi-daily":
        return dt + timedelta(days=2)
    if frequency == "weekly":
        return dt + timedelta(days=7)
    if frequency == "monthly":
        return _add_one_month(dt)
    return None  # "once"


def _advance_to_future(dt: datetime, frequency: str) -> datetime:
    """
    Advance dt by frequency increments until it's in the future.
    Used during crash recovery to skip missed occurrences.
    """
    now = datetime.now(timezone.utc)
    while dt <= now:
        nxt = _next_occurrence(dt, frequency)
        if nxt is None:
            break  # "once" — stays in the past; caller handles this case separately
        dt = nxt
    return dt


class SetEvent(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Maps "{guild_id}:{event_name}" -> asyncio.Task
        self.active_tasks: dict[str, asyncio.Task] = {}
        self._recovered = False

    def _task_key(self, guild_id: str, event_name: str) -> str:
        return f"{guild_id}:{event_name}"

    def _cancel_task(self, guild_id: str, event_name: str) -> None:
        task = self.active_tasks.pop(self._task_key(guild_id, event_name), None)
        if task:
            task.cancel()

    def _start_task(self, guild_id: str, event: dict) -> None:
        """Cancel any existing task for this event, then start a new one."""
        self._cancel_task(guild_id, event["event_name"])
        key = self._task_key(guild_id, event["event_name"])
        self.active_tasks[key] = asyncio.create_task(self._run_event(guild_id, event))

    async def _fire_event(self, event: dict, channel: discord.TextChannel) -> None:
        """Send the event notification to the channel."""
        player_ids = event.get("player_ids") or []
        text = event.get("custom_message") or event["event_name"]

        if player_ids:
            mention_str = " ".join(f"<@{uid}>" for uid in player_ids)
            allowed = USERS_PING
        else:
            mention_str = "@everyone"
            allowed = EVERYONE_PING

        await channel.send(f"{mention_str} {text}", allowed_mentions=allowed)

    async def _run_event(self, guild_id: str, event: dict) -> None:
        """
        Core event loop: sleep until next_ts, fire the notification,
        then advance the schedule and repeat for recurring events.
        """
        key = self._task_key(guild_id, event["event_name"])
        try:
            while True:
                sleep_for = event["next_ts"] - datetime.now(timezone.utc).timestamp()
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)

                channel = self.bot.get_channel(event["channel_id"])
                if channel:
                    await self._fire_event(event, channel)
                else:
                    print(f"[set_event] Channel {event['channel_id']} not found for event '{event['event_name']}'")

                if event["frequency"] == "once":
                    await delete_event(guild_id, event["event_name"])
                    return

                # Compute next occurrence from the planned fire time (not wall clock)
                # to avoid drift accumulating over many repetitions.
                fired_dt = datetime.fromtimestamp(event["next_ts"], tz=timezone.utc)
                next_dt = _next_occurrence(fired_dt, event["frequency"])
                event = {**event, "next_ts": next_dt.timestamp()}
                await upsert_event(guild_id, event["event_name"], {
                    k: v for k, v in event.items() if k not in ("guild_id", "event_name")
                })
        except asyncio.CancelledError:
            pass
        finally:
            self.active_tasks.pop(key, None)

    # --- crash recovery ---

    @commands.Cog.listener()
    async def on_ready(self):
        if self._recovered:
            return
        self._recovered = True

        now = datetime.now(timezone.utc)

        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            events = await load_events(guild_id)

            for event in events:
                channel = self.bot.get_channel(event["channel_id"])
                if channel is None:
                    print(f"[set_event] Channel for event '{event['event_name']}' in guild {guild_id} not found, skipping.")
                    continue

                event_dt = datetime.fromtimestamp(event["next_ts"], tz=timezone.utc)

                if event_dt <= now:
                    if event["frequency"] == "once":
                        # Missed one-time event while bot was offline — fire it now.
                        await self._fire_event(event, channel)
                        await delete_event(guild_id, event["event_name"])
                    else:
                        # Recurring: skip missed occurrences and schedule the next future one.
                        event_dt = _advance_to_future(event_dt, event["frequency"])
                        event = {**event, "next_ts": event_dt.timestamp()}
                        await upsert_event(guild_id, event["event_name"], {
                            k: v for k, v in event.items() if k not in ("guild_id", "event_name")
                        })
                        self._start_task(guild_id, event)
                else:
                    self._start_task(guild_id, event)

        print(f"[set_event] Recovery done — active event tasks: {len(self.active_tasks)}")

    # --- commands ---

    @discord.slash_command(
        name="set-event",
        description="Schedule a one-time or recurring event notification in this channel.",
    )
    @discord.option(
        "event_name",
        description="Unique event name for this server. Reusing a name replaces the existing event.",
        required=True,
    )
    @discord.option(
        "date_time",
        description="UTC time: 'HH:MM' (today or tomorrow) or 'YYYY-MM-DD HH:MM' (exact date)",
        required=True,
    )
    @discord.option(
        "frequency",
        description="How often the event repeats",
        required=True,
        choices=FREQUENCY_CHOICES,
    )
    @discord.option(
        "custom_message",
        description="Message text sent when the event fires. Defaults to the event name if omitted.",
        required=False,
    )
    @discord.option(
        "players",
        description="@Mention any number of players to ping. Leave empty to ping @everyone.",
        required=False,
    )
    async def set_event(
        self,
        ctx: discord.ApplicationContext,
        event_name: str,
        date_time: str,
        frequency: str,
        custom_message: str = None,
        players: str = None,
    ):
        dt = _parse_datetime(date_time)
        if dt is None:
            await ctx.respond(
                "❌ Couldn't parse the date/time.\n"
                "Use `HH:MM` for today/tomorrow at that hour, or `YYYY-MM-DD HH:MM` for an exact date. All times are UTC.",
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc)
        if dt <= now:
            await ctx.respond(
                "❌ That date/time is already in the past.\n"
                "Tip: use `HH:MM` without a date — the bot will automatically schedule it for tomorrow if the time has passed today.",
                ephemeral=True,
            )
            return

        # Parse optional player mentions
        player_ids = []
        if players:
            parsed = parse_mentions(players, ctx.guild)
            if not parsed:
                await ctx.respond(
                    "❌ No valid @mentions found in the players field. Make sure you @mention server members.",
                    ephemeral=True,
                )
                return
            player_ids = [uid for uid, _ in parsed]

        guild_id = str(ctx.guild.id)
        existing = await get_event(guild_id, event_name)

        event_data = {
            "channel_id": ctx.channel.id,
            "setter_id": str(ctx.author.id),
            "next_ts": dt.timestamp(),
            "frequency": frequency,
            "custom_message": custom_message,
            "player_ids": player_ids,
        }
        await upsert_event(guild_id, event_name, event_data)

        event_doc = {"guild_id": guild_id, "event_name": event_name, **event_data}
        self._start_task(guild_id, event_doc)

        dt_str = dt.strftime("%Y-%m-%d %H:%M UTC")
        action = "updated" if existing else "set"
        await ctx.respond(
            f"✅ Event **{event_name}** {action} — first notification on **{dt_str}**, repeating **{FREQ_LABELS[frequency]}**.",
            ephemeral=True,
        )

    @discord.slash_command(
        name="list-events",
        description="List all scheduled events in this server.",
    )
    async def see_events(self, ctx: discord.ApplicationContext):
        guild_id = str(ctx.guild.id)
        events = await load_events(guild_id)

        if not events:
            await ctx.respond("ℹ️ No events scheduled in this server.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📅 Scheduled Events ({len(events)})",
            colour=discord.Colour.blurple(),
        )

        for event in events:
            next_dt = datetime.fromtimestamp(event["next_ts"], tz=timezone.utc)
            next_str = next_dt.strftime("%Y-%m-%d %H:%M UTC")

            channel = self.bot.get_channel(event["channel_id"])
            channel_str = channel.mention if channel else f"<#{event['channel_id']}>"

            player_ids = event.get("player_ids") or []
            players_str = " ".join(f"<@{uid}>" for uid in player_ids) if player_ids else "@everyone"

            message_str = event.get("custom_message") or "*(event name)*"

            value = (
                f"⏰ **{next_str}** · 🔁 {FREQ_LABELS[event['frequency']]}\n"
                f"📢 {channel_str} · 💬 {message_str}\n"
                f"👥 {players_str}"
            )
            embed.add_field(name=event["event_name"], value=value, inline=False)

        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(
        name="cancel-event",
        description="Cancel a scheduled event by name.",
    )
    @discord.option(
        "event_name",
        description="Name of the event to cancel",
        required=True,
    )
    async def cancel_event(self, ctx: discord.ApplicationContext, event_name: str):
        guild_id = str(ctx.guild.id)
        deleted = await delete_event(guild_id, event_name)

        if deleted:
            self._cancel_task(guild_id, event_name)
            await ctx.respond(f"🚫 Event **{event_name}** has been cancelled.", ephemeral=True)
        else:
            await ctx.respond(
                f"ℹ️ No event named **{event_name}** found in this server.",
                ephemeral=True,
            )


def setup(bot: commands.Bot):
    bot.add_cog(SetEvent(bot))
