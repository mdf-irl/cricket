# AI Coding Agent Instructions for D&D Bot

## Project Overview
This is a Discord bot built with discord.py that serves D&D 5e community features. The bot uses a modular cog-based architecture with async/await patterns throughout. It integrates with external APIs via an HTTP manager for fetching data, manages local JSON data, and provides dice rolling, character sheets, weather, and book reference features.

**Key Stack:** Python 3.9+, discord.py 2.0+, aiohttp, discord slash commands (app_commands)

## Architecture

### Core Components

1. **main.py** - Bot bootstrap & lifecycle
   - Initializes `commands.Bot` with slash commands (command_prefix=None, no legacy prefix commands)
   - Dynamic cog loading from `./cogs/` directory with per-cog exception handling
   - `on_ready` event syncs slash commands to TEST_GUILD_ID for rapid iteration (guild-scoped for testing, not global)
   - HTTP session managed via `await HTTP.open()` in main() and lifecycle cleanup

2. **config.py** - Configuration & validation
   - Loads .env via python-dotenv; exposes DISCORD_TOKEN, TEST_GUILD_ID, OPENWEATHERMAP_KEY
   - **Pattern:** Use `Config.DISCORD_TOKEN`, not `os.getenv()` directly
   - `Config.load()` validates required fields before startup; logs warnings for optional keys (e.g., OPENWEATHERMAP_KEY)

3. **http_manager.py** - Singleton HTTP client
   - `aiohttp.ClientSession` singleton with 30-second timeout
   - Methods: `fetch_json()`, `fetch_text()`, `fetch_bytes()`
   - **Pattern:** All external requests use `await HTTP.fetch_json(url)`, never raw requests
   - Auto-opens session via `_ensure_session()` if closed

4. **logger_config.py** - Centralized logging
   - All modules import via `from logger_config import get_logger; logger = get_logger(__name__)`
   - INFO level by default; captures errors per operation

5. **cogs/** - Feature modules
   - Each cog inherits `commands.Cog`, implements `async def setup(bot)` at EOF
   - Commands use `@app_commands.command` decorator (slash commands only)
   - Cogs can load JSON data (Books) or call HTTP APIs (Weather) or compute logic (Roll)
   - See current cogs: Books (local data), Roll (dice logic), Weather (external API), Sheet (character data)

### Data Storage
- **data/books.json:** Category → Book → Edition Year → Links (ddb, pdf)
- **data/character_map.json:** Maps user/character IDs to sheet data
- JSON errors caught with fallback to empty dict; logged as warnings

### Data Flow
```
main.py (validate config)
  → HTTP.open() (session lifecycle)
  → load_cogs() (scans ./cogs/*.py, catches errors per cog)
    → each Cog.__init__() loads local data or prepares HTTP calls
    → each @app_commands.command() handler uses HTTP or local data
```

## Developer Workflows

### Running the Bot
```powershell
# Install dependencies
pip install -r requirements.txt

# Create .env file with:
# DISCORD_TOKEN=your_token_here
# TEST_GUILD_ID=your_guild_id_here
# OPENWEATHERMAP_KEY=your_api_key_here  # optional, disables weather if missing

# Run bot
python main.py
```

### Adding New Commands
1. Create `cogs/feature_name.py` inheriting from `commands.Cog`
2. Define `__init__(self, bot: commands.Bot)` storing `self.bot = bot` and loading any local data
3. Implement command methods with `@app_commands.command(name="cmd_name", description="...")` decorator
4. Use async/await throughout; call `await interaction.response.defer()` for long operations, then `await interaction.followup.send()`
5. Use logger via `from logger_config import get_logger; logger = get_logger(__name__)`
6. Include `async def setup(bot): await bot.add_cog(FeatureName(bot))` at EOF
7. Bot auto-discovers .py files in ./cogs/ during load_cogs() (sorted alphabetically)

### Data Loading Pattern (Books cog example)
```python
def __init__(self, bot: commands.Bot):
    self.bot = bot
    self.books_data = self.load_books_data()

def load_books_data(self) -> dict:
    try:
        with open(os.path.join("data", "books.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Loaded books data")
            return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading books.json: {e}")
        return {}
```

### HTTP API Pattern (Weather cog example)
```python
async def _fetch_data(self, url: str) -> dict | None:
    try:
        data = await HTTP.fetch_json(url)
        return data
    except Exception as e:
        logger.error(f"Error fetching: {type(e).__name__}: {e}")
        return None

@app_commands.command(name="weather", description="Get weather")
async def weather(self, interaction: discord.Interaction, location: str) -> None:
    await interaction.response.defer()
    data = await self._fetch_data(f"{BASE_URL}?q={location}&appid={Config.OPENWEATHERMAP_KEY}")
    if not data:
        await interaction.followup.send("Error fetching data", ephemeral=True)
        return
    # ... format and send response
```

## Key Conventions

### Async/Await Patterns
- All interactions are async (discord.py 2.0 requirement)
- Cog methods: `async def method_name(self, ...)`
- HTTP calls: `data = await HTTP.fetch_json(url)`
- Deferred interactions: `await interaction.response.defer()` then `await interaction.followup.send(message, ephemeral=True)`
- Discord buttons/views: use `@ui.button()` decorator with timeout, check `interaction.user.id` for permission

### Naming & Structure
- Cog classes: PascalCase (Books, Roll, Weather, Sheet)
- Cog file names: lowercase (books.py, roll.py, weather.py, sheet.py)
- Command names: lowercase with underscores, passed in decorator
- Button/View names: PascalCase (RollView from roll.py uses View + Button)

### Error Handling Strategy
- **Per-cog loading errors:** main.py catches ExtensionNotFound, ExtensionAlreadyLoaded, NoEntryPointError, ExtensionFailed, generic Exception
- **JSON errors:** catch FileNotFoundError + JSONDecodeError, log + return empty dict
- **HTTP errors:** catch generic Exception in try/except, log error details with type name, return None
- **API missing errors:** check `if not Config.OPENWEATHERMAP_KEY` before calling, log warning, send user-facing error

### Logging
- Import via `from logger_config import get_logger; logger = get_logger(__name__)`
- Use logger.info(), logger.error(), logger.warning() throughout
- Log at operation boundaries (cog loading, data loaded, API calls, errors)
- Include context: `logger.error(f"Failed X: {type(e).__name__}: {e}")`

## Integration Points

### Discord.py Slash Commands
- `@app_commands.command(name="cmd", description="Help text")`
- `await interaction.response.send_message(embed=discord.Embed(...), view=MyView(...), ephemeral=True)`
- Use embeds with color, title, description, fields for rich formatting
- Views/Buttons for interactive responses; check user_id for permission

### External APIs
- All HTTP requests via HTTP singleton: `await HTTP.fetch_json(url)`
- URL building: use urllib.parse.urlencode() for query params
- Handle missing API keys gracefully (e.g., Config.OPENWEATHERMAP_KEY check)

### Guild Syncing
- Commands sync to TEST_GUILD_ID in on_ready() via `bot.tree.sync(guild=discord.Object(id=TEST_GUILD_ID))`
- Guild-scoped sync for fast testing (not global deployment)
- Sync errors (Forbidden, HTTPException) caught and logged

## Cog Reference

| Cog | Pattern | Data Source | Key Features |
|-----|---------|-------------|--------------|
| **books.py** | Local JSON | data/books.json | Categories, editions, links (DDB/PDF) |
| **roll.py** | Dice logic | DICE_BLOCK_REGEX parsing | 4d6kh3r1, rerolls, breakdowns, View buttons |
| **weather.py** | External API | openweathermap.org | City/ZIP lookup, error handling, defer+followup |
| **sheet.py** | Local JSON | data/character_map.json | User character management |

## File References
- **main.py:** Bot lifecycle (validate → HTTP.open → load_cogs → start), cog loading error handling, guild sync in on_ready
- **config.py:** Config.load() validation, optional API keys with warnings
- **http_manager.py:** HTTP.fetch_json/fetch_text/fetch_bytes patterns, singleton session management
- **logger_config.py:** get_logger(name) for all modules
- **cogs/books.py:** JSON loading pattern, category → book → edition structure
- **cogs/roll.py:** Dice regex parsing (DICE_BLOCK_REGEX), View/Button UI patterns, breakdown logic
- **cogs/weather.py:** HTTP API pattern, deferred interactions, error handling
- **cogs/sheet.py:** Character data management, user ID mapping

