"""Cosa sposta il vantaggio a T minuti e quanto predice l'esito?
    python tools/early_drivers.py reports/prefix T_sec trace1.json [trace2.json ...]
Per ogni partita (vista del candidato) a T: differenza candidato-avversario di networth, livello, cs, campi,
kill, torri, danno ai campioni, primo sangue; networth per ruolo e per personaggio.
Misura: AUC di ogni feature da sola sull'esito, regressione logistica multipla (coefficienti standardizzati),
e scomposizione del vantaggio di networth nelle componenti (OLS)."""
import json, os, sys
from collections import defaultdict
os.environ["SDL_VIDEODRIVER"] = "dummy"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]
import numpy as np
import config
from engine.content import load_pokemon_def
import tier_sim
import phi_fit

pref, T = sys.argv[1], float(sys.argv[2])
res = []
for p in sys.argv[3:]: res += json.load(open(p))
defs = {d.name: d for d in (load_pokemon_def(os.path.join(ROOT, rel)) for rel in config.ROSTER)}
ROLES = ["jungler", "support", "tiratore", "mago", "combattente", "assassino", "tank"]


def grp(name, jg):
    if jg: return "jungler"
    d = defs.get(name)
    if d is None: return "?"
    if d.role == "supporto" or name in tier_sim.SUPPORTS: return "support"
    return "mago" if d.role == "mago mobile" else d.role


COMP = ["cs", "camp", "kill", "torri", "danno", "lvl"]
rows, labels, chars = [], [], []
for r in res:
    L = r["log"]; side = r["side"]; o = 1 - side
    ids = {int(k): v for k, v in L["all"].items()}
    jg = {(u["team"], u["name"]) for u in r["all"] if u["smites"] is not None}
    st = {int(k): {row[0]: row for row in v} for k, v in L["st"].items()}
    ts = min({row[0] for v in st.values() for row in v.values()}, key=lambda t: abs(t - T))
    w = {side: 0.0, o: 0.0}; lv = {side: 0.0, o: 0.0}; byrole = {side: defaultdict(float), o: defaultdict(float)}
    unit = []
    for pid, d in ids.items():
        row = st[pid].get(ts)
        if row is None: continue
        g = grp(d["name"], (d["team"], d["name"]) in jg)
        w[d["team"]] += row[3]; lv[d["team"]] += row[2]; byrole[d["team"]][g] += row[3]
        unit.append((d["team"], d["name"], g, row[3]))
    cnt = {side: dict.fromkeys(COMP, 0.0), o: dict.fromkeys(COMP, 0.0)}
    for t, kind, kid, x, y in L["farm"]:
        if t > ts: continue
        tm = ids.get(int(kid), {}).get("team")
        if tm is None: continue
        if kind == "cs": cnt[tm]["cs"] += 1
        elif kind in ("camp", "legend"): cnt[tm]["camp"] += 1
        elif kind == "tower": cnt[tm]["torri"] += 1
    fb = 0
    for k in sorted(L["kills"]):
        if k[0] > ts: break
        if int(k[3]) in ids and k[6] in cnt:
            cnt[k[6]]["kill"] += 1
            if fb == 0: fb = 1 if k[6] == side else -1
    for t, att, vic, lost, kind in L["dmg"]:
        if t <= ts and kind == "P" and int(att) in ids if att is not None else False:
            cnt[ids[int(att)]["team"]]["danno"] += lost
    for tm in (side, o): cnt[tm]["lvl"] = lv[tm]
    f = {"networth": (w[side] - w[o]) / 1000.0, "livello": lv[side] - lv[o], "cs": cnt[side]["cs"] - cnt[o]["cs"],
         "campi": cnt[side]["camp"] - cnt[o]["camp"], "kill": cnt[side]["kill"] - cnt[o]["kill"],
         "torri": cnt[side]["torri"] - cnt[o]["torri"], "danno ai campioni": (cnt[side]["danno"] - cnt[o]["danno"]) / 1000.0,
         "primo sangue": fb}
    for g in ROLES: f["worth " + g] = (byrole[side][g] - byrole[o][g]) / 1000.0
    rows.append(f); labels.append(1.0 if r["winner"] == side else 0.0)
    tm_mean = {tm: np.mean([u[3] for u in unit if u[0] == tm]) for tm in (0, 1)}
    for tm, name, g, wv in unit:
        chars.append((name, g, wv - tm_mean[tm], (wv - tm_mean[tm]) * (1 if tm == side else -1), labels[-1], tm == side))

names = list(rows[0]); X = np.array([[f[n] for n in names] for f in rows]); y = np.array(labels)
auc = {n: phi_fit.auc(X[:, i], y) for i, n in enumerate(names)}
# logistica multipla standardizzata (vista specchio, senza intercetta)
sd = X.std(0) + 1e-9; Z = X / sd
Zs = np.vstack([Z, -Z]); ys = np.concatenate([y, 1 - y])
main_cols = [names.index(n) for n in ("livello", "cs", "campi", "kill", "torri", "danno ai campioni", "primo sangue")]
w_main = phi_fit.fit(Zs[:, main_cols], ys, lam=5.0)
w_role = phi_fit.fit(Zs[:, [names.index("worth " + g) for g in ROLES]], ys, lam=5.0)
# scomposizione networth: OLS su componenti
comp_names = ["livello", "cs", "campi", "kill", "torri", "danno ai campioni"]
C = X[:, [names.index(n) for n in comp_names]]; nwd = X[:, names.index("networth")]
Cz = (C - C.mean(0)) / (C.std(0) + 1e-9); b, *_ = np.linalg.lstsq(np.c_[Cz, np.ones(len(Cz))], nwd, rcond=None)
pred = np.c_[Cz, np.ones(len(Cz))] @ b; r2 = 1 - ((nwd - pred) ** 2).sum() / ((nwd - nwd.mean()) ** 2).sum()
L = [f"# Cosa muove il vantaggio a {T / 60:.0f} minuti", "",
     f"{len(res)} partite bilanciate (vista del candidato), istante {T:.0f} s. AUC = quanto la feature, da sola, predice la vittoria finale.", "",
     "## Singole feature", "", "| feature | AUC | media se vince | media se perde |", "|---|---|---|---|"]
for n in sorted(names, key=lambda n: -auc[n]):
    i = names.index(n); L.append(f"| {n} | {auc[n]:.3f} | {X[y == 1, i].mean():+.2f} | {X[y == 0, i].mean():+.2f} |")
L += ["", "## Regressione logistica multipla (coefficienti su feature standardizzate)", "", "| feature | peso |", "|---|---|"]
for c, wv in sorted(zip(main_cols, w_main[:-1]), key=lambda t: -abs(t[1])): L.append(f"| {names[c]} | {wv:+.2f} |")
L += ["", "Per ruolo (networth del ruolo a T):", "", "| ruolo | peso |", "|---|---|"]
for g, wv in sorted(zip(ROLES, w_role[:-1]), key=lambda t: -abs(t[1])): L.append(f"| {g} | {wv:+.2f} |")
L += ["", f"## Da cosa dipende il vantaggio di networth a {T / 60:.0f}' (OLS, R2 = {r2:.2f})", "", "| componente | contributo standardizzato |", "|---|---|"]
for n, bv in sorted(zip(comp_names, b[:-1]), key=lambda t: -abs(t[1])): L.append(f"| {n} | {bv:+.2f} |")
# per personaggio: networth relativo alla media di squadra a T, vista del candidato
by = defaultdict(list)
for name, g, rel, relc, win, mine in chars:
    by[name].append((rel, win, mine))
L += ["", "## Per personaggio: quanto conta essere davanti alla propria squadra", "",
      "Per ogni personaggio, networth a T meno la media della squadra; AUC = quanto quel margine predice la vittoria della sua squadra "
      "(n = apparizioni).", "", "| personaggio | ruolo | n | margine medio | AUC |", "|---|---|---|---|---|"]
out = []
for name, v in by.items():
    if len(v) < 25: continue
    rel = np.array([a for a, _, _ in v]); won = np.array([(wn if mine else 1 - wn) for _, wn, mine in v])
    out.append((phi_fit.auc(rel, won), name, len(v), rel.mean()))
role_of = {c[0]: c[1] for c in chars}
for a, name, n, m in sorted(out, reverse=True): L.append(f"| {name} | {role_of[name]} | {n} | {m:+.0f} | {a:.2f} |")
open(pref + ".md", "w", encoding="utf-8").write("\n".join(L) + "\n")

# grafico: barre AUC per feature
import pygame; pygame.init()
fnt = pygame.font.SysFont("consolas", 13)
items = sorted(((n, auc[n]) for n in names), key=lambda t: -t[1])
Wd, Hd = 640, 60 + 22 * len(items); S = pygame.Surface((Wd, Hd)); S.fill((16, 18, 22))
S.blit(fnt.render(f"AUC sulla vittoria a {T / 60:.0f}' (0.5 = nessuna informazione)", True, (225, 228, 232)), (10, 8))
for i, (n, a) in enumerate(items):
    yy = 36 + 22 * i; S.blit(fnt.render(n, True, (200, 205, 215)), (10, yy))
    pygame.draw.rect(S, (60, 64, 74), (200, yy + 2, 380, 14))
    pygame.draw.rect(S, (90, 190, 250) if "worth" not in n else (230, 150, 80), (200, yy + 2, int(380 * max(0, a - 0.5) / 0.5), 14))
    S.blit(fnt.render(f"{a:.2f}", True, (225, 228, 232)), (586, yy))
pygame.image.save(S, pref + ".png"); print("\n".join(L))
