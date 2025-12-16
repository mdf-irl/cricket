import json
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands

from config import Config
from logger_config import get_logger

logger = get_logger(__name__)

BASE_IMG_PREFIX = Config.PRIVATE_URL_BASE
MAX_PAGES_BY_SOURCE = {
    "XPHB": 384,
    "XGE": 193,
    "TCE": 192,
}
SOURCE_DISPLAY = {
    "XPHB": "Player's Handbook (2024)",
    "XGE": "Xanathar's Guide to Everything (2017)",
    "TCE": "Tasha's Cauldron of Everything (2020)",
}


class SpellPageView(discord.ui.View):
    """View for displaying spell page images with navigation."""
    
    def __init__(self, user_id: int, spell_name: str, source: str, page: int, max_pages: int = 400):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.spell_name = spell_name
        self.source = source
        self.source_lower = source.lower()
        self.current_page = page
        self.max_pages = max_pages
        
        # Add link button dynamically (can't use decorator with url)
        self.link_button = discord.ui.Button(
            label="Open",
            style=discord.ButtonStyle.link,
            url=self._current_url()
        )
        self.add_item(self.link_button)
        
        self._update_buttons()
    
    def _current_url(self) -> str:
        return f"{BASE_IMG_PREFIX}{self.source_lower}/{self.current_page}.jpg"
    
    def _current_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🐉 D&D Spell: {self.spell_name}",
            color=discord.Color.red()
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
        if self.current_page > 1:
            self.prev_button.label = f"◀ {self.current_page - 1}"
        else:
            self.prev_button.label = "◀"
        
        if self.current_page < self.max_pages:
            self.next_button.label = f"{self.current_page + 1} ▶"
        else:
            self.next_button.label = "▶"
        
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


class SpellPage(commands.Cog):
    """D&D 5e spell page viewer cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spells_data: dict[str, list[dict]] = self._load_all_spells()
        self.spell_entries: list[tuple[str, str]] = self._build_spell_entries()
    
    def _load_all_spells(self) -> dict[str, list[dict]]:
        """Load spells from all JSON files in data/spells folder."""
        spells_dict = {}
        spells_dir = Path("data/spells")
        
        if not spells_dir.exists():
            logger.warning(f"Spells directory not found: {spells_dir}")
            return {}
        
        try:
            for spell_file in sorted(spells_dir.glob("*.json")):
                with open(spell_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                
                for spell in raw_data.get("spell", []):
                    name = spell.get("name", "")
                    source = spell.get("source", "")
                    page = spell.get("page")
                    
                    if name and source and page is not None:
                        spell_key = name.lower()
                        
                        spell_info = {
                            "name": name,
                            "source": source,
                            "page": page,
                        }
                        
                        if spell_key not in spells_dict:
                            spells_dict[spell_key] = []
                        spells_dict[spell_key].append(spell_info)
            
            total = sum(len(v) for v in spells_dict.values())
            logger.info(f"Loaded {total} spells from {spells_dir}")
            return spells_dict
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading spells from {spells_dir}: {e}")
            return {}
    
    def _build_spell_entries(self) -> list[tuple[str, str]]:
        """Pre-compute spell entries for autocomplete as 'name (source)'."""
        entries: list[tuple[str, str]] = []
        
        for key, versions in self.spells_dict.items():
            # If multiple sources exist, add each version separately
            if isinstance(versions, list) and len(versions) > 1:
                for v in sorted(versions, key=lambda x: x.get("source", "")):
                    display_name = f"{v.get('name')} ({v.get('source')})"
                    # Use composite value to identify the exact version
                    entries.append((display_name, f"{key}|{v.get('source')}"))
            else:
                v = versions[0] if isinstance(versions, list) else versions
                display_name = f"{v.get('name')} ({v.get('source')})"
                entries.append((display_name, key))
        
        entries.sort(key=lambda x: x[0])
        return entries
    
    @property
    def spells_dict(self) -> dict[str, list[dict]]:
        """Property to access spells_data."""
        return self.spells_data
    
    @app_commands.command(name="spell", description="View a spell page from D&D 5e books.")
    @app_commands.describe(name="The spell name to view")
    async def spell(self, interaction: discord.Interaction, name: str) -> None:
        """Display a spell's page as an image."""
        await interaction.response.defer()
        
        if not self.spells_data:
            await interaction.followup.send(
                "❌ Could not load spell data. Please try again later.",
                ephemeral=True
            )
            return
        
        # Parse composite value if it contains source
        spell_key = name.lower().strip()
        selected_source = None
        if "|" in spell_key:
            parts = spell_key.split("|", 1)
            spell_key = parts[0]
            selected_source = parts[1].upper()
        
        if spell_key not in self.spells_data:
            available = ", ".join(sorted(list(self.spells_data.keys())[:5]))
            await interaction.followup.send(
                f"❌ Spell **{name}** not found.\n\n**Example spells**: {available}...",
                ephemeral=True
            )
            return
        
        # Get the spell info (handle multiple sources)
        versions = self.spells_data[spell_key]
        if not isinstance(versions, list):
            versions = [versions]
        
        # If a specific source was selected via autocomplete, prefer that version
        if selected_source:
            spell_info = next((v for v in versions if v.get("source", "").upper() == selected_source), versions[0])
        else:
            spell_info = versions[0]
        
        spell_name = spell_info.get("name", name)
        source = spell_info.get("source", "Unknown")
        page = spell_info.get("page", 1)
        max_pages = MAX_PAGES_BY_SOURCE.get(source.upper(), 400)
        
        # Create view with link button
        view = SpellPageView(
            user_id=interaction.user.id,
            spell_name=spell_name,
            source=source,
            page=page,
            max_pages=max_pages,
        )
        
        await interaction.followup.send(embed=view._current_embed(), view=view)
        logger.info(f"spell command used by {interaction.user} (ID: {interaction.user.id}) for: {spell_name}")
    
    @spell.autocomplete("name")
    async def spell_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete spell names as 'name (source)'."""
        if not self.spells_data:
            return []
        
        matches = [
            app_commands.Choice(name=display, value=key)
            for display, key in self.spell_entries
            if current.lower() in display.lower() or current.lower() in key.lower()
        ]
        return matches[:25]


async def setup(bot: commands.Bot) -> None:
    """Load the SpellPage cog."""
    await bot.add_cog(SpellPage(bot))
