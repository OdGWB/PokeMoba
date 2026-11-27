"""Screening di vettori casuali con selezione a stadi (successive halving), partite a orizzonte 6' e fitness Phi.
    python tools/screen_random.py --out tools/cma_out/screen [--n 200] [--horizon 360]
Vettori di squadra interi (tutti i gruppi insieme) contro BASE.
Campionatori: meta' uniformi in [0,1]^d, meta' gaussiani attorno alla media di gen 30 (sigma 0.3, tagliati).
Stadi: 200 x 4 partite -> migliori 30 x +16 -> migliori 10 x +36. Ogni stadio usa semi nuovi (gli stessi per tutti).
Riprendibile: ogni partita finita va in out/results.jsonl."""
import argparse, json, os, sys
from pathlib import Path
os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
import multiprocessing as mp  # noqa: E402
import numpy as np  # noqa: E402
import cma_tune  # noqa: E402


def encode(lay, params):
    return cma_tune.x0_of(lay, params)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tools/cma_out/screen")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--horizon", type=float, default=360.0)
    ap.add_argument("--phi", default="reports/phi_g35_g30_weights.json")
    ap.add_argument("--center", default="tools/cma_out/gen5_mean_g30.json")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--stages", default="2:30,8:10,18:0", help="seed:tieni, ... (seed per candidato; tieni=quanti passano)")
    a = ap.parse_args()
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    import tier_sim
    lay = cma_tune.layout(cma_tune.GROUPS)
    cf, rf = out / "candidates.json", out / "results.jsonl"
    if cf.exists():
        C = json.loads(cf.read_text())
    else:
        rng = np.random.RandomState(12345); mu = np.array(encode(lay, json.loads(Path(ROOT / a.center).read_text())))
        C = []
        for i in range(a.n):
            if i % 2 == 0: x = rng.uniform(0, 1, len(lay)); kind = "uniforme"
            else: x = np.clip(mu + 0.3 * rng.randn(len(lay)), 0, 1); kind = "gauss0.3"
            C.append({"id": i, "kind": kind, "x": x.tolist(), "params": cma_tune.decode(lay, x)})
        cf.write_text(json.dumps(C))
    phi = json.loads(Path(ROOT / a.phi).read_text())
    done = {}
    if rf.exists():
        for ln in rf.read_text().splitlines():
            r = json.loads(ln); done[(r["stage"], r["cid"], r["seed"], r["side"])] = r["score"]
    stages = [(int(s.split(":")[0]), int(s.split(":")[1])) for s in a.stages.split(",")]
    alive = [c["id"] for c in C]; scores = {c["id"]: [] for c in C}
    with mp.get_context("spawn").Pool(a.workers, initializer=cma_tune._init,
                                      initargs=(a.horizon, None, 3, 2, phi)) as pool, rf.open("a", encoding="utf-8") as fo:
        for si, (nseeds, keep) in enumerate(stages):
            jobs = tier_sim.make_jobs(nseeds, 20000 + 1000 * si)
            tasks, meta = [], []
            for cid in alive:
                for j in jobs:
                    for side in (0, 1):
                        k = (si, cid, j[0], side)
                        if k in done: scores[cid].append(done[k]); continue
                        tasks.append((j, side, C[cid]["params"], cma_tune.BASE_PARAMS)); meta.append(k)
            print(f"stadio {si}: {len(alive)} candidati, {len(tasks)} partite da fare", flush=True)
            for n, (k, r) in enumerate(zip(meta, pool.imap(cma_tune._eval, tasks, chunksize=1))):
                scores[k[1]].append(r["score"]); done[k] = r["score"]
                fo.write(json.dumps({"stage": k[0], "cid": k[1], "seed": k[2], "side": k[3], "score": r["score"]}) + "\n"); fo.flush()
                if n % 50 == 0: print(f"  {n + 1}/{len(tasks)}", flush=True)
            order = sorted(alive, key=lambda c: -np.mean(scores[c]))
            if keep: alive = order[:keep]
            print(f"stadio {si}: migliori " + ", ".join(f"{c}({C[c]['kind'][:3]}) {np.mean(scores[c]):+.2f}" for c in order[:8]), flush=True)
    final = sorted(alive, key=lambda c: -np.mean(scores[c]))
    L = ["# Screening casuale a stadi (partite a 6', fitness Phi, avversario BASE)", "",
         f"{len(C)} candidati, stadi (seed per candidato:passano) = {a.stages}.", "", "| cand | campionatore | partite | 2Phi-1 medio |", "|---|---|---|---|"]
    for c in final: L.append(f"| {c} | {C[c]['kind']} | {len(scores[c])} | {np.mean(scores[c]):+.3f} |")
    allm = {k: np.mean([np.mean(scores[c]) for c in range(len(C)) if C[c]["kind"] == k and scores[c]]) for k in ("uniforme", "gauss0.3")}
    L += ["", "Media dei candidati dopo il primo stadio (tutti i 200 non hanno lo stesso numero di partite, solo stadio 1): " +
          ", ".join(f"{k} {v:+.3f}" for k, v in allm.items())]
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    json.dump({str(c): C[c]["params"] for c in final}, (out / "top.json").open("w"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
