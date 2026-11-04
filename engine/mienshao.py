"""Regole della linea Mienfoo > Mienshao (assassino da combo, danno fisico).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Sneasel e
Teddiursa: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge la lista del Match mien_leaps
(balzi di Calcinvolo) e i campi delle unità (parry_until, dance_until,
mien_crit_until, itemlock_until, mien_regen) per disegnare.

Passiva Maniche a Frusta + Rigenergia (stesso id per le due forme):
  - il 30% più esterno della portata degli attacchi base e di Bruciapelo è
    un PUNTO DOLCE: +40% di danno e -1 s alla ricarica di Calcinvolo;
  - dopo 4 s senza subire né infliggere danni rigenera il 3% degli HP max
    al secondo (si ferma al primo danno, subito o inflitto).
Mosse: Calcinvolo (balzo a distanza fissa: a vuoto costa HP e stordisce),
Individua (parata breve), Bruciapelo (stordisce solo dopo 4 s di calma),
R Danza delle Maniche (Q/W/E in fila senza ripetere -> colpo finale) o
Contropiede (più danno con meno HP).
Stato generico: oggetti disattivati (itemlock_until, letto da _fx_items).
"""
from __future__ import annotations

import copy
import random

from .entities import Minion, Pokemon, Structure, Wild
from .vec import Vec2

MIEN_ID = "manichefrusta"
MIEN_PASSIVES = {MIEN_ID}

SWEET_FROM = 0.70             # punto dolce: dal 70% della portata in su
SWEET_MULT = 1.40
SWEET_CDR = 1.0               # -1 s alla ricarica di Calcinvolo
CALM = 4.0                    # Rigenergia / Bruciapelo: secondi di calma
REGEN = 0.03                  # Rigenergia: 3% HP max al secondo
CRIT_HOLD = 5.0               # Individua: il brutto colpo garantito resta pronto per 5 s
JUMP_PEAK = 0.9               # altezza del balzo di Calcinvolo (tile, solo grafica)
MELEE_COUNTER = 1.8           # Contrattacco: "corpo a corpo" = bordo entro questa distanza
# Mosse che viaggiano verso il bersaglio (Guardia Rapida le blocca sugli alleati).
PROJ_SHAPES = {"projectile", "moonorb", "bubble", "fan", "arc", "spiritbeam", "swift", "armorcannon",
               "bolt", "dragonpulse", "flashcannon"}


def is_mien_line(p) -> bool:
    return getattr(p, "passive_id", None) in MIEN_PASSIVES


class MienshaoMixin:
    def _init_mien(self) -> None:
        self.mien_leaps: list[dict] = []    # Calcinvolo: balzi in volo
        self._mien_guard = False            # una Guardia Rapida è aperta (salta il giro)
        self._mien_mv_cache: dict = {}

    # --- dispatcher -----------------------------------------------------------
    def _mien_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"jumpkick": self._cast_jumpkick, "detect": self._cast_detect,
              "fakeout": self._cast_fakeout, "sleevedance": self._cast_sleevedance,
              "reversal": self._cast_reversal}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _slot_of(self, p, mv):
        for s in ("Q", "W", "E", "R"):
            ms = p.moveset.get(s)
            if ms is not None and ms.chosen is not None and ms.chosen.id == mv.id:
                return s
        return None

    # --- stato generico: oggetti disattivati (Privazione) -----------------------
    def _fx_items(self, p):
        """Gli oggetti di `p` di cui valgono gli EFFETTI UNICI (le statistiche
        restano): nessuno mentre è sotto Privazione."""
        if getattr(p, "itemlock_until", -1.0) > self.time:
            return ()
        return getattr(p, "items", ())

    # --- passiva: punto dolce, calma, Rigenergia --------------------------------
    def _sweet(self, d_edge, reach) -> bool:
        return d_edge >= SWEET_FROM * reach - 1e-6

    def _calm_for(self, p) -> float:
        """Secondi senza infliggere né subire danni (né azioni offensive)."""
        return self.time - max(p.last_dealt_at, p.last_damaged_at, p.mien_act_at)

    def _fakeout_ready(self, p) -> bool:
        ms = p.moveset.get("E")
        if ms is None or ms.chosen is None or ms.chosen.shape != "fakeout" or ms.rank <= 0:
            return False
        if p.double_until > self.time:
            return True
        return "stun" in ms.chosen.effects and self._calm_for(p) >= CALM

    def _q_cdr(self, p, secs) -> None:
        ms = p.moveset.get("Q")
        if ms is not None and ms.chosen is not None and ms.chosen.shape == "jumpkick":
            ms.cooldown_remaining = max(0.0, ms.cooldown_remaining - secs)

    def _mien_before_aa(self, u, tgt) -> None:
        """Prima del danno dell'attacco base: punto dolce e brutto colpo di Individua."""
        if not isinstance(u, Pokemon) or u.passive_id != MIEN_ID:
            return
        d = u.pos.dist(tgt.pos) - getattr(tgt, "radius", 0.0)
        u._mien_sweet = self._sweet(d, self._auto_reach(u))
        if u.mien_crit_until > self.time:
            u._force_crit = True

    def _mien_aa_mult(self, u) -> float:
        return SWEET_MULT if getattr(u, "_mien_sweet", False) else 1.0

    def _mien_after_aa(self, u, tgt) -> None:
        if not isinstance(u, Pokemon) or u.passive_id != MIEN_ID:
            return
        u.mien_act_at = self.time
        if u.mien_crit_until > self.time:
            u.mien_crit_until = -1.0
            u._force_crit = False
            self.fx_events.append({"kind": "hit", "a": (u.pos.x, u.pos.y),
                                   "b": (tgt.pos.x, tgt.pos.y), "mtype": "Fighting",
                                   "fx": "detectcrit"})
        if getattr(u, "_mien_sweet", False):
            u._mien_sweet = False
            self._q_cdr(u, SWEET_CDR)
            self.fx_events.append({"kind": "hit", "a": (u.pos.x, u.pos.y),
                                   "b": (tgt.pos.x, tgt.pos.y), "mtype": "Fighting",
                                   "fx": "sweetspot"})

    # --- Individua: parata ------------------------------------------------------
    def _mien_parry(self, attacker, target, ranged: bool) -> bool:
        """True se il colpo di `attacker` su `target` è annullato: parata di
        Individua, o Guardia Rapida di un Mienshao alleato vicino (proiettili)."""
        if (attacker is None or not isinstance(target, Pokemon) or not target.alive
                or getattr(attacker, "team", target.team) == target.team):
            return False
        now = self.time
        if target.parry_until > now:
            self._parry_success(target, attacker)
            return True
        if ranged and self._mien_guard:
            for q in self.world.pokemons():
                if (q is target or q.team != target.team or not q.alive
                        or q.parry_until <= now or not q.parry_eff):
                    continue
                r = float(q.parry_eff.get("guard_allies", 0.0))
                if r > 0.0 and q.pos.dist(target.pos) <= r:
                    self.fx_events.append({"kind": "hit", "a": (q.pos.x, q.pos.y),
                                           "b": (target.pos.x, target.pos.y),
                                           "mtype": "Fighting", "fx": "quickguard"})
                    return True
        return False

    def _mien_parry_aa(self, attacker, target) -> bool:
        """Parata contro un attacco base (torri, minion, neutrali, Pokémon)."""
        if not isinstance(target, Pokemon) or (target.parry_until <= self.time
                                               and not self._mien_guard):
            return False
        if isinstance(attacker, Structure):
            ranged = True
        elif isinstance(attacker, Minion):
            ranged = attacker.minion_type in ("caster", "cannon")
        else:
            ranged = getattr(attacker, "attack_range", 0.0) > 2.2
        return self._mien_parry(attacker, target, ranged)

    def _parry_success(self, p, attacker) -> None:
        now = self.time
        eff = p.parry_eff or {}
        p.parry_until = -1.0
        ms = p.moveset.get("Q")
        if ms is not None and ms.chosen is not None:
            ms.cooldown_remaining = 0.0        # Calcinvolo subito pronto
        p.mien_crit_until = now + CRIT_HOLD    # prossimo attacco base: brutto colpo
        self.fx_events.append({"kind": "hit", "a": (attacker.pos.x, attacker.pos.y),
                               "b": (p.pos.x, p.pos.y), "mtype": "Fighting", "fx": "parry"})
        push = float(eff.get("counter", 0.0))
        if (push > 0.0 and isinstance(attacker, (Pokemon, Minion, Wild)) and attacker.alive
                and p.pos.dist(attacker.pos) - p.radius - attacker.radius <= MELEE_COUNTER):
            d = attacker.pos - p.pos
            dirv = d.normalized() if d.length() > 1e-6 else Vec2(1.0, 0.0)
            if "iron_ball" in self._fx_items(attacker):
                push *= 0.4   # Ferropalla: respinte subite ridotte
            a = Vec2(attacker.pos.x, attacker.pos.y)
            attacker.pos = self._clamp_to_wall(a, a + dirv * push)
            attacker.stop()
            if isinstance(attacker, Pokemon):
                attacker.aa_active = False
                attacker.recalling = False
            self.fx_events.append({"kind": "hit", "a": (a.x, a.y),
                                   "b": (attacker.pos.x, attacker.pos.y), "mtype": "Fighting",
                                   "fx": "counter"})

    def _cast_detect(self, p, mv, rank, origin, tgt, dirv):
        """Individua: finestra di parata (0,5 s); ripetuta entro 6 s dall'uso
        precedente la finestra si dimezza (minimo 0,15 s)."""
        eff = mv.effects
        now = self.time
        win = float(eff.get("window", 0.5))
        if now - p.parry_cast_at <= float(eff.get("chain", 6.0)):
            win = max(float(eff.get("min_window", 0.15)), p.parry_window * 0.5)
        p.parry_window = win
        p.parry_cast_at = now
        p.parry_until = now + win
        p.parry_eff = dict(eff)
        if eff.get("guard_allies"):
            self._mien_guard = True
        self.fx_events.append({"kind": "area", "c": (origin.x, origin.y),
                               "radius": float(eff.get("guard_allies", 0.0)) or mv.radius,
                               "mtype": mv.type, "win": win})
        self._dance_step(p, "W", True)

    # --- Q: Calcinvolo ------------------------------------------------------------
    def _cast_jumpkick(self, p, mv, rank, origin, tgt, dirv):
        """Balzo a distanza FISSA nella direzione scelta (fermato dai muri)."""
        p.mien_act_at = self.time
        if p.dashlock_until > self.time:   # Cucitombra / Abbattimento: niente balzi
            return
        dest = self._clamp_to_wall(origin, origin + dirv * mv.range)
        dest, _ = self._intercept_dash(p, origin, dest)
        dur = float(mv.effects.get("leap_time", 0.45))
        p.stop()
        p.aa_active = False
        p.recalling = False
        p.stun_until = max(p.stun_until, self.time + dur)   # in volo: niente azioni
        self.mien_leaps.append({"pid": p.id, "a": Vec2(origin.x, origin.y),
                                "c": Vec2(dest.x, dest.y), "start": self.time,
                                "end": self.time + dur, "peak": JUMP_PEAK, "team": p.team,
                                "radius": mv.radius, "mv": mv, "rank": rank})
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (dest.x, dest.y), "mtype": mv.type})
        self.fx_events.append({"eid": p.id, "anim": "Hop", "anim_speed": 1.0 / max(0.2, dur)})

    def _update_mien_leaps(self) -> None:
        now = self.time
        keep = []
        for lp in self.mien_leaps:
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
            self._land_jumpkick(p, lp)
        self.mien_leaps = keep

    def _land_jumpkick(self, p, lp) -> None:
        mv, rank = lp["mv"], lp["rank"]
        eff = mv.effects
        c = p.pos
        hits = []
        for e in self._combat_hash.query_radius(c.x, c.y, mv.radius + 1.5):
            if (e.team == p.team or not getattr(e, "alive", False)
                    or not isinstance(e, (Pokemon, Minion, Wild))):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            if c.dist(e.pos) <= mv.radius + e.radius:
                hits.append(e)
        if hits:
            for e in hits:
                self._hit(p, mv, rank, e)
            t = min(hits, key=lambda e: c.dist(e.pos)).pos
            self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                                   "mtype": mv.type, "fx": "jumpkickhit", "t": (t.x, t.y)})
            self._dance_step(p, "Q", True)
            return
        # A vuoto: Mienshao si schianta (danno senza tipo, mai letale) e resta
        # stordito; Calcio Controllato invece raddoppia la ricarica.
        frac = float(eff.get("crash", 0.15))
        if frac > 0.0:
            p.hp = max(1.0, p.hp - p.max_hp * frac)
            p.last_damaged_at = self.time
        st = float(eff.get("crash_stun", 0.5))
        if st > 0.0:
            p.stop()
            p.stun_until = max(p.stun_until, self.time + st)
        ms = p.moveset.get("Q")
        mult = float(eff.get("miss_cd_mult", 1.0))
        if ms is not None and mult != 1.0:
            ms.cooldown_remaining *= mult
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "jumpkickcrash" if frac > 0.0
                               else "jumpkickmiss"})
        self._dance_step(p, "Q", False)

    # --- E: Bruciapelo ------------------------------------------------------------
    def _line_first(self, p, origin, dirv, rng, width):
        """Il primo nemico (Pokémon, minion, neutrale) lungo la linea."""
        best, bp = None, 1e9
        mid = origin + dirv * (rng * 0.5)
        for e in self._combat_hash.query_radius(mid.x, mid.y, rng * 0.5 + 1.5):
            if (e.team == p.team or not getattr(e, "alive", False)
                    or not isinstance(e, (Pokemon, Minion, Wild))):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            rel = e.pos - origin
            proj = rel.x * dirv.x + rel.y * dirv.y
            if proj < -e.radius or proj - e.radius > rng:
                continue
            perp = abs(rel.x * dirv.y - rel.y * dirv.x)
            if perp > width + e.radius:
                continue
            if proj < bp:
                best, bp = e, proj
        return best

    def _without(self, mv, key):
        """Copia della mossa senza un effetto (Bruciapelo senza stordimento)."""
        k = (mv.id, key)
        out = self._mien_mv_cache.get(k)
        if out is None:
            out = copy.copy(mv)
            out.d = dict(mv.d)
            out.d["effects"] = {kk: v for kk, v in mv.effects.items() if kk != key}
            self._mien_mv_cache[k] = out
        return out

    def _cast_fakeout(self, p, mv, rank, origin, tgt, dirv):
        """Schiaffo rapido. Stordisce solo se è la prima azione dopo 4 s di
        calma (o il rilancio di Doppio Bruciapelo), altrimenti danno basso.
        Privazione: sempre danno pieno, niente stordimento, oggetti del
        bersaglio spenti per 3 s."""
        eff = mv.effects
        now = self.time
        recast = p.double_until > now
        ready = "stun" in eff and (recast or self._calm_for(p) >= CALM)
        p.mien_act_at = now
        if recast:
            p.double_until = -1.0          # rilancio speso
        e = self._line_first(p, origin, dirv, mv.range, mv.radius)
        if e is None:
            b = origin + dirv * mv.range
            self.fx_events.append({"kind": "hit", "a": (origin.x, origin.y), "b": (b.x, b.y),
                                   "mtype": mv.type, "miss": True})
            self._dance_step(p, "E", False)
            return
        d = origin.dist(e.pos) - e.radius
        sweet = self._sweet(d, mv.range)
        mult = SWEET_MULT if sweet else 1.0
        use = mv
        if "stun" in eff and not ready:
            mult *= float(eff.get("weak", 0.4))
            use = self._without(mv, "stun")
        self._hit(p, use, rank, e, mult)
        stunned = ready and isinstance(e, Pokemon)
        if sweet:
            self._q_cdr(p, SWEET_CDR)
        lock = float(eff.get("itemlock", 0.0))
        if lock > 0.0 and isinstance(e, Pokemon):
            e.itemlock_until = max(e.itemlock_until, now + lock)
        dbl = float(eff.get("double", 0.0))
        if stunned and dbl > 0.0 and not recast:
            ms = p.moveset.get("E")
            if ms is not None:
                p.double_cd = ms.cooldown_remaining
                ms.cooldown_remaining = 0.0
                p.double_until = now + dbl
        self.fx_events.append({"kind": "hit", "a": (origin.x, origin.y),
                               "b": (e.pos.x, e.pos.y), "mtype": mv.type,
                               "stun": bool(ready), "sweet": sweet})
        if sweet:
            self.fx_events.append({"kind": "hit", "a": (origin.x, origin.y),
                                   "b": (e.pos.x, e.pos.y), "mtype": "Fighting",
                                   "fx": "sweetspot"})
        self._dance_step(p, "E", True)

    # --- R: Danza delle Maniche ----------------------------------------------------
    def _cast_sleevedance(self, p, mv, rank, origin, tgt, dirv):
        p.mien_act_at = self.time
        p.dance_until = self.time + float(mv.effects.get("duration", 6.0))
        p.dance_seq = ""
        p.dance_mv = (mv, rank)
        self.fx_events.append({"kind": "area", "c": (origin.x, origin.y), "radius": 1.2,
                               "mtype": mv.type})

    def _dance_step(self, p, slot, ok) -> None:
        """Una mossa della danza: niente ripetizioni né colpi a vuoto. Ogni mossa
        azzera la ricarica delle altre ancora da usare; la terza scatena il
        colpo finale."""
        if p.dance_until <= self.time:
            return
        if not ok or slot in p.dance_seq:
            self._dance_end(p)
            self.fx_events.append({"kind": "area", "c": (p.pos.x, p.pos.y), "radius": 0.8,
                                   "mtype": "Fighting", "fx": "dancebreak"})
            return
        p.dance_seq += slot
        for s in ("Q", "W", "E"):
            if s not in p.dance_seq:
                ms = p.moveset.get(s)
                if ms is not None:
                    ms.cooldown_remaining = 0.0
        self.fx_events.append({"kind": "area", "c": (p.pos.x, p.pos.y), "radius": 0.8,
                               "mtype": "Fighting", "fx": "dancestep", "n": len(p.dance_seq)})
        if len(p.dance_seq) >= 3:
            self._dance_finale(p)

    def _dance_finale(self, p) -> None:
        mv, rank = p.dance_mv
        self._dance_end(p)
        c = p.pos
        for e in self._combat_hash.query_radius(c.x, c.y, mv.radius + 1.5):
            if (e.team == p.team or not getattr(e, "alive", False)
                    or not isinstance(e, (Pokemon, Minion, Wild))):
                continue
            if c.dist(e.pos) <= mv.radius + e.radius:
                self._hit(p, mv, rank, e)
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "dancefinale"})
        self.fx_events.append({"eid": p.id, "anim": "Twirl"})

    def _dance_end(self, p) -> None:
        p.dance_until = -1.0
        p.dance_seq = ""
        p.dance_mv = None

    # --- R: Contropiede ------------------------------------------------------------
    def _reversal_mult(self, p, mv) -> float:
        frac = p.hp / max(1.0, p.max_hp)
        low = float(mv.effects.get("low_hp", 0.15))
        k = max(0.0, min(1.0, (1.0 - frac) / max(1e-6, 1.0 - low)))
        return 1.0 + (float(mv.effects.get("max_mult", 3.0)) - 1.0) * k

    def _cast_reversal(self, p, mv, rank, origin, tgt, dirv):
        p.mien_act_at = self.time
        e = self._line_first(p, origin, dirv, mv.range, mv.radius)
        mult = self._reversal_mult(p, mv)
        if e is None:
            b = origin + dirv * mv.range
            self.fx_events.append({"kind": "hit", "a": (origin.x, origin.y), "b": (b.x, b.y),
                                   "mtype": mv.type, "miss": True, "mult": mult})
            return
        self._hit(p, mv, rank, e, mult)
        self.fx_events.append({"kind": "hit", "a": (origin.x, origin.y),
                               "b": (e.pos.x, e.pos.y), "mtype": mv.type, "mult": mult})

    # --- tick -----------------------------------------------------------------------
    def _update_mien(self, dt: float) -> None:
        if self.mien_leaps:
            self._update_mien_leaps()
        now = self.time
        guard = False
        for p in self.world.pokemons():
            if p.parry_until > now and p.parry_eff and p.parry_eff.get("guard_allies"):
                guard = True
            if p.passive_id != MIEN_ID:
                continue
            if not p.alive:
                p.mien_regen = False
                p.parry_until = p.dance_until = -1.0
                continue
            if p.dance_until > 0.0 and p.dance_until <= now:
                self._dance_end(p)   # tempo scaduto: la danza finisce
            if p.double_until > 0.0 and p.double_until <= now:
                p.double_until = -1.0   # rilancio non usato: torna la ricarica rimasta
                ms = p.moveset.get("E")
                if ms is not None:
                    ms.cooldown_remaining = max(ms.cooldown_remaining, p.double_cd - 3.0)
            idle = now - max(p.last_damaged_at, p.last_dealt_at)
            p.mien_regen = idle >= CALM
            if p.mien_regen and p.hp < p.max_hp:
                p.hp = min(p.max_hp, p.hp + p.max_hp * REGEN * dt * self._heal_in_mult(p))
            p.fakeout_ready = self._fakeout_ready(p)
            p.mien_calm_at = max(p.last_damaged_at, p.last_dealt_at, p.mien_act_at)
        self._mien_guard = guard

    # --- bot ------------------------------------------------------------------------
    def _bot_mien_cast(self, p, target) -> bool:
        """Calcinvolo solo se il bersaglio è a ~5 tile (a vuoto fa male), Individua
        quando è sotto attacco, Bruciapelo dal punto dolce, R da vicino."""
        d = p.pos.dist(target.pos)
        now = self.time

        def ready(slot):
            ms = p.moveset.get(slot)
            return ms if ms and ms.ready and ms.chosen and ms.rank > 0 else None

        if p.dance_until > now:   # in danza: le mosse che mancano, senza ripeterne
            seq = p.dance_seq
            if "W" not in seq and ready("W"):
                p.pending_cast = ("W", p.pos.x, p.pos.y)
                return True
            ms = ready("E")
            if ("E" not in seq and ms
                    and d - getattr(target, "radius", 0.0) <= ms.chosen.range):
                p.pending_cast = ("E", target.pos.x, target.pos.y)
                return True
            if "Q" not in seq and ready("Q") and abs(d - 5.0) <= 0.8:
                p.pending_cast = ("Q", target.pos.x, target.pos.y)
                return True
            return True
        ms = ready("R")
        if ms and d <= 3.0 and isinstance(target, Pokemon):
            if ms.chosen.shape == "sleevedance" or p.hp < p.max_hp * 0.5:
                p.pending_cast = ("R", target.pos.x, target.pos.y)
                return True
        if ready("Q") and abs(d - 5.0) <= 0.8 and not isinstance(target, Structure):
            p.pending_cast = ("Q", target.pos.x, target.pos.y)
            return True
        ms = ready("W")
        if (ms and d <= 3.5 and isinstance(target, Pokemon)
                and (getattr(target, "aa_target_id", None) == p.id or random.random() < 0.03)):
            p.pending_cast = ("W", p.pos.x, p.pos.y)
            return True
        ms = ready("E")
        if ms and d - getattr(target, "radius", 0.0) <= ms.chosen.range:
            p.pending_cast = ("E", target.pos.x, target.pos.y)
            return True
        return True   # niente mosse generiche: Calcinvolo a caso si schianta
