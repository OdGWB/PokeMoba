"""Regole della linea Swinub > Piloswine > Mamoswine (jungler tank d'ingaggio).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Magnezone e
Ursaring: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge le liste del Match
(swine_tracks, ice_trails, glacial_blocks, ice_storms, swine_shoves) e i
campi `frost_stacks`, `frost_until`, `fat_shield` delle unità per disegnare.

Passive (si sommano con l'evoluzione):
  - Fiuto (Swinub e successivi): nella giungla la sua squadra vede le
    IMPRONTE dei Pokémon nemici degli ultimi 8 s, anche nella nebbia (solo le
    impronte, non il Pokémon); +30% di danno ai Pokémon neutrali e ai
    leggendari (tutti i Wild).
  - Grassospesso (da Piloswine): -50% di danno dalle mosse Fuoco e Ghiaccio;
    scudo pari al 10% degli HP max che torna pieno dopo 8 s senza subire danni
    (si consuma DOPO gli altri scudi, che scadono prima).
  - Gelo (Mamoswine): ogni mossa o attacco base a segno su un Pokémon nemico
    gli dà 1 accumulo (5 s, max 4); con 4 accumuli il prossimo attacco base di
    Mamoswine lo congela 1 s e li azzera. Ogni nemico al massimo una volta
    ogni 8 s (frost_lock_until).
"""
from __future__ import annotations

import math
import random

from .entities import Minion, Pokemon, Structure, Wild
from .grid import TILE_LANE
from .vec import Vec2

FIUTO_ID = "fiuto"
FAT_ID = "grassospesso"
GELO_ID = "gelo"
SWINE_PASSIVES = {FIUTO_ID, FAT_ID, GELO_ID}

WILD_MULT = 1.30          # Fiuto: danno ai neutrali e ai leggendari
TRACK_LIFE = 8.0          # le impronte restano 8 s
TRACK_STEP = 0.75         # un'impronta ogni 0,75 tile percorsi
FAT_TYPES = ("Fire", "Ice")
FAT_MULT = 0.5            # Grassospesso: -50% dalle mosse Fuoco e Ghiaccio
FAT_FRAC = 0.10           # scudo = 10% degli HP max
FAT_REGEN = 8.0           # torna pieno dopo 8 s senza danni
FROST_DUR = 5.0           # Gelo: durata degli accumuli
FROST_MAX = 4
FROST_FREEZE = 1.0
FROST_LOCK = 8.0          # un congelamento da Gelo ogni 8 s per nemico
SHOVE_SPEED = 13.0        # Riduttore: velocità della respinta (tile/s)


def has_fiuto(p) -> bool:
    return getattr(p, "passive_id", "") in SWINE_PASSIVES


def has_fat(p) -> bool:
    return getattr(p, "passive_id", "") in (FAT_ID, GELO_ID)


def has_gelo(p) -> bool:
    return getattr(p, "passive_id", "") == GELO_ID


class MamoswineMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(SWINE_PASSIVES),
        "init": "_init_swine",
        "update": "_update_swine",
        "cast": "_swine_cast",
        "speed_mult": "_swine_speed_mult",
    }

    def _init_swine(self) -> None:
        self.swine_tracks: list[dict] = []    # Fiuto: impronte dei nemici (per la squadra che fiuta)
        self.ice_trails: list[dict] = []      # Scia Ghiacciata
        self.swine_shoves: list[dict] = []    # Riduttore: nemici respinti
        self.glacial_blocks: list[dict] = []  # Era Glaciale: blocco di ghiaccio in volo
        self.ice_storms: list[dict] = []      # Era Glaciale: bufera
        self._track_last: dict = {}           # (squadra che fiuta, id) -> ultima impronta

    # --- dispatcher -----------------------------------------------------------
    def _swine_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"icetrail": self._cast_icetrail, "takedown": self._cast_takedown,
              "icefang": self._cast_icefang, "ancientpower": self._cast_ancientpower,
              "iceage": self._cast_iceage}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    # --- passiva: Fiuto -----------------------------------------------------------
    def _swine_wild_mult(self, attacker, target) -> float:
        if isinstance(target, Wild) and isinstance(attacker, Pokemon) and has_fiuto(attacker):
            return WILD_MULT
        return 1.0

    def _in_jungle(self, pos) -> bool:
        g = self.world.grid
        tx, ty = int(pos.x), int(pos.y)
        if not (0 <= tx < g.width and 0 <= ty < g.height):
            return False
        return g.tiles[ty][tx] != TILE_LANE

    def _update_tracks(self) -> None:
        now = self.time
        if self.swine_tracks:
            self.swine_tracks = [t for t in self.swine_tracks if now - t["t"] < TRACK_LIFE]
        sniffers = {p.team for p in self.world.pokemons() if p.alive and has_fiuto(p)}
        if not sniffers:
            return
        for e in self.world.pokemons():
            if not e.alive or e.team not in {1 - t for t in sniffers} or e.is_decoy:
                continue
            if getattr(e, "airborne_until", -1.0) > now or getattr(e, "air_z", 0.0) > 0.05:
                continue
            viewer = 1 - e.team
            key = (viewer, e.id)
            last = self._track_last.get(key)
            if last is None:
                self._track_last[key] = (Vec2(e.pos.x, e.pos.y), 0)
                continue
            lp, side = last
            d = e.pos.dist(lp)
            if d < TRACK_STEP:
                continue
            self._track_last[key] = (Vec2(e.pos.x, e.pos.y), 1 - side)
            if d > 3.0 or not self._in_jungle(e.pos):   # teletrasporto / lane: niente impronta
                continue
            dx, dy = (e.pos.x - lp.x) / d, (e.pos.y - lp.y) / d
            self.swine_tracks.append({"pos": Vec2(e.pos.x, e.pos.y), "t": now,
                                      "dir": (round(dx, 2), round(dy, 2)), "side": side,
                                      "big": e.radius >= 0.5, "team": e.team,
                                      "viewer": viewer})

    # --- passiva: Grassospesso --------------------------------------------------------
    def _swine_type_mult(self, target, dmg_type) -> float:
        if dmg_type in FAT_TYPES and isinstance(target, Pokemon) and has_fat(target):
            return FAT_MULT
        return 1.0

    def _fat_absorb(self, target, amount: float) -> float:
        """Lo scudo di Grassospesso assorbe dopo gli altri scudi."""
        sh = getattr(target, "fat_shield", 0.0)
        if sh <= 0.0 or amount <= 0.0:
            return amount
        a = min(sh, amount)
        target.fat_shield = sh - a
        return amount - a

    def _update_fat(self, p) -> None:
        if not has_fat(p):
            p.fat_shield = 0.0
            return
        cap = p.max_hp * FAT_FRAC
        if self.time - p.last_damaged_at >= FAT_REGEN:
            if p.fat_shield < cap - 0.5:
                self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "radius": 0.9,
                                       "mtype": "Ice", "fx": "fatregen"})
            p.fat_shield = cap
        p.fat_shield = min(p.fat_shield, cap)

    # --- passiva: Gelo ------------------------------------------------------------------
    def _add_frost(self, src, e, n: int = 1) -> None:
        if not (isinstance(e, Pokemon) and e.alive and has_gelo(src) and e.team != src.team):
            return
        if e.frost_until <= self.time:
            e.frost_stacks = 0
        e.frost_stacks = min(FROST_MAX, e.frost_stacks + n)
        e.frost_until = self.time + FROST_DUR
        e.frost_src = src.id

    def _swine_on_hit(self, caster, target, mv) -> None:
        """Dopo ogni colpo di una mossa: accumuli di Gelo, stordimento di Frana."""
        if not (isinstance(caster, Pokemon) and isinstance(target, Pokemon)
                and target.team != caster.team and target.alive):
            return
        if caster.passive_id not in SWINE_PASSIVES:
            return
        sc = mv.effects.get("stun_chance")
        if sc and random.random() < float(sc.get("chance", 0.3)):
            self._apply_stun(target, float(sc.get("duration", 0.75)))
            self.fx_events.append({"kind": "buff", "c": (target.pos.x, target.pos.y),
                                   "radius": 0.6, "mtype": "Rock", "fx": "swinestun"})
        self._add_frost(caster, target, int(mv.effects.get("frost_stacks", 1)))

    def _swine_after_aa(self, u, tgt) -> None:
        """Attacco base di Mamoswine: con 4 accumuli congela (una volta ogni
        8 s per nemico), altrimenti aggiunge un accumulo."""
        if not (has_gelo(u) and isinstance(tgt, Pokemon) and tgt.team != u.team and tgt.alive):
            return
        now = self.time
        if (tgt.frost_stacks >= FROST_MAX and tgt.frost_until > now
                and tgt.frost_lock_until <= now):
            tgt.frost_stacks = 0
            tgt.frost_until = -1.0
            tgt.frost_lock_until = now + FROST_LOCK
            self._apply_freeze(tgt, FROST_FREEZE)
            self.fx_events.append({"kind": "area", "c": (tgt.pos.x, tgt.pos.y), "radius": 0.9,
                                   "mtype": "Ice", "fx": "frostfreeze"})
            return
        self._add_frost(u, tgt, 1)

    # --- moltiplicatori ---------------------------------------------------------------
    def _swine_dmg_mult(self, caster, target, mv) -> float:
        """Valanga (e varianti): danno doppio a chi ha colpito Mamoswine da poco."""
        rv = mv.effects.get("revenge")
        if not rv or not isinstance(caster, Pokemon):
            return 1.0
        seen = getattr(caster, "_damagers", None) or {}
        t = seen.get(getattr(target, "id", -1))
        if t is not None and self.time - t <= float(rv.get("window", 3.0)):
            return float(rv.get("mult", 2.0))
        return 1.0

    def _swine_speed_mult(self, p) -> float:
        m = p.ancient_mult if p.ancient_active else 1.0
        for tr in self.ice_trails:
            if tr["team"] == p.team and self._on_trail(p, tr):
                m *= tr["ally"]
                break
        return m

    def _on_trail(self, e, tr) -> bool:
        return self._point_seg_dist(e.pos, tr["a"], tr["b"]) <= tr["w"] + e.radius * 0.5

    # --- Q: Scia Ghiacciata ---------------------------------------------------------
    def _cast_icetrail(self, p, mv, rank, origin, tgt, dirv):
        if p.dashlock_until > self.time:
            return
        dist = min((tgt - origin).length(), mv.range)
        dest = self._clamp_to_wall(origin, origin + dirv * dist)
        dest, _ = self._intercept_dash(p, origin, dest)
        for e in self._swine_line_foes(p, origin, dest, mv.radius):
            self._hit(p, mv, rank, e)
        p.pos = dest
        p.stop()
        eff = mv.effects
        if origin.dist(dest) > 0.2:
            self.ice_trails.append({"a": Vec2(origin.x, origin.y), "b": Vec2(dest.x, dest.y),
                                    "c": (origin + dest) * 0.5, "w": mv.radius,
                                    "team": p.team, "caster_id": p.id, "start": self.time,
                                    "end": self.time + float(eff.get("trail", 4.0)),
                                    "ally": float(eff.get("ally_speed", 1.3)),
                                    "slow": float(eff.get("foe_slow", 0.7)), "seed": p.cast_seq})
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y), "b": (dest.x, dest.y),
                               "mtype": "Ice", "fx": "icetrail"})

    def _swine_line_foes(self, p, a, b, r):
        out = []
        L = a.dist(b)
        for e in self._combat_hash.query_radius((a.x + b.x) / 2, (a.y + b.y) / 2, L / 2 + r + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild, Structure)):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            if self._point_seg_dist(e.pos, a, b) <= r + getattr(e, "radius", 0.0):
                out.append(e)
        return out

    def _update_ice_trails(self) -> None:
        now = self.time
        self.ice_trails = [tr for tr in self.ice_trails if tr["end"] > now]
        for tr in self.ice_trails:
            for e in self.world.pokemons():
                if e.team == tr["team"] or not e.alive or e.untargetable_until > now:
                    continue
                if self._on_trail(e, tr):
                    self._apply_slow(e, tr["slow"], 0.25)

    # --- Q: Riduttore -----------------------------------------------------------------
    def _cast_takedown(self, p, mv, rank, origin, tgt, dirv):
        """Carica fino a 6 tile: si ferma sul PRIMO nemico, lo respinge di 2 tile
        e prende il 10% del danno come contraccolpo (effects.recoil in _hit)."""
        if p.dashlock_until > self.time:
            return
        dest = self._clamp_to_wall(origin, origin + dirv * mv.range)
        dest, _ = self._intercept_dash(p, origin, dest)
        first, best = None, 1e9
        for e in self._swine_line_foes(p, origin, dest, mv.radius):
            if isinstance(e, Structure):
                continue
            proj = (e.pos - origin).x * dirv.x + (e.pos - origin).y * dirv.y
            if proj < best:
                first, best = e, proj
        if first is not None:
            stop = max(0.0, best - first.radius - p.radius * 0.8)
            dest = self._nearest_walkable(origin + dirv * stop, origin)
        p.pos = dest
        p.stop()
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y), "b": (dest.x, dest.y),
                               "mtype": "Normal", "fx": "takedown"})
        if first is None:
            return
        self._hit(p, mv, rank, first)
        self.fx_events.append({"kind": "area", "c": (first.pos.x, first.pos.y), "radius": 0.8,
                               "mtype": "Normal", "fx": "takedownhit",
                               "dir": (dirv.x, dirv.y)})
        kb = float(mv.effects.get("knockback", 2.0))
        if first.alive and kb > 0 and isinstance(first, (Pokemon, Minion)):
            if isinstance(first, Pokemon) and "iron_ball" in self._fx_items(first):
                from .item_effects import IRONBALL_MULT
                kb *= IRONBALL_MULT
            kb *= self._octi_disp_mult(first)   # Ventose
            self.swine_shoves.append({"id": first.id, "dir": Vec2(dirv.x, dirv.y), "left": kb,
                                      "a": Vec2(first.pos.x, first.pos.y),
                                      "c": Vec2(first.pos.x, first.pos.y),
                                      "team": first.team, "start": self.time,
                                      "end": self.time + kb / SHOVE_SPEED + 0.25})

    def _update_swine_shoves(self, dt: float) -> None:
        """Dopo il movimento normale (come i trascinamenti di Magnetismo)."""
        if not self.swine_shoves:
            return
        keep = []
        for sh in self.swine_shoves:
            e = self.world.get(sh["id"])
            if e is None or not e.alive:
                continue
            step = min(sh["left"], SHOVE_SPEED * dt)
            a = Vec2(e.pos.x, e.pos.y)
            dest = self._clamp_to_wall(a, a + sh["dir"] * step)
            e.pos = dest
            e.stop()
            if isinstance(e, Pokemon):
                e.aa_active = False
                e.recalling = False
            sh["left"] -= step
            sh["c"] = Vec2(dest.x, dest.y)
            if sh["left"] > 1e-3 and a.dist(dest) > step * 0.25 and self.time < sh["end"]:
                keep.append(sh)
        self.swine_shoves = keep

    # --- W: Gelodenti -----------------------------------------------------------------
    def _cast_icefang(self, p, mv, rank, origin, tgt, dirv):
        """Morso in corpo a corpo su UN solo bersaglio (il più vicino davanti)."""
        half = math.radians(mv.angle)
        best, bd = None, 1e9
        for e in self._combat_hash.query_radius(origin.x, origin.y, mv.range + 1.5):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild, Structure)):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            rel = e.pos - origin
            d = rel.length()
            if d > mv.range + getattr(e, "radius", 0.0):
                continue
            if d > 1e-6:
                cosang = (rel.x * dirv.x + rel.y * dirv.y) / d
                if math.acos(max(-1.0, min(1.0, cosang))) > half:
                    continue
            score = d - (1.0 if isinstance(e, Pokemon) else 0.0)   # preferisce i Pokémon
            if score < bd:
                best, bd = e, score
        if best is None:
            c = origin + dirv * (mv.range * 0.7)
            self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": 0.5,
                                   "mtype": "Ice", "fx": "icefang", "miss": True})
            return
        self._hit(p, mv, rank, best)
        self.fx_events.append({"kind": "area", "c": (best.pos.x, best.pos.y), "radius": 0.6,
                               "mtype": "Ice", "fx": "icefang"})

    # --- E: Forzantica / Frana ----------------------------------------------------------
    def _cast_ancientpower(self, p, mv, rank, origin, tgt, dirv):
        to = tgt - origin
        c = (Vec2(tgt.x, tgt.y) if to.length() <= mv.range
             else origin + to.normalized() * mv.range)
        champ = False
        for e in self._combat_hash.query_radius(c.x, c.y, mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if c.dist(e.pos) > mv.radius + getattr(e, "radius", 0.0):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            self._hit(p, mv, rank, e)
            champ = champ or isinstance(e, Pokemon)
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "a": (origin.x, origin.y),
                               "mtype": "Rock", "fx": mv.fx or "ancientpower"})
        st = mv.effects.get("all_stats")
        if champ and st:
            p.ancient_mult = float(st.get("mult", 1.1))
            p.ancient_until = self.time + float(st.get("duration", 4.0))
            p.ancient_active = True
            self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "radius": 1.0,
                                   "mtype": "Rock", "fx": "ancientbuff"})

    # --- R: Era Glaciale ------------------------------------------------------------------
    def _cast_iceage(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        spd = float(eff.get("block_speed", 14.0))
        self.glacial_blocks.append({"pos": Vec2(origin.x, origin.y),
                                    "origin": Vec2(origin.x, origin.y),
                                    "dir": Vec2(dirv.x, dirv.y), "left": mv.range,
                                    "speed": spd, "radius": mv.radius, "team": p.team,
                                    "caster_id": p.id, "mv": mv, "rank": rank,
                                    "start": self.time, "born": self.time})

    def _update_glacial_blocks(self, dt: float) -> None:
        keep = []
        for o in self.glacial_blocks:
            p = self.world.get(o["caster_id"])
            if p is None:
                continue
            step = min(o["speed"] * dt, max(0.0, o["left"]))
            a = o["pos"]
            b = a + o["dir"] * step
            hit, best = None, 1e9
            for e in self.world.pokemons():   # passa sopra minion, neutrali e muri
                if e.team == o["team"] or not e.alive or e.untargetable_until > self.time:
                    continue
                if self._point_seg_dist(e.pos, a, b) <= o["radius"] + e.radius:
                    d = a.dist(e.pos)
                    if d < best:
                        hit, best = e, d
            if hit is not None:
                mv = o["mv"]
                self._hit(p, mv, o["rank"], hit)
                if hit.alive:
                    self._apply_freeze(hit, float(mv.effects.get("block_freeze", 1.5)))
                self.fx_events.append({"kind": "area", "c": (hit.pos.x, hit.pos.y),
                                       "radius": 1.0, "mtype": "Ice", "fx": "iceagehit"})
                self._spawn_ice_storm(p, o, Vec2(hit.pos.x, hit.pos.y))
                continue
            o["pos"] = b
            o["left"] -= step
            if o["left"] > 1e-4:
                keep.append(o)
            else:
                self.fx_events.append({"kind": "area", "c": (b.x, b.y), "radius": 1.0,
                                       "mtype": "Ice", "fx": "iceageburst"})
                self._spawn_ice_storm(p, o, b)
        self.glacial_blocks = keep

    def _spawn_ice_storm(self, p, o, c) -> None:
        eff = o["mv"].effects
        dur = float(eff.get("storm_dur", 3.0))
        self.ice_storms.append({"c": c, "radius": float(eff.get("storm_radius", 3.0)),
                                "team": o["team"], "caster_id": p.id, "start": self.time,
                                "end": self.time + dur, "next": self.time + 1.0,
                                "slow": float(eff.get("storm_slow", 0.6))})

    def _update_ice_storms(self) -> None:
        now = self.time
        keep = []
        for z in self.ice_storms:
            if now > z["end"] + 1e-6:
                continue
            keep.append(z)
            src = self.world.get(z["caster_id"])
            tick = now >= z["next"] - 1e-6
            if tick:
                z["next"] += 1.0
            c, r = z["c"], z["radius"]
            for e in self.world.pokemons():
                if e.team == z["team"] or not e.alive or e.untargetable_until > now:
                    continue
                if c.dist(e.pos) > r + e.radius:
                    continue
                self._apply_slow(e, z["slow"], 0.25)
                if tick and src is not None:
                    self._add_frost(src, e, 1)
                    self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y),
                                           "radius": 0.5, "mtype": "Ice", "fx": "frostgain"})
        self.ice_storms = keep

    # --- ciclo ----------------------------------------------------------------------------
    def _update_swine(self, dt: float) -> None:
        now = self.time
        self._update_tracks()
        if self.ice_trails:
            self._update_ice_trails()
        if self.glacial_blocks:
            self._update_glacial_blocks(dt)
        if self.ice_storms:
            self._update_ice_storms()
        for p in self.world.pokemons():
            if p.frost_stacks and p.frost_until <= now:
                p.frost_stacks = 0
            if p.ancient_active and p.ancient_until <= now:
                p.ancient_active = False
            if not p.alive:
                p.fat_shield = 0.0
                continue
            if has_fat(p) or p.fat_shield:
                self._update_fat(p)
