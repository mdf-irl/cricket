import discord
from discord import app_commands, ui
from discord.ext import commands

from logger_config import get_logger
from http_manager import HTTP

logger = get_logger(__name__)


class UrbanDictionaryView(ui.View):
    """Paginated view for browsing Urban Dictionary definitions."""

    def __init__(self, definitions: list[dict], term: str, user_id: int):
        super().__init__(timeout=300)
        self.definitions = definitions
        self.term = term
        self.user_id = user_id
        self.current_index = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.definitions) - 1

    def _build_embed(self) -> discord.Embed:
        defn = self.definitions[self.current_index]
        word = defn.get("word", self.term)
        definition = defn.get("definition", "No definition available")
        example = defn.get("example", "")
        permalink = defn.get("permalink", "")

        # Clean up formatting (UD uses [brackets] for links)
        definition = definition.replace("[", "").replace("]", "").replace("`", "")
        if len(definition) > 1024:
            definition = definition[:1021] + "..."
        if len(example) > 1024:
            example = example[:1021] + "..."

        embed = discord.Embed(
            title=f"Urban Dictionary: {word}",
            description=f"{definition} ([link]({permalink}))",
            color=discord.Color.pink(),
        )
        embed.set_footer(text=f"📖 Definition {self.current_index + 1} of {len(self.definitions)}")
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

        self.current_index = min(len(self.definitions) - 1, self.current_index + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


class UrbanDictionary(commands.Cog):
    """Look up terms on Urban Dictionary."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ud", description="Look up a term on Urban Dictionary.")
    @app_commands.describe(term="The term to look up")
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UrbanDictionary(bot))
