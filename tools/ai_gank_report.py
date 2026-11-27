"""Gank e uccisioni dal json di jungle_trace (con eventi). Scrive <out>.md e <out>.png.
    python tools/ai_gank_report.py tools/cma_out/jt2_g25_mean.json reports/ai_g25_mean_gank --label "gen25 mean" """
import json, sys, os, math, collections
os.environ["SDL_VIDEODRIVER"] = "dummy"
import numpy as np, pygame
res = json.load(open(sys.argv[1])); out = sys.argv[2]
label = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else "cand"
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
n = len(res); W = 150
mean = lambda xs: sum(xs) / max(1, len(xs))

def team_of(r, who): return r["side"] if who == "cand" else 1 - r["side"]
def norm(tm, x, y): return (x, y) if tm == 0 else (W - x, W - y)

D = {}
for who in ("cand", "base"):
    G = []; K = []; jk = tk = 0; jdeaths = []; per = []
    for r in res:
        tm = team_of(r, who)
        kills = r["log"]["kills"]
        jg_ids = {d_id for d_id, d in r["log"]["all"].items() if d["team"] == tm and d["name"] in
                  {u["name"] for u in r["all"] if u["team"] == tm and u["smites"] is not None}}
        jid = next(iter(jg_ids), None)
        ng = 0
        for k in kills:
            t, x, y, vid, vteam, kid, kteam, ktype, asst = k
            vid, kid = str(vid), kid if kid is None else kid
            if vteam == 1 - tm and ktype == "Pokemon":         # nostra uccisione di un campione
                tk += 1; K.append((t, *norm(tm, x, y)))
                if kid is not None and (str(kid) == jid or str(jid) in [str(a) for a in asst]):
                    jk += 1
            if str(vid) == jid and vteam == tm:
                jdeaths.append((t, *norm(tm, x, y)))
        for g in r["log"]["ganks"]:
            if g["team"] != tm: continue
            end = g["end"] if g["end"] is not None else g["t"]
            hit = next((k for k in kills if k[3] == g["tid"] and g["t"] - 1 <= k[0] <= end + 4), None)
            dead = any(k[3] == g["jid"] and g["t"] <= k[0] <= end + 4 for k in kills)
            cred = hit is not None and (hit[5] == g["jid"] or g["jid"] in hit[8])
            G.append({**g, "ok": hit is not None, "cred": cred, "jdead": dead, "dur": end - g["t"], "game": r["seed"], "tm": tm,
                      "dist": math.dist(g["jpos"], g["tpos"])})
            ng += 1
        per.append(ng)
    D[who] = dict(G=G, K=K, jk=jk, tk=tk, jd=jdeaths, per=per)

L = [f"# Gank e uccisioni: {label} contro base", "", f"{n} partite esatte ({n//2} semi, entrambi i lati).", "",
     "Gank = il jungler assegna un bersaglio (`gank_id`) dal motore. *Riuscito* = il bersaglio muore entro la durata + 4 s; "
     "*merito* = il jungler è killer o assistente; *jungler morto* = muore durante o entro 4 s dalla fine.", "",
     "| | gank/partita | durata (s) | distanza (tile) | PV bersaglio | primo gank | riusciti | merito jungler | jungler morto |",
     "|---|---|---|---|---|---|---|---|---|"]
for who, d in D.items():
    G = d["G"]
    firsts = []
    for r in res:
        gs = [g["t"] for g in G if g["game"] == r["seed"] and g["tm"] == team_of(r, who)]
        if gs: firsts.append(min(gs))
    L.append(f"| {who} | {mean(d['per']):.1f} | {mean([g['dur'] for g in G]):.1f} | {mean([g['dist'] for g in G]):.0f} | "
             f"{mean([g['hp'] for g in G]):.0%} | {mean(firsts):.0f}s | {mean([g['ok'] for g in G]):.0%} | "
             f"{mean([g['cred'] for g in G]):.0%} | {mean([g['jdead'] for g in G]):.0%} |")
L += ["", "## Uccisioni di campioni (squadra che le fa)", "", "| | uccisioni/partita | con il jungler (killer/assist) | morti del jungler/partita |", "|---|---|---|---|"]
for who, d in D.items():
    L.append(f"| {who} | {d['tk']/n:.1f} | {d['jk']/max(1,d['tk']):.0%} | {len(d['jd'])/n:.1f} |")
why = {who: collections.Counter((g["why"] or "aperto") for g in D[who]["G"]) for who in D}
L += ["", "## Come finiscono i gank", "", "| | " + " | ".join(sorted({w for c in why.values() for w in c})) + " |", "|---|" + "---|" * len({w for c in why.values() for w in c})]
keys = sorted({w for c in why.values() for w in c})
for who in D:
    tot = sum(why[who].values()) or 1
    L.append(f"| {who} | " + " | ".join(f"{why[who][k]/tot:.0%}" for k in keys) + " |")
open(out + ".md", "w", encoding="utf8").write("\n".join(L))

# ---- immagine
pygame.init(); font = pygame.font.SysFont("consolas", 15)
S = 3; P = W * S
surf = pygame.Surface((P * 3 + 40, P * 2 + 90)); surf.fill((16, 18, 22))
def panel(ci, ri):
    x0 = 10 + ci * (P + 10); y0 = 40 + ri * (P + 40)
    pygame.draw.rect(surf, (28, 32, 38), (x0, y0, P, P)); return x0, y0
def txt(s, x, y, c=(230, 230, 230)): surf.blit(font.render(s, True, c), (x, y))
for ri, who in enumerate(("cand", "base")):
    d = D[who]
    # (0) origine -> bersaglio dei gank, verde riuscito / rosso no
    x0, y0 = panel(0, ri); txt(f"{who}: gank (jungler -> bersaglio), verde = riuscito", x0, y0 - 22)
    for g in d["G"]:
        a = norm(g["tm"], *g["jpos"]); b = norm(g["tm"], *g["tpos"])
        col = (90, 220, 120) if g["ok"] else (220, 90, 90)
        pygame.draw.line(surf, col, (x0 + a[0] * S, y0 + a[1] * S), (x0 + b[0] * S, y0 + b[1] * S), 1)
        pygame.draw.circle(surf, col, (x0 + int(b[0] * S), y0 + int(b[1] * S)), 3)
    # (1) mappa delle uccisioni (blu) e morti del jungler (rosso)
    x0, y0 = panel(1, ri); txt(f"{who}: uccisioni di campioni (blu) e morti del jungler (rosso)", x0, y0 - 22)
    for t, x, y in d["K"]:
        pygame.draw.circle(surf, (100, 170, 255), (x0 + int(x * S), y0 + int(y * S)), 3)
    for t, x, y in d["jd"]:
        pygame.draw.circle(surf, (255, 90, 90), (x0 + int(x * S), y0 + int(y * S)), 4, 1)
    # (2) istogramma: gank per minuto (barre) e uccisioni per minuto (linea)
    x0, y0 = panel(2, ri); txt(f"{who}: gank (barre) e uccisioni (linea) per minuto", x0, y0 - 22)
    gb = collections.Counter(int(g["t"] // 60) for g in d["G"]); kb = collections.Counter(int(k[0] // 60) for k in d["K"])
    top = max(list(gb.values()) + list(kb.values()) + [1]) / n * 1.15
    bw = P // 15
    for m in range(15):
        h = int(gb[m] / n / top * P)
        pygame.draw.rect(surf, (230, 160, 70), (x0 + m * bw + 2, y0 + P - h, bw - 4, h))
        txt(str(m), x0 + m * bw + 4, y0 + P + 2, (160, 170, 180))
    pts = [(x0 + m * bw + bw // 2, y0 + P - int(kb[m] / n / top * P)) for m in range(15)]
    pygame.draw.lines(surf, (100, 170, 255), False, pts, 2)
pygame.image.save(surf, out + ".png")
print("\n".join(L))
