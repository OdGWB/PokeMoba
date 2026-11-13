"""Regole della linea Flabébé > Floette > Florges (supporto guaritore
"giardiniera": cura soprattutto con i FIORI che pianta sulla mappa).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Venomoth e
Octillery: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge le liste `flowers`,
`flor_roots`, `flor_mists` del Match (visibili a TUTTI, come i pilastri) e i
campi `flower_color`, `flor_*_until` delle unità.

Passiva Giardino (tutte e tre le forme):
  - I fiori crescono in 3 fasi: germoglio (0-2 s), bocciolo (2-4 s),
    sbocciato (da 4 s; con Fioritura Rapida da 2 s). Durano 60 s.
  - Al massimo 2 / 3 / 4 fiori (Flabébé / Floette / Florges): piantarne uno
    oltre il limite toglie il più vecchio. I fiori del Giardino Reale non
    contano nel limite.
  - Un Pokémon alleato (anche Florges) che passa su un fiore SBOCCIATO lo
    raccoglie: si cura (Att. Sp. di Florges, valori della Q) e per 4 s ha
    l'effetto del COLORE scelto nella selezione:
      Rosso +15% danno inflitto, Giallo +25% velocità, Arancione scudo del
      10% degli HP max, Blu ricariche -1,5 s subito, Bianco toglie gli stati.
  - Un Pokémon nemico che passa su un fiore (in qualsiasi fase) lo distrugge.
"""
from __future__ import annotations

import math
import random

from .entities import Minion, Pokemon, Wild
from .vec import Vec2

GARDEN_ID = "giardino"
FLOR_PASSIVES = {GARDEN_ID}
COLORS = ("red", "yellow", "orange", "blue", "white")
COLOR_NAMES = {"red": "Rosso", "yellow": "Giallo", "orange": "Arancione",
               "blue": "Blu", "white": "Bianco"}

BLOOM_AT = 4.0              # sbocciato da qui (germoglio fino a metà)
LIFE = 60.0                 # durata di un fiore
MAX_FLOWERS = (2, 3, 4)     # per stadio
PICK_R = 0.45               # raggio del fiore (+ raggio dell'unità)
COLOR_DUR = 4.0
RED_MULT = 1.15
YELLOW_MULT = 1.25
ORANGE_FRAC = 0.10
BLUE_CDR = 1.5
ROOTS_TICK = 0.5
MIST_TICK = 0.1


def has_garden(p) -> bool:
    return getattr(p, "passive_id", "") == GARDEN_ID


def flower_phase(fl, now) -> int:
    """0 germoglio, 1 bocciolo, 2 sbocciato."""
    if now >= fl["bloom"] - 1e-6:
        return 2
    if now >= fl["bud"] - 1e-6:
        return 1
    return 0


def _rank_at(arr, rank, default=0.0):
    if not arr:
        return default
    if not isinstance(arr, list):
        return float(arr)
    return float(arr[min(max(1, rank), len(arr)) - 1])


class FlorgesMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(FLOR_PASSIVES),
        "init": "_init_flor",
        "update": "_update_flor",
        "precheck": "_flor_precheck",
        "cast": "_flor_cast",
        "bot_cast": "_bot_flor_cast",
        "speed_mult": "_flor_speed_mult",
        # Rete (net/visual.py, game/online_world.py): cosa passa al client.
        "net": {
            "shared": ("flowers", "flor_roots", "flor_mists"),
            "unit_flags": {"flower_color": "red"},
            "me": ("flower_color",),
        },
    }

    def _init_flor(self) -> None:
        self.flowers: list[dict] = []     # fiori sul terreno (visibili a tutti)
        self.flor_roots: list[dict] = []  # Radici: aree di cura dopo una raccolta
        self.flor_mists: list[dict] = []  # Campo Nebbioso
        self._flor_seq = 0
        self._flor_heal2: dict = {}       # id Florges -> fine del Giardino Reale (cure x2)

    # --- dispatcher -----------------------------------------------------------
    def _flor_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"florseed": self._cast_florseed, "florheal": self._cast_florheal,
              "florstorm": self._cast_florstorm, "florgarden": self._cast_florgarden,
              "florsolar": self._cast_florsolar}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _flor_precheck(self, p, mv, tgt) -> bool:
        """Solarraggio senza fiori non parte (la ricarica non si spende)."""
        if mv.shape == "florsolar":
            return any(fl["owner"] == p.id for fl in self.flowers)
        return True

    # --- fiori ------------------------------------------------------------------
    def _flor_point(self, origin, tgt, rng):
        to = tgt - origin
        c = Vec2(tgt.x, tgt.y) if to.length() <= rng else origin + to.normalized() * rng
        return self._clamp_to_wall(origin, c)

    def _flor_max(self, p) -> int:
        return MAX_FLOWERS[max(0, min(len(MAX_FLOWERS) - 1, int(p.stage)))]

    def _plant_flower(self, p, pos, bloom=BLOOM_AT, life=LIFE, extra=False) -> dict:
        now = self.time
        if not extra:
            mine = [fl for fl in self.flowers if fl["owner"] == p.id and not fl["extra"]]
            while len(mine) >= self._flor_max(p):
                old = min(mine, key=lambda f: f["born"])
                mine.remove(old)
                self.flowers.remove(old)
                self.fx_events.append({"kind": "buff", "c": (old["pos"].x, old["pos"].y),
                                       "radius": 0.5, "mtype": "Grass", "fx": "florwilt",
                                       "color": old["color"]})
        self._flor_seq += 1
        fl = {"id": self._flor_seq, "pos": Vec2(pos.x, pos.y), "team": p.team, "owner": p.id,
              "color": getattr(p, "flower_color", "red"), "born": now,
              "bud": now + bloom * 0.5, "bloom": now + bloom, "end": now + life,
              "extra": extra, "seed": self._flor_seq * 7 + p.id}
        self.flowers.append(fl)
        return fl

    def _flor_pick_heal(self, owner) -> float:
        """Cura di un fiore raccolto: valori della Q di Florges + Att. Sp."""
        ms = owner.moveset.get("Q") if isinstance(owner, Pokemon) else None
        mv = ms.chosen if ms else None
        eff = mv.effects if mv else {}
        rank = ms.rank if ms else 1
        amt = _rank_at(eff.get("heal", [45]), rank) + float(eff.get("heal_scaling", 0.35)) * owner.eff_sp_attack()
        amt *= owner.heal_power
        if self._flor_heal2.get(owner.id, -1.0) > self.time:
            amt *= 2.0   # Giardino Reale: cure dei fiori raddoppiate
        return amt

    def _flor_pick(self, fl, a) -> None:
        """L'alleato `a` raccoglie il fiore sbocciato `fl`."""
        owner = self.world.get(fl["owner"])
        if owner is None:
            return
        heal = self._flor_pick_heal(owner)
        self._give_heal(owner, a, heal)
        col = fl["color"]
        now = self.time
        if col == "red":
            a.flor_red_until = now + COLOR_DUR
        elif col == "yellow":
            a.flor_yellow_until = now + COLOR_DUR
        elif col == "orange":
            self._give_shield(owner, a, a.max_hp * ORANGE_FRAC, COLOR_DUR)
        elif col == "blue":
            for ms in a.moveset.values():
                if ms.cooldown_remaining > 0.0:
                    ms.cooldown_remaining = max(0.0, ms.cooldown_remaining - BLUE_CDR)
        elif col == "white":
            self._cleanse(a)
        a.flor_pick_at = now
        a.flor_pick_color = col
        self.fx_events.append({"kind": "buff", "c": (fl["pos"].x, fl["pos"].y), "radius": 0.8,
                               "mtype": "Fairy", "fx": "florpick", "color": col})
        # Radici: resta un'area di cura per qualche secondo.
        ms = owner.moveset.get("Q")
        roots = ms.chosen.effects.get("roots") if ms and ms.chosen else None
        if roots:
            dur = float(roots.get("duration", 3.0))
            ticks = max(1, int(round(dur / ROOTS_TICK)))
            self.flor_roots.append({
                "c": Vec2(fl["pos"].x, fl["pos"].y), "radius": float(roots.get("radius", 2.0)),
                "team": fl["team"], "owner": owner.id, "start": now, "end": now + dur,
                "next": now + ROOTS_TICK, "per": heal * float(roots.get("frac", 0.45)) / ticks,
                "color": col})

    def _flor_wilt(self, fl, fx="florcrush") -> None:
        self.fx_events.append({"kind": "buff", "c": (fl["pos"].x, fl["pos"].y), "radius": 0.6,
                               "mtype": "Grass", "fx": fx, "color": fl["color"]})

    def _update_flowers(self) -> None:
        now = self.time
        keep = []
        for fl in self.flowers:
            if now >= fl["end"]:
                self._flor_wilt(fl, "florwilt")
                continue
            pos = fl["pos"]
            gone = False
            ph = flower_phase(fl, now)
            for e in self._combat_hash.query_radius(pos.x, pos.y, PICK_R + 1.0):
                if not isinstance(e, Pokemon) or not e.alive or e.is_decoy:
                    continue
                if e.untargetable_until > now or getattr(e, "airborne_until", -1.0) > now:
                    continue
                if pos.dist(e.pos) > PICK_R + e.radius:
                    continue
                if e.team != fl["team"]:
                    self._flor_wilt(fl)   # calpestato da un nemico
                    gone = True
                    break
                if ph == 2:
                    self._flor_pick(fl, e)
                    gone = True
                    break
            if not gone:
                keep.append(fl)
        self.flowers = keep

    def _flor_allies_in(self, c, r, team):
        for a in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
            if (isinstance(a, Pokemon) and a.team == team and a.alive and not a.is_decoy
                    and c.dist(a.pos) <= r + a.radius):
                yield a

    def _flor_foes_in(self, c, r, team):
        for e in self._combat_hash.query_radius(c.x, c.y, r + 1.5):
            if e.team == team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild)):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            if c.dist(e.pos) <= r + getattr(e, "radius", 0.0):
                yield e

    # --- Q: Semina ------------------------------------------------------------------
    def _cast_florseed(self, p, mv, rank, origin, tgt, dirv):
        c = self._flor_point(origin, tgt, mv.range)
        fl = self._plant_flower(p, c, bloom=float(mv.effects.get("bloom", BLOOM_AT)))
        self.fx_events.append({"kind": "projectile", "a": (origin.x, origin.y),
                               "b": (c.x, c.y), "mtype": mv.type, "fx": "florseed",
                               "color": fl["color"]})

    # --- W: Florocura -----------------------------------------------------------------
    def _flor_heal_target(self, p, mv, tgt):
        best, bd = None, 1.6
        for a in self._flor_allies_in(tgt, 1.6, p.team):
            d = tgt.dist(a.pos)
            if d < bd and p.pos.dist(a.pos) <= mv.range + a.radius + 0.5:
                best, bd = a, d
        return best or p

    def _cast_florheal(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        a = self._flor_heal_target(p, mv, tgt)
        amt = (_rank_at(eff.get("heal"), rank) + float(eff.get("heal_scaling", 0.45))
               * p.eff_sp_attack()) * p.heal_power
        fr = float(eff.get("flower_radius", 3.0))
        near = [fl for fl in self.flowers if fl["owner"] == p.id and fl["pos"].dist(a.pos) <= fr]
        if near:
            amt *= float(eff.get("flower_mult", 2.0))
            for fl in near:   # tutti i fiori vicini sbocciano subito
                if flower_phase(fl, self.time) < 2:
                    fl["bud"] = min(fl["bud"], self.time)
                    fl["bloom"] = self.time
                    self.fx_events.append({"kind": "buff", "c": (fl["pos"].x, fl["pos"].y),
                                           "radius": 0.7, "mtype": "Fairy", "fx": "florbloom",
                                           "color": fl["color"]})
        self._give_heal(p, a, amt)
        cr = eff.get("cleanse_radius")
        if cr:   # Aromaterapia
            for b in list(self._flor_allies_in(a.pos, float(cr), p.team)):
                self._cleanse(b)
                self.fx_events.append({"kind": "buff", "c": (b.pos.x, b.pos.y), "radius": 0.8,
                                       "mtype": "Grass", "fx": "floraroma"})
        sym = eff.get("symbiosis")
        if sym and a is not p:
            frac = float(sym.get("frac", 0.3))
            a.flor_sym_bonus = {k: v * frac for k, v in p.item_bonus.items()
                                if isinstance(v, (int, float)) and v}
            a.flor_sym_until = self.time + float(sym.get("duration", 4.0))
            self._apply_items(a)
            self.fx_events.append({"kind": "link", "a": (p.pos.x, p.pos.y),
                                   "b": (a.pos.x, a.pos.y), "mtype": "Fairy", "fx": "florsym"})
        self.fx_events.append({"kind": "buff", "c": (a.pos.x, a.pos.y), "radius": 1.0,
                               "mtype": "Fairy", "fx": "florheal", "double": bool(near),
                               "a": (origin.x, origin.y)})

    def _flor_sym_bonus(self, p) -> dict:
        if p.flor_sym_until > self.time:
            return p.flor_sym_bonus
        return {}

    # --- E: Petalbufera ---------------------------------------------------------------
    def _flor_vortex(self, p, mv, rank, c, mult) -> None:
        push = float(mv.effects.get("push", 2.0))
        for e in list(self._flor_foes_in(c, mv.radius, p.team)):
            self._hit(p, mv, rank, e, mult)
            if not e.alive or isinstance(e, Wild):
                continue
            if isinstance(e, Pokemon) and self._cc_immune(e):
                continue
            away = e.pos - c
            if away.length() < 1e-6:
                away = Vec2(1.0, 0.0)
            self._item_push(e, away, push)
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": "Grass", "fx": "florstorm",
                               "color": getattr(p, "flower_color", "red")})

    def _cast_florstorm(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        dance, mist = eff.get("dance"), eff.get("mist")
        if dance:   # Petalodanza (al posto del vortice intorno a Florges)
            p.flor_dance_until = self.time + float(dance.get("duration", 3.0))
            p.flor_dance_next = self.time
            self._flor_dance = getattr(self, "_flor_dance", {})
            self._flor_dance[p.id] = (mv, rank, dict(dance))
            self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": 1.2,
                                   "mtype": "Grass", "fx": "flordance"})
        elif mist:   # Campo Nebbioso (al posto del vortice intorno a Florges)
            self.flor_mists.append({"c": Vec2(origin.x, origin.y),
                                    "radius": float(mist.get("radius", 4.0)),
                                    "team": p.team, "owner": p.id, "start": self.time,
                                    "end": self.time + float(mist.get("duration", 5.0))})
            self.fx_events.append({"kind": "area", "c": (origin.x, origin.y),
                                   "radius": float(mist.get("radius", 4.0)),
                                   "mtype": "Fairy", "fx": "flormist"})
        else:
            self._flor_vortex(p, mv, rank, origin, 1.0)
        fr = float(eff.get("flower_range", 8.0))
        fm = float(eff.get("flower_mult", 0.5))
        for fl in list(self.flowers):   # ogni fiore entro 8 tile: stesso vortice al 50%
            if fl["owner"] == p.id and fl["pos"].dist(origin) <= fr:
                self._flor_vortex(p, mv, rank, fl["pos"], fm)

    def _update_dance(self) -> None:
        dances = getattr(self, "_flor_dance", None)
        if not dances:
            return
        now = self.time
        for pid in list(dances):
            p = self.world.get(pid)
            mv, rank, d = dances[pid]
            if p is None or not p.alive:
                dances.pop(pid)
                continue
            if now >= p.flor_dance_until - 1e-6:
                dances.pop(pid)
                p.confuse_until = max(p.confuse_until, now + float(d.get("confuse", 1.0)))
                self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "radius": 0.6,
                                       "mtype": "Psychic", "fx": "mothconfuse"})
                continue
            if now >= p.flor_dance_next - 1e-6:
                p.flor_dance_next += float(d.get("tick", 0.5))
                for e in list(self._flor_foes_in(p.pos, float(d.get("radius", 2.0)), p.team)):
                    self._hit(p, mv, rank, e, float(d.get("tick_mult", 0.25)))

    # --- R: Giardino Reale --------------------------------------------------------------
    def _cast_florgarden(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        c = self._flor_point(origin, tgt, mv.range)
        n = int(eff.get("flowers", 6))
        life = float(eff.get("duration", 20.0))
        rr = mv.radius * 0.62
        spots = [c] + [c + Vec2(math.cos(2 * math.pi * k / (n - 1) + 0.3),
                                math.sin(2 * math.pi * k / (n - 1) + 0.3)) * rr
                       for k in range(max(0, n - 1))]
        for s in spots[:n]:
            self._plant_flower(p, self._clamp_to_wall(c, s), bloom=0.0, life=life, extra=True)
        self._flor_heal2[p.id] = self.time + float(eff.get("heal_dur", 6.0))
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": "Fairy", "fx": "florgarden",
                               "color": getattr(p, "flower_color", "red")})

    # --- R: Solarraggio -------------------------------------------------------------------
    def _cast_florsolar(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        hr = float(eff.get("heal_radius", 3.0))
        heal = self._flor_pick_heal(p) * float(eff.get("heal_frac", 0.6))
        mine = [fl for fl in self.flowers if fl["owner"] == p.id]
        for fl in mine:
            c = fl["pos"]
            best, bd = None, mv.range
            for e in self._combat_hash.query_radius(c.x, c.y, mv.range + 1.0):
                if (isinstance(e, Pokemon) and e.team != p.team and e.alive
                        and e.untargetable_until <= self.time):
                    d = c.dist(e.pos)
                    if d <= bd:
                        best, bd = e, d
            if best is not None:
                self._hit(p, mv, rank, best)
                self.fx_events.append({"kind": "projectile", "a": (c.x, c.y),
                                       "b": (best.pos.x, best.pos.y), "mtype": "Grass",
                                       "fx": "florsolar"})
            for a in list(self._flor_allies_in(c, hr, p.team)):
                self._give_heal(p, a, heal)
            self.fx_events.append({"kind": "buff", "c": (c.x, c.y), "radius": hr,
                                   "mtype": "Grass", "fx": "florsolarflower",
                                   "color": fl["color"]})
        self.flowers = [fl for fl in self.flowers if fl["owner"] != p.id]

    # --- aree --------------------------------------------------------------------------------
    def _update_roots(self) -> None:
        now = self.time
        keep = []
        for z in self.flor_roots:
            if now > z["end"] + 1e-6:
                continue
            keep.append(z)
            if now >= z["next"] - 1e-6:
                z["next"] += ROOTS_TICK
                owner = self.world.get(z["owner"])
                if owner is None:
                    continue
                for a in list(self._flor_allies_in(z["c"], z["radius"], z["team"])):
                    self._give_heal(owner, a, z["per"])
        self.flor_roots = keep

    def _update_mists(self) -> None:
        now = self.time
        self.flor_mists = [z for z in self.flor_mists if now <= z["end"] + 1e-6]
        for z in self.flor_mists:
            for a in list(self._flor_allies_in(z["c"], z["radius"], z["team"])):
                a.cc_immune_until = max(a.cc_immune_until, now + MIST_TICK + 0.05)
                a.flor_mist_until = now + MIST_TICK + 0.05

    def _flor_status_immune(self, p) -> bool:
        """Campo Nebbioso: anche veleno e scottature non attecchiscono."""
        return getattr(p, "flor_mist_until", -1.0) > self.time

    # --- moltiplicatori ----------------------------------------------------------------------
    def _flor_dmg_mult(self, attacker) -> float:
        if isinstance(attacker, Pokemon) and attacker.flor_red_until > self.time:
            return RED_MULT
        return 1.0

    def _flor_speed_mult(self, p) -> float:
        m = 1.0
        if p.flor_yellow_until > self.time:
            m *= YELLOW_MULT
        if p.flor_dance_until > self.time:
            d = getattr(self, "_flor_dance", {}).get(p.id)
            m *= float(d[2].get("speed", 1.3)) if d else 1.3
        return m

    # --- ciclo ---------------------------------------------------------------------------------
    def _update_flor(self, dt: float) -> None:
        if self.flowers:
            self._update_flowers()
        if self.flor_roots:
            self._update_roots()
        if self.flor_mists:
            self._update_mists()
        self._update_dance()
        now = self.time
        for p in self.world.pokemons():
            if p.is_bot and has_garden(p) and not p.__dict__.get("_flor_colored"):
                p.__dict__["_flor_colored"] = True   # i bot scelgono un colore a caso
                p.flower_color = random.choice(COLORS)
            if p.flor_sym_until > 0.0 and p.flor_sym_until <= now:
                p.flor_sym_until = -1.0
                p.flor_sym_bonus = {}
                self._apply_items(p)

    # --- bot ------------------------------------------------------------------------------------
    def _flor_bot_seek(self, p, dt) -> bool:
        """Un bot ferito va a raccogliere un fiore alleato sbocciato vicino."""
        if not self.flowers or p.hp >= p.max_hp * 0.85:
            return False
        now = self.time
        best, bd = None, 3.5
        for fl in self.flowers:
            if fl["team"] != p.team or flower_phase(fl, now) < 2:
                continue
            d = fl["pos"].dist(p.pos)
            if d < bd:
                best, bd = fl, d
        if best is None:
            return False
        p.target_id = None
        p.aa_active = False
        self._move_towards(p, best["pos"], dt, use_astar=False)
        return True

    def _bot_flor_cast(self, p, target) -> bool:
        now = self.time
        allies = [a for a in self.world.pokemons()
                  if a.team == p.team and a.alive and not a.is_decoy and p.pos.dist(a.pos) <= 7.0]
        hurt = min(allies, key=lambda a: a.hp / max(1.0, a.max_hp)) if allies else p
        d = p.pos.dist(target.pos)
        mine = [fl for fl in self.flowers if fl["owner"] == p.id]
        for slot in ("R", "W", "E", "Q"):
            ms = p.moveset.get(slot)
            if not (ms and ms.ready and ms.chosen):
                continue
            mv = ms.chosen
            if mv.shape == "florheal" and hurt.hp < hurt.max_hp * 0.7:
                p.pending_cast = (slot, hurt.pos.x, hurt.pos.y)
                return True
            if mv.shape == "florstorm":
                near = any(fl["pos"].dist(target.pos) <= mv.radius + 0.5 for fl in mine)
                if d <= mv.radius + 0.5 or near:
                    p.pending_cast = (slot, p.pos.x, p.pos.y)
                    return True
            if mv.shape == "florgarden" and hurt.hp < hurt.max_hp * 0.6:
                p.pending_cast = (slot, hurt.pos.x, hurt.pos.y)
                return True
            if mv.shape == "florsolar" and len(mine) >= 2 and any(
                    fl["pos"].dist(target.pos) <= mv.range for fl in mine):
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
            if mv.shape == "florseed":
                # un passo dietro all'alleato più ferito (verso la propria base)
                back = (p.spawn_pos - hurt.pos)
                back = back.normalized() * 1.2 if back.length() > 1e-6 else Vec2(0.0, 0.0)
                c = hurt.pos + back
                p.pending_cast = (slot, c.x, c.y)
                return True
        return False
