"""Modello dati delle mosse (data-driven) e del set di mosse di un Pokémon.

Puro: nessun pygame. La mossa è descritta nel JSON del Pokémon; qui la si
avvolge con accessori comodi. L'ESECUZIONE (danno, forme, effetti) sta in
engine/match.py; qui ci sono solo i dati e lo stato (grado, ricarica).

Schema di una mossa (variante base o potenziamento):
    {
      "id": "ember", "name": "Braciere", "type": "Fire",
      "category": "special",          # physical | special | none
      "shape": "projectile",          # projectile | cone | area | dash | buff
      "target": "direction",          # direction | point | self | ally
      "power": [70,110,150,190],      # danno base per grado (1..max_rank)
      "ratio": 0.5,                    # + frazione della stat offensiva del lanciatore
      "cooldown": [5,4.5,4,3.5],       # ricarica per grado
      "range": 7, "radius": 0.5, "speed": 11, "angle": 45,
      "wall_pierce": false,
      "effects": { "slow": {"mult":0.6,"duration":1.5}, "heal":[...],
                   "shield": {"amount":[...],"duration":3},
                   "atk": {"mult":1.4,"duration":5}, "speed": {"mult":1.3,"duration":3} },
      "passive": { "stat":"attack", "amount":[6,12,18,24] }   # mosse di potenziamento
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field

Q_W_E_RANKS = 4
R_RANKS = 3


def _at(arr, rank: int, default=0.0):
    """Valore di un array per grado (1-based), con clamp."""
    if not arr:
        return default
    i = max(1, rank) - 1
    return arr[min(i, len(arr) - 1)]


@dataclass
class Move:
    slot: str
    max_rank: int
    d: dict = field(default_factory=dict)

    @property
    def id(self) -> str: return self.d.get("id", "")
    @property
    def name(self) -> str: return self.d.get("name", "?")
    @property
    def type(self) -> str: return self.d.get("type", "Normal")
    @property
    def category(self) -> str: return self.d.get("category", "physical")
    @property
    def shape(self) -> str: return self.d.get("shape", "projectile")
    @property
    def fx(self) -> str: return self.d.get("fx", "")   # stile effetto visivo (vedi game/fx.py)
    @property
    def target(self) -> str: return self.d.get("target", "direction")
    @property
    def ratio(self) -> float: return float(self.d.get("ratio", 0.0))
    @property
    def range(self) -> float: return float(self.d.get("range", 5.0))
    @property
    def radius(self) -> float: return float(self.d.get("radius", 1.0))
    @property
    def speed(self) -> float: return float(self.d.get("speed", 10.0))
    @property
    def angle(self) -> float: return float(self.d.get("angle", 45.0))
    @property
    def wall_pierce(self) -> bool: return bool(self.d.get("wall_pierce", False))
    @property
    def charges(self) -> int: return int(self.d.get("charges", 0))         # >0 = mossa a cariche
    @property
    def charge_time(self) -> float: return float(self.d.get("charge_time", 0.0))  # s per ricaricare 1
    @property
    def refund_on_hit(self) -> bool: return bool(self.d.get("refund_on_hit", False))
    @property
    def effects(self) -> dict: return self.d.get("effects", {})
    @property
    def passive(self) -> dict | None: return self.d.get("passive")

    def power_at(self, rank: int) -> float:
        return float(_at(self.d.get("power"), rank, 0.0))

    def cooldown_at(self, rank: int) -> float:
        return float(_at(self.d.get("cooldown"), rank, 5.0))


@dataclass
class MoveSlot:
    slot: str                       # "Q" | "W" | "E" | "R"
    base: Move | None               # None per la R (si sblocca scegliendo l'ultimate)
    upgrades: list                  # lista di Move (potenziamenti / ultimate)
    chosen: Move | None             # variante attiva corrente
    max_rank: int
    rank: int = 0                   # 0 = non ancora sbloccata (nessun punto speso)
    cooldown_remaining: float = 0.0
    unlocked: bool = True           # la R parte False finché non si evolve del tutto
    charges_cur: float = -1.0       # mosse a cariche (Erboscivolata); -1 = da inizializzare

    @property
    def ready(self) -> bool:
        if not (self.unlocked and self.rank > 0):
            return False
        if self.cooldown_remaining > 0.0:   # piccola pausa tra una carica e l'altra
            return False
        mv = self.chosen
        if mv is not None and mv.charges > 0:
            # -1 = non ancora inizializzata: la si considera piena (pronta).
            return self.charges_cur >= 1.0 or self.charges_cur < 0.0
        return True


def _parse_move(d: dict, slot: str, max_rank: int) -> Move:
    return Move(slot=slot, max_rank=max_rank, d=dict(d))


def build_moveset(moves_json: dict) -> dict:
    """Costruisce il set di mosse {slot: MoveSlot} dal JSON del Pokémon."""
    out = {}
    for slot in ("Q", "W", "E", "R"):
        spec = moves_json.get(slot)
        if not spec:
            continue
        max_rank = R_RANKS if slot == "R" else Q_W_E_RANKS
        base = _parse_move(spec["base"], slot, max_rank) if spec.get("base") else None
        upgrades = [_parse_move(u, slot, max_rank) for u in spec.get("upgrades", [])]
        chosen = base if base is not None else None
        out[slot] = MoveSlot(slot=slot, base=base, upgrades=upgrades, chosen=chosen,
                             max_rank=max_rank, unlocked=(slot != "R"))
        # "start_rank": la mossa parte già imparata (grado gratuito, senza punti):
        # Cambio Munizioni della linea Remoraid si usa dal livello 1.
        if base is not None and base.d.get("start_rank"):
            out[slot].rank = int(base.d["start_rank"])
    return out
