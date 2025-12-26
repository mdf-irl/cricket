import discord
from discord.ext import commands
from discord import app_commands, ui
from urllib.parse import urlencode, quote_plus

from logger_config import get_logger
from config import Config
from http_manager import HTTP

logger = get_logger(__name__)

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_SEARCH_URL = f"{TMDB_API_BASE}/search/movie"
TMDB_MOVIE_URL = f"{TMDB_API_BASE}/movie"
TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"


class MovieView(ui.View):
    """View with a button to search DrunkenSlug."""
    
    def __init__(self, movie_title: str, movie_year: int | None):
        super().__init__(timeout=None)
        
        # Build search query: "Movie Title Year 1080p"
        year_str = f" {movie_year}" if movie_year else ""
        search_query = f"{movie_title}{year_str} 1080p -remux"
        
        # Create DrunkenSlug URL
        drunkenslug_url = f"https://drunkenslug.com/search/{quote_plus(search_query)}?t=2000&ob=size_desc"
        
        # Add link button
        self.add_item(ui.Button(
            label="Search DrunkenSlug",
            style=discord.ButtonStyle.link,
            url=drunkenslug_url,
            emoji="🔍"
        ))


class Movies(commands.Cog):
    """Movie information cog with details from TMDb API."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _fetch_movie_by_id(self, movie_id: int) -> dict | None:
        """Fetch single movie data from TMDb by ID with credits."""
        if not Config.TMDB_API_KEY:
            return None
        
        try:
            details_params = {
                "api_key": Config.TMDB_API_KEY,
                "append_to_response": "credits",
            }
            details_url = f"{TMDB_MOVIE_URL}/{movie_id}?" + urlencode(details_params)
            details = await HTTP.fetch_json(details_url)
            
            # Extract director from appended credits
            director = "N/A"
            credits = details.get("credits", {}) if isinstance(details, dict) else {}
            crew = credits.get("crew", []) if isinstance(credits, dict) else []
            for person in crew:
                if person.get("job") == "Director":
                    director = person.get("name", "N/A")
                    break
            
            return {
                "id": movie_id,
                "title": details.get("title", "Unknown"),
                "year": int(details.get("release_date", "")[:4]) if details.get("release_date") else None,
                "director": director,
                "genre": ", ".join([g.get("name", "") for g in details.get("genres", [])]) or "Unknown",
                "plot": details.get("overview", "No plot available"),
                "runtime": details.get("runtime", 0),
                "poster_path": details.get("poster_path"),
            }
        except Exception as e:
            logger.warning(f"Error fetching TMDb movie {movie_id}: {e}")
            return None

    async def _fetch_from_tmdb(self, title: str) -> dict | None:
        """Search TMDb and return first result with full details."""
        if not Config.TMDB_API_KEY:
            return None
        
        try:
            # Search for the movie
            search_params = {
                "api_key": Config.TMDB_API_KEY,
                "query": title,
                "page": 1,
            }
            search_url = TMDB_SEARCH_URL + "?" + urlencode(search_params)
            response = await HTTP.fetch_json(search_url)
            
            if not response.get("results"):
                return None
            
            # Get first result and fetch full details
            first_result = response["results"][0]
            movie_id = first_result.get("id")
            if not movie_id:
                return None
            
            return await self._fetch_movie_by_id(movie_id)
        
        except Exception as e:
            logger.warning(f"Error searching TMDb for '{title}': {e}")
            return None

    def _format_movie_embed(self, movie: dict) -> discord.Embed:
        """Format movie data into a Discord embed."""
        title = movie.get("title", "Unknown")
        year = movie.get("year", "?")
        director = movie.get("director", "N/A")
        genre = movie.get("genre", "Unknown")
        plot = movie.get("plot", "No plot available")
        runtime = movie.get("runtime", "?")
        poster_path = movie.get("poster_path")

        embed = discord.Embed(
            title=f"🎬 {title} ({year})",
            description=plot[:300] + "..." if len(str(plot)) > 300 else plot,
            color=discord.Color.purple()
        )

        # Add poster thumbnail if available
        if poster_path:
            embed.set_thumbnail(url=f"{TMDB_POSTER_BASE}{poster_path}")

        # Add fields
        if director != "N/A":
            embed.add_field(name="📽️ Director", value=director, inline=True)
        embed.add_field(name="🏷️ Genre", value=genre, inline=True)
        embed.add_field(name="⏱️ Runtime", value=f"{runtime} min" if runtime else "N/A", inline=True)

        embed.set_footer(text="🔋 Powered by TMDb")
        return embed

    @app_commands.command(name="movie", description="Get information about a movie from TMDb.")
    @app_commands.describe(title="The movie title to look up")
    async def movie(self, interaction: discord.Interaction, title: str) -> None:
        """Display movie information from TMDb API."""
        await interaction.response.defer()

        if not Config.TMDB_API_KEY:
            await interaction.followup.send(
                "❌ TMDb API key not configured. Please set TMDB_API_KEY.",
                ephemeral=True,
            )
            return

        # Only accept autocomplete selections (id|title format or just id)
        if "|" not in title:
            # Check if it's just a numeric ID
            try:
                tmdb_id = int(title)
            except ValueError:
                await interaction.followup.send(
                    "❌ Please select a movie from the autocomplete dropdown.",
                    ephemeral=True,
                )
                return
        else:
            # Parse id|title format
            parts = title.split("|", 1)
            try:
                tmdb_id = int(parts[0])
            except ValueError:
                await interaction.followup.send(
                    "❌ Invalid selection. Please try again.",
                    ephemeral=True,
                )
                return

        # Fetch exact movie by id from autocomplete selection
        try:
            movie_data = await self._fetch_movie_by_id(tmdb_id)
            if movie_data:
                embed = self._format_movie_embed(movie_data)
                view = MovieView(movie_data.get("title", ""), movie_data.get("year"))
                await interaction.followup.send(embed=embed, view=view)
                logger.info(f"Movie fetched by {interaction.user}: {movie_data.get('title')} (id: {tmdb_id})")
                return
            else:
                await interaction.followup.send(
                    "❌ Could not fetch movie details. Please try again.",
                    ephemeral=True,
                )
        except (ValueError, Exception) as e:
            logger.warning(f"Error fetching movie: {e}")
            await interaction.followup.send(
                "❌ An error occurred. Please select from the autocomplete dropdown.",
                ephemeral=True,
            )

    @movie.autocomplete("title")
    async def movie_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete movie titles directly from TMDb, sorted by earliest year first."""
        if not Config.TMDB_API_KEY or not current:
            return []

        try:
            params = {
                "api_key": Config.TMDB_API_KEY,
                "query": current,
                "page": 1,
            }
            search_url = TMDB_SEARCH_URL + "?" + urlencode(params)
            resp = await HTTP.fetch_json(search_url)
            results = resp.get("results", [])

            # Sort by earliest release year first
            def _year(r: dict) -> int:
                rd = (r.get("release_date") or "")[:4]
                try:
                    return int(rd)
                except Exception:
                    return 9999  # push undated items to the end

            sorted_results = sorted(
                results,
                key=lambda r: (_year(r), (r.get("title") or r.get("name") or "").lower()),
            )

            choices: list[app_commands.Choice[str]] = []
            for r in sorted_results[:25]:
                title = r.get("title") or r.get("name") or "Untitled"
                year = (r.get("release_date") or "")[:4]
                tmdb_id = r.get("id")
                if not tmdb_id:
                    continue
                display = f"{title} ({year})" if year else title
                # Encode id in value - truncate title to ensure under 100 char limit
                # Format: "id|title" but limit total to 95 chars to be safe
                title_truncated = title[:80] if len(title) > 80 else title
                value = f"{tmdb_id}|{title_truncated}"
                if len(value) > 95:
                    # If still too long, just use the ID
                    value = str(tmdb_id)
                choices.append(app_commands.Choice(name=display, value=value))

            return choices
        except Exception:
            # On error, return no suggestions
            return []


async def setup(bot: commands.Bot) -> None:
    """Load the Movies cog."""
    await bot.add_cog(Movies(bot))
