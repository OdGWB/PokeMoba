"""Controllo del motore della versione ufficiale: Python + Rust (native/).

Dal codice sorgente il Rust resta facoltativo (sviluppo e confronto di parita'
col Python puro). L'exe pubblicato invece DEVE averlo: senza non parte, e la
Release si ferma, invece di girare piu' lento senza che nessuno se ne accorga.
"""
from __future__ import annotations

from . import grid

# Tutto cio' che il gioco usa dell'estensione: una build vecchia non basta.
REQUIRED = ("GridView", "WalkGrid", "SpatialHash", "VisionScan", "MinionAI",
            "BotHelpers", "obstacle_hits", "GridView.step_collide_units")


def native_problem() -> str | None:
    """None se il motore Rust e' caricato e completo, altrimenti cosa non va."""
    native = grid._native
    if native is None:
        return "il motore Rust (pokemoba_native) non e' caricato"
    missing = []
    for name in REQUIRED:
        obj = native
        for part in name.split("."):
            obj = getattr(obj, part, None)
        if obj is None:
            missing.append(name)
    if missing:
        return "il motore Rust e' di una versione vecchia, manca: " + ", ".join(missing)
    return None
