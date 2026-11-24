"""Torneo di bot per la tier list Developer.

Fa giocare tante partite 3v3 SENZA grafica (solo motore, a tick fisso) tra
squadre di Pokemon scelti a caso dal roster e registra per ogni partita chi ha
vinto e le statistiche di ognuno. Una riga JSON per partita in --out, cosi si
puo' interrompere e riprendere. Poi `tools/tier_build.py` ne ricava la classifica.

    python tools/tier_sim.py --matches 600 --workers 6 --out tools/tier_matches.jsonl
"""
from __future__ import annotations

import argparse
import json
import operator
import os
import random
import sys
import time
from datetime import datetime, timedelta
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import config  # noqa: E402
from engine.content import load_map, load_pokemon_def  # noqa: E402
from engine import evolution  # noqa: E402
from engine.entities import Core, Minion, Pokemon, Wild  # noqa: E402
from engine.match import Match  # noqa: E402
from engine.vec import Vec2  # noqa: E402
from engine.stats import respawn_time  # noqa: E402
from engine.world import World  # noqa: E402

from engine.entities import Structure, Unit  # noqa: E402
from engine.grid import TILE_BUSH  # noqa: E402
from engine.vision import BUSH_REVEAL, VisionSystem  # noqa: E402
from engine.grid import _native  # noqa: E402

LANES = ["top", "mid", "bot"]
MAP_5V5 = "data/maps/map_5v5.json"
MAX_TIME = 18 * 60.0        # secondi di gioco: oltre, si decide per torri/uccisioni/danno
ASSIST_WINDOW = 10.0     # secondi: chi ha colpito la vittima entro questo tempo e' assistente
JUNGLERS = ["Nincada", "Sneasel", "Teddiursa", "Swinub", "Totodile"]   # chi puo' fare il jungler
SUPPORTS = {"Rookidee"}         # oltre ai ruoli "supporto": conta come supporto per la bot lane
# Scelte Q/W/E (indice del potenziamento) che portano Eevee alla forma voluta.
EEVEE_CHOICES = {"jolteon": {"Q": 0, "W": 0, "E": 0}, "flareon": {"Q": 0, "W": 0, "E": 1},
                 "espeon": {"Q": 0, "W": 1, "E": 0}, "glaceon": {"Q": 0, "W": 1, "E": 1},
                 "leafeon": {"Q": 1, "W": 0, "E": 0}, "umbreon": {"Q": 1, "W": 0, "E": 1},
                 "sylveon": {"Q": 1, "W": 1, "E": 0}, "vaporeon": {"Q": 1, "W": 1, "E": 1}}
# Stati di controllo (campo "_until" dell'unita', peso): contano i secondi di CC inflitti.
CC_FIELDS = (("stun_until", 1.0), ("root_until", 1.0), ("sleep_until", 1.0), ("fear_until", 1.0),
             ("charm_until", 1.0), ("airborne_until", 1.0), ("taunt_until", 0.7),
             ("confuse_until", 0.6), ("silence_until", 0.5), ("slow_until", 0.4))
_cc_get = operator.attrgetter(*(f for f, _ in CC_FIELDS))
FORCED = {}     # id Pokemon -> {slot: indice}: scelte forzate per i rami (vedi _force_choice)

_orig_apply_choice = evolution.apply_choice


def _force_choice(p, slot, index):
    plan = FORCED.get(p.id)
    if plan and slot in plan:
        index = plan[slot]
    return _orig_apply_choice(p, slot, index)


evolution.apply_choice = _force_choice


SLOT_OFFSET = {"top": Vec2(-1.2, 0.0), "mid": Vec2(0.0, 0.0), "bot": Vec2(0.0, 1.2)}


class FastVision(VisionSystem):
    """Stessa visione dei nemici di VisionSystem, ma senza costruire gli insiemi di
    tile (nessuno li usa nel motore): ~3x piu' veloce, risultato identico."""

    # Modalita' allenamento: visione ricalcolata ogni `stride` chiamate per squadra
    # (approssimata, i nemici visti restano quelli dell'ultimo calcolo). 1 = esatta.
    stride = 1

    def update(self, world, team):
        if self.stride > 1:
            calls = self.__dict__.setdefault("_calls", {})
            n = calls[team] = calls.get(team, -1) + 1
            if n % self.stride and team in self.visible_enemies:
                return False
        if not self.reveals.get(team) and _native is not None and hasattr(_native, "VisionScan"):
            return self._update_native(world, team)
        scan = self.__dict__.get("_nscan")
        if scan is not None:
            scan.reset(team)              # il prossimo giro in Rust ricalcola
        sources, keys, extra, foes = [], [], [], []
        for e in world.entities.values():
            if getattr(e, "team", team) == team:
                if (getattr(e, "team", None) == team and getattr(e, "alive", False)
                        and isinstance(e, (Unit, Structure))):
                    v = getattr(e, "vision", 0)
                    if v > 0:
                        sources.append(e)
                        keys.append((e.id, int(e.pos.x), int(e.pos.y), int(v)))
                continue
            if getattr(e, "invisible", False):
                extra.append(("inv", e.id))
            if getattr(e, "agitated", False):
                extra.append(("agi", e.id, int(e.pos.x), int(e.pos.y)))
            if isinstance(e, Unit) and e.alive:
                foes.append(e)
        sig = set(keys)
        sig.update(extra)
        reveals = self.reveals.get(team) or ()
        if reveals:
            sig.update(("ping", round(x, 1), round(y, 1), r) for x, y, r in reveals)
            sig.update(("pos", u.id, int(u.pos.x), int(u.pos.y)) for u in foes)
        if sig == self._sig.get(team):
            return False
        self._sig[team] = sig
        self.version[team] = self.version.get(team, 0) + 1
        if foes and keys:
            ux = np.fromiter((int(u.pos.x) for u in foes), np.int64, len(foes))
            uy = np.fromiter((int(u.pos.y) for u in foes), np.int64, len(foes))
            k = np.array([kk[1:] for kk in keys], dtype=np.int64)
            inside = (((ux[:, None] - k[None, :, 0]) ** 2 + (uy[:, None] - k[None, :, 1]) ** 2)
                      <= (k[None, :, 2] ** 2)).any(axis=1).tolist()
        else:
            inside = [False] * len(foes)
        tile_at = self.grid.tile_at
        enemies = set()
        for u, seen in zip(foes, inside):
            if reveals and any((u.pos.x - x) ** 2 + (u.pos.y - y) ** 2 <= r * r
                               for x, y, r in reveals):
                enemies.add(u.id)
                continue
            if not seen or getattr(u, "invisible", False):
                continue
            if tile_at(int(u.pos.x), int(u.pos.y)) == TILE_BUSH and not getattr(u, "agitated", False):
                if not any(e.pos.dist(u.pos) <= BUSH_REVEAL for e in sources):
                    continue
            enemies.add(u.id)
        self.visible_enemies[team] = enemies
        return True

    def _update_native(self, world, team):
        """Come update senza reveals: scansione e cerchi in Rust, regola dei
        cespugli qui (stesso risultato)."""
        scan = self.__dict__.get("_nscan")
        if scan is None:
            scan = self._nscan = _native.VisionScan()
        r = scan.scan(world.entities.values(), team, Unit, Structure)
        if r is None:
            return False
        self._sig[team] = None            # un eventuale giro in Python ricalcola
        self.version[team] = self.version.get(team, 0) + 1
        sources, seen = r
        tile_at = self.grid.tile_at
        enemies = set()
        for u in seen:
            if tile_at(int(u.pos.x), int(u.pos.y)) == TILE_BUSH and not getattr(u, "agitated", False):
                if not any(e.pos.dist(u.pos) <= BUSH_REVEAL for e in sources):
                    continue
            enemies.add(u.id)
        self.visible_enemies[team] = enemies
        return True


_SLOT_N = {}


def _spawn(world, map_data, team, lane, pdef, is_jg=False, name=""):
    base = Vec2(*map_data.spawns[f"team{team}"]) + Vec2(0.5, 0.5)
    k = _SLOT_N.get((team, lane), 0)
    _SLOT_N[(team, lane)] = k + 1
    off = SLOT_OFFSET[lane] + (Vec2(0.7 * k, 0.0) if lane == "bot" else Vec2(0, 0))
    if is_jg:
        off = Vec2(0.5, -0.9)
    p = world.spawn_pokemon(
        pos=base + off, team=team, dex=pdef.dex, name=pdef.name,
        color=config.TEAM_COLORS[team], speed=pdef.base_speed, is_bot=True,
        assigned_lane=lane, types=pdef.types, base_stats=pdef.base_stats,
        growth=pdef.growth, moves=pdef.moves, evolutions=pdef.evolutions,
        role=pdef.role, passive=pdef.passive, attack_range=pdef.attack_range,
        attack_cooldown=pdef.attack_cooldown, attack_fx=pdef.attack_fx,
        rec_items=pdef.recommended_items)
    p.radius = pdef.radius
    return p


def compose_team(rng, defs, jungler, others, support_pure, support_forms):
    """Ruoli e rami di una squadra da 5: 1 jungler + 4 giocatori, due dei quali in bot lane.

    Il supporto va in bot: un supporto puro (a caso se piu' di uno); se non ce ne sono,
    un Pokemon con una forma support la prende (a caso se piu' di uno); gli altri con
    forma support scelgono una forma NON support. Ritorna [(idx, lane, plan, e_supporto)]."""
    pure = [i for i in others if defs[i].name in support_pure]
    cand = [i for i in others if defs[i].name in support_forms]
    support = None
    if pure:
        support = rng.choice(pure)
    elif cand:
        support = rng.choice(cand)
    rest = [i for i in others if i != support]
    rng.shuffle(rest)
    if support is not None:
        bot = [support, rest.pop()]
    else:
        bot = [rest.pop(), rest.pop()]
    lanes = {"top": [rest[0]], "mid": [rest[1]], "bot": bot}
    out = [(jungler, "jungle", None, False)]
    for lane, idxs in lanes.items():
        for i in idxs:
            out.append((i, lane, None, i == support))
    return out


def branch_plan(rng, name, is_jungler, is_support):
    """Ramo forzato per i Pokemon con evoluzioni ramificate comandate dal ruolo."""
    if name == "Sneasel":
        return "sneasler" if is_jungler else "weavile"
    if name == "Poliwag":
        return "politoad" if is_support else "poliwrath"
    if name == "Eevee":
        return "sylveon" if is_support else rng.choice(
            [k for k in EEVEE_CHOICES if k != "sylveon"])
    return None


OPTS = {"open_nexus": False, "max_time": MAX_TIME, "plan": False, "utility": None,
        "params": None,   # impostato nei processi dal Pool (initializer)
        "early_stop": None,      # dict di EARLY_STOP (anche parziale) per fermare le partite decise
        "vision_stride": 1,      # modalita' allenamento: visione ogni N tick (1 = esatta)
        "minion_stride": 1}      # modalita' allenamento: IA dei minion ogni N tick (1 = esatta)

# Stop anticipato: dopo `min_time`, ogni `every` secondi si misura il vantaggio
#   A = (patrimonio_0 - patrimonio_1) / gold_unit + (torri_0 - torri_1) / tower_unit
#       (+ `nexus` se il nucleo dell'avversario e' scoperto, - se lo e' il proprio)
# (patrimonio = oro in tasca + prezzo pieno degli oggetti). Se |A| >= `threshold` per
# `hold` controlli di fila la partita si chiude e vince chi e' avanti.
EARLY_STOP = {"min_time": 420.0, "every": 10.0, "threshold": 2.0, "hold": 2,
              "gold_unit": 4000.0, "tower_unit": 3.0, "nexus": 1.0}


def _utility_teams(mode, seed):
    """Squadre con l'IA a punteggio. alt: una sola squadra, che cambia col seme (A/B equo)."""
    if mode == "both":
        return (0, 1)
    if mode in ("0", "1"):
        return (int(mode),)
    if mode == "alt":
        return (seed % 2,)
    return ()


def param_group(role, is_jg, is_sup):
    """Gruppo dei parametri tarati (tools/cma_tune.py): jungler, support o il ruolo base."""
    if is_jg:
        return "jungler"
    if is_sup:
        return "support"
    return "mago" if role == "mago mobile" else role


def _init_worker(open_nexus, max_time, plan=False, utility=None, early_stop=None,
                 vision_stride=1, minion_stride=1):
    OPTS["early_stop"] = early_stop
    OPTS["vision_stride"] = vision_stride
    OPTS["minion_stride"] = minion_stride
    OPTS["utility"] = utility
    OPTS["open_nexus"] = open_nexus
    OPTS["max_time"] = max_time
    OPTS["plan"] = plan


def play(job):
    """Una partita 5v5. job = (seed, jungler0, altri0, jungler1, altri1) (indici del roster)."""
    seed, j0, o0, j1, o1 = job
    max_time = OPTS["max_time"]
    random.seed(seed)
    rng = random.Random(seed)
    defs = [load_pokemon_def(str(ROOT / rel)) for rel in config.ROSTER]
    map_data = load_map(str(ROOT / MAP_5V5))
    world = World(map_data.grid)
    match = Match(world, map_data)
    match.vision = FastVision(world.grid)
    match.vision.stride = max(1, int(OPTS.get("vision_stride") or 1))
    match.minion_ai_stride = max(1, int(OPTS.get("minion_stride") or 1))
    core_ev = [{}, {}]              # per nucleo: esposto / primo colpo / ultimo colpo (secondi)
    if OPTS["plan"]:
        # IA a piani (engine/bot_plan.py): shopping, assedio, aiuto alle torri, roam del
        # support; gank del jungler piu largo (nemici fino al 90% di vita, ogni 40 s).
        match.bot_plan = True
        for bp in match.bot_params:
            bp.gank_hp = 0.9
            bp.gank_cooldown = 40.0
            bp.gank_min_time = 210.0
    u_teams = _utility_teams(OPTS["utility"], seed)
    for t_ in u_teams:
        match.bot_params[t_].utility = True     # IA a punteggio (engine/bot_utility.py)
    if OPTS["open_nexus"]:
        # La regola "nexus scoperto con una lane senza torri" ora e' nel motore
        # (Match._alive_towers); qui si registra solo quando si apre, per le statistiche.
        _orig_alive = match._alive_towers

        def _exposed(team):
            n = _orig_alive(team)
            if n == 0:
                core_ev[team].setdefault("exposed", round(match.time))
            return n
        match._alive_towers = _exposed

    stat = {}                       # id -> dict
    units = []
    FORCED.clear()
    _SLOT_N.clear()
    plans = {}                      # id -> ramo forzato
    support_pure = SUPPORTS | {d.name for d in defs if d.role == "supporto"}
    support_forms = {d.name for d in defs if d.role != "supporto" and any(
        e.get("role") == "supporto" for e in d.evolutions)}
    team_info = {}
    for team, (jg, others) in ((0, (j0, o0)), (1, (j1, o1))):
        roster = compose_team(rng, defs, jg, others, support_pure, support_forms)
        names = [defs[i].name for i, *_ in roster]
        team_info[team] = {"jungler": True, "support": any(sup for *_, sup in roster)}
        for idx, lane, _plan, is_sup in roster:
            name = defs[idx].name
            is_jg = lane == "jungle"
            spawn_lane = "mid" if is_jg else lane
            p = _spawn(world, map_data, team, spawn_lane, defs[idx], is_jg, name)
            plan = branch_plan(rng, name, is_jg, is_sup)
            if name == "Eevee":
                FORCED[p.id] = EEVEE_CHOICES[plan]
            if plan:
                plans[p.id] = plan
            p.is_jungler = is_jg
            p.bot_support = bool(is_sup)
            # Parametri per gruppo: OPTS["params"] = {squadra: {gruppo | "*": {campo: valore}}}
            tp = (OPTS.get("params") or {}).get(team)
            if tp:
                ov = dict(tp.get("*", {}))
                ov.update(tp.get(param_group(defs[idx].role, is_jg, is_sup), {}))
                if ov:
                    p.bot_params = match.bot_params[team].copy(**ov)
            others_n = [n for n in names if n != name]
            stat[p.id] = {"name": name, "team": team, "idx": idx, "lane": lane,
                          "kills": 0, "deaths": 0, "dmg": 0.0, "taken": 0.0, "camps": 0,
                          "jungle": is_jg, "plan": plan, "is_support": is_sup,
                          "with_support": (any(n in support_pure for n in others_n)
                                           or (any(sup for *_, sup in roster) and not is_sup)),
                          "camps_clear": 0}
            units.append(p)
    match.vision.update(world, 0)
    match.vision.update(world, 1)

    # Contatori (solo osservazione, nessun cambio di logica).
    orig_death = match._on_death
    orig_dmg = match._deal_damage

    last_hit = {}                   # id vittima -> {id attaccante: tempo ultimo colpo}

    for s in stat.values():
        s.update(assists=0, cc=0.0, support=0.0, t8=None, t5=None,
                 maxhit=0.0, selfheal=0.0, tower_deaths=0, streak=0, best_streak=0, fb=0)
    first_blood = [False]

    def on_death(victim, killer):
        if isinstance(victim, Wild) and isinstance(killer, Pokemon) and killer.id in stat:
            stat[killer.id]["camps"] += 1
            if victim.kind != "camp":
                stat[killer.id]["legend"] = stat[killer.id].get("legend", 0) + 1
        elif isinstance(victim, Minion) and isinstance(killer, Pokemon) and killer.id in stat:
            stat[killer.id]["cs"] = stat[killer.id].get("cs", 0) + 1
        elif isinstance(victim, Structure) and isinstance(killer, Pokemon) and killer.id in stat                 and victim.kind == "tower":
            stat[killer.id]["towers"] = stat[killer.id].get("towers", 0) + 1
        if isinstance(victim, Pokemon) and victim.id in stat:
            stat[victim.id]["deaths"] += 1
            stat[victim.id]["streak"] = 0
            if isinstance(killer, Structure):
                stat[victim.id]["tower_deaths"] += 1
            if (isinstance(killer, Pokemon) and killer.id in stat and killer.team != victim.team
                    and not first_blood[0]):
                first_blood[0] = True
                stat[killer.id]["fb"] = 1
            if isinstance(killer, Pokemon) and killer.id in stat and killer.team != victim.team:
                k_ = stat[killer.id]
                k_["streak"] += 1
                k_["best_streak"] = max(k_["best_streak"], k_["streak"])
            stat[victim.id]["dead_time"] = stat[victim.id].get("dead_time", 0.0) +                 respawn_time(victim.level)
            if isinstance(killer, Pokemon) and killer.id in stat and killer.team != victim.team:
                stat[killer.id]["kills"] += 1
            kid = killer.id if killer is not None else None
            for aid, t in last_hit.pop(victim.id, {}).items():
                if aid != kid and match.time - t <= ASSIST_WINDOW:
                    stat[aid]["assists"] += 1
        return orig_death(victim, killer)

    def deal(attacker, target, amount, *a, **kw):
        if isinstance(target, Pokemon) and target.id in stat and amount > 0:
            hp0 = target.hp
            r = orig_dmg(attacker, target, amount, *a, **kw)
            lost = max(0.0, hp0 - target.hp)
            stat[target.id]["taken"] += lost
            if isinstance(attacker, Pokemon) and attacker.id in stat and attacker.team != target.team:
                stat[attacker.id]["dmg"] += lost
                stat[attacker.id]["maxhit"] = max(stat[attacker.id]["maxhit"], lost)
                last_hit.setdefault(target.id, {})[attacker.id] = match.time
            scan_cc(attacker if isinstance(attacker, Pokemon) else None)
            return r
        if isinstance(target, Structure) and isinstance(attacker, Pokemon) and attacker.id in stat:
            hp0 = target.hp
            r = orig_dmg(attacker, target, amount, *a, **kw)
            stat[attacker.id]["sdmg"] = stat[attacker.id].get("sdmg", 0.0) + max(0.0, hp0 - target.hp)
            return r
        if isinstance(attacker, Pokemon) and attacker.id in stat and amount > 0:
            key = "dmg_minion" if isinstance(target, Minion) else (
                "dmg_wild" if isinstance(target, Wild) else None)
            if key:
                hp0 = target.hp
                r = orig_dmg(attacker, target, amount, *a, **kw)
                stat[attacker.id][key] = stat[attacker.id].get(key, 0.0) + max(0.0, hp0 - target.hp)
                return r
        return orig_dmg(attacker, target, amount, *a, **kw)

    def source_of(target):
        """Chi ha colpito per ultimo il bersaglio (entro 3 s)."""
        hits = last_hit.get(target.id)
        if hits:
            aid, t = max(hits.items(), key=lambda kv: kv[1])
            if match.time - t <= 3.0:
                return next((u for u in units if u.id == aid), None)
        return None

    seen = {}                       # (id, campo) -> ultima scadenza vista
    last_raw = {}                   # id -> scadenze lette all'ultima scansione

    def scan_cc(hint=None):
        """Conta i secondi di CC appena inflitti: confronta le scadenze degli stati di
        controllo con quelle viste prima e li attribuisce a `hint` (chi sta colpendo o
        lanciando) se e' un nemico, altrimenti a chi ha colpito per ultimo."""
        now = match.time
        for v in units:
            # Uscita rapida: scadenze identiche all'ultima scansione -> nessun
            # campo supera il massimo gia' visto (seen tiene il massimo).
            try:
                raw = _cc_get(v)
            except AttributeError:
                raw = None
            if raw is not None:
                if last_raw.get(v.id) == raw:
                    continue
                last_raw[v.id] = raw
            for f, w in CC_FIELDS:
                cur = getattr(v, f, -1.0)
                key = (v.id, f)
                prev = seen.get(key, -1.0)
                if cur <= prev:
                    continue
                seen[key] = cur
                if cur <= now:
                    continue
                gain = cur - max(prev, now)
                src = hint if (hint is not None and hint.team != v.team) else source_of(v)
                if src is not None and src.id in stat and src.team != v.team:
                    stat[src.id]["cc"] += w * gain
                    if w >= 0.7:
                        stat[src.id]["cc_n"] = stat[src.id].get("cc_n", 0) + 1

    orig_cast = match._cast

    def cast(p, *a, **kw):
        r = orig_cast(p, *a, **kw)
        scan_cc(p if isinstance(p, Pokemon) else None)
        return r

    orig_heal = match._give_heal
    orig_shield = match._give_shield

    def heal(caster, target, amount):
        hp0 = target.hp
        r = orig_heal(caster, target, amount)
        if (isinstance(caster, Pokemon) and caster.id in stat and target is caster):
            stat[caster.id]["selfheal"] += max(0.0, target.hp - hp0)
        if (isinstance(caster, Pokemon) and caster.id in stat and target is not caster
                and isinstance(target, Pokemon) and target.id in stat):
            stat[caster.id]["support"] += max(0.0, target.hp - hp0)
        return r

    def shield(caster, target, amt, dur):
        if (isinstance(caster, Pokemon) and caster.id in stat and target is not caster
                and isinstance(target, Pokemon) and target.id in stat):
            stat[caster.id]["support"] += max(0.0, amt)
        return orig_shield(caster, target, amt, dur)

    def prepare_branch(p, plan):
        """Prima del livello 8 porta il Pokemon sulla condizione del ramo voluto
        (stessi campi che il gioco gia' usa: oggetto, oro dei neutrali/minion)."""
        if plan == "politoad" and "king_rock" not in p.items:
            p.items.append("king_rock")
            match._apply_items(p)
        elif plan == "poliwrath" and "king_rock" in p.items:
            p.items.remove("king_rock")
            match._apply_items(p)
        elif plan == "sneasler" and not p.gold_wild > p.gold_minion:
            p.gold_wild = p.gold_minion + 1.0
        elif plan == "weavile" and p.gold_wild > p.gold_minion:
            p.gold_minion = p.gold_wild

    orig_smite = match.use_smite

    def smite(p, target=None):
        ok = orig_smite(p, target)
        if ok and p.id in stat:
            stat[p.id]["smites"] = stat[p.id].get("smites", 0) + 1
        return ok

    def deal_core(attacker, target, amount, *a, **kw):
        if isinstance(target, Core):
            hp0 = target.hp
            r = deal(attacker, target, amount, *a, **kw)
            if target.hp < hp0 - 0.01:
                ev = core_ev[target.team]
                ev.setdefault("first_hit", round(match.time))
                ev["last_hit"] = round(match.time)
                ev["hits"] = ev.get("hits", 0) + 1
                ev["by_minion"] = ev.get("by_minion", 0) + (1 if isinstance(attacker, Minion) else 0)
            return r
        return deal(attacker, target, amount, *a, **kw)

    match.use_smite = smite
    match._on_death = on_death
    match._deal_damage = deal_core
    match._cast = cast
    match._give_heal = heal
    match._give_shield = shield

    es = OPTS.get("early_stop")
    es = dict(EARLY_STOP, **es) if es is not None else None
    early = None                    # (vincitore, istante, vantaggio) se fermata prima
    es_next = es["min_time"] if es else float("inf")
    es_run = [0, 0]                 # controlli di fila con la squadra 0 / 1 avanti

    def networth(t):
        cat = match.item_catalog.items
        return sum(float(p.gold) + sum(cat[i].price for i in p.items if i in cat)
                   for p in units if p.team == t)

    def advantage():
        tw = [sum(1 for x in world.structures() if x.team == t and x.alive and x.kind == "tower")
              for t in (0, 1)]
        a = (networth(0) - networth(1)) / es["gold_unit"] + (tw[0] - tw[1]) / es["tower_unit"]
        for t, sign in ((1, 1.0), (0, -1.0)):
            if match._alive_towers(t) == 0:
                a += sign * es["nexus"]
        return a

    dt = config.TICK_DT
    tick = 0
    while match.winner is None and match.time < max_time:
        match.update(dt, tick)
        tick += 1
        scan_cc()
        if match.time >= es_next and match.winner is None:
            es_next += es["every"]
            a = advantage()
            lead = 0 if a >= es["threshold"] else 1 if a <= -es["threshold"] else None
            for t in (0, 1):
                es_run[t] = es_run[t] + 1 if lead == t else 0
            if lead is not None and es_run[lead] >= es["hold"]:
                early = (lead, round(match.time, 1), round(a, 2))
                break
        if tick % 30 == 0:
            for p in units:
                if p.level >= 8 and stat[p.id]["t8"] is None:
                    stat[p.id]["t8"] = round(match.time, 1)
                if p.level >= 5 and stat[p.id].get("t5") is None:
                    stat[p.id]["t5"] = round(match.time, 1)
                if match.time >= 600.0 and "lvl10" not in stat[p.id]:
                    st = stat[p.id]
                    st["lvl10"] = p.level
                    st["gold10"] = round(float(getattr(p, "gold", 0)))
                    st["kills10"], st["deaths10"] = st["kills"], st["deaths"]
                    st["assists10"] = st["assists"]
                    st["dmg10"] = round(st["dmg"])
                    st["cs10"] = st.get("cs", 0) + st["camps"]
                if p.level >= 7 and p.id in plans and p.stage < 2:
                    prepare_branch(p, plans[p.id])

    timeout = match.winner is None and early is None
    if early is not None:
        winner = early[0]
    elif timeout:
        towers = [sum(1 for s in world.structures() if s.team == t and s.alive and
                      s.__class__.__name__ == "Structure") for t in (0, 1)]
        if towers[0] != towers[1]:
            winner = 0 if towers[0] > towers[1] else 1
        else:
            sc = [(sum(stat[p.id]["kills"] for p in units if p.team == t),
                   sum(stat[p.id]["dmg"] for p in units if p.team == t)) for t in (0, 1)]
            winner = 0 if sc[0] >= sc[1] else 1
    else:
        winner = match.winner
    for p in units:
        s = stat[p.id]
        s["level"] = p.level
        s["final_name"] = p.name
        s["types"] = list(p.types)
        s["cc"] = round(s["cc"], 1)
        s["support"] = round(s["support"])
        s["gold"] = round(float(getattr(p, "gold", 0)))
        s["maxhit"] = round(s["maxhit"])
        s["selfheal"] = round(s["selfheal"])
        s["items"] = len(getattr(p, "items", []))
        for k_ in ("dmg_minion", "dmg_wild", "sdmg"):
            s[k_] = round(s.get(k_, 0.0))
        s.pop("streak", None)
        for k_, v_ in getattr(match, "bot_stat", {}).get(p.id, {}).items():
            s["bp_" + k_] = round(v_, 1)
        tr_ = getattr(match, "bot_trace", {}).get(p.id)
        if tr_:
            s["u_time"] = {k_: round(v_, 1) for k_, v_ in tr_["time"].items() if v_ > 0}
            s["u_switches"] = tr_["switches"]
    return {"seed": seed, "winner": winner, "timeout": timeout,
            "early_stop": None if early is None else {"time": early[1], "adv": early[2]},
            "networth": [round(networth(t)) for t in (0, 1)],
            "train": {"vision_stride": match.vision.stride, "minion_stride": match.minion_ai_stride},
            "open_nexus": OPTS["open_nexus"], "plan": OPTS["plan"], "utility_teams": list(u_teams),
            "end": {"towers": [{ln: sum(1 for x in world.structures() if x.team == t and x.alive
                                        and x.kind == "tower" and x.lane == ln) for ln in LANES}
                               for t in (0, 1)],
                    "core_hp": [round(c.hp) for c in sorted(world.cores(), key=lambda c: c.team)],
                    "core_events": core_ev}, "time": round(match.time, 1),
            "jungler": [team_info[0]["jungler"], team_info[1]["jungler"]],
            "support": [team_info[0]["support"], team_info[1]["support"]],
            "units": list(stat.values())}


def make_jobs(n, start_seed):
    """Squadre casuali ma BILANCIATE. Ogni squadra ha UN jungler (scelto tra quelli
    che possono farlo) e 4 giocatori diversi tra loro. Si pesca sempre tra i meno
    usati finora (a parita' a caso), cosi ogni Pokemon gioca quasi lo stesso numero
    di partite; le prime n partite sono le stesse anche se si chiede un n maggiore."""
    rng = random.Random(start_seed)
    names = [load_pokemon_def(str(ROOT / rel)).name for rel in config.ROSTER]
    jg_idx = [names.index(n) for n in JUNGLERS]
    used = [0] * len(names)
    jused = [0] * len(names)
    jobs = []
    for i in range(n):
        jungs = sorted(jg_idx, key=lambda x: (jused[x], rng.random()))[:2]
        for x in jungs:
            jused[x] += 1
            used[x] += 1
        pool = [x for x in range(len(names)) if x not in jungs]
        picks = sorted(pool, key=lambda x: (used[x], rng.random()))[:8]
        for x in picks:
            used[x] += 1
        rng.shuffle(picks)
        jobs.append((start_seed * 100000 + i, jungs[0], picks[:4], jungs[1], picks[4:]))
    return jobs


def parse_until(txt):
    """'16:00' -> timestamp di oggi (o di domani se l'ora e' gia' passata)."""
    h, m = (int(x) for x in txt.split(":"))
    now = datetime.now()
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t.timestamp()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=160)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--until", default=None,
                    help="HH:MM: non parte una partita che non farebbe in tempo a finire")
    ap.add_argument("--open-nexus", action="store_true",
                    help="il nexus e' attaccabile appena una lane non ha piu torri")
    ap.add_argument("--plan", action="store_true",
                    help="IA a piani: shopping, assedio, aiuto alle torri, roam del support, gank piu largo")
    ap.add_argument("--utility", default=None, choices=["both", "0", "1", "alt"],
                    help="IA a punteggio: per entrambe, solo la squadra 0/1, o alt = a turno per seme (A/B)")
    ap.add_argument("--max-minutes", type=float, default=MAX_TIME / 60.0,
                    help="minuti di gioco massimi per partita")
    ap.add_argument("--early-stop", type=float, default=0.0, metavar="SOGLIA",
                    help="ferma le partite gia' decise (vantaggio >= SOGLIA, vedi EARLY_STOP; 0 = spento)")
    ap.add_argument("--vision-stride", type=int, default=1,
                    help="allenamento: visione ricalcolata ogni N tick (approssimata)")
    ap.add_argument("--minion-stride", type=int, default=1,
                    help="allenamento: IA dei minion ogni N tick (approssimata)")
    ap.add_argument("--status", default=str(ROOT / "tools" / "tier_status.json"))
    ap.add_argument("--out", default=str(ROOT / "tools" / "tier_matches_5v5.jsonl"))
    a = ap.parse_args()
    out = Path(a.out)
    status = Path(a.status)
    deadline = parse_until(a.until) if a.until else None
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["seed"])
            except (ValueError, KeyError):
                pass
    todo = [j for j in make_jobs(a.matches, a.seed) if j[0] not in done]
    print(f"{len(done)} gia' fatte, {len(todo)} da giocare con {a.workers} processi"
          + (f", stop alle {a.until}" if a.until else ""), flush=True)
    t0 = time.time()
    running = {}                    # seed -> istante di avvio
    durations = []                  # secondi reali per partita (per sapere se c'e' tempo)
    finished = 0
    queue = list(todo)
    reason = "finito"

    def write_status(state):
        data = {"pid": os.getpid(), "state": state, "started": t0, "updated": time.time(),
                "out": str(out), "deadline": deadline, "workers": a.workers,
                "done_before": len(done), "finished": finished, "running": len(running),
                "running_since": sorted(running.values()), "queued": len(queue),
                "avg_match_s": (sum(durations) / len(durations)) if durations else None,
                "out_lines": sum(1 for _ in out.open(encoding="utf-8")) if out.exists() else 0}
        tmp = status.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(status)

    def can_start():
        if deadline is None:
            return True
        est = (max(durations) * 1.15) if durations else 16 * 60.0
        return time.time() + est <= deadline

    with Pool(a.workers, initializer=_init_worker,
              initargs=(a.open_nexus, a.max_minutes * 60.0, a.plan, a.utility,
                        {"threshold": a.early_stop} if a.early_stop else None,
                        a.vision_stride, a.minion_stride)) as pool, out.open("a", encoding="utf-8") as f:
        results = []
        last_beat = 0.0
        while True:
            while queue and len(running) < a.workers and can_start():
                job = queue.pop(0)
                running[job[0]] = time.time()
                pool.apply_async(play, (job,), callback=results.append)
            if not running and (not queue or not can_start()):
                reason = "finito" if not queue else "limite orario"
                break
            while results:
                res = results.pop(0)
                started = running.pop(res["seed"], time.time())
                durations.append(time.time() - started)
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                f.flush()
                finished += 1
                el = time.time() - t0
                print(f"{finished} fatte  {el:.0f}s  (partita {durations[-1]:.0f}s)", flush=True)
            if time.time() - last_beat > 20:
                write_status("running")
                last_beat = time.time()
            time.sleep(1.0)
    write_status("stopped: " + reason)
    print(f"Fine ({reason}): {finished} partite in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
