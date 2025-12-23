import asyncio
import json
import os
import platform
from pathlib import Path
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from http_manager import HTTP
from logger_config import get_logger

logger = get_logger(__name__)

IMAGES_DIR = os.path.join("data", "images")
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
CHARACTER_MAP_FILE = os.path.join("data", "character_map.json")


class Admin(commands.Cog):
    """Administrator-only maintenance commands."""

    admin_group = app_commands.Group(
        name="admin",
        description="Admin-only bot controls",
        default_permissions=discord.Permissions(administrator=True),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _reload_extension_safe(self, module_name: str) -> bool:
        """Reload or load an extension; return success status."""
        try:
            if module_name in self.bot.extensions:
                await self.bot.reload_extension(module_name)
            else:
                await self.bot.load_extension(module_name)
            return True
        except Exception as e:
            logger.warning("Failed to load/reload %s: %s: %s", module_name, type(e).__name__, e)
            return False

    def _prepare_image_save(self, raw_name: str, suffix: str) -> tuple[Path | None, str | None, str | None]:
        """Normalize name, validate extension, and ensure target path exists."""
        name = raw_name.strip().lower()
        if not name or len(name) > 50:
            return None, None, "❌ Name must be 1-50 characters."

        if suffix not in ALLOWED_EXTENSIONS:
            return None, None, f"❌ Image must use one of: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

        images_cog = self.bot.get_cog("Images")
        if images_cog and name in getattr(images_cog, "images", {}):
            return None, None, f"❌ `{name}` already exists."

        images_path = Path(IMAGES_DIR)
        try:
            images_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error("Failed to create images dir: %s: %s", type(e).__name__, e)
            return None, None, "❌ Could not create images directory."

        return images_path / f"{name}{suffix}", name, None

    def _load_character_map_file(self) -> dict | None:
        """Load character map JSON, returning None on unrecoverable errors."""
        try:
            with open(CHARACTER_MAP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            logger.error("Error reading character map: %s", e)
            return None

    def _save_character_map_file(self, character_map: dict) -> bool:
        """Persist character map JSON to disk."""
        try:
            with open(CHARACTER_MAP_FILE, "w", encoding="utf-8") as f:
                json.dump(character_map, f, indent=4)
            return True
        except Exception as e:
            logger.error("Failed to save character map: %s: %s", type(e).__name__, e)
            return False

    async def _ensure_admin(self, interaction: discord.Interaction) -> bool:
        """Validate the interaction is from a guild admin."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.", ephemeral=True
            )
            return False

        perms = interaction.user.guild_permissions if hasattr(interaction.user, "guild_permissions") else None
        if not perms or not perms.administrator:
            await interaction.response.send_message(
                "❌ You must be a server administrator to use this command.", ephemeral=True
            )
            return False
        return True

    @admin_group.command(name="reboot", description="Reboot the host system.")
    async def reboot(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        # Choose the appropriate reboot command for the current platform
        if os.name == "nt":
            cmd = ["shutdown", "/r", "/t", "5", "/f"]
        else:
            cmd = ["sudo", "reboot"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            logger.warning("Reboot command issued by %s (ID: %s)", interaction.user, interaction.user.id)
            await interaction.followup.send("🔄 Reboot command issued. Host will restart shortly.", ephemeral=True)
            await proc.wait()
        except Exception as e:
            logger.error("Failed to execute reboot: %s: %s", type(e).__name__, e)
            await interaction.followup.send(
                "❌ Failed to issue reboot command.", ephemeral=True
            )

    @admin_group.command(name="quit", description="Shut down the bot process.")
    async def quit(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        logger.warning("Bot shutdown requested by %s (ID: %s)", interaction.user, interaction.user.id)
        await interaction.followup.send("🛑 Bot is shutting down now.", ephemeral=True)
        await self.bot.close()

    @admin_group.command(name="reloadcogs", description="Reload all bot cogs.")
    async def reloadcogs(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        cogs_dir = Path("./cogs")
        if not cogs_dir.exists():
            await interaction.followup.send("❌ ./cogs directory not found.", ephemeral=True)
            return

        reloaded = 0
        loaded_new = 0
        failed = 0
        failed_cogs: list[str] = []

        for file in sorted(cogs_dir.glob("*.py")):
            if file.stem.startswith("_"):
                continue

            module_name = f"cogs.{file.stem}"
            try:
                if module_name in self.bot.extensions:
                    await self.bot.reload_extension(module_name)
                    reloaded += 1
                    logger.info(f"Reloaded cog: {module_name}")
                else:
                    await self.bot.load_extension(module_name)
                    loaded_new += 1
                    logger.info(f"Loaded new cog: {module_name}")
            except Exception as e:
                failed += 1
                failed_cogs.append(f"{module_name} ({type(e).__name__})")
                logger.error(f"Failed to load/reload cog {module_name}: {type(e).__name__}: {e}")

        status_parts = [f"✅ Reloaded {reloaded} cogs", f"✅ Loaded {loaded_new} new cogs"]
        if failed > 0:
            status_parts.append(f"⚠️ Failed to load/reload {failed} cogs:\n" + "\n".join(failed_cogs))
        status = "\n".join(status_parts)

        logger.warning(
            "Cog reload issued by %s (ID: %s): %s reloaded, %s new, %s failed",
            interaction.user,
            interaction.user.id,
            reloaded,
            loaded_new,
            failed,
        )
        await interaction.followup.send(status, ephemeral=True)

    @admin_group.command(name="reloadconfig", description="Reload the bot configuration.")
    async def reloadconfig(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            if Config.load():
                status = "✅ Configuration reloaded successfully."
                logger.warning(f"Config reload issued by {interaction.user} (ID: {interaction.user.id}): success")
            else:
                status = "⚠️ Configuration reload failed validation. Check logs for details."
                logger.warning(f"Config reload issued by {interaction.user} (ID: {interaction.user.id}): validation failed")
        except Exception as e:
            status = f"❌ Configuration reload failed: {type(e).__name__}: {e}"
            logger.error(f"Config reload failed: {type(e).__name__}: {e}")

        await interaction.followup.send(status, ephemeral=True)

    @admin_group.command(name="testsheetproxy", description="Check if the sheet proxy is reachable.")
    async def testsheetproxy(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        base = getattr(Config, "SHEET_PROXY_BASE", None)
        if not base:
            await interaction.followup.send("❌ SHEET_PROXY_BASE is not configured.", ephemeral=True)
            return

        url = f"{base.rstrip('/')}/health"
        try:
            data = await HTTP.fetch_json(url)
            status_val = data.get("status") if isinstance(data, dict) else str(data)
            await interaction.followup.send(
                f"✅ Sheet proxy reachable at {url}\nStatus: {status_val}",
                ephemeral=True,
            )
            logger.info("Sheet proxy health OK at %s", url)
        except Exception as e:
            logger.warning("Sheet proxy health check failed: %s: %s", type(e).__name__, e)
            await interaction.followup.send(
                f"❌ Sheet proxy unreachable at {url}: {type(e).__name__}",
                ephemeral=True,
            )

    @admin_group.command(name="addimagebyurl", description="Add an image to the gallery by URL.")
    @app_commands.describe(name="Name to save the image as", url="Direct image URL")
    async def addimagebyurl(self, interaction: discord.Interaction, name: str, url: str) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix.lower()

        filepath, normalized_name, error = self._prepare_image_save(name, suffix)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        try:
            data = await HTTP.fetch_bytes(url)
        except Exception as e:
            logger.error(f"Failed to fetch image URL {url}: {type(e).__name__}: {e}")
            await interaction.followup.send("❌ Failed to download the image.", ephemeral=True)
            return

        max_size = 10 * 1024 * 1024
        if len(data) > max_size:
            await interaction.followup.send("❌ File too large (max 10 MB).", ephemeral=True)
            return

        try:
            filepath.write_bytes(data)

            await self._reload_extension_safe("cogs.images")
            await interaction.followup.send(
                f"✅ Image `{normalized_name}` added. Use `/image {normalized_name}` to send it.",
                ephemeral=True,
            )
            logger.info(
                "Image '%s' added by URL by %s (ID: %s)",
                normalized_name,
                interaction.user,
                interaction.user.id,
            )
        except Exception as e:
            logger.error(f"Failed to save image {filepath}: {type(e).__name__}: {e}")
            await interaction.followup.send("❌ Failed to save image.", ephemeral=True)

    @admin_group.command(name="addimagebyattachment", description="Add an image to the gallery by attachment.")
    @app_commands.describe(name="Name to save the image as", image="Image attachment")
    async def addimagebyattachment(self, interaction: discord.Interaction, name: str, image: discord.Attachment) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        suffix = Path(image.filename).suffix.lower()
        filepath, normalized_name, error = self._prepare_image_save(name, suffix)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        max_size = 10 * 1024 * 1024
        if image.size and image.size > max_size:
            await interaction.followup.send("❌ File too large (max 10 MB).", ephemeral=True)
            return
        try:
            await image.save(filepath)

            await self._reload_extension_safe("cogs.images")
            await interaction.followup.send(
                f"✅ Image `{normalized_name}` added. Use `/image {normalized_name}` to send it.",
                ephemeral=True,
            )
            logger.info(
                "Image '%s' added by attachment by %s (ID: %s)",
                normalized_name,
                interaction.user,
                interaction.user.id,
            )
        except Exception as e:
            logger.error(f"Failed to save image {filepath}: {type(e).__name__}: {e}")
            await interaction.followup.send("❌ Failed to save image.", ephemeral=True)

    @admin_group.command(name="deleteimage", description="Delete an image from the gallery.")
    @app_commands.describe(name="Name of the image to delete")
    async def deleteimage(self, interaction: discord.Interaction, name: str) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        name = name.strip().lower()
        if not name:
            await interaction.followup.send("❌ Please provide a valid image name.", ephemeral=True)
            return

        images_cog = self.bot.get_cog("Images")
        if not images_cog or name not in getattr(images_cog, "images", {}):
            await interaction.followup.send(f"❌ Image `{name}` not found in gallery.", ephemeral=True)
            return

        # Get the actual filename with extension
        filename = images_cog.images.get(name)
        if not filename:
            await interaction.followup.send(f"❌ Image `{name}` not found.", ephemeral=True)
            return

        filepath = Path(IMAGES_DIR) / filename

        try:
            if filepath.exists():
                filepath.unlink()
                logger.info(f"Deleted image file: {filepath}")

            await self._reload_extension_safe("cogs.images")
            await interaction.followup.send(
                f"✅ Image `{name}` deleted from gallery.",
                ephemeral=True,
            )
            logger.info(f"Image '{name}' deleted by {interaction.user} (ID: {interaction.user.id})")
        except Exception as e:
            logger.error(f"Failed to delete image {filepath}: {type(e).__name__}: {e}")
            await interaction.followup.send("❌ Failed to delete image.", ephemeral=True)

    @admin_group.command(name="addsheet", description="Add a user to the character sheet map.")
    @app_commands.describe(user="Discord user to add", character_id="D&D Beyond character ID")
    async def addsheet(self, interaction: discord.Interaction, user: discord.Member, character_id: str) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        # Validate character ID is numeric
        if not character_id.strip().isdigit():
            await interaction.followup.send("❌ Character ID must be numeric.", ephemeral=True)
            return

        character_id = character_id.strip()

        character_map = self._load_character_map_file()
        if character_map is None:
            await interaction.followup.send("❌ Failed to read character map.", ephemeral=True)
            return

        # Add or update the mapping
        user_id_str = str(user.id)
        character_map[user_id_str] = character_id

        if not self._save_character_map_file(character_map):
            await interaction.followup.send("❌ Failed to save character map.", ephemeral=True)
            return

        await self._reload_extension_safe("cogs.sheet")
        await interaction.followup.send(
            f"✅ Added {user.mention} → Character ID `{character_id}`",
            ephemeral=True,
        )
        logger.info(
            "Character mapping added for %s (ID: %s) → %s by %s",
            user,
            user.id,
            character_id,
            interaction.user,
        )

    @admin_group.command(name="deletesheet", description="Remove a user from the character sheet map.")
    @app_commands.describe(user="Discord user to remove")
    async def deletesheet(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        character_map = self._load_character_map_file()
        if character_map is None:
            await interaction.followup.send("❌ Failed to read character map.", ephemeral=True)
            return

        # Check if user exists in map
        user_id_str = str(user.id)
        if user_id_str not in character_map:
            await interaction.followup.send(f"❌ {user.mention} is not in the character map.", ephemeral=True)
            return

        # Remove the mapping
        removed_char_id = character_map.pop(user_id_str)

        if not self._save_character_map_file(character_map):
            await interaction.followup.send("❌ Failed to save character map.", ephemeral=True)
            return

        await self._reload_extension_safe("cogs.sheet")
        await interaction.followup.send(
            f"✅ Removed {user.mention} (Character ID `{removed_char_id}`)",
            ephemeral=True,
        )
        logger.info(
            "Character mapping removed for %s (ID: %s) by %s",
            user,
            user.id,
            interaction.user,
        )


async def setup(bot: commands.Bot) -> None:
    """Load the Admin cog."""
    await bot.add_cog(Admin(bot))
