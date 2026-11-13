"""Regole della linea Remoraid > Octillery (tiratore da duello a distanza,
danno fisico, munizioni di tipo diverso).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Venomoth: usa lo
stesso stato (self.time, self.world, self.fx_events, _combat_hash, gli
_apply_*). Il client legge la lista `octi_shots` del Match e i campi `ammo`,
`ammo_boost`, `octi_lock_ready_at` (il proprio Pokémon), `octi_lock_until`,
`octi_held_until`, `octi_grab_until`, `octi_recharge_until` delle unità.

Passive (si sommano con l'evoluzione):
  - Cecchino (Remoraid e Octillery): i brutti colpi fanno +125% invece di +75%.
  - Prendimira (Remoraid e Octillery): ogni 10 s il prossimo attacco base
    aggancia il bersaglio per 4 s. Sul bersaglio agganciato attacchi base e
    mosse della linea sono SEMPRE brutti colpi e ignorano le schivate
    (Luminpolvere, Mantelneve). Il colpo che aggancia è già un brutto colpo.
  - Ventose (Octillery): respinte, trascinamenti e lanci in aria subiti -50%.
  - L'Att. Sp. bonus degli oggetti diventa Attacco (tutto il danno è fisico).

Munizioni: attacchi base e Q hanno il tipo della munizione attiva (efficacia
dei tipi; lo STAB vale solo per l'Acqua, il tipo della linea). La W le fa
girare: Acqua e Ghiaccio dal liv.1, + Fuoco o Erba col potenziamento del liv.6.
  - Ghiaccio: -10% danno, rallenta del 20% per 1 s.
  - Fuoco: 25% di scottare per 3 s.
  - Erba: il 40% del danno ai nemici entro 1,5 tile dal bersaglio.
I gradi della W accorciano la ricarica e potenziano Ghiaccio/Fuoco/Erba.
Octillery: il primo attacco base o la prima Q dopo un cambio fa +30%.
"""
from __future__ import annotations

import math
import random

from .entities import Minion, Pokemon, Structure, Wild
from .moves import Move
from .stats import STAB_MULT
from .vec import Vec2

SNIPER_ID = "cecchino"
SUCKER_ID = "ventose"
OCTI_PASSIVES = {SNIPER_ID, SUCKER_ID}

SNIPER_CRIT = 2.25          # brutto colpo: +125% (gli altri +75%)
LOCK_CD = 10.0              # Prendimira: ogni 10 s
LOCK_DUR = 4.0              #   aggancio di 4 s
SUCKER_MULT = 0.5           # Ventose: spostamenti forzati subiti -50%
SWAP_BOOST = 1.3            # Octillery: primo colpo dopo il cambio +30%
DEFAULT_AMMO = ("Water", "Ice")


def has_octi(p) -> bool:
    return getattr(p, "passive_id", "") in OCTI_PASSIVES


def _rank_at(arr, rank, default):
    if not arr:
        return default
    return float(arr[min(max(1, rank), len(arr)) - 1])


class OctilleryMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(OCTI_PASSIVES),
        "init": "_init_octi",
        "update": "_update_octi",
        "precheck": "_octi_precheck",
        "cast": "_octi_cast",
        "bot_cast": "_bot_octi_cast",
        # Rete (net/visual.py, game/online_world.py): cosa passa al client.
        "net": {
            "lists": {"octi_shots": "pos"},
            "moving": ("octi_shots",),
            "unit_flags": {"octi_lock_by": -1},
            "me": ("ammo", "ammo_boost"),
        },
    }

    def _init_octi(self) -> None:
        self.octi_shots: list[dict] = []    # proiettili di Pistolacqua / Raffica / Colpo Perforante
        self._octi_queue: list[dict] = []   # colpi di Raffica non ancora partiti

    # --- dispatcher --------------------------------------------------------------
    def _octi_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"octishot": self._cast_octishot, "ammoswap": self._cast_ammoswap,
              "octazooka": self._cast_octazooka, "octibeam": self._cast_octibeam,
              "octigrab": self._cast_octigrab}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _octi_precheck(self, p, mv, tgt) -> bool:
        """Presa a Ventosa senza un Pokémon nemico a portata: non parte."""
        if mv.shape != "octigrab":
            return True
        return self._grab_target(p, mv, tgt) is not None

    # --- munizioni ----------------------------------------------------------------
    def _ammo_move(self, p):
        ms = p.moveset.get("W")
        if ms is None or ms.chosen is None or ms.chosen.shape != "ammoswap":
            return None, 0
        return ms.chosen, ms.rank

    def _ammo_list(self, p) -> list:
        mv, _ = self._ammo_move(p)
        if mv is None:
            return list(DEFAULT_AMMO)
        return list(mv.effects.get("ammo", DEFAULT_AMMO))

    def _ammo(self, p) -> str:
        lst = self._ammo_list(p)
        if p.ammo not in lst:
            p.ammo = lst[0]
        return p.ammo

    def _ammo_val(self, p, key, default):
        mv, rank = self._ammo_move(p)
        if mv is None:
            return default
        v = mv.effects.get(key, default)
        return _rank_at(v, rank, default) if isinstance(v, list) else float(v)

    def _cast_ammoswap(self, p, mv, rank, origin, tgt, dirv):
        lst = self._ammo_list(p)
        cur = self._ammo(p)
        p.ammo = lst[(lst.index(cur) + 1) % len(lst)]
        if p.passive_id == SUCKER_ID:
            p.ammo_boost = True   # Octillery: il primo colpo dopo il cambio +30%
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": 0.8,
                               "mtype": p.ammo, "fx": "ammoswap"})

    def _ammo_dmg_mult(self, p, ammo) -> float:
        return self._ammo_val(p, "ice_dmg", 0.9) if ammo == "Ice" else 1.0

    def _ammo_effects(self, p, tgt, dealt: float, ammo: str) -> None:
        """Effetti della munizione su un colpo a segno (attacco base o Q)."""
        if not getattr(tgt, "alive", False) and ammo != "Grass":
            return
        if ammo == "Ice" and isinstance(tgt, Pokemon) and tgt.alive:
            self._apply_slow(tgt, 1.0 - self._ammo_val(p, "ice_slow", 0.2),
                             self._ammo_val(p, "ice_dur", 1.0))
        elif ammo == "Fire" and isinstance(tgt, Pokemon) and tgt.alive:
            if random.random() < self._ammo_val(p, "fire_chance", 0.25):
                self._apply_burn(p, tgt, self._ammo_val(p, "fire_dur", 3.0))
        elif ammo == "Grass" and dealt > 0.0:
            frac = self._ammo_val(p, "grass_splash", 0.4)
            r = self._ammo_val(p, "grass_radius", 1.5)
            c = tgt.pos
            for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
                if e is tgt or e.team == p.team or not getattr(e, "alive", False):
                    continue
                if not isinstance(e, (Pokemon, Minion, Wild)):
                    continue
                if isinstance(e, Pokemon) and (e.untargetable_until > self.time or e.is_decoy):
                    continue
                if c.dist(e.pos) <= r + getattr(e, "radius", 0.0):
                    self._deal_damage(p, e, dealt * frac, dmg_type="Grass")
            self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": r,
                                   "mtype": "Grass", "fx": "octisplash"})

    # --- passive: Cecchino, Prendimira, Ventose -------------------------------------
    def _octi_convert(self, p) -> None:
        """L'Att. Sp. bonus degli oggetti diventa Attacco."""
        if not has_octi(p):
            return
        spa = p.item_bonus.pop("sp_attack", 0.0)
        if spa:
            p.item_bonus["attack"] = p.item_bonus.get("attack", 0.0) + spa

    def _crit_mult(self, caster, base: float) -> float:
        return SNIPER_CRIT if has_octi(caster) else base

    def _octi_locked(self, caster, target) -> bool:
        """Il bersaglio è agganciato (Prendimira) o afferrato (Presa a Ventosa) da `caster`."""
        if not has_octi(caster) or target is None:
            return False
        now = self.time
        if getattr(target, "octi_lock_until", -1.0) > now and target.octi_lock_by == caster.id:
            return True
        return caster.octi_grab_until > now and caster.octi_grab_id == target.id

    def _octi_crit_bonus(self, caster, target) -> float:
        return 1.0 if self._octi_locked(caster, target) else 0.0

    def _octi_disp_mult(self, u) -> float:
        """Ventose: durata/distanza degli spostamenti forzati subiti -50%."""
        return SUCKER_MULT if getattr(u, "passive_id", "") == SUCKER_ID else 1.0

    def _octi_as_bonus(self, u) -> float:
        if isinstance(u, Pokemon) and u.octi_grab_until > self.time:
            return u.octi_grab_as
        return 0.0

    # --- attacco base ------------------------------------------------------------------
    def _octi_snap(self, u, tgt, snap) -> None:
        """Al rilascio: tipo della munizione e bonus del cambio (Octillery)."""
        if not has_octi(u):
            return
        ammo = self._ammo(u)
        snap["ammo"] = ammo
        snap["mult"] *= self._ammo_dmg_mult(u, ammo)
        if u.ammo_boost:
            u.ammo_boost = False
            snap["mult"] *= SWAP_BOOST

    def _octi_before_land(self, u, tgt) -> None:
        """Prendimira: il colpo pronto aggancia il bersaglio (prima del danno)."""
        if not has_octi(u) or isinstance(tgt, Structure):
            return
        if u.octi_lock_ready_at > self.time:
            return
        if isinstance(tgt, Pokemon) and tgt.is_decoy:
            return
        tgt.octi_lock_until = self.time + LOCK_DUR
        tgt.octi_lock_by = u.id
        u.octi_lock_ready_at = self.time + LOCK_CD
        self.fx_events.append({"kind": "buff", "c": (tgt.pos.x, tgt.pos.y), "radius": 0.8,
                               "mtype": "Water", "fx": "octilock"})

    def _octi_type_mult(self, u, tgt, ammo: str) -> float:
        """Efficacia del tipo della munizione + STAB (solo se è un tipo della linea)."""
        eff = (self.types.moba_multiplier(ammo, tgt.types)
               if isinstance(tgt, Pokemon) else 1.0)
        return eff * (STAB_MULT if ammo in u.types else 1.0)

    def _octi_aa_land(self, u, tgt, snap, dmg: float) -> float:
        ammo = snap.get("ammo")
        if not ammo:
            return dmg
        return dmg * self._octi_type_mult(u, tgt, ammo)

    def _octi_after_aa(self, u, tgt, snap, dealt: float) -> None:
        ammo = snap.get("ammo")
        if ammo:
            self._ammo_effects(u, tgt, dealt, ammo)

    def _octi_ignores_dodge(self, attacker, target) -> bool:
        return self._octi_locked(attacker, target)

    # --- Q: Pistolacqua / Raffica / Colpo Perforante -------------------------------------
    def _cast_octishot(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        ammo = self._ammo(p)
        typed = Move(mv.slot, mv.max_rank, dict(mv.d, type=ammo))
        mult = self._ammo_dmg_mult(p, ammo)
        if p.passive_id == SUCKER_ID and p.ammo_boost:
            p.ammo_boost = False
            mult *= SWAP_BOOST
        mode = str(eff.get("mode", "single"))
        if mode == "burst":
            n = int(eff.get("shots", 3))
            gap = float(eff.get("gap", 0.15))
            mult *= float(eff.get("mult", 0.45))
            for i in range(n):
                self._octi_queue.append({"at": self.time + i * gap, "caster_id": p.id,
                                         "dir": Vec2(dirv.x, dirv.y), "mv": typed,
                                         "rank": rank, "mult": mult, "pierce": False})
            self._update_octi_queue()   # il primo parte subito
            return
        pierce = mode == "pierce"
        if pierce:
            mult *= float(eff.get("mult", 1.3))
        self._spawn_octishot(p, typed, rank, origin, dirv, mult, pierce)

    def _spawn_octishot(self, p, mv, rank, origin, dirv, mult, pierce) -> None:
        self.octi_shots.append({
            "pos": Vec2(origin.x, origin.y), "dir": Vec2(dirv.x, dirv.y),
            "speed": mv.speed, "left": mv.range, "radius": mv.radius,
            "team": p.team, "caster_id": p.id, "mv": mv, "rank": rank,
            "mult": mult, "pierce": pierce, "hit": set(), "ammo": mv.type,
            "big": pierce, "seed": p.cast_seq})
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": 0.5,
                               "mtype": mv.type, "fx": "octimuzzle",
                               "dir": (dirv.x, dirv.y)})

    def _update_octi_queue(self) -> None:
        if not self._octi_queue:
            return
        keep = []
        for q in self._octi_queue:
            if q["at"] > self.time + 1e-6:
                keep.append(q)
                continue
            p = self.world.get(q["caster_id"])
            if p is None or not p.alive or self._immobile(p):
                continue
            self._spawn_octishot(p, q["mv"], q["rank"], Vec2(p.pos.x, p.pos.y),
                                 q["dir"], q["mult"], q["pierce"])
        self._octi_queue = keep

    def _update_octi_shots(self, dt: float) -> None:
        if not self.octi_shots:
            return
        alive = []
        for sh in self.octi_shots:
            step = sh["speed"] * dt
            n = max(1, int(step / 0.4) + 1)   # passi corti: niente salti oltre i bersagli
            done = False
            for _ in range(n):
                sh["pos"] = sh["pos"] + sh["dir"] * (step / n)
                sh["left"] -= step / n
                if not self.world.grid.is_walkable_point(sh["pos"].x, sh["pos"].y):
                    done = True
                    break
                if self._octi_shot_hits(sh):
                    done = True
                    break
                if sh["left"] <= 0:
                    done = True
                    break
            if not done:
                alive.append(sh)
        self.octi_shots = alive

    def _octi_shot_hits(self, sh) -> bool:
        """Colpisce i nemici toccati; True se il proiettile si consuma."""
        c = sh["pos"]
        caster = self.world.get(sh["caster_id"])
        for e in self._combat_hash.query_radius(c.x, c.y, sh["radius"] + 1.0):
            if e.team == sh["team"] or not getattr(e, "alive", False) or e.id in sh["hit"]:
                continue
            if not isinstance(e, (Pokemon, Minion, Structure, Wild)):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            if c.dist(e.pos) > sh["radius"] + getattr(e, "radius", 0.0):
                continue
            sh["hit"].add(e.id)
            if caster is not None:
                before = e.hp + getattr(e, "shield", 0.0)
                self._hit(caster, sh["mv"], sh["rank"], e, mult=sh["mult"])
                dealt = max(0.0, before - e.hp - getattr(e, "shield", 0.0))
                self._ammo_effects(caster, e, dealt, sh["ammo"])
            self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": 0.5,
                                   "mtype": sh["ammo"], "fx": "octihit"})
            if not sh["pierce"]:
                return True
        return False

    # --- E: Octazooka -----------------------------------------------------------------------
    def _cast_octazooka(self, p, mv, rank, origin, tgt, dirv):
        """Spruzzo d'inchiostro a cono (accecati: gli attacchi base mancano) e
        spinta all'indietro di Octillery (3 tile, 5 con Getto Propulsore)."""
        half = math.radians(mv.angle)
        for e in self._combat_hash.query_radius(origin.x, origin.y, mv.range + 1.5):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Wild)):
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
            self._hit(p, mv, rank, e)
        self.fx_events.append({"kind": "cone", "o": (origin.x, origin.y),
                               "dir": (dirv.x, dirv.y), "range": mv.range,
                               "angle": mv.angle, "mtype": mv.type})
        back = float(mv.effects.get("backjet", 3.0))
        if back > 0 and p.dashlock_until <= self.time:
            dest = self._clamp_to_wall(origin, origin - dirv * back)
            dest, _ = self._intercept_dash(p, origin, dest)
            p.pos = dest
            p.stop()
            self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                                   "b": (dest.x, dest.y), "mtype": mv.type,
                                   "fx": "octijet"})

    # --- R: Iper Raggio -------------------------------------------------------------------------
    def _cast_octibeam(self, p, mv, rank, origin, tgt, dirv):
        """Raggio di 15 tile che attraversa tutti i nemici (fino al muro), poi
        Octillery resta fermo e senza azioni per 1,5 s (ricarica)."""
        end = self._beam_end(origin, dirv, mv.range)
        L = origin.dist(end)
        mid = (origin + end) * 0.5
        for e in self._combat_hash.query_radius(mid.x, mid.y, L * 0.5 + mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if not isinstance(e, (Pokemon, Minion, Structure, Wild)):
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
        self.fx_events.append({"kind": "projectile", "a": (origin.x, origin.y),
                               "b": (end.x, end.y), "mtype": mv.type})
        rec = float(mv.effects.get("recharge", 1.5))
        p.stun_until = max(p.stun_until, self.time + rec)   # ricarica: niente CC "nemico"
        p.octi_recharge_until = self.time + rec
        p.stop()
        p.aa_active = False

    # --- R: Presa a Ventosa -----------------------------------------------------------------------
    def _grab_target(self, p, mv, tgt):
        """Il Pokémon nemico più vicino al punto mirato, entro la portata da Octillery."""
        best, bd = None, 1e9
        for e in self._combat_hash.query_radius(p.pos.x, p.pos.y, mv.range + 1.5):
            if not isinstance(e, Pokemon) or e.team == p.team or not e.alive or e.is_decoy:
                continue
            if e.untargetable_until > self.time:
                continue
            if p.pos.dist(e.pos) > mv.range + e.radius:
                continue
            d = tgt.dist(e.pos)
            if d < bd:
                best, bd = e, d
        return best

    def _cast_octigrab(self, p, mv, rank, origin, tgt, dirv):
        e = self._grab_target(p, mv, tgt)
        if e is None:
            return
        dur = float(mv.effects.get("duration", 2.0))
        now = self.time
        p.octi_grab_until = now + dur
        p.octi_grab_id = e.id
        p.octi_grab_as = float(mv.effects.get("attack_speed", 0.5))
        p.root_until = max(p.root_until, now + dur)
        p.octi_grab_root = now + dur
        p.stop()
        p.target_id = e.id
        self._apply_root(e, dur)
        e.octi_held_until = now + dur
        e.stop()
        self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y), "radius": 1.0,
                               "mtype": "Water", "fx": "octigrab",
                               "a": (p.pos.x, p.pos.y)})

    def _octi_grabbing(self, p, dt) -> bool:
        """IA durante la Presa: attacca solo il bersaglio afferrato. True se attiva."""
        if p.octi_grab_until <= self.time:
            return False
        e = self.world.get(p.octi_grab_id)
        if (e is None or not getattr(e, "alive", False)
                or (isinstance(e, Pokemon) and e.untargetable_until > self.time)):
            self._octi_release(p)
            return False
        p.target_id = e.id
        p.stop()
        self._face(p, e)
        return True

    def _octi_release(self, p) -> None:
        e = self.world.get(p.octi_grab_id) if p.octi_grab_id is not None else None
        p.octi_grab_until = -1.0
        if abs(p.root_until - p.octi_grab_root) < 1e-6:   # solo il blocco della Presa
            p.root_until = self.time
        if e is not None:
            e.octi_held_until = -1.0

    # --- ciclo ------------------------------------------------------------------------------------
    def _update_octi(self, dt: float) -> None:
        self._update_octi_queue()
        self._update_octi_shots(dt)

    # --- bot ----------------------------------------------------------------------------------------
    def _best_ammo(self, p, target) -> str:
        lst = self._ammo_list(p)
        if not isinstance(target, Pokemon):
            return "Water" if "Water" in lst else lst[0]
        return max(lst, key=lambda a: (self._octi_type_mult(p, target, a)
                                       * self._ammo_dmg_mult(p, a), a == p.ammo))

    def _bot_octi_cast(self, p, target) -> bool:
        """Munizione più efficace contro il bersaglio e Presa a Ventosa (potenza 0)."""
        d = p.pos.dist(target.pos)
        ms = p.moveset.get("W")
        if (ms and ms.ready and ms.chosen and ms.chosen.shape == "ammoswap"
                and self._best_ammo(p, target) != self._ammo(p)):
            p.pending_cast = ("W", p.pos.x, p.pos.y)
            return True
        ms = p.moveset.get("R")
        if (ms and ms.ready and ms.chosen and ms.chosen.shape == "octigrab"
                and isinstance(target, Pokemon) and d <= ms.chosen.range + 0.3):
            p.pending_cast = ("R", target.pos.x, target.pos.y)
            return True
        return False
