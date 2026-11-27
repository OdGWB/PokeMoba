"""Stato del mondo e avanzamento del movimento di un tick.

Il World non sa nulla di pygame, rete o rendering: contiene la griglia e le
entità, sa farle muovere e risolvere le collisioni. Le REGOLE di gioco (ondate,
IA, combattimento, vittoria) stanno in engine/match.py, che opera sul World.
"""
from __future__ import annotations

import config

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
        self.spirits: list = []   # spiriti della passiva di Spiritomb (entities.Spirit)
        # Liste per tipo in cache (stesso ordine di self.entities), rifatte solo
        # quando si aggiunge o toglie un'entita': pokemons()/structures()/... si
        # chiamano decine di volte a tick e il filtro con isinstance costava.
        self._by_type: dict = {}

    # --- gestione entità -----------------------------------------------------
    def _alloc_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def add(self, entity) -> None:
        if entity.id == 0:
            entity.id = self._alloc_id()
        self.entities[entity.id] = entity
        self._by_type.clear()

    def remove(self, entity_id: int) -> None:
        if self.entities.pop(entity_id, None) is not None:
            self._by_type.clear()

    def _of_type(self, cls) -> list:
        """Entita' di quel tipo (o tupla di tipi), in ordine di inserimento. NON
        modificare la lista restituita: e' quella in cache."""
        lst = self._by_type.get(cls)
        if lst is None:
            lst = [e for e in self.entities.values() if isinstance(e, cls)]
            self._by_type[cls] = lst
        return lst

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
                      passive: str = "", attack_fx: str = "",
                      rec_items: list | None = None) -> Pokemon:
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
                    attack_fx=attack_fx, rec_items=list(rec_items or []))
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
        return list(self._of_type(Wild))

    def spawn_core(self, pos: Vec2, team: int, hp: float = 6000.0) -> Core:
        t = Core(pos=pos, team=team, kind="core", hp=hp, max_hp=hp,
                 attack_damage=0.0, attack_range=0.0, radius=1.6, vision=12.0)
        self.add(t)
        return t

    # --- accessori per tipo --------------------------------------------------
    def units(self) -> list:
        return list(self._of_type(Unit))

    def alive_units(self) -> list:
        return [e for e in self._of_type(Unit) if e.alive]

    def pokemons(self) -> list:
        return list(self._of_type(Pokemon))

    def minions(self) -> list:
        return list(self._of_type(Minion))

    def structures(self) -> list:
        return list(self._of_type(Structure))

    def cores(self) -> list:
        return list(self._of_type(Core))

    def combatants(self) -> list:
        """Tutto ciò che ha hp ed è vivo (unità + strutture)."""
        return [e for e in self._of_type((Unit, Structure)) if e.alive]

    # --- avanzamento ---------------------------------------------------------
    def tick(self, dt: float) -> None:
        """Avanza il movimento di dt secondi. Muove solo le unità vive."""
        movers = self.alive_units()
        grid = self.grid
        # Le torri vive sono ostacoli fisici: chi ci finisce dentro (passo,
        # spinta, scatto) viene spinto fuori lungo il bordo.
        towers = [(s.pos.x, s.pos.y, config.TOWER_BLOCK_RADIUS)
                  for s in self._of_type(Structure)
                  if s.kind == "tower" and s.alive]
        nv = grid.native_view() if movement._STEP_NATIVE and grid._shape_on else None
        if nv is not None and hasattr(nv, "collide_units"):
            # Stesso ciclo in Rust (advance_unit di ogni unita' in ordine, poi le
            # collisioni); chi ha il centro dentro un muro torna al Python. Le
            # collisioni restituiscono anche chi tocca una torre.
            if hasattr(nv, "step_collide_units"):
                # Passo + collisioni in UNA chiamata (attributi letti una volta);
                # se qualcuno torna al Python, le collisioni si fanno dopo, come sotto.
                bad, hits = nv.step_collide_units(movers, dt, Vec2, 2, towers)
                if bad:
                    for i in bad:
                        movement.advance_unit(movers[i], dt, grid)
                    hits = nv.collide_units(movers, Vec2, 2, towers)
                if towers and hits:
                    movement.resolve_obstacles(movers, towers, grid, hits)
                return
            for i in nv.step_units(movers, dt, Vec2):
                movement.advance_unit(movers[i], dt, grid)
            hits = nv.collide_units(movers, Vec2, 2, towers)
            if towers and hits:
                movement.resolve_obstacles(movers, towers, grid, hits)
            return
        for u in movers:
            movement.advance_unit(u, dt, grid)
        movement.resolve_collisions(movers, grid, spatial=self.spatial)
        if towers:
            movement.resolve_obstacles(movers, towers, grid)
