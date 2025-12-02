from __future__ import annotations

import asyncio
import datetime
import platform
import time
import typing

import discord

import logger_config

try:
    import psutil
except Exception:
    psutil = None

try:
    import gpiozero
except Exception:
    gpiozero = None

logger = logger_config.get_logger(__name__)


async def setup(bot: discord.ext.commands.Bot):
    await bot.add_cog(Info(bot))


class Info(discord.ext.commands.Cog):
    """Cog exposing information commands as slash commands.

    Uses `psutil` when available. Blocking system calls are executed via
    `asyncio.to_thread` to avoid blocking the event loop.
    """

    # expose commands as top-level slash commands (no `/info` group)
    _BYTES_PER_GB = 1024 ** 3
    _is_linux = platform.system().lower() == "linux"
    _platform_name: str = platform.system()
    _machine_name: str = platform.machine()
    _stats_ttl = 5  # seconds
    _stats_cache: typing.Optional[dict[str, typing.Any]] = None

    @staticmethod
    def _format_bytes(size: int) -> str:
        """Format bytes to human-friendly GB string."""
        gb = size / Info._BYTES_PER_GB
        return f"{gb:.2f} GB"

    def __init__(self, bot: discord.ext.commands.Bot):
        self.bot = bot
        self.connected_time: datetime.datetime = datetime.datetime.utcnow()

    @discord.ext.commands.Cog.listener()
    async def on_ready(self) -> None:
        self.connected_time = datetime.datetime.utcnow()
        try:
            await self.bot.change_presence(activity=None)
        except Exception:
            # best-effort; don't fail startup
            pass

    @discord.app_commands.command(name="avatar")
    async def avatar(self, i: discord.Interaction, user: typing.Optional[discord.Member] = None) -> None:
        """Show the full-size avatar for a user (defaults to caller)."""
        target = user or i.user
        if not isinstance(target, discord.Member) and hasattr(i, "user"):
            # When outside a guild Member may not be available; use the Interaction user
            target = i.user

        embed = discord.Embed(title=f"{target.display_name}'s Full-Sized Avatar", color=discord.Color.pink())
        embed.set_image(url=target.display_avatar.url)
        await i.response.send_message(embed=embed)

    @discord.app_commands.command(name="about")
    async def about(self, i: discord.Interaction) -> None:
        """Show information about the bot and host system."""
        await i.response.defer()

        cpu = await self._cpu_info()
        mem = await self._memory_info()
        disk = await self._disk_info()

        # System info (use cached stats where possible)
        stats = await self._get_stats()
        boot = stats.get("boot") if stats else None
        booted_time = datetime.datetime.fromtimestamp(boot) if boot else None
        bot_uptime = self._format_uptime(self.connected_time)
        system_uptime = self._format_uptime(booted_time) if booted_time else "N/A"

        # Build main info embed
        embed = discord.Embed(
            title="🦗 Cricket v420.69",
            color=discord.Color.pink(),
            description=(
                f"**Latency**: {round(self.bot.latency * 1000)}ms\n"
                f"**Uptime**: {bot_uptime} (**bot**) / {system_uptime} (**system**)\n"
                # f"Powered by **discord.py** {discord.__version__} w/ Python {platform.python_version()} on {platform.system()} ({platform.machine()})"
            ),
        )

        # System stats in separate section
        embed.add_field(name="💾 CPU", value=cpu, inline=True)
        embed.add_field(name="🧠 Memory", value=mem, inline=True)
        embed.add_field(name="💿 Disk", value=disk, inline=True)

        #embed.set_footer(text=f"Uptime: {bot_uptime} (bot) / {system_uptime} (system)")
        embed.set_footer(text=f"🔋 Powered by discord.py {discord.__version__} w/ Python {platform.python_version()} on {platform.system()} ({platform.machine()})")

        await i.followup.send(embed=embed, ephemeral=True)

    async def _cpu_info(self) -> str:
        stats = await self._get_stats()
        if not stats:
            return "N/A"

        cpu_percent = stats.get("cpu_percent") or 0.0
        cpu_count = stats.get("cpu_count") or 0
        freq_cur = stats.get("freq") or "N/A"
        cpu_temp_c = stats.get("cpu_temp") or "N/A"

        return f"**Usage**: {cpu_percent:.2f}%\n**Cores**: {cpu_count} @ {freq_cur}\n**Temp**: {cpu_temp_c}"

    async def _memory_info(self) -> str:
        stats = await self._get_stats()
        if not stats:
            return "N/A"
        vm = stats.get("vm")
        if not vm:
            return "N/A"
        used = vm.used
        total = vm.total
        pct = getattr(vm, "percent", None)
        pct_display = f" ({pct:.0f}%)" if pct is not None else ""
        return f"**Used**: {self._format_bytes(used)}\n**Total**: {self._format_bytes(total)}{pct_display}"

    async def _disk_info(self) -> str:
        stats = await self._get_stats()
        if not stats:
            return "N/A"
        du = stats.get("du")
        if not du:
            return "N/A"
        used = du.used
        total = du.total
        pct = getattr(du, "percent", None)
        pct_display = f" ({pct:.0f}%)" if pct is not None else ""
        return f"**Used**: {self._format_bytes(used)}\n**Total**: {self._format_bytes(total)}{pct_display}"

    async def _get_stats(self) -> dict | None:
        """Fetch psutil stats once and cache for `_stats_ttl` seconds."""
        if not psutil:
            return None

        now = time.monotonic()
        if self._stats_cache and (now - self._stats_cache.get("ts", 0) < self._stats_ttl):
            return self._stats_cache.get("value")

        try:
            tasks = [
                asyncio.to_thread(psutil.cpu_percent, 0.1),
                asyncio.to_thread(psutil.cpu_count, False),
                asyncio.to_thread(psutil.cpu_count, True),
                asyncio.to_thread(psutil.cpu_freq),
                asyncio.to_thread(psutil.virtual_memory),
                asyncio.to_thread(psutil.disk_usage, '/'),
                asyncio.to_thread(psutil.boot_time),
            ]

            cpu_percent, cpu_count_false, cpu_count_true, freq, vm, du, boot = await asyncio.gather(*tasks)

            cpu_count = cpu_count_false or cpu_count_true or 0
            freq_cur = f"{(freq.current/1000):.2f} GHz" if freq else "N/A"

            cpu_temp = None
            if self._is_linux and gpiozero:
                try:
                    temp = await asyncio.to_thread(gpiozero.CPUTemperature)
                    cpu_temp = f"{temp.temperature:.2f} °C"
                except Exception:
                    cpu_temp = None

            value = {
                "cpu_percent": cpu_percent,
                "cpu_count": cpu_count,
                "freq": freq_cur,
                "vm": vm,
                "du": du,
                "boot": boot,
                "cpu_temp": cpu_temp,
            }

            self._stats_cache = {"ts": now, "value": value}
            return value
        except Exception as e:
            logger.warning(f"_get_stats psutil gather error: {e}")
            return None

    def _format_uptime(self, start: typing.Optional[datetime.datetime]) -> str:
        if not start:
            return "N/A"
        delta = datetime.datetime.utcnow() - start
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d, {hours}h, {minutes}m, {seconds}s"

    @discord.app_commands.command(name="guildinfo")
    async def guildinfo(self, i: discord.Interaction) -> None:
        """Show information about the guild the command was used in."""
        guild = i.guild
        if not guild:
            await i.response.send_message("This command must be used in a server.", ephemeral=True)
            return

        embed = discord.Embed(title=guild.name, color=discord.Color.pink())
        embed.add_field(name="Created", value=guild.created_at.strftime('%m/%d/%Y'), inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await i.response.send_message(embed=embed)

    @discord.app_commands.command(name="userinfo")
    @discord.app_commands.describe(user="The user to display information about; defaults to you.")
    async def userinfo(self, i: discord.Interaction, user: typing.Optional[discord.Member] = None) -> None:
        """Show information about a user (defaults to caller)."""
        target = user or i.user
        embed = discord.Embed(title=f"{target.display_name} ({target})", color=discord.Color.pink())
        joined = getattr(target, 'joined_at', None)
        embed.add_field(name="Guild join date", value=(joined.strftime('%m/%d/%Y') if joined else 'N/A'))
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)
        await i.response.send_message(embed=embed)
