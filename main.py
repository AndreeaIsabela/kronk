import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from web import start_web
from db import init_db

load_dotenv()

COGS = [
    "commands.pet_buff",
    "commands.rally_leaders",
]

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.sync_commands()
    print("Slash commands synced.")


async def main():
    init_db()
    await start_web(port=int(os.getenv("PORT") or os.getenv("WEB_PORT", 8080)))
    async with bot:
        for cog in COGS:
            bot.load_extension(cog)
            print(f"Loaded cog: {cog}")
        await bot.start(os.getenv("BOT_TOKEN"))


asyncio.run(main())
