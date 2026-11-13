"""Regole della linea Magnemite > Magneton > Magnezone (mago di controllo ad
alta difficoltà basato sulle CARICHE MAGNETICHE).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Hatterene. Il
client legge le liste del Match (mag_bolts, mag_walls, ion_trails,
mag_pillars, mag_fields, mag_links) e i campi delle unità (mag_sign,
mag_until) per disegnare.

Passiva Magnetismo (stesso id per le tre forme):
  - le mosse applicano una carica + o - a Pokémon nemici, Pokémon alleati o
    muri per 4 s (8 s sui nemici di tipo Acciaio); una nuova carica sostituisce
    la precedente; visibili a tutti;
  - due cariche entro 5 tile interagiscono (ognuna con la più vicina, una
    sola alla volta; l'interazione consuma entrambe le cariche):
      nemico + nemico, opposte -> trascinati l'uno contro l'altro: all'urto
        danno a entrambi e stordimento di 0,5 s;
      nemico + nemico, uguali  -> spinti in direzioni opposte di 3 tile,
        rallentati;
      nemico + ANCORA (alleato o muro, non si muovono mai): opposte -> il
        nemico è trascinato verso l'ancora (contro un muro: danno e
        stordimento all'impatto); uguali -> respinto di 3 tile.
Mosse: Q Tuonoshock (proiettile rapido, carica + al primo nemico o muro;
Elettrotela = attraversa e rallenta, Falcecannone = lento, +50% e paralizza),
W Campo Magnetico (nemico: danno e carica -; alleato: scudo e carica -;
Doppia Polarità = scudo +50% per 5 s, Catena = la carica - salta al nemico
più vicino con metà danno), E Voltcambio (scatto che INVERTE le cariche
attraversate; Doppio scatto = 2 cariche, Scia Ionica = scia che carica +),
R Bombagnete (pilastro-ostacolo con polarità scelta che a ogni secondo
attira o respinge i nemici carichi entro 6 tile) o Campo Elettrico (area di
6 s che ogni secondo carica i nemici dentro con la polarità scelta; dentro,
le mosse della linea hanno +50% di portata).

POLARITÀ della R: viaggia nel campo `hold` del comando di lancio (lo stesso
della pressione di Tiro Lungo): hold >= 0,5 -> "-", altrimenti "+".
"""
from __future__ import annotations

import math

from .entities import Minion, Pokemon, Structure, Wild
from .grid import TILE_JUNGLE_WALL, TILE_PILLAR, TILE_WALL
from .moves import Move
from .vec import Vec2

MAG_ID = "magnetismo"
MAG_PASSIVES = {MAG_ID}

CHARGE_DUR = 4.0              # durata di una carica
CHARGE_DUR_STEEL = 8.0        # sui nemici di tipo Acciaio
LINK_RANGE = 5.0              # due cariche entro 5 tile interagiscono
PULL_SPEED = 15.0             # tile/s del trascinamento
PUSH_SPEED = 12.0             # tile/s della respinta
PUSH_DIST = 3.0
PUSH_SLOW = 0.6               # rallentamento durante (e subito dopo) la spinta
PUSH_SLOW_TAIL = 0.6          # s di rallentamento dopo la fine della spinta
CLASH_STUN = 0.5
DRAG_MAX = 1.0                # s massimi di trascinamento (poi l'urto scatta comunque)
NEG_HOLD = 0.5                # hold >= 0,5 -> polarità "-"
WALL_TILES = (TILE_WALL, TILE_JUNGLE_WALL, TILE_PILLAR)

# Danno dello scontro magnetico (passiva): cresce col livello del Magnemite.
CLASH_MOVE = {"id": "magnetclash", "name": "Scontro magnetico", "type": "Steel",
              "category": "special", "shape": "none", "power": [35, 60, 85, 110],
              "ratio": 0.35}


def is_mag_line(p) -> bool:
    return getattr(p, "passive_id", None) in MAG_PASSIVES


def sign_of(hold: float) -> int:
    return -1 if float(hold or 0.0) >= NEG_HOLD else 1


class MagnezoneMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(MAG_PASSIVES),
        "init": "_init_mag",
        "update": "_update_mag",
        "precheck": "_mag_precheck",
        "cast": "_mag_cast",
        "bot_cast": "_bot_mag_cast",
    }

    def _init_mag(self) -> None:
        self.mag_bolts: list[dict] = []    # Tuonoshock in volo
        self.mag_walls: list[dict] = []    # cariche sui muri (visibili a tutti)
        self.ion_trails: list[dict] = []   # Scia Ionica
        self.mag_pillars: list[dict] = []  # Bombagnete (ostacolo, visibile a tutti)
        self.mag_fields: list[dict] = []   # Campo Elettrico (visibile a tutti)
        self.mag_links: list[dict] = []    # interazioni in corso (trascinamenti/spinte)
        self._clash_move = Move("P", 4, dict(CLASH_MOVE))

    # --- dispatcher -------------------------------------------------------------
    def _mag_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"magbolt": self._cast_magbolt, "magfield": self._cast_magfield,
              "voltdash": self._cast_voltdash, "magpillar": self._cast_magpillar,
              "magterrain": self._cast_magterrain}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _mag_precheck(self, p, mv, tgt) -> bool:
        """Campo Magnetico parte solo con un Pokémon sotto il cursore (la
        ricarica non si spende)."""
        if mv.shape != "magfield":
            return True
        return self._mag_pick(p, self._mag_range_mv(p, mv), tgt) is not None

    def _mag_on_cast(self, p, mv):
        """Dentro il proprio Campo Elettrico le mosse della linea hanno +50% di
        portata (copia della mossa, come Grandelente)."""
        return self._mag_range_mv(p, mv)

    def _mag_range_mv(self, p, mv):
        if not is_mag_line(p) or not self.mag_fields or mv.range <= 0:
            return mv
        for z in self.mag_fields:
            if z["team"] == p.team and z["c"].dist(p.pos) <= z["radius"]:
                return Move(mv.slot, mv.max_rank,
                            dict(mv.d, range=mv.range * float(z.get("range_bonus", 1.5))))
        return mv

    # --- cariche ------------------------------------------------------------------
    def _mag_charge(self, e, sign: int, src) -> None:
        """Carica + (1) o - (-1) su un Pokémon per 4 s (8 s sui nemici Acciaio)."""
        if not isinstance(e, Pokemon) or not e.alive or sign == 0:
            return
        dur = CHARGE_DUR
        if e.team != src.team and "Steel" in e.types:
            dur = CHARGE_DUR_STEEL
        e.mag_sign = 1 if sign > 0 else -1
        e.mag_until = self.time + dur
        e.mag_src = src.id
        e.mag_team = src.team
        self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y), "radius": 0.5,
                               "mtype": "Electric", "fx": "magcharge", "sign": e.mag_sign,
                               "eid2": e.id})

    def _mag_charge_wall(self, pt, tile, sign: int, src) -> None:
        """Carica su un muro (`pt` = punto della superficie colpita)."""
        tx, ty = tile
        self.mag_walls = [w for w in self.mag_walls if (w["tx"], w["ty"]) != (tx, ty)]
        self.mag_walls.append({"c": Vec2(pt.x, pt.y), "tx": tx, "ty": ty,
                               "sign": 1 if sign > 0 else -1, "team": src.team,
                               "src": src.id, "start": self.time,
                               "until": self.time + CHARGE_DUR})
        self.fx_events.append({"kind": "area", "c": (pt.x, pt.y), "radius": 0.5,
                               "mtype": "Electric", "fx": "magcharge",
                               "sign": 1 if sign > 0 else -1, "wall": True})

    def _mag_clear(self, e) -> None:
        e.mag_sign = 0
        e.mag_until = -1.0

    def _mag_charged(self, e) -> bool:
        return (isinstance(e, Pokemon) and e.alive and e.mag_sign != 0
                and e.mag_until > self.time)

    def _mag_is_wall(self, tx, ty) -> bool:
        return self.world.grid.tile_at(tx, ty) in WALL_TILES

    def _mag_wall_hit(self, a, b):
        """Primo tile-muro sul segmento a->b: (punto calpestabile prima del muro,
        tile del muro) oppure None."""
        d = b - a
        L = d.length()
        if L < 1e-6:
            return None
        steps = int(L * 6) + 1
        last = a
        for i in range(1, steps + 1):
            pt = a + d * (i / steps)
            tx, ty = int(math.floor(pt.x)), int(math.floor(pt.y))
            if not self.world.grid.is_walkable(tx, ty):
                return last, (tx, ty)
            last = pt
        return None

    # --- utilità ------------------------------------------------------------------
    def _mag_foes(self, p, c, r, champs_only=False):
        out = []
        for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if champs_only and not isinstance(e, Pokemon):
                continue
            if c.dist(e.pos) > r + getattr(e, "radius", 0.0):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            out.append(e)
        return out

    def _mag_pick(self, p, mv, tgt):
        """Campo Magnetico: il Pokémon (nemico o alleato, anche sé stesso) più
        vicino al cursore, entro la portata."""
        best, bd = None, 1e9
        for e in self.world.pokemons():
            if not e.alive:
                continue
            if e.team != p.team and e.untargetable_until > self.time:
                continue
            d = e.pos.dist(tgt)
            if d > mv.radius + e.radius:
                continue
            if p.pos.dist(e.pos) > mv.range + e.radius + 0.3:
                continue
            if e.team != p.team and getattr(e, "invisible", False):
                continue
            if d < bd:
                best, bd = e, d
        return best

    # --- Q: Tuonoshock / Elettrotela / Falcecannone ---------------------------------
    def _cast_magbolt(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        self.mag_bolts.append({"pos": Vec2(origin.x, origin.y), "origin": Vec2(origin.x, origin.y),
                               "dir": Vec2(dirv.x, dirv.y), "left": mv.range,
                               "speed": float(eff.get("bolt_speed", 18.0)),
                               "radius": mv.radius, "team": p.team, "caster_id": p.id,
                               "mv": mv, "rank": rank, "pierce": bool(eff.get("pierce")),
                               "big": bool(eff.get("big")), "hit": set(),
                               "fx": mv.fx or "magbolt", "born": self.time})

    def _update_mag_bolts(self, dt: float) -> None:
        keep = []
        for o in self.mag_bolts:
            p = self.world.get(o["caster_id"])
            if p is None:
                continue
            step = o["speed"] * dt
            a = o["pos"]
            b = a + o["dir"] * min(step, max(0.0, o["left"]))
            wall = self._mag_wall_hit(a, b)
            if wall is not None:
                b = wall[0]
            done = False
            # Nemici lungo il tratto percorso in questo tick.
            mid = (a + b) * 0.5
            seg = a.dist(b)
            cands = []
            for e in self._combat_hash.query_radius(mid.x, mid.y, seg * 0.5 + o["radius"] + 1.0):
                if e.team == o["team"] or not getattr(e, "alive", False) or e.id in o["hit"]:
                    continue
                if not isinstance(e, (Pokemon, Minion, Structure, Wild)):
                    continue
                if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                    continue
                if self._point_seg_dist(e.pos, a, b) <= o["radius"] + getattr(e, "radius", 0.0):
                    cands.append((a.dist(e.pos), e))
            cands.sort(key=lambda t: t[0])
            for _, e in cands:
                o["hit"].add(e.id)
                self._mag_bolt_hit(p, o, e)
                if not o["pierce"]:
                    o["pos"] = Vec2(e.pos.x, e.pos.y)
                    done = True
                    break
            if done:
                continue
            o["pos"] = b
            o["left"] -= step
            if wall is not None:
                self._mag_charge_wall(b, wall[1], 1, p)
                self.fx_events.append({"kind": "area", "c": (b.x, b.y), "radius": 0.4,
                                       "mtype": "Electric", "fx": "magboltwall",
                                       "big": o["big"]})
                continue
            if o["left"] > 0:
                keep.append(o)
            else:
                self.fx_events.append({"kind": "area", "c": (b.x, b.y), "radius": 0.3,
                                       "mtype": "Electric", "fx": "magfizzle"})
        self.mag_bolts = keep

    def _mag_bolt_hit(self, p, o, e) -> None:
        mv = o["mv"]
        self._hit(p, mv, o["rank"], e)
        if isinstance(e, Pokemon) and e.alive:
            self._mag_charge(e, 1, p)
            if "root" in mv.effects:
                self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y),
                                       "radius": 0.6, "mtype": "Electric", "fx": "paralyzed"})
        self.fx_events.append({"kind": "area", "c": (e.pos.x, e.pos.y), "radius": 0.5,
                               "mtype": "Electric", "fx": "magbolthit", "big": o["big"],
                               "web": o["pierce"]})

    # --- W: Campo Magnetico / Doppia Polarità / Catena -------------------------------
    def _cast_magfield(self, p, mv, rank, origin, tgt, dirv):
        e = self._mag_pick(p, mv, tgt)
        if e is None:
            return
        eff = mv.effects
        self.fx_events.append({"kind": "beam", "a": (origin.x, origin.y), "b": (e.pos.x, e.pos.y),
                               "c": (e.pos.x, e.pos.y), "mtype": "Steel", "fx": "magfield",
                               "ally": e.team == p.team})
        if e.team == p.team:
            sh = eff.get("mag_shield") or {}
            amt = self._rank_val(sh.get("amount", [60, 90, 120, 150]), rank)
            amt += float(sh.get("scaling", 0.35)) * p.eff_sp_attack()
            amt *= p.heal_power * float(sh.get("mult", 1.0))
            self._give_shield(p, e, amt, float(sh.get("duration", 3.0)))
            self._mag_charge(e, -1, p)
            return
        self._hit(p, mv, rank, e)
        if not e.alive:
            return
        self._mag_charge(e, -1, p)
        ch = eff.get("chain")
        if ch:
            best, bd = None, float(ch.get("range", 4.0))
            for o in self.world.pokemons():
                if (o is e or o.team == p.team or not o.alive
                        or o.untargetable_until > self.time):
                    continue
                d = o.pos.dist(e.pos)
                if d <= bd:
                    best, bd = o, d
            if best is not None:
                self._hit(p, mv, rank, best, float(ch.get("mult", 0.5)))
                self.fx_events.append({"kind": "beam", "a": (e.pos.x, e.pos.y),
                                       "b": (best.pos.x, best.pos.y),
                                       "c": (best.pos.x, best.pos.y), "mtype": "Steel",
                                       "fx": "magchain"})
                if best.alive:
                    self._mag_charge(best, -1, p)

    # --- E: Voltcambio / Doppio scatto / Scia Ionica ---------------------------------
    def _cast_voltdash(self, p, mv, rank, origin, tgt, dirv):
        if p.dashlock_until > self.time:   # Cucitombra: scatti bloccati
            return
        dist = min((tgt - origin).length(), mv.range)
        dest = self._clamp_to_wall(origin, origin + dirv * dist)
        dest, _ = self._intercept_dash(p, origin, dest)
        flips = []
        r = mv.radius
        for e in self.world.pokemons():
            if e is p or not self._mag_charged(e):
                continue
            if self._point_seg_dist(e.pos, origin, dest) <= r + e.radius:
                e.mag_sign = -e.mag_sign
                flips.append((e.pos.x, e.pos.y))
        for w in self.mag_walls:
            if self._point_seg_dist(w["c"], origin, dest) <= r + 0.6:
                w["sign"] = -w["sign"]
                flips.append((w["c"].x, w["c"].y))
        p.pos = dest
        p.stop()
        trail = float(mv.effects.get("trail", 0.0))
        if trail > 0.0 and origin.dist(dest) > 0.2:
            self.ion_trails.append({"a": Vec2(origin.x, origin.y), "b": Vec2(dest.x, dest.y),
                                    "c": (origin + dest) * 0.5, "team": p.team,
                                    "caster_id": p.id, "start": self.time,
                                    "end": self.time + trail, "hit": set()})
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y), "b": (dest.x, dest.y),
                               "mtype": "Electric", "fx": "voltdash"})
        for c in flips:
            self.fx_events.append({"kind": "area", "c": c, "radius": 0.5,
                                   "mtype": "Electric", "fx": "magflip"})

    def _update_ion_trails(self) -> None:
        now = self.time
        keep = []
        for tr in self.ion_trails:
            if tr["end"] <= now:
                continue
            keep.append(tr)
            p = self.world.get(tr["caster_id"])
            if p is None:
                continue
            for e in self.world.pokemons():
                if (e.team == tr["team"] or not e.alive or e.id in tr["hit"]
                        or e.untargetable_until > now):
                    continue
                if self._point_seg_dist(e.pos, tr["a"], tr["b"]) <= 0.55 + e.radius:
                    tr["hit"].add(e.id)
                    self._mag_charge(e, 1, p)
        self.ion_trails = keep

    # --- R: Bombagnete -----------------------------------------------------------------
    def _cast_magpillar(self, p, mv, rank, origin, tgt, dirv):
        """Pilastro magnetico (ostacolo come un muro) con la polarità scelta:
        all'arrivo e ogni secondo attira o respinge i nemici carichi entro 6 tile."""
        to = tgt - origin
        dist = min(to.length(), mv.range)
        c = self._clamp_to_wall(origin, origin + dirv * dist)
        tx, ty = int(math.floor(c.x)), int(math.floor(c.y))
        c = Vec2(tx + 0.5, ty + 0.5)
        eff = mv.effects
        dur = float(eff.get("duration", 4.0))
        land = float(eff.get("land", 0.35))
        pl = {"c": c, "tx": tx, "ty": ty, "sign": sign_of(p.cast_hold), "team": p.team,
              "caster_id": p.id, "start": self.time, "land": self.time + land,
              "end": self.time + land + dur, "next": self.time + land,
              "radius": mv.radius, "mv": mv, "rank": rank, "prev_tile": None,
              "landed": False}
        p.cast_hold = 0.0
        self.mag_pillars.append(pl)

    def _mag_pillar_stamp(self, pl) -> None:
        g = self.world.grid
        tx, ty = pl["tx"], pl["ty"]
        if not g.is_walkable(tx, ty) or self._pillar_at(tx, ty) is not None:
            return
        for s in self.world.structures():
            if s.alive and pl["c"].dist(s.pos) < s.radius + 0.9:
                return
        pl["prev_tile"] = g.tiles[ty][tx]
        g.tiles[ty][tx] = TILE_PILLAR
        self._eject_from_tile(tx, ty)

    def _mag_pillar_unstamp(self, pl) -> None:
        g = self.world.grid
        if pl["prev_tile"] is not None and g.tiles[pl["ty"]][pl["tx"]] == TILE_PILLAR:
            g.tiles[pl["ty"]][pl["tx"]] = pl["prev_tile"]
        pl["prev_tile"] = None

    def _update_mag_pillars(self) -> None:
        now = self.time
        keep = []
        g = self.world.grid
        for pl in self.mag_pillars:
            if now >= pl["end"]:
                self._mag_pillar_unstamp(pl)
                self.fx_events.append({"kind": "area", "c": (pl["c"].x, pl["c"].y),
                                       "radius": 0.8, "mtype": "Steel", "fx": "magpillarend"})
                continue
            keep.append(pl)
            if now < pl["land"]:
                continue
            if not pl["landed"]:
                pl["landed"] = True
                self._mag_pillar_stamp(pl)
                self.fx_events.append({"kind": "area", "c": (pl["c"].x, pl["c"].y),
                                       "radius": pl["radius"], "mtype": "Steel",
                                       "fx": "magpillarland", "sign": pl["sign"]})
            elif pl["prev_tile"] is not None and g.tiles[pl["ty"]][pl["tx"]] != TILE_PILLAR:
                # un cambio meteo ha rigenerato la griglia: si ri-timbra
                pl["prev_tile"] = g.tiles[pl["ty"]][pl["tx"]]
                g.tiles[pl["ty"]][pl["tx"]] = TILE_PILLAR
            if now >= pl["next"]:
                pl["next"] += 1.0
                self._mag_pillar_pulse(pl)
        self.mag_pillars = keep

    def _mag_pillar_pulse(self, pl) -> None:
        p = self.world.get(pl["caster_id"])
        if p is None:
            return
        c = pl["c"]
        busy = self._mag_busy()
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": pl["radius"],
                               "mtype": "Steel", "fx": "magpulse", "sign": pl["sign"]})
        for e in self.world.pokemons():
            if (e.team == pl["team"] or e.id in busy or not self._mag_charged(e)
                    or e.mag_team != pl["team"] or e.pos.dist(c) > pl["radius"]):
                continue
            if e.mag_sign != pl["sign"]:
                self._mag_clear(e)
                self._mag_pull(e, None, c, p, impact=True, mv=pl["mv"], rank=pl["rank"],
                               contact=0.5 + e.radius)
            else:
                self._mag_clear(e)
                away = e.pos - c
                d = away.length()
                self._mag_push(e, away, max(0.5, pl["radius"] - d + 0.3), src=(c.x, c.y))

    # --- R: Campo Elettrico ------------------------------------------------------------
    def _cast_magterrain(self, p, mv, rank, origin, tgt, dirv):
        to = tgt - origin
        c = origin + dirv * min(to.length(), mv.range)
        eff = mv.effects
        dur = float(eff.get("duration", 6.0))
        self.mag_fields.append({"c": Vec2(c.x, c.y), "radius": mv.radius,
                                "sign": sign_of(p.cast_hold), "team": p.team,
                                "caster_id": p.id, "start": self.time,
                                "end": self.time + dur, "next": self.time,
                                "range_bonus": float(eff.get("range_bonus", 1.5))})
        p.cast_hold = 0.0
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": "Electric", "fx": "magterrain"})

    def _update_mag_fields(self) -> None:
        now = self.time
        keep = []
        for z in self.mag_fields:
            if z["end"] <= now:
                continue
            keep.append(z)
            if now < z["next"]:
                continue
            z["next"] += 1.0
            p = self.world.get(z["caster_id"])
            if p is None:
                continue
            for e in self.world.pokemons():
                if (e.team != z["team"] and e.alive and e.untargetable_until <= now
                        and e.pos.dist(z["c"]) <= z["radius"]):
                    self._mag_charge(e, z["sign"], p)
            self.fx_events.append({"kind": "area", "c": (z["c"].x, z["c"].y),
                                   "radius": z["radius"], "mtype": "Electric",
                                   "fx": "magterrainpulse", "sign": z["sign"]})
        self.mag_fields = keep

    # --- interazioni tra cariche -----------------------------------------------------------
    def _mag_busy(self) -> set:
        out = set()
        for ln in self.mag_links:
            out.update(ln["ids"])
        return out

    def _update_mag_links(self) -> None:
        """Accoppia le cariche: ogni unità/muro carico con il più vicino entro
        5 tile (coppie scelte dalla più corta), almeno uno dei due un nemico."""
        now = self.time
        nodes = []
        busy = self._mag_busy()
        for e in self.world.pokemons():
            if e.mag_sign != 0 and (not e.alive or e.mag_until <= now):
                self._mag_clear(e)
                continue
            if e.mag_sign == 0 or e.id in busy:
                continue
            nodes.append((e.mag_team, "foe" if e.team != e.mag_team else "ally",
                          e.pos, e))
        for w in self.mag_walls:
            nodes.append((w["team"], "wall", w["c"], w))
        if len(nodes) < 2:
            return
        pairs = []
        for i in range(len(nodes)):
            ti, ki, pi, _ = nodes[i]
            for j in range(i + 1, len(nodes)):
                tj, kj, pj, _ = nodes[j]
                if ti != tj or (ki != "foe" and kj != "foe"):
                    continue
                d = pi.dist(pj)
                if d <= LINK_RANGE:
                    pairs.append((d, i, j))
        pairs.sort(key=lambda t: t[0])
        used = set()
        for _, i, j in pairs:
            if i in used or j in used:
                continue
            used.add(i)
            used.add(j)
            self._mag_interact(nodes[i], nodes[j])

    def _mag_sign(self, node) -> int:
        kind, obj = node[1], node[3]
        return obj["sign"] if kind == "wall" else obj.mag_sign

    def _mag_consume(self, node) -> None:
        kind, obj = node[1], node[3]
        if kind == "wall":
            if obj in self.mag_walls:
                self.mag_walls.remove(obj)
        else:
            self._mag_clear(obj)

    def _mag_interact(self, na, nb) -> None:
        if na[1] != "foe":
            na, nb = nb, na                     # il primo è sempre un nemico
        sa, sb = self._mag_sign(na), self._mag_sign(nb)
        e = na[3]
        src = self.world.get(e.mag_src)
        self._mag_consume(na)
        self._mag_consume(nb)
        opposite = sa != sb
        self.fx_events.append({"kind": "beam", "a": (na[2].x, na[2].y), "b": (nb[2].x, nb[2].y),
                               "c": (na[2].x, na[2].y), "mtype": "Electric",
                               "fx": "magsnap", "attract": opposite})
        if nb[1] == "foe":
            f = nb[3]
            if opposite:
                self._mag_clash(e, f, src)
            else:
                away = e.pos - f.pos
                if away.length() < 1e-6:
                    away = Vec2(1.0, 0.0)
                self._mag_push(e, away, PUSH_DIST, src=(f.pos.x, f.pos.y))
                self._mag_push(f, away * -1.0, PUSH_DIST, src=(e.pos.x, e.pos.y))
            return
        # Ancora: alleato (lo si segue) o muro (punto fisso).
        if nb[1] == "ally":
            ally = nb[3]
            if opposite:
                self._mag_pull(e, ally, None, src, impact=False,
                               contact=e.radius + ally.radius + 0.05)
            else:
                self._mag_push(e, e.pos - ally.pos, PUSH_DIST, src=(ally.pos.x, ally.pos.y))
            return
        w = nb[3]
        if opposite:
            self._mag_pull(e, None, w["c"], src, impact=True, contact=e.radius + 0.1)
        else:
            self._mag_push(e, e.pos - w["c"], PUSH_DIST, src=(w["c"].x, w["c"].y))

    # --- movimenti forzati (trascinamenti e spinte) -----------------------------------------
    def _mag_can_move(self, e) -> bool:
        return e.alive and not self._cc_immune(e)

    def _drag_end(self, units, dist, speed) -> float:
        """Fine di un trascinamento: con Ventose (Octillery) dura la metà
        (poi l'urto scatta comunque)."""
        if min(self._octi_disp_mult(u) for u in units) < 1.0:
            return self.time + min(DRAG_MAX, max(0.0, dist) / speed) * 0.5
        return self.time + DRAG_MAX

    def _mag_clash(self, a, b, src) -> None:
        self.mag_links.append({"kind": "clash", "ids": (a.id, b.id), "a_id": a.id, "b_id": b.id,
                               "src": src.id if src is not None else 0,
                               "start": self.time,
                               "end": self._drag_end((a, b), a.pos.dist(b.pos), 2 * PULL_SPEED),
                               "a": Vec2(a.pos.x, a.pos.y), "b": Vec2(b.pos.x, b.pos.y),
                               "c": Vec2(a.pos.x, a.pos.y), "team": a.team})

    def _mag_pull(self, e, ally, point, src, impact, contact, mv=None, rank=0) -> None:
        anchor = Vec2(point.x, point.y) if point is not None else Vec2(ally.pos.x, ally.pos.y)
        self.mag_links.append({"kind": "pull", "ids": (e.id,), "a_id": e.id,
                               "ally_id": ally.id if ally is not None else 0,
                               "anchor": anchor, "impact": impact, "contact": contact,
                               "src": src.id if src is not None else 0,
                               "mv": mv, "rank": rank, "start": self.time,
                               "end": self._drag_end((e,), e.pos.dist(anchor) - contact,
                                                     PULL_SPEED),
                               "a": Vec2(e.pos.x, e.pos.y), "b": anchor,
                               "c": Vec2(e.pos.x, e.pos.y), "team": e.team})

    def _mag_push(self, e, away, dist, src=None) -> None:
        if away.length() < 1e-6:
            away = Vec2(1.0, 0.0)
        if isinstance(e, Pokemon) and "iron_ball" in self._fx_items(e):
            from .item_effects import IRONBALL_MULT
            dist *= IRONBALL_MULT
        dist *= self._octi_disp_mult(e)   # Ventose
        dur = dist / PUSH_SPEED
        self.mag_links.append({"kind": "push", "ids": (e.id,), "a_id": e.id,
                               "dir": away.normalized(), "left": dist,
                               "start": self.time, "end": self.time + dur + 0.3,
                               "a": Vec2(e.pos.x, e.pos.y),
                               "b": Vec2(*(src if src is not None else (e.pos.x, e.pos.y))),
                               "c": Vec2(e.pos.x, e.pos.y), "team": e.team})
        if self._mag_can_move(e):
            self._apply_slow(e, PUSH_SLOW, dur + PUSH_SLOW_TAIL)

    def _mag_step(self, e, goal, step) -> float:
        """Sposta `e` verso `goal` di al massimo `step` (fermato dai muri).
        Ritorna lo spostamento effettivo."""
        if not self._mag_can_move(e):
            return 0.0
        to = goal - e.pos
        d = to.length()
        if d < 1e-6:
            return 0.0
        a = Vec2(e.pos.x, e.pos.y)
        dest = self._clamp_to_wall(a, a + to * (min(step, d) / d))
        e.pos = dest
        e.stop()
        if isinstance(e, Pokemon):
            e.aa_active = False
            e.recalling = False
        return a.dist(dest)

    def _mag_impact(self, src, mv, rank, targets) -> None:
        for t in targets:
            if not t.alive:
                continue
            if src is not None:
                if mv is None:
                    lvl = getattr(src, "level", 1)
                    self._hit(src, self._clash_move, 1 + min(3, (lvl - 1) // 4), t)
                else:
                    self._hit(src, mv, rank, t)
            if t.alive:
                self._apply_stun(t, CLASH_STUN)
            self.fx_events.append({"kind": "area", "c": (t.pos.x, t.pos.y), "radius": 0.7,
                                   "mtype": "Steel", "fx": "magclash"})

    def _update_mag_drags(self, dt: float) -> None:
        """Dopo il movimento normale (come Ribaltiro): muove chi è trascinato o
        respinto e risolve gli urti."""
        if not self.mag_links:
            return
        now = self.time
        keep = []
        for ln in self.mag_links:
            kind = ln["kind"]
            a = self.world.get(ln["a_id"])
            if a is None or not a.alive:
                continue
            if kind == "push":
                step = min(ln["left"], PUSH_SPEED * dt)
                goal = a.pos + ln["dir"] * step
                moved = self._mag_step(a, goal, step)
                ln["left"] -= step
                ln["a"] = Vec2(a.pos.x, a.pos.y)
                ln["c"] = ln["a"]
                if ln["left"] > 1e-3 and moved > step * 0.25 and now < ln["end"]:
                    keep.append(ln)
                continue
            src = self.world.get(ln["src"]) if ln["src"] else None
            if kind == "clash":
                b = self.world.get(ln["b_id"])
                if b is None or not b.alive:
                    continue
                contact = a.radius + b.radius + 0.05
                gap = a.pos.dist(b.pos) - contact
                moved = 0.0
                if gap > 0.02:
                    step = min(gap * 0.5 + 1e-3, PULL_SPEED * dt)
                    ma = self._mag_step(a, b.pos, step)
                    mb = self._mag_step(b, a.pos, step if ma > 0 else min(gap, PULL_SPEED * dt * 2))
                    moved = ma + mb
                    gap = a.pos.dist(b.pos) - contact
                ln["a"], ln["b"] = Vec2(a.pos.x, a.pos.y), Vec2(b.pos.x, b.pos.y)
                ln["c"] = (ln["a"] + ln["b"]) * 0.5
                if gap <= 0.02 or moved < 1e-4 or now >= ln["end"]:
                    self._mag_impact(src, None, 0, (a, b))
                    continue
                keep.append(ln)
                continue
            # pull verso un'ancora (alleato che si muove, muro o pilastro fisso)
            if ln["ally_id"]:
                ally = self.world.get(ln["ally_id"])
                if ally is None or not ally.alive:
                    continue
                ln["anchor"] = Vec2(ally.pos.x, ally.pos.y)
            goal = ln["anchor"]
            gap = a.pos.dist(goal) - ln["contact"]
            moved = 0.0
            if gap > 0.02:
                moved = self._mag_step(a, goal, min(gap, PULL_SPEED * dt))
                gap = a.pos.dist(goal) - ln["contact"]
            ln["a"], ln["b"] = Vec2(a.pos.x, a.pos.y), Vec2(goal.x, goal.y)
            ln["c"] = ln["a"]
            if gap <= 0.02 or moved < 1e-4 or now >= ln["end"]:
                if ln["impact"]:
                    self._mag_impact(src, ln["mv"], ln["rank"], (a,))
                continue
            keep.append(ln)
        self.mag_links = keep

    # --- aggiornamento ------------------------------------------------------------------
    def _update_mag(self, dt: float) -> None:
        now = self.time
        if self.mag_bolts:
            self._update_mag_bolts(dt)
        if self.ion_trails:
            self._update_ion_trails()
        if self.mag_walls:
            # scadute o muro sparito (pilastro di roccia crollato, Vento forte)
            self.mag_walls = [w for w in self.mag_walls
                              if w["until"] > now and self._mag_is_wall(w["tx"], w["ty"])]
        if self.mag_pillars:
            self._update_mag_pillars()
        if self.mag_fields:
            self._update_mag_fields()
        self._update_mag_links()

    # --- IA (bot) ---------------------------------------------------------------------
    def _bot_mag_cast(self, p, target) -> bool:
        """Bot della linea: Tuonoshock e Campo Magnetico per creare coppie di
        cariche opposte, Voltcambio per invertire, R quando ci sono nemici carichi."""
        d = p.pos.dist(target.pos)
        tp = (target.pos.x, target.pos.y)
        champ = isinstance(target, Pokemon)
        ms = p.moveset.get("R")
        if ms is not None and ms.ready and ms.chosen is not None and champ:
            mv = ms.chosen
            if mv.shape == "magpillar" and d <= mv.range and self._mag_charged(target):
                # polarità opposta: lo attira contro il pilastro
                p.cast_hold = 1.0 if target.mag_sign > 0 else 0.0
                p.pending_cast = ("R", *tp)
                return True
            if mv.shape == "magterrain" and d <= mv.range:
                near = sum(1 for e in self.world.pokemons()
                           if e.team != p.team and e.alive and e.pos.dist(target.pos) <= mv.radius)
                if near >= 2 or target.hp < target.max_hp * 0.6:
                    p.cast_hold = 0.0
                    p.pending_cast = ("R", *tp)
                    return True
        ms = p.moveset.get("Q")
        if ms is not None and ms.ready and ms.chosen is not None and d <= ms.chosen.range:
            p.pending_cast = ("Q", *tp)
            return True
        ms = p.moveset.get("W")
        if ms is not None and ms.ready and ms.chosen is not None and champ:
            # se il bersaglio è già carico +, la carica - di un vicino lo trascina
            if d <= ms.chosen.range:
                p.pending_cast = ("W", *tp)
                return True
        ms = p.moveset.get("E")
        if (ms is not None and ms.ready and ms.chosen is not None and champ
                and self._mag_charged(target) and d <= ms.chosen.range + 1.0):
            p.pending_cast = ("E", *tp)   # scatta attraverso: inverte la carica
            return True
        return False
