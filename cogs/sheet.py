import json
import os
import re
import asyncio
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands
from playwright.async_api import async_playwright

from logger_config import get_logger

logger = get_logger(__name__)

# Precompile regex used for class formatting
CLASS_PAIR_PATTERN = re.compile(r"([A-Za-z][A-Za-z'\-\s]+?)\s+(\d{1,2})")


async def _has_proficiency_indicator(element) -> bool:
    """Detect proficiency using SVG circle indicators near the row content.
    This approach looks specifically for an SVG circle used by D&D Beyond's
    proficiency bubbles. It is intentionally strict to avoid false positives.
    """
    try:
        # Look for SVG circles within common proficiency/bubble containers
        sel = ", ".join([
            ".ct-proficiency-bubble svg circle",
            ".ct-proficiency-bubble__icon svg circle",
            ".ddbc-proficiency-bubble svg circle",
            "svg.ct-proficiency-bubble__svg circle",
            # Fallback: any svg circle within the row element
            "svg circle",
        ])
        circles = element.locator(sel)
        count = await circles.count()
        if count == 0:
            return False

        # If present, ensure at least one circle looks like a real bubble
        # by having a radius attribute (r) or a fill attribute.
        for idx in range(min(count, 5)):
            c = circles.nth(idx)
            r = await c.get_attribute("r")
            fill = await c.get_attribute("fill")
            if (r and r != "0") or (fill and fill.lower() != "none"):
                return True
        # If attributes aren't exposed, still treat presence as signal
        return True
    except Exception:
        return False


class CharacterSheetView(discord.ui.View):
    """View with a button to open the full character sheet on D&D Beyond."""
    
    def __init__(self, url: str):
        super().__init__(timeout=None)
        # Add a link button
        self.add_item(discord.ui.Button(
            label="View Full Sheet",
            style=discord.ButtonStyle.link,
            url=url,
            emoji="📋"
        ))


class Sheet(commands.Cog):
    """D&D character sheet cog that fetches character data from D&D Beyond."""
    
    DATA_FILE = os.path.join("data", "character_map.json")
    BASE_URL = "https://www.dndbeyond.com/characters/"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.character_map = self.load_character_map()
        # Playwright browser reuse to avoid relaunching for every request
        self._pw = None
        self._browser = None
        self._browser_lock = asyncio.Lock()

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

    async def _get_element_text(self, page, selector: str, timeout: int = 10000) -> str:
        """Generic helper to get text from a selector."""
        locator = page.locator(selector).first
        await locator.wait_for(timeout=timeout)
        return (await locator.inner_text()).strip()

    def _format_classes(self, raw: str) -> str:
        """Format classes: single -> name only; multi -> Name (L) / Name (L)."""
        pairs = CLASS_PAIR_PATTERN.findall(raw or "")
        if not pairs:
            return raw.strip() if raw else ""
        if len(pairs) == 1:
            return pairs[0][0].strip()
        return " / ".join(f"{name.strip()} ({lvl})" for name, lvl in pairs)

    async def _ensure_browser(self):
        """Ensure a shared Playwright browser is available."""
        async with self._browser_lock:
            if self._browser is not None:
                return
            # Start Playwright and launch a single Chromium browser instance
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)

    async def _close_browser(self):
        try:
            if self._browser:
                await self._browser.close()
        finally:
            self._browser = None
            if self._pw:
                await self._pw.stop()
                self._pw = None

    def cog_unload(self) -> None:
        # Schedule async cleanup
        try:
            asyncio.create_task(self._close_browser())
        except Exception:
            pass

    async def _get_abilities(self, page) -> list[str]:
        """Return all 6 ability scores formatted with abbreviations."""
        locator = page.locator(".ddbc-ability-summary")
        await locator.first.wait_for(timeout=10000)
        raw_texts = await locator.all_inner_texts()
        
        # Map full names to abbreviations
        abbrev_map = {
            "STRENGTH": "STR",
            "DEXTERITY": "DEX",
            "CONSTITUTION": "CON",
            "INTELLIGENCE": "INT",
            "WISDOM": "WIS",
            "CHARISMA": "CHA"
        }
        
        abilities = []
        for text in raw_texts:
            parts = [p.strip() for p in text.splitlines() if p.strip()]
            if len(parts) >= 4:
                full_name = parts[0].upper()
                abbrev = abbrev_map.get(full_name, parts[0][:3].upper())
                abilities.append(f"{abbrev} {parts[1]}{parts[2]} ({parts[3]})")
            else:
                abilities.append(" ".join(parts))
        return abilities

    async def _get_avatar(self, page) -> str:
        """Return the avatar image URL."""
        portrait = page.locator(".ddbc-character-avatar__portrait").first
        await portrait.wait_for(timeout=10000)
        
        # Try direct src attribute
        if src := await portrait.get_attribute("src"):
            return src.strip()
        
        # Try img child
        try:
            img = page.locator(".ddbc-character-avatar__portrait img").first
            await img.wait_for(timeout=3000)
            if src := await img.get_attribute("src"):
                return src.strip()
        except Exception:
            pass
        
        # Try background-image in style
        if style := await portrait.get_attribute("style"):
            if match := re.search(r"background-image:\s*url\(['\"]?(.*?)['\"]?\)", style):
                return match.group(1)
        
        return ""

    async def _get_saving_throws(self, page) -> list[str]:
        """Return all 6 saving throws with proficiency markers.
        Detection prefers proficiency bubbles or checked checkboxes within each save.
        """
        abilities = ["str", "dex", "con", "int", "wis", "cha"]
        abbrevs = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]

        # Wait for saves to load (anchor on STR save existing)
        await page.locator(".ddbc-saving-throws-summary__ability--str").first.wait_for(
            timeout=10000, state="attached"
        )

        saves: list[str] = []
        for i, suffix in enumerate(abilities):
            try:
                ability_elem = page.locator(f".ddbc-saving-throws-summary__ability--{suffix}").first

                # Extract the numeric modifier by reading text segments
                text = await ability_elem.inner_text()
                parts = [p.strip() for p in text.splitlines() if p.strip()]
                modifier = f"{parts[-2]}{parts[-1]}" if len(parts) >= 2 else "+0"

                # Robust proficiency detection using shared helper
                is_proficient = await _has_proficiency_indicator(ability_elem)

                save_text = f"{abbrevs[i]} {modifier}"
                if is_proficient:
                    save_text = f"**{save_text}**"
                saves.append(save_text)
            except Exception:
                saves.append(f"{abbrevs[i]} +0")

        return saves

    async def _get_skills(self, page) -> list[str]:
        """Return all 18 skills with bonuses and proficiency markers.
        Detection prefers presence of proficiency bubbles or checked indicators within each skill row.
        """
        # Wait for skills to load
        await page.locator(".ct-skills__item").first.wait_for(timeout=10000)

        # Get all skill items
        skill_items = page.locator(".ct-skills__item")
        count = await skill_items.count()

        skills: list[str] = []
        for i in range(count):
            item = skill_items.nth(i)
            text = await item.inner_text()
            parts = [p.strip() for p in text.splitlines() if p.strip()]

            # Expected order: [STAT, Skill Name, +/-, Bonus, ...]
            if len(parts) >= 4:
                skill_name = parts[1]
                bonus = f"{parts[2]}{parts[3]}"

                # Robust proficiency detection within the same row
                is_proficient = await _has_proficiency_indicator(item)

                skill_text = f"{skill_name} {bonus}"
                if is_proficient:
                    skill_text = f"**{skill_text}**"
                skills.append(skill_text)

        return skills

    async def _scrape_character_page(self, url: str) -> Optional[dict]:
        """Scrape character data from D&D Beyond.
        
        Args:
            url: Full D&D Beyond character URL.
            
        Returns:
            Dictionary of character data or None on error.
        """
        try:
            # Ensure a shared browser exists
            await self._ensure_browser()
            context = await self._browser.new_context()
            page = await context.new_page()

            logger.info(f"Navigating to {url}")
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(1000)

            # Extract character name from page title
            title = await page.title()
            name_match = re.search(r"^(.+?)'s Character Sheet", title)
            name = name_match.group(1) if name_match else ""

            # Extract simple fields first
            level_task = asyncio.create_task(self._get_element_text(page, ".ddbc-character-progression-summary__level"))
            race_task = asyncio.create_task(self._get_element_text(page, ".ddbc-character-summary__race"))
            classes_text_task = asyncio.create_task(self._get_element_text(page, ".ddbc-character-summary__classes"))
            max_hp_task = asyncio.create_task(self._get_element_text(page, "[data-testid='max-hp']"))
            ac_task = asyncio.create_task(self._get_element_text(page, ".ddbc-armor-class-box__value"))
            speed_text_task = asyncio.create_task(self._get_element_text(page, ".ct-quick-info__box--speed"))

            # Heavier sections in parallel
            abilities_task = asyncio.create_task(self._get_abilities(page))
            avatar_task = asyncio.create_task(self._get_avatar(page))
            saves_task = asyncio.create_task(self._get_saving_throws(page))
            skills_task = asyncio.create_task(self._get_skills(page))

            # Await simple tasks
            level, race, classes_text, max_hp, ac, speed_text = await asyncio.gather(
                level_task, race_task, classes_text_task, max_hp_task, ac_task, speed_text_task
            )
            classes = self._format_classes(classes_text)

            speed_match = re.search(r"(\d+)\s*ft", speed_text)
            speed = f"{speed_match.group(1)} ft." if speed_match else ""

            # Await heavier sections
            abilities, avatar, saves, skills = await asyncio.gather(
                abilities_task, avatar_task, saves_task, skills_task
            )
            avatar = (avatar or "").split("?")[0]

            await context.close()

            return {
                "name": name,
                "level": level,
                "race": race,
                "classes": classes,
                "max_hp": max_hp,
                "ac": ac,
                "speed": speed,
                "abilities": abilities,
                "avatar": avatar,
                "saving_throws": saves,
                "skills": skills,
            }
        except Exception as e:
            logger.error(f"Error scraping character page {url}: {type(e).__name__}: {e}")
            return None

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
        
        # Set footer with Discord member
        # embed.set_footer(text=f"Character of {member.display_name}", icon_url=member.display_avatar.url)
        
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
        
        # Scrape character data
        url = f"{self.BASE_URL}{character_id}"
        logger.info(f"Fetching character {character_id} for member {discord_member.display_name}")
        
        data = await self._scrape_character_page(url)
        
        if not data:
            await interaction.followup.send(
                "❌ Failed to fetch character data from D&D Beyond. The character may be private or the page may have changed.",
                ephemeral=True
            )
            logger.error(f"Failed to scrape character {character_id}")
            return
        
        # Format and send embed with button
        embed = self._format_character_embed(data, discord_member)
        view = CharacterSheetView(url)
        await interaction.followup.send(embed=embed, view=view)
        logger.info(f"Successfully displayed character sheet for {data['name']} ({discord_member.display_name})")


async def setup(bot: commands.Bot):
    await bot.add_cog(Sheet(bot))
