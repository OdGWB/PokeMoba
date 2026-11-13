"""Regole della linea Venonat > Venomoth (tiratore di logoramento a distanza,
danno speciale, veleno che si accumula).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Mamoswine e
Noivern: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge la lista `powder_clouds` del
Match e i campi `venom_stacks`, `quiver_until`, `silver_until`,
`powdershield_until` delle unità.

Passive (si sommano con l'evoluzione):
  - Scaglie Velenose (Venonat e Venomoth): attacchi base a distanza con danno
    SPECIALE (come Ecolocalizzazione: potere speciale per livello + Att. Sp.,
    mitigati dalla Dif. Sp.); l'Attacco bonus degli oggetti diventa Att. Sp.;
    ogni attacco base dà 1 accumulo di veleno al bersaglio (max 6, 4 s, si
    rinnovano a ogni colpo), ognuno fa danno nel tempo di tipo Veleno (segue
    la tabella dei tipi sui Pokémon: es. poco efficace sugli Acciaio).
  - Lentifumé (Venomoth): le mosse poco efficaci fanno danno normale (x1).

Il veleno degli accumuli NON sveglia chi dorme (altrimenti Sonnifero e la
Tempesta di Polveri si annullerebbero da soli al primo tick).
"""
from __future__ import annotations

import math
import random

from .entities import Minion, Pokemon, Structure, Wild
from .vec import Vec2

SCALES_ID = "scaglievelenose"
TINTED_ID = "lentifume"
MOTH_PASSIVES = {SCALES_ID, TINTED_ID}

VENOM_MAX = 6
VENOM_DUR = 4.0
VENOM_TICK = 0.5            # s tra due tick di danno
VENOM_BASE = 1.5            # danno al secondo PER ACCUMULO = base + per_livello × liv
VENOM_LVL = 0.6             #   + ratio × Att. Sp.
VENOM_RATIO = 0.02
SCALES_AA_MULT = 0.95       # penalità da tiratore (come Ecolocalizzazione)


def has_scales(p) -> bool:
    return getattr(p, "passive_id", "") in MOTH_PASSIVES


def has_tinted(p) -> bool:
    return getattr(p, "passive_id", "") == TINTED_ID


class VenomothMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(MOTH_PASSIVES),
        "init": "_init_moth",
        "update": "_update_moth",
        "cast": "_moth_cast",
        "bot_cast": "_bot_moth_cast",
        "speed_mult": "_moth_speed_mult",
    }

    def _init_moth(self) -> None:
        self.powder_clouds: list[dict] = []   # Velenpolvere / Paralizzante / Sonnifero / Tempesta
        self._venom: dict = {}                # id unità -> stato degli accumuli

    # --- dispatcher -----------------------------------------------------------
    def _moth_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"mothbeam": self._cast_mothbeam, "powdercloud": self._cast_powdercloud,
              "mothgust": self._cast_mothgust, "quiverdance": self._cast_quiverdance,
              "powderstorm": self._cast_powderstorm}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    # --- passiva: Scaglie Velenose ----------------------------------------------
    def _moth_convert(self, p) -> None:
        """L'Attacco bonus degli oggetti diventa Att. Sp. (sui bonus degli oggetti)."""
        if not has_scales(p):
            return
        atk = p.item_bonus.pop("attack", 0.0)
        if atk:
            p.item_bonus["sp_attack"] = p.item_bonus.get("sp_attack", 0.0) + atk

    def _moth_aa_power(self, u) -> float:
        return u.stats.sp_attack * SCALES_AA_MULT + u.eff_sp_attack()

    def _venom_dps(self, src) -> float:
        lv = getattr(src, "level", 1)
        return VENOM_BASE + VENOM_LVL * lv + VENOM_RATIO * src.eff_sp_attack()

    def _add_venom(self, src, e, n: int = 1) -> None:
        """Aggiunge `n` accumuli di veleno (max 6) e li rinnova tutti."""
        if n <= 0 or not getattr(e, "alive", False) or e.team == src.team:
            return
        if isinstance(e, Structure):
            return
        if isinstance(e, Pokemon) and (e.untargetable_until > self.time or e.is_decoy):
            return
        st = self._venom.get(e.id)
        if st is None or st["until"] <= self.time:
            st = {"n": 0, "next": self.time + VENOM_TICK}
            self._venom[e.id] = st
        st["n"] = min(VENOM_MAX, st["n"] + n)
        st["until"] = self.time + VENOM_DUR
        st["src"] = src.id
        st["dps"] = self._venom_dps(src)   # fotografato all'ultimo colpo
        e.venom_stacks = st["n"]

    def _moth_after_aa(self, u, tgt) -> None:
        if not has_scales(u):
            return
        self._add_venom(u, tgt, 2 if u.quiver_until > self.time else 1)

    def _update_venom(self) -> None:
        if not self._venom:
            return
        now = self.time
        for eid in list(self._venom):
            st = self._venom[eid]
            e = self.world.get(eid)
            if e is None or not e.alive or st["until"] <= now:
                self._venom.pop(eid, None)
                if e is not None:
                    e.venom_stacks = 0
                continue
            e.venom_stacks = st["n"]
            if now < st["next"] - 1e-6:
                continue
            st["next"] += VENOM_TICK
            src = self.world.get(st["src"])
            if src is None:
                continue
            asleep = e.sleep_until if isinstance(e, Pokemon) else -1.0
            eff = 1.0
            if isinstance(e, Pokemon):   # tipo Veleno: tabella dei tipi + Lentifume'
                eff = self._moth_eff(src, self.types.moba_multiplier("Poison", e.types))
            self._deal_damage(src, e, st["dps"] * st["n"] * VENOM_TICK * eff,
                              dmg_type="Poison")
            if isinstance(e, Pokemon) and e.alive and asleep > now:
                e.sleep_until = asleep   # il veleno non sveglia

    # --- passiva: Lentifumé ------------------------------------------------------
    def _moth_eff(self, caster, eff: float) -> float:
        if eff < 1.0 and has_tinted(caster):
            return 1.0
        return eff

    # --- moltiplicatori ------------------------------------------------------------
    def _moth_speed_mult(self, p) -> float:
        m = 1.0
        if p.quiver_until > self.time:
            m *= p.quiver_speed
        if p.silver_active:
            m *= p.silver_mult
        return m

    def _moth_as_bonus(self, u) -> float:
        if isinstance(u, Pokemon) and u.quiver_until > self.time:
            return u.quiver_as
        return 0.0

    # --- Q: Psicoraggio / Ventargenteo (raggio) -------------------------------------
    def _cast_mothbeam(self, p, mv, rank, origin, tgt, dirv):
        """Raggio in linea retta: colpisce TUTTI i nemici attraversati (fino al
        primo muro). Psicoraggio: 30% di confondere; Ventargenteo: se prende un
        Pokémon nemico, +10% a tutte le statistiche per 2,5 s."""
        end = self._beam_end(origin, dirv, mv.range)
        L = origin.dist(end)
        mid = (origin + end) * 0.5
        champ = False
        cc = mv.effects.get("confuse_chance")
        for e in self._combat_hash.query_radius(mid.x, mid.y, L * 0.5 + mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            rel = e.pos - origin
            proj = rel.x * dirv.x + rel.y * dirv.y
            if proj < -0.3 or proj > L + 0.3:
                continue
            perp = abs(rel.x * (-dirv.y) + rel.y * dirv.x)
            if perp > mv.radius + getattr(e, "radius", 0.0):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            self._hit(p, mv, rank, e)
            if isinstance(e, Pokemon) and not e.is_decoy:
                champ = True
                if cc and e.alive and random.random() < float(cc.get("chance", 0.3)):
                    self._apply_confuse(e, float(cc.get("duration", 1.0)))
                    self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y),
                                           "radius": 0.6, "mtype": "Psychic",
                                           "fx": "mothconfuse"})
        self.fx_events.append({"kind": "projectile", "a": (origin.x, origin.y),
                               "b": (end.x, end.y), "mtype": mv.type})
        st = mv.effects.get("silver_stats")
        if champ and st:
            p.silver_mult = float(st.get("mult", 1.1))
            p.silver_until = self.time + float(st.get("duration", 2.5))
            p.silver_active = True
            self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "radius": 1.0,
                                   "mtype": "Bug", "fx": "mothsilverbuff"})

    # --- W: nubi di polvere -------------------------------------------------------------
    def _cloud_center(self, origin, tgt, rng):
        to = tgt - origin
        if to.length() <= rng:
            return Vec2(tgt.x, tgt.y)
        return origin + to.normalized() * rng

    def _cast_powdercloud(self, p, mv, rank, origin, tgt, dirv):
        """Nube a terra per 3 s: ogni secondo 1 accumulo di veleno ai nemici
        dentro. Paralizzante: paralizza chi c'è alla comparsa; Sonnifero: chi
        resta dentro più di 1 s si addormenta (una volta per nube)."""
        eff = mv.effects
        c = self._cloud_center(origin, tgt, mv.range)
        kind = str(eff.get("powder", "poison"))
        cl = {"c": c, "radius": mv.radius, "team": p.team, "caster_id": p.id,
              "start": self.time, "end": self.time + float(eff.get("duration", 3.0)),
              "next": self.time, "kind": kind, "stacks": int(eff.get("stacks", 1)),
              "since": {}, "slept": set(), "seed": p.cast_seq}
        if kind == "sleep":
            cl["sleep_after"] = float(eff.get("sleep_after", 1.0))
            cl["sleep"] = float(eff.get("sleep", 1.5))
        self.powder_clouds.append(cl)
        if kind == "stun":
            dur = float(eff.get("para", 1.0))
            for e in self._cloud_foes(cl):
                if isinstance(e, Pokemon):
                    self._apply_root(e, dur)
                    self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y),
                                           "radius": 0.6, "mtype": "Electric",
                                           "fx": "mothpara"})
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "powder": kind})

    def _cloud_foes(self, cl):
        c, r = cl["c"], cl["radius"]
        out = []
        for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
            if e.team == cl["team"] or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild)):
                continue
            if isinstance(e, Pokemon) and (e.untargetable_until > self.time or e.is_decoy):
                continue
            if c.dist(e.pos) <= r + getattr(e, "radius", 0.0):
                out.append(e)
        return out

    # --- R: Tempesta di Polveri -----------------------------------------------------------
    def _cast_powderstorm(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        c = self._cloud_center(origin, tgt, mv.range)
        self.powder_clouds.append({
            "c": c, "radius": mv.radius, "team": p.team, "caster_id": p.id,
            "start": self.time, "end": self.time + float(eff.get("duration", 5.0)),
            "next": self.time, "kind": "storm", "stacks": int(eff.get("stacks", 2)),
            "para": float(eff.get("para", 0.75)), "sleep": float(eff.get("sleep", 1.0)),
            "since": {}, "slept": set(), "seed": p.cast_seq})
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "powder": "storm"})

    def _update_clouds(self) -> None:
        now = self.time
        keep = []
        for cl in self.powder_clouds:
            if now > cl["end"] + 1e-6:
                continue
            keep.append(cl)
            src = self.world.get(cl["caster_id"])
            if src is None:
                continue
            foes = self._cloud_foes(cl)
            inside = {e.id for e in foes}
            since = cl["since"]
            for eid in list(since):
                if eid not in inside:
                    since.pop(eid)   # uscito: il conto del Sonnifero riparte
            for e in foes:
                since.setdefault(e.id, now)
            tick = now >= cl["next"] - 1e-6 and now < cl["end"] - 1e-6   # a 0, 1, 2 s...
            if tick:
                cl["next"] += 1.0
            kind = cl["kind"]
            for e in foes:
                if kind == "sleep" and isinstance(e, Pokemon) and e.id not in cl["slept"]:
                    if now - since[e.id] >= cl["sleep_after"] - 1e-6:
                        cl["slept"].add(e.id)
                        self._apply_sleep(e, cl["sleep"])
                        self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y),
                                               "radius": 0.6, "mtype": "Psychic",
                                               "fx": "mothsleep"})
                if not tick:
                    continue
                if kind != "storm":
                    self._add_venom(src, e, cl["stacks"])
                    continue
                self._storm_roll(src, cl, e)
        self.powder_clouds = keep

    def _storm_roll(self, src, cl, e) -> None:
        """Tempesta di Polveri: a ogni secondo un effetto a caso tra veleno (2
        accumuli), paralisi e sonno (il sonno al massimo una volta per bersaglio)."""
        opts = ["poison", "para"]
        if isinstance(e, Pokemon):
            if e.id not in cl["slept"]:
                opts.append("sleep")
        else:
            opts = ["poison"]   # minion e neutrali: solo il veleno
        pick = random.choice(opts)
        if pick == "poison":
            self._add_venom(src, e, cl["stacks"])
            fx = "mothpoison"
        elif pick == "para":
            self._apply_root(e, cl["para"])
            fx = "mothpara"
        else:
            cl["slept"].add(e.id)
            self._apply_sleep(e, cl["sleep"])
            fx = "mothsleep"
        self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y), "radius": 0.6,
                               "mtype": "Bug", "fx": fx})

    # --- E: Raffica -------------------------------------------------------------------------
    def _cast_mothgust(self, p, mv, rank, origin, tgt, dirv):
        """Folata in avanti (i nemici entro 2 tile davanti vengono respinti di 2
        tile) e scatto all'indietro di 4 tile. Polvoscudo: dopo lo scatto 1,5 s
        immune agli stati alterati e scudo del 15% degli HP max."""
        half = math.radians(70)
        push = float(mv.effects.get("push", 2.0))
        for e in self._combat_hash.query_radius(origin.x, origin.y, mv.radius + 1.5):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild)):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            rel = e.pos - origin
            d = rel.length()
            if d > mv.radius + getattr(e, "radius", 0.0):
                continue
            if d > 1e-6:
                cosang = (rel.x * dirv.x + rel.y * dirv.y) / d
                if math.acos(max(-1.0, min(1.0, cosang))) > half:
                    continue
            self._hit(p, mv, rank, e)
            if not e.alive or isinstance(e, Wild):
                continue   # i neutrali non si spostano
            if isinstance(e, Pokemon) and self._cc_immune(e):
                continue
            self._item_push(e, dirv, push)
        self.fx_events.append({"kind": "cone", "o": (origin.x, origin.y),
                               "dir": (dirv.x, dirv.y), "range": mv.radius,
                               "angle": 70, "mtype": mv.type})
        if p.dashlock_until <= self.time:
            dest = self._clamp_to_wall(origin, origin - dirv * mv.range)
            dest, _ = self._intercept_dash(p, origin, dest)
            p.pos = dest
            p.stop()
            self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                                   "b": (dest.x, dest.y), "mtype": mv.type,
                                   "fx": "mothgustdash"})
        ps = mv.effects.get("powder_shield")
        if ps:
            dur = float(ps.get("duration", 1.5))
            p.cc_immune_until = max(p.cc_immune_until, self.time + dur)
            self._apply_shield(p, p.max_hp * float(ps.get("frac", 0.15)), dur)
            p.powdershield_until = self.time + dur
            self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "radius": 1.0,
                                   "mtype": "Bug", "fx": "mothshield"})

    # --- R: Eledanza ---------------------------------------------------------------------
    def _cast_quiverdance(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        dur = float(eff.get("duration", 6.0))
        p.quiver_until = self.time + dur
        p.quiver_spa = float(eff.get("spa", 1.3))
        p.quiver_spd = float(eff.get("spd", 1.3))
        p.quiver_speed = float(eff.get("speed", 1.2))
        p.quiver_as = float(eff.get("attack_speed", 0.3))
        p.quiver_active = True
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": 1.2,
                               "mtype": "Bug", "fx": "mothquiver"})

    # --- ciclo -------------------------------------------------------------------------------
    def _update_moth(self, dt: float) -> None:
        now = self.time
        if self.powder_clouds:
            self._update_clouds()
        self._update_venom()
        for p in self.world.pokemons():
            if p.quiver_active and p.quiver_until <= now:
                p.quiver_active = False
            if p.silver_active and p.silver_until <= now:
                p.silver_active = False

    # --- bot ----------------------------------------------------------------------------------
    def _bot_moth_cast(self, p, target) -> bool:
        """Le mosse senza potenza (nubi, Eledanza, Tempesta) non le lancia il
        lanciatore generico dei bot."""
        d = p.pos.dist(target.pos)
        for slot in ("R", "W"):
            ms = p.moveset.get(slot)
            if not (ms and ms.ready and ms.chosen):
                continue
            mv = ms.chosen
            if mv.shape == "quiverdance" and d <= p.attack_range + 1.5 and isinstance(target, Pokemon):
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
            if mv.shape in ("powdercloud", "powderstorm") and d <= mv.range + 0.5:
                p.pending_cast = (slot, target.pos.x, target.pos.y)
                return True
        return False
