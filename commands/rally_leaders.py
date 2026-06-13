import discord
from discord.ext import commands

from db import load_rally_leaders, save_rally_leaders
from utils import parse_mentions


class RallyLeaders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @discord.slash_command(
        name="set-rally-leaders",
        description="Set the rally leaders list (replaces any existing list).",
    )
    @discord.option(
        "roster",
        description="@Mention all rally leaders.",
        required=True,
    )
    async def set_rally_leaders(self, ctx: discord.ApplicationContext, roster: str):
        targets = parse_mentions(roster, ctx.guild)
        if not targets:
            await ctx.respond("No valid players mentioned.", ephemeral=True)
            return

        leaders = [{"user_id": uid, "username": name} for uid, name in targets]
        await save_rally_leaders(str(ctx.guild.id), leaders)

        names = ", ".join(f"<@{uid}>" for uid, _ in targets)
        await ctx.respond(f"✅ Rally leaders set: {names}", allowed_mentions=discord.AllowedMentions(users=False))

    @discord.slash_command(
        name="rally-leaders",
        description="Show the current rally leaders list.",
    )
    async def show_rally_leaders(self, ctx: discord.ApplicationContext):
        leaders = await load_rally_leaders(str(ctx.guild.id))
        if not leaders:
            await ctx.respond("No rally leaders set yet. Use `/set-rally-leaders` to add some.", ephemeral=True)
            return

        names = ", ".join(f"<@{l['user_id']}>" for l in leaders)
        await ctx.respond(f"Rally leaders: {names}", ephemeral=True, allowed_mentions=discord.AllowedMentions(users=False))


def setup(bot: commands.Bot):
    bot.add_cog(RallyLeaders(bot))
