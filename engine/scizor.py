"""Regole della linea Scyther > Scizor / Kleavor (combattente da top lane,
evoluzione ramificata TRAMITE OGGETTO).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Octillery e
Florges: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge la lista `scy_fields` (campi di
schegge, visibili a TUTTI), `scy_chops` (Taglio d'Albero in carica, a tutti)
e i campi `scy_*` delle unità.

Evoluzione (engine/evolution.py, condizione "evo_item"): dal liv.8 Scyther
evolve appena possiede Metalcoperta (-> Scizor) o Augite Nera (-> Kleavor),
anche nel negozio; con entrambi vale la prima comprata. Senza oggetto resta
Scyther (la R resta chiusa).

Passive:
  - Cuordeciso (Scyther): quando finisce uno stordimento, paralisi, sonno,
    congelamento o lancio in aria subito, +30% velocità per 2 s.
  - Tecnico (Scizor): mosse con ricarica base < 4 s fanno +40% danno (per le
    mosse a cariche conta il tempo di ricarica di una carica).
  - Asce di Pietra (Kleavor): attacchi base -20% velocità d'attacco, +40%
    danno, e colpiscono tutti i nemici in un piccolo arco davanti.

Mosse (Scyther): Q Tagliofuria (arco; ogni uso entro 3 s da uno a segno
+25% sul precedente, fino a 4 accumuli), W Focalenergia (+40% brutto colpo
per 4 s; Doppiocolpo: in più il prossimo attacco base colpisce due volte),
E Attacco d'Ala (scatto di 4 tile che si ferma sul primo nemico; Retromarcia:
poi torna indietro di 3 tile; Doppio scatto: 2 cariche).
Scizor: Q Pugnoscarica (scatto di 2 tile + pugno, non interrompibile,
interrompe cariche e canalizzazioni del colpito), R Troppoforte / Chele
d'Acciaio. Kleavor: Q Asciapietra (arco + campo di schegge), R Taglio
d'Albero / Spaccaroccia.
"""
from __future__ import annotations

import math
import random

from .entities import Minion, Pokemon, Structure, Wild
from .moves import Move
from .vec import Vec2

HEART_ID = "cuordeciso"
TECH_ID = "tecnico"
AXE_ID = "ascedipietra"
SCY_PASSIVES = {HEART_ID, TECH_ID, AXE_ID}
SCY_DEX = (123, 212, 900)
EVO_ITEMS = {"metal_coat": "Scizor", "black_augurite": "Kleavor"}

HEART_SPEED = 1.30          # Cuordeciso: +30% velocità
HEART_DUR = 2.0
TECH_CD = 4.0               # Tecnico: ricarica base sotto i 4 s
TECH_MULT = 1.40
AXE_AS = 0.80               # Asce di Pietra: -20% velocità d'attacco
AXE_DMG = 1.40              #   +40% danno
AXE_ARC = math.radians(55)  #   arco (mezza apertura) dei colpi secondari
DOUBLE_DELAY = 0.15         # secondo colpo (Doppiocolpo, Chele d'Acciaio)
FIELD_SLOW_TICK = 0.25      # i campi rinfrescano il rallentamento ogni 0,25 s
INTERRUPT_STUN = 0.1        # Pugnoscarica: micro-interruzione delle cariche


def has_scy(p) -> bool:
    return getattr(p, "passive_id", "") in SCY_PASSIVES


def _cc_now(p, now) -> bool:
    """Controlli che fanno scattare Cuordeciso quando finiscono."""
    return (p.stun_until > now or p.sleep_until > now or p.frozen_until > now
            or p.airborne_until > now or p.root_until > now and p.channel_until <= now)


def _in_cone(pos, origin, dirv, rng, half, extra=0.0) -> bool:
    rel = pos - origin
    d = rel.length()
    if d > rng + extra:
        return False
    if d < 1e-6:
        return True
    cosang = (rel.x * dirv.x + rel.y * dirv.y) / d
    return math.acos(max(-1.0, min(1.0, cosang))) <= half


class ScizorMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(SCY_PASSIVES),
        "init": "_init_scy",
        "update": "_update_scy",
        "cast": "_scy_cast",
        "bot_cast": "_bot_scy_cast",
        "speed_mult": "_scy_speed_mult",
    }

    def _init_scy(self) -> None:
        self.scy_fields: list[dict] = []    # campi di schegge (Asciapietra, Taglio d'Albero)
        self.scy_chops: list[dict] = []     # Taglio d'Albero in carica (0,5 s)
        self._scy_hits: list[dict] = []     # secondi colpi degli attacchi base

    # --- dispatcher --------------------------------------------------------------
    def _scy_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"scyfury": self._cast_scyfury, "scyfocus": self._cast_scyfocus,
              "scywing": self._cast_scywing, "scybullet": self._cast_scybullet,
              "scysuperpower": self._cast_scysuperpower, "scyclaws": self._cast_scyclaws,
              "kleaaxe": self._cast_kleaaxe, "kleachop": self._cast_kleachop,
              "kleasmash": self._cast_kleasmash}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    def _scy_foes_in_cone(self, p, origin, dirv, rng, half):
        out = []
        for e in self._combat_hash.query_radius(origin.x, origin.y, rng + 1.5):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            if _in_cone(e.pos, origin, dirv, rng, half, getattr(e, "radius", 0.0)):
                out.append(e)
        return out

    def _scy_first_on_path(self, p, origin, dest, width):
        """Primo nemico (non struttura) lungo il segmento origin -> dest."""
        best, bt = None, 1e9
        seg = dest - origin
        L2 = max(1e-9, seg.length_sq())
        for e in self._combat_hash.query_radius((origin.x + dest.x) / 2, (origin.y + dest.y) / 2,
                                                origin.dist(dest) / 2 + width + 1.5):
            if e.team == p.team or not getattr(e, "alive", False) or isinstance(e, Structure):
                continue
            if isinstance(e, Pokemon) and (e.untargetable_until > self.time):
                continue
            if self._point_seg_dist(e.pos, origin, dest) > width + getattr(e, "radius", 0.0):
                continue
            t = ((e.pos.x - origin.x) * seg.x + (e.pos.y - origin.y) * seg.y) / L2
            if t < bt:
                best, bt = e, t
        return best

    # --- Q Tagliofuria -----------------------------------------------------------
    def _cast_scyfury(self, p, mv, rank, origin, tgt, dirv):
        fx = mv.effects
        if self.time - p.scy_fury_last > float(fx.get("window", 3.0)):
            p.scy_fury_stacks = 0
        n = min(int(fx.get("max_stacks", 4)), p.scy_fury_stacks)
        mult = float(fx.get("per_stack", 1.25)) ** n
        half = math.radians(mv.angle)
        hit = False
        for e in self._scy_foes_in_cone(p, origin, dirv, mv.range, half):
            self._hit(p, mv, rank, e, mult=mult)
            if not isinstance(e, Structure):
                hit = True
        if hit:
            p.scy_fury_stacks = min(int(fx.get("max_stacks", 4)), p.scy_fury_stacks + 1)
            p.scy_fury_last = self.time
            p.scy_fury_until = self.time + float(fx.get("window", 3.0))
        else:
            p.scy_fury_stacks = 0
            p.scy_fury_until = -1.0
        self.fx_events.append({"kind": "cone", "o": (origin.x, origin.y),
                               "dir": (dirv.x, dirv.y), "range": mv.range,
                               "angle": mv.angle, "mtype": mv.type, "stacks": n,
                               "hit": hit})

    # --- W Focalenergia / Doppiocolpo ----------------------------------------------
    def _cast_scyfocus(self, p, mv, rank, origin, tgt, dirv):
        fx = mv.effects
        p.scy_focus_until = self.time + float(fx.get("duration", 4.0))
        if fx.get("double"):
            p.scy_double_ready = True
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": 1.0,
                               "mtype": mv.type, "double": bool(fx.get("double"))})

    def _scy_crit_bonus(self, caster) -> float:
        if isinstance(caster, Pokemon) and caster.scy_focus_until > self.time:
            return 0.4
        return 0.0

    # --- E Attacco d'Ala / Retromarcia / Doppio scatto -------------------------------
    def _cast_scywing(self, p, mv, rank, origin, tgt, dirv):
        if p.dashlock_until > self.time:   # Cucitombra: scatti bloccati
            return
        dest = self._clamp_to_wall(origin, origin + dirv * mv.range)
        dest, _ = self._intercept_dash(p, origin, dest)
        foe = self._scy_first_on_path(p, origin, dest, mv.radius)
        if foe is not None:
            # Si ferma davanti al primo nemico colpito.
            back = getattr(foe, "radius", 0.4) + p.radius * 0.6
            d = max(0.0, origin.dist(foe.pos) - back)
            dest = self._clamp_to_wall(origin, origin + dirv * min(d, origin.dist(dest)))
        p.pos = dest
        p.stop()
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (dest.x, dest.y), "mtype": mv.type})
        if foe is None:
            return
        self._hit(p, mv, rank, foe)
        back = float(mv.effects.get("back", 0.0))
        if back > 0.0 and p.alive:
            b0 = Vec2(p.pos.x, p.pos.y)
            b1 = self._clamp_to_wall(b0, b0 - dirv * back)
            p.pos = b1
            p.stop()
            self.fx_events.append({"kind": "dash", "a": (b0.x, b0.y), "b": (b1.x, b1.y),
                                   "mtype": mv.type, "back": True})

    # --- Scizor: Q Pugnoscarica --------------------------------------------------
    def _scy_interrupt(self, t) -> None:
        """Interrompe cariche e canalizzazioni del bersaglio (Pugnoscarica)."""
        if not isinstance(t, Pokemon) or not t.alive or self._cc_immune(t):
            return
        had = [ch for ch in self.channels if ch.get("caster_id") == t.id]
        busy = had or t.channel_until > self.time or any(
            c["caster_id"] == t.id for c in self.scy_chops)
        if not busy:
            return
        self.channels = [ch for ch in self.channels if ch not in had]
        self.scy_chops = [c for c in self.scy_chops if c["caster_id"] != t.id]
        t.channel_until = self.time
        t.root_until = min(t.root_until, self.time)
        # Le cariche delle altre linee (Elettroraggio, Armor Cannon...) si
        # annullano quando il lanciatore è immobilizzato: un istante basta.
        t.stun_until = max(t.stun_until, self.time + INTERRUPT_STUN)
        self.fx_events.append({"kind": "area", "c": (t.pos.x, t.pos.y), "radius": 0.8,
                               "mtype": "Steel", "fx": "scyinterrupt"})

    def _cast_scybullet(self, p, mv, rank, origin, tgt, dirv):
        fx = mv.effects
        p.cc_immune_until = max(p.cc_immune_until, self.time + float(fx.get("unstoppable", 0.3)))
        reach = mv.range + 0.9   # scatto + braccio del pugno
        far = self._clamp_to_wall(origin, origin + dirv * reach)
        foe = self._scy_first_on_path(p, origin, far, mv.radius)
        if foe is not None:
            stop = max(0.0, origin.dist(foe.pos) - getattr(foe, "radius", 0.4) - p.radius * 0.5)
            dest = origin + dirv * min(mv.range, stop)
        else:
            dest = origin + dirv * mv.range
        if p.dashlock_until <= self.time:
            dest = self._clamp_to_wall(origin, dest)
            p.pos = dest
            p.stop()
        else:
            dest = origin
        self.fx_events.append({"kind": "dash", "a": (origin.x, origin.y),
                               "b": (dest.x, dest.y), "mtype": mv.type})
        if foe is None or dest.dist(foe.pos) > 1.6 + getattr(foe, "radius", 0.0):
            return
        self._hit(p, mv, rank, foe)
        if fx.get("interrupt"):
            self._scy_interrupt(foe)
        self.fx_events.append({"kind": "attack", "a": (dest.x, dest.y),
                               "b": (foe.pos.x, foe.pos.y), "mtype": mv.type,
                               "melee": True, "fx": "scypunch"})

    # --- Scizor: R ----------------------------------------------------------------
    def _cast_scysuperpower(self, p, mv, rank, origin, tgt, dirv):
        half = math.radians(mv.angle)
        foes = self._scy_foes_in_cone(p, origin, dirv, mv.range, half)
        for e in foes:
            self._hit(p, mv, rank, e)
        sd = mv.effects.get("self_down", {})
        p.scy_down_until = self.time + float(sd.get("duration", 4.0))
        tip = origin + dirv * min(mv.range * 0.6, 1.4)
        self.fx_events.append({"kind": "area", "c": (tip.x, tip.y), "radius": 1.0,
                               "mtype": mv.type, "a": (origin.x, origin.y),
                               "hit": bool(foes)})

    def _cast_scyclaws(self, p, mv, rank, origin, tgt, dirv):
        p.scy_claws_until = self.time + float(mv.effects.get("duration", 6.0))
        p.attack_timer = 0.0   # il primo colpo parte subito
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": 1.0,
                               "mtype": mv.type})

    # --- Kleavor: Q Asciapietra e campi di schegge ---------------------------------
    def _scy_field(self, p, mv, rank, fx, **shape) -> dict:
        # I tick del campo fanno solo danno: copia della mossa SENZA effetti
        # (Taglio d'Albero non rilancia in aria a ogni secondo).
        tick_mv = Move(mv.slot, mv.max_rank, {**mv.d, "effects": {}})
        f = {"id": random.randrange(1 << 30), "team": p.team, "owner": p.id,
             "mv": tick_mv, "rank": rank, "end": self.time + float(fx.get("duration", 6.0)),
             "born": self.time, "tick": float(fx.get("tick", 1.0)),
             "tick_mult": float(fx.get("tick_mult", 0.2)), "slow": float(fx.get("slow", 0.8)),
             "self_def": float(fx.get("self_def", 1.2)), "next": self.time + 1.0,
             "next_slow": self.time}
        f.update(shape)
        self.scy_fields.append(f)
        return f

    def _cast_kleaaxe(self, p, mv, rank, origin, tgt, dirv):
        half = math.radians(mv.angle)
        foes = self._scy_foes_in_cone(p, origin, dirv, mv.range, half)
        for e in foes:
            self._hit(p, mv, rank, e)
        fd = mv.effects.get("field", {})
        c = self._clamp_to_wall(origin, origin + dirv * min(1.6, mv.range))
        self._scy_field(p, mv, rank, fd, kind="circle", c=Vec2(c.x, c.y),
                        r=float(fd.get("radius", 2.0)))
        self.fx_events.append({"kind": "cone", "o": (origin.x, origin.y),
                               "dir": (dirv.x, dirv.y), "range": mv.range,
                               "angle": mv.angle, "mtype": mv.type, "c": (c.x, c.y)})

    def _in_field(self, f, pos, extra=0.0) -> bool:
        if f["kind"] == "circle":
            return f["c"].dist(pos) <= f["r"] + extra
        return _in_cone(pos, f["o"], f["dir"], f["range"], f["half"], extra)

    def _update_fields(self) -> None:
        now = self.time
        keep = []
        for f in self.scy_fields:
            if now >= f["end"]:
                continue
            keep.append(f)
            owner = self.world.get(f["owner"])
            if owner is None:
                continue
            if f["kind"] == "circle":
                cx, cy, R = f["c"].x, f["c"].y, f["r"]
            else:
                mid = f["o"] + f["dir"] * (f["range"] * 0.5)
                cx, cy, R = mid.x, mid.y, f["range"] * 0.6 + 0.5
            dmg_tick = now >= f["next"]
            slow_tick = now >= f["next_slow"]
            if dmg_tick:
                f["next"] += f["tick"]
            if slow_tick:
                f["next_slow"] = now + FIELD_SLOW_TICK
            if not (dmg_tick or slow_tick):
                continue
            for e in self._combat_hash.query_radius(cx, cy, R + 1.0):
                if e.team == f["team"] or not getattr(e, "alive", False):
                    continue
                if not isinstance(e, (Pokemon, Minion, Wild)):
                    continue
                if not self._in_field(f, e.pos, getattr(e, "radius", 0.0)):
                    continue
                if isinstance(e, Pokemon) and e.untargetable_until > now:
                    continue
                if dmg_tick and getattr(owner, "alive", False):
                    self._hit(owner, f["mv"], f["rank"], e, mult=f["tick_mult"])
                if slow_tick and isinstance(e, Pokemon) and e.alive:
                    self._apply_slow(e, f["slow"], FIELD_SLOW_TICK + 0.15)
        self.scy_fields = keep

    # --- Kleavor: R ---------------------------------------------------------------
    def _cast_kleachop(self, p, mv, rank, origin, tgt, dirv):
        delay = float(mv.effects.get("delay", 0.5))
        p.stop()
        p.channel_until = self.time + delay
        p.root_until = max(p.root_until, self.time + delay)
        self.scy_chops.append({"caster_id": p.id, "mv": mv, "rank": rank, "t": self.time + delay,
                               "start": self.time, "o": Vec2(origin.x, origin.y),
                               "dir": Vec2(dirv.x, dirv.y), "range": mv.range,
                               "angle": mv.angle, "team": p.team})
        self.fx_events.append({"kind": "cone", "o": (origin.x, origin.y), "dir": (dirv.x, dirv.y),
                               "range": mv.range, "angle": mv.angle, "mtype": mv.type,
                               "tele": delay})

    def _update_chops(self) -> None:
        keep = []
        for c in self.scy_chops:
            p = self.world.get(c["caster_id"])
            if p is None or not p.alive:
                continue
            if self._immobile(p) and self.time < c["t"]:
                p.channel_until = self.time   # interrotto: niente colpo (ricarica spesa)
                p.root_until = self.time
                continue
            if self.time < c["t"]:
                keep.append(c)
                continue
            mv, rank = c["mv"], c["rank"]
            o, d = c["o"], c["dir"]
            half = math.radians(mv.angle)
            for e in self._scy_foes_in_cone(p, o, d, mv.range, half):
                self._hit(p, mv, rank, e)   # lancio in aria di 1 s (effetto "airborne")
            fd = mv.effects.get("field", {})
            self._scy_field(p, mv, rank, fd, kind="cone", o=Vec2(o.x, o.y), dir=Vec2(d.x, d.y),
                            range=mv.range, half=half, angle=mv.angle)
            p.channel_until = self.time
            p.root_until = self.time
            self.fx_events.append({"kind": "cone", "o": (o.x, o.y), "dir": (d.x, d.y),
                                   "range": mv.range, "angle": mv.angle, "mtype": mv.type,
                                   "fx": "kleachophit", "src": p.id, "move": mv.id})
        self.scy_chops = keep

    def _cast_kleasmash(self, p, mv, rank, origin, tgt, dirv):
        p.scy_smash_until = self.time + float(mv.effects.get("duration", 6.0))
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": 1.0,
                               "mtype": mv.type})

    def _smash_fx(self, p):
        ms = p.moveset.get("R")
        mv = ms.chosen if ms is not None else None
        if mv is not None and mv.shape == "kleasmash":
            return mv.effects
        return {"per_hit": 0.08, "max": 0.40, "shred_dur": 4.0}

    # --- attacchi base ----------------------------------------------------------------
    def _scy_as_bonus(self, u) -> float:
        """Chele d'Acciaio: +25% velocità d'attacco."""
        if getattr(u, "scy_claws_until", -1.0) > self.time:
            ms = u.moveset.get("R")
            mv = ms.chosen if ms is not None else None
            return float(mv.effects.get("attack_speed", 0.25)) if mv is not None else 0.25
        return 0.0

    def _scy_as_mult(self, u) -> float:
        return AXE_AS if getattr(u, "passive_id", "") == AXE_ID else 1.0

    def _scy_aa_mult(self, u) -> float:
        return AXE_DMG if getattr(u, "passive_id", "") == AXE_ID else 1.0

    def _scy_after_aa(self, u, tgt) -> None:
        if not isinstance(u, Pokemon):
            return
        now = self.time
        wait = DOUBLE_DELAY
        if u.scy_double_ready:   # Doppiocolpo: secondo colpo pieno
            u.scy_double_ready = False
            self._scy_hits.append({"t": now + wait, "src": u.id, "tgt": tgt.id, "mult": 1.0})
            wait += DOUBLE_DELAY
        if u.scy_claws_until > now:   # Chele d'Acciaio: secondo colpo al 60%
            ms = u.moveset.get("R")
            mv = ms.chosen if ms is not None else None
            m2 = float(mv.effects.get("second_mult", 0.6)) if mv is not None else 0.6
            self._scy_hits.append({"t": now + wait, "src": u.id, "tgt": tgt.id, "mult": m2})
        if u.passive_id == AXE_ID:
            self._axe_cleave(u, tgt)
        if (u.scy_smash_until > now and isinstance(tgt, Pokemon) and tgt.alive
                and tgt.team != u.team):
            fx = self._smash_fx(u)
            per, mx = float(fx.get("per_hit", 0.08)), float(fx.get("max", 0.4))
            if tgt.scy_shred_until <= now:
                tgt.scy_shred = 0
            tgt.scy_shred = min(int(round(mx / per)), tgt.scy_shred + 1)
            tgt.scy_shred_until = now + float(fx.get("shred_dur", 4.0))
            self._scy_stat_mults(tgt)
            self.fx_events.append({"kind": "area", "c": (tgt.pos.x, tgt.pos.y), "radius": 0.6,
                                   "mtype": "Fighting", "fx": "kleashred",
                                   "n": tgt.scy_shred})

    def _axe_cleave(self, u, tgt) -> None:
        """Asce di Pietra: anche gli altri nemici nel piccolo arco davanti."""
        to = tgt.pos - u.pos
        if to.length() < 1e-6:
            return
        d = to.normalized()
        rng = self._auto_reach(u) + u.radius + 0.4
        for e in self._combat_hash.query_radius(u.pos.x, u.pos.y, rng + 1.0):
            if (e is tgt or e.team == u.team or not getattr(e, "alive", False)
                    or not isinstance(e, (Pokemon, Minion, Wild))):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            if not _in_cone(e.pos, u.pos, d, rng, AXE_ARC, getattr(e, "radius", 0.0)):
                continue
            dmg = self._basic_damage(u, e) * AXE_DMG
            self._deal_damage(u, e, dmg)
            self._vamp(u, dmg, physical=True)
        self.fx_events.append({"kind": "cone", "o": (u.pos.x, u.pos.y), "dir": (d.x, d.y),
                               "range": rng, "angle": math.degrees(AXE_ARC), "mtype": "Rock",
                               "fx": "kleacleavearc"})

    def _update_scy_hits(self) -> None:
        keep = []
        for h in self._scy_hits:
            if self.time < h["t"]:
                keep.append(h)
                continue
            u, t = self.world.get(h["src"]), self.world.get(h["tgt"])
            if (u is None or t is None or not u.alive or not getattr(t, "alive", False)
                    or (isinstance(t, Pokemon) and t.untargetable_until > self.time)
                    or u.pos.dist(t.pos) > self._aa_reach(u, t) + 0.8):
                continue
            dmg = self._basic_damage(u, t) * h["mult"]
            self._deal_damage(u, t, dmg)
            self._vamp(u, dmg, physical=True)
            self.fx_events.append({"kind": "attack", "a": (u.pos.x, u.pos.y),
                                   "b": (t.pos.x, t.pos.y), "mtype": u.types[0] if u.types else "Bug",
                                   "melee": True, "fx": u.attack_fx, "second": True})
        self._scy_hits = keep

    # --- danno ----------------------------------------------------------------------
    def _scy_move_mult(self, caster, mv, rank) -> float:
        """Tecnico (Scizor): +40% alle mosse con ricarica base sotto i 4 s."""
        if getattr(caster, "passive_id", "") != TECH_ID or mv.power_at(rank) <= 0:
            return 1.0
        base = mv.charge_time if mv.charges > 0 else mv.cooldown_at(rank)
        return TECH_MULT if base < TECH_CD else 1.0

    def _scy_on_dealt(self, attacker, target, amount) -> None:
        """Chele d'Acciaio: si cura del 10% del danno inflitto ai nemici."""
        if (not isinstance(attacker, Pokemon) or attacker.scy_claws_until <= self.time
                or amount <= 0.0 or not attacker.alive or target.team == attacker.team):
            return
        ms = attacker.moveset.get("R")
        mv = ms.chosen if ms is not None else None
        frac = float(mv.effects.get("heal_frac", 0.1)) if mv is not None else 0.1
        attacker.hp = min(attacker.max_hp,
                          attacker.hp + amount * frac * self._heal_in_mult(attacker))

    def _scy_speed_mult(self, p) -> float:
        return HEART_SPEED if p.scy_heart_until > self.time else 1.0

    # --- stato per tick ------------------------------------------------------------------
    def _scy_stat_mults(self, p) -> None:
        now = self.time
        down = p.scy_down_until > now
        shred = p.scy_shred if p.scy_shred_until > now else 0
        if p.scy_shred_until <= now:
            p.scy_shred = 0
        field = 1.0
        if p.passive_id == AXE_ID and p.alive:
            for f in self.scy_fields:
                if f["owner"] == p.id and self._in_field(f, p.pos, p.radius * 0.5):
                    field = f["self_def"]
                    break
        p.scy_infield = field > 1.0
        p.scy_atk_mult = 0.8 if down else 1.0
        p.scy_def_mult = (0.8 if down else 1.0) * field * (1.0 - 0.08 * shred)
        p.scy_spdef_mult = field

    def _update_scy(self, dt: float) -> None:
        now = self.time
        self._update_chops()
        self._update_fields()
        self._update_scy_hits()
        for p in self.world.pokemons():
            if p.passive_id == HEART_ID:
                cc = p.alive and _cc_now(p, now)
                if p.scy_was_cc and not cc and p.alive:
                    p.scy_heart_until = now + HEART_DUR
                    self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y),
                                           "radius": 0.8, "mtype": "Flying", "fx": "scyheart"})
                p.scy_was_cc = cc
            if (p.scy_down_until > -1.0 or p.scy_shred or p.scy_shred_until > -1.0
                    or p.passive_id == AXE_ID or p.scy_atk_mult != 1.0
                    or p.scy_def_mult != 1.0 or p.scy_spdef_mult != 1.0):
                self._scy_stat_mults(p)
            if (p.is_bot and has_scy(p) and not p.__dict__.get("_scy_bot_item")):
                # I bot scelgono a caso il ramo: tengono uno solo dei due oggetti.
                p.__dict__["_scy_bot_item"] = True
                drop = random.choice(tuple(EVO_ITEMS))
                base = list(p.rec_items or [])
                p.rec_items = [i for i in base if i != drop]

    # --- bot ------------------------------------------------------------------------------
    def _bot_scy_cast(self, p, target) -> bool:
        """W (Focalenergia/Doppiocolpo), Chele d'Acciaio e Spaccaroccia hanno
        potenza 0: il ciclo generico non le lancerebbe. Le usa in mischia."""
        d = p.pos.dist(target.pos)
        if d > 2.6 or not isinstance(target, (Pokemon, Wild, Minion)):
            return False
        for slot in ("R", "W"):
            ms = p.moveset.get(slot)
            mv = ms.chosen if ms is not None else None
            if (mv is not None and ms.ready and ms.rank > 0 and mv.target == "self"
                    and mv.shape in ("scyfocus", "scyclaws", "kleasmash")):
                if slot == "R" and not isinstance(target, Pokemon):
                    continue
                p.pending_cast = (slot, p.pos.x, p.pos.y)
                return True
        return False
