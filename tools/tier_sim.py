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
import os
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from engine.content import load_map, load_pokemon_def  # noqa: E402
from engine.entities import Pokemon  # noqa: E402
from engine.match import Match  # noqa: E402
from engine.vec import Vec2  # noqa: E402
from engine.world import World  # noqa: E402

from engine.entities import Structure, Unit  # noqa: E402
from engine.grid import TILE_BUSH  # noqa: E402
from engine.vision import BUSH_REVEAL, VisionSystem  # noqa: E402

LANES = ["top", "mid", "bot"]
MAX_TIME = 18 * 60.0        # secondi di gioco: oltre, si decide per torri/uccisioni/danno
ASSIST_WINDOW = 10.0     # secondi: chi ha colpito la vittima entro questo tempo e' assistente
SLOT_OFFSET = {"top": Vec2(-1.2, 0.0), "mid": Vec2(0.0, 0.0), "bot": Vec2(0.0, 1.2)}


class FastVision(VisionSystem):
    """Stessa visione dei nemici di VisionSystem, ma senza costruire gli insiemi di
    tile (nessuno li usa nel motore): ~3x piu' veloce, risultato identico."""

    def update(self, world, team):
        sources = self._sources(world, team)
        sig = frozenset((e.id, int(e.pos.x), int(e.pos.y), int(getattr(e, "vision", 0)))
                        for e in sources)
        sig |= frozenset(("inv", e.id) for e in world.entities.values()
                         if getattr(e, "invisible", False) and getattr(e, "team", team) != team)
        reveals = self.reveals.get(team) or ()
        if reveals:
            sig |= frozenset(("ping", round(x, 1), round(y, 1), r) for x, y, r in reveals)
            sig |= frozenset(("pos", u.id, int(u.pos.x), int(u.pos.y))
                             for u in world.entities.values()
                             if isinstance(u, Unit) and u.team != team and u.alive)
        if sig == self._sig.get(team):
            return False
        self._sig[team] = sig
        self.version[team] = self.version.get(team, 0) + 1
        circles = [(int(e.pos.x), int(e.pos.y), int(getattr(e, "vision", 0)) ** 2)
                   for e in sources]
        enemies = set()
        for u in world.entities.values():
            if not isinstance(u, Unit) or u.team == team or not u.alive:
                continue
            if any((u.pos.x - x) ** 2 + (u.pos.y - y) ** 2 <= r * r for x, y, r in reveals):
                enemies.add(u.id)
                continue
            tx, ty = int(u.pos.x), int(u.pos.y)
            if not any((tx - cx) ** 2 + (ty - cy) ** 2 <= r2 for cx, cy, r2 in circles):
                continue
            if getattr(u, "invisible", False):
                continue
            if self.grid.tile_at(tx, ty) == TILE_BUSH:
                if not any(e.pos.dist(u.pos) <= BUSH_REVEAL for e in sources):
                    continue
            enemies.add(u.id)
        self.visible_enemies[team] = enemies
        return True


def _spawn(world, map_data, team, lane, pdef):
    base = Vec2(*map_data.spawns[f"team{team}"]) + Vec2(0.5, 0.5)
    p = world.spawn_pokemon(
        pos=base + SLOT_OFFSET[lane], team=team, dex=pdef.dex, name=pdef.name,
        color=config.TEAM_COLORS[team], speed=pdef.base_speed, is_bot=True,
        assigned_lane=lane, types=pdef.types, base_stats=pdef.base_stats,
        growth=pdef.growth, moves=pdef.moves, evolutions=pdef.evolutions,
        role=pdef.role, passive=pdef.passive, attack_range=pdef.attack_range,
        attack_cooldown=pdef.attack_cooldown, attack_fx=pdef.attack_fx,
        rec_items=pdef.recommended_items)
    p.radius = pdef.radius
    return p


def play(job):
    """Una partita. job = (seed, roster_idx_team0, roster_idx_team1)."""
    seed, t0, t1 = job
    random.seed(seed)
    defs = [load_pokemon_def(str(ROOT / rel)) for rel in config.ROSTER]
    map_data = load_map(str(ROOT / config.DEFAULT_MAP))
    world = World(map_data.grid)
    match = Match(world, map_data)
    match.vision = FastVision(world.grid)

    stat = {}                       # id -> dict
    units = []
    for team, picks in ((0, t0), (1, t1)):
        lanes = LANES[:]
        random.shuffle(lanes)
        for lane, idx in zip(lanes, picks):
            p = _spawn(world, map_data, team, lane, defs[idx])
            stat[p.id] = {"name": defs[idx].name, "team": team, "idx": idx, "lane": lane,
                          "kills": 0, "deaths": 0, "dmg": 0.0, "taken": 0.0}
            units.append(p)
    match.assign_junglers()
    match.vision.update(world, 0)
    match.vision.update(world, 1)

    # Contatori (solo osservazione, nessun cambio di logica).
    orig_death = match._on_death
    orig_dmg = match._deal_damage

    last_hit = {}                   # id vittima -> {id attaccante: tempo ultimo colpo}
    ctx = {"caster": None}          # chi sta lanciando una mossa in questo momento

    for s in stat.values():
        s.update(assists=0, cc=0.0, support=0.0, t8=None)

    def on_death(victim, killer):
        if isinstance(victim, Pokemon) and victim.id in stat:
            stat[victim.id]["deaths"] += 1
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
                last_hit.setdefault(target.id, {})[attacker.id] = match.time
            return r
        return orig_dmg(attacker, target, amount, *a, **kw)

    def source_of(target):
        """Chi ha causato un controllo: chi sta lanciando, altrimenti chi ha colpito per ultimo."""
        c = ctx["caster"]
        if c is not None and c.team != target.team:
            return c
        hits = last_hit.get(target.id)
        if hits:
            aid, t = max(hits.items(), key=lambda kv: kv[1])
            if match.time - t <= 3.0:
                return next((u for u in units if u.id == aid), None)
        return None

    def wrap_cc(name, weight, dur_index):
        orig = getattr(match, name)

        def f(p, *args, **kw):
            if isinstance(p, Pokemon) and p.id in stat:
                src = source_of(p)
                if src is not None and src.id in stat:
                    try:
                        stat[src.id]["cc"] += weight * float(args[dur_index])
                    except (IndexError, TypeError, ValueError):
                        pass
            return orig(p, *args, **kw)
        setattr(match, name, f)

    # (nome, peso, posizione della durata negli argomenti dopo `p`)
    for name, w, di in (("_apply_stun", 1.0, 0), ("_apply_root", 1.0, 0),
                        ("_apply_sleep", 1.0, 0), ("_apply_fear", 1.0, 1),
                        ("_apply_airborne", 1.0, 0), ("_apply_confuse", 0.6, 0),
                        ("_apply_slow", 0.4, 1)):
        if hasattr(match, name):
            wrap_cc(name, w, di)

    orig_cast = match._cast

    def cast(p, *a, **kw):
        prev, ctx["caster"] = ctx["caster"], p
        try:
            return orig_cast(p, *a, **kw)
        finally:
            ctx["caster"] = prev

    orig_heal = match._give_heal
    orig_shield = match._give_shield

    def heal(caster, target, amount):
        hp0 = target.hp
        r = orig_heal(caster, target, amount)
        if (isinstance(caster, Pokemon) and caster.id in stat and target is not caster
                and isinstance(target, Pokemon) and target.id in stat):
            stat[caster.id]["support"] += max(0.0, target.hp - hp0)
        return r

    def shield(caster, target, amt, dur):
        if (isinstance(caster, Pokemon) and caster.id in stat and target is not caster
                and isinstance(target, Pokemon) and target.id in stat):
            stat[caster.id]["support"] += max(0.0, amt)
        return orig_shield(caster, target, amt, dur)

    match._on_death = on_death
    match._deal_damage = deal
    match._cast = cast
    match._give_heal = heal
    match._give_shield = shield

    dt = config.TICK_DT
    tick = 0
    while match.winner is None and match.time < MAX_TIME:
        match.update(dt, tick)
        tick += 1
        if tick % 30 == 0:
            for p in units:
                if p.level >= 8 and stat[p.id]["t8"] is None:
                    stat[p.id]["t8"] = round(match.time, 1)

    timeout = match.winner is None
    if timeout:
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
    return {"seed": seed, "winner": winner, "timeout": timeout, "time": round(match.time, 1),
            "units": list(stat.values())}


def make_jobs(n, start_seed, per_pokemon_balanced=True):
    """Squadre casuali ma BILANCIATE: ogni Pokemon compare lo stesso numero di volte."""
    rng = random.Random(start_seed)
    size = len(config.ROSTER)
    jobs, bag = [], []
    for i in range(n):
        picks = []
        while len(picks) < 6:
            if not bag:
                bag = list(range(size))
                rng.shuffle(bag)
            x = bag.pop()
            if x not in picks:
                picks.append(x)
            else:
                bag.insert(0, x)
                rng.shuffle(bag)
        jobs.append((start_seed * 100000 + i, picks[:3], picks[3:]))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=255)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "tools" / "tier_matches.jsonl"))
    a = ap.parse_args()
    out = Path(a.out)
    done = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["seed"])
            except (ValueError, KeyError):
                pass
    jobs = [j for j in make_jobs(a.matches, a.seed) if j[0] not in done]
    print(f"{len(done)} gia' fatte, {len(jobs)} da giocare con {a.workers} processi", flush=True)
    t0 = time.time()
    with Pool(a.workers) as pool, out.open("a", encoding="utf-8") as f:
        for k, res in enumerate(pool.imap_unordered(play, jobs), 1):
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            if k % 10 == 0 or k == len(jobs):
                el = time.time() - t0
                print(f"{k}/{len(jobs)}  {el:.0f}s  (~{el / k * (len(jobs) - k):.0f}s rimasti)",
                      flush=True)


if __name__ == "__main__":
    main()
