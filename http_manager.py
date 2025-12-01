import aiohttp
from logger_config import get_logger

logger = get_logger(__name__)


class HTTP:
    """Singleton HTTP client manager for async requests."""
    
    session: aiohttp.ClientSession | None = None
    TIMEOUT = aiohttp.ClientTimeout(total=30)

    @classmethod
    async def open(cls) -> None:
        """Initialize the HTTP session."""
        if cls.session is None or cls.session.closed:
            try:
                cls.session = aiohttp.ClientSession(timeout=cls.TIMEOUT)
                # logger.info("HTTP session opened")
            except Exception as e:
                logger.error(f"Failed to open HTTP session: {type(e).__name__}: {e}")
                raise

    @classmethod
    async def close(cls) -> None:
        """Close the HTTP session gracefully."""
        if cls.session and not cls.session.closed:
            try:
                await cls.session.close()
                logger.info("HTTP session closed")
            except Exception as e:
                logger.error(f"Error closing HTTP session: {type(e).__name__}: {e}")

    @classmethod
    async def _ensure_session(cls) -> aiohttp.ClientSession:
        """Ensure session is open and return it."""
        if cls.session is None or cls.session.closed:
            await cls.open()
        if cls.session is None:
            raise RuntimeError("Failed to initialize HTTP session")
        return cls.session

    @classmethod
    async def fetch_json(cls, url: str) -> dict:
        """Fetch JSON data from URL.
        
        Args:
            url: The URL to fetch from.
            
        Returns:
            Parsed JSON data as dictionary.
            
        Raises:
            aiohttp.ClientError: Network or HTTP errors.
            ValueError: Invalid JSON response.
        """
        session = await cls._ensure_session()
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection error fetching {url}: {e}")
            raise
        except aiohttp.ClientSSLError as e:
            logger.error(f"SSL error fetching {url}: {e}")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            raise
        except ValueError as e:
            logger.error(f"Invalid JSON from {url}: {e}")
            raise

    @classmethod
    async def fetch_text(cls, url: str) -> str:
        """Fetch plain text from URL.
        
        Args:
            url: The URL to fetch from.
            
        Returns:
            Response text.
            
        Raises:
            aiohttp.ClientError: Network or HTTP errors.
        """
        session = await cls._ensure_session()
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.text()
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error fetching text from {url}: {e}")
            raise

    @classmethod
    async def fetch_bytes(cls, url: str) -> bytes:
        """Fetch binary data from URL (images, files, etc.).
        
        Args:
            url: The URL to fetch from.
            
        Returns:
            Raw binary data.
            
        Raises:
            aiohttp.ClientError: Network or HTTP errors.
        """
        session = await cls._ensure_session()
        try:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.read()
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error fetching bytes from {url}: {e}")
            raise
