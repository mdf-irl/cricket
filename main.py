import asyncio
import os

import discord
from discord.ext import commands

from config import Config
from http_manager import HTTP
from logger_config import get_logger

logger = get_logger(__name__)

bot = commands.Bot(command_prefix=None, intents=discord.Intents.default(), help_command=None)

async def load_cogs():
    """Load all cogs from the cogs directory."""
    try:
        cog_files = os.listdir("./cogs")
    except FileNotFoundError:
        logger.error("./cogs directory not found!")
        return
    except PermissionError:
        logger.error("Permission denied accessing ./cogs directory!")
        return

    loaded_count = 0
    failed_count = 0

    for file in sorted(cog_files):
        if file.endswith(".py") and not file.startswith("_"):
            cog_name = file[:-3]
            try:
                await bot.load_extension(f"cogs.{cog_name}")
                logger.info(f"Loaded cog: {cog_name}")
                loaded_count += 1
            except commands.ExtensionNotFound:
                logger.error(f"Cog module not found: {cog_name}")
                failed_count += 1
            except commands.ExtensionAlreadyLoaded:
                logger.warning(f"Cog already loaded: {cog_name}")
            except commands.NoEntryPointError:
                logger.error(f"Cog missing setup() function: {cog_name}")
                failed_count += 1
            except commands.ExtensionFailed as e:
                logger.error(f"Cog execution error ({cog_name}): {e.original}")
                failed_count += 1
            except Exception as e:
                logger.error(f"Unexpected error loading cog {cog_name}: {type(e).__name__}: {e}")
                failed_count += 1

    logger.info(f"Cog loading complete: {loaded_count} loaded, {failed_count} failed")

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    try:
        await bot.change_presence(activity=discord.Game(name="Dungeons & Dragons"))
    except Exception as e:
        logger.warning(f"Failed to set presence: {e}")

    if not Config.TEST_GUILD_ID:
        logger.error("TEST_GUILD_ID not set in environment variables")
        return

    try:
        bot.tree.copy_global_to(guild=discord.Object(id=Config.TEST_GUILD_ID))
        synced = await bot.tree.sync(guild=discord.Object(id=Config.TEST_GUILD_ID))
        logger.info(f"Synced {len(synced)} command(s) to guild {Config.TEST_GUILD_ID}")
    except discord.Forbidden:
        logger.error(f"Permission denied syncing commands to guild {Config.TEST_GUILD_ID}")
    except discord.HTTPException as e:
        logger.error(f"HTTP error syncing commands: {e}")
    except Exception as e:
        logger.error(f"Unexpected error syncing commands: {type(e).__name__}: {e}")

def validate_config() -> bool:
    """Validate required configuration before starting bot."""
    return Config.load()

async def main():
    try:
        if not validate_config():
            logger.error("Configuration validation failed. Exiting.")
            return

        await HTTP.open()
        logger.info("HTTP session initialized")

        async with bot:
            await load_cogs()
            logger.info("Starting bot...")
            await bot.start(Config.DISCORD_TOKEN)

    except discord.LoginFailure:
        logger.error("Invalid DISCORD_TOKEN provided")
    except discord.HTTPException as e:
        logger.error(f"Discord HTTP error: {e}")
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
    except Exception as e:
        logger.critical(f"Critical error: {type(e).__name__}: {e}")
