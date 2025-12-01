import discord
from discord.ext import commands
from discord import app_commands, ui
import random
import re
import ast
import operator
from typing import Tuple, List

from logger_config import get_logger

logger = get_logger(__name__)


# Regex for dice expressions like 4d6kh3r1, d20, d%, etc.
DICE_BLOCK_REGEX = re.compile(
    r"(\d*)"                   # Number of dice (optional)
    r"d(100|%|\d+)"            # Dice sides
    r"(?:(kh|kl)(\d+))?"       # Keep/Drop highest/lowest
    r"(?:r(\d+))?",            # Reroll threshold
    re.IGNORECASE
)


class RollView(ui.View):
    """View with buttons to show/hide roll breakdown."""

    def __init__(self, embed_base: discord.Embed, breakdown_text: str, user_id: int):
        super().__init__(timeout=300)
        self.embed_base = embed_base.copy()
        self.breakdown_text = breakdown_text
        self.user_id = user_id
        self.breakdown_visible = False
        # Initialize button states
        self.hide_button.disabled = True
        self.show_button.disabled = False

    def _get_embed(self) -> discord.Embed:
        """Get current embed with or without breakdown."""
        embed = self.embed_base.copy()
        if self.breakdown_visible and self.breakdown_text:
            embed.add_field(name="Roll Breakdown", value=self.breakdown_text, inline=False)
        return embed

    @ui.button(label="Hide Breakdown", style=discord.ButtonStyle.secondary, emoji="📖")
    async def hide_button(self, interaction: discord.Interaction, button: ui.Button):
        """Hide the roll breakdown."""
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.breakdown_visible = False
        self.hide_button.disabled = True
        self.show_button.disabled = False
        embed = self._get_embed()

        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Show Breakdown", style=discord.ButtonStyle.secondary, emoji="📋")
    async def show_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show the roll breakdown."""
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.breakdown_visible = True
        self.hide_button.disabled = False
        self.show_button.disabled = True
        embed = self._get_embed()

        await interaction.response.edit_message(embed=embed, view=self)


class DiceRoller(commands.Cog):
    """Dice roller cog with robust interaction handling and KeepAlive."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Dice rolling logic ---
    def _roll_dice_block(self, match: re.Match) -> Tuple[int, str, List[int]]:
        """Rolls a dice block match and returns (total, breakdown, kept_rolls)."""
        n_dice_str, dice_type, keep_drop_op, keep_drop_val_str, reroll_val_str = match.groups()
        n_dice = int(n_dice_str) if n_dice_str else 1
        dice_sides = 100 if dice_type in ('%', '100') else int(dice_type)
        keep_drop_val = int(keep_drop_val_str) if keep_drop_val_str else None
        reroll_threshold = int(reroll_val_str) if reroll_val_str else None

        # Initial rolls
        rolls = [random.randint(1, dice_sides) for _ in range(n_dice)]
        history = [f"Initial Rolls ({n_dice}d{dice_sides}): {', '.join(map(str, rolls))}"]

        # Reroll logic
        if reroll_threshold is not None:
            new_rolls = []
            for r in rolls:
                count = 0
                MAX_REROLLS = 50
                while r <= reroll_threshold and count < MAX_REROLLS:
                    r = random.randint(1, dice_sides)
                    count += 1
                new_rolls.append(r)
            rolls = new_rolls
            history.append(f"Rerolls (<= {reroll_threshold}): {', '.join(map(str, rolls))}")

        # Keep/Drop logic
        kept = list(rolls)
        if keep_drop_op and keep_drop_val is not None:
            sorted_rolls = sorted(rolls)
            if keep_drop_op.lower() == "kh":
                kept = sorted_rolls[-keep_drop_val:]
                dropped = sorted_rolls[:-keep_drop_val]
            elif keep_drop_op.lower() == "kl":
                kept = sorted_rolls[:keep_drop_val]
                dropped = sorted_rolls[keep_drop_val:]
            history.append(f"Kept Rolls ({keep_drop_op}{keep_drop_val}): {', '.join(map(str, kept))}")
            if dropped:
                history.append(f"Dropped Rolls: {', '.join(map(str, dropped))}")

        total = sum(kept)
        breakdown = "\n".join(f"> {line}" for line in history)
        return total, breakdown, kept

    # --- Safe math evaluation using AST ---
    def _safe_eval(self, expr: str) -> int:
        """Safely evaluate a numeric expression (only +, -, *, /, parentheses).

        Returns the floored integer result.
        """
        # parse
        node = ast.parse(expr, mode="eval")

        # allowed operators mapping
        allowed_ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        def _eval(n):
            if isinstance(n, ast.Expression):
                return _eval(n.body)
            if isinstance(n, ast.BinOp):
                left = _eval(n.left)
                right = _eval(n.right)
                op_type = type(n.op)
                if op_type in allowed_ops:
                    return allowed_ops[op_type](left, right)
                raise ValueError(f"Unsupported operator: {op_type}")
            if isinstance(n, ast.UnaryOp):
                operand = _eval(n.operand)
                op_type = type(n.op)
                if op_type in allowed_ops:
                    return allowed_ops[op_type](operand)
                raise ValueError(f"Unsupported unary operator: {op_type}")
            # Handle both old ast.Num (Python <3.8) and new ast.Constant (Python 3.8+)
            if hasattr(ast, 'Num') and isinstance(n, ast.Num):
                return n.n
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
            if isinstance(n, ast.Call):
                raise ValueError("Function calls are not allowed")
            raise ValueError("Invalid expression")

        result = _eval(node)
        return int(result // 1)

    # --- Slash command ---
    @app_commands.command(
        name="roll",
        description="Roll dice using D&D syntax (e.g., 4d6kh3r1 + d20)."
    )
    @app_commands.describe(roll_string="Full dice expression")
    async def roll_dice(self, interaction: discord.Interaction, roll_string: str):
        """Roll dice and respond with a summary embed.

        Supports expressions combining dice blocks and arithmetic, e.g. `4d6kh3 + d20 + 5`.
        """
        cleaned = roll_string.replace(" ", "")
        substitutions: List[Tuple[int, int, str]] = []
        breakdowns: List[str] = []

        try:
            # Try to defer immediately to buy time for processing
            try:
                await interaction.response.defer()
            except Exception:
                # If deferring fails, we'll try to use followup or channel later
                pass

            matches = list(DICE_BLOCK_REGEX.finditer(cleaned))

            if not matches:
                # Handle simple math expressions like 10+5
                try:
                    total = self._safe_eval(cleaned)
                    await interaction.followup.send(f"**Result:** {total} (Static calculation)")
                    return
                except Exception as e:
                    await interaction.followup.send(f"❌ Invalid expression: {e}")
                    return

            # Process each dice block
            for m in matches:
                total_block, breakdown, kept = self._roll_dice_block(m)
                substitutions.append((m.start(), m.end(), f"({total_block})"))
                breakdowns.append(f"**{m.group(0)}** = {total_block}\n{breakdown}")

            # Construct final expression by replacing dice blocks with their totals
            final_expr = cleaned
            for start, end, replacement in reversed(substitutions):
                final_expr = final_expr[:start] + replacement + final_expr[end:]

            final_total = self._safe_eval(final_expr)

            # Build embed with breakdown (truncate if too long)
            embed = discord.Embed(
                title=f"🎲 Roll: {roll_string}",
                description=f"{interaction.user.mention} rolled a final total of **{final_total}**.",
                color=discord.Color.pink()
            )

            breakdown_text = "\n\n".join(breakdowns)
            if breakdown_text and len(breakdown_text) > 1900:
                breakdown_text = breakdown_text[:1900] + "\n…(truncated)"

            # Create view with show/hide buttons
            view = RollView(embed, breakdown_text, interaction.user.id)

            # Send result
            try:
                await interaction.followup.send(embed=view._get_embed(), view=view)
                logger.info(f"Roll command executed by {interaction.user} — '{roll_string}' = {final_total}")
            except Exception as e:
                logger.error(f"Failed to send roll embed via followup: {type(e).__name__}: {e}")

        except Exception as e:
            logger.exception("Unexpected error during roll command")
            # Try to notify user
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"{interaction.user.mention} ❌ Error: {e}")
                elif interaction.channel:
                    await interaction.channel.send(f"{interaction.user.mention} ❌ Error: {e}")
                else:
                    logger.error("Unable to send error message to user")
            except Exception:
                logger.exception("Failed to report error to user")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DiceRoller(bot))
    
