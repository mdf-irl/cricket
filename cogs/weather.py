import json
from urllib.parse import urlencode

import discord
from discord.ext import commands
from discord import app_commands

from logger_config import get_logger
from http_manager import HTTP
from config import Config
from constants import WEATHER_LOCATIONS_FILE

logger = get_logger(__name__)

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


class WeatherCog(commands.Cog):
    """Weather cog using OpenWeatherMap and the project's HTTP manager."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_locations: dict[int, str] = self._load_locations()

    def _load_locations(self) -> dict[int, str]:
        """Load user locations from JSON file."""
        try:
            with open(WEATHER_LOCATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Error loading weather locations: {e}")
            return {}

    def _save_locations(self) -> None:
        """Save user locations to JSON file."""
        try:
            WEATHER_LOCATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(WEATHER_LOCATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in self.user_locations.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving weather locations: {e}")

    @app_commands.command(name="weather", description="Get current weather by city or US ZIP code.")
    async def weather(self, interaction: discord.Interaction, location: str | None = None) -> None:
        await interaction.response.defer()

        if not Config.OPENWEATHERMAP_KEY:
            await interaction.followup.send(
                "❌ Weather API key not configured. Contact the bot admin.",
                ephemeral=True,
            )
            logger.warning("Weather command attempted but OPENWEATHERMAP_KEY is missing")
            return

        # Use stored location if none provided
        if not location:
            location = self.user_locations.get(interaction.user.id)
            if not location:
                await interaction.followup.send(
                    "❌ Please provide a location. Example: `/weather New York` or `/weather 10001`",
                    ephemeral=True,
                )
                return

        # Build params and fetch weather
        params = {"appid": Config.OPENWEATHERMAP_KEY, "units": "imperial"}
        params["zip" if location.isdigit() and len(location) == 5 else "q"] = f"{location},us" if location.isdigit() and len(location) == 5 else location

        try:
            url = f"{BASE_URL}?{urlencode(params)}"
            data = await HTTP.fetch_json(url)
        except Exception as e:
            logger.error(f"Error fetching weather data: {type(e).__name__}: {e}")
            await interaction.followup.send(
                "❌ Could not retrieve weather information. Please try again later.",
                ephemeral=True,
            )
            return

        # Validate API response code
        try:
            if int(data.get("cod", 0)) != 200:
                await interaction.followup.send(f"❌ `{data.get('message', 'Unknown error')}`")
                return
        except (ValueError, TypeError):
            pass  # If cod is invalid, proceed anyway

        try:
            main = data.get("main", {})
            weather = data.get("weather", [{}])[0]
            wind = data.get("wind", {})
            clouds = data.get("clouds", {})

            city = data.get("name", "Unknown")
            icon = weather.get("icon", "01d")

            embed = discord.Embed(
                title=f"Current Weather — {city}",
                description=weather.get("description", "N/A").title(),
                color=discord.Color.blue(),
            )
            embed.set_thumbnail(url=f"https://openweathermap.org/img/wn/{icon}@2x.png")

            # Add fields only if data exists
            if (temp := main.get("temp")) is not None:
                embed.add_field(name="🌡 Temperature", value=f"{temp:.1f}°F")
            if (feels := main.get("feels_like")) is not None:
                embed.add_field(name="🧊 Feels Like", value=f"{feels:.1f}°F")
            if (humidity := main.get("humidity")) is not None:
                embed.add_field(name="💧 Humidity", value=f"{humidity}%")
            if (wind_speed := wind.get("speed")) is not None:
                embed.add_field(name="💨 Wind Speed", value=f"{wind_speed:.1f} mph")
            if (temp_min := main.get("temp_min")) is not None and (temp_max := main.get("temp_max")) is not None:
                embed.add_field(name="⬇️ Low / ⬆️ High", value=f"{temp_min:.1f}°F / {temp_max:.1f}°F")
            embed.add_field(name="☁️ Cloud Coverage", value=f"{clouds.get('all', 0)}%")

            embed.set_footer(text="🔋 Powered by OpenWeatherMap")

            # Remember this location for the user
            self.user_locations[interaction.user.id] = location
            self._save_locations()

            await interaction.followup.send(embed=embed)
            logger.info(f"Weather for '{location}' requested by {interaction.user}")
        except Exception as e:
            logger.error(f"Error processing weather data: {type(e).__name__}: {e}")
            await interaction.followup.send(
                "❌ An error occurred while preparing the weather data.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WeatherCog(bot))
