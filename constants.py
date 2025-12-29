"""Shared constants across the bot."""

from pathlib import Path

# Image gallery
IMAGES_DIR = Path("data") / "images"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Data files
CHARACTER_MAP_FILE = Path("data") / "character_map.json"
SHEET_CACHE_FILE = Path("data") / "sheet_cache.json"
WEATHER_LOCATIONS_FILE = Path("data") / "weather_locations.json"
BOOKS_FILE = Path("data") / "books.json"
CHAT_LOG_DIR = Path("data") / "chat_logs"

# Data directories
SPELLS_DIR = Path("data") / "spells"
MONSTERS_DIR = Path("data") / "monsters"
ITEMS_DIR = Path("data") / "items"

# Max pages per book source
MAX_PAGES_BY_SOURCE = {
    "XPHB": 384,
    "XGE": 193,
    "TCE": 192,
    "MPMM": 288,
    "XMM": 384,
    "XDMG": 379,
}

# Source display names
SOURCE_DISPLAY = {
    "XPHB": "Player's Handbook (2024)",
    "XGE": "Xanathar's Guide to Everything (2017)",
    "TCE": "Tasha's Cauldron of Everything (2020)",
    "MPMM": "Monsters of the Multiverse (2022)",
    "XMM": "Monster Manual (2024)",
    "XDMG": "Dungeon Master's Guide (2024)",
}
