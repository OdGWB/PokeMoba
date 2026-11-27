"""Punto 1 del piano reward: fit di Phi(s,t) = P(vittoria candidato | stato) dalle tracce della suite.
    python tools/phi_fit.py out_prefix trace1.json [trace2.json ...]
Una riga ogni 5 s per partita, vista del candidato (feature = candidato meno base, simmetriche).
Valutazione con k-fold raggruppato per seed (le due facce/params dello stesso seed non finiscono mai
in train e test insieme). Produce out_prefix.md (AUC per minuto, modelli a confronto, pesi)
e out_prefix_auc.png. Salva anche i pesi in out_prefix_weights.json (Phi riusabile)."""
import bisect, json, os, sys
os.environ["SDL_VIDEODRIVER"] = "dummy"
import numpy as np

CAP = 840.0
NAMES = ["worth", "level", "alive", "hp", "kills", "towers", "camps", "cs", "thp", "core"]


def rows_of(res):
    X, y, T, G = [], [], [], []
    for r in res:
        L = r["log"]; side = r["side"]
        ids = {int(k): v["team"] for k, v in L["all"].items()}
        al = {int(k): [p[3] for p in v["p"]] for k, v in L["all"].items()}
        kt = sorted((k[0], k[6]) for k in L["kills"] if int(k[3]) in ids and k[6] is not None)   # (t, team killer) su Pokemon
        st_ = sorted((k[0], k[6]) for k in L["kills"] if int(k[3]) not in ids and k[6] is not None)  # strutture
        farm = sorted((f[0], f[1], ids.get(int(f[2]), -1)) for f in L["farm"])
        ts = sorted({row[0] for v in L["st"].values() for row in v})
        stm = {int(k): {row[0]: row for row in v} for k, v in L["st"].items()}
        strm = {row[0]: row for row in L.get("str", [])}   # (t, torri0, hp torri0, nucleo0, torri1, hp torri1, nucleo1)
        for t in ts:
            f = {0: dict.fromkeys(NAMES, 0.0), 1: dict.fromkeys(NAMES, 0.0)}
            for pid, tm in ids.items():
                row = stm[pid].get(t)
                if row is None: continue
                a = al[pid][min(len(al[pid]) - 1, int(t))]
                f[tm]["worth"] += row[3]; f[tm]["level"] += row[2]; f[tm]["alive"] += 1.0 if a else 0.0
                f[tm]["hp"] += row[1] / 100.0 if a else 0.0
            if t in strm:
                q = strm[t]; f[0]["thp"], f[0]["core"], f[1]["thp"], f[1]["core"] = q[2], q[3], q[5], q[6]
            for tt, tm in kt:
                if tt <= t and tm in f: f[tm]["kills"] += 1
            for tt, kind, tm in farm:
                if tt <= t and tm in f:
                    if kind == "tower": f[tm]["towers"] += 1
                    elif kind in ("camp", "legend"): f[tm]["camps"] += 1
                    elif kind == "cs": f[tm]["cs"] += 1
            me, ot = f[side], f[1 - side]
            x = []
            for n in NAMES:
                a, b = me[n], ot[n]
                x.append((a - b) / (a + b + (1000.0 if n == "worth" else 0.5 if n == "core" else 3.0)))   # differenza normalizzata, in [-1,1]
            w1 = 1.0 if r["winner"] == side else 0.0
            X.append(x); T.append(t); y.append(w1); G.append(r["seed"])
            X.append([-v for v in x]); T.append(t); y.append(1.0 - w1); G.append(r["seed"])   # vista speculare
    return np.array(X), np.array(y), np.array(T), np.array(G)


def feats(X, T, inter):
    u = (T / CAP)[:, None]
    return np.hstack([X, X * u]) if inter else X


def fit(Xm, y, lam=1.0, it=30):
    A = np.hstack([Xm, np.ones((len(Xm), 1))]); w = np.zeros(A.shape[1])
    R = lam * np.eye(len(w)); R[-1, -1] = 0
    for _ in range(it):
        p = 1 / (1 + np.exp(-np.clip(A @ w, -30, 30)))
        g = A.T @ (p - y) + R @ w
        H = A.T @ (A * (p * (1 - p))[:, None]) + R + 1e-6 * np.eye(len(w))
        w -= np.linalg.solve(H, g)
    return w


def pred(Xm, w):
    return 1 / (1 + np.exp(-np.clip(np.hstack([Xm, np.ones((len(Xm), 1))]) @ w, -30, 30)))


def auc(p, y):
    if y.min() == y.max(): return float("nan")
    o = np.argsort(p, kind="mergesort"); ps = p[o]; rk = np.empty(len(p))
    first = np.r_[True, ps[1:] != ps[:-1]]; gid = np.cumsum(first) - 1
    start = np.flatnonzero(first); cnt = np.diff(np.r_[start, len(p)])
    rk[o] = (start + (cnt + 1) / 2.0)[gid]       # rango medio sui pareggi
    n1 = y.sum(); n0 = len(y) - n1
    return float((rk[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def cv(X, y, T, G, cols, inter, k=5):
    seeds = np.unique(G); rng = np.random.RandomState(0); rng.shuffle(seeds)
    fold = {s: i % k for i, s in enumerate(seeds)}; f = np.array([fold[g] for g in G])
    P = np.zeros(len(y)); Xm = feats(X[:, cols], T, inter)
    for i in range(k):
        w = fit(Xm[f != i], y[f != i]); P[f == i] = pred(Xm[f == i], w)
    return P


def main():
    pref = sys.argv[1]; res = []
    for p in sys.argv[2:]: res += json.load(open(p))
    X, y, T, G = rows_of(res)
    print("righe", len(y), "partite", len(res), "seed", len(set(G.tolist())), flush=True)
    models = {"solo networth": ([0], False), "networth+livello+vivi+hp": ([0, 1, 2, 3], False),
              "+ torri/nucleo (no kill/farm)": ([0, 1, 2, 3, 8, 9], False),
              "tutte (lineare)": (list(range(len(NAMES))), False),
              "tutte x tempo": (list(range(len(NAMES))), True)}
    Ps = {n: cv(X, y, T, G, c, i) for n, (c, i) in models.items()}
    mins = [2, 4, 6, 8, 10, 12]
    L = [f"# Phi(s,t) = P(vittoria candidato | stato): fit dalle tracce", "",
         f"{len(res)} partite, {len(y)} istanti (ogni 5 s), {len(set(G.tolist()))} seed, k-fold per seed. "
         f"Dataset simmetrico (ogni istante in entrambe le viste).", "", "## AUC per minuto (finestra +-10 s)", "",
         "| modello | " + " | ".join(f"{m}'" for m in mins) + " | tutti | Brier |", "|---|" + "---|" * (len(mins) + 2)]
    curves = {}
    for n, P in Ps.items():
        a = []
        for m in mins:
            s = np.abs(T - m * 60) <= 10; a.append(auc(P[s], y[s]) if s.sum() > 20 else float("nan"))
        curves[n] = a
        L.append(f"| {n} | " + " | ".join(f"{v:.3f}" for v in a) + f" | {auc(P, y):.3f} | {np.mean((P - y) ** 2):.3f} |")
    # curva fine
    tg = np.arange(60, 840, 30); fine = {}
    for n in ("solo networth", "tutte x tempo"):
        fine[n] = [auc(Ps[n][np.abs(T - t) <= 15], y[np.abs(T - t) <= 15]) for t in tg]
    # pesi finali (tutti i dati) per il modello migliore lineare
    cols = list(range(len(NAMES))); w = fit(feats(X[:, cols], T, True), y)
    L += ["", "## Pesi (modello 'tutte x tempo', feature = differenza normalizzata candidato-base)", "",
          "| feature | peso base | peso x t/840 |", "|---|---|---|"]
    for i, n in enumerate(NAMES): L.append(f"| {n} | {w[i]:+.2f} | {w[len(NAMES) + i]:+.2f} |")
    L.append(f"| intercetta | {w[-1]:+.2f} | |")
    json.dump({"names": NAMES, "cap": CAP, "w": w.tolist(), "interactions": True}, open(pref + "_weights.json", "w"))
    # calibrazione
    P = Ps["tutte x tempo"]; L += ["", "## Calibrazione (tutte x tempo, out-of-fold)", "", "| P predetta | n | vittorie reali |", "|---|---|---|"]
    for lo in np.arange(0, 1, 0.2):
        s = (P >= lo) & (P < lo + 0.2 + (1e-9 if lo > 0.7 else 0))
        if s.sum(): L.append(f"| {lo:.1f}-{lo + 0.2:.1f} | {int(s.sum())} | {y[s].mean():.2f} |")
    # primo istante in cui Phi e' "decisa": |P-0.5|>0.4 e resta tale (solo informativo)
    open(pref + ".md", "w", encoding="utf-8").write("\n".join(L) + "\n")
    # grafico AUC(t)
    import pygame; pygame.init()
    W, H = 760, 380; S = pygame.Surface((W, H)); S.fill((16, 18, 22)); f = pygame.font.SysFont("consolas", 13)
    x0, y0, x1, y1 = 50, 30, W - 20, H - 40
    for v in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        yy = y1 - (v - 0.45) / 0.55 * (y1 - y0); pygame.draw.line(S, (45, 48, 56), (x0, yy), (x1, yy)); S.blit(f.render(f"{v:.1f}", True, (170, 175, 185)), (8, yy - 7))
    for m in range(0, 15, 2):
        xx = x0 + m * 60 / 840 * (x1 - x0); S.blit(f.render(f"{m}'", True, (170, 175, 185)), (xx - 6, y1 + 8))
    for (n, c), col in zip(fine.items(), ((230, 120, 80), (90, 190, 250))):
        pts = [(x0 + t / 840 * (x1 - x0), y1 - (min(max(v, 0.45), 1.0) - 0.45) / 0.55 * (y1 - y0)) for t, v in zip(tg, c) if v == v]
        pygame.draw.lines(S, col, False, pts, 2); S.blit(f.render(n, True, col), (x0 + 10, y0 + (0 if "solo" in n else 18)))
    S.blit(f.render("AUC di Phi nel tempo (k-fold per seed)", True, (225, 228, 232)), (x0, 6))
    pygame.image.save(S, pref + "_auc.png"); print("\n".join(L), flush=True)


if __name__ == "__main__":
    main()
