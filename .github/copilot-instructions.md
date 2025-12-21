## AI Coding Agent Instructions for D&D Bot

- Purpose: discord.py 2.x guild-scoped slash-command bot for D&D 5e utilities (dice, books, sheet scraper, weather, reference lookups).

### Quick start
- Install: `pip install -r requirements.txt` (Playwright users may need `python -m playwright install chromium`).
- Env: `.env` with DISCORD_TOKEN, TEST_GUILD_ID, PRIVATE_URL_BASE; OPENWEATHERMAP_KEY optional (disables weather if missing).
- Run: `python main.py` (config validated before startup; HTTP session opened/closed around bot lifecycle).

### Core architecture
- [main.py](../main.py): builds `commands.Bot` (no prefix commands), loads cogs from cogs/*.py (sorted, skips leading `_`), logs per-cog failures, starts after `HTTP.open()`. `on_ready` copies global commands to TEST_GUILD_ID and syncs guild-only.
- [config.py](../config.py): single source of env; always reference `Config.*` instead of `os.getenv`. Requires DISCORD_TOKEN/TEST_GUILD_ID/PRIVATE_URL_BASE; warns if OPENWEATHERMAP_KEY missing.
- [http_manager.py](../http_manager.py): singleton aiohttp session (30s timeout) with `fetch_json/text/bytes`; use `HTTP.fetch_json(...)` for all external requests to reuse session and centralize errors.
- [logger_config.py](../logger_config.py): use `get_logger(__name__)`; INFO default format with timestamp/module.

### Interaction patterns
- Slash only via `@app_commands.command`; long work defers with `await interaction.response.defer()` then `interaction.followup.send(...)`.
- Views limit control to caller by checking `interaction.user.id` (see RollView, PageView, OnThisDayView, UrbanDictionaryView); embed toggles done by editing messages.
- JSON loads guard FileNotFoundError/JSONDecodeError and fall back to empty data while logging.

### Data and assets
- Book links: [data/books.json](../data/books.json) category→book→edition with ddb/pdf URLs.
- Character mapping: [data/character_map.json](../data/character_map.json) maps Discord user ID (string) → D&D Beyond character ID used by sheet scraper.
- Weather cache: [data/weather_locations.json](../data/weather_locations.json) persists user → location.
- Page images: spells/monsters/items in [data/spells](../data/spells), [data/monsters](../data/monsters), [data/items](../data/items); images served from `Config.PRIVATE_URL_BASE/{source}/{page}.jpg` (source codes XPHB/XGE/TCE/MPMM/XMM/XDMG).

### Cog notes
- [cogs/books.py](../cogs/books.py): embeds core/expansion book links; fails gracefully if data missing.
- [cogs/book_pages.py](../cogs/book_pages.py): spells/monsters/items autocomplete built from JSON; PageView paginates images with source-aware page caps; only invoker can page.
- [cogs/roll.py](../cogs/roll.py): `DICE_BLOCK_REGEX` parses blocks (keep-high/low, rerolls); safe arithmetic via AST; breakdown shown/hidden via buttons.
- [cogs/sheet.py](../cogs/sheet.py): Playwright Chromium scrape of D&D Beyond; shared browser guarded by asyncio.Lock; pulls abilities, saves, skills, avatar, and builds embed + link button. Cleaned in `cog_unload`.
- [cogs/weather.py](../cogs/weather.py): OpenWeatherMap via HTTP singleton; ZIP detection for zip vs city; stores user default location back to JSON.
- [cogs/on_this_day.py](../cogs/on_this_day.py): Wikipedia REST feed with custom UA; paginated view for events.
- [cogs/urban_dictionary.py](../cogs/urban_dictionary.py): Urban Dictionary API; pagination with sanitized definitions.
- [cogs/info.py](../cogs/info.py): botinfo/guildinfo/userinfo/avatar; psutil data via `asyncio.to_thread` with short cache; presence cleared on ready.
- [cogs/novelty.py](../cogs/novelty.py): 8ball + date-delta novelty command.

### Conventions and gotchas
- Keep new commands slash-only; include `async def setup(bot): await bot.add_cog(MyCog(bot))`.
- Respect Config: bail early when required env missing; weather command exits if no OPENWEATHERMAP_KEY.
- When adding HTTP calls, pass through `HTTP.fetch_*` and consider headers (see OnThisDay USER_AGENT).
- When building embeds with large text (roll breakdown), truncate around 1900 chars to fit Discord limits.
- If scraping or long I/O, defer immediately to avoid 3s interaction timeout.

### When extending
- For new data-backed commands, load JSON with error handling and log counts loaded (see book_pages _load_data).
- For new paginated views, mirror existing interaction_check patterns to restrict to invoker and update buttons on state change.
- If adding new env/config, extend Config.load validation and log warnings/errors consistently.

