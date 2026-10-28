"""Regole di gioco della partita (Fase 2).

Opera su un World già popolato dei Pokémon (creati dallo scene/client). Qui
dentro vivono: costruzione delle strutture dalla mappa, ondate di minion, IA di
minion e bot, combattimento, respawn e condizione di vittoria.

Puro: nessun pygame. In Fase 5 girerà identico sul server.

Prestazioni:
  - I minion seguono percorsi fissi (waypoint della lane) e usano A* SOLO quando
    inseguono un bersaglio dietro un ostacolo.
  - Target e vicinato via griglia spaziale, non O(n^2).
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import config
from . import evolution, skills
from .entities import Core, Minion, Pokemon, Structure, Unit, Wild
from .grid import TILE_BUSH
from .items import ITEM_SLOTS, ItemCatalog
from .jungle import JungleSystem
from .pathfinding import find_path, smooth_path
from .spatial import SpatialHash
from .stats import (CRIT_MULT, HIGH_CRIT_CHANCE, STAB_MULT, Stats,
                    ability_haste_factor, combine_tenacity as stat_combine_ten,
                    derive, evolution_mult as stat_evo_mult,
                    level_from_xp, mitigate as stat_mitigate,
                    penetrate as stat_penetrate, respawn_time)
from .types import TypeChart
from .vec import Vec2, direction_index
from .vision import VisionSystem

# Priorità di bersaglio (numero più basso = preferito).
_PRIO = {Minion: 0, Pokemon: 1, Structure: 2}

# Statistiche dei minion per tipo (stile LoL: melee tanky, caster dalla distanza,
# cannone grosso e lento). Valori greybox da bilanciare.
MINION_STATS = {
    "melee":  dict(hp=170, attack_damage=12, attack_range=1.1, attack_cooldown=1.0,
                   speed=3.1, radius=0.28, gold=20, xp=60),
    "caster": dict(hp=90,  attack_damage=18, attack_range=3.4, attack_cooldown=1.3,
                   speed=3.1, radius=0.24, gold=15, xp=30),
    "cannon": dict(hp=460, attack_damage=34, attack_range=3.0, attack_cooldown=1.6,
                   speed=2.9, radius=0.34, gold=50, xp=95),
}

BOT_AGGRO = 6.5
BOT_RETREAT_HP = 0.28       # sotto questa frazione di hp il bot si ritira
_WAYPOINT_REACHED = 0.6
_TOWER_AGGRO_WINDOW = 4.0   # s: finestra in cui una torre può colpire un Pokémon
_MINION_LEASH = 5.5         # tile: distanza max dalla lane prima di tornare indietro
_MINION_AGGRO_WINDOW = 4.0  # s: i minion focalizzano il campione che attacca un alleato
_MINION_RETALIATE = 2.5     # s: finestra per ritorsione contro chi li ha colpiti
XP_RADIUS = 8.0             # tile: raggio entro cui i nemici ricevono esperienza
# Livello a cui si sblocca la SCELTA del potenziamento di ogni slot (scaglionata).
SLOT_UPGRADE_LEVEL = {"Q": 5, "W": 6, "E": 7, "R": 8}
AA_WINDUP_FRAC = 0.2   # frazione dell'attacco spesa nel windup (danno a fine windup)


def _prio(entity) -> int:
    for cls, p in _PRIO.items():
        if isinstance(entity, cls):
            return p
    return 9


class Match:
    def __init__(self, world, map_data):
        self.world = world
        self.map = map_data
        self.time = 0.0
        self.winner: int | None = None
        self._first_blood_done = False   # prima uccisione della partita (punto 4)
        self.announcements: list[tuple[float, str]] = []  # (tempo, testo) per l'HUD
        self._wave_timer = config.FIRST_WAVE_TIME
        self._wave_number = 0
        self._spawn_queue: list[tuple[float, int, str]] = []  # (due, team, lane)
        self._combat_hash = SpatialHash(cell_size=3.0)
        self._ai: dict[int, dict] = {}  # stato IA per unità (indice waypoint, cooldown A*)
        data_dir = Path(__file__).resolve().parent.parent / "data"
        self.types = TypeChart.load(data_dir / "types.json")
        self.item_catalog = ItemCatalog.load(data_dir / "items.json")
        self.fx_events: list[dict] = []   # effetti visivi per il client (cosmetici)
        self.projectiles: list[dict] = []  # proiettili che viaggiano (es. bolla Idropulsar)
        self.area_effects: list[dict] = []  # aree persistenti (es. Pioggia di Frecce)
        self.vision = VisionSystem(self.world.grid)
        self._build_structures()
        self.jungle = JungleSystem(self)

    # --- costruzione ---------------------------------------------------------
    def _build_structures(self):
        for s in self.map.structures:
            x, y = s["pos"]
            pos = Vec2(x + 0.5, y + 0.5)
            team = s["team"]
            if s["type"] == "core":
                core = self.world.spawn_core(pos, team, hp=config.CORE_HP)
                setattr(core, "color", config.TEAM_COLORS[team])
            else:
                tier = s.get("tier", 1)
                hp = config.TOWER_HP_INNER if tier >= 2 else config.TOWER_HP_OUTER
                tw = self.world.spawn_tower(pos, team, s.get("lane", "mid"), tier,
                                            hp=hp, attack_damage=config.TOWER_DAMAGE)
                setattr(tw, "color", config.TEAM_COLORS[team])
                setattr(tw, "plates_left", config.PLATE_COUNT)   # placche (punto 6)

    def oriented_lane(self, lane_name: str, team: int) -> list[Vec2]:
        """Waypoint della lane dalla propria base a quella nemica."""
        pts = [Vec2(x, y) for (x, y) in self.map.lanes.get(lane_name, [])]
        # Le lane nel JSON vanno da base0 a base1; la squadra 1 le percorre al contrario.
        return pts if team == 0 else list(reversed(pts))

    # --- ciclo ---------------------------------------------------------------
    def update(self, dt: float, tick: int) -> None:
        if self.winner is not None:
            return
        self.time += dt
        self._combat_hash.rebuild(self.world.combatants())
        # Visione per entrambe le squadre (ricalcolo solo al cambio tile): la usano
        # i bot per ingaggiare solo nemici realmente visibili, e il client per la
        # nebbia. In Fase 5 il server la userà per filtrare gli snapshot.
        self.vision.update(self.world, 0)
        self.vision.update(self.world, 1)

        self.jungle.update(dt)
        self._update_recall(dt)
        self._update_waves(dt)
        self._update_ai(dt)
        self._update_submerge(dt)    # SUB: riemersione (prima dei cast)
        self._update_casts(dt)       # esecuzione mosse Q/W/E/R
        self._update_projectiles(dt) # proiettili che viaggiano (bolla)
        self._update_area_effects(dt)  # aree persistenti (Pioggia di Frecce)
        self._update_blink_return(dt)  # Spettrotuffo: ritorno automatico
        self._update_curses(dt)        # Maledizione: danno ritardato
        self._update_combat(dt)      # attacchi base
        self._update_status(dt)      # scadenza stati + velocità effettiva + ricariche
        self.world.tick(dt)          # movimento + collisioni
        self._update_regen(dt)
        self._update_plates(dt)      # placche delle torri (oro ai vicini)
        self._update_gold(dt)
        self._update_bot_shop(dt)
        self._update_respawns(dt)
        self._update_evolution(dt)   # evoluzioni + offerte di scelta
        self._check_win()

    # --- ondate --------------------------------------------------------------
    def _update_waves(self, dt: float) -> None:
        self._wave_timer -= dt
        if self._wave_timer <= 0.0:
            self._wave_timer += config.WAVE_INTERVAL
            self._wave_number += 1
            # Composizione dell'ondata: 3 melee + 3 caster, + cannone ogni N ondate.
            comp = (["melee"] * config.MELEE_PER_WAVE
                    + ["caster"] * config.CASTER_PER_WAVE)
            if self._wave_number % config.CANNON_EVERY == 0:
                comp.append("cannon")
            for team in (0, 1):
                for lane in self.map.lanes.keys():
                    for k, mtype in enumerate(comp):
                        due = self.time + k * config.MINION_SPAWN_GAP
                        self._spawn_queue.append((due, team, lane, mtype))

        # Fai spawnare i minion la cui attesa è scaduta.
        ready = [s for s in self._spawn_queue if s[0] <= self.time]
        if ready:
            self._spawn_queue = [s for s in self._spawn_queue if s[0] > self.time]
            for (_due, team, lane, mtype) in ready:
                self._spawn_minion(team, lane, mtype)

    def _spawn_minion(self, team: int, lane: str, mtype: str) -> None:
        pts = self.oriented_lane(lane, team)
        if len(pts) < 2:
            return
        base = pts[0]
        d = (pts[1] - base).normalized()
        perp = Vec2(-d.y, d.x)
        # Scostamento perpendicolare per non impilarli, pseudo-casuale ma deterministico.
        jig = (hash((int(self.time * 10), team, lane, len(self.world.minions()))) % 7 - 3) * 0.25
        pos = base + d * 3.0 + perp * jig
        stats = dict(MINION_STATS[mtype])
        # I minion crescono col tempo (hp e danno) per rompere gli stalli.
        scale = 1.0 + config.MINION_SCALE_PER_MIN * (self.time / 60.0)
        stats["hp"] = stats["hp"] * scale
        stats["attack_damage"] = stats["attack_damage"] * scale
        m = self.world.spawn_minion(pos, team, lane, pts,
                                    self._minion_color(team, mtype),
                                    minion_type=mtype, **stats)
        m.lane_idx = 1
        self._ai[m.id] = {"astar_cd": 0.0}

    @staticmethod
    def _minion_color(team: int, mtype: str) -> tuple:
        base = config.TEAM_COLORS[team]
        if mtype == "caster":   # più chiaro
            return tuple(min(255, int(c + (255 - c) * 0.45)) for c in base)
        if mtype == "cannon":   # più scuro
            return tuple(int(c * 0.6) for c in base)
        return base

    # --- IA ------------------------------------------------------------------
    def _update_ai(self, dt: float) -> None:
        for m in self.world.minions():
            if m.alive:
                self._ai_minion(m, dt)
        for p in self.world.pokemons():
            if not p.alive:
                continue
            if p.fear_until > self.time and p.fear_src is not None:
                self._flee(p, dt)     # spavento: fuga automatica dalla fonte
                continue
            if p.is_bot and p.is_jungler:
                self._ai_jungler(p, dt)
            elif p.is_bot:
                self._ai_bot(p, dt)
            else:
                self._ai_player(p, dt)
        # Neutrali (giungla): stazionari, colpiscono chi si avvicina.
        for w in self.world.wilds():
            if not w.alive:
                continue
            tgt = self._nearest_wild_target(w)
            w.target_id = tgt.id if tgt is not None else None
            if tgt is not None:
                self._face(w, tgt)

    def _nearest_wild_target(self, w):
        best, bd = None, 1e9
        for e in self._combat_hash.query_radius(w.pos.x, w.pos.y, w.attack_range + 2.0):
            if e.team == 2 or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion)):
                continue
            d = w.pos.dist(e.pos)
            if d <= w.attack_range + getattr(e, "radius", 0.0) + 0.5 and d < bd:
                best, bd = e, d
        return best

    def _ai_minion(self, m: Minion, dt: float) -> None:
        state = self._ai.setdefault(m.id, {})
        target = self._valid_minion_target(m, state)
        if target is None:
            target = self._acquire_minion_target(m)
            m.target_id = target.id if target else None
            if target is not None:
                # Ancora del guinzaglio: dove il minion si trovava quando ha ingaggiato.
                state["leash"] = Vec2(m.pos.x, m.pos.y)
            else:
                state.pop("leash", None)
        if target is not None:
            if self._within_attack(m, target):
                m.stop()
                self._face(m, target)
                m.chasing = False
            else:
                origin = state.get("leash", m.pos)
                if m.pos.dist(origin) <= _MINION_LEASH:
                    m.chasing = True
                    self._chase(m, target, dt)
                else:
                    # Troppo lontano dal punto di ingaggio: molla e torna in lane.
                    m.target_id = None
                    state.pop("leash", None)
                    m.chasing = False
                    self._follow_lane(m)
            return
        m.chasing = False
        self._follow_lane(m)

    def _valid_minion_target(self, m: Minion, state: dict):
        if m.target_id is None:
            return None
        t = self.world.get(m.target_id)
        if t is None or not getattr(t, "alive", False) or t.team == m.team:
            return None
        origin = state.get("leash", m.pos)
        # Perde il bersaglio se è troppo lontano o se si è allontanato dall'ingaggio.
        if m.pos.dist(t.pos) > m.aggro * 1.6 or m.pos.dist(origin) > _MINION_LEASH:
            return None
        return t

    def _acquire_minion_target(self, m: Minion):
        """Scelta del bersaglio in stile LoL.

        Priorità:
          1. Campione nemico che sta attaccando un alleato (difesa).
          2. Chi ha colpito questo minion di recente (ritorsione).
          3. Minion nemico più vicino.
          4. Campione nemico più vicino.
          5. Struttura nemica più vicina.
        """
        cands = []
        for e in self._combat_hash.query_radius(m.pos.x, m.pos.y, m.aggro):
            if e is m or e.team == m.team or not getattr(e, "alive", False):
                continue
            if m.pos.dist(e.pos) <= m.aggro + getattr(e, "radius", 0.0):
                cands.append(e)
        if not cands:
            return None

        def nearest(items):
            return min(items, key=lambda e: m.pos.dist(e.pos)) if items else None

        # 1) Campione che ha appena attaccato un alleato.
        defenders = [e for e in cands if isinstance(e, Pokemon)
                     and self.time - getattr(e, "_minion_aggro_at", -1e9) <= _MINION_AGGRO_WINDOW]
        if defenders:
            return nearest(defenders)
        # 2) Ritorsione contro chi ci ha colpito.
        if (m.last_attacker_id is not None
                and self.time - m.last_damaged_at <= _MINION_RETALIATE):
            attacker = self.world.get(m.last_attacker_id)
            if attacker in cands:
                return attacker
        # 3-5) Priorità per tipo.
        minions = [e for e in cands if isinstance(e, Minion)]
        if minions:
            return nearest(minions)
        pokes = [e for e in cands if isinstance(e, Pokemon)]
        if pokes:
            return nearest(pokes)
        structs = [e for e in cands if isinstance(e, Structure)]
        return nearest(structs)

    def _ai_player(self, p: Pokemon, dt: float) -> None:
        """Il Pokémon del giocatore è guidato dagli ORDINI (non da un'IA autonoma)."""
        if self._immobile(p):
            p.stop()
            return
        if p.recalling:                 # fermo durante il richiamo
            p.target_id = None
            p.stop()
            return
        if p.order == "move":
            if p.path:
                p.target_id = None   # in movimento puro non attacca
                return
            p.order = "idle"         # arrivato: passa a idle (auto-attacco di prossimità)

        if p.order == "attack":
            t = self.world.get(p.order_target_id) if p.order_target_id is not None else None
            if t is not None and getattr(t, "alive", False) and t.team != p.team:
                p.target_id = t.id
                if self._within_attack(p, t):
                    p.stop()
                    self._face(p, t)
                else:
                    self._chase(p, t, dt)
                return
            p.order = "idle"

        if p.order == "attackmove":
            tgt = self._acquire_target(p, BOT_AGGRO)
            if tgt is not None:
                p.target_id = tgt.id
                if self._within_attack(p, tgt):
                    p.stop()
                    self._face(p, tgt)
                else:
                    self._chase(p, tgt, dt)
                return
            p.target_id = None
            if p.order_point is not None and p.pos.dist(p.order_point) > 0.5:
                self._move_towards(p, p.order_point, dt, use_astar=True)
            else:
                p.order = "idle"
                p.stop()
            return

        # idle / stop: auto-attacco del nemico più vicino a portata.
        tgt = self._acquire_target(p, self._auto_reach(p) + 1.5)
        if tgt is not None and self._within_attack(p, tgt):
            p.target_id = tgt.id
            self._face(p, tgt)
        else:
            p.target_id = None

    def _ai_bot(self, p: Pokemon, dt: float) -> None:
        if self._immobile(p):
            p.stop()
            return
        # Ritirata se la vita è bassa.
        if p.hp < p.max_hp * BOT_RETREAT_HP:
            p.target_id = None
            self._move_towards(p, p.spawn_pos, dt, use_astar=True)
            return
        target = self._valid_target(p)
        if target is None:
            target = self._acquire_target(p, BOT_AGGRO)
        # Non fare dive su una struttura nemica senza minion alleati a proteggerti.
        if (isinstance(target, Structure)
                and not self._has_allied_minion_near(p, target.pos, 4.5)):
            target = None
        p.target_id = target.id if target is not None else None
        if target is not None:
            self._bot_try_cast(p, target)
            if self._within_attack(p, target):
                p.stop()
                self._face(p, target)
            else:
                self._chase(p, target, dt)
            return
        # Difendi una struttura alleata sotto attacco, se vicina.
        defend = self._threatened_structure(p)
        if defend is not None:
            self._move_towards(p, defend.pos, dt, use_astar=True)
            return
        # Altrimenti spingi la lane, ma fermati fuori dalla gittata delle torri
        # nemiche se non hai minion davanti.
        self._follow_bot_lane_safe(p, dt)

    def _has_allied_minion_near(self, p, pos, r: float) -> bool:
        for e in self._combat_hash.query_radius(pos.x, pos.y, r):
            if isinstance(e, Minion) and e.team == p.team and e.alive and pos.dist(e.pos) <= r:
                return True
        return False

    def _unsafe_dive(self, p, point) -> bool:
        for e in self.world.structures():
            if e.kind != "tower" or not e.alive or e.team == p.team:
                continue
            if point.dist(e.pos) <= e.attack_range + 0.8 and \
                    not self._has_allied_minion_near(p, e.pos, 4.5):
                return True
        return False

    def _threatened_structure(self, p):
        best, bestd = None, 1e9
        for e in self.world.structures():
            if e.team != p.team or not e.alive:
                continue
            enemies = [x for x in self._combat_hash.query_radius(e.pos.x, e.pos.y, 6.0)
                       if x.team != p.team and getattr(x, "alive", False)
                       and isinstance(x, (Pokemon, Minion))]
            if not enemies:
                continue
            d = p.pos.dist(e.pos)
            if d < bestd:
                bestd, best = d, e
        # Difende solo se la struttura è abbastanza vicina (altrimenti continua
        # a spingere: difendere sempre porterebbe allo stallo).
        return best if best is not None and bestd < 20.0 else None

    def _follow_bot_lane_safe(self, p: Pokemon, dt: float) -> None:
        st = self._ai.setdefault(p.id, {})
        pts = self.oriented_lane(p.assigned_lane, p.team)
        if len(pts) < 2:
            self._move_towards(p, p.spawn_pos, dt)
            return
        idx = min(st.get("lane_idx", 1), len(pts) - 1)
        wp = pts[idx]
        if p.pos.dist(wp) <= 1.2 and idx < len(pts) - 1:
            idx += 1
            wp = pts[idx]
        st["lane_idx"] = idx
        # Se avanzare porterebbe dentro la gittata di una torre nemica non
        # protetta da minion alleati, aspetta (equilibrio di lane).
        step = (wp - p.pos)
        ahead = p.pos + (step.normalized() * min(2.5, step.length())) if step.length() > 1e-6 else p.pos
        if self._unsafe_dive(p, ahead) or self._unsafe_dive(p, p.pos):
            p.stop()
            return
        self._set_step(p, wp, dt)

    # --- aiutanti IA ---------------------------------------------------------
    def _valid_target(self, u):
        if u.target_id is None:
            return None
        t = self.world.get(u.target_id)
        if t is None or not getattr(t, "alive", False):
            return None
        # I bot perdono un bersaglio che entra in nebbia/cespuglio.
        if (getattr(u, "is_bot", False) and isinstance(t, Unit)
                and not self.vision.is_enemy_visible(u.team, t.id)):
            return None
        # Mantieni il bersaglio solo entro un guinzaglio ragionevole.
        leash = (u.aggro if isinstance(u, Minion) else BOT_AGGRO) * 1.8
        if u.pos.dist(t.pos) > leash:
            return None
        return t

    def _acquire_target(self, u, radius: float):
        bot = getattr(u, "is_bot", False)
        best, best_key = None, None
        for e in self._combat_hash.query_radius(u.pos.x, u.pos.y, radius):
            if e is u or e.team == u.team or not getattr(e, "alive", False):
                continue
            d = u.pos.dist(e.pos)
            if d > radius:
                continue
            # I bot ingaggiano solo nemici che la loro squadra vede davvero
            # (rispettano nebbia e cespugli). Le strutture sono sempre note.
            if bot and isinstance(e, Unit) and not self.vision.is_enemy_visible(u.team, e.id):
                continue
            key = (_prio(e), d)
            if best_key is None or key < best_key:
                best, best_key = e, key
        return best

    def _within_attack(self, u, target) -> bool:
        reach = getattr(u, "attack_range", 0.0) + getattr(target, "radius", 0.0)
        if isinstance(u, Pokemon):
            reach = self._auto_reach(u) + getattr(target, "radius", 0.0)
        return u.pos.dist(target.pos) <= reach

    def _chase(self, u, target, dt: float) -> None:
        if isinstance(u, Minion):
            u.chasing = True
        bb = getattr(u, "bush_blocks", False)   # minion: aggira i cespugli
        if self.world.grid.line_of_sight(u.pos.x, u.pos.y,
                                          target.pos.x, target.pos.y, bb):
            self._set_step(u, target.pos, dt)
        else:
            self._move_towards(u, target.pos, dt, use_astar=True)
        self._face(u, target)

    def _follow_lane(self, m: Minion) -> None:
        if not m.lane_points:
            m.stop()
            return
        if m.lane_idx >= len(m.lane_points):
            m.lane_idx = len(m.lane_points) - 1
        wp = m.lane_points[m.lane_idx]
        if m.pos.dist(wp) <= _WAYPOINT_REACHED and m.lane_idx < len(m.lane_points) - 1:
            m.lane_idx += 1
            wp = m.lane_points[m.lane_idx]
        m.set_path([wp])
        m.facing = direction_index(wp.x - m.pos.x, wp.y - m.pos.y)

    def _follow_bot_lane(self, p: Pokemon, dt: float) -> None:
        st = self._ai.setdefault(p.id, {})
        pts = self.oriented_lane(p.assigned_lane, p.team)
        if len(pts) < 2:
            self._move_towards(p, p.spawn_pos, dt)
            return
        idx = st.get("lane_idx", 1)
        idx = min(idx, len(pts) - 1)
        wp = pts[idx]
        if p.pos.dist(wp) <= 1.2 and idx < len(pts) - 1:
            idx += 1
            wp = pts[idx]
        st["lane_idx"] = idx
        self._set_step(p, wp, dt)

    def _set_step(self, u, dest: Vec2, dt: float) -> None:
        """Movimento diretto verso dest (un waypoint singolo)."""
        u.set_path([dest])

    def _move_towards(self, u, dest: Vec2, dt: float, use_astar: bool = False) -> None:
        bb = getattr(u, "bush_blocks", False)   # minion: aggira i cespugli
        if not use_astar or self.world.grid.line_of_sight(u.pos.x, u.pos.y,
                                                           dest.x, dest.y, bb):
            u.set_path([dest])
            return
        st = self._ai.setdefault(u.id, {})
        st["astar_cd"] = st.get("astar_cd", 0.0) - dt
        if st["astar_cd"] <= 0.0:
            st["astar_cd"] = 0.3  # ricalcola A* al massimo ~3 volte/s
            start = (int(u.pos.x), int(u.pos.y))
            goal = (int(dest.x), int(dest.y))
            tile_path = find_path(self.world.grid, start, goal, bb)
            if tile_path:
                pts = smooth_path(self.world.grid, tile_path, bb)
                wps = [Vec2(px, py) for (px, py) in pts[1:]]
                st["astar_path"] = wps
        wps = st.get("astar_path") or [dest]
        u.set_path(wps)

    def _face(self, u, target) -> None:
        u.facing = direction_index(target.pos.x - u.pos.x, target.pos.y - u.pos.y)

    # --- combattimento -------------------------------------------------------
    def _update_combat(self, dt: float) -> None:
        for c in self.world.combatants():
            if c.attack_timer > 0.0:
                c.attack_timer = max(0.0, c.attack_timer - dt)

        # Minion e Pokémon colpiscono il proprio target se a tiro.
        for u in self.world.alive_units():
            if isinstance(u, Pokemon):
                if self._immobile(u) or u.submerged:
                    u.aa_active = False   # stordito/addormentato/immerso: perde il windup
                    continue
                self._pokemon_auto_attack(u)
                continue
            t = self.world.get(u.target_id) if u.target_id is not None else None
            if t is not None and getattr(t, "alive", False) and self._within_attack(u, t):
                self._try_attack(u, t)

        # Torri: minion nemici a tiro per primi, poi Pokémon nemici "aggressivi".
        for s in self.world.structures():
            if not s.alive or s.attack_damage <= 0:
                continue
            self._tower_fire(s)

        self._cleanup_dead()

    def _tower_fire(self, tower: Structure) -> None:
        enemy_minions = []
        enemy_pokes = []
        for e in self._combat_hash.query_radius(tower.pos.x, tower.pos.y, tower.attack_range):
            if e.team == tower.team or not getattr(e, "alive", False):
                continue
            if tower.pos.dist(e.pos) > tower.attack_range + getattr(e, "radius", 0.0):
                continue
            if isinstance(e, Minion):
                enemy_minions.append(e)
            elif isinstance(e, Pokemon):
                enemy_pokes.append(e)
        target = None
        if enemy_minions:
            target = min(enemy_minions, key=lambda m: tower.pos.dist(m.pos))
        else:
            # Un Pokémon viene colpito solo se ha fatto danno a un alleato di recente.
            aggressive = [p for p in enemy_pokes
                          if self.time - getattr(p, "_tower_aggro_at", -1e9) <= _TOWER_AGGRO_WINDOW]
            if aggressive:
                target = min(aggressive, key=lambda p: tower.pos.dist(p.pos))
        tower.target_id = target.id if target else None
        if target is not None:
            self._try_attack(tower, target)

    def _try_attack(self, attacker, target) -> None:
        if attacker.attack_timer > 0.0:
            return
        cd = attacker.attack_cooldown
        if isinstance(attacker, Pokemon) and attacker.rampage_until > self.time:
            cd *= 0.5   # Oltraggio: attacca più in fretta
        attacker.attack_timer = cd
        # FX dell'auto-attacco dei Pokémon (così si vede quando si attacca):
        # fendente per il corpo a corpo, piccolo colpo per chi tira da lontano.
        if isinstance(attacker, Pokemon):
            mt = attacker.types[0] if attacker.types else "Normal"
            self.fx_events.append({"kind": "attack",
                                   "a": (attacker.pos.x, attacker.pos.y),
                                   "b": (target.pos.x, target.pos.y), "mtype": mt,
                                   "melee": attacker.attack_range <= 2.2,
                                   "fx": attacker.attack_fx})
        dmg = self._basic_damage(attacker, target)
        self._deal_damage(attacker, target, dmg)
        self._vamp(attacker, dmg, physical=True)

    def _pokemon_auto_attack(self, u) -> None:
        """Auto-attacco con windup/recovery (stile LoL). Il danno è garantito solo
        a fine windup; muoversi o lanciare un'abilità prima lo annulla (senza perdere
        il cooldown). Dopo che il colpo è partito ci si può muovere (kiting)."""
        t = self.world.get(u.target_id) if u.target_id is not None else None
        if u.confuse_until > self.time:
            t = self._nearest_ally(u)   # confuso: colpisce gli alleati
        if u.aa_active:
            tgt = self.world.get(u.aa_target_id)
            if u.moving or tgt is None or not getattr(tgt, "alive", False):
                u.aa_active = False
                if u.moving:
                    u.attack_timer = 0.0   # windup annullato: niente cooldown perso
                return
            if self.time >= u.aa_until:    # fine windup: danno garantito + colpo
                if self._within_attack(u, tgt):
                    dmg = self._basic_damage(u, tgt)
                    if u.aa_stealth:       # Distacco: primo colpo furtivo potenziato
                        dmg *= config.DISTACCO_BONUS_MULT
                        u.stealth_shot_ready = False
                        u.reveal_block_until = self.time + config.DISTACCO_REVEAL_BLOCK
                    self._deal_damage(u, tgt, dmg)
                    self._vamp(u, dmg, physical=True)
                    mt = u.types[0] if u.types else "Normal"
                    self.fx_events.append({"kind": "attack", "a": (u.pos.x, u.pos.y),
                                           "b": (tgt.pos.x, tgt.pos.y), "mtype": mt,
                                           "melee": u.attack_range <= 2.2,
                                           "fx": u.attack_fx})
                u.aa_active = False
            return
        # Nuovo attacco: servono bersaglio a tiro, cooldown pronto e stare fermi.
        if t is None or not getattr(t, "alive", False) or not self._within_attack(u, t):
            return
        if u.attack_timer > 0.0 or u.moving:
            return
        # Passiva Distacco: ricarica il colpo furtivo quando sei allo scoperto.
        if u.passive_id == "distacco" and not self._is_hidden(u):
            u.stealth_shot_ready = True
        u.aa_stealth = (u.passive_id == "distacco" and u.stealth_shot_ready
                        and self._is_hidden(u))
        cd = u.attack_cooldown
        if u.rampage_until > self.time:
            cd *= 0.5   # Oltraggio: attacca più in fretta
        u.aa_active = True
        u.aa_target_id = t.id
        u.aa_until = self.time + cd * AA_WINDUP_FRAC
        u.attack_timer = cd            # il cooldown parte dall'inizio dell'attacco
        self._face(u, t)
        self.fx_events.append({"eid": u.id, "anim": "Attack"})   # avvia l'anim

    def _nearest_ally(self, u):
        best, bd = None, 1e9
        for e in self._combat_hash.query_radius(u.pos.x, u.pos.y, u.attack_range + 2.0):
            if e is u or e.team != u.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion)):
                continue
            d = u.pos.dist(e.pos)
            if d < bd:
                best, bd = e, d
        return best

    def _basic_damage(self, attacker, target) -> float:
        """Danno di un attacco base: fisico, mitigato dalla difesa del bersaglio.

        - Pokémon: usano l'Attacco effettivo (con buff/passivi).
        - Torri: potenza con "ramp" crescente sullo stesso bersaglio (anti-dive).
        - Minion: potenza fissa, ridotta contro le strutture (grattano lento).
        """
        if isinstance(attacker, Pokemon):
            power = attacker.eff_attack()
            if attacker.rampage_until > self.time:
                power *= 1.4   # Oltraggio: attacchi base più forti
        elif isinstance(attacker, Structure):
            power = attacker.attack_damage * self._tower_ramp(attacker, target)
        else:  # Minion o Wild
            power = attacker.attack_damage
            if isinstance(target, Structure):
                power *= config.STRUCT_MINION_DMG_MULT
                # Giudizio: i minion della squadra buffata fanno doppio alle torri.
                if isinstance(attacker, Minion) and self.jungle.team_has_judgment(attacker.team):
                    power *= 2.0
        if isinstance(target, Pokemon):
            # Gli auto-attacchi sono fisici e senza tipo (niente STAB/efficacia);
            # possono fare critico e beneficiano di penetrazione armatura.
            return self._mitigate_hit(attacker, target, power, magic=False,
                                      can_crit=True)
        return max(1.0, power)

    def _mitigate_hit(self, caster, target, raw: float, *, magic: bool,
                      crit_bonus: float = 0.0, can_crit: bool = False) -> float:
        """Critico -> penetrazione difesa -> mitigazione -> riduzione fissa.

        La penetrazione (percentuale poi fissa/letalita') non porta mai la difesa
        sotto 0; la riduzione danni fissa del difensore agisce dopo la mitigazione.
        """
        if isinstance(caster, Pokemon):
            chance = (caster.crit if can_crit else 0.0) + crit_bonus
            if chance > 0.0 and random.random() < chance:
                raw *= CRIT_MULT
        if not isinstance(target, Pokemon):
            return max(1.0, raw)
        defense = target.eff_sp_defense() if magic else target.eff_defense()
        if isinstance(caster, Pokemon):
            if magic:
                flat = caster.magic_pen_flat + (0.0 if caster.lethality_physical
                                                else caster.lethality)
                defense = stat_penetrate(defense, caster.magic_pen_pct, flat)
            else:
                flat = caster.lethality if caster.lethality_physical else 0.0
                defense = stat_penetrate(defense, caster.armor_pen_pct, flat)
        out = stat_mitigate(raw, defense) - target.flat_reduction
        return max(1.0, out)

    def _vamp(self, caster, dmg: float, physical: bool) -> None:
        """Rubavita (solo fisico/auto) e omnivamp (ogni danno): cura = danno × %."""
        if not isinstance(caster, Pokemon) or dmg <= 0.0 or not caster.alive:
            return
        frac = caster.omnivamp + (caster.lifesteal if physical else 0.0)
        if frac > 0.0:
            caster.hp = min(caster.max_hp, caster.hp + dmg * frac)

    @staticmethod
    def _tower_ramp(tower, target) -> float:
        if getattr(tower, "_ramp_target", None) == target.id:
            tower._ramp_stacks = getattr(tower, "_ramp_stacks", 0) + 1
        else:
            tower._ramp_target = target.id
            tower._ramp_stacks = 0
        return min(config.TOWER_RAMP_MAX,
                   1.0 + tower._ramp_stacks * config.TOWER_RAMP_PER_HIT)

    def _alive_towers(self, team: int) -> int:
        return sum(1 for e in self.world.structures()
                   if e.kind == "tower" and e.team == team and e.alive)

    def _deal_damage(self, attacker, target, amount: float) -> None:
        # Bersaglio non bersagliabile (es. SUB sotto terra): nessun danno.
        if isinstance(target, Pokemon) and target.untargetable_until > self.time:
            return
        # Il nucleo è invulnerabile finché restano abbastanza torri della squadra.
        if isinstance(target, Core) and self._alive_towers(target.team) > config.CORE_EXPOSE_TOWERS_LEFT:
            return
        # Scudo (solo Pokémon): assorbe prima degli HP.
        if (isinstance(target, Pokemon) and target.shield > 0.0
                and target.shield_until > self.time):
            absorbed = min(target.shield, amount)
            target.shield -= absorbed
            amount -= absorbed
        target.hp -= amount
        target.last_attacker_id = attacker.id
        target.last_damaged_at = self.time
        # Il sonno si rompe al primo danno subito.
        if isinstance(target, Pokemon) and amount > 0.0 and target.sleep_until > self.time:
            target.sleep_until = -1.0
        # Un Pokémon che danneggia un Pokémon/struttura diventa bersaglio valido per le torri.
        if isinstance(attacker, Pokemon) and isinstance(target, (Pokemon, Structure)):
            setattr(attacker, "_tower_aggro_at", self.time)
        # Un Pokémon che attacca un altro Pokémon viene focalizzato dai minion
        # nemici vicini che difendono l'alleato colpito.
        if isinstance(attacker, Pokemon) and isinstance(target, Pokemon):
            setattr(attacker, "_minion_aggro_at", self.time)
            if attacker.team != target.team:   # registra per gli assist
                dmg = getattr(target, "_damagers", None)
                if dmg is None:
                    dmg = {}
                    setattr(target, "_damagers", dmg)
                dmg[attacker.id] = self.time
        if target.hp <= 0.0 and target.alive:
            self._on_death(target, attacker)

    def _on_death(self, victim, killer) -> None:
        victim.hp = 0.0
        victim.alive = False
        if isinstance(victim, Wild):
            self.jungle.on_wild_death(victim, killer)
            return
        self._award_xp(victim, killer)
        self._award_gold(victim, killer)
        if isinstance(victim, Pokemon):
            victim.stop()
            victim.target_id = None
            victim.judgment_until = -1.0   # perde il Giudizio morendo
            victim.respawn_timer = respawn_time(victim.level)
            victim.respawn_max = victim.respawn_timer
        elif isinstance(victim, Core):
            self.winner = killer.team if killer is not None else (1 - victim.team)
            self.announcements.append((self.time,
                                       f"Nucleo squadra {victim.team} distrutto!"))
        elif isinstance(victim, Structure):
            self.announcements.append((self.time,
                                       f"Torre {victim.lane} squadra {victim.team} distrutta!"))

    def _cleanup_dead(self) -> None:
        for e in list(self.world.entities.values()):
            if isinstance(e, Minion) and not e.alive:
                self.world.remove(e.id)
                self._ai.pop(e.id, None)
            elif isinstance(e, Wild) and not e.alive:
                self.world.remove(e.id)
            elif isinstance(e, Structure) and not isinstance(e, Core) and not e.alive:
                self.world.remove(e.id)

    # --- esperienza / livelli ------------------------------------------------
    # XP condivisa tra i presenti: 100% da solo, 65% a testa in due, 47% in tre+.
    _XP_SHARE = {1: 1.0, 2: 0.65}

    def _team_avg_level(self, team: int) -> float:
        lv = [p.level for p in self.world.pokemons() if p.team == team]
        return sum(lv) / len(lv) if lv else 1.0

    def _avg_player_level(self) -> float:
        lv = [p.level for p in self.world.pokemons()]
        return sum(lv) / len(lv) if lv else 1.0

    def _recovery_mult(self, p: Pokemon) -> float:
        """Recupero: +15% XP da minion/giungla per chi e' 2+ livelli sotto la media."""
        return 1.15 if p.level <= self._team_avg_level(p.team) - 2.0 else 1.0

    def _award_xp(self, victim, killer=None) -> None:
        recipients = [p for p in self.world.pokemons()
                      if p.alive and p.team != victim.team
                      and p.pos.dist(victim.pos) <= XP_RADIUS]
        if not recipients:
            return
        if isinstance(victim, Minion):
            # XP dei minion condivisa tra i presenti, con bonus recupero.
            frac = self._XP_SHARE.get(len(recipients), 0.47)
            for p in recipients:
                self._gain_xp(p, victim.xp * frac * self._recovery_mult(p))
        elif isinstance(victim, Pokemon):
            # Uccisione: 140 + 40×liv. vittima, +20% se la vittima e' di livello
            # piu' alto del killer. Non condivisa, niente recupero.
            base = 140.0 + 40.0 * victim.level
            if isinstance(killer, Pokemon) and victim.level > killer.level:
                base *= 1.2
            for p in recipients:
                self._gain_xp(p, base)
        # strutture: niente esperienza (per ora)

    def _gain_xp(self, p: Pokemon, amount: float) -> None:
        p.xp += amount
        new_level = level_from_xp(p.xp)
        while p.level < new_level:
            p.level += 1
            self._recompute_stats(p, heal_delta=True)

    @staticmethod
    def _n_stages(p: Pokemon) -> int:
        """Numero di stadi della linea evolutiva (per M, punto 8)."""
        stages = {int(e.get("stage", 0)) for e in p.evolutions} if p.evolutions else set()
        return max(1, len(stages))

    def _recompute_stats(self, p: Pokemon, heal_delta: bool = False,
                         preserve_ratio: bool = False) -> None:
        """Ricalcola le statistiche da livello, stadio e oggetti/passivi.

        Gli HP massimi includono i bonus HP di oggetti e mosse di potenziamento;
        p.stats resta "pulito" (il bonus HP non entra nelle statistiche base).
        """
        old_max = p.max_hp
        old_hp = p.hp
        d = derive(p.base_stats, p.level, ranged=p.ranged)
        # M (moltiplicatore d'evoluzione, punto 8) si applica a HP, AD, armatura,
        # RM, mana e rigenerazione; NON a MS/AS, gittata, AP e moltiplicatore
        # abilita', cosi' il "feeling" del Pokémon resta stabile fra gli stadi.
        m = stat_evo_mult(p.stage, self._n_stages(p))
        p.stat_mult = m
        p.stats = Stats(hp=d.stats.hp * m, attack=d.stats.attack * m,
                        defense=d.stats.defense * m, sp_attack=d.stats.sp_attack,
                        sp_defense=d.stats.sp_defense * m, speed=d.stats.speed)

        def _b(k):   # somma dei bonus da oggetti e mosse di potenziamento
            return p.item_bonus.get(k, 0.0) + p.passive_bonus.get(k, 0.0)

        # Velocita' (con eventuali extra MS/AS dagli oggetti; non toccati da M).
        p.move_speed_base = d.move_speed_tiles + _b("move_speed")
        as_total = min(2.5, d.attack_speed * (1.0 + _b("attack_speed")))
        p.attack_speed = as_total
        p.attack_cooldown = 1.0 / as_total if as_total > 0 else 1.0
        p.ability_mult = d.ability_mult
        p.max_mana = d.max_mana * m
        p.mana = min(p.mana, p.max_mana) if p.mana > 0 else p.max_mana
        p.mana_regen5 = d.mana_regen5 * m
        # Stat di combattimento dagli oggetti (AP = SpA degli oggetti + AP puro).
        p.ap = _b("sp_attack") + _b("ap")
        p.crit = max(0.0, min(1.0, _b("crit")))
        p.armor_pen_pct = max(0.0, _b("armor_pen_pct"))
        p.magic_pen_pct = max(0.0, _b("magic_pen_pct"))
        p.magic_pen_flat = max(0.0, _b("magic_pen_flat"))
        p.lifesteal = max(0.0, _b("lifesteal"))
        p.omnivamp = max(0.0, _b("omnivamp"))
        p.ability_haste = max(0.0, _b("ability_haste"))
        # Identita' innate (non dagli oggetti), con extra sommati dagli oggetti.
        p.tenacity = stat_combine_ten(d.tenacity, _b("tenacity"))
        p.hp_regen5 = d.hp_regen5
        p.flat_reduction = d.flat_reduction
        p.lethality = d.lethality + _b("lethality")
        p.lethality_physical = d.lethality_physical
        p.heal_power = d.heal_power + _b("heal_power")
        p.range_cls = d.range_cls
        p.range_val = d.range_val
        bonus_hp = p.item_bonus.get("hp", 0.0) + p.passive_bonus.get("hp", 0.0)
        p.max_hp = p.stats.hp + bonus_hp
        p.attack_damage = p.stats.attack
        if preserve_ratio and old_max > 0:
            p.hp = min(p.max_hp, old_hp / old_max * p.max_hp)
        elif heal_delta:
            p.hp = min(p.max_hp, old_hp + max(0.0, p.max_hp - old_max))
        else:
            p.hp = min(p.max_hp, old_hp)

    # --- richiamo ------------------------------------------------------------
    def _update_recall(self, dt: float) -> None:
        for p in self.world.pokemons():
            if not p.recalling:
                continue
            interrupted = (not p.alive or self._immobile(p)
                           or p.last_damaged_at > p.recall_start
                           or p.order in ("move", "attack", "attackmove"))
            if interrupted:
                p.recalling = False
            elif self.time >= p.recall_until:
                p.recalling = False
                p.pos = Vec2(p.spawn_pos.x, p.spawn_pos.y)
                p.hp = min(p.max_hp, p.hp + p.max_hp * config.RECALL_HEAL)
                p.stop()

    # --- oro / negozio -------------------------------------------------------
    def _update_gold(self, dt: float) -> None:
        # L'oro passivo matura solo a partire da 1:30 (vale per tutti).
        if self.time < config.GOLD_PASSIVE_START:
            return
        for p in self.world.pokemons():
            if p.alive:
                p.gold += config.GOLD_PASSIVE_PER_SEC * dt

    def _minion_gold(self, m: Minion) -> int:
        """Oro del minion. Il cannone cresce di +1/min fino al tetto; gli altri
        valgono il loro valore fisso."""
        if m.minion_type == "cannon":
            extra = int(self.time / 60.0) * config.CANNON_GOLD_PER_MIN
            return min(config.CANNON_GOLD_MAX, config.CANNON_GOLD_BASE + extra)
        return int(m.gold)

    def _award_gold(self, victim, killer) -> None:
        if isinstance(victim, Minion):
            # Oro solo a chi dà l'ultimo colpo (last-hit); kill da torre/altri
            # minion danno 0 (killer non è un Pokémon).
            if isinstance(killer, Pokemon):
                killer.gold += self._minion_gold(victim)
        elif isinstance(victim, Pokemon):
            self._award_kill(victim, killer)
        elif isinstance(victim, Structure):
            self._award_structure(victim, killer)

    def _award_structure(self, victim, killer) -> None:
        """Torre: 150 oro a tutta la squadra che l'ha distrutta, +100 a chi era
        vicino. Il nucleo non dà oro. Le placche residue (entro i 14 min) cadono
        alla distruzione, divise tra i vicini."""
        if isinstance(victim, Core):
            return
        team = 1 - victim.team   # la torre muore solo per mano della squadra avversaria
        for p in self.world.pokemons():
            if p.team != team:
                continue
            p.gold += config.TOWER_GOLD_TEAM
            if p.alive and p.pos.dist(victim.pos) <= config.OBJECTIVE_NEAR_RADIUS:
                p.gold += config.TOWER_GOLD_LOCAL
        # Placche ancora in piedi (burst che salta le soglie): cadono tutte ora.
        left = getattr(victim, "plates_left", 0)
        if left > 0 and self.time < config.PLATE_WINDOW:
            self._award_plates(victim, left)
            victim.plates_left = 0

    def _award_plates(self, tower, n: int) -> None:
        """Assegna `n` placche (120 oro l'una) divise tra i nemici vicini."""
        team = 1 - tower.team
        near = [p for p in self.world.pokemons()
                if p.team == team and p.alive
                and p.pos.dist(tower.pos) <= config.OBJECTIVE_NEAR_RADIUS]
        if not near:
            return                      # nessuno vicino: oro perso
        share = config.PLATE_GOLD * n / len(near)
        for p in near:
            p.gold += share

    def _update_plates(self, dt: float) -> None:
        """Le placche cadono man mano che la torre perde vita, nei primi 14 min.
        Una placca cade quando l'HP scende sotto max_hp × placche/(PLATE_COUNT+1)."""
        if self.time >= config.PLATE_WINDOW:
            return
        step = config.PLATE_COUNT + 1
        for s in self.world.structures():
            if isinstance(s, Core) or not s.alive:
                continue
            left = getattr(s, "plates_left", 0)
            if left <= 0 or s.max_hp <= 0:
                continue
            # Fa cadere tutte le placche le cui soglie sono state superate.
            while left > 0 and s.hp <= s.max_hp * left / step:
                self._award_plates(s, 1)
                left -= 1
            s.plates_left = left

    def _avg_player_gold(self) -> float:
        gs = [p.gold for p in self.world.pokemons()]
        return sum(gs) / len(gs) if gs else 0.0

    def _team_total_gold(self, team: int) -> float:
        return sum(p.gold for p in self.world.pokemons() if p.team == team)

    def _comeback_mult(self, team: int) -> float:
        """Taglie di recupero: gli obiettivi neutrali danno il doppio alla
        squadra indietro di oltre 3000 oro."""
        behind = self._team_total_gold(1 - team) - self._team_total_gold(team)
        return 2.0 if behind > config.COMEBACK_THRESHOLD else 1.0

    def _victim_bounty(self, victim) -> float:
        """Taglia per aver ucciso `victim`: base 300, su con la serie di
        uccisioni (max 600), giù con la serie di morti (min 150)."""
        bounty = float(config.KILL_BASE_BOUNTY)
        if victim.kill_streak >= 2:          # era in serie di uccisioni
            bounty *= 1.0 + config.KILL_STREAK_STEP * (victim.kill_streak - 1)
            bounty = min(bounty, config.BOUNTY_MAX)
        deaths = victim.death_streak + 1     # questa morte compresa
        if deaths >= 2:                      # in serie di morti
            bounty *= 1.0 - config.DEATH_STREAK_STEP * (deaths - 1)
            bounty = max(bounty, config.BOUNTY_MIN)
        return bounty

    def _award_kill(self, victim, killer) -> None:
        """Assegna oro per l'uccisione di un campione: taglia al killer (con
        prima uccisione e taglia sul vantaggio) e 50% agli assistenti. Se a
        uccidere è una torre/minion, la taglia va divisa tra gli assistenti;
        se non ce ne sono, si perde. Poi aggiorna le serie."""
        bounty = self._victim_bounty(victim)
        killer_is_champ = isinstance(killer, Pokemon) and killer.team != victim.team
        first_blood = not self._first_blood_done
        if first_blood:
            self._first_blood_done = True
            self.announcements.append((self.time, "Prima uccisione!"))

        # Assistenti: chi ha colpito la vittima negli ultimi ASSIST_WINDOW
        # secondi (escluso il killer), vivo e della squadra avversaria.
        dmg = getattr(victim, "_damagers", {})
        assisters = []
        for aid, t in list(dmg.items()):
            if self.time - t > config.ASSIST_WINDOW:
                continue
            if killer is not None and aid == getattr(killer, "id", None):
                continue
            a = self.world.get(aid)
            if isinstance(a, Pokemon) and a.alive and a.team != victim.team:
                assisters.append(a)
        setattr(victim, "_damagers", {})

        fb_assist = config.FIRST_BLOOD_ASSIST if first_blood else 0
        if killer_is_champ:
            gain = bounty
            if first_blood:
                gain += config.FIRST_BLOOD_BONUS
            avg = self._avg_player_gold()
            if victim.gold > avg:            # taglia sul vantaggio (shutdown)
                gain += min(config.SHUTDOWN_MAX,
                            config.SHUTDOWN_FACTOR * (victim.gold - avg))
            killer.gold += gain
            self._add_soul(killer, config.SOUL_PER_KILL)
            if assisters:                    # gli assistenti si dividono il 50%
                share = bounty * config.ASSIST_SHARE / len(assisters)
                for a in assisters:
                    a.gold += share + fb_assist
                    self._add_soul(a, config.SOUL_PER_ASSIST)
        elif assisters:
            # Uccisione da torre/minion: la taglia intera si divide tra gli assist.
            share = bounty / len(assisters)
            for a in assisters:
                a.gold += share + fb_assist
                self._add_soul(a, config.SOUL_PER_ASSIST)

        # Aggiorna le serie (la vittima perde la sua serie di uccisioni).
        victim.kill_streak = 0
        victim.death_streak += 1
        if killer_is_champ:
            killer.kill_streak += 1
            killer.death_streak = 0

    @staticmethod
    def _add_soul(p, n: int) -> None:
        if p.passive_id == "corpofunesto":
            p.soul_charges = min(config.SOUL_MAX, p.soul_charges + n)

    def _add_inversion(self, p, n: int = 5) -> None:
        """Passiva Inversione: cariche da colpo di spell. Tetto 50, che sale a
        100 durante il sovraccarico (stare dentro VerdeBufera)."""
        if getattr(p, "passive_id", "") != "inversione":
            return
        p.inversion_last_gain = self.time   # colpire tiene viva la finestra anti-decadimento
        cap = 100 if p.inversion_oc_until > self.time else 50
        if p.inversion_stacks < cap:
            p.inversion_stacks = min(cap, p.inversion_stacks + n)

    def shop_buy(self, unit, item_id: str) -> bool:
        if not isinstance(unit, Pokemon) or not unit.alive:
            return False
        if unit.pos.dist(unit.spawn_pos) > config.SHOP_RANGE:
            return False
        it = self.item_catalog.get(item_id)
        if it is None:
            return False
        price = self.item_catalog.effective_price(item_id, unit.items)
        if unit.gold < price:
            return False
        consumed = self.item_catalog.components_in(item_id, unit.items)
        if len(unit.items) - len(consumed) + 1 > ITEM_SLOTS:
            return False
        for c in consumed:
            unit.items.remove(c)
        unit.items.append(item_id)
        unit.gold -= price
        self._apply_items(unit)
        return True

    def shop_sell(self, unit, slot: int) -> bool:
        if not isinstance(unit, Pokemon) or not unit.alive:
            return False
        if unit.pos.dist(unit.spawn_pos) > config.SHOP_RANGE:
            return False
        if slot < 0 or slot >= len(unit.items):
            return False
        item_id = unit.items.pop(slot)
        unit.gold += self.item_catalog.sell_value(item_id)
        self._apply_items(unit)
        return True

    def _apply_items(self, unit) -> None:
        unit.item_bonus = self.item_catalog.total_bonus(unit.items)
        self._recompute_stats(unit, preserve_ratio=True)

    def _update_bot_shop(self, dt: float) -> None:
        """I bot comprano oggetti quando tornano in base con abbastanza oro."""
        for p in self.world.pokemons():
            if not p.alive or not p.is_bot:
                continue
            if p.pos.dist(p.spawn_pos) > config.SHOP_RANGE:
                continue
            st = self._ai.setdefault(p.id, {})
            st["shop_cd"] = st.get("shop_cd", 0.0) - dt
            if st["shop_cd"] <= 0.0:
                st["shop_cd"] = 1.5
                self._bot_buy(p)

    def _bot_buy(self, p) -> None:
        cat = self.item_catalog
        for target in cat.recommended_for(p.role):
            if target in p.items or cat.get(target) is None:
                continue
            price = cat.effective_price(target, p.items)
            slots_after = len(p.items) - len(cat.components_in(target, p.items)) + 1
            if p.gold >= price and slots_after <= ITEM_SLOTS:
                self.shop_buy(p, target)
                return
            # Altrimenti compra un componente mancante, se può permetterselo.
            for comp in cat.get(target).build_from:
                if comp not in p.items and len(p.items) < ITEM_SLOTS:
                    cd = cat.get(comp)
                    if cd is not None and p.gold >= cd.price:
                        self.shop_buy(p, comp)
                        return
            return  # non può avanzare su questo oggetto ora

    # --- rigenerazione -------------------------------------------------------
    def _update_regen(self, dt: float) -> None:
        """Cura rapida vicino alla propria base (fontana) e lieve rigen altrove."""
        for p in self.world.pokemons():
            if not p.alive or p.hp >= p.max_hp:
                continue
            if p.pos.dist(p.spawn_pos) <= 5.0:
                p.hp = min(p.max_hp, p.hp + p.max_hp * 0.25 * dt)   # ~25%/s
            else:
                p.hp = min(p.max_hp, p.hp + (p.max_hp * 0.015 + 2.0) * dt)

    # --- mosse: esecuzione ---------------------------------------------------
    def _update_casts(self, dt: float) -> None:
        for p in self.world.pokemons():
            cast = p.pending_cast
            p.pending_cast = None
            if cast is None or not p.alive or self._immobile(p) or p.fear_until > self.time:
                continue
            if p.submerged:          # sott'acqua non si lanciano altre mosse
                continue
            self._cast(p, cast[0], cast[1], cast[2])

    def _cast(self, p: Pokemon, slot: str, tx: float, ty: float) -> None:
        ms = p.moveset.get(slot)
        if ms is None or ms.chosen is None or not ms.ready:
            return
        mv = ms.chosen
        rank = ms.rank
        if p.aa_active:              # lanciare annulla un auto-attacco in windup
            p.aa_active = False
            p.attack_timer = 0.0
        if mv.charges > 0:           # Erboscivolata: consuma una carica (scatto)
            if ms.charges_cur < 0:
                ms.charges_cur = float(mv.charges)
            ms.charges_cur = max(0.0, ms.charges_cur - 1.0)
        ms.cooldown_remaining = mv.cooldown_at(rank) * ability_haste_factor(p.ability_haste)
        origin = Vec2(p.pos.x, p.pos.y)
        tgt = Vec2(tx, ty)
        to = tgt - origin
        dirv = to.normalized() if to.length() > 1e-6 else Vec2(1.0, 0.0)
        p.facing = direction_index(dirv.x, dirv.y)
        shape = mv.shape
        anim = {"projectile": "Shoot", "bubble": "Shoot",
                "cone": "Attack", "dash": "Attack", "bolt": "Shoot",
                "curse": "Shoot", "fan": "Shoot", "dashback": "Attack",
                "rain": "Shoot", "storm": "Shoot", "leap": "Attack"}.get(shape)
        if anim:
            self.fx_events.append({"eid": p.id, "anim": anim})
        # Gli eventi visivi aggiunti dai _cast_* qui sotto vengono "taggati" con lo
        # stile FX della mossa (campo "fx" nel JSON), così il client può disegnare
        # una forma dedicata e ricolorata invece del raggio/cerchio generico.
        _fx0 = len(self.fx_events)
        if shape == "projectile":
            self._cast_projectile(p, mv, rank, origin, dirv)
        elif shape == "bubble":
            self._cast_bubble(p, mv, rank, origin, dirv)
        elif shape == "cone":
            self._cast_cone(p, mv, rank, origin, dirv)
        elif shape == "area":
            self._cast_area(p, mv, rank, origin, tgt)
        elif shape == "dash":
            self._cast_dash(p, mv, rank, origin, tgt, dirv)
        elif shape == "sub":
            self._cast_sub(p, mv, rank, origin, tgt, dirv)
        elif shape == "bolt":
            self._cast_bolt(p, mv, rank, origin, tgt)
        elif shape == "blink":
            self._cast_blink(p, mv, rank, origin, tgt, dirv)
        elif shape == "curse":
            self._cast_curse(p, mv, rank, origin, tgt)
        elif shape == "fan":
            self._cast_fan(p, mv, rank, origin, dirv)
        elif shape == "dashback":
            self._cast_dashback(p, mv, rank, origin, tgt, dirv)
        elif shape == "rain":
            self._cast_rain(p, mv, rank, origin, tgt)
        elif shape == "storm":
            self._cast_storm(p, mv, rank, origin, tgt)
        elif shape == "leap":
            self._cast_leap(p, mv, rank, origin, tgt, dirv)
        elif shape == "buff":
            self._apply_support(p, mv, rank, origin)
            self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y),
                                   "mtype": mv.type, "radius": 1.0})
        if mv.fx:
            for ev in self.fx_events[_fx0:]:
                if "kind" in ev:
                    ev.setdefault("fx", mv.fx)

    def _cast_sub(self, p, mv, rank, origin, tgt, dirv):
        """SUB: si inabissa (non bersagliabile e inattaccabile) ma resta
        controllabile e si muove sott'acqua più in fretta. Riemerge a fine durata
        o ri-lanciando la R, con un'onda d'urto che fa danno attorno al punto
        raggiunto (stile Vladimir + Tham Kench)."""
        dur = float(mv.effects.get("untargetable", {}).get("duration", 3.0))
        p.submerged = True
        p.submerge_until = self.time + dur
        setattr(p, "_submerge_move", (mv, rank))
        self._apply_untargetable(p, dur + 0.05)
        self._apply_speed(p, 1.4, dur)   # più veloce sott'acqua, per riposizionarsi
        p.stop()                          # parte fermo: lo guida il giocatore
        self.fx_events.append({"kind": "dive", "c": (p.pos.x, p.pos.y),
                               "mtype": mv.type})

    # --- mosse della linea Gastly -------------------------------------------
    def _cast_bolt(self, p, mv, rank, origin, tgt):
        """Colpo ad aggancio automatico: prende il nemico più vicino al punto
        mirato entro gittata e lo colpisce subito (Velenoshock, Mangiasogni)."""
        want_sleep = "bonus_vs_sleep" in mv.effects   # Mangiasogni: preferisci i dormienti
        need_sleep = bool(mv.effects.get("requires_sleep"))  # colpisce SOLO i dormienti
        best, bk = None, 1e9
        for e in self._combat_hash.query_radius(origin.x, origin.y, mv.range + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild, Structure)):
                continue
            asleep = isinstance(e, Pokemon) and e.sleep_until > self.time
            if need_sleep and not asleep:
                continue   # Mangiasogni: niente danno se il bersaglio non dorme
            if origin.dist(e.pos) <= mv.range + getattr(e, "radius", 0.0):
                k = tgt.dist(e.pos)
                if want_sleep and asleep:
                    k -= 100.0   # i bersagli addormentati hanno priorità
                if k < bk:
                    best, bk = e, k
        if best is not None:
            self._hit(p, mv, rank, best)
            self.fx_events.append({"kind": "projectile", "a": (origin.x, origin.y),
                                   "b": (best.pos.x, best.pos.y), "mtype": mv.type})

    def _cast_blink(self, p, mv, rank, origin, tgt, dirv):
        if p.dashlock_until > self.time:   # Cucitombra: teletrasporti bloccati
            return
        """Spettrotuffo: teletrasporto attraverso i muri; la gittata cresce con le
        cariche di Corpofunesto; dopo `return_delay` torna al punto di partenza."""
        bonus = p.soul_charges * float(mv.effects.get("charge_range", 0.04))
        rng = mv.range + bonus
        to = tgt - origin
        dest = origin + dirv * min(to.length(), rng)
        dest = self._nearest_walkable(dest, origin)
        p.blink_return_pos = Vec2(origin.x, origin.y)
        p.blink_return_until = self.time + float(mv.effects.get("return_delay", 1.5))
        p.pos = dest
        p.stop()
        # Poof ai due capi + animazione Hop veloce (effetto teletrasporto).
        self.fx_events.append({"kind": "blink", "a": (origin.x, origin.y),
                               "b": (dest.x, dest.y), "mtype": mv.type})
        self.fx_events.append({"eid": p.id, "anim": "Hop", "anim_speed": 2.5})

    def _cast_curse(self, p, mv, rank, origin, tgt):
        """Maledizione: marchia un nemico; dopo `delay` subisce un danno alto che
        cresce con le cariche di Corpofunesto."""
        best, bk = None, 1e9
        for e in self._combat_hash.query_radius(origin.x, origin.y, mv.range + 1.0):
            if e.team == p.team or not getattr(e, "alive", False) or not isinstance(e, Pokemon):
                continue
            if origin.dist(e.pos) <= mv.range:
                k = tgt.dist(e.pos)
                if k < bk:
                    best, bk = e, k
        if best is None:
            return
        base = mv.power_at(rank) + mv.ratio * p.eff_sp_attack()
        best.curse_power = base + p.soul_charges * float(mv.effects.get("charge_power", 2.0))
        best.curse_until = self.time + float(mv.effects.get("delay", 3.0))
        best.curse_src = p.id
        self.fx_events.append({"kind": "buff", "c": (best.pos.x, best.pos.y),
                               "mtype": mv.type, "radius": 1.2})

    def _update_blink_return(self, dt: float) -> None:
        for p in self.world.pokemons():
            if p.blink_return_pos is not None and p.blink_return_until > 0.0 \
                    and self.time >= p.blink_return_until:
                if p.alive:
                    src = Vec2(p.pos.x, p.pos.y)
                    p.pos = Vec2(p.blink_return_pos.x, p.blink_return_pos.y)
                    p.stop()
                    self.fx_events.append({"kind": "blink", "a": (src.x, src.y),
                                           "b": (p.pos.x, p.pos.y), "mtype": "Ghost"})
                    self.fx_events.append({"eid": p.id, "anim": "Hop", "anim_speed": 2.5})
                p.blink_return_until = -1.0
                p.blink_return_pos = None

    def _update_curses(self, dt: float) -> None:
        for p in self.world.pokemons():
            if p.curse_until > 0.0 and self.time >= p.curse_until:
                src = self.world.get(p.curse_src) if p.curse_src is not None else None
                if p.alive and src is not None:
                    dmg = self._mitigate_hit(src, p, p.curse_power, magic=True)
                    self._deal_damage(src, p, dmg)
                    self._vamp(src, dmg, physical=False)
                    self.fx_events.append({"kind": "area", "c": (p.pos.x, p.pos.y),
                                           "radius": 1.6, "mtype": "Ghost"})
                p.curse_until = -1.0
                p.curse_src = None
                p.curse_power = 0.0

    # --- mosse della linea Rowlet -------------------------------------------
    def _cast_fan(self, p, mv, rank, origin, dirv):
        """Foglielama: ventaglio di 3 proiettili."""
        spread = math.radians(float(mv.d.get("spread", 16)))
        base = math.atan2(dirv.y, dirv.x)
        for a in (base - spread, base, base + spread):
            self._cast_projectile(p, mv, rank, origin, Vec2(math.cos(a), math.sin(a)))

    def _cast_dashback(self, p, mv, rank, origin, tgt, dirv):
        """Retromarcia: scatto verso il bersaglio; se colpisce, rimbalza indietro."""
        if p.dashlock_until > self.time:
            return
        dist = min((tgt - origin).length(), mv.range)
        dest = self._clamp_to_wall(origin, origin + dirv * dist)
        hit_any = False
        for e in self._combat_hash.query_radius((origin.x + dest.x) / 2,
                                                (origin.y + dest.y) / 2, dist + mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if self._point_seg_dist(e.pos, origin, dest) <= mv.radius + getattr(e, "radius", 0.0):
                self._hit(p, mv, rank, e)
                hit_any = True
        p.pos = dest
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (dest.x, dest.y), "mtype": mv.type})
        if hit_any:   # rimbalzo all'indietro (direzione opposta)
            back = self._clamp_to_wall(dest, dest - dirv * float(mv.d.get("recoil", mv.range)))
            self.fx_events.append({"kind": "dash", "a": (dest.x, dest.y),
                                   "b": (back.x, back.y), "mtype": mv.type})
            p.pos = back
        p.stop()

    def _cast_rain(self, p, mv, rank, origin, tgt):
        """Pioggia di Frecce: dopo un ritardo, l'area colpisce e rallenta a intervalli."""
        to = tgt - origin
        center = origin + to.normalized() * min(to.length(), mv.range) if to.length() > 1e-6 else Vec2(tgt.x, tgt.y)
        delay = float(mv.effects.get("delay", 1.0))
        self.area_effects.append({
            "center": Vec2(center.x, center.y), "radius": mv.radius,
            "start": self.time + delay, "end": self.time + delay + float(mv.effects.get("duration", 3.0)),
            "next": self.time + delay, "interval": 0.5,
            "caster_id": p.id, "mv": mv, "rank": rank, "mtype": mv.type, "fx": mv.fx})
        self.fx_events.append({"kind": "area", "c": (center.x, center.y),
                               "radius": mv.radius, "mtype": mv.type})

    def _cast_storm(self, p, mv, rank, origin, tgt):
        """VerdeBufera: zona persistente che pulsa danni a intervalli. Chi la
        lancia, restando dentro, accumula cariche extra di Inversione
        (sovraccarico: il tetto sale da 50 a 100)."""
        to = tgt - origin
        center = (origin + to.normalized() * min(to.length(), mv.range)
                  if to.length() > 1e-6 else Vec2(tgt.x, tgt.y))
        delay = float(mv.effects.get("delay", 0.0))
        self.area_effects.append({
            "center": Vec2(center.x, center.y), "radius": mv.radius,
            "start": self.time + delay,
            "end": self.time + delay + float(mv.effects.get("duration", 4.0)),
            "next": self.time + delay,
            "interval": float(mv.effects.get("interval", 0.75)),
            "caster_id": p.id, "mv": mv, "rank": rank, "mtype": mv.type,
            "fx": "", "inversion_owner": True})
        # Zona visibile fin dal lancio (fx "" così resta un evento "zone", non uno stile).
        self.fx_events.append({"kind": "zone", "c": (center.x, center.y),
                               "radius": mv.radius, "mtype": mv.type, "fx": ""})

    def _cast_leap(self, p, mv, rank, origin, tgt, dirv):
        """VastoImpatto: Serperior salta e, atterrando, infligge ingenti danni
        nell'area del punto d'arrivo (lo slow è negli effects della mossa)."""
        to = tgt - origin
        dist = min(to.length(), mv.range)
        dest = self._nearest_walkable(origin + dirv * dist, origin)
        p.pos = dest
        p.stop()
        for e in self._combat_hash.query_radius(dest.x, dest.y, mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if dest.dist(e.pos) <= mv.radius + getattr(e, "radius", 0.0):
                self._hit(p, mv, rank, e)
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (dest.x, dest.y), "mtype": mv.type})
        self.fx_events.append({"kind": "area", "c": (dest.x, dest.y),
                               "radius": mv.radius, "mtype": mv.type})

    def _update_area_effects(self, dt: float) -> None:
        alive = []
        for ae in self.area_effects:
            if self.time >= ae["end"]:
                continue
            if self.time >= ae["start"] and self.time >= ae["next"]:
                ae["next"] = self.time + ae["interval"]
                caster = self.world.get(ae["caster_id"])
                c = ae["center"]
                if caster is not None:
                    # VerdeBufera: se chi l'ha lanciata è dentro la zona, va in
                    # sovraccarico (tetto 100) e accumula cariche d'Inversione.
                    if (ae.get("inversion_owner")
                            and c.dist(caster.pos) <= ae["radius"] + getattr(caster, "radius", 0.0)):
                        caster.inversion_oc_until = self.time + ae["interval"] + 0.25
                        self._add_inversion(caster, int(ae["mv"].effects.get("overcharge", 5)))
                    for e in self._combat_hash.query_radius(c.x, c.y, ae["radius"] + 1.0):
                        if e.team == caster.team or not getattr(e, "alive", False):
                            continue
                        if c.dist(e.pos) <= ae["radius"] + getattr(e, "radius", 0.0):
                            self._hit(caster, ae["mv"], ae["rank"], e)
                if ae.get("inversion_owner"):
                    # VerdeBufera: ripulsa la zona intera a ogni tick (campo animato continuo).
                    self.fx_events.append({"kind": "zone", "c": (c.x, c.y),
                                           "radius": ae["radius"], "mtype": ae["mtype"], "fx": ""})
                else:
                    self.fx_events.append({"kind": "area", "c": (c.x, c.y),
                                           "radius": ae["radius"] * 0.5, "mtype": ae["mtype"],
                                           "fx": ae.get("fx", "")})
            alive.append(ae)
        self.area_effects = alive

    def _is_hidden(self, p) -> bool:
        """Nascosto ai nemici: in un cespuglio o non visibile alla squadra avversaria."""
        tx, ty = int(p.pos.x), int(p.pos.y)
        if self.world.grid.tile_at(tx, ty) == TILE_BUSH:
            return True
        return not self.vision.is_enemy_visible(1 - p.team, p.id)

    def _auto_reach(self, u) -> float:
        """Gittata dell'auto-attacco (passiva Distacco: molto più larga se nascosti)."""
        r = u.attack_range
        if isinstance(u, Pokemon) and u.passive_id == "distacco" and self._is_hidden(u):
            r += config.DISTACCO_RANGE_BONUS
        return r

    def _nearest_walkable(self, dest, fallback):
        if self.world.grid.is_walkable_point(dest.x, dest.y):
            return dest
        d = fallback - dest
        steps = int(d.length() * 4) + 1
        for i in range(1, steps + 1):
            pt = dest + d * (i / steps)
            if self.world.grid.is_walkable_point(pt.x, pt.y):
                return pt
        return Vec2(fallback.x, fallback.y)

    def _update_submerge(self, dt: float) -> None:
        """Gestisce lo stato SUB: riemersione a tempo o su ri-lancio della R."""
        for p in self.world.pokemons():
            if not p.submerged:
                continue
            # Ri-premere la R mentre si è immersi fa riemergere subito.
            early = p.pending_cast is not None and p.pending_cast[0] == "R"
            if early:
                p.pending_cast = None
            if not p.alive:
                p.submerged = False
                p.untargetable_until = self.time
                setattr(p, "_submerge_move", None)
                continue
            if early or self.time >= p.submerge_until:
                self._emerge(p)

    def _emerge(self, p) -> None:
        p.submerged = False
        p.untargetable_until = self.time   # torna bersagliabile all'istante
        data = getattr(p, "_submerge_move", None)
        setattr(p, "_submerge_move", None)
        if data is None:
            return
        mv, rank = data
        center = Vec2(p.pos.x, p.pos.y)
        for e in self._combat_hash.query_radius(center.x, center.y, mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if center.dist(e.pos) <= mv.radius + getattr(e, "radius", 0.0):
                self._hit(p, mv, rank, e)   # onda d'urto in riemersione
        p.stop()
        self.fx_events.append({"kind": "area", "c": (center.x, center.y),
                               "radius": mv.radius, "mtype": mv.type})

    def _cast_bubble(self, p, mv, rank, origin, dirv):
        """Idropulsar: una bolla d'acqua che VIAGGIA (più un getto alla bocca)."""
        self.projectiles.append({
            "pos": Vec2(origin.x, origin.y), "dir": Vec2(dirv.x, dirv.y),
            "speed": mv.speed, "left": mv.range, "radius": mv.radius,
            "team": p.team, "caster_id": p.id, "mv": mv, "rank": rank, "mtype": mv.type})
        muzzle = origin + dirv * 1.3
        self.fx_events.append({"kind": "projectile", "a": (origin.x, origin.y),
                               "b": (muzzle.x, muzzle.y), "mtype": mv.type})

    def _update_projectiles(self, dt: float) -> None:
        alive = []
        for pr in self.projectiles:
            step = pr["speed"] * dt
            pr["pos"] = pr["pos"] + pr["dir"] * step
            pr["left"] -= step
            if not self.world.grid.is_walkable_point(pr["pos"].x, pr["pos"].y):
                continue   # colpisce un muro: svanisce
            hit = None
            for e in self._combat_hash.query_radius(pr["pos"].x, pr["pos"].y, pr["radius"] + 1.0):
                if e.team == pr["team"] or not getattr(e, "alive", False):
                    continue
                if not isinstance(e, (Pokemon, Minion, Structure, Wild)):
                    continue
                if pr["pos"].dist(e.pos) <= pr["radius"] + getattr(e, "radius", 0.0):
                    hit = e
                    break
            if hit is not None:
                caster = self.world.get(pr["caster_id"])
                if caster is not None:
                    self._hit(caster, pr["mv"], pr["rank"], hit)
                self.fx_events.append({"kind": "area", "c": (pr["pos"].x, pr["pos"].y),
                                       "radius": pr["radius"], "mtype": pr["mtype"]})
                continue   # bolla consumata
            if pr["left"] > 0:
                alive.append(pr)
        self.projectiles = alive

    def _cast_projectile(self, p, mv, rank, origin, dirv):
        best, best_proj = None, mv.range + 1.0
        mid = origin + dirv * (mv.range * 0.5)
        for e in self._combat_hash.query_radius(mid.x, mid.y, mv.range + 2.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            rel = e.pos - origin
            proj = rel.x * dirv.x + rel.y * dirv.y
            if proj < 0 or proj > mv.range:
                continue
            perp = abs(rel.x * (-dirv.y) + rel.y * dirv.x)
            if perp <= mv.radius + getattr(e, "radius", 0.0):
                if not mv.wall_pierce and not self.world.grid.line_of_sight(
                        origin.x, origin.y, e.pos.x, e.pos.y):
                    continue
                if proj < best_proj:
                    best_proj, best = proj, e
        end = origin + dirv * (best_proj if best else mv.range)
        if best is not None:
            self._hit(p, mv, rank, best)
        self.fx_events.append({"kind": "projectile", "a": (origin.x, origin.y),
                               "b": (end.x, end.y), "mtype": mv.type})

    def _cast_cone(self, p, mv, rank, origin, dirv):
        half = math.radians(mv.angle)
        for e in self._combat_hash.query_radius(origin.x, origin.y, mv.range + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            rel = e.pos - origin
            d = rel.length()
            if d > mv.range + getattr(e, "radius", 0.0) or d < 1e-6:
                if d >= 1e-6:
                    continue
            if d >= 1e-6:
                cosang = (rel.x * dirv.x + rel.y * dirv.y) / d
                if math.acos(max(-1.0, min(1.0, cosang))) > half:
                    continue
            self._hit(p, mv, rank, e)
        self.fx_events.append({"kind": "cone", "o": (origin.x, origin.y),
                               "dir": (dirv.x, dirv.y), "range": mv.range,
                               "angle": mv.angle, "mtype": mv.type})

    def _cast_area(self, p, mv, rank, origin, tgt):
        to = tgt - origin
        d = to.length()
        if mv.target == "self" or mv.range <= 0:
            center = origin
        elif d > mv.range:
            center = origin + to.normalized() * mv.range
        else:
            center = tgt
        for e in self._combat_hash.query_radius(center.x, center.y, mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if center.dist(e.pos) <= mv.radius + getattr(e, "radius", 0.0):
                self._hit(p, mv, rank, e)
        self._apply_support(p, mv, rank, center)
        self.fx_events.append({"kind": "area", "c": (center.x, center.y),
                               "radius": mv.radius, "mtype": mv.type})

    def _cast_dash(self, p, mv, rank, origin, tgt, dirv):
        if p.dashlock_until > self.time:   # Cucitombra: scatti bloccati
            return
        to = tgt - origin
        dist = min(to.length(), mv.range)
        dest = origin + dirv * dist
        if not mv.wall_pierce:
            dest = self._clamp_to_wall(origin, dest)
        # Colpisce i nemici lungo il tragitto.
        hit_any = False
        for e in self._combat_hash.query_radius((origin.x + dest.x) / 2,
                                                (origin.y + dest.y) / 2,
                                                dist + mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if self._point_seg_dist(e.pos, origin, dest) <= mv.radius + getattr(e, "radius", 0.0):
                self._hit(p, mv, rank, e)
                hit_any = True
        # Erboscivolata: passare attraverso un nemico rende subito una carica.
        if hit_any and mv.refund_on_hit and mv.charges > 0:
            ms = p.moveset.get(mv.slot)
            if ms is not None:
                if ms.charges_cur < 0:
                    ms.charges_cur = float(mv.charges)
                ms.charges_cur = min(float(mv.charges), ms.charges_cur + 1.0)
        p.pos = dest
        p.stop()
        self._apply_support(p, mv, rank, dest)
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (dest.x, dest.y), "mtype": mv.type})

    def _clamp_to_wall(self, origin, dest):
        d = dest - origin
        dist = d.length()
        if dist < 1e-6:
            return dest
        steps = int(dist * 4) + 1
        last = origin
        for i in range(1, steps + 1):
            t = i / steps
            pt = origin + d * t
            if not self.world.grid.is_walkable_point(pt.x, pt.y):
                return last
            last = pt
        return dest

    @staticmethod
    def _point_seg_dist(pt, a, b):
        ab = b - a
        l2 = ab.length_sq()
        if l2 < 1e-9:
            return pt.dist(a)
        t = max(0.0, min(1.0, ((pt.x - a.x) * ab.x + (pt.y - a.y) * ab.y) / l2))
        proj = Vec2(a.x + ab.x * t, a.y + ab.y * t)
        return pt.dist(proj)

    def _hit(self, caster, mv, rank, target) -> None:
        # Bersaglio non bersagliabile (es. SUB sott'acqua): niente danno né CC.
        if isinstance(target, Pokemon) and target.untargetable_until > self.time:
            return
        fx = mv.effects
        power = mv.power_at(rank)
        if power > 0:
            # Danno abilita' = (base + ratio × stat offensiva). Le speciali usano
            # l'AP (eff_sp_attack) e poi il moltiplicatore SpA (ability_mult); le
            # fisiche usano l'AD. Sopra: STAB ×1,15, efficacia dei tipi compressa
            # (×0,6..×1,5) e meteo. La mitigazione (con penetrazione e riduzione
            # fissa) ed eventuale critico sono in _mitigate_hit.
            magic = mv.category == "special"
            raw = power + mv.ratio * (caster.eff_sp_attack() if magic
                                      else caster.eff_attack())
            if magic and isinstance(caster, Pokemon):
                raw *= caster.ability_mult
            eff = (self.types.moba_multiplier(mv.type, target.types)
                   if isinstance(target, Pokemon) else 1.0)
            has_plate = (isinstance(caster, Pokemon) and caster.judgment_until > self.time
                         and mv.type == caster.judgment_plate)
            stab = STAB_MULT if (mv.type in caster.types or has_plate) else 1.0
            raw *= eff * stab * self.jungle.weather_damage_mult(mv.type)
            # Bonus contro bersagli con stati alterati (Sciagura) o addormentati (Mangiasogni).
            if isinstance(target, Pokemon):
                if "bonus_vs_status" in fx and self._has_status(target):
                    raw *= float(fx["bonus_vs_status"])
                if "bonus_vs_sleep" in fx and target.sleep_until > self.time:
                    raw *= float(fx["bonus_vs_sleep"])
                if "bonus_vs_attacking" in fx and target.aa_active:   # Sbigoattacco
                    raw *= float(fx["bonus_vs_attacking"])
            bat = fx.get("bonus_if_ally_type")   # Erbapatto: +% con un alleato Acqua/Fuoco
            if bat and isinstance(caster, Pokemon):
                need = set(bat.get("types", []))
                if any(a is not caster and a.team == caster.team and a.alive
                       and need & set(a.types) for a in self.world.pokemons()):
                    raw *= float(bat.get("mult", 1.05))
            crit_bonus = HIGH_CRIT_CHANCE if mv.d.get("high_crit") else 0.0
            dmg = self._mitigate_hit(caster, target, raw, magic=magic,
                                     crit_bonus=crit_bonus)
            self._deal_damage(caster, target, dmg)
            self._vamp(caster, dmg, physical=not magic)
            if "heal_self_ratio" in fx and isinstance(caster, Pokemon):  # Mangiasogni
                caster.hp = min(caster.max_hp, caster.hp + dmg * float(fx["heal_self_ratio"]))
        # Effetti di controllo/debuff sui nemici colpiti.
        if isinstance(target, Pokemon) and target.alive:
            slow = fx.get("slow")
            if slow:
                self._apply_slow(target, float(slow.get("mult", 0.6)),
                                 float(slow.get("duration", 1.0)))
            cc = fx.get("stun") or fx.get("freeze")
            if cc:
                self._apply_stun(target, float(cc.get("duration", 1.0)))
            cf = fx.get("confuse")
            if cf:
                self._apply_confuse(target, float(cf.get("duration", 1.0)))
            dd = fx.get("def_debuff")
            if dd:
                self._apply_def_debuff(target, float(dd.get("amount", 0)),
                                       float(dd.get("duration", 3.0)),
                                       float(dd.get("mult", 1.0)))
            sd = fx.get("spdef_debuff")
            if sd:
                self._apply_spdef_debuff(target, float(sd.get("amount", 20)),
                                         float(sd.get("duration", 2.0)))
            rt = fx.get("root")
            if rt:
                self._apply_root(target, float(rt.get("duration", 1.0)))
            sl = fx.get("sleep")
            if sl:
                self._apply_sleep(target, float(sl.get("duration", 1.5)),
                                  float(sl.get("delay", 0.0)))
            po = fx.get("poison")
            if po:
                # Laccioerboso: il danno nel tempo può scalare sugli HP max del bersaglio.
                dps = float(po.get("dps", 0))
                hp_frac = float(po.get("hp_frac", 0.0))
                if hp_frac > 0.0:
                    dps += target.max_hp * hp_frac
                self._apply_poison(target, caster, dps,
                                   float(po.get("duration", 2.0)))
            fe = fx.get("fear")
            if fe and isinstance(caster, (Pokemon, Minion, Structure)):
                self._apply_fear(target, caster.pos, float(fe.get("duration", 1.0)))
            dl = fx.get("dashlock")
            if dl:
                self._apply_stun(target, float(dl.get("stun", 0.6)))
                self._apply_dashlock(target, float(dl.get("duration", 2.5)))
            ad = fx.get("atk_debuff")
            if ad:
                self._apply_atk_debuff(target, float(ad.get("amount", 20)),
                                       float(ad.get("duration", 3.0)))
        # Passiva Inversione: ogni spell a segno su un Pokémon nemico dà cariche
        # (non sui minion né sulle strutture).
        if (isinstance(caster, Pokemon) and isinstance(target, Pokemon)
                and target.team != caster.team):
            self._add_inversion(caster)

    def _apply_support(self, caster, mv, rank, center) -> None:
        """Effetti su sé/alleati: cura, scudo, buff attacco/velocità."""
        eff = mv.effects
        if not eff:
            return
        if mv.target == "ally":
            targets = [a for a in self._combat_hash.query_radius(center.x, center.y, mv.radius + 1.0)
                       if isinstance(a, Pokemon) and a.team == caster.team and a.alive
                       and center.dist(a.pos) <= mv.radius + a.radius]
            if caster not in targets:
                targets.append(caster)
        else:
            targets = [caster]
        # Potere cure/scudi del lanciatore: cure e scudi × heal_power.
        hp_power = caster.heal_power if isinstance(caster, Pokemon) else 1.0
        heal = eff.get("heal")
        if heal:
            amt = self._rank_val(heal, rank) * hp_power
            if eff.get("weather_heal"):   # Sintesi: x2 col Sole, dimezzata con la Pioggia
                w = self.jungle.weather
                amt *= 2.0 if w == "sun" else (0.5 if w == "rain" else 1.0)
            for a in targets:
                a.hp = min(a.max_hp, a.hp + amt)
        if "heal_self_ratio" in eff:
            caster.hp = min(caster.max_hp,
                            caster.hp + mv.power_at(rank) * float(eff["heal_self_ratio"]) * hp_power)
        sh = eff.get("shield")
        if sh:
            amt = self._rank_val(sh.get("amount", []), rank) * hp_power
            dur = float(sh.get("duration", 3.0))
            for a in targets:
                self._apply_shield(a, amt, dur)
        atk = eff.get("atk")
        if atk:
            self._apply_atk(caster, float(atk.get("mult", 1.3)), float(atk.get("duration", 5.0)))
        spd = eff.get("speed")
        if spd:
            for a in targets:
                self._apply_speed(a, float(spd.get("mult", 1.2)), float(spd.get("duration", 3.0)))
        ram = eff.get("rampage")
        if ram:   # Oltraggio: inarrestabile per qualche secondo
            self._apply_rampage(caster, float(ram.get("duration", 4.0)))

    @staticmethod
    def _rank_val(arr, rank):
        if not arr:
            return 0.0
        return float(arr[min(max(1, rank), len(arr)) - 1])

    # --- stati ---------------------------------------------------------------
    def _cc_immune(self, p):
        return getattr(p, "cc_immune_until", -1) > self.time

    def _tenacity_dur(self, p, dur):
        """Tenacia: accorcia la durata dei CC (durata × (1 − tenacia))."""
        ten = getattr(p, "tenacity", 0.0) if isinstance(p, Pokemon) else 0.0
        return dur * (1.0 - ten)

    def _apply_slow(self, p, mult, dur):
        if self._cc_immune(p):
            return
        dur = self._tenacity_dur(p, dur)
        p.slow_mult = min(p.slow_mult, mult) if self.time <= p.slow_until else mult
        p.slow_until = max(p.slow_until, self.time + dur)

    def _apply_stun(self, p, dur):
        if self._cc_immune(p):
            return
        dur = self._tenacity_dur(p, dur)
        p.stun_until = max(p.stun_until, self.time + dur)

    def _apply_confuse(self, p, dur):
        if self._cc_immune(p):
            return
        dur = self._tenacity_dur(p, dur)
        p.confuse_until = max(p.confuse_until, self.time + dur)

    def _apply_def_debuff(self, p, amt, dur, mult=1.0):
        p.def_debuff_amt = amt
        p.def_debuff_mult = mult
        p.def_debuff_until = max(p.def_debuff_until, self.time + dur)

    def _apply_spdef_debuff(self, p, amt, dur):
        p.spdef_debuff_amt = amt
        p.spdef_debuff_until = max(p.spdef_debuff_until, self.time + dur)

    def _apply_atk_debuff(self, p, amt, dur):   # Danzadipiume: -Attacco
        p.atk_debuff_amt = amt
        p.atk_debuff_until = max(p.atk_debuff_until, self.time + dur)

    def _apply_root(self, p, dur):          # paralisi (rooted): fermo ma può agire
        if self._cc_immune(p):
            return
        dur = self._tenacity_dur(p, dur)
        p.root_until = max(p.root_until, self.time + dur)

    def _apply_sleep(self, p, dur, delay=0.0):
        if self._cc_immune(p):
            return
        dur = self._tenacity_dur(p, dur)
        if delay > 0.0:
            p.sleep_arm_at = self.time + delay   # Ipnosi: dorme dopo il ritardo
            p.sleep_arm_dur = dur
        else:
            p.sleep_until = max(p.sleep_until, self.time + dur)

    def _apply_poison(self, p, src, dps, dur):
        p.poison_dps = max(p.poison_dps, dps)
        p.poison_until = max(p.poison_until, self.time + dur)
        p.poison_src = src.id if src is not None else None

    def _apply_fear(self, p, src_pos, dur):     # spavento: fugge dalla fonte
        if self._cc_immune(p):
            return
        dur = self._tenacity_dur(p, dur)
        p.fear_until = max(p.fear_until, self.time + dur)
        p.fear_src = Vec2(src_pos.x, src_pos.y)

    def _apply_dashlock(self, p, dur):          # Cucitombra: niente scatti/tp
        p.dashlock_until = max(p.dashlock_until, self.time + dur)

    def _has_status(self, p) -> bool:
        """Vero se il Pokémon ha un qualunque stato alterato (per Sciagura)."""
        t = self.time
        return (p.slow_until > t or p.stun_until > t or p.sleep_until > t
                or p.root_until > t or p.poison_until > t or p.confuse_until > t
                or p.def_debuff_until > t or p.spdef_debuff_until > t)

    def _apply_untargetable(self, p, dur):
        p.untargetable_until = max(p.untargetable_until, self.time + dur)

    def _apply_rampage(self, p, dur):
        p.rampage_until = self.time + dur
        p.cc_immune_until = self.time + dur   # Oltraggio = inarrestabile (immune ai CC)

    def _apply_shield(self, p, amt, dur):
        active = p.shield if p.shield_until > self.time else 0.0
        p.shield = max(active, amt)
        p.shield_until = self.time + dur

    def _apply_atk(self, p, mult, dur):
        p.atk_mult = mult
        p.atk_until = self.time + dur

    def _apply_speed(self, p, mult, dur):
        p.speed_mult = mult
        p.speed_until = self.time + dur

    def _immobile(self, p) -> bool:
        """Non può né muoversi né agire: stun/congelamento o sonno."""
        return p.stun_until > self.time or p.sleep_until > self.time

    def _flee(self, p, dt) -> None:
        """Spavento: corre via dalla fonte (rallentato, non controllabile)."""
        p.target_id = None
        p.aa_active = False
        away = p.pos - p.fear_src
        if away.length() < 1e-6:
            away = Vec2(1.0, 0.0)
        self._move_towards(p, p.pos + away.normalized() * 3.0, dt, use_astar=False)

    def _update_status(self, dt: float) -> None:
        for p in self.world.pokemons():
            # Le ricariche (cooldown e cariche) scorrono anche da morti: al respawn
            # le mosse sono avanti/pronte come in un MOBA, non congelate.
            for ms in p.moveset.values():
                if ms.cooldown_remaining > 0.0:
                    ms.cooldown_remaining = max(0.0, ms.cooldown_remaining - dt)
                mv = ms.chosen
                if mv is not None and mv.charges > 0:
                    if ms.charges_cur < 0:
                        ms.charges_cur = float(mv.charges)
                    elif ms.charges_cur < mv.charges and mv.charge_time > 0.0:
                        ms.charges_cur = min(float(mv.charges),
                                             ms.charges_cur + dt / mv.charge_time)
            if not p.alive:
                continue
            if self.time > p.slow_until:
                p.slow_mult = 1.0
            if self.time > p.speed_until:
                p.speed_mult = 1.0
            if self.time > p.atk_until:
                p.atk_mult = 1.0
            if self.time > p.shield_until:
                p.shield = 0.0
            p.def_debuff_active = p.def_debuff_until > self.time
            p.spdef_debuff_active = p.spdef_debuff_until > self.time
            p.atk_debuff_active = p.atk_debuff_until > self.time
            # Sonno ritardato (Ipnosi): scatta dopo il ritardo.
            if p.sleep_arm_at >= 0.0 and self.time >= p.sleep_arm_at:
                if not self._cc_immune(p):
                    p.sleep_until = self.time + p.sleep_arm_dur
                p.sleep_arm_at = -1.0
            # Veleno: danno nel tempo (attribuito alla sorgente, per le uccisioni).
            if p.poison_until > self.time and p.poison_dps > 0.0:
                src = self.world.get(p.poison_src) if p.poison_src is not None else None
                if src is not None and src.alive:
                    self._deal_damage(src, p, p.poison_dps * dt)
            # Passiva Inversione: senza colpi per 10s le cariche calano di 2 ogni 0.75s.
            if p.passive_id == "inversione":
                if p.inversion_stacks > 0 and self.time - p.inversion_last_gain >= 10.0:
                    if self.time >= p.inversion_decay_next:
                        p.inversion_stacks = max(0, p.inversion_stacks - 2)
                        p.inversion_decay_next = self.time + 0.75
                else:
                    p.inversion_decay_next = self.time + 0.75   # finestra ferma finché combatte
            immobile = self._immobile(p)
            rooted = p.root_until > self.time   # paralisi: fermo ma può agire
            p.cc_active = (p.slow_until > self.time or immobile or rooted
                           or p.confuse_until > self.time)
            p.speed = (p.move_speed_base * p.slow_mult * p.speed_mult
                       * self.jungle.terrain_speed_mult(p))
            if p.fear_until > self.time:
                p.speed *= 0.5   # spavento: fuga rallentata del 50%
                p.cc_active = True
            if immobile or rooted:
                p.speed = 0.0   # immobilizzato (stun/sonno) o paralizzato (rooted)

    # --- evoluzioni / scelte / punti (bot) -----------------------------------
    def _update_evolution(self, dt: float) -> None:
        for p in self.world.pokemons():
            if not p.alive:
                continue
            if evolution.check_evolution(p):
                self._recompute_stats(p, heal_delta=True)
                self.announcements.append((self.time, f"{p.name} si è evoluto!"))
            # Offerta della scelta scaglionata: Q@5, W@6, E@7, R@8.
            for slot, lvl in SLOT_UPGRADE_LEVEL.items():
                if p.level >= lvl and slot not in p.offered_slots:
                    ms = p.moveset.get(slot)
                    ready = ms and ms.upgrades and (
                        slot == "R" or (ms.base is not None and ms.chosen is ms.base))
                    if ready:
                        p.offered_slots.add(slot)
                        p.pending_choices.append(slot)
            if p.is_bot:
                for slot in list(p.pending_choices):
                    ms = p.moveset.get(slot)
                    if ms and ms.upgrades:
                        evolution.apply_choice(p, slot, random.randrange(len(ms.upgrades)))
                self._bot_spend_points(p)

    def _bot_spend_points(self, p) -> None:
        for _ in range(16):
            if skills.available_points(p) <= 0:
                break
            for slot in ("R", "Q", "E", "W"):
                if skills.can_rank_up(p, slot):
                    skills.rank_up(p, slot)
                    break
            else:
                break

    def _bot_try_cast(self, p, target) -> None:
        if p.pending_cast is not None:
            return
        for slot in ("R", "Q", "W", "E"):
            ms = p.moveset.get(slot)
            if ms and ms.ready and ms.chosen and ms.chosen.power_at(ms.rank) > 0:
                reach = max(2.5, ms.chosen.range)
                if p.pos.dist(target.pos) <= reach:
                    p.pending_cast = (slot, target.pos.x, target.pos.y)
                    return

    # --- IA del jungler ------------------------------------------------------
    def assign_junglers(self):
        """Designa un bot per squadra come jungler (va in giungla a farmare)."""
        for team in (0, 1):
            bots = [p for p in self.world.pokemons() if p.team == team and p.is_bot]
            if bots:
                bots[len(bots) // 2].is_jungler = True

    def _ai_jungler(self, p, dt):
        if self._immobile(p):
            p.stop()
            return
        if p.hp < p.max_hp * BOT_RETREAT_HP:
            p.target_id = None
            self._move_towards(p, p.spawn_pos, dt, use_astar=True)
            return
        # Minaccia nemica (campione/minion) vicina: ingaggia.
        enemy = self._acquire_enemy_unit(p, BOT_AGGRO)
        if enemy is not None:
            p.target_id = enemy.id
            self._bot_try_cast(p, enemy)
            if self._within_attack(p, enemy):
                p.stop(); self._face(p, enemy)
            else:
                self._chase(p, enemy, dt)
            return
        # Farming: campo neutrale (o leggendario, se abbastanza forte) più vicino.
        wild = self._nearest_wild_for(p)
        if wild is not None:
            p.target_id = wild.id
            self._bot_try_cast(p, wild)
            if self._within_attack(p, wild):
                p.stop(); self._face(p, wild)
            else:
                self._move_towards(p, wild.pos, dt, use_astar=True)
            return
        # Niente da fare: pattuglia verso il centro della giungla.
        p.target_id = None
        self._move_towards(p, Vec2(self.world.grid.width * 0.5,
                                   self.world.grid.height * 0.5), dt, use_astar=True)

    def _acquire_enemy_unit(self, p, radius):
        """Nemico (campione/minion della squadra avversaria, non neutrale) più
        vicino e VISIBILE entro il raggio."""
        best, bk = None, None
        for e in self._combat_hash.query_radius(p.pos.x, p.pos.y, radius):
            if not isinstance(e, (Pokemon, Minion)) or not getattr(e, "alive", False):
                continue
            if e.team == p.team or e.team == 2:
                continue
            if not self.vision.is_enemy_visible(p.team, e.id):
                continue
            d = p.pos.dist(e.pos)
            if d > radius:
                continue
            key = (_prio(e), d)
            if bk is None or key < bk:
                best, bk = e, key
        return best

    def _nearest_wild_for(self, p):
        best, bd = None, 1e9
        for w in self.world.wilds():
            if not w.alive or w.kind == "arceus":
                continue
            if w.kind == "meteo" and p.level < 6:   # il leggendario serve un po' di livello
                continue
            d = p.pos.dist(w.pos)
            if d < bd:
                best, bd = w, d
        return best

    # --- respawn / vittoria --------------------------------------------------
    def _update_respawns(self, dt: float) -> None:
        for p in self.world.pokemons():
            if not p.alive:
                p.respawn_timer -= dt
                if p.respawn_timer <= 0.0:
                    p.alive = True
                    p.hp = p.max_hp
                    p.pos = Vec2(p.spawn_pos.x, p.spawn_pos.y)
                    p.stop()
                    p.target_id = None

    def _check_win(self) -> None:
        for core in self.world.cores():
            if not core.alive and self.winner is None:
                self.winner = 1 - core.team
