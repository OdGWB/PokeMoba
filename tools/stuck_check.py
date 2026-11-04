"""Controllo incastri: gioca una partita bot headless e segnala le unita'
con il centro dentro un tile bloccante o ferme con un percorso da > 2 s."""
import sys, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import config
import tier_sim as ts
from engine.entities import Unit
from engine.grid import BLOCKING

def run(seed, minutes, mapname=None):
    random.seed(seed)
    defs = [ts.load_pokemon_def(str(ROOT / r)) for r in config.ROSTER]
    md = ts.load_map(str(ROOT / (mapname or config.DEFAULT_MAP)))
    world = ts.World(md.grid); match = ts.Match(world, md); match.vision = ts.FastVision(world.grid)
    idx = random.sample(range(len(defs)), 6)
    for team in (0, 1):
        lanes = ts.LANES[:]; random.shuffle(lanes)
        for lane, i in zip(lanes, idx[team*3:team*3+3]):
            ts._spawn(world, md, team, lane, defs[i])
    match.assign_junglers(); match.vision.update(world, 0); match.vision.update(world, 1)
    dt = config.TICK_DT; tick = 0
    inwall = {}; still = {}; last = {}
    g = world.grid
    while match.time < minutes * 60 and not getattr(match, "winner", None) is not None:
        match.update(dt, tick); tick += 1
        for e in list(world.entities.values()):
            if not isinstance(e, Unit) or not e.alive: continue
            t = g.tile_at(int(e.pos.x // 1), int(e.pos.y // 1))
            kind = type(e).__name__
            if t in BLOCKING:
                inwall.setdefault((kind, e.id), (round(match.time), e.pos.x, e.pos.y, t))
            lp = last.get(e.id)
            if e.path and lp and abs(lp[0].x - e.pos.x) + abs(lp[0].y - e.pos.y) < 1e-4:
                if match.time - lp[1] > 2.0 and not getattr(e, "stunned_until", 0) > match.time:
                    still.setdefault((kind, e.id), (round(match.time), e.pos.x, e.pos.y, [(p.x, p.y, g.tile_at(int(p.x), int(p.y))) for p in e.path], e.speed, [(o.id, round(o.pos.x,2), round(o.pos.y,2), round(o.radius,2)) for o in world.entities.values() if isinstance(o, Unit) and o is not e and abs(o.pos.x-e.pos.x) < 1 and abs(o.pos.y-e.pos.y) < 1]))
            else:
                last[e.id] = (e.pos, match.time)
    return inwall, still

if __name__ == "__main__":
    for seed in range(int(sys.argv[1]) if len(sys.argv) > 1 else 3):
        iw, st = run(seed, float(sys.argv[2]) if len(sys.argv) > 2 else 4)
        print("seed", seed, "in-muro:", len(iw), "fermi:", len(st))
        for k, v in list(iw.items())[:6]: print("  muro", k, v)
        for k, v in list(st.items())[:6]: print("  fermo", k, v)
