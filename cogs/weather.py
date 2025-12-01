import discord
from discord.ext import commands
from discord import app_commands
from urllib.parse import urlencode

from logger_config import get_logger
from http_manager import HTTP
from config import Config

logger = get_logger(__name__)

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


class WeatherCog(commands.Cog):
    """Weather cog using OpenWeatherMap and the project's HTTP manager."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_called = None

    async def _fetch_weather(self, params: dict) -> dict | None:
        """Fetch weather JSON using the shared HTTP manager."""
        # Build URL with query params
        url = f"{BASE_URL}?{urlencode(params)}"
        try:
            data = await HTTP.fetch_json(url)
            return data
        except Exception as e:
            logger.error(f"Error fetching weather data: {type(e).__name__}: {e}")
            return None

    @app_commands.command(name="weather", description="Get current weather by city or US ZIP code.")
    async def weather(self, interaction: discord.Interaction, location: str) -> None:
        await interaction.response.defer()

        if not Config.OPENWEATHERMAP_KEY:
            await interaction.followup.send(
                "❌ Weather API key not configured. Contact the bot admin.",
                ephemeral=True,
            )
            logger.warning("Weather command attempted but OPENWEATHERMAP_KEY is missing")
            return


        # Build params
        params = {"appid": Config.OPENWEATHERMAP_KEY, "units": "imperial"}
        if location.isdigit() and len(location) == 5:
            params["zip"] = f"{location},us"
        else:
            params["q"] = location

        data = await self._fetch_weather(params)

        if not data:
            await interaction.followup.send(
                "❌ Could not retrieve weather information. Please try again later.",
                ephemeral=True,
            )
            return

        # API may return cod as str or int
        cod = data.get("cod")
        try:
            cod_int = int(cod)
        except Exception:
            cod_int = 0

        if cod_int != 200:
            message = data.get("message", "Unknown error")
            await interaction.followup.send(f"❌ `{message}`")
            return

        try:
            main = data.get("main", {})
            weather = data.get("weather", [{}])[0]
            wind = data.get("wind", {})
            clouds = data.get("clouds", {})

            city = data.get("name", "Unknown")
            icon = weather.get("icon", "01d")
            icon_url = f"https://openweathermap.org/img/wn/{icon}@2x.png"

            embed = discord.Embed(
                title=f"Current Weather — {city}",
                description=weather.get("description", "N/A").title(),
                color=discord.Color.blue(),
            )
            embed.set_thumbnail(url=icon_url)

            temp = main.get("temp")
            feels = main.get("feels_like")
            humidity = main.get("humidity")
            wind_speed = wind.get("speed")
            temp_min = main.get("temp_min")
            temp_max = main.get("temp_max")

            if temp is not None:
                embed.add_field(name="🌡 Temperature", value=f"{temp:.1f}°F")
            if feels is not None:
                embed.add_field(name="🧊 Feels Like", value=f"{feels:.1f}°F")
            if humidity is not None:
                embed.add_field(name="💧 Humidity", value=f"{humidity}%")
            if wind_speed is not None:
                embed.add_field(name="💨 Wind Speed", value=f"{wind_speed:.1f} mph")
            if temp_min is not None and temp_max is not None:
                embed.add_field(name="⬇️ Low / ⬆️ High", value=f"{temp_min:.1f}°F / {temp_max:.1f}°F")
            embed.add_field(name="☁️ Cloud Coverage", value=f"{clouds.get('all', 0)}%")

            embed.set_footer(text="Powered by OpenWeatherMap")

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
