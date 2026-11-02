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
MAX_TIME = 10 * 60.0        # secondi di gioco: oltre, si decide per torri/uccisioni/danno
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

    def on_death(victim, killer):
        if isinstance(victim, Pokemon) and victim.id in stat:
            stat[victim.id]["deaths"] += 1
            if isinstance(killer, Pokemon) and killer.id in stat and killer.team != victim.team:
                stat[killer.id]["kills"] += 1
        return orig_death(victim, killer)

    def deal(attacker, target, amount, *a, **kw):
        if isinstance(target, Pokemon) and target.id in stat and amount > 0:
            hp0 = target.hp
            r = orig_dmg(attacker, target, amount, *a, **kw)
            lost = max(0.0, hp0 - target.hp)
            stat[target.id]["taken"] += lost
            if isinstance(attacker, Pokemon) and attacker.id in stat and attacker.team != target.team:
                stat[attacker.id]["dmg"] += lost
            return r
        return orig_dmg(attacker, target, amount, *a, **kw)

    match._on_death = on_death
    match._deal_damage = deal

    dt = config.TICK_DT
    tick = 0
    while match.winner is None and match.time < MAX_TIME:
        match.update(dt, tick)
        tick += 1

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
    ap.add_argument("--matches", type=int, default=336)
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
