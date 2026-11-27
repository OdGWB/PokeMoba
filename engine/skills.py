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
    """Punti mossa che il giocatore può spendere (1 per livello).

    Il punto del liv.8 è della ultimate: finché la R non ha il 1° grado resta
    da parte, e lo spende evolution.apply_choice quando la sblocca."""
    r = p.moveset.get("R")
    reserved = 1 if p.level >= R_RANK_LEVELS[0] and (r is None or r.rank <= 0) else 0
    return max(0, p.level - p.skill_points_spent - reserved)


def _base_rank_cap(level: int) -> int:
    return math.ceil(level / 2)


def rank_allowed(slot: str, rank: int, max_rank: int, level: int) -> bool:
    """Il livello consente un grado in più? (Punti e sblocco si controllano a
    parte: la usa anche l'HUD online, che ha solo i numeri dello snapshot.)"""
    if rank >= max_rank:
        return False
    if slot == "R":
        # Solo ai livelli 8/11/14 e nell'ordine.
        return level >= R_RANK_LEVELS[rank]
    return rank + 1 <= _base_rank_cap(level)


def can_rank_up(p, slot: str) -> bool:
    ms = p.moveset.get(slot)
    if ms is None or available_points(p) <= 0:
        return False
    if not ms.unlocked:
        return False
    return rank_allowed(slot, ms.rank, ms.max_rank, p.level)


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
