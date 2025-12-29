import os
import platform
from dotenv import load_dotenv
from logger_config import get_logger

logger = get_logger(__name__)

# Load environment variables from .env file
load_dotenv()

class Config:
    """Bot configuration from environment variables."""
    
    DISCORD_TOKEN: str | None = None
    TEST_GUILD_ID: int | None = None
    OPENWEATHERMAP_KEY: str | None = None
    PRIVATE_URL_BASE: str | None = None
    SHEET_PROXY_BASE: str | None = None
    TMDB_API_KEY: str | None = None
    
    @classmethod
    def load(cls) -> bool:
        """Load and validate configuration.
        
        Returns:
            bool: True if all required config is valid, False otherwise.
        """
        system_name = platform.system().lower()
        token_key = "DISCORD_TOKEN" if system_name != "windows" else "DEV_DISCORD_TOKEN"
        guild_key = "TEST_GUILD_ID" if system_name != "windows" else "DEV_TEST_GUILD_ID"

        cls.DISCORD_TOKEN = os.getenv(token_key)
        cls.PRIVATE_URL_BASE = os.getenv("PRIVATE_URL_BASE")
        cls.SHEET_PROXY_BASE = os.getenv("SHEET_PROXY_BASE")
        
        guild_id_str = os.getenv(guild_key)
        if guild_id_str:
            try:
                cls.TEST_GUILD_ID = int(guild_id_str)
            except ValueError:
                logger.error(f"Invalid {guild_key}: '{guild_id_str}' is not a valid integer")
                return False
        # Optional external API keys
        cls.OPENWEATHERMAP_KEY = os.getenv("OPENWEATHERMAP_KEY")
        if not cls.OPENWEATHERMAP_KEY:
            logger.warning("OPENWEATHERMAP_KEY not set — weather commands will be disabled")
        
        cls.TMDB_API_KEY = os.getenv("TMDB_API_KEY")
        if not cls.TMDB_API_KEY:
            logger.warning("TMDB_API_KEY not set — movie commands will use local fallback data")
        
        # Optional remote sheet proxy base URL
        if not cls.SHEET_PROXY_BASE:
            logger.warning("SHEET_PROXY_BASE not set — /sheet will use cached data if PC is unavailable")
        
        # Validate required settings
        if not cls.DISCORD_TOKEN:
            logger.error(f"{token_key} is not set in environment variables")
            return False
        
        if not cls.TEST_GUILD_ID:
            logger.error(f"{guild_key} is not set or invalid in environment variables")
            return False

        if not cls.PRIVATE_URL_BASE:
            logger.error("PRIVATE_URL_BASE not set")
            return False
        
        logger.info(
            f"Configuration loaded successfully (Guild ID: {cls.TEST_GUILD_ID}; token key: {token_key}; guild key: {guild_key})"
        )
        return True
    
    @classmethod
    def is_valid(cls) -> bool:
        """Check if configuration is valid without logging."""
        return bool(cls.DISCORD_TOKEN and cls.TEST_GUILD_ID)
