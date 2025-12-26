import json

import discord
from discord.ext import commands
from discord import app_commands

from logger_config import get_logger
from constants import BOOKS_FILE

logger = get_logger(__name__)


class Books(commands.Cog):
    """D&D books reference cog with links to official sources."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.books_data = self.load_books_data()

    def load_books_data(self) -> dict:
        """Load books data from JSON file with error handling."""
        try:
            with open(BOOKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Loaded books data from {BOOKS_FILE}")
                return data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading {BOOKS_FILE}: {type(e).__name__}: {e}")
            return {}

    def format_books(self, category: dict) -> list[str]:
        """Format book category data into markdown lines.
        
        Args:
            category: Dictionary of books with editions and links.
            
        Returns:
            List of formatted markdown strings.
        """
        lines = []
        for book, editions in category.items():
            edition_str = " | ".join(
                f"{year} [**DDB**]({links.get('ddb', '#')})/[**PDF**]({links.get('pdf', '#')})"
                for year, links in editions.items()
            )
            lines.append(f"{book} ({edition_str})")
        return lines

    @app_commands.command(name="books", description="Show links to official D&D books.")
    async def books(self, interaction: discord.Interaction) -> None:
        """Display D&D books with links to D&D Beyond and PDF sources."""
        if not self.books_data:
            await interaction.response.send_message(
                "❌ Books data unavailable. Please try again later.",
                ephemeral=True
            )
            logger.warning("Books command invoked but data is empty")
            return

        try:
            core = self.books_data.get("core_books", {})
            expansions = self.books_data.get("expansions", {})

            desc_lines = [
                "📘 **Core Books**",
                *self.format_books(core),
                "",
                "📚 **Expansion Books**",
                *self.format_books(expansions)
            ]

            embed = discord.Embed(
                title="Dungeons & Dragons 5th Edition Books",
                description="\n".join(desc_lines),
                color=discord.Color.pink()
            )

            await interaction.response.send_message(embed=embed)
            logger.info(f"Books command executed by {interaction.user}")
        except Exception as e:
            logger.error(f"Error in books command: {type(e).__name__}: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again later.",
                ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Books cog."""
    await bot.add_cog(Books(bot))
