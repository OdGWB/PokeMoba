"""Regole della linea Teddiursa > Ursaring > Ursaluna (jungler combattente).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Noivern e Charcadet:
usa lo stesso stato (self.time, self.world, self.fx_events, _combat_hash, gli
_apply_*). Il client legge le liste del Match (honey_zones, bear_leaps, quakes)
e i campi `honey`, `moon_until`, `rest_until` delle unità per disegnare.

Passive (si sommano con l'evoluzione):
  - Miele (Teddiursa e successivi): ogni campo neutrale ripulito dà un vasetto
    (max 3, visibile a tutti); sotto il 40% degli HP ne consuma uno e si cura del
    15% degli HP max, al massimo una volta ogni 10 s; +30% di danno ai neutrali
    (campi, leggendario meteo, Arceus).
  - Dentistretti (Ursaring e Ursaluna, passive_id "dentistretti", che comprende
    anche Miele): con uno stato alterato (scottatura, veleno, paralisi, sonno,
    confusione) +50% Attacco; la scottatura non gli riduce l'Attacco. Dopo
    Riposo il bonus resta 4 s dal risveglio (guts_until).
"""
from __future__ import annotations

from .entities import Minion, Pokemon, Wild
from .vec import Vec2

HONEY_ID = "miele"
GUTS_ID = "dentistretti"
URSA_PASSIVES = {HONEY_ID, GUTS_ID}

HONEY_MAX = 3
HONEY_HP_FRAC = 0.40          # sotto questa frazione di HP consuma un vasetto
HONEY_HEAL = 0.15             # cura (frazione degli HP max)
HONEY_CD = 10.0
HONEY_WILD_MULT = 1.30        # danno ai Pokémon neutrali
GUTS_MULT = 1.5               # Dentistretti: +50% Attacco (usato da Pokemon.eff_attack)

BODYSLAM_TIME = 0.22          # durata del balzo di Corposcontro / Battiterra


def has_honey(p) -> bool:
    return getattr(p, "passive_id", "") in URSA_PASSIVES


class UrsaringMixin:
    def _init_ursa(self) -> None:
        self.honey_zones: list[dict] = []   # Profumino: nuvole di miele a terra
        self.bear_leaps: list[dict] = []    # balzi in volo (Corposcontro, Battiterra, Luna Piena)
        self.quakes: list[dict] = []        # Terremoto: onde d'urto attorno a Ursaluna

    # --- dispatcher -----------------------------------------------------------
    def _ursa_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"honeyscent": self._cast_honeyscent, "rest": self._cast_rest,
              "bodyslam": self._cast_bodyslam, "bulldoze": self._cast_bodyslam,
              "fullmoon": self._cast_fullmoon,
              "earthquake": self._cast_earthquake}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    # --- passiva: Miele ---------------------------------------------------------
    def _honey_wild_mult(self, attacker, target) -> float:
        """+30% di danno ai Pokémon neutrali (campi, leggendario meteo, Arceus)."""
        if isinstance(target, Wild) and isinstance(attacker, Pokemon) and has_honey(attacker):
            return HONEY_WILD_MULT
        return 1.0

    def _honey_on_wild_death(self, victim, killer) -> None:
        """Ripulire un campo (ultimo colpo) dà un vasetto di miele."""
        if (victim.kind == "camp" and isinstance(killer, Pokemon) and has_honey(killer)
                and killer.honey < HONEY_MAX):
            killer.honey += 1
            self.fx_events.append({"kind": "buff", "c": (killer.pos.x, killer.pos.y),
                                   "mtype": "Normal", "fx": "honeygain", "radius": 0.8})

    def _update_honey(self, p) -> None:
        if p.honey <= 0 or p.hp >= p.max_hp * HONEY_HP_FRAC or self.time < p.honey_ready_at:
            return
        p.honey -= 1
        p.honey_ready_at = self.time + HONEY_CD
        self._give_heal(p, p, p.max_hp * HONEY_HEAL)
        self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "mtype": "Normal",
                               "fx": "honeyheal", "radius": 1.0})

    # --- passiva: Dentistretti ----------------------------------------------------
    def _guts_on(self, p) -> bool:
        t = self.time
        return (p.burn_until > t or p.poison_until > t or p.root_until > t
                or p.sleep_until > t or p.confuse_until > t or p.guts_until > t)

    # --- Luna Piena: HP massimi, immunità ai rallentamenti, attacchi ad area --------
    def _ursa_hp_mult(self, p) -> float:
        return p.moon_hp_mult if p.moon_until > self.time else 1.0

    def _ursa_slow_immune(self, p) -> bool:
        return isinstance(p, Pokemon) and p.moon_until > self.time

    def _ursa_after_aa(self, u, tgt) -> None:
        """Luna Piena: l'attacco base colpisce anche i nemici attorno al bersaglio."""
        if u.moon_until <= self.time:
            return
        r = u.moon_cleave
        c = tgt.pos
        for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
            if (e is tgt or e.team == u.team or not getattr(e, "alive", False)
                    or not isinstance(e, (Pokemon, Minion, Wild))):
                continue
            if c.dist(e.pos) > r + getattr(e, "radius", 0.0):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            self._deal_damage(u, e, self._basic_damage(u, e))
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": r,
                               "mtype": "Normal", "fx": "mooncleave"})

    # --- W: Profumino ---------------------------------------------------------------
    def _cast_honeyscent(self, p, mv, rank, origin, tgt, dirv):
        """Nuvola di miele a distanza per qualche secondo: i nemici dentro sono
        rallentati e restano visibili (anche nei cespugli o nella nebbia)."""
        to = tgt - origin
        c = (Vec2(tgt.x, tgt.y) if to.length() <= mv.range
             else origin + to.normalized() * mv.range)
        dur = float(mv.effects.get("duration", 4.0))
        sl = mv.effects.get("slow", {})
        self.honey_zones.append({"c": c, "radius": mv.radius, "team": p.team,
                                 "caster_id": p.id, "start": self.time,
                                 "end": self.time + dur,
                                 "slow": float(sl.get("mult", 0.7))})
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type})

    def _update_honey_zones(self) -> None:
        now = self.time
        self.honey_zones = [z for z in self.honey_zones if z["end"] > now]
        for z in self.honey_zones:
            c, r = z["c"], z["radius"]
            for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
                if (e.team == z["team"] or not getattr(e, "alive", False)
                        or not isinstance(e, Pokemon)):
                    continue
                if c.dist(e.pos) <= r + e.radius:
                    self._apply_slow(e, z["slow"], 0.3)
            self.vision.reveals.setdefault(z["team"], []).append((c.x, c.y, r))

    # --- W: Riposo ------------------------------------------------------------------
    def _cast_rest(self, p, mv, rank, origin, tgt, dirv):
        """Si addormenta: niente azioni, cura metà degli HP mancanti e si libera
        degli altri stati. Il sonno non si rompe col danno e attiva Dentistretti,
        che resta per `guts_after` secondi dopo il risveglio."""
        eff = mv.effects
        dur = float(eff.get("sleep", 2.0))
        now = self.time
        for name in ("slow_until", "stun_until", "root_until", "poison_until", "burn_until",
                     "confuse_until", "fear_until", "charm_until", "taunt_until",
                     "blind_until", "frozen_until", "silence_until", "dashlock_until",
                     "def_debuff_until", "spdef_debuff_until", "atk_debuff_until",
                     "curse_until"):
            if getattr(p, name) > now:
                setattr(p, name, now)
        p.slow_mult = 1.0
        p.sleep_arm_at = -1.0
        p.stop()
        p.target_id = None
        p.aa_active = False
        p.recalling = False
        p.sleep_until = now + dur
        p.rest_until = now + dur
        p.guts_until = now + dur + float(eff.get("guts_after", 4.0))
        self._give_heal(p, p, (p.max_hp - p.hp) * float(eff.get("heal_missing", 0.5)))
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "mtype": mv.type,
                               "radius": 1.0})
        self.fx_events.append({"eid": p.id, "anim": "Sleep"})

    # --- E: Corposcontro / Battiterra -------------------------------------------------
    def _cast_bodyslam(self, p, mv, rank, origin, tgt, dirv):
        """Balzo breve su un punto. Corposcontro si ferma sul PRIMO nemico lungo
        la traiettoria (danno + paralisi); Battiterra atterra sul punto con
        un'onda d'urto che danneggia e rallenta chi è a terra (non i Volanti)."""
        if p.dashlock_until > self.time:   # Cucitombra / Abbattimento: niente balzi
            return
        to = tgt - origin
        dist = min(to.length(), mv.range)
        dest = self._clamp_to_wall(origin, origin + dirv * dist)
        dest, _ = self._intercept_dash(p, origin, dest)
        first = None
        if mv.shape == "bodyslam":
            L = origin.dist(dest)
            best = L + 1.0
            for e in self._combat_hash.query_radius((origin.x + dest.x) / 2,
                                                    (origin.y + dest.y) / 2, L + 2.0):
                if (e.team == p.team or not getattr(e, "alive", False)
                        or not isinstance(e, (Pokemon, Minion, Wild))):
                    continue
                if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                    continue
                if self._point_seg_dist(e.pos, origin, dest) > mv.radius + e.radius:
                    continue
                proj = (e.pos - origin).x * dirv.x + (e.pos - origin).y * dirv.y
                if proj < best:
                    best, first = proj, e
            if first is not None:   # atterra appena davanti al nemico
                stop = max(0.0, best - first.radius - p.radius * 0.6)
                dest = self._nearest_walkable(origin + dirv * stop, origin)
        self._start_leap(p, origin, dest, BODYSLAM_TIME, 0.55, mv, rank,
                         target_id=first.id if first is not None else None)

    def _land_bodyslam(self, p, lp) -> None:
        mv, rank = lp["mv"], lp["rank"]
        c = p.pos
        if mv.shape == "bodyslam":
            e = self.world.get(lp["target_id"]) if lp["target_id"] is not None else None
            if e is not None and e.alive:
                self._hit(p, mv, rank, e)   # danno + paralisi (effects.root)
            self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": 0.9,
                                   "mtype": mv.type, "fx": mv.fx})
            return
        for e in self._ground_targets(p.team, c, mv.radius):
            self._hit(p, mv, rank, e)
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": mv.fx})

    def _is_flying(self, e) -> bool:
        """Volante (non toccato dalle mosse Terra a terra). Trespolo toglie il tipo."""
        return ("Flying" in getattr(e, "types", ())
                and getattr(e, "roost_until", -1.0) <= self.time)

    def _ground_targets(self, team, c, r):
        out = []
        for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
            if e.team == team or not getattr(e, "alive", False):
                continue
            if self._is_flying(e) or getattr(e, "airborne_until", -1.0) > self.time:
                continue
            if c.dist(e.pos) <= r + getattr(e, "radius", 0.0):
                out.append(e)
        return out

    # --- balzi (in volo per qualche istante) ------------------------------------------
    def _start_leap(self, p, a, b, dur, peak, mv, rank, target_id=None) -> None:
        p.stop()
        p.aa_active = False
        p.recalling = False
        p.stun_until = max(p.stun_until, self.time + dur)   # in volo: niente azioni
        self.bear_leaps.append({"pid": p.id, "a": Vec2(a.x, a.y), "c": Vec2(b.x, b.y),
                                "start": self.time, "end": self.time + dur, "peak": peak,
                                "team": p.team, "mv": mv, "rank": rank,
                                "target_id": target_id, "fx": mv.fx})
        self.fx_events.append({"eid": p.id, "anim": "Hop", "anim_speed": 1.0 / max(0.2, dur)})

    def _update_leaps(self) -> None:
        now = self.time
        keep = []
        for lp in self.bear_leaps:
            p = self.world.get(lp["pid"])
            if p is None or not p.alive:
                continue
            span = max(1e-6, lp["end"] - lp["start"])
            t = min(1.0, (now - lp["start"]) / span)
            a, b = lp["a"], lp["c"]
            p.pos = Vec2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
            p.air_z = lp["peak"] * 4.0 * t * (1.0 - t)
            p.stop()
            if t < 1.0:
                keep.append(lp)
                continue
            p.air_z = 0.0
            p.pos = Vec2(b.x, b.y)
            if lp["mv"].shape == "fullmoon":
                self._land_fullmoon(p, lp)
            else:
                self._land_bodyslam(p, lp)
        self.bear_leaps = keep

    # --- R: Luna Piena ------------------------------------------------------------------
    def _cast_fullmoon(self, p, mv, rank, origin, tgt, dirv):
        """Grande balzo su un punto entro 8 tile: all'atterraggio stordisce i
        nemici nell'area, poi per qualche secondo Ursaluna è più grande (+HP max
        con cura dello stesso valore, immune ai rallentamenti, attacchi base ad
        area)."""
        to = tgt - origin
        dest = (origin + to.normalized() * min(to.length(), mv.range)
                if to.length() > 1e-6 else Vec2(origin.x, origin.y))
        dest = self._nearest_walkable(dest, origin)
        dest, _ = self._intercept_dash(p, origin, dest)
        self._start_leap(p, origin, dest, float(mv.effects.get("leap_time", 0.55)), 1.8, mv, rank)

    def _land_fullmoon(self, p, lp) -> None:
        mv, rank = lp["mv"], lp["rank"]
        eff = mv.effects
        c = p.pos
        for e in self._combat_hash.query_radius(c.x, c.y, mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if c.dist(e.pos) <= mv.radius + getattr(e, "radius", 0.0):
                self._hit(p, mv, rank, e)   # danno + stordimento (effects.stun)
        p.moon_until = self.time + float(eff.get("duration", 6.0))
        p.moon_hp_mult = float(eff.get("hp_mult", 1.25))
        p.moon_cleave = float(eff.get("cleave_radius", 1.3))
        p.slow_until = self.time   # immune ai rallentamenti: quelli in corso spariscono
        p.slow_mult = 1.0
        self._recompute_stats(p, heal_delta=True)   # +25% HP max e cura dello stesso valore
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "fullmoonland"})

    def _update_moon(self, p) -> None:
        if p.moon_until > 0.0 and p.moon_until <= self.time:
            p.moon_until = -1.0
            self._recompute_stats(p)   # gli HP in più se ne vanno (restano quelli che ci stanno)

    # --- R: Terremoto -------------------------------------------------------------------
    def _cast_earthquake(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        dur = float(eff.get("duration", 3.0))
        iv = float(eff.get("interval", 0.5))
        self.quakes.append({"c": Vec2(origin.x, origin.y), "radius": mv.radius, "team": p.team,
                            "caster_id": p.id, "start": self.time, "end": self.time + dur,
                            "next": self.time, "interval": iv, "mv": mv, "rank": rank,
                            "mult": 1.0})   # danno in JSON PER COLPO (bilanciamento v2)

    def _update_quakes(self) -> None:
        now = self.time
        keep = []
        for q in self.quakes:
            p = self.world.get(q["caster_id"])
            if p is None or not p.alive or now > q["end"] + 1e-6:
                continue
            q["c"] = Vec2(p.pos.x, p.pos.y)   # le onde partono sempre da Ursaluna
            if now >= q["next"] - 1e-6 and q["next"] < q["end"] - 1e-6:
                q["next"] += q["interval"]
                for e in self._ground_targets(p.team, q["c"], q["radius"]):
                    self._hit(p, q["mv"], q["rank"], e, mult=q["mult"])
                self.fx_events.append({"kind": "area", "c": (q["c"].x, q["c"].y),
                                       "radius": q["radius"], "mtype": "Ground",
                                       "fx": "earthquakepulse"})
                self.fx_events.append({"eid": p.id, "anim": "Rumble"})
            keep.append(q)
        self.quakes = keep

    # --- ciclo ---------------------------------------------------------------------------
    def _self_slow(self, p, mv) -> None:
        """Martelpugno: chi lo usa resta più lento per qualche secondo."""
        ss = mv.effects.get("self_slow")
        if ss and not self._ursa_slow_immune(p):
            mult = float(ss.get("mult", 0.8))
            p.slow_mult = min(p.slow_mult, mult) if self.time <= p.slow_until else mult
            p.slow_until = max(p.slow_until, self.time + float(ss.get("duration", 3.0)))

    def _update_ursa(self, dt: float) -> None:
        if self.bear_leaps:
            self._update_leaps()
        if self.quakes:
            self._update_quakes()
        if self.honey_zones:
            self._update_honey_zones()
        for p in self.world.pokemons():
            if not p.alive or p.passive_id not in URSA_PASSIVES and p.moon_until <= 0.0:
                continue
            p.guts_active = p.passive_id == GUTS_ID and self._guts_on(p)
            self._update_moon(p)
            if has_honey(p):
                self._update_honey(p)

    # --- bot ------------------------------------------------------------------------------
    def _bot_ursa_cast(self, p, target) -> bool:
        """I bot usano anche le mosse senza danno: Profumino e Ruggito sul
        bersaglio, Unghiaguzze vicino, Riposo quando sono messi male."""
        d = p.pos.dist(target.pos)
        for slot in ("W", "E"):
            ms = p.moveset.get(slot)
            if not (ms and ms.ready and ms.chosen):
                continue
            mv = ms.chosen
            if mv.shape == "rest":
                if p.hp < p.max_hp * 0.35 and d > 2.5:
                    p.pending_cast = (slot, p.pos.x, p.pos.y)
                    return True
                continue
            if mv.shape == "buff" and d <= 2.5:
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
            if mv.shape == "honeyscent" and d <= mv.range and isinstance(target, Pokemon):
                p.pending_cast = (slot, target.pos.x, target.pos.y)
                return True
            if mv.id == "roar" and d <= mv.range * 0.8 and isinstance(target, Pokemon):
                p.pending_cast = (slot, target.pos.x, target.pos.y)
                return True
        ms = p.moveset.get("R")
        if ms and ms.ready and ms.chosen and ms.chosen.shape == "earthquake" and d <= 2.5:
            p.pending_cast = ("R", p.pos.x, p.pos.y)
            return True
        return False
