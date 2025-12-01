# AI Coding Agent Instructions for D&D Bot

## Project Overview
This is a Discord bot built with discord.py that serves D&D 5e community features. The bot uses a modular cog-based architecture with async/await patterns throughout. It integrates with external APIs via an HTTP manager for fetching data.

**Key Stack:** Python 3.9+, discord.py 2.0+, aiohttp, discord slash commands (app_commands)

## Architecture

### Core Components

1. **main.py** - Bot bootstrap
   - Initializes discord.Bot with slash commands (command_prefix=None, no legacy prefix commands)
   - Dynamic cog loading from `./cogs/` directory
   - on_ready event syncs slash commands to TEST_GUILD_ID for rapid iteration
   - HTTP session lifecycle management (open on startup, close on shutdown)

2. **config.py** - Environment configuration
   - Loads .env file via python-dotenv
   - Exposes DISCORD_TOKEN and TEST_GUILD_ID as class attributes
   - **Pattern:** Use Config.DISCORD_TOKEN, not os.getenv() directly

3. **http_manager.py** - Shared async HTTP client
   - Singleton aiohttp.ClientSession managed via classmethod
   - Methods: fetch_json(), fetch_text(), fetch_bytes()
   - **Pattern:** Always use HTTP class for external requests (e.g., Example cog's catfact command)

4. **cogs/** - Modular command handlers
   - Each cog: inherits commands.Cog, implements async setup(bot) function
   - Commands use @app_commands.command decorator (slash commands only)
   - Access bot instance via self.bot in __init__
   - **Pattern:** Books cog loads JSON data on init, Example cog uses HTTP.fetch_json()

### Data Flow
```
main.py (entry) 
  → config (env vars) 
  → load_cogs() → cogs/*.py 
  → each cog can use HTTP.fetch_json() or load local data
```

## Developer Workflows

### Running the Bot
```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file with:
DISCORD_TOKEN=your_token_here
TEST_GUILD_ID=your_guild_id_here

# Run bot
python main.py
```

### Adding New Commands
1. Create `cogs/feature_name.py` inheriting from commands.Cog
2. Implement @app_commands.command methods
3. Include async setup(bot) function at EOF
4. Bot auto-discovers and loads on startup (load_cogs scans ./cogs/)

### Data Storage Pattern
- JSON files in `data/` directory (loaded in cog __init__)
- Example: Books cog loads `data/books.json` with nested category structure
- Format: categories → items → versions → links (see books.json structure)

## Key Conventions

### Async/Await
- All bot operations are async (dpy 2.0 requirement)
- Cog methods marked `async def`
- HTTP calls: `await HTTP.fetch_json(url)`, `await HTTP.fetch_text(url)`
- Deferred interactions: `await interaction.response.defer()` → `await interaction.followup.send()`

### Naming & Structure
- Cog class names: PascalCase (Books, Example)
- Command names: lowercase with underscores, defined in decorator (name="command_name")
- Files: lowercase with underscores (books.py, example.py)

### Error Handling
- load_cogs catches exceptions per cog (Example cog pattern shows try/except wrapping load)
- JSON loading catches FileNotFoundError with fallback (Books cog returns {} if missing)
- HTTP errors: aiohttp.ClientSession.raise_for_status() propagates on failed requests

## Integration Points

### Discord.py Slash Commands
- @app_commands.command(name="", description="")
- await interaction.response.send_message() or defer + followup
- Embeds for rich formatting (discord.Embed with color, title, description)

### External APIs
- All HTTP requests go through HTTP singleton (centralized session management)
- Example: Example.catfact calls https://catfact.ninja/fact via HTTP.fetch_json()

### Discord Guild Sync
- Commands sync to TEST_GUILD_ID (not globally) for fast testing iteration
- Syncs happen in on_ready event
- Global sync would require code change (remove guild parameter)

## Testing & Debugging

### Local Testing
- Bot logs cog loading status to stdout
- Command sync results printed in on_ready
- Failed loads show exception messages
- Use TEST_GUILD_ID to test in private guild before global deployment

### Common Issues
- Missing .env file: Config returns None values
- Cog syntax errors: load_cogs exception catch logs the error
- Deferred interactions timeout: ensure followup sent within 15 minutes

## File References
- **main.py:** Bot lifecycle, cog discovery (lines 12-19 load_cogs)
- **config.py:** Environment variable management
- **http_manager.py:** Shared HTTP client patterns (classmethod decorators)
- **cogs/books.py:** Data loading pattern, embedding/formatting
- **cogs/example.py:** HTTP integration, simple command pattern
- **data/books.json:** Nested data structure (categories → books → editions → links)
