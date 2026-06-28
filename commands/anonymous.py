import discord
from discord.ext import commands

# Allow user and role pings but never @everyone / @here
ALLOW_MENTIONS = discord.AllowedMentions(everyone=False, users=True, roles=True)


class Anonymous(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @discord.slash_command(
        name="anonymous",
        description="Post an anonymous message to a channel.",
    )
    @discord.option("channel", description="Channel to post in", input_type=discord.TextChannel)
    @discord.option("message", description="The message to send anonymously")
    async def anonymous(
        self,
        ctx: discord.ApplicationContext,
        channel: discord.TextChannel,
        message: str,
    ):
        try:
            await channel.send(message, allowed_mentions=ALLOW_MENTIONS)
        except discord.Forbidden:
            await ctx.respond(
                f"❌ I don't have permission to send messages in <#{channel.id}>.",
                ephemeral=True,
            )
            return

        await ctx.respond("✅ Your anonymous message was sent.", ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(Anonymous(bot))
