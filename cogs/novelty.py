import datetime
import random
# from pathlib import Path

import discord
from discord.ext import commands

import logger_config

logger = logger_config.get_logger(__name__)


class Novelty(commands.Cog):
    """A cog for novelty commands."""

    def __init__(self, bot: commands.Bot):
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
    
    # @discord.app_commands.command(name="test", description="Send a test image.")
    # async def test(self, interaction: discord.Interaction) -> None:
    #     """Send the test image file."""
    #     await interaction.response.defer()
    #     file_path = Path("data/274.png")
        
    #     if not file_path.exists():
    #         await interaction.response.send_message(
    #             "❌ Test image file not found.",
    #             ephemeral=True
    #         )
    #         logger.error(f"Test image file not found: {file_path}")
    #         return
        
    #     file = discord.File(file_path)
        
    #     embed = discord.Embed(
    #         title="Player's Handbook (2024): Page 274",
    #         color=discord.Color.red()
    #     )
    #     embed.set_image(url="attachment://274.png")

    #     await interaction.followup.send(embed=embed, file=file)
    #     logger.info(f"test command used by {interaction.user} (ID: {interaction.user.id})")  

async def setup(bot: commands.Bot) -> None:
    """Load the Novelty cog."""
    await bot.add_cog(Novelty(bot))
