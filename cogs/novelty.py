import datetime
import random
import asyncio
import re
from pathlib import Path
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from http_manager import HTTP
from logger_config import get_logger

logger = get_logger(__name__)

C0N_IMAGE_PATH = Path("data/c0n.png")
AUTISM_IMAGE_PATH = Path("data/autism_announcement.jpg")
MENTION_PATTERN = re.compile(r"<@!?([0-9]+)>")


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

    @app_commands.command(name="announce", description="Send the autism announcement image with custom text.")
    @app_commands.describe(text="The announcement text to append after the image.")
    async def announce(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.defer()

        if not AUTISM_IMAGE_PATH.exists():
            await interaction.followup.send(
                "❌ Announcement image not found. Please contact the bot admin.",
                ephemeral=True,
            )
            logger.warning(f"announce image missing at {AUTISM_IMAGE_PATH}")
            return

        try:
            file = discord.File(AUTISM_IMAGE_PATH, filename="autism_announcement.jpg")
            embed = discord.Embed(color=discord.Color.pink())
            embed.set_image(url="attachment://autism_announcement.jpg")
            embed.set_footer(text=text)
            await interaction.followup.send(embed=embed, file=file)
            logger.info(
                f"announce command used by {interaction.user} (ID: {interaction.user.id}): {text[:50]}"
            )
        except Exception as e:
            logger.error(f"Error in announce command: {type(e).__name__}: {e}")
            await interaction.followup.send(
                "❌ Failed to send the announcement.",
                ephemeral=True,
            )
    
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

    @app_commands.command(name="c0nsay", description="Make c0n say something in a speech bubble.")
    @app_commands.describe(text="The text for the speech bubble.")
    async def c0nsay(self, interaction: discord.Interaction, text: str) -> None:
        """Create an image with c0n and a speech bubble containing text."""
        await interaction.response.defer()

        # Replace Discord mentions with display names for cleaner rendering
        text_for_image = self._replace_mentions(text, interaction.guild)

        # Check if image exists
        if not C0N_IMAGE_PATH.exists():
            await interaction.followup.send(
                "❌ c0n image not found. Please contact the bot admin.",
                ephemeral=True,
            )
            logger.warning(f"c0n.png not found at {C0N_IMAGE_PATH}")
            return

        try:
            # Run image processing in executor to avoid blocking
            image_bytes = await asyncio.to_thread(self._create_c0nsay_image, text_for_image)
            
            file = discord.File(image_bytes, filename="c0n_says.png")
            embed = discord.Embed(color=discord.Color.pink())
            embed.set_image(url="attachment://c0n_says.png")

            await interaction.followup.send(embed=embed, file=file)
            logger.info(f"c0nsay command used by {interaction.user} (ID: {interaction.user.id}): {text[:50]}")
        except Exception as e:
            logger.error(f"Error in c0nsay command: {type(e).__name__}: {e}")
            await interaction.followup.send(
                "❌ An error occurred while creating the image.",
                ephemeral=True,
            )

    def _replace_mentions(self, text: str, guild: discord.Guild | None) -> str:
        """Replace mention syntax with display names for the current guild."""
        if not guild:
            return text

        def _sub(match: re.Match[str]) -> str:
            try:
                user_id = int(match.group(1))
            except (ValueError, TypeError):
                return match.group(0)

            member = guild.get_member(user_id)
            return member.display_name if member else match.group(0)

        return MENTION_PATTERN.sub(_sub, text)

    def _create_c0nsay_image(self, text: str) -> BytesIO:
        """Create an image with c0n and a speech bubble containing text."""
        # Load the base image
        img = Image.open(C0N_IMAGE_PATH).convert("RGBA")
        width, height = img.size
        
        # Create a larger canvas to fit speech bubble above/beside the image
        canvas_width = width + 400
        canvas_height = height + 200
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 0))
        
        # Paste the c0n image onto the canvas (offset slightly to make room for bubble)
        canvas.paste(img, (50, 100), img)
        
        # Draw the speech bubble
        bubble_x = width - 50
        bubble_y = 20
        bubble_width = 350
        bubble_height = 150
        
        draw = ImageDraw.Draw(canvas)
        
        # Speech bubble background (rounded rectangle)
        bubble_bbox = [bubble_x, bubble_y, bubble_x + bubble_width, bubble_y + bubble_height]
        draw.rounded_rectangle(bubble_bbox, radius=15, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=2)
        
        # Draw pointer/tail to the character (pointing left)
        pointer_points = [
            (bubble_x + 40, bubble_y + bubble_height),
            (bubble_x - 10, bubble_y + bubble_height + 30),
            (bubble_x + 20, bubble_y + bubble_height),
        ]
        draw.polygon(pointer_points, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
        
        # Prepare text font with smart scaling (enlarge for short messages, shrink only if needed)
        font_size = 36
        font = self._get_font(font_size)
        lines = self._wrap_text(text, draw, font, bubble_width - 20)

        # Try to enlarge font for short messages while it still fits
        max_font = 96
        while font_size < max_font:
            next_size = font_size + 4
            next_font = self._get_font(next_size)
            next_lines = self._wrap_text(text, draw, next_font, bubble_width - 20)

            # Compute dimensions for next size
            next_total_height = len(next_lines) * (next_size + 4)
            next_max_line_width = 0
            for line in next_lines:
                bbox = draw.textbbox((0, 0), line, font=next_font)
                next_max_line_width = max(next_max_line_width, bbox[2] - bbox[0])

            if next_total_height <= bubble_height - 20 and next_max_line_width <= bubble_width - 20:
                font_size = next_size
                font = next_font
                lines = next_lines
            else:
                break

        # If text still doesn't fit, reduce font until it fits
        attempts = 0
        while (len(lines) * (font_size + 4) > bubble_height - 20 or
               max((draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0]) for line in lines) > bubble_width - 20) and font_size > 10 and attempts < 20:
            font_size -= 2
            font = self._get_font(font_size)
            lines = self._wrap_text(text, draw, font, bubble_width - 20)
            attempts += 1
        
        # Draw text centered in bubble
        total_text_height = len(lines) * (font_size + 4)
        text_y = bubble_y + (bubble_height - total_text_height) // 2
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            text_x = bubble_x + (bubble_width - line_width) // 2
            draw.text((text_x, text_y), line, fill=(0, 0, 0, 255), font=font)
            text_y += font_size + 4
        
        # Auto-crop transparent edges
        canvas = self._autocrop_image(canvas)
        
        # Save to bytes
        image_bytes = BytesIO()
        canvas.save(image_bytes, format="PNG")
        image_bytes.seek(0)
        
        return image_bytes

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Get a TrueType font at the requested size with Windows fallbacks."""
        candidates = [
            # Generic names (if fontconfig resolves them)
            "Arial.ttf",
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "FreeSans.ttf",
            "NotoSans-Regular.ttf",
            # Windows common paths
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/ARIAL.TTF",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/SEGOEUI.TTF",
            "C:/Windows/Fonts/tahoma.ttf",
            "C:/Windows/Fonts/TAHOMA.TTF",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/CALIBRI.TTF",
            # Linux/Raspberry Pi common paths
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "/usr/share/fonts/truetype/droid/DroidSans.ttf",
            "/usr/share/fonts/truetype/ttf-bitstream-vera/Vera.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _wrap_text(self, text: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """Wrap text to fit within max_width."""
        lines = []
        words = text.split()
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_width = bbox[2] - bbox[0]
            
            if line_width > max_width and current_line:
                lines.append(current_line)
                current_line = word
            else:
                current_line = test_line
        
        if current_line:
            lines.append(current_line)
        
        return lines

    def _autocrop_image(self, img: Image.Image) -> Image.Image:
        """Remove transparent borders from image."""
        # Get the alpha channel
        alpha = img.split()[-1] if img.mode == "RGBA" else None
        
        if not alpha:
            return img
        
        # Find bounding box of non-transparent pixels
        bbox = alpha.getbbox()
        
        if bbox:
            return img.crop(bbox)
        
        return img

async def setup(bot: commands.Bot) -> None:
    """Load the Novelty cog."""
    await bot.add_cog(Novelty(bot))
