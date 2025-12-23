import datetime
import random

import discord
from discord import app_commands
from discord.ext import commands

from http_manager import HTTP
import logger_config

logger = logger_config.get_logger(__name__)


class Novelty(commands.Cog):
    """A cog for novelty commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="insult", description="Insult a user.")
    @app_commands.describe(user="The user to insult.")
    async def insult(self, interaction: discord.Interaction, user: discord.Member) -> None:
        await interaction.response.defer()

        insult = await HTTP.fetch_text("https://insult.mattbas.org/api/insult.txt")
        insult = insult.strip()
        insult = insult[0].lower() + insult[1:]

        embed = discord.Embed(description=f"{user.mention}, {insult}.", color=discord.Color.pink())
        await interaction.followup.send(embed=embed)
        logger.info(f"Insult command used by {interaction.user} (ID: {interaction.user.id}) on {user} (ID: {user.id})")
    
    @app_commands.command(name="fact", description="Get a random fact.")
    async def fact(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        fact = await HTTP.fetch_json("https://uselessfacts.jsph.pl/random.txt?language=en")

        embed = discord.Embed(title="Random Fact", description=fact["text"], color=discord.Color.pink())
        await interaction.followup.send(embed=embed)
        logger.info(f"Fact command used by {interaction.user} (ID: {interaction.user.id})")
    
    @app_commands.command(name="joke", description="Get a random joke.")
    async def joke(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        joke = await HTTP.fetch_json("https://official-joke-api.appspot.com/random_joke")
        setup = joke.get("setup", "").strip()
        punchline = joke.get("punchline", "").strip()

        embed = discord.Embed(title="Random Joke", color=discord.Color.pink())
        embed.add_field(name="Setup", value=setup, inline=False)
        embed.add_field(name="Punchline", value=punchline, inline=False)

        await interaction.followup.send(embed=embed)
        logger.info(f"Joke command used by {interaction.user} (ID: {interaction.user.id})")      
    
    @app_commands.command(name="coinflip", description="Flip a coin.")
    async def coinflip(self, interaction: discord.Interaction) -> None:
        result = random.choice(["heads", "tails"])
        embed = discord.Embed(title="Coin Flip", description=f"The coin landed on **{result}**!", color=discord.Color.pink())
        await interaction.response.send_message(embed=embed)
        logger.info(f"Coinflip command used by {interaction.user} (ID: {interaction.user.id})")

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question.")
    @app_commands.describe(question="The question to ask the magic 8-ball.")
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
    
    @app_commands.command(name="newbycon", description="Show how many days it has been since gabby ruined newbyCon.")
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

async def setup(bot: commands.Bot) -> None:
    """Load the Novelty cog."""
    await bot.add_cog(Novelty(bot))
