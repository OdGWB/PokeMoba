"""Punto 2: la fitness a orizzonte troncato ordina i candidati come quella finale?
    python tools/phi_rank.py run    out.json [--seeds 18] [--seed-base 11000] [--workers 16]
    python tools/phi_rank.py report out.json reports/prefix phi_weights.json
12 candidati (6 campionati dalla distribuzione CMA di gen30ref + base, gen15, gen25, gen30, gen35 media/best)
contro lo STESSO avversario del training (media gen 30), stessi seed per tutti (numeri casuali comuni).
Per ogni partita si salva: punteggio finale (stessa formula di cma_tune) e, a T = 4/6/8/10 min,
 phi(T) (modello di phi_fit), differenza di networth e di torri vive."""
import argparse, json, math, os, pickle, sys
from multiprocessing import get_context
from pathlib import Path
os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
import numpy as np  # noqa: E402

TS = (240, 360, 480, 600)
CO = ROOT / "tools" / "cma_out"


def candidates(n_sample):
    import cma_tune
    out = {"base": cma_tune.BASE_PARAMS}
    for lab, f in (("g15", "gen5_mean_g15.json"), ("g25", "gen5_mean_g25.json"), ("g30", "gen5_mean_g30.json"),
                   ("g35_mean", "g35_mean.json"), ("g35_best", "g35_best.json")):
        out[lab] = json.loads((CO / f).read_text())
    st = pickle.loads((CO / "gen30ref" / "state.pkl").read_bytes())
    es, lay = st["es"], st["lay"]
    for i, x in enumerate(es.ask(n_sample)):
        out[f"s{i}"] = cma_tune.decode(lay, x)
    return out


def work(task):
    import suite_trace, phi_fit
    label, job, side, cand, opp = task
    r = suite_trace.run((job, side, cand, opp))
    gold = r["networth"]; o = 1 - side
    tw = [sum(r["end"]["towers"][t].values()) for t in (0, 1)]
    win = 1.0 if r["winner"] == side else -1.0
    score = 0.5 * win + 0.25 * math.tanh((gold[side] - gold[o]) / 5000.0) + 0.25 * (tw[side] - tw[o]) / 9.0
    X, y, T, G = phi_fit.rows_of([r]); X, T = X[0::2], T[0::2]     # solo vista del candidato
    L = r["log"]; sm = {row[0]: row for row in L.get("str", [])}
    ids = {int(k): v["team"] for k, v in L["all"].items()}
    snap = {}
    for t0 in TS:
        k = int(np.argmin(np.abs(T - t0)))
        if abs(T[k] - t0) > 10: continue
        tt = int(T[k]); nw = [0.0, 0.0]
        for pid, rows in L["st"].items():
            for row in rows:
                if row[0] == tt: nw[ids[int(pid)]] += row[3]
        q = sm.get(tt); twd = ((q[1] - q[4]) if side == 0 else (q[4] - q[1])) if q else 0
        snap[str(t0)] = {"x": X[k].tolist(), "t": tt, "nwd": nw[side] - nw[o], "twd": twd}
    return {"label": label, "seed": job[0], "side": side, "score": score, "win": win > 0, "time": r["time"], "snap": snap}


def run(a):
    import tier_sim, cma_tune
    cf, jf = Path(a.out + ".cands.json"), Path(a.out + ".jsonl")
    if cf.exists():                      # candidati fissati al primo avvio: stessi in caso di ripresa
        cands = json.loads(cf.read_text())
    else:
        cands = candidates(6); cf.write_text(json.dumps(cands))
    opp = json.loads((CO / "gen5_mean_g30.json").read_text())
    jobs = tier_sim.make_jobs(a.seeds, a.seed_base)
    done = set(); res = []
    if jf.exists():
        for ln in jf.read_text().splitlines():
            r = json.loads(ln); res.append(r); done.add((r["label"], r["seed"], r["side"]))
    tasks = [(lab, j, s, c, opp) for lab, c in cands.items() for j in jobs for s in (0, 1)
             if (lab, j[0], s) not in done]
    print(f"gia' fatte {len(done)}, da fare {len(tasks)}", flush=True)
    with get_context("spawn").Pool(a.workers, initializer=cma_tune._init, initargs=(840.0,)) as pool, \
            jf.open("a", encoding="utf-8") as fo:
        for i, r in enumerate(pool.imap_unordered(work, tasks, chunksize=1)):
            res.append(r); fo.write(json.dumps(r) + "\n"); fo.flush()
            print(len(res), len(done) + len(tasks), r["label"], r["seed"], flush=True)
    Path(a.out).write_text(json.dumps(res))


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float); rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def report(a):
    res = json.loads(Path(a.out).read_text()); W = json.loads(Path(a.weights).read_text())
    w = np.array(W["w"]); nx = len(W["names"])

    def phi(x, t):
        x = np.array(x); z = float(np.dot(w[:nx], x) + np.dot(w[nx:2 * nx], x) * t / W["cap"] + w[-1])
        return 1 / (1 + math.exp(-z))
    labels = sorted({r["label"] for r in res}); seeds = sorted({r["seed"] for r in res})
    metrics = {"finale": lambda r: r["score"]}
    for t0 in TS:
        k = str(t0)
        def mk(k, kind):
            def f(r):
                s = r["snap"].get(k)
                if s is None: return float("nan")
                p = phi(s["x"], s["t"])
                if kind == "phi": return p
                return 0.5 * (2 * p - 1) + 0.25 * math.tanh(s["nwd"] / 5000.0) + 0.25 * s["twd"] / 9.0
            return f
        metrics[f"phi@{t0 // 60}'"] = mk(k, "phi"); metrics[f"score@{t0 // 60}'"] = mk(k, "score")
    M = {m: {l: np.nanmean([f(r) for r in res if r["label"] == l]) for l in labels} for m, f in metrics.items()}
    L = [f"# Fitness troncata vs finale: correlazione di rango tra candidati", "",
         f"{len(labels)} candidati x {len(seeds)} seed x 2 lati = {len(res) // len(labels)} partite ciascuno, "
         f"avversario = media gen 30 (come nel training). Spearman tra i {len(labels)} candidati.", ""]
    # affidabilita' della fitness finale: meta' seed contro meta' seed
    half = {s: i % 2 for i, s in enumerate(seeds)}
    A = [np.mean([r["score"] for r in res if r["label"] == l and half[r["seed"]] == 0]) for l in labels]
    B = [np.mean([r["score"] for r in res if r["label"] == l and half[r["seed"]] == 1]) for l in labels]
    L += [f"**Affidabilita' della fitness finale** (meta' seed contro l'altra meta'): Spearman {spearman(A, B):+.2f} "
          f"(e' il tetto realistico per qualunque proxy).", "",
          "| candidato | win% | finale | " + " | ".join(m for m in metrics if m != "finale") + " |",
          "|---|---|---|" + "---|" * (len(metrics) - 1)]
    for l in sorted(labels, key=lambda l: -M["finale"][l]):
        wr = np.mean([r["win"] for r in res if r["label"] == l])
        L.append(f"| {l} | {100 * wr:.0f}% | {M['finale'][l]:+.3f} | " + " | ".join(f"{M[m][l]:+.3f}" for m in metrics if m != "finale") + " |")
    L += ["", "## Correlazione con la fitness finale", "", "| metrica | Spearman tra candidati | Spearman per partita | Pearson per partita |", "|---|---|---|---|"]
    fin = np.array([r["score"] for r in res])
    for m, f in metrics.items():
        if m == "finale": continue
        v = np.array([f(r) for r in res]); ok = ~np.isnan(v)
        L.append(f"| {m} | {spearman([M['finale'][l] for l in labels], [M[m][l] for l in labels]):+.2f} | "
                 f"{spearman(fin[ok], v[ok]):+.2f} | {np.corrcoef(fin[ok], v[ok])[0, 1]:+.2f} |")
    # rumore: errore standard della media per candidato (finale vs proxy a 6')
    L += ["", "Errore standard della media finale per candidato: "
          f"{np.mean([np.std([r['score'] for r in res if r['label'] == l]) / math.sqrt(sum(r['label'] == l for r in res)) for l in labels]):.3f}"]
    Path(a.prefix + ".md").write_text("\n".join(L) + "\n", encoding="utf-8"); print("\n".join(L))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("out"); ap.add_argument("prefix", nargs="?"); ap.add_argument("weights", nargs="?")
    ap.add_argument("--seeds", type=int, default=18); ap.add_argument("--seed-base", type=int, default=11000)
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    run(a) if a.cmd == "run" else report(a)
