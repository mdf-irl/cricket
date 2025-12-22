import datetime
import discord
from discord import app_commands, ui
from discord.ext import commands

from logger_config import get_logger
from http_manager import HTTP

logger = get_logger(__name__)

USER_AGENT = {"User-Agent": "Cricket/420.69 (https://github.com/mdf-irl/cricket)"}


class OnThisDayView(ui.View):
    """Paginated view for browsing on-this-day events."""

    def __init__(self, events: list[dict], date_str: str, user_id: int):
        super().__init__(timeout=300)
        self.events = events
        self.date_str = date_str
        self.user_id = user_id
        self.current_index = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.events) - 1

    def _build_embed(self) -> discord.Embed:
        ev = self.events[self.current_index]
        year = ev.get("year", "?")
        desc = ev.get("text") or ev.get("description") or "(no description)"

        pages = ev.get("pages") or []
        link = None
        title = None
        if pages and isinstance(pages, list):
            first = pages[0]
            title = first.get("titles", {}).get("normalized") or first.get("title")
            link = first.get("content_urls", {}).get("desktop", {}).get("page")

        embed = discord.Embed(
            title=f"On This Day — {self.date_str}",
            description=f"**{year}** — {desc}" + (f" (**source**: [{title}]({link}))" if link else ""),
            color=discord.Color.pink(),
        )
        embed.set_footer(text=f"🔋 Powered by Wikipedia | Event {self.current_index + 1} of {len(self.events)}")
        return embed

    @ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.current_index = max(0, self.current_index - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.current_index = min(len(self.events) - 1, self.current_index + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


class OnThisDay(commands.Cog):
    """Historical events for today's date."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="onthisday", description="Browse historical events that happened on this day.")
    async def onthisday(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        today = datetime.date.today()
        date_str = today.strftime("%B %d")
        url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{today.month}/{today.day}"

        try:
            data = await HTTP.fetch_json(url, headers=USER_AGENT)
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OnThisDay(bot))
