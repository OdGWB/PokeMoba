"""Heatmap DELTA tra due insiemi di partite (due gen, o base vs candidato).
    python tools/suite_delta.py A B out_prefix [titolo]
A e B = file.json[:cand|:base]  (default :cand). Esempio base vs gen25:
    python tools/suite_delta.py tools/cma_out/st_g25_mean.json:base tools/cma_out/st_g25_mean.json:cand reports/delta_base_g25 "base -> gen25"
Delta = densita' normalizzata B meno A (ogni mappa somma a 1, quindi conta DOVE, non quanto tempo vivo):
rosso = B ci sta di piu', blu = A ci sta di piu'. Righe: fase (early/mid/late); colonne: ruolo.
Produce _roles.png (ruolo x fase), _chars.png (per personaggio, tutta la partita) e _all.png (tutti insieme)."""
import json, math, os, sys
from collections import defaultdict
os.environ["SDL_VIDEODRIVER"] = "dummy"
import numpy as np, pygame
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]
import config
from engine.content import load_pokemon_def
import tier_sim
pygame.init()

def load(spec):
    f, _, who = spec.partition(":")
    return json.load(open(f)), (who or "cand")
(A, wa), (B, wb) = load(sys.argv[1]), load(sys.argv[2]); pref = sys.argv[3]
title = sys.argv[4] if len(sys.argv) > 4 else "delta"
os.makedirs(os.path.dirname(pref) or ".", exist_ok=True)
ROLES = ["jungler", "support", "tiratore", "mago", "combattente", "assassino", "tank"]
PH = ["early 0-5'", "mid 5-10'", "late 10'+"]
defs = {d.name: d for d in (load_pokemon_def(os.path.join(ROOT, rel)) for rel in config.ROSTER)}
def grp(name, jg):
    if jg: return "jungler"
    d = defs.get(name)
    if d is None: return "?"
    if d.role == "supporto" or name in tier_sim.SUPPORTS: return "support"
    return "mago" if d.role == "mago mobile" else d.role
NB = 75
def units(res, who):
    out = []
    for r in res:
        cs = {int(k): v for k, v in r["log"]["meta"]["cores"].items()}; W = cs[0][0] + cs[1][0]
        jg = {(u["team"], u["name"]) for u in r["all"] if u["smites"] is not None}
        for k, d in r["log"]["all"].items():
            if (d["team"] == r["side"]) != (who == "cand"): continue
            out.append(dict(name=d["name"], grp=grp(d["name"], (d["team"], d["name"]) in jg), team=d["team"], p=d["p"], W=W))
    return out
UA, UB = units(A, wa), units(B, wb)
def grid(us, ph=None):
    H = np.zeros((NB, NB))
    for u in us:
        for t, x, y, alive in u["p"]:
            if not alive: continue
            if ph is not None and (0 if t < 300 else 1 if t < 600 else 2) != ph: continue
            if u["team"] == 1: x, y = u["W"] - x, u["W"] - y
            H[min(NB - 1, max(0, int(y / u["W"] * NB))), min(NB - 1, max(0, int(x / u["W"] * NB)))] += 1
    return H
def smooth(H):
    k = np.array([1, 2, 1]) / 4.0
    H = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 0, H)
    return np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 1, H)
def delta(ua, ub, ph=None):
    ha, hb = smooth(grid(ua, ph)), smooth(grid(ub, ph))
    if ha.sum() == 0 or hb.sum() == 0: return None
    return hb / hb.sum() - ha / ha.sum()
def tile(D, px, vmax):
    if D is None:
        s = pygame.Surface((px, px)); s.fill((30, 30, 34)); return s
    v = np.clip(np.sign(D) * np.sqrt(np.abs(D) / vmax), -1, 1)
    img = np.zeros((NB, NB, 3)); pos = np.clip(v, 0, 1); neg = np.clip(-v, 0, 1)
    img[..., 0] = 255 * pos + 40 * (1 - pos - neg); img[..., 2] = 255 * neg + 40 * (1 - pos - neg)
    img[..., 1] = 40 * (1 - pos - neg) + 70 * np.minimum(pos, neg)
    img = np.clip(img * (0.25 + 0.75 * np.maximum(pos, neg))[..., None] + 14, 0, 255).astype(np.uint8)
    sf = pygame.transform.scale(pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2))), (px, px))
    for bx, by, c in ((0.12, 0.88, (80, 160, 255)), (0.88, 0.12, (255, 90, 90))):
        pygame.draw.circle(sf, c, (int(bx * px), int(by * px)), 5, 2)
    pygame.draw.line(sf, (60, 60, 70), (0, px - 1), (px - 1, 0))
    return sf
font = lambda s: pygame.font.SysFont("consolas", s)
f11, f13, f16 = font(11), font(13), font(16)
head = f"{title}: ROSSO = piu' presenza in B ({sys.argv[2].split(os.sep)[-1]}), BLU = piu' presenza in A ({sys.argv[1].split(os.sep)[-1]})"

# ruolo x fase
tl = 220; cells = {}
for pi in range(3):
    for g in ROLES:
        cells[(pi, g)] = delta([u for u in UA if u["grp"] == g], [u for u in UB if u["grp"] == g], pi)
vmax = np.percentile(np.concatenate([np.abs(D).ravel() for D in cells.values() if D is not None]), 99.3)
S = pygame.Surface((len(ROLES) * (tl + 6) + 6, 3 * (tl + 24) + 34)); S.fill((16, 18, 22))
S.blit(f13.render(head, True, (225, 228, 232)), (6, 6))
for pi in range(3):
    for gi, g in enumerate(ROLES):
        x0 = 6 + gi * (tl + 6); y0 = 34 + pi * (tl + 24) + 18
        S.blit(f11.render(f"{g} {PH[pi]}", True, (225, 228, 232)), (x0, y0 - 15)); S.blit(tile(cells[(pi, g)], tl, vmax), (x0, y0))
pygame.image.save(S, pref + "_roles.png")

# per personaggio (tutta la partita)
names = sorted({u["name"] for u in UA + UB}, key=lambda n: -sum(u["name"] == n for u in UA + UB))
cd = {n: delta([u for u in UA if u["name"] == n], [u for u in UB if u["name"] == n]) for n in names}
cvmax = np.percentile(np.concatenate([np.abs(D).ravel() for D in cd.values() if D is not None]), 99.3)
cols = 6; tl = 190; rows = math.ceil(len(names) / cols)
S = pygame.Surface((cols * (tl + 6) + 6, rows * (tl + 22) + 34)); S.fill((16, 18, 22))
S.blit(f13.render(head + " (per personaggio)", True, (225, 228, 232)), (6, 6))
for i, n in enumerate(names):
    x0 = 6 + (i % cols) * (tl + 6); y0 = 34 + (i // cols) * (tl + 22) + 16
    na, nb = sum(u["name"] == n for u in UA), sum(u["name"] == n for u in UB)
    S.blit(f11.render(f"{n} A={na} B={nb}", True, (225, 228, 232)), (x0, y0 - 15)); S.blit(tile(cd[n], tl, cvmax), (x0, y0))
pygame.image.save(S, pref + "_chars.png")

# complessivo
D = delta(UA, UB); tl = 520
S = pygame.Surface((tl + 12, tl + 36)); S.fill((16, 18, 22))
S.blit(f13.render("tutti i ruoli, tutta la partita", True, (225, 228, 232)), (6, 8))
S.blit(tile(D, tl, np.percentile(np.abs(D), 99.3)), (6, 30)); pygame.image.save(S, pref + "_all.png")
print("ok", len(UA), len(UB))
