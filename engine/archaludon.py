"""Regole della linea Duraludon > Archaludon (supporto che bersaglia da
lontano, sinergia con la pioggia).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Mienshao e
Noivern: usa lo stesso stato (self.time, self.world, self.fx_events,
_combat_hash, gli _apply_*). Il client legge le liste del Match (wave_zones,
beam_charges, thunder_marks) e i campi delle unità (arch_spa_until,
thunder_until, thunder_left, beam_charge_until) per disegnare.

Passiva Conduzione (stesso id per le due forme), sotto la pioggia (meteo
Pioggia, aura di Politoad, Pioggiadanza):
  - i tempi di carica e i ritardi delle sue mosse sono dimezzati;
  - le sue mosse Elettro rallentano del 25% per 1,5 s i nemici colpiti.
Mosse: Cannonflash (proiettile lungo, -15% Dif. Sp. al primo colpito; Tiro
Lungo si carica tenendo premuto, Raffica ha 2 cariche), Tuononda (area a
distanza che paralizza dopo 0,75 s; Fulmine fa danno, Tuononda + è più
grande), Codadrago (respinge di 4 tile; Ferrosuono = area di -30% Dif. Sp.,
Ferroscudo = scudo e +30% Difesa a un alleato), R Elettroraggio (carica di
1,5 s, poi raggio di 25 tile; sotto la pioggia spara subito) o Tuono (fino a
3 fulmini ritardati entro 5 s).
"""
from __future__ import annotations

import copy
import random

from .entities import Minion, Pokemon, Structure
from .vec import Vec2

CONDUCT_ID = "conduzione"
ARCH_PASSIVES = {CONDUCT_ID}

RAIN_TIME = 0.5               # sotto la pioggia: cariche e ritardi dimezzati
RAIN_SLOW = 0.75              # mosse Elettro sotto la pioggia: -25% velocità
RAIN_SLOW_DUR = 1.5
RECAST_GAP = 0.3              # Tuono: pausa minima tra due fulmini
TAIL_ARC = 0.55               # Codadrago: coseno minimo verso la mira (~57°)
SHAKE_DUR = 0.6               # Elettroraggio: tremolio dello schermo (per tutti)


def is_arch_line(p) -> bool:
    return getattr(p, "passive_id", None) in ARCH_PASSIVES


class ArchaludonMixin:
    # Agganci al Match (registro in engine/lines.py): nome dell'aggancio ->
    # metodo di questa classe. "passives" = passive della linea (IA dei bot).
    LINE = {
        "passives": frozenset(ARCH_PASSIVES),
        "init": "_init_arch",
        "update": "_update_arch",
        "cast": "_arch_cast",
        "bot_cast": "_bot_arch_cast",
    }

    def _init_arch(self) -> None:
        self.wave_zones: list[dict] = []     # Tuononda: aree che scattano dopo il ritardo
        self.beam_charges: list[dict] = []   # Elettroraggio: carica visibile ai nemici
        self.thunder_marks: list[dict] = []  # Tuono: fulmini in arrivo
        self._arch_mv_cache: dict = {}

    # --- dispatcher -----------------------------------------------------------
    def _arch_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"flashcannon": self._cast_flashcannon, "thunderwave": self._cast_thunderwave,
              "dragontail": self._cast_dragontail, "metalsound": self._cast_metalsound,
              "irondefense": self._cast_irondefense, "electroshot": self._cast_electroshot,
              "thunderstorm": self._cast_thunderstorm}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    # --- passiva: Conduzione ----------------------------------------------------
    def _arch_rain(self, p) -> bool:
        """Conduzione attiva: Pokémon della linea sotto la pioggia."""
        return is_arch_line(p) and self._raining_at(p.pos)

    def _arch_time(self, p, t: float) -> float:
        """Tempo di carica / ritardo, dimezzato sotto la pioggia."""
        return t * RAIN_TIME if self._arch_rain(p) else t

    def _arch_hit(self, p, mv, rank, e, rain: bool, mult: float = 1.0) -> None:
        """_hit con le regole della linea: +Att. Sp. della carica di Elettroraggio
        sulle mosse speciali e rallentamento delle mosse Elettro sotto la pioggia."""
        if mv.category == "special" and p.arch_spa_until > self.time:
            mult *= p.arch_spa_mult
        self._hit(p, mv, rank, e, mult)
        if (rain and mv.type == "Electric" and isinstance(e, Pokemon) and e.alive
                and e.team != p.team):
            self._apply_slow(e, RAIN_SLOW, RAIN_SLOW_DUR)

    def _arch_enemies(self, p, c, r):
        """Nemici colpibili (campioni, minion, neutrali, strutture) entro r da c."""
        out = []
        for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            if c.dist(e.pos) > r + getattr(e, "radius", 0.0):
                continue
            if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                continue
            out.append(e)
        return out

    def _arch_clamp(self, origin, tgt, rng):
        to = tgt - origin
        if to.length() > rng:
            return origin + to.normalized() * rng
        return Vec2(tgt.x, tgt.y)

    # --- Q: Cannonflash -----------------------------------------------------------
    def _arch_line_first(self, p, origin, dirv, rng, radius, pierce=False):
        """Primo nemico sulla linea (fermato dai muri, salvo `pierce`)."""
        best, best_proj = None, rng + 1.0
        mid = origin + dirv * (rng * 0.5)
        for e in self._combat_hash.query_radius(mid.x, mid.y, rng * 0.5 + radius + 2.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            rel = e.pos - origin
            proj = rel.x * dirv.x + rel.y * dirv.y
            if proj < 0 or proj > rng:
                continue
            perp = abs(rel.x * (-dirv.y) + rel.y * dirv.x)
            if perp > radius + getattr(e, "radius", 0.0):
                continue
            if not pierce and not self.world.grid.line_of_sight(origin.x, origin.y,
                                                                e.pos.x, e.pos.y):
                continue
            if proj < best_proj:
                best_proj, best = proj, e
        return best, best_proj

    def _cast_flashcannon(self, p, mv, rank, origin, tgt, dirv):
        """Proiettile a lunga distanza: il primo nemico colpito ha la Dif. Sp.
        ridotta. Tiro Lungo: la pressione tenuta (cast_hold) carica fino a +40%
        di portata e +50% di danno (carica piena dimezzata sotto la pioggia)."""
        hold = mv.effects.get("hold")
        frac = 0.0
        if hold:
            full = self._arch_time(p, float(hold.get("time", 1.0)))
            frac = max(0.0, min(1.0, p.cast_hold / max(0.05, full)))
        p.cast_hold = 0.0
        rng = mv.range * (1.0 + (float(hold.get("range", 0.4)) * frac if hold else 0.0))
        mult = 1.0 + (float(hold.get("power", 0.5)) * frac if hold else 0.0)
        best, proj = self._arch_line_first(p, origin, dirv, rng, mv.radius, mv.wall_pierce)
        end = origin + dirv * (proj if best is not None else rng)
        if best is not None:
            self._arch_hit(p, mv, rank, best, self._arch_rain(p), mult)
        self.fx_events.append({"kind": "projectile", "a": (origin.x, origin.y),
                               "b": (end.x, end.y), "mtype": mv.type, "fx": "flashcannon",
                               "charge": round(frac, 2), "hit": best is not None})

    # --- W: Tuononda ----------------------------------------------------------------
    def _cast_thunderwave(self, p, mv, rank, origin, tgt, dirv):
        """Area a distanza che scatta dopo il ritardo (dimezzato sotto la pioggia):
        paralizza (Tuononda) o fa danno Elettro (Fulmine)."""
        c = self._arch_clamp(origin, tgt, mv.range)
        delay = self._arch_time(p, float(mv.effects.get("delay", 0.75)))
        self.wave_zones.append({"c": c, "radius": mv.radius, "team": p.team,
                                "caster_id": p.id, "start": self.time,
                                "at": self.time + delay, "mv": mv, "rank": rank,
                                "rain": self._arch_rain(p), "dmg": mv.power_at(rank) > 0})
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": mv.radius,
                               "mtype": mv.type, "fx": "wavecast", "delay": delay})

    def _update_wave_zones(self) -> None:
        now = self.time
        keep = []
        for z in self.wave_zones:
            if now < z["at"]:
                keep.append(z)
                continue
            p = self.world.get(z["caster_id"])
            if p is None:
                continue
            mv = z["mv"]
            for e in self._arch_enemies(p, z["c"], z["radius"]):
                self._arch_hit(p, mv, z["rank"], e, z["rain"])
            self.fx_events.append({"kind": "area", "c": (z["c"].x, z["c"].y),
                                   "radius": z["radius"], "mtype": "Electric",
                                   "fx": "waveburst", "dmg": z["dmg"]})
        self.wave_zones = keep

    # --- E: Codadrago / Ferrosuono / Ferroscudo ---------------------------------------
    def _cast_dragontail(self, p, mv, rank, origin, tgt, dirv):
        """Colpo di coda sul nemico più vicino davanti a sé: danno e respinta."""
        push = float(mv.effects.get("push", 4.0))
        best, bd = None, 1e9
        for e in self._arch_enemies(p, origin, mv.range):
            rel = e.pos - origin
            d = rel.length()
            if d > 1e-6 and (rel.x * dirv.x + rel.y * dirv.y) / d < TAIL_ARC:
                continue
            if d < bd:
                best, bd = e, d
        self.fx_events.append({"kind": "cone", "o": (origin.x, origin.y),
                               "dir": (dirv.x, dirv.y), "range": mv.range, "angle": 55,
                               "mtype": mv.type, "fx": "tailswipe"})
        if best is None:
            return
        self._arch_hit(p, mv, rank, best, self._arch_rain(p))
        if (not best.alive or not isinstance(best, (Pokemon, Minion))
                or (isinstance(best, Pokemon) and self._cc_immune(best))):
            return
        away = best.pos - origin
        if away.length() < 1e-6:
            away = dirv
        a = Vec2(best.pos.x, best.pos.y)
        if isinstance(best, Pokemon) and "iron_ball" in self._fx_items(best):
            from .item_effects import IRONBALL_MULT
            push *= IRONBALL_MULT
        push *= self._octi_disp_mult(best)   # Ventose
        dest = self._clamp_to_wall(a, a + away.normalized() * push)
        best.pos = dest
        best.stop()
        if isinstance(best, Pokemon):
            best.aa_active = False
            best.recalling = False
        self.fx_events.append({"kind": "dash", "a": (a.x, a.y), "b": (dest.x, dest.y),
                               "mtype": mv.type, "fx": "tailpush"})

    def _cast_metalsound(self, p, mv, rank, origin, tgt, dirv):
        """Stridio metallico attorno a sé: Dif. Sp. dei nemici ridotta."""
        for e in self._arch_enemies(p, origin, mv.radius):
            self._arch_hit(p, mv, rank, e, self._arch_rain(p))
        self.fx_events.append({"kind": "area", "c": (origin.x, origin.y),
                               "radius": mv.radius, "mtype": mv.type, "fx": "metalsound"})

    def _cast_irondefense(self, p, mv, rank, origin, tgt, dirv):
        """Scudo e +Difesa all'alleato più vicino al punto mirato entro la
        portata (sé stesso se non ce n'è nessuno)."""
        eff = mv.effects
        best, bd = p, 1e9
        for a in self.world.pokemons():
            if a.team != p.team or not a.alive or a is p:
                continue
            if origin.dist(a.pos) > mv.range + a.radius:
                continue
            d = tgt.dist(a.pos)
            if d < bd:
                best, bd = a, d
        sh = eff.get("shield", [80])
        amt = float(sh[min(len(sh) - 1, max(0, rank - 1))]) if isinstance(sh, list) else float(sh)
        amt += float(eff.get("shield_ratio", 0.0)) * p.eff_sp_attack()
        dur = float(eff.get("duration", 3.0))
        self._give_shield(p, best, amt, dur)
        self._apply_def_buff(best, float(eff.get("def_mult", 1.3)), dur)
        self.fx_events.append({"kind": "buff", "c": (best.pos.x, best.pos.y), "radius": 1.0,
                               "a": (origin.x, origin.y), "b": (best.pos.x, best.pos.y),
                               "mtype": mv.type, "fx": "irondefense", "eid2": best.id})

    # --- R: Elettroraggio -----------------------------------------------------------------
    def _cast_electroshot(self, p, mv, rank, origin, tgt, dirv):
        """Carica (visibile ai nemici, +Att. Sp. per qualche secondo), poi raggio
        dritto lunghissimo che attraversa tutto. Sotto la pioggia spara subito."""
        eff = mv.effects
        p.arch_spa_mult = float(eff.get("spa_mult", 1.3))
        p.arch_spa_until = self.time + float(eff.get("spa_dur", 4.0))
        charge = 0.0 if self._arch_rain(p) else float(eff.get("charge", 1.5))
        if charge <= 0.0:
            self._fire_electroshot(p, mv, rank, origin, dirv)
            return
        p.stop()
        p.channel_until = self.time + charge
        p.beam_charge_until = self.time + charge
        self._apply_speed(p, 0.0, charge)          # fermo mentre carica
        end = origin + dirv * mv.range
        self.beam_charges.append({"pos": Vec2(origin.x, origin.y), "dir": Vec2(dirv.x, dirv.y),
                                  "end": end, "team": p.team, "caster_id": p.id,
                                  "start": self.time, "at": self.time + charge,
                                  "mv": mv, "rank": rank})

    def _update_beam_charges(self) -> None:
        now = self.time
        keep = []
        for ch in self.beam_charges:
            p = self.world.get(ch["caster_id"])
            if p is None or not p.alive or self._immobile(p):
                if p is not None:              # interrotto: si ferma la carica
                    p.channel_until = p.beam_charge_until = now
                    p.speed_until = min(p.speed_until, now)
                continue
            if now < ch["at"]:
                keep.append(ch)
                continue
            self._fire_electroshot(p, ch["mv"], ch["rank"], Vec2(p.pos.x, p.pos.y), ch["dir"])
        self.beam_charges = keep

    def _fire_electroshot(self, p, mv, rank, origin, dirv):
        L = mv.range
        end = origin + dirv * L
        rain = self._arch_rain(p)
        mid = (origin + end) * 0.5
        for e in self._combat_hash.query_radius(mid.x, mid.y, L * 0.5 + mv.radius + 1.0):
            if e.team == p.team or not getattr(e, "alive", False):
                continue
            rel = e.pos - origin
            proj = rel.x * dirv.x + rel.y * dirv.y
            if proj < -0.3 or proj > L + 0.3:
                continue
            perp = abs(rel.x * (-dirv.y) + rel.y * dirv.x)
            if perp <= mv.radius + getattr(e, "radius", 0.0):
                if isinstance(e, Pokemon) and e.untargetable_until > self.time:
                    continue
                self._arch_hit(p, mv, rank, e, rain)
        self.fx_events.append({"kind": "beam", "a": (origin.x, origin.y), "b": (end.x, end.y),
                               "c": (mid.x, mid.y), "mtype": "Electric", "fx": "electroshot",
                               "radius": mv.radius})
        self.fx_events.append({"kind": "shake", "dur": SHAKE_DUR, "fx": "shake"})
        self.fx_events.append({"eid": p.id, "anim": "Shoot"})

    # --- R: Tuono ---------------------------------------------------------------------------
    def _cast_thunderstorm(self, p, mv, rank, origin, tgt, dirv):
        """Fino a 3 fulmini su punti scelti entro 5 s: ognuno cade dopo il ritardo
        (dimezzato sotto la pioggia), fa danno e può paralizzare. Sotto la pioggia
        le aree sono più grandi del 50%."""
        eff = mv.effects
        ms = p.moveset.get("R")
        if p.thunder_left > 0 and p.thunder_until > self.time:
            p.thunder_left -= 1                       # rilancio dentro la finestra
        else:
            p.thunder_left = int(eff.get("bolts", 3)) - 1
            p.thunder_until = self.time + float(eff.get("window", 5.0))
            p.thunder_cd = ms.cooldown_remaining if ms is not None else 0.0
        if ms is not None:
            if p.thunder_left > 0:
                ms.cooldown_remaining = RECAST_GAP     # altri fulmini da lanciare
            else:
                ms.cooldown_remaining = p.thunder_cd
                p.thunder_until = -1.0
        rain = self._arch_rain(p)
        r = mv.radius * (float(eff.get("rain_mult", 1.5)) if rain else 1.0)
        c = self._arch_clamp(origin, tgt, mv.range)
        delay = self._arch_time(p, float(eff.get("delay", 0.75)))
        self.thunder_marks.append({"c": c, "radius": r, "team": p.team, "caster_id": p.id,
                                   "start": self.time, "at": self.time + delay,
                                   "mv": mv, "rank": rank, "rain": rain})

    def _update_thunder(self) -> None:
        now = self.time
        keep = []
        for tm in self.thunder_marks:
            if now < tm["at"]:
                keep.append(tm)
                continue
            p = self.world.get(tm["caster_id"])
            if p is None:
                continue
            mv = tm["mv"]
            par = mv.effects.get("paralyze") or {}
            for e in self._arch_enemies(p, tm["c"], tm["radius"]):
                self._arch_hit(p, mv, tm["rank"], e, tm["rain"])
                if (par and isinstance(e, Pokemon) and e.alive
                        and random.random() < float(par.get("chance", 0.5))):
                    self._apply_root(e, float(par.get("duration", 1.0)))
                    self.fx_events.append({"kind": "buff", "c": (e.pos.x, e.pos.y),
                                           "radius": 0.6, "mtype": "Electric",
                                           "fx": "paralyzed"})
            self.fx_events.append({"kind": "area", "c": (tm["c"].x, tm["c"].y),
                                   "radius": tm["radius"], "mtype": "Electric",
                                   "fx": "thunderstrike"})
        self.thunder_marks = keep
        # Finestra scaduta con fulmini non lanciati: parte la ricarica piena.
        for p in self.world.pokemons():
            if p.thunder_left > 0 and p.thunder_until <= now:
                ms = p.moveset.get("R")
                if ms is not None:
                    ms.cooldown_remaining = max(ms.cooldown_remaining, p.thunder_cd - 5.0)
                p.thunder_left = 0

    # --- aggiornamento --------------------------------------------------------------
    def _update_arch(self, dt: float) -> None:
        if self.wave_zones:
            self._update_wave_zones()
        if self.beam_charges:
            self._update_beam_charges()
        self._update_thunder()
        for p in self.world.pokemons():
            if is_arch_line(p):
                p.arch_rain = p.alive and self._raining_at(p.pos)

    # --- IA (bot) ------------------------------------------------------------------------
    def _bot_arch_cast(self, p, target) -> bool:
        """Bot della linea: tiene la distanza e usa le mosse con criterio."""
        d = p.pos.dist(target.pos)
        tp = (target.pos.x, target.pos.y)
        ms_r = p.moveset.get("R")
        if p.thunder_left > 0 and ms_r is not None and ms_r.ready and d <= 14.0:
            p.pending_cast = ("R", *tp)               # i fulmini rimasti
            return True
        if ms_r is not None and ms_r.ready and ms_r.chosen is not None and isinstance(target, Pokemon):
            sh = ms_r.chosen.shape
            if (sh == "electroshot" and d <= 16.0) or (sh == "thunderstorm" and d <= 12.0):
                p.pending_cast = ("R", *tp)
                return True
        ms = p.moveset.get("E")
        if ms is not None and ms.ready and ms.chosen is not None:
            sh = ms.chosen.shape
            if sh == "irondefense":
                hurt = [a for a in self.world.pokemons()
                        if a.team == p.team and a.alive and a.pos.dist(p.pos) <= 6.0
                        and a.hp < a.max_hp * 0.7]
                if hurt:
                    a = min(hurt, key=lambda q: q.hp / max(1.0, q.max_hp))
                    p.pending_cast = ("E", a.pos.x, a.pos.y)
                    return True
            elif sh == "metalsound" and d <= 3.0 and isinstance(target, Pokemon):
                p.pending_cast = ("E", *tp)
                return True
            elif sh == "dragontail" and d <= 2.4:
                p.pending_cast = ("E", *tp)
                return True
        ms = p.moveset.get("W")
        if ms is not None and ms.ready and d <= 8.0 and isinstance(target, (Pokemon, Minion)):
            p.pending_cast = ("W", *tp)
            return True
        ms = p.moveset.get("Q")
        if ms is not None and ms.ready and ms.chosen is not None:
            hold = ms.chosen.effects.get("hold")
            reach = ms.chosen.range * (1.4 if hold else 1.0)
            if d <= reach:
                p.cast_hold = 1.0 if hold else 0.0
                p.pending_cast = ("Q", *tp)
                return True
        return False
