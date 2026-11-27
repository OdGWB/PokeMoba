"""La pendenza (d networth/dt) aggiunge informazione oltre al livello? AUC e logistica k-fold per seed.
    python tools/slope_check.py trace1.json [trace2.json ...]"""
import json, sys
import numpy as np
sys.path[:0] = ["tools"]
import phi_fit
res = []
for p in sys.argv[1:]: res += json.load(open(p))
series = []
for r in res:
    L = r["log"]; side = r["side"]; team = {int(k): v["team"] for k, v in L["all"].items()}
    ts = sorted({row[0] for v in L["st"].values() for row in v}); w = {t: [0.0, 0.0] for t in ts}
    for pid, rows in L["st"].items():
        for row in rows: w[row[0]][team[int(pid)]] += row[3]
    d = np.array([(w[t][side] - w[t][1 - side]) / 1000.0 for t in ts]); series.append((np.array(ts), d, 1.0 if r["winner"] == side else 0.0, r["seed"]))
def at(ts, d, t): return d[int(np.argmin(np.abs(ts - t)))]
def cv(F, y, g, k=5):
    seeds = np.unique(g); rng = np.random.RandomState(0); rng.shuffle(seeds)
    fo = {s: i % k for i, s in enumerate(seeds)}; f = np.array([fo[s] for s in g]); P = np.zeros(len(y))
    sd = F.std(0) + 1e-9; Z = F / sd
    for i in range(k):
        tr = f != i; A = np.vstack([Z[tr], -Z[tr]]); yy = np.concatenate([y[tr], 1 - y[tr]])
        P[f == i] = phi_fit.pred(Z[f == i], phi_fit.fit(A, yy, lam=2.0))
    return phi_fit.auc(P, y)
print("| T | AUC livello | AUC pend.60s | AUC pend.120s | livello+pend.60 | livello+pend.120 | livello+pend60+accel |")
print("|---|---|---|---|---|---|---|")
for T in (180, 240, 300, 360, 480, 600):
    rows = []; y = []; g = []
    for ts, d, win, seed in series:
        if ts[-1] < T + 5: continue
        L0 = at(ts, d, T); s60 = (L0 - at(ts, d, T - 60)) / 60; s120 = (L0 - at(ts, d, T - 120)) / 120
        acc = s60 - (at(ts, d, T - 60) - at(ts, d, T - 120)) / 60
        rows.append([L0, s60, s120, acc]); y.append(win); g.append(seed)
    F = np.array(rows); y = np.array(y); g = np.array(g)
    a = [phi_fit.auc(F[:, i], y) for i in (0, 1, 2)]
    print(f"| {T // 60}'{T % 60:02d} (n={len(y)}) | {a[0]:.3f} | {a[1]:.3f} | {a[2]:.3f} | {cv(F[:, [0, 1]], y, g):.3f} | {cv(F[:, [0, 2]], y, g):.3f} | {cv(F[:, [0, 1, 3]], y, g):.3f} |")
