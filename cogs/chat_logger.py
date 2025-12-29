import asyncio
import datetime
import json
from collections import defaultdict
from typing import Any, Dict

import discord
from discord.ext import commands

from constants import CHAT_LOG_DIR
from logger_config import get_logger

logger = get_logger(__name__)


class ChatLogger(commands.Cog):
    """Cog that batches guild chat logs to NDJSON for later analysis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.buffer: list[Dict[str, Any]] = []
        self.max_buffer = 50  # flush early if many messages arrive
        self.flush_interval_seconds = 3 * 60 * 60  # every few hours
        self._lock = asyncio.Lock()
        self._flush_task = self.bot.loop.create_task(self._flush_periodically())

    async def _flush_periodically(self) -> None:
        """Background task that flushes the buffer periodically."""
        try:
            while True:
                await asyncio.sleep(self.flush_interval_seconds)
                await self.flush()
        except asyncio.CancelledError:
            # Graceful shutdown
            pass
        except Exception as e:
            logger.error(f"ChatLogger periodic flush error: {type(e).__name__}: {e}")

    async def _enqueue(self, record: Dict[str, Any]) -> None:
        """Add a record to the buffer and flush if it grows too large."""
        self.buffer.append(record)
        if len(self.buffer) >= self.max_buffer:
            await self.flush()

    async def flush(self) -> int:
        """Persist buffered messages to disk as NDJSON, one file per day.

        Returns:
            int: Number of messages written (0 if nothing was flushed).
        """
        async with self._lock:
            if not self.buffer:
                return 0

            # Copy and clear to avoid holding messages during I/O
            to_write = self.buffer.copy()
            self.buffer.clear()
            count = len(to_write)

        def _write() -> None:
            CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)

            # Group records by date string (YYYY-MM-DD) derived from their timestamp
            grouped: dict[str, list[dict]] = defaultdict(list)
            for record in to_write:
                ts = str(record.get("ts", ""))
                date_key = ts[:10] if len(ts) >= 10 else datetime.date.today().isoformat()
                grouped[date_key].append(record)

            for date_key, records in grouped.items():
                path = CHAT_LOG_DIR / f"{date_key}.ndjson"
                with path.open("a", encoding="utf-8") as f:
                    for rec in records:
                        f.write(json.dumps(rec, ensure_ascii=True))
                        f.write("\n")

        try:
            await asyncio.to_thread(_write)
            logger.debug(f"ChatLogger wrote {count} messages into {CHAT_LOG_DIR}")
            return count
        except Exception as e:
            logger.error(f"ChatLogger flush failed: {type(e).__name__}: {e}")
            # If write fails, re-queue messages for a later attempt
            async with self._lock:
                self.buffer[:0] = to_write + self.buffer
            return 0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Capture guild text messages for logging; skip bots and DMs."""
        if message.author.bot:
            return
        if not message.guild:
            return

        timestamp = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        record: Dict[str, Any] = {
            "ts": timestamp,
            "guild_id": message.guild.id,
            "channel_id": message.channel.id,
            "message_id": message.id,
            "author_id": message.author.id,
            "author_display": getattr(message.author, "display_name", message.author.name),
            "content": message.content or "",
        }

        try:
            await self._enqueue(record)
        except Exception as e:
            logger.error(f"ChatLogger enqueue failed: {type(e).__name__}: {e}")

    def cog_unload(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
        # Best-effort final flush
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.flush())
        except RuntimeError:
            # No running loop; ignore
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChatLogger(bot))
