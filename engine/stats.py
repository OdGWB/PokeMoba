"""Statistiche, livelli, esperienza e formula del danno.

Puro: nessun pygame. Le statistiche sono data-driven (base + crescita per livello
nel JSON del Pokémon). Il danno usa Attacco vs Difesa (fisico) o Att.Sp vs
Dif.Sp (speciale), con efficacia dei tipi e STAB (+50%).
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_LEVEL = 15
STAB_MULT = 1.5

# Statistiche considerate.
STAT_NAMES = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]


@dataclass
class Stats:
    hp: float = 100.0
    attack: float = 10.0
    defense: float = 10.0
    sp_attack: float = 10.0
    sp_defense: float = 10.0
    speed: float = 10.0

    @classmethod
    def from_dict(cls, d: dict) -> "Stats":
        return cls(**{k: float(d.get(k, 0.0)) for k in STAT_NAMES})


def stats_at_level(base: Stats, growth: Stats, level: int) -> Stats:
    """Statistiche a un dato livello: base + crescita * (livello - 1)."""
    level = max(1, min(MAX_LEVEL, level))
    f = level - 1
    return Stats(**{k: getattr(base, k) + getattr(growth, k) * f for k in STAT_NAMES})


# --- Esperienza e livelli ----------------------------------------------------
def _cumulative_xp() -> list[float]:
    """XP totale necessario per raggiungere ogni livello (indice = livello)."""
    cum = [0.0, 0.0]  # livelli 0 e 1 a 0 XP
    total = 0.0
    for lvl in range(1, MAX_LEVEL):
        # Curva pensata per partite da ~15-25 min: il livello 15 si raggiunge
        # verso i 12-15 minuti di gioco attivo.
        need = 160.0 + 80.0 * (lvl - 1)  # XP da lvl a lvl+1
        total += need
        cum.append(total)
    return cum


CUMULATIVE_XP = _cumulative_xp()


def level_from_xp(xp: float) -> int:
    lvl = 1
    for L in range(1, MAX_LEVEL + 1):
        if xp >= CUMULATIVE_XP[L]:
            lvl = L
        else:
            break
    return lvl


def respawn_time(level: int) -> float:
    """Tempo di respawn crescente col livello (stile LoL/Wild Rift).

    A fine partita i respawn lunghi creano la finestra "squadra spazzata ->
    push libero" che permette di chiudere la partita (altrimenti stallo).
    Lv1 ~8s, lv15 ~41s.
    """
    return 6.0 + level * 2.3


# --- Danno -------------------------------------------------------------------
def damage(power: float, defense: float, effectiveness: float = 1.0,
           stab: float = 1.0) -> float:
    """Danno mitigato dalla difesa (formula ad armatura) con efficacia e STAB.

    power: potenza effettiva dell'attacco (per un attacco base = statistica
    d'attacco; per una mossa = potenza base per grado + eventuali rapporti).
    """
    mitigated = power * (100.0 / (100.0 + max(0.0, defense)))
    return max(1.0, mitigated * effectiveness * stab)
