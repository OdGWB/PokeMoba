"""Regole di assegnazione dei punti mossa (gradi), stile LoL.

- 1 punto mossa per livello (15 al livello 15).
- Q/W/E: 4 gradi. R: 3 gradi, assegnabili solo ai livelli 8, 11, 14.
- Una mossa base (Q/W/E) non può superare il grado = ceil(livello / 2).
- La R va prima sbloccata (evoluzione finale, livello 8).

Puro: nessun pygame. Opera su un Pokemon (entities.Pokemon) e il suo moveset.
"""
from __future__ import annotations

import math

# Livelli minimi per assegnare il 1°, 2°, 3° grado della R.
R_RANK_LEVELS = [8, 11, 14]


def available_points(p) -> int:
    """Punti mossa non ancora spesi (1 per livello)."""
    return max(0, p.level - p.skill_points_spent)


def _base_rank_cap(level: int) -> int:
    return math.ceil(level / 2)


def can_rank_up(p, slot: str) -> bool:
    ms = p.moveset.get(slot)
    if ms is None or available_points(p) <= 0:
        return False
    if not ms.unlocked:
        return False
    if ms.rank >= ms.max_rank:
        return False
    new_rank = ms.rank + 1
    if slot == "R":
        # Solo ai livelli 8/11/14 e nell'ordine.
        return p.level >= R_RANK_LEVELS[new_rank - 1]
    return new_rank <= _base_rank_cap(p.level)


def rank_up(p, slot: str) -> bool:
    """Assegna un punto alla mossa `slot`, se consentito. Ritorna True se fatto."""
    if not can_rank_up(p, slot):
        return False
    ms = p.moveset[slot]
    ms.rank += 1
    p.skill_points_spent += 1
    _apply_passive(p)
    return True


def _apply_passive(p) -> None:
    """Ricalcola i bonus passivi permanenti delle mosse di potenziamento."""
    bonus: dict[str, float] = {}
    for ms in p.moveset.values():
        mv = ms.chosen
        if mv is None or ms.rank <= 0:
            continue
        pas = mv.passive
        if pas:
            stat = pas.get("stat")
            amounts = pas.get("amount", [])
            if stat and amounts:
                idx = min(ms.rank, len(amounts)) - 1
                bonus[stat] = bonus.get(stat, 0.0) + float(amounts[idx])
    p.passive_bonus = bonus
