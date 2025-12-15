import os
import json
import discord
from discord.ext import commands
from discord import app_commands

from logger_config import get_logger

logger = get_logger(__name__)

# School of Magic abbreviations to full names
SCHOOLS = {
    "A": "Abjuration",
    "C": "Conjuration",
    "D": "Divination",
    "E": "Enchantment",
    "V": "Evocation",
    "I": "Illusion",
    "N": "Necromancy",
    "T": "Transmutation",
}


class Spells(commands.Cog):
    """D&D 5e spells reference cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spells_data: dict[str, dict] = self._load_spells_data()

    def _load_spells_data(self) -> dict[str, dict]:
        """Load spells data from local JSON file."""
        try:
            file_path = os.path.join("data", "spells-xphb.json")
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                # Convert list format to dict by spell name (lowercase for case-insensitive lookup)
                spells_dict = {}
                for spell in raw_data.get("spell", []):
                    name = spell.get("name", "")
                    if name:
                        spells_dict[name.lower()] = spell
                logger.info(f"Loaded {len(spells_dict)} spells from spells-xphb.json")
                return spells_dict
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading spells-xphb.json: {e}")
            return {}

    def _format_level(self, level: int) -> str:
        """Convert level number to level name."""
        if level == 0:
            return "Cantrip"
        elif level == 1:
            return "1st Level"
        elif level == 2:
            return "2nd Level"
        elif level == 3:
            return "3rd Level"
        else:
            return f"{level}th Level"

    def _format_school(self, school_code: str) -> str:
        """Convert school code to full name."""
        return SCHOOLS.get(school_code, school_code)

    def _format_casting_time(self, time_data: list) -> str:
        """Format casting time from spell data."""
        if not time_data:
            return "Unknown"
        
        time_entry = time_data[0]
        number = time_entry.get("number", 1)
        unit = time_entry.get("unit", "action")
        
        # Capitalize unit and handle pluralization
        unit_str = unit.capitalize()
        if number > 1 and not unit_str.endswith("s"):
            unit_str += "s"
        
        return f"{number} {unit_str}" if number > 1 else unit_str

    def _format_range(self, range_data: dict) -> str:
        """Format range from spell data."""
        range_type = range_data.get("type", "unknown")
        
        if range_type == "self":
            return "Self"
        elif range_type == "point":
            distance = range_data.get("distance", {})
            amount = distance.get("amount", 0)
            dist_type = distance.get("type", "feet")
            return f"{amount} {dist_type.capitalize()}"
        elif range_type == "line":
            distance = range_data.get("distance", {})
            amount = distance.get("amount", 0)
            return f"{amount} feet (line)"
        elif range_type == "cone":
            distance = range_data.get("distance", {})
            amount = distance.get("amount", 0)
            return f"{amount} feet (cone)"
        elif range_type == "sphere":
            distance = range_data.get("distance", {})
            amount = distance.get("amount", 0)
            return f"{amount} feet (sphere)"
        elif range_type == "sight":
            return "Sight"
        elif range_type == "unlimited":
            return "Unlimited"
        else:
            return "Special"

    def _format_components(self, components: dict) -> str:
        """Format components from spell data."""
        parts = []
        if components.get("v"):
            parts.append("V")
        if components.get("s"):
            parts.append("S")
        if components.get("m"):
            parts.append("M")
        
        result = ", ".join(parts)
        
        # Add material component details if present
        if components.get("m") and isinstance(components.get("m"), str):
            result += f" ({components['m']})"
        
        return result if result else "None"

    def _format_duration(self, duration_data: list) -> str:
        """Format duration from spell data."""
        if not duration_data:
            return "Unknown"
        
        dur_entry = duration_data[0]
        dur_type = dur_entry.get("type", "instant")
        
        if dur_type == "instant":
            return "Instantaneous"
        elif dur_type == "timed":
            duration = dur_entry.get("duration", {})
            amount = duration.get("amount", 1)
            time_unit = duration.get("type", "hour")
            return f"{amount} {time_unit.capitalize()}{'s' if amount > 1 else ''}"
        elif dur_type == "permanent":
            return "Permanent"
        elif dur_type == "special":
            return "Special"
        else:
            return "Unknown"

    def _clean_text(self, text: str) -> str:
        """Clean spell text by removing wiki formatting tags."""
        import re
        # First handle {@tag text|SOURCE} format - extract text before pipe
        text = re.sub(r'\{@\w+\s+([^}|]+)\|[^}]*\}', r'\1', text)
        # Then handle {@tag text} format without pipe/source
        text = re.sub(r'\{@\w+\s+([^}]+)\}', r'\1', text)
        # Finally remove any remaining |SOURCE references without braces
        text = re.sub(r'\|[A-Z]+\b', '', text)
        return text

    def _format_description(self, spell: dict) -> str:
        """Format the spell description from entries."""
        entries = spell.get("entries", [])
        if not entries:
            return "No description available."
        
        description_parts = []
        for entry in entries:
            if isinstance(entry, str):
                text = self._clean_text(entry)
                description_parts.append(text)
            elif isinstance(entry, dict) and "entries" in entry:
                # Handle nested entries
                for nested in entry["entries"]:
                    if isinstance(nested, str):
                        text = self._clean_text(nested)
                        description_parts.append(text)
        
        return "\n".join(description_parts)

    @app_commands.command(name="spell", description="Look up a D&D 5e spell.")
    @app_commands.describe(name="The spell name to look up")
    async def spell(self, interaction: discord.Interaction, name: str) -> None:
        """Display information about a D&D 5e spell."""
        await interaction.response.defer()
        
        if not self.spells_data:
            await interaction.followup.send(
                "❌ Could not load spell data. Please try again later.",
                ephemeral=True
            )
            return
        
        spell_key = name.lower().strip()
        
        if spell_key not in self.spells_data:
            available = ", ".join(sorted(list(self.spells_data.keys())[:10]))
            await interaction.followup.send(
                f"❌ Spell **{name}** not found.\n\n**Example spells**: {available}...",
                ephemeral=True
            )
            return

        spell_data = self.spells_data[spell_key]
        spell_name = spell_data.get("name", name)
        level = spell_data.get("level", 0)
        school = spell_data.get("school", "")
        
        # Build title with school and level
        level_str = self._format_level(level)
        school_str = self._format_school(school)
        title = f"{school_str} {level_str}"
        
        embed = discord.Embed(
            title=spell_name,
            description=title,
            color=discord.Color.blue()
        )
        
        # Add spell details
        casting_time = self._format_casting_time(spell_data.get("time", []))
        embed.add_field(name="Casting Time", value=casting_time, inline=True)
        
        spell_range = self._format_range(spell_data.get("range", {}))
        embed.add_field(name="Range", value=spell_range, inline=True)
        
        components = self._format_components(spell_data.get("components", {}))
        embed.add_field(name="Components", value=components, inline=True)
        
        duration = self._format_duration(spell_data.get("duration", []))
        embed.add_field(name="Duration", value=duration, inline=True)
        
        # Add description
        description = self._format_description(spell_data)
        if len(description) > 1024:
            # Truncate with ellipsis if too long for one field
            description = description[:1021] + "..."
        embed.add_field(name="Description", value=description, inline=False)
        
        # Add higher level info if available
        higher_level = spell_data.get("entriesHigherLevel", [])
        if higher_level:
            higher_parts = []
            for entry in higher_level:
                if isinstance(entry, dict):
                    entry_name = entry.get("name", "")
                    entry_list = entry.get("entries", [])
                    if entry_name and entry_list:
                        text = entry_list[0] if isinstance(entry_list[0], str) else ""
                        if text:
                            text = self._clean_text(text)
                            higher_parts.append(f"**{entry_name}**: {text}")
            
            if higher_parts:
                higher_text = "\n".join(higher_parts)
                if len(higher_text) > 1024:
                    higher_text = higher_text[:1021] + "..."
                embed.add_field(name="At Higher Levels", value=higher_text, inline=False)
        
        page = spell_data.get("page", "Unknown")
        embed.set_footer(text=f"📖 XPHB page {page}")
        
        await interaction.followup.send(embed=embed)
        logger.info(f"spell command used by {interaction.user} (ID: {interaction.user.id}) for: {spell_name}")

    @spell.autocomplete("name")
    async def spell_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Provide autocomplete suggestions for spell names."""
        if not self.spells_data:
            return []
        
        spell_names = list(self.spells_data.keys())
        matches = [
            app_commands.Choice(name=name.title(), value=name)
            for name in spell_names
            if current.lower() in name.lower()
        ]
        return matches[:25]  # Discord limits to 25 choices


async def setup(bot: commands.Bot) -> None:
    """Load the Spells cog."""
    await bot.add_cog(Spells(bot))
