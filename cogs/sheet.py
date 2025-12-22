import json
import os
import re
import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
from discord import app_commands

from config import Config
from http_manager import HTTP
from logger_config import get_logger

logger = get_logger(__name__)

# Precompile regex used for class formatting
CLASS_PAIR_PATTERN = re.compile(r"([A-Za-z][A-Za-z'\-\s]+?)\s+(\d{1,2})")


"""Sheet command now relies solely on a remote proxy and local cache.
All Playwright scraping code has been removed from the bot to keep the Pi light.
"""


class CharacterSheetView(discord.ui.View):
    """View with a button to open the full character sheet on D&D Beyond."""
    
    def __init__(self, url: str):
        super().__init__(timeout=None)
        # Add a link button
        self.add_item(discord.ui.Button(
            label="Open Full Sheet",
            style=discord.ButtonStyle.link,
            url=url,
            emoji="📋"
        ))


class Sheet(commands.Cog):
    """D&D character sheet cog fetching data via proxy or cache."""
    
    DATA_FILE = os.path.join("data", "character_map.json")
    CACHE_FILE = os.path.join("data", "sheet_cache.json")
    BASE_URL = "https://www.dndbeyond.com/characters/"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.character_map = self.load_character_map()
        # Cache in-memory map: character_id -> data
        self._cache: dict[str, dict] = self._load_cache()

    def load_character_map(self) -> dict[str, str]:
        """Load character map from JSON file with error handling."""
        try:
            with open(self.DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Loaded character map with {len(data)} entries from {self.DATA_FILE}")
                return data
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading {self.DATA_FILE}: {type(e).__name__}: {e}")
            return {}

    def _load_cache(self) -> dict[str, dict]:
        """Load previously scraped character data cache."""
        try:
            with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    logger.info(f"Loaded sheet cache with {len(data)} entries from {self.CACHE_FILE}")
                    return data
        except FileNotFoundError:
            logger.info("No existing sheet cache; starting fresh")
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid cache JSON {self.CACHE_FILE}: {e}; starting empty")
        return {}

    def _save_cache(self) -> None:
        """Persist cache to disk."""
        try:
            os.makedirs("data", exist_ok=True)
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving sheet cache: {type(e).__name__}: {e}")

    # Scraping helpers removed; bot no longer performs direct scraping.

    def _format_classes(self, raw: str) -> str:
        """Format classes: single -> name only; multi -> Name (L) / Name (L)."""
        pairs = CLASS_PAIR_PATTERN.findall(raw or "")
        if not pairs:
            return raw.strip() if raw else ""
        if len(pairs) == 1:
            return pairs[0][0].strip()
        return " / ".join(f"{name.strip()} ({lvl})" for name, lvl in pairs)

    # No browser lifecycle management required anymore.

    # All scraping logic removed.

    def _format_character_embed(self, data: dict, member: discord.Member) -> discord.Embed:
        """Format character data into a Discord embed.
        
        Args:
            data: Character data dictionary from scraper.
            member: Discord member who owns the character.
            
        Returns:
            Discord embed with character information.
        """
        embed = discord.Embed(
            title=f"{data['name']}",
            description=f"**{data['race']}** • **{data['classes']}** • {data['level']}",
            color=discord.Color.blue()
        )
        
        # Set character avatar as thumbnail
        if data['avatar']:
            embed.set_thumbnail(url=data['avatar'])
        
        # Set footer with Discord member and last scraped time
        footer_text = f"Character of {member.display_name}"
        if "_scraped_at" in data:
            try:
                scraped = datetime.datetime.fromisoformat(data["_scraped_at"])
                formatted_time = scraped.strftime('%m/%d/%Y %I:%M %p')
                # Replace UTC offset with EST/EDT
                tz_offset = scraped.strftime('%z')
                if tz_offset == '-0500':
                    tz_name = 'EST'
                elif tz_offset == '-0400':
                    tz_name = 'EDT'
                else:
                    tz_name = scraped.strftime('%Z') or 'UTC'
                footer_text += f" • Last scraped: {formatted_time} {tz_name}"
            except (ValueError, TypeError):
                pass
        embed.set_footer(text=footer_text)
        
        # Core stats
        embed.add_field(
            name="⚔️ Combat Stats",
            value=f"**HP:** {data['max_hp']}\n**AC:** {data['ac']}\n**Speed:** {data['speed']}",
            inline=True
        )
        
        # Ability scores (3 per column)
        abilities_text = "\n".join(data['abilities'][:3])
        embed.add_field(name="📊 Abilities", value=abilities_text, inline=True)
        
        abilities_text2 = "\n".join(data['abilities'][3:])
        embed.add_field(name="** **", value=abilities_text2, inline=True)
        
        # Saving throws (formatted in 2 columns)
        saves_col1 = "\n".join(data['saving_throws'][:3])
        saves_col2 = "\n".join(data['saving_throws'][3:])
        embed.add_field(name="🛡️ Saving Throws", value=saves_col1, inline=True)
        embed.add_field(name="** **", value=saves_col2, inline=True)
        embed.add_field(name="** **", value="** **", inline=True)  # Spacer
        
        # Skills (formatted in 3 columns)
        skills_per_col = (len(data['skills']) + 2) // 3  # Divide evenly into 3 columns
        skills_col1 = "\n".join(data['skills'][:skills_per_col])
        skills_col2 = "\n".join(data['skills'][skills_per_col:skills_per_col*2])
        skills_col3 = "\n".join(data['skills'][skills_per_col*2:])
        embed.add_field(name="🎯 Skills", value=skills_col1, inline=True)
        embed.add_field(name="** **", value=skills_col2, inline=True)
        embed.add_field(name="** **", value=skills_col3, inline=True)
        
        return embed

    async def member_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete that only shows members with mapped character IDs."""
        if not interaction.guild:
            return []
        
        choices = []
        for discord_id_str, character_id in self.character_map.items():
            try:
                discord_id = int(discord_id_str)
                member = interaction.guild.get_member(discord_id)
                
                if member and current.lower() in member.display_name.lower():
                    choices.append(
                        app_commands.Choice(
                            name=member.display_name,
                            value=str(member.id)
                        )
                    )
            except (ValueError, AttributeError):
                continue
        
        # Limit to 25 choices (Discord API limit)
        return choices[:25]

    @app_commands.command(name="sheet", description="Display a D&D character sheet from D&D Beyond")
    @app_commands.describe(member="The server member whose character you want to view")
    @app_commands.autocomplete(member=member_autocomplete)
    async def sheet(self, interaction: discord.Interaction, member: str) -> None:
        """Fetch and display a D&D character sheet from D&D Beyond.
        
        Args:
            interaction: Discord interaction object.
            member: String representation of member ID (from autocomplete).
        """
        # Defer immediately as scraping takes time
        await interaction.response.defer()
        
        # Validate character map loaded
        if not self.character_map:
            await interaction.followup.send(
                "❌ Character map unavailable. Please contact the bot administrator.",
                ephemeral=True
            )
            logger.warning("Sheet command invoked but character_map is empty")
            return
        
        # Get character ID from map
        character_id = self.character_map.get(member)
        if not character_id:
            await interaction.followup.send(
                "❌ No character found for this member.",
                ephemeral=True
            )
            logger.warning(f"Sheet command invoked for unmapped member ID: {member}")
            return
        
        # Get Discord member object
        discord_member = interaction.guild.get_member(int(member))
        if not discord_member:
            await interaction.followup.send(
                "❌ Member not found in this server.",
                ephemeral=True
            )
            return
        
        # Prefer remote proxy if configured; else fall back to cache
        data: dict | None = None
        remote_base = getattr(Config, "SHEET_PROXY_BASE", None)
        if remote_base:
            proxy_url = f"{remote_base.rstrip('/')}/sheet/{character_id}"
            logger.info(f"Attempting remote sheet fetch from {proxy_url}")
            try:
                data = await HTTP.fetch_json(proxy_url)
                # Minimal validation
                required_keys = {"name", "level", "race", "classes", "max_hp", "ac", "speed", "abilities", "avatar", "saving_throws", "skills"}
                if not isinstance(data, dict) or not required_keys.issubset(data.keys()):
                    logger.warning("Remote sheet fetch returned unexpected shape; ignoring")
                    data = None
                else:
                    # Cache successful fetch with timestamp (in New York timezone)
                    try:
                        ny_tz = ZoneInfo("America/New_York")
                        scraped_time = datetime.datetime.now(ny_tz).isoformat()
                    except Exception:
                        # Fall back to UTC if timezone data unavailable
                        scraped_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    data["_scraped_at"] = scraped_time
                    self._cache[str(character_id)] = data
                    self._save_cache()
            except Exception as e:
                logger.warning(f"Remote sheet fetch failed: {type(e).__name__}: {e}")

        if data is None:
            # Fallback to cached data
            cached = self._cache.get(str(character_id))
            if not cached:
                await interaction.followup.send(
                    "❌ Sheet proxy unavailable and no cached data found. Try again when your PC is online.",
                    ephemeral=True,
                )
                return
            data = cached
        
        # Format and send embed with button
        # Build canonical URL for the button
        url = f"{self.BASE_URL}{character_id}"
        embed = self._format_character_embed(data, discord_member)
        view = CharacterSheetView(url)
        await interaction.followup.send(embed=embed, view=view)
        logger.info(f"Successfully displayed character sheet for {data['name']} ({discord_member.display_name})")


async def setup(bot: commands.Bot):
    await bot.add_cog(Sheet(bot))
