"""Percentuale di vittoria per Pokemon: IA allenata contro SE STESSA (forza dell'IA cancellata).
    python tools/char_winrates.py tools/cma_out/gen5_mean_g25.json --matches 300 --out tools/cma_out/char_wr.json"""
import argparse, json, os, sys
from multiprocessing import get_context
from pathlib import Path
os.environ.setdefault("PYTHONHASHSEED", "0"); os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
import cma_tune

def play(task):
    import tier_sim
    job, prm = task
    tier_sim.OPTS["params"] = {0: prm, 1: prm}
    r = tier_sim.play(job)
    return {"seed": job[0], "winner": r["winner"], "time": r["time"],
            "units": [{k: u.get(k) for k in ("team", "name", "final_name", "kills", "deaths", "assists", "dmg", "gold", "smites")}
                      for u in r["units"]]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("params"); ap.add_argument("--matches", type=int, default=300)
    ap.add_argument("--seed-base", type=int, default=7000); ap.add_argument("--workers", type=int, default=18)
    ap.add_argument("--out", default="tools/cma_out/char_wr.json")
    a = ap.parse_args()
    import tier_sim
    prm = json.loads(Path(a.params).read_text())
    jobs = tier_sim.make_jobs(a.matches, a.seed_base)[:a.matches]
    res = []
    with get_context("spawn").Pool(a.workers, initializer=cma_tune._init, initargs=(14 * 60.0, {"threshold": 2.0}, 3, 2)) as pool:
        for i, r in enumerate(pool.imap(play, [(j, prm) for j in jobs])):
            res.append(r); print(i + 1, len(jobs), flush=True)
    Path(a.out).write_text(json.dumps(res))

if __name__ == "__main__":
    main()
