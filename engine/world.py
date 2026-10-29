"""Stato del mondo e avanzamento del movimento di un tick.

Il World non sa nulla di pygame, rete o rendering: contiene la griglia e le
entità, sa farle muovere e risolvere le collisioni. Le REGOLE di gioco (ondate,
IA, combattimento, vittoria) stanno in engine/match.py, che opera sul World.
"""
from __future__ import annotations

from . import movement
from .entities import Core, Entity, Minion, Pokemon, Structure, Unit, Wild
from .grid import Grid
from .moves import build_moveset
from .spatial import SpatialHash
from .stats import Stats, derive
from .vec import Vec2


class World:
    def __init__(self, grid: Grid):
        self.grid = grid
        self.entities: dict[int, Entity] = {}  # type: ignore[name-defined]
        self._next_id = 1
        self.spatial = SpatialHash(cell_size=2.0)
        # Pilastri di roccia temporanei (entities.Pillar): gestiti dal Match,
        # letti dal renderer. Lista mutata sul posto (mai riassegnata).
        self.pillars: list = []

    # --- gestione entità -----------------------------------------------------
    def _alloc_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def add(self, entity) -> None:
        if entity.id == 0:
            entity.id = self._alloc_id()
        self.entities[entity.id] = entity

    def remove(self, entity_id: int) -> None:
        self.entities.pop(entity_id, None)

    def get(self, entity_id: int):
        return self.entities.get(entity_id)

    # --- spawn ---------------------------------------------------------------
    def spawn_pokemon(self, pos: Vec2, team: int, dex: int, name: str,
                      color: tuple, speed: float, attack_range: float = 1.6,
                      attack_cooldown: float = 0.8, is_bot: bool = False,
                      assigned_lane: str = "mid", types: list | None = None,
                      base_stats: dict | None = None,
                      growth: dict | None = None, moves: dict | None = None,
                      evolutions: list | None = None, role: str = "",
                      passive: str = "", attack_fx: str = "") -> Pokemon:
        # `growth` e `speed`/`attack_cooldown` dei parametri sono ignorati: ora
        # tutto si deriva dalle 6 stat base REALI (vedi engine/stats.derive).
        base = Stats.from_dict(base_stats or {})
        d = derive(base, 1)
        p = Pokemon(pos=pos, team=team, dex=dex, name=name, color=color,
                    speed=d.move_speed_tiles, hp=d.stats.hp, max_hp=d.stats.hp,
                    attack_damage=d.stats.attack, attack_range=attack_range,
                    attack_cooldown=d.attack_cooldown, is_bot=is_bot,
                    assigned_lane=assigned_lane, spawn_pos=pos, vision=9.0,
                    types=list(types or []), level=1, xp=0.0,
                    base_stats=base, stats=d.stats, ranged=d.ranged,
                    attack_speed=d.attack_speed, ability_mult=d.ability_mult,
                    max_mana=d.max_mana, mana=d.max_mana, mana_regen5=d.mana_regen5,
                    tenacity=d.tenacity, hp_regen5=d.hp_regen5,
                    flat_reduction=d.flat_reduction, lethality=d.lethality,
                    lethality_physical=d.lethality_physical, heal_power=d.heal_power,
                    range_cls=d.range_cls, range_val=d.range_val,
                    moveset=build_moveset(moves or {}),
                    evolutions=list(evolutions or []),
                    move_speed_base=d.move_speed_tiles, role=role, passive_id=passive,
                    attack_fx=attack_fx)
        self.add(p)
        return p

    def spawn_minion(self, pos: Vec2, team: int, lane: str, lane_points: list,
                     color: tuple, hp: float = 140.0, attack_damage: float = 14.0,
                     attack_range: float = 1.3, attack_cooldown: float = 1.0,
                     speed: float = 3.1, minion_type: str = "melee",
                     radius: float = 0.28, gold: int = 20, xp: int = 20) -> Minion:
        m = Minion(pos=pos, team=team, lane=lane, minion_type=minion_type,
                   lane_points=list(lane_points), hp=hp, max_hp=hp,
                   attack_damage=attack_damage, attack_range=attack_range,
                   attack_cooldown=attack_cooldown, speed=speed, radius=radius,
                   vision=6.0, gold=gold, xp=xp)
        m.color = color  # type: ignore[attr-defined]
        self.add(m)
        return m

    def spawn_tower(self, pos: Vec2, team: int, lane: str, tier: int,
                    hp: float = 2600.0, attack_damage: float = 80.0,
                    attack_range: float = 6.0, attack_cooldown: float = 0.9) -> Structure:
        t = Structure(pos=pos, team=team, kind="tower", lane=lane, tier=tier,
                      hp=hp, max_hp=hp, attack_damage=attack_damage,
                      attack_range=attack_range, attack_cooldown=attack_cooldown,
                      radius=1.1, vision=12.0)
        self.add(t)
        return t

    def spawn_wild(self, pos: Vec2, kind: str, hp: float, attack_damage: float,
                   attack_range: float, attack_cooldown: float, reward_xp: float,
                   reward_gold: int, radius: float = 0.8, weather: str = "",
                   plate: str = "", color: tuple = (180, 180, 150)) -> Wild:
        w = Wild(pos=pos, team=2, kind=kind, hp=hp, max_hp=hp,
                 attack_damage=attack_damage, attack_range=attack_range,
                 attack_cooldown=attack_cooldown, speed=0.0, radius=radius,
                 vision=7.0, reward_xp=reward_xp, reward_gold=reward_gold,
                 weather=weather, plate=plate, color=color)
        self.add(w)
        return w

    def wilds(self) -> list:
        return [e for e in self.entities.values() if isinstance(e, Wild)]

    def spawn_core(self, pos: Vec2, team: int, hp: float = 6000.0) -> Core:
        t = Core(pos=pos, team=team, kind="core", hp=hp, max_hp=hp,
                 attack_damage=0.0, attack_range=0.0, radius=1.6, vision=12.0)
        self.add(t)
        return t

    # --- accessori per tipo --------------------------------------------------
    def units(self) -> list:
        return [e for e in self.entities.values() if isinstance(e, Unit)]

    def alive_units(self) -> list:
        return [e for e in self.entities.values() if isinstance(e, Unit) and e.alive]

    def pokemons(self) -> list:
        return [e for e in self.entities.values() if isinstance(e, Pokemon)]

    def minions(self) -> list:
        return [e for e in self.entities.values() if isinstance(e, Minion)]

    def structures(self) -> list:
        return [e for e in self.entities.values() if isinstance(e, Structure)]

    def cores(self) -> list:
        return [e for e in self.entities.values() if isinstance(e, Core)]

    def combatants(self) -> list:
        """Tutto ciò che ha hp ed è vivo (unità + strutture)."""
        out = []
        for e in self.entities.values():
            if isinstance(e, (Unit, Structure)) and getattr(e, "alive", True):
                out.append(e)
        return out

    # --- avanzamento ---------------------------------------------------------
    def tick(self, dt: float) -> None:
        """Avanza il movimento di dt secondi. Muove solo le unità vive."""
        movers = self.alive_units()
        for u in movers:
            movement.advance_unit(u, dt, self.grid)
        movement.resolve_collisions(movers, self.grid, spatial=self.spatial)
