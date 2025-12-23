import os
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands

from logger_config import get_logger

logger = get_logger(__name__)


class Images(commands.Cog):
    """Image gallery cog for serving custom images and GIFs."""
    
    IMAGES_DIR = os.path.join("data", "images")
    ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.images: dict[str, str] = self._load_images()
        self.image_entries: list[tuple[str, str]] = self._build_entries()
    
    def _load_images(self) -> dict[str, str]:
        """Load all image files from the images directory.
        
        Returns:
            Dictionary mapping lowercase filename (without extension) to full filename.
        """
        images_dict = {}
        images_path = Path(self.IMAGES_DIR)
        
        if not images_path.exists():
            logger.warning(f"Images directory not found: {images_path}")
            return {}
        
        try:
            for image_file in images_path.iterdir():
                if image_file.is_file() and image_file.suffix.lower() in self.ALLOWED_EXTENSIONS:
                    # Store without extension as key
                    name_key = image_file.stem.lower()
                    images_dict[name_key] = image_file.name
            
            logger.info(f"Loaded {len(images_dict)} images from {self.IMAGES_DIR}")
            return images_dict
        except Exception as e:
            logger.error(f"Error loading images from {images_path}: {type(e).__name__}: {e}")
            return {}
    
    def _build_entries(self) -> list[tuple[str, str]]:
        """Pre-compute entries for autocomplete."""
        entries = [
            (name, name) for name in sorted(self.images.keys())
        ]
        return entries
    
    @app_commands.command(name="image", description="Send an image or GIF from the gallery.")
    @app_commands.describe(name="The image name to send")
    async def image(self, interaction: discord.Interaction, name: str) -> None:
        """Send an image file from the gallery."""
        await interaction.response.defer()
        
        if not self.images:
            await interaction.followup.send(
                "❌ Image gallery is empty or unavailable.",
                ephemeral=True
            )
            return
        
        # Normalize input
        name_key = name.lower().strip()
        
        # Find the image
        if name_key not in self.images:
            await interaction.followup.send(
                f"❌ Image **{name}** not found in gallery.",
                ephemeral=True
            )
            logger.warning(f"Image '{name}' not found, requested by {interaction.user}")
            return
        
        # Get the full filename and path
        filename = self.images[name_key]
        filepath = os.path.join(self.IMAGES_DIR, filename)
        
        try:
            # Send the image file
            file = discord.File(filepath, filename=filename)
            await interaction.followup.send(file=file)
            logger.info(f"Image '{filename}' sent by {interaction.user} (ID: {interaction.user.id})")
        except FileNotFoundError:
            await interaction.followup.send(
                f"❌ Image file not found: {filename}",
                ephemeral=True
            )
            logger.error(f"Image file not found: {filepath}")
        except Exception as e:
            logger.error(f"Error sending image {filename}: {type(e).__name__}: {e}")
            await interaction.followup.send(
                "❌ An error occurred while sending the image.",
                ephemeral=True
            )
    
    @image.autocomplete("name")
    async def image_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete image names."""
        if not self.images:
            return []
        
        # Filter entries based on current input
        matches = [
            app_commands.Choice(name=display, value=key)
            for display, key in self.image_entries
            if current.lower() in display.lower()
        ]
        
        # Discord limits autocomplete to 25 choices
        return matches[:25]

    @app_commands.command(name="imagelist", description="Show all available images in the gallery.")
    async def imagelist(self, interaction: discord.Interaction) -> None:
        """Display a list of all available images."""
        await interaction.response.defer()
        
        if not self.images:
            await interaction.followup.send(
                "❌ Image gallery is empty or unavailable.",
                ephemeral=True
            )
            return
        
        # Sort image names
        sorted_images = sorted(self.images.keys())
        
        # Create embed with image list
        embed = discord.Embed(
            title="🖼️ Image Gallery",
            description=f"Total images: {len(sorted_images)}",
            color=discord.Color.blue()
        )
        
        # Split images into chunks for fields (Discord field value limit ~1024 chars)
        chunk_size = 50
        for i in range(0, len(sorted_images), chunk_size):
            chunk = sorted_images[i:i+chunk_size]
            images_text = ", ".join(f"`{img}`" for img in chunk)
            embed.add_field(name="** **", value=images_text, inline=False)
        
        embed.set_footer(text="Use /image <name> to send an image")
        await interaction.followup.send(embed=embed)
        logger.info(f"Image list viewed by {interaction.user} (ID: {interaction.user.id})")


async def setup(bot: commands.Bot) -> None:
    """Load the Images cog."""
    await bot.add_cog(Images(bot))
