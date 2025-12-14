import datetime
import random

import discord

import logger_config
from http_manager import HTTP

logger = logger_config.get_logger(__name__)

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
            description=f"😡 It has been **{days_passed}** days since gabby ruined newbyCon.",
            color=discord.Color.pink()
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"newbycon command used by {interaction.user} (ID: {interaction.user.id})")  

    @discord.app_commands.command(name="onthisday", description="See a random historical event that happened on this day.")
    async def onthisday(self, interaction: discord.Interaction) -> None:
        """Fetch a random historical event for today's month/day and display it."""
        await interaction.response.defer()

        today = datetime.date.today()
        month = today.month
        day = today.day
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

        ev = random.choice(events)
        year = ev.get("year", "?")
        desc = ev.get("text") or ev.get("description") or "(no description)"

        # Try to attach a source URL from pages
        pages = ev.get("pages") or []
        if pages and isinstance(pages, list):
            first = pages[0]
            title = first.get("titles", {}).get("normalized") or first.get("title")
            link = (
                first.get("content_urls", {})
                .get("desktop", {})
                .get("page")
            ) or first.get("extract")

        embed = discord.Embed(
            title=f"On This Day — {today.strftime('%B %d')}",
            description=f"**{year}** — {desc}\n\n**Source**: [{title or 'Link'}]({link})" if link else f"**{year}** — {desc}",
            color=discord.Color.pink(),
        )

        embed.set_footer(text="🔋 Powered by Wikipedia")
        await interaction.followup.send(embed=embed)
        logger.info(f"onthisday command used by {interaction.user} (ID: {interaction.user.id})")

async def setup(bot: discord.ext.commands.Bot) -> None:
    """Load the Novelty cog."""
    await bot.add_cog(Novelty(bot))
