import json
import re
from pathlib import Path

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

# Display names for known source abbreviations
SOURCE_DISPLAY = {
    "XPHB": "Player's Handbook (2024)",
    "TCE": "Tasha's Cauldron of Everything",
    "XGE": "Xanathar's Guide to Everything",
}

# Precompiled regex patterns for cleaning spell text
TAG_WITH_SOURCE_RE = re.compile(r'\{@\w+\s+([^}|]+)\|[^}]*\}')
TAG_SIMPLE_RE = re.compile(r'\{@\w+\s+([^}]+)\}')
PIPE_SOURCE_RE = re.compile(r'\|[A-Z]+\b')
AOE_BRACKET_RE = re.compile(r'\[\s*Area of Effect\s*\]', re.IGNORECASE)
MULTI_SPACE_RE = re.compile(r'[ \t]{2,}')


class Spells(commands.Cog):
    """D&D 5e spells reference cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spells_data: dict[str, list[dict]] = self._load_spells_data()
        self.spell_entries: list[tuple[str, str]] = self._build_spell_entries()
        self.spell_source_index: dict[str, dict[str, dict]] = self._build_source_index()

    def _load_spells_data(self) -> dict[str, list[dict]]:
        """Load spells data from all JSON files in data/spells folder."""
        spells_dict = {}
        spells_dir = Path("data/spells")
        
        if not spells_dir.exists():
            logger.warning(f"Spells directory not found: {spells_dir}")
            return {}
        
        try:
            for spell_file in sorted(spells_dir.glob("*.json")):
                source = spell_file.stem.replace("spells-", "").upper()
                
                with open(spell_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                
                for spell in raw_data.get("spell", []):
                    name = spell.get("name", "")
                    if name:
                        spell_key = name.lower()
                        
                        # Add source to spell data
                        spell_with_source = spell.copy()
                        spell_with_source["source_abbr"] = source
                        
                        if spell_key not in spells_dict:
                            spells_dict[spell_key] = []
                        spells_dict[spell_key].append(spell_with_source)
            
            total = sum(len(v) for v in spells_dict.values())
            logger.info(f"Loaded {total} spells from {spells_dir} ({len(spells_dict)} unique names)")
            return spells_dict
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading spells from {spells_dir}: {e}")
            return {}

    def _format_level(self, level: int) -> str:
        """Convert level number to level name."""
        if level == 0:
            return "Cantrip"
        else:
            return f"Level {level}"
        # elif level == 1:
        #     return "1st Level"
        # elif level == 2:
        #     return "2nd Level"
        # elif level == 3:
        #     return "3rd Level"
        # else:
        #     return f"{level}th Level"

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
        # Quick exit if no markup-like tokens present
        if "{@" not in text and "[" not in text and "|" not in text:
            return text
        # First handle {@tag text|SOURCE} format - extract text before pipe
        text = TAG_WITH_SOURCE_RE.sub(r"\1", text)
        # Then handle {@tag text} format without pipe/source
        text = TAG_SIMPLE_RE.sub(r"\1", text)
        # Finally remove any remaining |SOURCE references without braces
        text = PIPE_SOURCE_RE.sub("", text)
        # Remove bracketed AoE headings like "[Area of Effect]"
        text = AOE_BRACKET_RE.sub("", text)
        # Collapse excessive spaces (but keep newlines)
        text = MULTI_SPACE_RE.sub(" ", text).strip()
        return text

    def _build_source_index(self) -> dict[str, dict[str, dict]]:
        """Build a fast lookup: spell_key -> SOURCE_ABBR -> spell version dict."""
        index: dict[str, dict[str, dict]] = {}
        for key, versions in self.spells_data.items():
            vlist = versions if isinstance(versions, list) else [versions]
            by_src: dict[str, dict] = {}
            for v in vlist:
                src = v.get("source_abbr")
                if src:
                    by_src[src.upper()] = v
            if by_src:
                index[key] = by_src
        return index

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

    def _select_spell_versions(self, spell_key: str) -> list[dict]:
        """Return all versions for a spell key sorted by source abbreviation."""
        versions = self.spells_data.get(spell_key, [])
        if not isinstance(versions, list):
            versions = [versions]
        return sorted(versions, key=lambda v: v.get("source_abbr", ""))

    def _build_footer(self, spell_versions: list[dict]) -> str:
        """Build footer text listing all sources/pages for the spell."""
        if len(spell_versions) > 1:
            parts = []
            for v in spell_versions:
                src = v.get("source_abbr", "UNK")
                src = SOURCE_DISPLAY.get(src, src)
                pg = v.get("page", "?")
                parts.append(f"{src} page {pg}")
            return f"📖 {', '.join(parts)}"

        spell = spell_versions[0]
        page = spell.get("page", "Unknown")
        source = spell.get("source_abbr", "Unknown")
        source = SOURCE_DISPLAY.get(source, source)
        return f"📖 {source} page {page}"

    def _build_spell_entries(self) -> list[tuple[str, str]]:
        """Pre-compute display and key pairs for autocomplete."""
        entries: list[tuple[str, str]] = []
        for key, versions in self.spells_data.items():
            # If multiple sources exist for this spell, expose each version
            if isinstance(versions, list) and len(versions) > 1:
                for v in sorted(versions, key=lambda x: x.get("source_abbr", "")):
                    display_name = v.get("name", key.title())
                    src = v.get("source_abbr", "")
                    entries.append((f"{display_name} ({src})", f"{key}|{src}"))
            else:
                v = versions[0] if isinstance(versions, list) else versions
                display_name = v.get("name", key.title())
                entries.append((display_name, key))
        entries.sort(key=lambda x: x[0])
        return entries

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
        
        raw_value = name
        spell_key = raw_value.lower().strip()
        selected_source = None
        if "|" in spell_key:
            parts = spell_key.split("|", 1)
            spell_key = parts[0]
            selected_source = parts[1].upper()

        if spell_key not in self.spells_data:
            available = ", ".join(sorted(list(self.spells_data.keys())[:10]))
            await interaction.followup.send(
                f"❌ Spell **{name}** not found.\n\n**Example spells**: {available}...",
                ephemeral=True
            )
            return

        # Handle multiple versions of the same spell
        spell_versions = self._select_spell_versions(spell_key)
        # If a specific source was selected via autocomplete, prefer that version
        if selected_source:
            by_src = self.spell_source_index.get(spell_key)
            if by_src and selected_source in by_src:
                spell_data = by_src[selected_source]
            else:
                spell_data = spell_versions[0]
        else:
            spell_data = spell_versions[0]
        
        spell_name = spell_data.get("name", name)
        level = spell_data.get("level", 0)
        school = spell_data.get("school", "")
        
        # Build title with school and level
        level_str = self._format_level(level)
        school_str = self._format_school(school)
        title = f"{spell_name} — {level_str} {school_str}" if level > 0 else f"{spell_name} — {school_str} Cantrip"
        
        embed = discord.Embed(
            title=title,
            # description=title,
            color=discord.Color.pink()
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
        embed.add_field(name="Description", value=description, inline=True)
        
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
                embed.add_field(name="At Higher Levels", value=higher_text, inline=True)
        
        # Footer should reflect only the selected version's source/page
        embed.set_footer(text=self._build_footer([spell_data]))
        
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

        # Filter by current input (case-insensitive) against display name and key
        matches = [
            app_commands.Choice(name=display, value=key)
            for display, key in self.spell_entries
            if current.lower() in display.lower() or current.lower() in key.lower()
        ]
        return matches[:25]  # Discord limits to 25 choices


async def setup(bot: commands.Bot) -> None:
    """Load the Spells cog."""
    await bot.add_cog(Spells(bot))
