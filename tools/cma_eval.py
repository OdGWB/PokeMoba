"""Valuta parametri allenati (best.json / mean.json di cma_tune) contro l'IA di base.

Partite ESATTE (niente stop anticipato ne' stride), semi nuovi, ogni seme giocato sui
due lati. Stampa vittorie, punteggio medio e differenze di oro/torri/uccisioni.

    python tools/cma_eval.py tools/cma_out/fast1/best.json tools/cma_out/fast1/mean.json --seeds 18
"""
import argparse
import json
import math
import os
import sys
from multiprocessing import get_context
from pathlib import Path

os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]

import cma_tune  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("params", nargs="+", help="file json di parametri")
    ap.add_argument("--seeds", type=int, default=18)
    ap.add_argument("--seed-base", type=int, default=5000)
    ap.add_argument("--minutes", type=float, default=14.0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--out", default=None, help="jsonl con le singole partite")
    a = ap.parse_args()

    import tier_sim
    jobs = tier_sim.make_jobs(a.seeds, a.seed_base)
    cands = {Path(p).parent.name + "/" + Path(p).stem: json.loads(Path(p).read_text()) for p in a.params}
    tasks, names = [], []
    for name, prm in cands.items():
        for job in jobs:
            for side in (0, 1):
                tasks.append((job, side, prm, cma_tune.BASE_PARAMS))
                names.append(name)
    print(f"{len(tasks)} partite esatte su {a.workers} processi", flush=True)
    ctx = get_context("spawn")
    res = {n: [] for n in cands}
    with ctx.Pool(a.workers, initializer=cma_tune._init, initargs=(a.minutes * 60.0,)) as pool:
        for i, r in enumerate(pool.imap(cma_tune._eval, tasks)):
            r["cand"] = names[i]
            res[names[i]].append(r)
            if a.out:
                with open(a.out, "a") as f:
                    f.write(json.dumps(r) + "\n")
            print(f"[{i + 1}/{len(tasks)}] {names[i]} seed {r['seed']} lato {r['side']}: "
                  f"{'V' if r['win'] else 'S'} score {r['score']:+.2f}", flush=True)
    for n, rs in res.items():
        k = len(rs)
        w = sum(r["win"] for r in rs)
        p = w / k
        se = math.sqrt(p * (1 - p) / k)
        m = lambda key: sum(r[key] for r in rs) / k
        pairs = {}
        for r in rs:
            pairs.setdefault(r["seed"], []).append(r["win"])
        sweep = sum(all(v) for v in pairs.values())
        lost = sum(not any(v) for v in pairs.values())
        print(f"\n== {n} vs base ({k} partite)")
        print(f"  vittorie {w}/{k} = {p:.0%} (+-{se:.0%}); semi vinti su entrambi i lati {sweep}, "
              f"persi su entrambi {lost}, divisi {len(pairs) - sweep - lost}")
        print(f"  score {m('score'):+.3f}  oro {m('gold'):+.0f}  torri {m('towers'):+.2f}  "
              f"uccisioni {m('kills'):+.1f}  timeout {sum(r['timeout'] for r in rs)}  "
              f"durata media {m('time') / 60:.1f} min")


if __name__ == "__main__":
    main()
