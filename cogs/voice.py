import discord
from discord.ext import commands
from discord import app_commands
from pathlib import Path
import shutil

from logger_config import get_logger

logger = get_logger(__name__)

SOUNDS_DIR = Path("data/sounds")

# Try to locate ffmpeg (explicit path on Windows, fallback to PATH)
FFMPEG_PATH = shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"


class Voice(commands.Cog):
    """Voice channel management cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.available_sounds = self._load_available_sounds()

    def _load_available_sounds(self) -> dict[str, str]:
        """Load available sound files from data/sounds directory.
        
        Returns:
            Dictionary mapping sound name (lowercase, no extension) to full file path.
        """
        sounds = {}
        
        if not SOUNDS_DIR.exists():
            logger.warning(f"Sounds directory not found: {SOUNDS_DIR}")
            return sounds
        
        # Support common audio formats
        for ext in ["*.wav", "*.mp3", "*.ogg", "*.flac"]:
            for sound_file in SOUNDS_DIR.glob(ext):
                sound_name = sound_file.stem.lower()
                sounds[sound_name] = str(sound_file)
        
        logger.info(f"Loaded {len(sounds)} sound(s) from {SOUNDS_DIR}")
        return sounds

    @app_commands.command(name="joinvoice", description="Join your current voice channel.")
    async def joinvoice(self, interaction: discord.Interaction) -> None:
        """Join the voice channel that the command invoker is currently in."""
        await interaction.response.defer()

        # Check if the user is in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(
                "❌ You are not in a voice channel.",
                ephemeral=True,
            )
            logger.warning(f"joinvoice command invoked by {interaction.user} but they are not in a voice channel")
            return

        voice_channel = interaction.user.voice.channel

        try:
            # Check if bot is already in a voice channel in this guild
            if interaction.guild.voice_client:
                # If already in a channel, move to the new one
                await interaction.guild.voice_client.move_to(voice_channel)
                await interaction.followup.send(f"✅ Moved to **{voice_channel.name}**.")
                logger.info(f"Bot moved to voice channel: {voice_channel.name} (Guild: {interaction.guild.name})")
            else:
                # Join the voice channel
                await voice_channel.connect()
                await interaction.followup.send(f"✅ Joined **{voice_channel.name}**.")
                logger.info(f"Bot joined voice channel: {voice_channel.name} (Guild: {interaction.guild.name})")

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to join this voice channel.",
                ephemeral=True,
            )
            logger.error(f"Permission denied joining voice channel: {voice_channel.name}")
        except discord.ClientException as e:
            await interaction.followup.send(
                "❌ An error occurred while joining the voice channel.",
                ephemeral=True,
            )
            logger.error(f"Error joining voice channel: {type(e).__name__}: {e}")
        except Exception as e:
            await interaction.followup.send(
                "❌ An unexpected error occurred.",
                ephemeral=True,
            )
            logger.error(f"Unexpected error in joinvoice: {type(e).__name__}: {e}")

    @app_commands.command(name="leavevoice", description="Leave the current voice channel.")
    async def leavevoice(self, interaction: discord.Interaction) -> None:
        """Disconnect the bot from the current voice channel."""
        await interaction.response.defer()

        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            await interaction.followup.send(
                "❌ I'm not in a voice channel.",
                ephemeral=True,
            )
            logger.warning(f"leavevoice command invoked but bot is not in a voice channel")
            return

        try:
            await voice_client.disconnect()
            await interaction.followup.send("✅ Disconnected from the voice channel.")
            logger.info(f"Bot disconnected from voice channel (Guild: {interaction.guild.name})")
        except Exception as e:
            await interaction.followup.send(
                "❌ An error occurred while leaving the voice channel.",
                ephemeral=True,
            )
            logger.error(f"Error leaving voice channel: {type(e).__name__}: {e}")

    async def sound_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete available sound names."""
        if not self.available_sounds:
            return []
        
        matches = [
            app_commands.Choice(name=sound_name, value=sound_name)
            for sound_name in self.available_sounds.keys()
            if current.lower() in sound_name.lower()
        ]
        return matches[:25]

    @app_commands.command(name="sound", description="Play a sound from the sounds folder.")
    @app_commands.describe(sound="The name of the sound to play")
    @app_commands.autocomplete(sound=sound_autocomplete)
    async def sound(self, interaction: discord.Interaction, sound: str) -> None:
        """Play a sound file from data/sounds folder."""
        await interaction.response.defer()

        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            await interaction.followup.send(
                "❌ I'm not in a voice channel. Use `/joinvoice` first.",
                ephemeral=True,
            )
            logger.warning(f"sound command invoked but bot is not in a voice channel")
            return

        if voice_client.is_playing():
            await interaction.followup.send(
                "❌ Already playing a sound.",
                ephemeral=True,
            )
            return

        sound_lower = sound.lower().strip()
        if sound_lower not in self.available_sounds:
            available = ", ".join(sorted(list(self.available_sounds.keys())[:5]))
            await interaction.followup.send(
                f"❌ Sound **{sound}** not found.\n\n**Examples**: {available}...",
                ephemeral=True,
            )
            logger.warning(f"sound command invoked for non-existent sound: {sound}")
            return

        sound_path = self.available_sounds[sound_lower]

        try:
            # Use FFmpegPCMAudio with explicit executable path
            audio = discord.FFmpegPCMAudio(sound_path, executable=FFMPEG_PATH)
            voice_client.play(audio, after=lambda e: logger.error(f"Playback error: {e}") if e else None)
            await interaction.followup.send(f"🔊 Now playing **{sound}**.")
            logger.info(f"Playing sound '{sound}' in {interaction.guild.name}")
        except discord.ClientException as e:
            # More specific error message for ffmpeg issues
            if "ffmpeg" in str(e).lower():
                logger.error(f"ffmpeg not found or not working: {e}")
                await interaction.followup.send(
                    "❌ ffmpeg is not installed or not found in PATH. Please install ffmpeg to play audio.",
                    ephemeral=True,
                )
            else:
                logger.error(f"Error playing sound: {type(e).__name__}: {e}")
                await interaction.followup.send(
                    "❌ An error occurred while playing the sound.",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error playing sound: {type(e).__name__}: {e}")
            await interaction.followup.send(
                "❌ An error occurred while playing the sound.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Voice cog."""
    await bot.add_cog(Voice(bot))
