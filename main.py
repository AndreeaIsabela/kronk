import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from web import start_web

load_dotenv()

COGS = [
    "commands.pet_buff",
]

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


async def main():
    await start_web(port=int(os.getenv("WEB_PORT", 8080)))
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            print(f"Loaded cog: {cog}")
        await bot.start(os.getenv("BOT_TOKEN"))


asyncio.run(main())
