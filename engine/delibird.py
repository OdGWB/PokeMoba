"""Regole della linea Delibird (tiratore a distanza, danno speciale, nessuna
evoluzione: potenziamenti delle mosse Q5/W6/E7, R al liv.8).

Puro: nessun pygame. Mixin di Match (engine/match.py) come Venomoth: usa lo
stesso stato (self.time, self.world, self.fx_events, _combat_hash, _hit...).
Il client legge le liste `deli_gifts`, `deli_spikes`, `deli_bombs`,
`deli_drops` del Match e i campi `deli_queue`, `ferro_until`, `quark_*`
delle unità.

Passive:
  - Pacco in Arrivo (Delibird): attacchi base speciali (palle di neve, tipo
    Ghiaccio); l'Attacco bonus degli oggetti diventa Att. Sp. La Q lancia il
    PROSSIMO PACCO di una coda (piccolo x1, medio x2, grande x3 + schizzo del
    50% entro 2 tile, regalo = cura); le probabilità vengono dalla Q scelta
    (effects.odds). L'HUD mostra i 2 pacchi dopo quello pronto.
  - Propulsione Quark (Ferrosacco, forma della R Paradosso Futuro): dentro un
    Campo Elettrico (mag_fields) o dopo aver subito una mossa Elettro la forma
    dura 12 s da quel momento e la statistica più alta sale del 30% (una volta
    per forma).

Il pacco si ferma sulla PRIMA unità che incontra, alleata o nemica (mai chi
lo lancia). Su un nemico i pacchi di danno colpiscono e il regalo cura
Delibird; su un alleato il regalo lo cura, i pacchi di danno si aprono senza
fare nulla (niente fuoco amico): è il rischio del pacco a sorpresa.
"""
from __future__ import annotations

import json
import math
import random

from .entities import Minion, Pokemon, Structure, Wild
from .moves import Move, build_moveset
from .stats import Stats
from .vec import Vec2

PACK_ID = "paccoinarrivo"
QUARK_ID = "propulsionequark"
DELI_PASSIVES = {PACK_ID, QUARK_ID}

KINDS = ("s", "m", "l", "g")          # piccolo, medio, grande, regalo
KIND_MULT = {"s": 1.0, "m": 2.0, "l": 3.0, "g": 0.0}
QUEUE_LEN = 3                         # pronto + i 2 mostrati nell'HUD
DELI_AA_MULT = 0.95                   # penalità da tiratore (come Venomoth)
QUARK_MULT = 1.3
QUARK_STATS = ("attack", "defense", "sp_attack", "sp_defense", "speed")

_FERRO_CACHE: dict = {}


def ferro_data() -> dict:
    """Blocco "ferro" di data/pokemon/delibird.json (il caricatore del roster
    scarta le chiavi che non conosce, quindi lo si legge qui, una volta)."""
    if "d" not in _FERRO_CACHE:
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "pokemon", "delibird.json")
        try:
            with open(path, encoding="utf-8") as f:
                _FERRO_CACHE["d"] = json.load(f).get("ferro", {})
        except OSError:
            _FERRO_CACHE["d"] = {}
    return _FERRO_CACHE["d"]


def is_deli(p) -> bool:
    return getattr(p, "passive_id", "") in DELI_PASSIVES


def is_ferro(p) -> bool:
    return getattr(p, "passive_id", "") == QUARK_ID


class DelibirdMixin:
    LINE = {
        "passives": frozenset(DELI_PASSIVES),
        "init": "_init_deli",
        "update": "_update_deli",
        "cast": "_deli_cast",
        "bot_cast": "_bot_deli_cast",
        "speed_mult": "_deli_speed_mult",
        "net": {
            "lists": {"deli_spikes": "c", "deli_bombs": "c", "deli_drops": "c",
                      "deli_gifts": "pos"},
            "moving": ("deli_gifts",),
            "unit_flags": {"quark_active": False},
            "me": ("deli_queue",),
        },
    }

    def _init_deli(self) -> None:
        self.deli_gifts: list[dict] = []    # pacchi della Q in volo
        self.deli_spikes: list[dict] = []   # Punte a terra
        self.deli_bombs: list[dict] = []    # Pacco a Sorpresa (bomba allo scatto)
        self.deli_drops: list[dict] = []    # Consegna Speciale in arrivo

    # --- dispatcher -----------------------------------------------------------
    def _deli_cast(self, p, mv, rank, origin, tgt, dirv) -> bool:
        fn = {"deligift": self._cast_deligift, "delispikes": self._cast_delispikes,
              "delibeam": self._cast_delibeam, "delidash": self._cast_delidash,
              "deliparadox": self._cast_deliparadox,
              "delidelivery": self._cast_delidelivery}.get(mv.shape)
        if fn is None:
            return False
        fn(p, mv, rank, origin, tgt, dirv)
        return True

    # --- passiva: attacchi base e conversione -----------------------------------
    def _deli_convert(self, p) -> None:
        """L'Attacco bonus degli oggetti diventa Att. Sp. (Delibird e Ferrosacco)."""
        if not is_deli(p):
            return
        atk = p.item_bonus.pop("attack", 0.0)
        if atk:
            p.item_bonus["sp_attack"] = p.item_bonus.get("sp_attack", 0.0) + atk

    def _deli_aa_power(self, u) -> float:
        return u.stats.sp_attack * DELI_AA_MULT + u.eff_sp_attack()

    def _deli_as_bonus(self, u) -> float:
        if isinstance(u, Pokemon) and is_ferro(u):
            return float(ferro_data().get("attack_speed_bonus", 0.25))
        return 0.0

    def _deli_speed_mult(self, p) -> float:
        if p.quark_active and p.quark_stat == "speed":
            return QUARK_MULT
        return 1.0

    # --- coda dei pacchi -----------------------------------------------------------
    def _deli_odds(self, p) -> list:
        ms = p.moveset.get("Q")
        mv = ms.chosen if ms else None
        if mv is None or mv.shape != "deligift":
            saved = p.deli_saved or {}
            ms = saved.get("slots", {}).get("Q")
            mv = ms.chosen if ms else None
        odds = (mv.effects.get("odds") if mv is not None else None) or [40, 30, 10, 20]
        return [max(0.0, float(x)) for x in odds[:4]]

    def _deli_roll(self, p) -> str:
        odds = self._deli_odds(p)
        tot = sum(odds)
        if tot <= 0:
            return "s"
        r = random.random() * tot
        for k, w in zip(KINDS, odds):
            r -= w
            if r < 0:
                return k
        return "g"

    def _deli_fill(self, p) -> None:
        while len(p.deli_queue) < QUEUE_LEN:
            p.deli_queue.append(self._deli_roll(p))

    # --- moltiplicatori e colpi subiti ---------------------------------------------
    def _deli_move_mult(self, caster, target, mv) -> float:
        m = 1.0
        if mv.shape == "deligift":
            m *= getattr(caster, "_deli_pack_mult", 1.0)
        bvt = mv.effects.get("bonus_vs_types")   # Liofilizzazione: x2 sui tipi Acqua
        if bvt and isinstance(target, Pokemon):
            for t in target.types:
                if t in bvt:
                    m *= float(bvt[t])
        return m

    def _deli_on_hit(self, caster, target, mv) -> None:
        """Propulsione Quark: una mossa Elettro subita da Ferrosacco la accende."""
        if mv.type == "Electric" and isinstance(target, Pokemon) and is_ferro(target):
            self._deli_quark(target)

    def _deli_quark(self, p) -> None:
        if p.quark_active or not is_ferro(p) or not p.alive:
            return
        fd = ferro_data()
        dur = float(fd.get("quark_duration", 12.0))
        bs = p.base_stats
        p.quark_stat = max(QUARK_STATS, key=lambda k: getattr(bs, k, 0.0))
        p.quark_active = True
        p.quark_until = self.time + dur
        p.ferro_until = max(p.ferro_until, p.quark_until)
        self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "radius": 1.2,
                               "mtype": "Electric", "fx": "ferroquark", "src": p.id})

    # --- Q: Regalino ---------------------------------------------------------------------
    def _cast_deligift(self, p, mv, rank, origin, tgt, dirv):
        self._deli_fill(p)
        kind = p.deli_queue.pop(0)
        self._deli_fill(p)
        end = self._beam_end(origin, dirv, mv.range)
        self.deli_gifts.append({
            "pos": Vec2(origin.x, origin.y), "dir": Vec2(dirv.x, dirv.y), "speed": mv.speed,
            "left": origin.dist(end), "kind": kind, "team": p.team, "caster_id": p.id,
            "mv": mv, "rank": rank, "r": mv.radius, "fx": mv.fx})
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": 0.5,
                               "mtype": mv.type, "fx": "deligiftthrow", "pack": kind})

    def _deli_gift_target(self, g, src, a, b):
        """Prima unità sul tratto a->b (alleati Pokémon o nemici), mai chi lancia."""
        mid = (a + b) * 0.5
        best, bt = None, 1e9
        seg = b - a
        L2 = max(1e-9, seg.x * seg.x + seg.y * seg.y)
        for e in self._combat_hash.query_radius(mid.x, mid.y, a.dist(b) * 0.5 + g["r"] + 1.0):
            if e is src or not getattr(e, "alive", False) or isinstance(e, Structure):
                continue
            if e.team == g["team"] and not isinstance(e, Pokemon):
                continue
            if isinstance(e, Pokemon) and (e.untargetable_until > self.time or e.is_decoy):
                continue
            if self._point_seg_dist(e.pos, a, b) > g["r"] + getattr(e, "radius", 0.0):
                continue
            rel = e.pos - a
            t = (rel.x * seg.x + rel.y * seg.y) / L2
            if t < bt:
                best, bt = e, t
        return best

    def _update_gifts(self, dt: float) -> None:
        keep = []
        for g in self.deli_gifts:
            src = self.world.get(g["caster_id"])
            if src is None or not src.alive:
                continue
            step = min(g["left"], g["speed"] * dt)
            a = g["pos"]
            b = a + g["dir"] * step
            hit = self._deli_gift_target(g, src, a, b)
            if hit is not None:
                self._deli_open(src, g, hit)
                continue
            g["pos"] = b
            g["left"] -= step
            if g["left"] <= 1e-6:
                self.fx_events.append({"kind": "buff", "c": (b.x, b.y), "radius": 0.5,
                                       "mtype": "Ice", "fx": "deligiftopen",
                                       "pack": g["kind"], "miss": True, "src": src.id})
                continue
            keep.append(g)
        self.deli_gifts = keep

    def _deli_gift_heal(self, src, mv, rank) -> float:
        gh = mv.effects.get("gift_heal") or {}
        base = gh.get("base", [40, 60, 80, 100])
        i = max(0, min(len(base) - 1, rank - 1))
        return float(base[i]) + float(gh.get("ratio", 0.3)) * src.eff_sp_attack()

    def _deli_open(self, src, g, e) -> None:
        mv, rank, kind = g["mv"], g["rank"], g["kind"]
        c = e.pos
        self.fx_events.append({"kind": "buff", "c": (c.x, c.y), "radius": 0.7,
                               "mtype": "Ice", "fx": "deligiftopen", "pack": kind,
                               "hit": e.id, "src": src.id})
        if kind == "g":
            heal = self._deli_gift_heal(src, mv, rank)
            who = e if e.team == src.team else src   # sul nemico il regalo torna a Delibird
            self._give_heal(src, who, heal)
            self.fx_events.append({"kind": "buff", "c": (who.pos.x, who.pos.y), "radius": 0.8,
                                   "mtype": "Fairy", "fx": "deligiftheal", "src": src.id})
            return
        if e.team == src.team:
            return   # pacco di danno su un alleato: si apre senza fare nulla
        src._deli_pack_mult = KIND_MULT[kind]
        try:
            self._hit(src, mv, rank, e)
            if kind == "l":
                sp = mv.effects.get("splash") or {}
                rad = float(sp.get("radius", 2.0))
                for o in self._combat_hash.query_radius(c.x, c.y, rad + 1.0):
                    if o is e or o.team == src.team or not getattr(o, "alive", False):
                        continue
                    if not isinstance(o, (Pokemon, Minion, Wild)):
                        continue
                    if c.dist(o.pos) <= rad + getattr(o, "radius", 0.0):
                        self._hit(src, mv, rank, o, mult=float(sp.get("mult", 0.5)))
                self.fx_events.append({"kind": "buff", "c": (c.x, c.y), "radius": rad,
                                       "mtype": "Ice", "fx": "deligiftboom", "src": src.id})
        finally:
            src._deli_pack_mult = 1.0

    # --- W: Punte --------------------------------------------------------------------------
    def _deli_point(self, origin, tgt, rng):
        to = tgt - origin
        if to.length() <= rng:
            return Vec2(tgt.x, tgt.y)
        return origin + to.normalized() * rng

    def _cast_delispikes(self, p, mv, rank, origin, tgt, dirv):
        eff = mv.effects
        c = self._deli_point(origin, tgt, mv.range)
        n = int(eff.get("count", 3))
        spread = float(eff.get("spread", 0.9))
        life = float(eff.get("life", 30.0))
        base_ang = math.atan2(dirv.y, dirv.x)
        for i in range(n):
            a = base_ang + i * 2.0 * math.pi / max(1, n)
            pt = Vec2(c.x + math.cos(a) * spread, c.y + math.sin(a) * spread)
            pt = self._nearest_walkable(pt, c)
            self.deli_spikes.append({"c": pt, "team": p.team, "caster_id": p.id,
                                     "start": self.time, "end": self.time + life,
                                     "mv": mv, "rank": rank, "r": mv.radius,
                                     "seed": p.cast_seq * 7 + i})
        mine = [s for s in self.deli_spikes if s["caster_id"] == p.id]
        extra = len(mine) - int(eff.get("max", 6))
        if extra > 0:
            drop = {id(s) for s in mine[:extra]}   # le più vecchie
            self.deli_spikes = [s for s in self.deli_spikes if id(s) not in drop]
        self.fx_events.append({"kind": "area", "c": (c.x, c.y), "radius": spread + 0.4,
                               "mtype": mv.type})

    def _update_spikes(self) -> None:
        now = self.time
        keep = []
        for s in self.deli_spikes:
            if now > s["end"]:
                continue
            src = self.world.get(s["caster_id"])
            if src is None:
                continue
            c, r = s["c"], s["r"]
            hit = None
            for e in self._combat_hash.query_radius(c.x, c.y, r + 1.0):
                if e.team == s["team"] or not getattr(e, "alive", False):
                    continue
                if not isinstance(e, (Pokemon, Minion, Wild)):
                    continue
                if isinstance(e, Pokemon) and (e.untargetable_until > now or e.is_decoy
                                               or getattr(e, "air_z", 0.0) > 0.0):
                    continue
                if c.dist(e.pos) <= r + getattr(e, "radius", 0.0):
                    hit = e
                    break
            if hit is None:
                keep.append(s)
                continue
            self._hit(src, s["mv"], s["rank"], hit)   # rallentamento dagli effetti
            self.fx_events.append({"kind": "buff", "c": (c.x, c.y), "radius": 0.7,
                                   "mtype": "Ice", "fx": "delispikehit", "src": src.id})
        self.deli_spikes = keep

    # --- W: Liofilizzazione / Q di Ferrosacco: Idropompa (raggio) ---------------------------
    def _cast_delibeam(self, p, mv, rank, origin, tgt, dirv):
        end = self._beam_end(origin, dirv, mv.range)
        L = origin.dist(end)
        mid = (origin + end) * 0.5
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
        self.fx_events.append({"kind": "projectile", "a": (origin.x, origin.y),
                               "b": (end.x, end.y), "mtype": mv.type})

    # --- E: Pacco a Sorpresa ---------------------------------------------------------------
    def _cast_delidash(self, p, mv, rank, origin, tgt, dirv):
        self._cast_dash(p, mv, rank, origin, tgt, dirv)
        bomb = mv.effects.get("bomb") or {}
        bmv = Move(slot="E", max_rank=mv.max_rank, d={
            "id": mv.id + "_bomb", "name": mv.name, "type": mv.type,
            "category": mv.category, "shape": "delibomb", "fx": mv.fx,
            "power": bomb.get("power", [60, 95, 130, 165]),
            "ratio": bomb.get("ratio", 0.6)})
        self.deli_bombs.append({"c": Vec2(origin.x, origin.y), "team": p.team,
                                "caster_id": p.id, "start": self.time,
                                "at": self.time + float(bomb.get("delay", 1.0)),
                                "radius": float(bomb.get("radius", 2.0)),
                                "mv": bmv, "rank": rank})

    def _update_bombs(self) -> None:
        now = self.time
        keep = []
        for b in self.deli_bombs:
            if now < b["at"]:
                keep.append(b)
                continue
            src = self.world.get(b["caster_id"])
            if src is None:
                continue
            c, rad = b["c"], b["radius"]
            for e in self._combat_hash.query_radius(c.x, c.y, rad + 1.0):
                if e.team == b["team"] or not getattr(e, "alive", False):
                    continue
                if not isinstance(e, (Pokemon, Minion, Wild)):
                    continue
                if c.dist(e.pos) <= rad + getattr(e, "radius", 0.0):
                    self._hit(src, b["mv"], b["rank"], e)
            self.fx_events.append({"kind": "buff", "c": (c.x, c.y), "radius": rad,
                                   "mtype": "Ice", "fx": "delibomb", "src": src.id})
        self.deli_bombs = keep

    # --- R: Consegna Speciale ------------------------------------------------------------------
    def _cast_delidelivery(self, p, mv, rank, origin, tgt, dirv):
        c = self._deli_point(origin, tgt, mv.range)
        delay = float(mv.effects.get("delay", 1.0))
        self.deli_drops.append({"c": c, "team": p.team, "caster_id": p.id,
                                "start": self.time, "at": self.time + delay,
                                "radius": mv.radius, "mv": mv, "rank": rank})

    def _update_drops(self) -> None:
        now = self.time
        keep = []
        for d in self.deli_drops:
            if now < d["at"]:
                keep.append(d)
                continue
            src = self.world.get(d["caster_id"])
            if src is None:
                continue
            mv, rank, c, rad = d["mv"], d["rank"], d["c"], d["radius"]
            ah = mv.effects.get("ally_heal") or {}
            base = ah.get("base", [120, 180, 240])
            heal = (float(base[max(0, min(len(base) - 1, rank - 1))])
                    + float(ah.get("ratio", 0.4)) * src.eff_sp_attack())
            for e in self._combat_hash.query_radius(c.x, c.y, rad + 1.0):
                if not getattr(e, "alive", False) or c.dist(e.pos) > rad + getattr(e, "radius", 0.0):
                    continue
                if e.team == d["team"]:
                    if isinstance(e, Pokemon) and not e.is_decoy:
                        self._give_heal(src, e, heal)
                    continue
                if isinstance(e, (Pokemon, Minion, Wild)):
                    self._hit(src, mv, rank, e)   # congelamento dagli effetti
            self.fx_events.append({"kind": "buff", "c": (c.x, c.y), "radius": rad,
                                   "mtype": "Ice", "fx": "delideliveryland", "src": src.id})
        self.deli_drops = keep

    # --- R: Paradosso Futuro (Ferrosacco) ----------------------------------------------------
    def _cast_deliparadox(self, p, mv, rank, origin, tgt, dirv):
        if is_ferro(p):
            p.ferro_until = max(p.ferro_until, self.time + float(mv.effects.get("duration", 8.0)))
            return
        self._deli_to_ferro(p, float(mv.effects.get("duration", 8.0)))
        self.fx_events.append({"kind": "buff", "c": (origin.x, origin.y), "radius": 1.4,
                               "mtype": "Water", "fx": "deliparadox", "src": p.id})

    def _deli_to_ferro(self, p, dur: float) -> None:
        fd = ferro_data()
        if not fd:
            return
        p.deli_saved = {
            "name": p.name, "dex": p.dex, "types": list(p.types),
            "base_stats": p.base_stats, "passive": p.passive_id,
            "attack_fx": p.attack_fx, "radius": p.radius,
            "slots": {s: p.moveset.get(s) for s in ("Q", "E")}, "t": self.time,
        }
        p.name = fd.get("name", "Ferrosacco")
        p.dex = int(fd.get("dex", 991))
        p.types = list(fd.get("types", ["Water", "Ice"]))
        p.base_stats = Stats.from_dict(fd["base_stats"])
        p.passive_id = fd.get("passive", QUARK_ID)
        p.attack_fx = fd.get("attack_fx", p.attack_fx)
        p.radius = float(fd.get("radius", p.radius))
        new = build_moveset({s: {"base": d} for s, d in fd.get("moves", {}).items()})
        for s, ms in new.items():
            old = p.moveset.get(s)
            if old is not None:
                ms.rank = max(1, old.rank)
                ms.unlocked = old.unlocked
            p.moveset[s] = ms
        p.ferro_until = self.time + dur
        p.quark_active = False
        p.quark_stat = ""
        self._recompute_stats(p, preserve_ratio=True)

    def _deli_from_ferro(self, p) -> None:
        sv = p.deli_saved
        p.deli_saved = None
        p.quark_active = False
        p.quark_stat = ""
        p.ferro_until = -1.0
        if not sv:
            return
        p.name, p.dex, p.types = sv["name"], sv["dex"], list(sv["types"])
        p.base_stats = sv["base_stats"]
        p.passive_id = sv["passive"]
        p.attack_fx = sv["attack_fx"]
        p.radius = sv["radius"]
        el = self.time - sv["t"]
        for s, old in sv["slots"].items():
            if old is None:
                continue
            cur = p.moveset.get(s)
            if cur is not None:
                old.rank = max(old.rank, min(cur.rank, old.max_rank))
            old.cooldown_remaining = max(0.0, old.cooldown_remaining - el)
            p.moveset[s] = old
        self._recompute_stats(p, preserve_ratio=True)
        self.fx_events.append({"kind": "buff", "c": (p.pos.x, p.pos.y), "radius": 1.2,
                               "mtype": "Ice", "fx": "deliparadoxend", "src": p.id})

    # --- ciclo ---------------------------------------------------------------------------------
    def _update_deli(self, dt: float) -> None:
        now = self.time
        if self.deli_gifts:
            self._update_gifts(dt)
        if self.deli_spikes:
            self._update_spikes()
        if self.deli_bombs:
            self._update_bombs()
        if self.deli_drops:
            self._update_drops()
        for p in self.world.pokemons():
            if not is_deli(p):
                continue
            if p.passive_id == PACK_ID and len(p.deli_queue) < QUEUE_LEN:
                self._deli_fill(p)
            if not is_ferro(p):
                continue
            if not p.alive or p.ferro_until <= now:
                self._deli_from_ferro(p)
                continue
            if not p.quark_active:
                for f in getattr(self, "mag_fields", ()):
                    if f["c"].dist(p.pos) <= f["radius"]:
                        self._deli_quark(p)
                        break

    # --- bot --------------------------------------------------------------------------------------
    def _bot_deli_cast(self, p, target) -> bool:
        """Paradosso Futuro (senza potenza) non la lancia il lanciatore generico."""
        ms = p.moveset.get("R")
        if not (ms and ms.ready and ms.chosen) or ms.chosen.shape != "deliparadox":
            return False
        if isinstance(target, Pokemon) and p.pos.dist(target.pos) <= p.attack_range + 2.0:
            p.pending_cast = ("R", p.pos.x, p.pos.y)
            return True
        return False
