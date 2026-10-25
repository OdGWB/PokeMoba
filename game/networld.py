"""Mondo ricostruito dagli snapshot, con interpolazione (lato client).

Riusa le classi entità del motore (Pokemon/Minion/Structure/Core) così il
renderer, la minimappa, gli effetti e gli animatori funzionano identici alla
modalità locale. Le posizioni vengono interpolate tra gli ultimi due snapshot,
con un piccolo ritardo di rendering, per un movimento fluido.
"""
from __future__ import annotations

import config
from engine.entities import Core, Minion, Pokemon, Structure
from engine.vec import Vec2
from net.protocol import K_CORE, K_MINION, K_POKEMON, K_TOWER

_MINION_TYPES = {0: "melee", 1: "caster", 2: "cannon"}
INTERP_DELAY = 0.06   # s: si renderizza leggermente nel passato per interpolare


class NetWorld:
    def __init__(self, grid):
        self.grid = grid
        self.entities: dict = {}
        self._prev: dict = {}
        self._next: dict = {}
        self._prev_t = None
        self._next_t = None
        self.core_hp = {0: 0.0, 1: 0.0}
        self.winner = None
        self.match_time = 0.0
        self.hud = None
        self._last_seq = -1

    # --- aggiornamento da snapshot ------------------------------------------
    def push(self, snap, local_time):
        if snap["seq"] <= self._last_seq:
            return  # snapshot vecchio/fuori ordine
        self._last_seq = snap["seq"]
        self._prev, self._prev_t = self._next, self._next_t
        self._next = {e["id"]: (e["x"], e["y"]) for e in snap["entities"]}
        self._next_t = local_time

        seen = set()
        for e in snap["entities"]:
            seen.add(e["id"])
            obj = self._ensure(e)
            obj.team = e["team"]
            obj.radius = e["radius"]
            obj.hp = e["hp"]
            obj.max_hp = max(1.0, e["max_hp"])
            obj.facing = e["facing"]
            obj.moving = e["moving"]
            obj.alive = e["alive"]
            obj.color = config.TEAM_COLORS.get(e["team"], (200, 200, 200))
            if isinstance(obj, Core):
                self.core_hp[e["team"]] = e["hp"]
        for eid in list(self.entities):
            if eid not in seen:
                del self.entities[eid]

        self.match_time = snap["time"]
        self.winner = None if snap["winner"] < 0 else snap["winner"]
        self.hud = snap

    def _ensure(self, e):
        obj = self.entities.get(e["id"])
        kind = e["kind"]
        want = {K_POKEMON: Pokemon, K_MINION: Minion, K_TOWER: Structure, K_CORE: Core}[kind]
        if obj is not None and type(obj) is want:
            return obj
        pos = Vec2(e["x"], e["y"])
        if kind == K_POKEMON:
            obj = Pokemon(id=e["id"], pos=pos, dex=e["extra"])
        elif kind == K_MINION:
            obj = Minion(id=e["id"], pos=pos, minion_type=_MINION_TYPES.get(e["extra"], "melee"))
        elif kind == K_TOWER:
            obj = Structure(id=e["id"], pos=pos, kind="tower", tier=e["extra"])
        else:
            obj = Core(id=e["id"], pos=pos, kind="core")
        self.entities[e["id"]] = obj
        return obj

    def interpolate(self, local_time):
        render_t = local_time - INTERP_DELAY
        dur = (self._next_t - self._prev_t) if (self._prev_t is not None and self._next_t is not None) else 0.0
        for eid, obj in self.entities.items():
            np = self._next.get(eid)
            if np is None:
                continue
            pp = self._prev.get(eid)
            if pp is None or dur <= 1e-6:
                obj.pos = Vec2(np[0], np[1])
            else:
                a = (render_t - self._prev_t) / dur
                a = 0.0 if a < 0 else (1.0 if a > 1 else a)
                obj.pos = Vec2(pp[0] + (np[0] - pp[0]) * a, pp[1] + (np[1] - pp[1]) * a)

    # --- accessori stile World (per renderer / minimappa / visione) ----------
    def get(self, eid):
        return self.entities.get(eid)

    def units(self):
        return [e for e in self.entities.values() if isinstance(e, (Pokemon, Minion))]

    def alive_units(self):
        return [e for e in self.entities.values() if isinstance(e, (Pokemon, Minion)) and e.alive]

    def pokemons(self):
        return [e for e in self.entities.values() if isinstance(e, Pokemon)]

    def minions(self):
        return [e for e in self.entities.values() if isinstance(e, Minion)]

    def structures(self):
        return [e for e in self.entities.values() if isinstance(e, Structure)]

    def cores(self):
        return [e for e in self.entities.values() if isinstance(e, Core)]

    def combatants(self):
        return [e for e in self.entities.values()
                if isinstance(e, (Pokemon, Minion, Structure)) and getattr(e, "alive", True)]
