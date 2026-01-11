import json
from pathlib import Path
from typing import Literal

import discord
from discord.ext import commands
from discord import app_commands

from config import Config
from logger_config import get_logger
from constants import (
    MAX_PAGES_BY_SOURCE,
    SOURCE_DISPLAY,
    SPELLS_DIR,
    MONSTERS_DIR,
    ITEMS_DIR,
    SPECIES_DIR,
    CLASSES_DIR,
)

logger = get_logger(__name__)

BASE_IMG_PREFIX = Config.PRIVATE_URL_BASE


class PageView(discord.ui.View):
    """Generic view for displaying D&D page images with navigation."""
    
    def __init__(
        self,
        user_id: int,
        item_name: str,
        source: str,
        page: int,
        max_pages: int = 400,
        title_emoji: str = "📖",
        title_prefix: str = "D&D",
        color: discord.Color = discord.Color.blue(),
    ):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.item_name = item_name
        self.source = source
        self.source_lower = source.lower()
        self.current_page = page
        self.max_pages = max_pages
        self.title_emoji = title_emoji
        self.title_prefix = title_prefix
        self.color = color
        
        # Add link button dynamically (can't use decorator with url)
        self.link_button = discord.ui.Button(
            label="Open Full-Sized",
            style=discord.ButtonStyle.link,
            url=self._current_url()
        )
        self.add_item(self.link_button)
        
        self._update_buttons()
    
    def _current_url(self) -> str:
        return f"{BASE_IMG_PREFIX}{self.source_lower}/{self.current_page}.jpg"
    
    def _current_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.title_emoji} {self.title_prefix}: {self.item_name}",
            color=self.color
        )
        embed.set_image(url=self._current_url())
        source_display = SOURCE_DISPLAY.get(self.source.upper(), self.source)
        embed.set_footer(text=f"📖 {source_display}, page {self.current_page}")
        return embed
    
    def _update_buttons(self) -> None:
        """Update button disabled state and labels based on current page."""
        self.prev_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.max_pages
        
        # Update labels with target page numbers
        self.prev_button.label = f"◀ {self.current_page - 1}" if self.current_page > 1 else "◀"
        self.next_button.label = f"{self.current_page + 1} ▶" if self.current_page < self.max_pages else "▶"
        
        # Update link button URL
        self.link_button.url = self._current_url()
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only allow the invoking user to use buttons."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the command invoker can use these buttons.", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            self._update_buttons()
        await interaction.response.edit_message(embed=self._current_embed(), view=self)
    
    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.max_pages:
            self.current_page += 1
            self._update_buttons()
        await interaction.response.edit_message(embed=self._current_embed(), view=self)


class BookPage(commands.Cog):
    """D&D 5e spell and monster page viewer cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spells_data: dict[str, list[dict]] = self._load_data(SPELLS_DIR, "spell")
        self.spell_entries: list[tuple[str, str]] = self._build_entries(self.spells_data)
        self.monsters_data: dict[str, list[dict]] = self._load_data(MONSTERS_DIR, "monster")
        self.monster_entries: list[tuple[str, str]] = self._build_entries(self.monsters_data)
        self.items_data: dict[str, list[dict]] = self._load_data(ITEMS_DIR, "item")
        self.item_entries: list[tuple[str, str]] = self._build_entries(self.items_data)
        self.species_data: dict[str, list[dict]] = self._load_data(SPECIES_DIR, "species")
        self.species_entries: list[tuple[str, str]] = self._build_entries(self.species_data)
        self.classes_data: dict[str, list[dict]] = self._load_data(CLASSES_DIR, "class")
        self.class_entries: list[tuple[str, str]] = self._build_entries(self.classes_data)
    
    def _load_data(self, folder: Path, data_key: str) -> dict[str, list[dict]]:
        """Load data from all JSON files in specified folder."""
        data_dict = {}
        data_dir = folder
        
        if not data_dir.exists():
            logger.warning(f"Directory not found: {data_dir}")
            return {}
        
        try:
            for data_file in sorted(data_dir.glob("*.json")):
                with open(data_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                
                for item in raw_data.get(data_key, []):
                    name = item.get("name", "")
                    source = item.get("source", "")
                    page = item.get("page")
                    
                    if name and source and page is not None:
                        item_key = name.lower()
                        
                        item_info = {
                            "name": name,
                            "source": source,
                            "page": page,
                        }
                        
                        if item_key not in data_dict:
                            data_dict[item_key] = []
                        data_dict[item_key].append(item_info)
            
            total = sum(len(v) for v in data_dict.values())
            logger.info(f"Loaded {total} {data_key}s from {data_dir}")
            return data_dict
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading {data_key}s from {data_dir}: {e}")
            return {}
    
    def _build_entries(self, data_dict: dict[str, list[dict]]) -> list[tuple[str, str]]:
        """Pre-compute entries for autocomplete as 'name (source)'."""
        entries: list[tuple[str, str]] = []
        
        for key, versions in data_dict.items():
            # If multiple sources exist, add each version separately
            if isinstance(versions, list) and len(versions) > 1:
                for v in sorted(versions, key=lambda x: x.get("source", "")):
                    display_name = f"{v.get('name')} ({v.get('source')})"
                    entries.append((display_name, f"{key}|{v.get('source')}"))
            else:
                v = versions[0] if isinstance(versions, list) else versions
                display_name = f"{v.get('name')} ({v.get('source')})"
                entries.append((display_name, key))
        
        entries.sort(key=lambda x: x[0])
        return entries
    
    async def _handle_page_command(
        self,
        interaction: discord.Interaction,
        name: str,
        data_dict: dict[str, list[dict]],
        item_type: Literal["spell", "monster", "item", "species", "class"],
    ) -> None:
        """Generic handler for spell and monster page commands."""
        await interaction.response.defer()
        
        if not data_dict:
            await interaction.followup.send(
                f"❌ Could not load {item_type} data. Please try again later.",
                ephemeral=True
            )
            return
        
        # Parse composite value if it contains source
        item_key = name.lower().strip()
        selected_source = None
        if "|" in item_key:
            parts = item_key.split("|", 1)
            item_key = parts[0]
            selected_source = parts[1].upper()
        
        if item_key not in data_dict:
            available = ", ".join(sorted(list(data_dict.keys())[:5]))
            await interaction.followup.send(
                f"❌ {item_type.capitalize()} **{name}** not found.\n\n**Examples**: {available}...",
                ephemeral=True
            )
            return
        
        # Get the item info (handle multiple sources)
        versions = data_dict[item_key]
        if not isinstance(versions, list):
            versions = [versions]
        
        # If a specific source was selected via autocomplete, prefer that version
        if selected_source:
            item_info = next((v for v in versions if v.get("source", "").upper() == selected_source), versions[0])
        else:
            item_info = versions[0]
        
        item_name = item_info.get("name", name)
        source = item_info.get("source", "Unknown")
        page = item_info.get("page", 1)
        max_pages = MAX_PAGES_BY_SOURCE.get(source.upper(), 400)
        
        # Create view with appropriate styling
        if item_type == "spell":
            view = PageView(
                user_id=interaction.user.id,
                item_name=item_name,
                source=source,
                page=page,
                max_pages=max_pages,
                title_emoji="🐉",
                title_prefix="D&D Spell",
                color=discord.Color.blue(),
            )
        elif item_type == "monster":
            view = PageView(
                user_id=interaction.user.id,
                item_name=item_name,
                source=source,
                page=page,
                max_pages=max_pages,
                title_emoji="🐉",
                title_prefix="D&D Monster",
                color=discord.Color.red(),
            )
        elif item_type == "item":
            view = PageView(
                user_id=interaction.user.id,
                item_name=item_name,
                source=source,
                page=page,
                max_pages=max_pages,
                title_emoji="🐉",
                title_prefix="D&D Item",
                color=discord.Color.gold(),
            )
        elif item_type == "class":
            view = PageView(
                user_id=interaction.user.id,
                item_name=item_name,
                source=source,
                page=page,
                max_pages=max_pages,
                title_emoji="🐉",
                title_prefix="D&D Class",
                color=discord.Color.purple(),
            )
        else:  # species
            view = PageView(
                user_id=interaction.user.id,
                item_name=item_name,
                source=source,
                page=page,
                max_pages=max_pages,
                title_emoji="🐉",
                title_prefix="D&D Species",
                color=discord.Color.green(),
            )
        
        await interaction.followup.send(embed=view._current_embed(), view=view)
        logger.info(f"{item_type} command used by {interaction.user} (ID: {interaction.user.id}) for: {item_name}")
    
    @app_commands.command(name="spell", description="View a spell page from D&D 5e books.")
    @app_commands.describe(name="The spell name to view")
    async def spell(self, interaction: discord.Interaction, name: str) -> None:
        """Display a spell's page as an image."""
        await self._handle_page_command(interaction, name, self.spells_data, "spell")
    
    @spell.autocomplete("name")
    async def spell_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete spell names as 'name (source)'."""
        return self._autocomplete(current, self.spell_entries, self.spells_data)
    
    @app_commands.command(name="monster", description="View a monster page from D&D 5e books.")
    @app_commands.describe(name="The monster name to view")
    async def monster(self, interaction: discord.Interaction, name: str) -> None:
        """Display a monster's page as an image."""
        await self._handle_page_command(interaction, name, self.monsters_data, "monster")
    
    @monster.autocomplete("name")
    async def monster_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete monster names as 'name (source)'."""
        return self._autocomplete(current, self.monster_entries, self.monsters_data)

    @app_commands.command(name="item", description="View an item page from D&D 5e books.")
    @app_commands.describe(name="The item name to view")
    async def item(self, interaction: discord.Interaction, name: str) -> None:
        """Display an item's page as an image."""
        await self._handle_page_command(interaction, name, self.items_data, "item")

    @item.autocomplete("name")
    async def item_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete item names as 'name (source)'."""
        return self._autocomplete(current, self.item_entries, self.items_data)
    @app_commands.command(name="species", description="View a species page from D&D 5e books.")
    @app_commands.describe(name="The species name to view")
    async def species(self, interaction: discord.Interaction, name: str) -> None:
        """Display a species's page as an image."""
        await self._handle_page_command(interaction, name, self.species_data, "species")

    @species.autocomplete("name")
    async def species_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete species names as 'name (source)'."""  
        return self._autocomplete(current, self.species_entries, self.species_data)

    @app_commands.command(name="class", description="View a class page from D&D 5e books.")
    @app_commands.describe(name="The class name to view")
    async def class_cmd(self, interaction: discord.Interaction, name: str) -> None:
        """Display a class's page as an image."""
        await self._handle_page_command(interaction, name, self.classes_data, "class")

    @class_cmd.autocomplete("name")
    async def class_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete class names as 'name (source)'."""
        return self._autocomplete(current, self.class_entries, self.classes_data)

    def _autocomplete(
        self,
        current: str,
        entries: list[tuple[str, str]],
        data_dict: dict[str, list[dict]],
    ) -> list[app_commands.Choice[str]]:
        """Generic autocomplete handler."""
        if not data_dict:
            return []
        
        matches = [
            app_commands.Choice(name=display, value=key)
            for display, key in entries
            if current.lower() in display.lower() or current.lower() in key.lower()
        ]
        return matches[:25]


async def setup(bot: commands.Bot) -> None:
    """Load the BookPage cog."""
    await bot.add_cog(BookPage(bot))
