"""At yarisi simulasyonu — ciftlik atlari + NPC rakipler."""
from __future__ import annotations

import random
from typing import Sequence

from stable import Racer

TRACK = 100


def _bar(progress: int, width: int = 14) -> str:
    progress = max(0, min(TRACK, progress))
    filled = int(width * progress / TRACK)
    return "█" * filled + "░" * (width - filled)


def race_embed(
    racers: Sequence[Racer],
    positions: dict[str, int],
    *,
    title: str = "🏁 At Yarisi",
    footer: str | None = None,
    color: int = 0xE67E22,
):
    import discord

    by_key = {r.key: r for r in racers}
    ranked = sorted(positions.items(), key=lambda x: x[1], reverse=True)
    lines = []
    for key, pos in ranked:
        r = by_key[key]
        mark = " 👈" if r.is_player else ""
        lines.append(f"{r.emoji} **{r.name}** `{_bar(pos)}` {pos}%{mark}")
    emb = discord.Embed(title=title, description="\n".join(lines), color=color)
    if footer:
        emb.set_footer(text=footer)
    return emb


def init_positions(racers: Sequence[Racer]) -> dict[str, int]:
    return {r.key: 0 for r in racers}


def tick(positions: dict[str, int], racers: Sequence[Racer]) -> None:
    by_key = {r.key: r for r in racers}
    for key in positions:
        r = by_key[key]
        gain = (
            random.randint(3, 9)
            + r.speed // 14
            + random.randint(0, r.luck // 18)
            + (r.stamina // 25 if random.random() > 0.5 else 0)
        )
        positions[key] = min(TRACK, positions[key] + gain)


def winner(positions: dict[str, int], racers: Sequence[Racer]) -> Racer:
    best_key = max(positions, key=lambda k: positions[k])
    return next(r for r in racers if r.key == best_key)


def payout(bet: int, racer: Racer, won: bool) -> int:
    if not won:
        return 0
    return int(bet * racer.odds)
