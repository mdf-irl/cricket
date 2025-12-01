import discord
import json
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from typing import Optional

from discord.ext import commands
from discord import app_commands

from logger_config import get_logger
from http_manager import HTTP

logger = get_logger(__name__)


DATA_FILE = Path("data") / "character_map.json"


def clean_url(url: str) -> str:
    if not url or not url.startswith(("http://", "https://")):
        return ""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query="", fragment=""))


async def fetch_character(char_id: int) -> Optional[dict]:
    """Fetch a character from D&D Beyond via the shared HTTP manager.

    Returns parsed data or None on failure.
    """
    url = f"https://character-service.dndbeyond.com/character/v5/character/{char_id}"
    try:
        data = await HTTP.fetch_json(url)
    except Exception as e:
        logger.error(f"HTTP error fetching character {char_id}: {e}")
        return None

    if not isinstance(data, dict):
        logger.warning(f"Unexpected response for character {char_id}")
        return None

    char_data = data.get("data", {})
    avatar = (
        char_data.get("decorations", {}).get("avatarUrl") or
        char_data.get("avatarUrl") or
        char_data.get("portraitAvatarUrl", "")
    )

    classes = char_data.get("classes", [])
    if classes:
        class_info = " / ".join(
            f"{c.get('definition', {}).get('name', 'Unknown')} ({c.get('level', 0)})"
            for c in classes
        )
    else:
        class_info = "No Class Info"

    return {
        "name": char_data.get("name", "Unknown"),
        "race": char_data.get("race", {}).get("fullName", "Unknown Race"),
        "level": sum(int(c.get("level", 0)) for c in classes),
        "classes": class_info,
        "avatar": clean_url(avatar)
    }


class Sheet(commands.Cog):
    """Cog to map Discord users to D&D Beyond character IDs and display a sheet."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.characters = self.load_character_data()

    @staticmethod
    def load_character_data() -> dict[int, int]:
        if not DATA_FILE.exists():
            logger.warning(f"Missing character map file: {DATA_FILE}")
            return {}
        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                raw = json.load(f)
                return {int(uid): int(cid) for uid, cid in raw.items()}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {DATA_FILE}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading {DATA_FILE}: {type(e).__name__}: {e}")
            return {}

    @app_commands.command(name="sheet", description="Get a user's D&D Beyond character sheet")
    async def sheet(self, interaction: discord.Interaction, user: discord.User) -> None:
        """Show a user's linked D&D Beyond character sheet (if mapped)."""
        char_id = self.characters.get(user.id)
        if not char_id:
            await interaction.response.send_message(
                f"❌ No D&D sheet stored for **{user.display_name}**.",
                ephemeral=True,
            )
            logger.info(f"Sheet command: no mapping found for {user} (requested by {interaction.user})")
            return

        await interaction.response.defer()

        info = await fetch_character(char_id)
        if not info:
            await interaction.followup.send(
                "⚠️ Could not fetch character. Sheet may be private or API down.",
                ephemeral=True,
            )
            logger.warning(f"Failed to fetch character {char_id} for user {user}")
            return

        embed = discord.Embed(
            title=f"⚔️ {info['name']}",
            description=f"Level **{info['level']}** {info['race']} — {info['classes']}",
            url=f"https://www.dndbeyond.com/characters/{char_id}",
            color=discord.Color.blue(),
        )

        if info.get("avatar"):
            embed.set_thumbnail(url=info["avatar"])

        await interaction.followup.send(embed=embed)
        logger.info(f"Sheet command executed by {interaction.user} for {user} -> character {char_id}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Sheet(bot))
