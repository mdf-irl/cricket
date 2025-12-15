import datetime
import random

import discord
from discord import ui

import logger_config
from http_manager import HTTP

logger = logger_config.get_logger(__name__)


class OnThisDayView(ui.View):
    """Paginated view for browsing on-this-day events."""

    def __init__(self, events: list[dict], date_str: str, user_id: int):
        super().__init__(timeout=300)
        self.events = events
        self.date_str = date_str
        self.user_id = user_id
        self.current_index = 0
        self._update_buttons()

    def _update_buttons(self):
        """Enable/disable buttons based on current position."""
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.events) - 1

    def _build_embed(self) -> discord.Embed:
        """Build embed for current event."""
        ev = self.events[self.current_index]
        year = ev.get("year", "?")
        desc = ev.get("text") or ev.get("description") or "(no description)"

        # Try to attach a source URL from pages
        pages = ev.get("pages") or []
        link = None
        title = None
        if pages and isinstance(pages, list):
            first = pages[0]
            title = first.get("titles", {}).get("normalized") or first.get("title")
            link = (
                first.get("content_urls", {})
                .get("desktop", {})
                .get("page")
            )

        embed = discord.Embed(
            title=f"On This Day — {self.date_str}",
            description=f"**{year}** — {desc}" + (f" (**source**: [{title}]({link}))" if link else ""),
            color=discord.Color.pink(),
        )
        embed.set_footer(text=f"🔋 Powered by Wikipedia | Event {self.current_index + 1} of {len(self.events)}")
        return embed

    @ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show previous event."""
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.current_index = max(0, self.current_index - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show next event."""
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.current_index = min(len(self.events) - 1, self.current_index + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


class UrbanDictionaryView(ui.View):
    """Paginated view for browsing Urban Dictionary definitions."""

    def __init__(self, definitions: list[dict], term: str, user_id: int):
        super().__init__(timeout=300)
        self.definitions = definitions
        self.term = term
        self.user_id = user_id
        self.current_index = 0
        self._update_buttons()

    def _update_buttons(self):
        """Enable/disable buttons based on current position."""
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.definitions) - 1

    def _build_embed(self) -> discord.Embed:
        """Build embed for current definition."""
        defn = self.definitions[self.current_index]
        word = defn.get("word", self.term)
        definition = defn.get("definition", "No definition available")
        example = defn.get("example", "")
        # author = defn.get("author", "Unknown")
        permalink = defn.get("permalink", "")
        # thumbs_up = defn.get("thumbs_up", 0)
        # thumbs_down = defn.get("thumbs_down", 0)

        # Clean up formatting (UD uses [brackets] for links)
        definition = definition.replace("[", "").replace("]", "").replace("`", "")
        # example = example.replace("[", "*").replace("]", "*")

        # Truncate if too long
        if len(definition) > 1024:
            definition = definition[:1021] + "..."
        if len(example) > 1024:
            example = example[:1021] + "..."

        embed = discord.Embed(
            title=f"Urban Dictionary: {word}",
            description=f"{definition} ([link]({permalink}))",
            color=discord.Color.pink(),
            # url=permalink if permalink else None
        )

        # if example:
        #     embed.add_field(name="Example", value=example, inline=False)

        # embed.add_field(name="👍", value=str(thumbs_up), inline=True)
        # embed.add_field(name="👎", value=str(thumbs_down), inline=True)
        embed.set_footer(text=f"📖 Definition {self.current_index + 1} of {len(self.definitions)}")
        
        return embed

    @ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show previous definition."""
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.current_index = max(0, self.current_index - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show next definition."""
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.current_index = min(len(self.definitions) - 1, self.current_index + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


class Novelty(discord.ext.commands.Cog):
    """A cog for novelty commands."""

    def __init__(self, bot: discord.ext.commands.Bot):
        self.bot = bot

    @discord.app_commands.command(name="8ball", description="Ask the magic 8-ball a question.")
    @discord.app_commands.describe(question="The question to ask the magic 8-ball.")
    async def _8ball(self, interaction: discord.Interaction, question: str) -> None:
        """Respond to a user's question with a magic 8-ball answer."""
        if not question.endswith("?"):
            question += "?"

        responses = [
            "It is certain.",
            "Without a doubt.",
            "You may rely on it.",
            "Yes, definitely.",
            "As I see it, yes.",
            "Most likely.",
            "Outlook good.",
            "Yes.",
            "Signs point to yes.",
            "Reply hazy, try again.",
            "Ask again later.",
            "Better not tell you now.",
            "Cannot predict now.",
            "Concentrate and ask again.",
            "Don't count on it.",
            "My reply is no.",
            "My sources say no.",
            "Outlook not so good.",
            "Very doubtful."
        ]
        answer = random.choice(responses)
        embed = discord.Embed(
            title="Magic 8-Ball",
            description=f"**Q**: {question}\n**A**: {answer}",
            color=discord.Color.pink()
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"8ball command used by {interaction.user} (ID: {interaction.user.id})")
    
    @discord.app_commands.command(name="newbycon", description="Show how many days it has been since gabby ruined newbyCon.")
    async def newbycon(self, interaction: discord.Interaction) -> None:
        """Calculate and display the number of days since newbyCon was ruined."""
        ruined_date = datetime.date(2018, 4, 24)
        today = datetime.date.today()
        delta = today - ruined_date
        days_passed = delta.days

        embed = discord.Embed(
            title="URGENT REMINDER",
            description=f"It has been **{days_passed}** days since gabby ruined newbyCon. 😡",
            color=discord.Color.pink()
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"newbycon command used by {interaction.user} (ID: {interaction.user.id})")  

    @discord.app_commands.command(name="onthisday", description="Browse historical events that happened on this day.")
    async def onthisday(self, interaction: discord.Interaction) -> None:
        """Fetch historical events for today's month/day and allow browsing through them."""
        await interaction.response.defer()

        today = datetime.date.today()
        month = today.month
        day = today.day
        date_str = today.strftime('%B %d')
        # Wikipedia On This Day API
        url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{month}/{day}"

        headers = {"User-Agent": "Cricket/420.69 (https://github.com/mdf-irl/cricket)"}

        try:
            data = await HTTP.fetch_json(url, headers=headers)
        except Exception as e:
            logger.error(f"Error fetching on-this-day data: {type(e).__name__}: {e}")
            await interaction.followup.send("❌ Could not retrieve historical facts right now.", ephemeral=True)
            return

        events = data.get("events") if isinstance(data, dict) else None
        if not events:
            await interaction.followup.send("❌ No historical events found for today.", ephemeral=True)
            return

        view = OnThisDayView(events, date_str, interaction.user.id)
        await interaction.followup.send(embed=view._build_embed(), view=view)
        logger.info(f"onthisday command used by {interaction.user} (ID: {interaction.user.id})")

    @discord.app_commands.command(name="ud", description="Look up a term on Urban Dictionary.")
    @discord.app_commands.describe(term="The term to look up")
    async def urban_dictionary(self, interaction: discord.Interaction, term: str) -> None:
        """Fetch Urban Dictionary definitions and allow browsing through them."""
        await interaction.response.defer()

        url = f"https://api.urbandictionary.com/v0/define?term={term}"

        try:
            data = await HTTP.fetch_json(url)
        except Exception as e:
            logger.error(f"Error fetching Urban Dictionary data: {type(e).__name__}: {e}")
            await interaction.followup.send("❌ Could not retrieve definitions right now.", ephemeral=True)
            return

        definitions = data.get("list") if isinstance(data, dict) else None
        if not definitions:
            await interaction.followup.send(f"❌ No definitions found for **{term}**.", ephemeral=True)
            return

        view = UrbanDictionaryView(definitions, term, interaction.user.id)
        await interaction.followup.send(embed=view._build_embed(), view=view)
        logger.info(f"ud command used by {interaction.user} (ID: {interaction.user.id}) for term: {term}")

async def setup(bot: discord.ext.commands.Bot) -> None:
    """Load the Novelty cog."""
    await bot.add_cog(Novelty(bot))
