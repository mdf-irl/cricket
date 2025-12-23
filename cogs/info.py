from __future__ import annotations

import asyncio
import datetime
import os
import platform
import time
import typing
from pathlib import Path
from zoneinfo import ZoneInfo

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
    _platform_system = platform.system()
    _is_linux = _platform_system.lower() == "linux"
    _platform_machine = platform.machine()
    _python_version = platform.python_version()
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
    async def avatar(self, interaction: discord.Interaction, user: typing.Optional[discord.Member] = None) -> None:
        """Show the full-size avatar for a user (defaults to caller)."""
        target = user or interaction.user
        embed = discord.Embed(title=f"{target.display_name}'s Full-Sized Avatar", color=discord.Color.pink())
        embed.set_image(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="botinfo")
    async def botinfo(self, interaction: discord.Interaction) -> None:
        """Show information about the bot and host system."""
        await interaction.response.defer()

        stats = await self._get_stats()
        
        # Build CPU info
        cpu = "N/A"
        if stats:
            cpu_percent = stats.get("cpu_percent", 0.0)
            cpu_count = stats.get("cpu_count", 0)
            freq_cur = stats.get("freq", "N/A")
            cpu_temp_c = stats.get("cpu_temp", "N/A")
            cpu = f"**Usage**: {cpu_percent:.2f}%\n**Cores**: {cpu_count} @ {freq_cur}\n**Temp**: {cpu_temp_c}"
        
        # Build memory info
        mem = "N/A"
        if stats and (vm := stats.get("vm")):
            pct = getattr(vm, "percent", None)
            pct_display = f" ({pct:.0f}%)" if pct is not None else ""
            mem = f"**Used**: {self._format_bytes(vm.used)}\n**Total**: {self._format_bytes(vm.total)}{pct_display}"
        
        # Build disk info
        disk = "N/A"
        if stats and (du := stats.get("du")):
            pct = getattr(du, "percent", None)
            pct_display = f" ({pct:.0f}%)" if pct is not None else ""
            disk = f"**Used**: {self._format_bytes(du.used)}\n**Total**: {self._format_bytes(du.total)}{pct_display}"

        # Uptime calculations
        bot_uptime = self._format_uptime(self.connected_time)
        system_uptime = "N/A"
        if stats and (boot := stats.get("boot")):
            booted_time = datetime.datetime.fromtimestamp(boot)
            system_uptime = self._format_uptime(booted_time)

        # Build main info embed
        embed = discord.Embed(
            title="🦗 Cricket v420.69",
            color=discord.Color.pink(),
            description=(
                f"**Latency**: {round(self.bot.latency * 1000)}ms\n"
                f"**Uptime**: {bot_uptime} (**bot**) / {system_uptime} (**system**)"
            ),
        )

        embed.add_field(name="💾 CPU", value=cpu, inline=True)
        embed.add_field(name="🧠 Memory", value=mem, inline=True)
        embed.add_field(name="💿 Disk", value=disk, inline=True)
        embed.set_footer(text=f"🔋 Powered by discord.py {discord.__version__} w/ Python {self._python_version} on {self._platform_system} ({self._platform_machine})")

        await interaction.followup.send(embed=embed, ephemeral=True)

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

            cpu_percent, cpu_count_physical, cpu_count_logical, freq, vm, du, boot = await asyncio.gather(*tasks)

            cpu_count = cpu_count_physical or cpu_count_logical or 0
            freq_cur = f"{freq.current / 1000:.2f} GHz" if freq else "N/A"

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
    async def guildinfo(self, interaction: discord.Interaction) -> None:
        """Show information about the guild the command was used in."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            return

        # Owner lookup with fallback chain
        owner_display = "Unknown"
        if guild.owner:
            owner_display = guild.owner.mention
        elif guild.owner_id:
            try:
                owner_user = await self.bot.fetch_user(guild.owner_id)
                owner_display = owner_user.mention
            except Exception:
                owner_display = f"<@{guild.owner_id}>"

        # Boosts / premium info
        boost_count = guild.premium_subscription_count or 0
        tier_display = getattr(guild.premium_tier, "name", str(guild.premium_tier)) if guild.premium_tier else "None"

        embed = discord.Embed(title=guild.name, color=discord.Color.pink())
        embed.add_field(name="Owner", value=owner_display, inline=True)
        embed.add_field(name="Boosts", value=f"{boost_count} (Tier: {tier_display})", inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created", value=guild.created_at.strftime('%m/%d/%Y'), inline=True)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="userinfo")
    @discord.app_commands.describe(user="The user to display information about; defaults to you.")
    async def userinfo(self, interaction: discord.Interaction, user: typing.Optional[discord.User] = None) -> None:
        """Show information about a user (defaults to caller)."""
        target = user or interaction.user

        # Determine if we have a Member (guild-scoped) or only a User
        # Try to get the freshest member data from the guild
        member: typing.Optional[discord.Member] = None
        if interaction.guild:
            try:
                # Fetch member to get fresh presence data
                member = await interaction.guild.fetch_member(target.id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                # Fall back to cached member
                member = interaction.guild.get_member(target.id)
        
        if not member and isinstance(target, discord.Member):
            member = target

        embed = discord.Embed(title=f"{target.display_name} ({target})", color=discord.Color.pink())

        # Thumbnail / avatar
        try:
            if target.display_avatar:
                embed.set_thumbnail(url=target.display_avatar.url)
        except Exception:
            pass

        # Basic fields
        embed.add_field(name="Mention", value=target.mention, inline=True)
        embed.add_field(name="ID", value=str(target.id), inline=True)
        embed.add_field(name="Bot", value="Yes" if target.bot else "No", inline=True)
        embed.add_field(name="Created", value=target.created_at.strftime('%m/%d/%Y'), inline=True)

        # Guild-specific info
        if member:
            embed.add_field(name="Nickname", value=member.nick or "-", inline=True)

            # Roles (exclude @everyone)
            roles = [r for r in member.roles if r.name != "@everyone"]
            top_role = member.top_role.name if member.top_role and member.top_role.name != "@everyone" else "-"
            roles_display = ", ".join(r.mention for r in roles[-5:]) if roles else "-"
            embed.add_field(name="Top Role", value=top_role, inline=True)
            embed.add_field(name="Roles", value=f"{len(roles)} ({roles_display})", inline=True)

            embed.add_field(name="Guild Join", value=member.joined_at.strftime('%m/%d/%Y') if member.joined_at else 'N/A', inline=True)

            if member.activities:
                act_list = [getattr(a, 'name', str(a)) for a in member.activities[:3]]
                if act_list:
                    embed.add_field(name="Activities", value="; ".join(act_list), inline=False)
        else:
            # Non-guild user: only global info available
            embed.add_field(name="Nickname", value="-", inline=True)
            embed.add_field(name="Top Role", value="-", inline=True)
            embed.add_field(name="Roles", value="-", inline=True)
            embed.add_field(name="Guild Join", value="-", inline=True)

        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="cogversions")
    async def cogversions(self, interaction: discord.Interaction) -> None:
        """Show the last modification time of all loaded cogs."""
        await interaction.response.defer()

        cogs_dir = Path("./cogs")
        cog_info = []

        # Get modification times for all .py files in cogs directory
        for cog_file in sorted(cogs_dir.glob("*.py")):
            if cog_file.stem.startswith("_"):
                continue

            try:
                mod_time = os.path.getmtime(cog_file)
                # Convert to EST/EDT timezone
                mod_dt = datetime.datetime.fromtimestamp(mod_time, tz=ZoneInfo("America/New_York"))
                formatted_time = mod_dt.strftime('%m/%d/%Y %I:%M %p %Z')
                cog_info.append((cog_file.stem, formatted_time))
            except OSError as e:
                logger.warning(f"Could not get mtime for {cog_file}: {e}")
                cog_info.append((cog_file.stem, "N/A"))

        # Build embed
        embed = discord.Embed(
            title="🔧 Cog Versions",
            description="Last modification times of all loaded cogs",
            color=discord.Color.blurple()
        )

        if cog_info:
            cog_text = "\n".join(f"`{name}`: {time_str}" for name, time_str in cog_info)
            embed.add_field(name="Cogs", value=cog_text, inline=False)
        else:
            embed.add_field(name="Cogs", value="No cogs found", inline=False)

        embed.set_footer(text="🔋 Times shown in EST/EDT")
        await interaction.followup.send(embed=embed)
