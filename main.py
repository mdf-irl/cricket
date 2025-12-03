import asyncio
from pathlib import Path

import discord
from discord.ext import commands

from config import Config
from http_manager import HTTP
from logger_config import get_logger

logger = get_logger(__name__)

intents = discord.Intents.default()
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix=None, intents=intents, help_command=None)

async def load_cogs():
    """Load all cogs from the cogs directory."""
    cogs_dir = Path("./cogs")
    
    if not cogs_dir.exists():
        logger.error("./cogs directory not found!")
        return

    loaded_count = 0
    failed_count = 0

    for file in sorted(cogs_dir.glob("*.py")):
        if file.stem.startswith("_"):
            continue
            
        try:
            await bot.load_extension(f"cogs.{file.stem}")
            logger.info(f"Loaded cog: {file.stem}")
            loaded_count += 1
        except (commands.ExtensionNotFound, commands.NoEntryPointError) as e:
            logger.error(f"Cog error ({file.stem}): {type(e).__name__}")
            failed_count += 1
        except commands.ExtensionAlreadyLoaded:
            logger.warning(f"Cog already loaded: {file.stem}")
        except commands.ExtensionFailed as e:
            logger.error(f"Cog execution error ({file.stem}): {e.original}")
            failed_count += 1
        except Exception as e:
            logger.error(f"Unexpected error loading {file.stem}: {type(e).__name__}: {e}")
            failed_count += 1

    logger.info(f"Cog loading complete: {loaded_count} loaded, {failed_count} failed")

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    if not Config.TEST_GUILD_ID:
        logger.error("TEST_GUILD_ID not set in environment variables")
        return

    try:
        guild = discord.Object(id=Config.TEST_GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} command(s) to guild {Config.TEST_GUILD_ID}")
    except (discord.Forbidden, discord.HTTPException) as e:
        logger.error(f"Error syncing commands to guild {Config.TEST_GUILD_ID}: {type(e).__name__}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error syncing commands: {type(e).__name__}: {e}")

async def main():
    """Main bot entry point."""
    if not Config.load():
        logger.error("Configuration validation failed. Exiting.")
        return

    try:
        await HTTP.open()
        logger.info("HTTP session initialized")

        async with bot:
            await load_cogs()
            logger.info("Starting bot...")
            await bot.start(Config.DISCORD_TOKEN)
    except (discord.LoginFailure, discord.HTTPException) as e:
        logger.error(f"Discord error: {type(e).__name__}: {e}")
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error in main: {type(e).__name__}: {e}")
    finally:
        try:
            await HTTP.close()
            logger.info("HTTP session closed")
        except Exception as e:
            logger.warning(f"Error closing HTTP session: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown complete")
