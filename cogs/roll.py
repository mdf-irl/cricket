import ast
import operator
import random
import re
from typing import List, Tuple

import discord
from discord.ext import commands
from discord import app_commands, ui

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
        self.embed_base = embed_base
        self.breakdown_text = breakdown_text
        self.user_id = user_id
        self.breakdown_visible = False

    def _get_embed(self) -> discord.Embed:
        """Get current embed with or without breakdown."""
        embed = self.embed_base.copy()
        if self.breakdown_visible and self.breakdown_text:
            embed.add_field(name="Roll Breakdown", value=self.breakdown_text, inline=False)
        return embed

    @ui.button(label="Hide Breakdown", style=discord.ButtonStyle.secondary, emoji="📖", disabled=True)
    async def hide_button(self, interaction: discord.Interaction, button: ui.Button):
        """Hide the roll breakdown."""
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.breakdown_visible = False
        button.disabled = True
        self.show_button.disabled = False
        await interaction.response.edit_message(embed=self._get_embed(), view=self)

    @ui.button(label="Show Breakdown", style=discord.ButtonStyle.secondary, emoji="📋")
    async def show_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show the roll breakdown."""
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return

        self.breakdown_visible = True
        button.disabled = True
        self.hide_button.disabled = False
        await interaction.response.edit_message(embed=self._get_embed(), view=self)


class DiceRoller(commands.Cog):
    """Dice roller cog with robust interaction handling and KeepAlive."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
            MAX_REROLLS = 50
            new_rolls = []
            for r in rolls:
                if r <= reroll_threshold:
                    for _ in range(MAX_REROLLS):
                        r = random.randint(1, dice_sides)
                        if r > reroll_threshold:
                            break
                new_rolls.append(r)
            rolls = new_rolls
            history.append(f"Rerolls (<= {reroll_threshold}): {', '.join(map(str, rolls))}")

        # Keep/Drop logic
        kept = rolls
        if keep_drop_op and keep_drop_val is not None:
            sorted_rolls = sorted(rolls)
            if keep_drop_op.lower() == "kh":
                kept = sorted_rolls[-keep_drop_val:]
                dropped = sorted_rolls[:-keep_drop_val]
            else:  # kl
                kept = sorted_rolls[:keep_drop_val]
                dropped = sorted_rolls[keep_drop_val:]
            history.append(f"Kept Rolls ({keep_drop_op}{keep_drop_val}): {', '.join(map(str, kept))}")
            if dropped:
                history.append(f"Dropped Rolls: {', '.join(map(str, dropped))}")

        total = sum(kept)
        breakdown = "\n".join(f"> {line}" for line in history)
        return total, breakdown, kept

    def _safe_eval(self, expr: str) -> int:
        """Safely evaluate a numeric expression (only +, -, *, /, parentheses).

        Returns the floored integer result.
        """
        node = ast.parse(expr, mode="eval")

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
                op_type = type(n.op)
                if op_type not in allowed_ops:
                    raise ValueError(f"Unsupported operator: {op_type}")
                return allowed_ops[op_type](_eval(n.left), _eval(n.right))
            if isinstance(n, ast.UnaryOp):
                op_type = type(n.op)
                if op_type not in allowed_ops:
                    raise ValueError(f"Unsupported unary operator: {op_type}")
                return allowed_ops[op_type](_eval(n.operand))
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
            if hasattr(ast, 'Num') and isinstance(n, ast.Num):
                return n.n
            if isinstance(n, ast.Call):
                raise ValueError("Function calls are not allowed")
            raise ValueError("Invalid expression")

        return int(_eval(node))

    @app_commands.command(
        name="roll",
        description="Roll dice using D&D syntax (e.g., 4d6kh3r1 + d20)."
    )
    @app_commands.describe(roll_string="Full dice expression")
    async def roll_dice(self, interaction: discord.Interaction, roll_string: str):
        """Roll dice and respond with a summary embed.

        Supports expressions combining dice blocks and arithmetic, e.g. `4d6kh3 + d20 + 5`.
        """
        await interaction.response.defer()
        
        cleaned = roll_string.replace(" ", "")
        matches = list(DICE_BLOCK_REGEX.finditer(cleaned))

        try:
            if not matches:
                # Handle simple math expressions like 10+5
                total = self._safe_eval(cleaned)
                await interaction.followup.send(f"**Result:** {total} (Static calculation)")
                return

            # Process each dice block
            substitutions: List[Tuple[int, int, str]] = []
            breakdowns: List[str] = []
            
            for m in matches:
                total_block, breakdown, kept = self._roll_dice_block(m)
                substitutions.append((m.start(), m.end(), f"({total_block})"))
                breakdowns.append(f"**{m.group(0)}** = {total_block}\n{breakdown}")

            # Construct final expression by replacing dice blocks with their totals
            final_expr = cleaned
            for start, end, replacement in reversed(substitutions):
                final_expr = final_expr[:start] + replacement + final_expr[end:]

            final_total = self._safe_eval(final_expr)

            # Build embed with breakdown
            embed = discord.Embed(
                title=f"🎲 Roll: {roll_string}",
                description=f"{interaction.user.mention} rolled a final total of **{final_total}**.",
                color=discord.Color.pink()
            )

            breakdown_text = "\n\n".join(breakdowns)
            if len(breakdown_text) > 1900:
                breakdown_text = breakdown_text[:1900] + "\n…(truncated)"

            # Create view with show/hide buttons
            view = RollView(embed, breakdown_text, interaction.user.id)
            await interaction.followup.send(embed=view._get_embed(), view=view)
            logger.info(f"Roll command executed by {interaction.user} — '{roll_string}' = {final_total}")
            
        except Exception as e:
            logger.exception("Error during roll command")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DiceRoller(bot))
    
