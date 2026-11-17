"""Caricamento dei contenuti data-driven (mappe, Pokémon) dai file JSON.

Puro: nessun pygame. La mappa diventa una Grid; le definizioni Pokémon restano
dizionari/dataclass che il client userà per creare le entità e scegliere lo
sprite.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .grid import Grid


@dataclass
class MapData:
    name: str
    grid: Grid
    spawns: dict[str, tuple[int, int]]
    lanes: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    structures: list[dict] = field(default_factory=list)
    dens: dict[str, tuple[float, float]] = field(default_factory=dict)
    teams: dict[int, dict] = field(default_factory=dict)
    puddles: list = field(default_factory=list)   # punti pozza (vecchio reticolo; ripiego)
    puddle_spots: list = field(default_factory=list)   # dischi pozza grandi: {"pos":[x,y], "r":int}
    wind_passages: list = field(default_factory=list)  # varchi del Vento: {"pos":[x,y], "r":int}
    camps: list = field(default_factory=list)     # campi neutrali: {"pos":[x,y], "type": "big"|"small"}
    team_size: int = 3                            # giocatori per squadra (3v3 o 5v5)

    @property
    def is_moba_map(self) -> bool:
        """True se la mappa ha le strutture di una partita (lane, torri, nucleo)."""
        return bool(self.structures)


def load_map(path: str | Path) -> MapData:
    """Carica una mappa da JSON.

    Supporta due formati di griglia:
      - "rows" + "legend": griglia ASCII (facile da editare a mano)
      - "tiles": matrice di interi già pronta
    e i metadati opzionali di una mappa MOBA: lanes, structures, dens, teams.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "rows" in data:
        legend = data.get("legend", {".": 0, "#": 1})
        rows = [[legend[ch] for ch in row] for row in data["rows"]]
    elif "tiles" in data:
        rows = data["tiles"]
    else:
        raise ValueError("Mappa senza 'rows' né 'tiles'")

    grid = Grid.from_rows(rows)
    spawns = {k: tuple(v) for k, v in data.get("spawns", {}).items()}
    lanes = {k: [tuple(p) for p in v] for k, v in data.get("lanes", {}).items()}
    dens = {k: tuple(v) for k, v in data.get("dens", {}).items()}
    teams = {int(k): v for k, v in data.get("teams", {}).items()}
    if data.get("structures") or data.get("camps"):
        # Collisione dei muri sulla sagoma disegnata (mappe di partita). Zone
        # sempre libere anche se la sagoma ci sporge: campi, tane, strutture, basi.
        keep = [(c["pos"][0] + 0.5, c["pos"][1] + 0.5, 1.0) for c in data.get("camps", [])]
        keep += [(p[0] + 0.5, p[1] + 0.5, 1.5) for p in dens.values()]
        keep += [(s["pos"][0], s["pos"][1], 1.2) for s in data.get("structures", [])]
        keep += [(p[0] + 0.5, p[1] + 0.5, 2.5) for p in spawns.values()]
        grid.enable_wall_shape(keep)
    return MapData(name=data.get("name", "senza nome"), grid=grid, spawns=spawns,
                   lanes=lanes, structures=list(data.get("structures", [])),
                   dens=dens, teams=teams,
                   puddles=[tuple(p) for p in data.get("puddles", [])],
                   puddle_spots=list(data.get("puddle_spots", [])),
                   wind_passages=list(data.get("wind_passages", [])),
                   camps=list(data.get("camps", [])),
                   team_size=int(data.get("team_size", 3)))


@dataclass
class PokemonDef:
    dex: int
    name: str
    types: list[str] = field(default_factory=list)
    role: str = ""
    color: tuple[int, int, int] = (230, 120, 60)
    radius: float = 0.35
    base_speed: float = 3.6
    attack_range: float = 1.6
    attack_cooldown: float = 0.8
    attack_fx: str = ""
    sprite_dir: str | None = None
    base_stats: dict = field(default_factory=dict)
    growth: dict = field(default_factory=dict)
    moves: dict = field(default_factory=dict)
    evolutions: list = field(default_factory=list)
    passive: str = ""
    recommended_items: list = field(default_factory=list)   # consigliati nel negozio (e per i bot)


def load_pokemon_def(path: str | Path) -> PokemonDef:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PokemonDef(
        dex=int(data["dex"]),
        name=data.get("name", "Pokemon"),
        types=list(data.get("types", [])),
        role=data.get("role", ""),
        color=tuple(data.get("color", (230, 120, 60))),
        radius=float(data.get("radius", 0.35)),
        base_speed=float(data.get("base_speed", 3.6)),
        attack_range=float(data.get("attack_range", 1.6)),
        attack_cooldown=float(data.get("attack_cooldown", 0.8)),
        attack_fx=data.get("attack_fx", ""),
        sprite_dir=data.get("sprite_dir"),
        base_stats=dict(data.get("base_stats", {})),
        growth=dict(data.get("growth", {})),
        moves=dict(data.get("moves", {})),
        evolutions=list(data.get("evolutions", [])),
        passive=(data["passive"].get("id", "") if isinstance(data.get("passive"), dict)
                 else data.get("passive", "")),
        recommended_items=list(data.get("recommended_items", [])),
    )
