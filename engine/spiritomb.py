"""Regole di Spiritomb (supporto roamer, Spettro/Buio): passiva I 108 Spiriti e
mosse Stordiraggio / Malcomune / Richiamo degli Spiriti / Legione dei 108 /
Memento.

Puro: nessun pygame. È un mixin di Match (engine/match.py): usa lo stesso stato
(self.time, self.world, self.fx_events, _combat_hash, gli _apply_*). Il client
legge world.spirits, match.spirit_beams, match.pain_binds e match.legion_waves
per disegnare.
"""
from __future__ import annotations

import math
import random

from .entities import Minion, Pokemon, Spirit, Structure, Wild
from .grid import BLOCKING, TILE_BUSH, TILE_FLOOR, TILE_LANE, TILE_RIVER
from .vec import Vec2

PASSIVE_ID = "108spiriti"
SPIRIT_INTERVAL = 20.0       # s tra una comparsa e l'altra (per Spiritomb)
SPIRIT_MAX = 6               # spiriti presenti contemporaneamente (per Spiritomb)
SPIRIT_CHARGES_MAX = 108
SPIRIT_PICKUP = 0.8          # tile oltre il raggio di Spiritomb per raccoglierlo
SPIRIT_SPEED = 1.3           # +30% velocità per 3s alla raccolta
SPIRIT_SPEED_DUR = 3.0
SPIRIT_XP_BASE = 60.0        # XP per spirito = base + per_livello × livello
SPIRIT_XP_LVL = 12.0
SPIRIT_BASE_DIST = 14.0      # niente spiriti vicino alle basi
SPIRIT_SPACING = 4.0         # distanza minima tra due spiriti dello stesso Spiritomb
AWAKEN_AT = (36, 72, 108)    # risvegli: ognuno dà il bonus qui sotto (cumulativo)
AWAKEN_BONUS = {"hp": 120.0, "defense": 12.0, "sp_defense": 12.0}
WANDER_CD = 6.0              # Spirito Vagante: un attacco base potenziato ogni 6s


def _frac(p) -> float:
    """Cariche di spiriti in 0..1 (scala di tutti gli effetti che crescono)."""
    return max(0, min(SPIRIT_CHARGES_MAX, p.spirit_charges)) / SPIRIT_CHARGES_MAX


class SpiritombMixin:
    def _init_spiritomb(self) -> None:
        self.spirit_beams: list[dict] = []   # Stordiraggio / Neropulsar / Finta in volo
        self.pain_binds: list[dict] = []     # Malcomune: legami di 1s
        self.legion_waves: list[dict] = []   # Legione dei 108: ondata che si espande
        self._spirit_spots: list | None = None

    # --- passiva: spiriti ----------------------------------------------------
    def _spirit_candidates(self) -> list:
        """Tile dove possono comparire gli spiriti (calcolati una volta): giungla o
        fiume RAGGIUNGIBILI a piedi da una base (niente zona oltre la cinta
        muraria né sacche chiuse), lontani dalle basi, dalle lane e dai muri."""
        if self._spirit_spots is not None:
            return self._spirit_spots
        g = self.world.grid
        bases = [Vec2(*v) for k, v in self.map.spawns.items() if k.startswith("team")]
        walk = lambda x, y: (0 <= x < g.width and 0 <= y < g.height
                             and g.tiles[y][x] not in BLOCKING)
        seen, stack = set(), []
        for b in bases:
            st = (int(b.x), int(b.y))
            if st not in seen and walk(*st):
                seen.add(st)
                stack.append(st)
        while stack:
            x, y = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n not in seen and walk(*n):
                    seen.add(n)
                    stack.append(n)
        ok = (TILE_FLOOR, TILE_BUSH, TILE_RIVER)
        spots = []
        for (tx, ty) in seen:
            if g.tiles[ty][tx] not in ok:
                continue
            ring = [(tx + dx, ty + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
            if any(g.tiles[y][x] == TILE_LANE for x, y in ring if 0 <= x < g.width and 0 <= y < g.height):
                continue
            if not all(walk(x, y) for x, y in ring):   # a ridosso di un muro: no
                continue
            c = Vec2(tx + 0.5, ty + 0.5)
            if any(c.dist(b) < SPIRIT_BASE_DIST for b in bases):
                continue
            spots.append(c)
        self._spirit_spots = spots
        return spots

    def _spawn_spirit(self, p) -> None:
        mine = [s for s in self.world.spirits if s.owner_id == p.id]
        if len(mine) >= SPIRIT_MAX:
            return
        spots = self._spirit_candidates()
        g = self.world.grid
        for _ in range(40):
            if not spots:
                return
            c = random.choice(spots)
            if not g.is_walkable_point(c.x, c.y):   # il meteo può aver cambiato il terreno
                continue
            if any(c.dist(s.pos) < SPIRIT_SPACING for s in mine):
                continue
            self.world.spirits.append(Spirit(pos=Vec2(c.x, c.y), owner_id=p.id, team=p.team,
                                             born=self.time, seed=random.randrange(1 << 16)))
            return

    def _collect_spirit(self, p, s) -> None:
        if s in self.world.spirits:
            self.world.spirits.remove(s)
        self._gain_xp(p, SPIRIT_XP_BASE + SPIRIT_XP_LVL * p.level)
        self._apply_speed(p, SPIRIT_SPEED, SPIRIT_SPEED_DUR)
        if p.spirit_charges < SPIRIT_CHARGES_MAX:
            p.spirit_charges += 1
            self._check_awaken(p)
        self.fx_events.append({"kind": "spiritpick", "c": (s.pos.x, s.pos.y),
                               "to": (p.pos.x, p.pos.y), "mtype": "Ghost",
                               "fx": "spiritpick", "team": p.team})

    def _check_awaken(self, p) -> None:
        lvl = sum(1 for n in AWAKEN_AT if p.spirit_charges >= n)
        if lvl == p.spirit_awaken:
            return
        p.spirit_awaken = lvl
        p.spirit_bonus = {k: v * lvl for k, v in AWAKEN_BONUS.items()}
        self._recompute_stats(p, heal_delta=True)
        self.announcements.append((self.time, f"{p.name}: risveglio {lvl}/3 "
                                               f"({p.spirit_charges} spiriti)!"))
        self.fx_events.append({"kind": "spiritawaken", "c": (p.pos.x, p.pos.y),
                               "mtype": "Ghost", "fx": "spiritawaken", "lvl": lvl})

    def _update_spirits(self) -> None:
        owners = {}
        for p in self.world.pokemons():
            if p.passive_id != PASSIVE_ID or p.is_decoy:
                continue
            owners[p.id] = p
            if self.time >= p.spirit_next:
                p.spirit_next = self.time + SPIRIT_INTERVAL
                self._spawn_spirit(p)
        # Spiriti di uno Spiritomb uscito dalla partita: spariscono.
        self.world.spirits = [s for s in self.world.spirits if s.owner_id in owners]
        for s in list(self.world.spirits):
            p = owners[s.owner_id]
            if p.alive and p.pos.dist(s.pos) <= p.radius + SPIRIT_PICKUP:
                self._collect_spirit(p, s)

    def _spirit_wander(self, u, tgt) -> None:
        """Spirito Vagante: ogni 6s il prossimo attacco base libera gli spiriti,
        danno in una piccola area attorno al bersaglio + rallentamento. Danno,
        area e rallentamento crescono con le cariche."""
        if u.passive_id != PASSIVE_ID or self.time < u.wander_ready_at:
            return
        u.wander_ready_at = self.time + WANDER_CD
        f = _frac(u)
        c = Vec2(tgt.pos.x, tgt.pos.y)
        r = 1.0 + 1.2 * f
        raw = 25.0 + 5.0 * u.level + 1.0 * u.spirit_charges + 0.3 * u.eff_sp_attack()
        slow = 0.8 - 0.25 * f
        for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
            if e.team == u.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild, Structure)):
                continue
            if c.dist(e.pos) > r + getattr(e, "radius", 0.0):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            dmg = self._mitigate_hit(u, e, raw, magic=True)
            self._deal_damage(u, e, dmg, dmg_type="Ghost")
            if isinstance(e, Pokemon) and e.alive:
                self._apply_slow(e, slow, 1.5)
        self.fx_events.append({"kind": "spiritburst", "c": (c.x, c.y), "radius": r,
                               "mtype": "Ghost", "fx": "spiritburst"})

    # --- controllo comune ----------------------------------------------------
    def _spirit_precheck(self, p, mv, tgt) -> bool:
        """Falso = la mossa non parte e la ricarica NON si spende (nessun
        bersaglio valido: Malcomune senza nessuno vicino, Richiamo senza
        spiriti nel raggio o con i teletrasporti bloccati)."""
        shape = mv.shape
        if shape == "painsplit":
            return self._painsplit_target(p, mv, tgt) is not None
        if shape == "spiritcall":
            if p.dashlock_until > self.time:
                return False
            return self._spirit_call_target(p, mv, tgt) is not None
        return True

    def _spirit_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        shape = mv.shape
        if shape == "spiritbeam":
            self._cast_spiritbeam(p, mv, rank, origin, dirv)
        elif shape == "painsplit":
            self._cast_painsplit(p, mv, rank, tgt)
        elif shape == "spiritcall":
            self._cast_spiritcall(p, mv, rank, tgt)
        elif shape == "legion":
            self._cast_legion(p, mv, rank, origin)
        elif shape == "memento":
            self._cast_memento(p, mv, rank, origin)
        else:
            return False
        return True

    def _update_spiritomb(self, dt: float) -> None:
        self._update_spirits()
        self._update_spirit_beams(dt)
        self._update_pain_binds()
        self._update_legion_waves()
        self._update_memento()

    # --- Q: Stordiraggio / Neropulsar / Finta --------------------------------
    def _cast_spiritbeam(self, p, mv, rank, origin, dirv) -> None:
        self.spirit_beams.append({
            "pos": Vec2(origin.x, origin.y), "dir": dirv, "left": mv.range,
            "speed": mv.speed, "radius": mv.radius, "team": p.team,
            "caster_id": p.id, "mv": mv, "rank": rank, "first": None,
            "fx": mv.fx or "spiritbeam", "born": self.time})

    def _beam_target(self, b):
        for e in self._combat_hash.query_radius(b["pos"].x, b["pos"].y, b["radius"] + 1.0):
            if e.team == b["team"] or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild)):
                continue
            if isinstance(e, Pokemon) and (e.untargetable_until > self.time or e.is_decoy):
                continue
            if b["first"] is not None and e.id == b["first"]:
                continue
            if b["pos"].dist(e.pos) <= b["radius"] + getattr(e, "radius", 0.0):
                return e
        return None

    def _update_spirit_beams(self, dt: float) -> None:
        alive = []
        g = self.world.grid
        for b in self.spirit_beams:
            caster = self.world.get(b["caster_id"])
            mv = b["mv"]
            fx = mv.effects
            step = b["speed"] * dt
            n = max(1, int(step / 0.25) + 1)     # sotto-passi: niente salti di muri sottili
            done = False
            for _ in range(n):
                b["pos"] = b["pos"] + b["dir"] * (step / n)
                b["left"] -= step / n
                first = self.world.get(b["first"]) if b["first"] is not None else None
                if not g.is_walkable_point(b["pos"].x, b["pos"].y):
                    if first is not None:        # dopo il bersaglio, contro un muro: combo
                        self._beam_combo(b, first, None)
                    self.fx_events.append({"kind": "spiritbeamhit", "c": (b["pos"].x, b["pos"].y),
                                           "mtype": mv.type, "fx": "spiritbeamhit",
                                           "wall": first is not None})
                    done = True
                    break
                hit = self._beam_target(b)
                if hit is None:
                    continue
                if caster is not None and mv.power_at(b["rank"]) > 0:
                    self._hit(caster, mv, b["rank"], hit)
                if first is None:
                    # Primo nemico: confuso (o stordito con Neropulsar); il proiettile
                    # prosegue ancora per un tratto dietro di lui.
                    fst = fx.get("first", {})
                    if isinstance(hit, Pokemon) and hit.alive:
                        if fst.get("confuse"):
                            self._apply_confuse(hit, float(fst["confuse"]))
                        if fst.get("stun"):
                            self._apply_stun(hit, float(fst["stun"]))
                    b["first"] = hit.id
                    b["left"] = float(fx.get("combo", {}).get("reach", 3.0))
                    self.fx_events.append({"kind": "spiritbeamhit", "c": (hit.pos.x, hit.pos.y),
                                           "mtype": mv.type, "fx": "spiritbeamhit"})
                else:
                    self._beam_combo(b, first, hit)
                    done = True
                    break
            if done:
                continue
            if b["left"] > 0:
                alive.append(b)
        self.spirit_beams = alive

    def _beam_combo(self, b, first, second) -> None:
        """Dopo il primo bersaglio il proiettile colpisce un muro o un secondo
        nemico: entrambi storditi (Finta: più a lungo)."""
        dur = float(b["mv"].effects.get("combo", {}).get("stun", 1.5))
        pts = []
        for e in (first, second):
            if isinstance(e, Pokemon) and e.alive:
                e.confuse_until = min(e.confuse_until, self.time)   # lo stordimento sostituisce la confusione
                self._apply_stun(e, dur)
            if e is not None:
                pts.append((e.pos.x, e.pos.y))
        self.fx_events.append({"kind": "spiritbind", "pts": pts,
                               "c": (b["pos"].x, b["pos"].y), "dur": dur,
                               "mtype": b["mv"].type, "fx": "spiritbind"})

    # --- W: Malcomune / Malcomune + / Dispetto -------------------------------
    def _painsplit_target(self, p, mv, tgt):
        best, bk = None, 1e9
        for e in self._combat_hash.query_radius(p.pos.x, p.pos.y, mv.range + 1.0):
            if e is p or not isinstance(e, Pokemon) or not e.alive or e.is_decoy:
                continue
            if e.team != p.team and e.untargetable_until > self.time:
                continue
            if p.pos.dist(e.pos) > mv.range + e.radius:
                continue
            k = tgt.dist(e.pos)
            if k < bk:
                best, bk = e, k
        return best

    def _cast_painsplit(self, p, mv, rank, tgt) -> None:
        first = self._painsplit_target(p, mv, tgt)
        if first is None:
            return
        ids = [first.id]
        # Malcomune +: con un alleato, si lega anche a un secondo alleato vicino.
        if mv.effects.get("allies", 1) >= 2 and first.team == p.team:
            best, bd = None, 1e9
            for e in self.world.pokemons():
                if e is p or e is first or e.team != p.team or not e.alive or e.is_decoy:
                    continue
                d = p.pos.dist(e.pos)
                if d <= mv.range + e.radius and d < bd:
                    best, bd = e, d
            if best is not None:
                ids.append(best.id)
        dur = float(mv.effects.get("duration", 1.0))
        self.pain_binds.append({"caster_id": p.id, "ids": ids, "start": self.time,
                                "until": self.time + dur, "mv": mv,
                                "break": mv.range + 3.0})
        self.fx_events.append({"kind": "painlink", "c": (p.pos.x, p.pos.y),
                               "mtype": "Ghost", "fx": "painlink"})

    def _update_pain_binds(self) -> None:
        keep = []
        for bd in self.pain_binds:
            p = self.world.get(bd["caster_id"])
            if p is None or not p.alive:
                continue
            ids = []
            for i in bd["ids"]:
                e = self.world.get(i)
                if (e is not None and e.alive and p.pos.dist(e.pos) <= bd["break"]
                        and not (e.team != p.team and e.untargetable_until > self.time)):
                    ids.append(i)
            bd["ids"] = ids
            if not ids:
                continue   # legame spezzato (troppo lontano / morto / non bersagliabile)
            if self.time < bd["until"]:
                keep.append(bd)
                continue
            # Fine del legame: gli HP percentuali di tutti diventano la media.
            group = [p] + [self.world.get(i) for i in ids]
            avg = sum(u.hp / max(1.0, u.max_hp) for u in group) / len(group)
            for u in group:
                u.hp = max(1.0, min(u.max_hp, avg * u.max_hp))
            pts = [(u.pos.x, u.pos.y) for u in group]
            self.fx_events.append({"kind": "painsplit", "pts": pts, "mtype": "Ghost",
                                   "fx": "painsplit"})
            sp = bd["mv"].effects.get("spite")
            if sp:   # Dispetto: le ricariche del nemico legato si allungano
                for u in group[1:]:
                    if u.team != p.team:
                        self._apply_spite(u, float(sp.get("mult", 1.5)),
                                          float(sp.get("duration", 4.0)))
        self.pain_binds = keep

    def _apply_spite(self, u, mult, dur) -> None:
        for ms in u.moveset.values():
            if ms.cooldown_remaining > 0.0:
                ms.cooldown_remaining *= mult
        u.spite_mult = mult
        u.spite_until = max(u.spite_until, self.time + dur)

    # --- E: Richiamo degli Spiriti / Accompagnatore / Inseguimento ------------
    def _spirit_call_target(self, p, mv, tgt):
        best, bk = None, 1e9
        for s in self.world.spirits:
            if s.owner_id != p.id or p.pos.dist(s.pos) > mv.range:
                continue
            k = tgt.dist(s.pos)
            if k < bk:
                best, bk = s, k
        return best

    def _cast_spiritcall(self, p, mv, rank, tgt) -> None:
        s = self._spirit_call_target(p, mv, tgt)
        if s is None:
            return
        src = Vec2(p.pos.x, p.pos.y)
        dest = Vec2(s.pos.x, s.pos.y)
        fx = mv.effects
        mate = None
        if fx.get("escort"):   # Accompagnatore: porta con sé un alleato vicino
            r = float(fx["escort"])
            best = 1e9
            for e in self.world.pokemons():
                if e is p or e.team != p.team or not e.alive or e.is_decoy:
                    continue
                if self._immobile(e) or e.submerged or e.channel_until > self.time:
                    continue
                d = src.dist(e.pos)
                if d <= r + e.radius and d < best:
                    mate, best = e, d
        p.pos = dest
        p.stop()
        p.recalling = False
        self.fx_events.append({"kind": "spiritwarp", "a": (src.x, src.y), "b": (dest.x, dest.y),
                               "mtype": "Ghost", "fx": "spiritwarp"})
        self.fx_events.append({"eid": p.id, "anim": "Hop", "anim_speed": 2.0})
        if mate is not None:
            off = mate.pos - src
            if off.length() < 0.6:
                off = Vec2(0.9, 0.0)
            spot = self._nearest_walkable(dest + off.normalized() * 0.9, dest)
            msrc = Vec2(mate.pos.x, mate.pos.y)
            mate.pos = spot
            mate.stop()
            mate.recalling = False
            self.fx_events.append({"kind": "spiritwarp", "a": (msrc.x, msrc.y),
                                   "b": (spot.x, spot.y), "mtype": "Ghost", "fx": "spiritwarp"})
        self._collect_spirit(p, s)
        ch = fx.get("chase")
        if ch:   # Inseguimento: velocità e ricarica di Q azzerata
            self._apply_speed(p, float(ch.get("mult", 1.4)), float(ch.get("duration", 3.0)))
            q = p.moveset.get("Q")
            if q is not None:
                q.cooldown_remaining = 0.0

    # --- R: Legione dei 108 ---------------------------------------------------
    def _cast_legion(self, p, mv, rank, origin) -> None:
        fx = mv.effects
        f = _frac(p)
        shield = (self._rank_val(fx.get("shield", [80]), rank)
                  + float(fx.get("shield_per_charge", 3.0)) * p.spirit_charges) * p.heal_power
        fmin, fmax = fx.get("fear", [0.6, 2.5])
        self.legion_waves.append({
            "caster_id": p.id, "team": p.team, "c": Vec2(origin.x, origin.y),
            "start": self.time, "dur": float(fx.get("duration", 3.0)),
            "radius": mv.radius, "r": 0.0, "touched": set(), "shield": shield,
            "fear": float(fmin) + (float(fmax) - float(fmin)) * f,
            "speed": float(fx.get("speed", 1.3)), "buff": float(fx.get("buff", 3.0)),
            "charges": p.spirit_charges})
        self.fx_events.append({"kind": "legioncast", "c": (origin.x, origin.y),
                               "mtype": "Ghost", "fx": "legioncast"})

    def _update_legion_waves(self) -> None:
        keep = []
        for w in self.legion_waves:
            p = self.world.get(w["caster_id"])
            if p is not None and p.alive:
                w["c"] = Vec2(p.pos.x, p.pos.y)   # l'ondata resta centrata su Spiritomb
            t = min(1.0, (self.time - w["start"]) / max(1e-6, w["dur"]))
            w["r"] = w["radius"] * (1.0 - (1.0 - t) ** 2)   # rapida all'inizio, poi rallenta
            c = w["c"]
            for e in self._combat_hash.query_radius(c.x, c.y, w["r"] + 1.0):
                if not isinstance(e, Pokemon) or not e.alive or e.is_decoy:
                    continue
                if e.id in w["touched"] or c.dist(e.pos) > w["r"] + e.radius:
                    continue
                w["touched"].add(e.id)
                if e.team == w["team"]:
                    self._give_shield(p, e, w["shield"], w["buff"])   # Creta Luce
                    self._apply_speed(e, w["speed"], w["buff"])
                    self.fx_events.append({"kind": "legionally", "c": (e.pos.x, e.pos.y),
                                           "mtype": "Ghost", "fx": "legionally"})
                elif e.untargetable_until <= self.time:
                    self._apply_fear(e, c, w["fear"])
                    self.fx_events.append({"kind": "legionfear", "c": (e.pos.x, e.pos.y),
                                           "mtype": "Ghost", "fx": "legionfear"})
            if t < 1.0:
                keep.append(w)
        self.legion_waves = keep

    # --- R: Memento -----------------------------------------------------------
    def _cast_memento(self, p, mv, rank, origin) -> None:
        fx = mv.effects
        dur = float(fx.get("duration", 4.0))
        r = mv.radius
        for e in self._combat_hash.query_radius(origin.x, origin.y, r + 1.0):
            if (isinstance(e, Pokemon) and e.alive and e.team != p.team and not e.is_decoy
                    and origin.dist(e.pos) <= r + e.radius
                    and e.untargetable_until <= self.time):
                e.memento_weak_until = max(e.memento_weak_until, self.time + dur)
                e.memento_weak = True
                self.fx_events.append({"kind": "mementocurse", "c": (e.pos.x, e.pos.y),
                                       "mtype": "Dark", "fx": "mementocurse"})
        p.memento_until = self.time + dur
        p.invisible = True
        self._apply_untargetable(p, dur)
        p.aa_active = False
        p.target_id = None
        p.recalling = False
        self.fx_events.append({"kind": "memento", "c": (origin.x, origin.y), "radius": r,
                               "mtype": "Dark", "fx": "memento"})

    def _update_memento(self) -> None:
        for p in self.world.pokemons():
            if p.memento_until < 0.0 or self.time < p.memento_until:
                continue
            p.memento_until = -1.0
            p.invisible = False
            p.untargetable_until = min(p.untargetable_until, self.time)
            if not p.alive:
                continue
            # Riappare accanto all'alleato più vicino (se c'è).
            best, bd = None, 1e9
            for e in self.world.pokemons():
                if e is p or e.team != p.team or not e.alive or e.is_decoy:
                    continue
                d = p.pos.dist(e.pos)
                if d < bd:
                    best, bd = e, d
            src = Vec2(p.pos.x, p.pos.y)
            if best is not None:
                off = p.pos - best.pos
                if off.length() < 0.6:
                    off = Vec2(-0.9, 0.3)
                p.pos = self._nearest_walkable(best.pos + off.normalized() * 1.0, best.pos)
                p.stop()
            self.fx_events.append({"kind": "spiritwarp", "a": (src.x, src.y),
                                   "b": (p.pos.x, p.pos.y), "mtype": "Ghost",
                                   "fx": "spiritwarp"})

    # --- bot ------------------------------------------------------------------
    def _bot_spiritomb_cast(self, p, target) -> bool:
        """Mosse di Spiritomb per i bot (le mosse di controllo hanno power 0 e il
        bot generico non le userebbe). True se ha lanciato qualcosa."""
        def ready(slot):
            ms = p.moveset.get(slot)
            return ms is not None and ms.ready and ms.chosen is not None

        hp = p.hp / max(1.0, p.max_hp)
        d = p.pos.dist(target.pos)
        r = p.moveset.get("R")
        if ready("R"):
            if r.chosen.shape == "legion" and isinstance(target, Pokemon) and d <= 6.0:
                p.pending_cast = ("R", p.pos.x, p.pos.y)
                return True
            if r.chosen.shape == "memento" and hp < 0.35 and d <= 4.0:
                p.pending_cast = ("R", p.pos.x, p.pos.y)
                return True
        if ready("W") and isinstance(target, Pokemon):
            mv = p.moveset["W"].chosen
            thp = target.hp / max(1.0, target.max_hp)
            if d <= mv.range and thp - hp > 0.25:
                p.pending_cast = ("W", target.pos.x, target.pos.y)
                return True
            for a in self.world.pokemons():
                if (a is not p and a.team == p.team and a.alive
                        and p.pos.dist(a.pos) <= mv.range
                        and hp - a.hp / max(1.0, a.max_hp) > 0.3):
                    p.pending_cast = ("W", a.pos.x, a.pos.y)
                    return True
        if ready("Q") and d <= p.moveset["Q"].chosen.range:
            p.pending_cast = ("Q", target.pos.x, target.pos.y)
            return True
        return False

    def _bot_spirit_roam(self, p, dt) -> bool:
        """Senza bersagli il bot Spiritomb va a raccogliere gli spiriti: a piedi
        se vicini, con Richiamo degli Spiriti se lontani."""
        mine = [s for s in self.world.spirits if s.owner_id == p.id]
        if not mine:
            return False
        s = min(mine, key=lambda it: p.pos.dist(it.pos))
        d = p.pos.dist(s.pos)
        e = p.moveset.get("E")
        if (d > 8.0 and e is not None and e.ready and e.chosen is not None
                and e.chosen.shape == "spiritcall" and d <= e.chosen.range):
            p.pending_cast = ("E", s.pos.x, s.pos.y)
            return True
        if d <= 14.0:
            self._move_towards(p, s.pos, dt, use_astar=True)
            return True
        return False
