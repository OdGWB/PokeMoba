"""Heatmap delle posizioni PER RUOLO (righe: candidato, base) dal json di jungle_trace.
    python tools/jungle_roles_plot.py tools/cma_out/jt_g25_mean.json reports/ai_g25_mean_roles.png
Lato blu normalizzato (squadra 1 ribaltata). Ruolo da roster; jungler = chi ha lo Smite; support = ruolo supporto."""
import json, sys, os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import numpy as np, pygame
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]
import config
from engine.content import load_pokemon_def
import tier_sim
pygame.init()
res = json.load(open(sys.argv[1])); out = sys.argv[2]
defs = {d.name: d for d in (load_pokemon_def(os.path.join(ROOT, rel)) for rel in config.ROSTER)}
def grp(name, is_jg):
    if is_jg: return "jungler"
    d = defs.get(name)
    if d is None: return "?"
    if d.role == "supporto" or name in tier_sim.SUPPORTS: return "support"
    return "mago" if d.role == "mago mobile" else d.role
ROLES = ["jungler", "support", "tiratore", "mago", "combattente", "assassino", "tank"]
W = 150; S = 2; P = W * S
font = pygame.font.SysFont("consolas", 15)
surf = pygame.Surface((len(ROLES) * (P + 8) + 8, 2 * (P + 36) + 8)); surf.fill((16, 18, 22))
def heat(v):
    v = np.clip(v, 0, 1); r = np.clip(v * 3, 0, 1); g = np.clip(v * 3 - 1, 0, 1); b = np.clip(v * 3 - 2, 0, 1)
    return (np.stack([r, g, b], -1) * 255).astype(np.uint8)
k = np.ones(3) / 3
for ri, who in enumerate(("cand", "base")):
    Hs = {g: np.zeros((W, W)) for g in ROLES}; cnt = dict.fromkeys(ROLES, 0)
    for r in res:
        tm = r["side"] if who == "cand" else 1 - r["side"]
        jg = {u["name"] for u in r["all"] if u["team"] == tm and u["smites"] is not None}
        for d in r["log"]["all"].values():
            if d["team"] != tm: continue
            g = grp(d["name"], d["name"] in jg)
            if g not in Hs: continue
            cnt[g] += 1
            for t, x, y, alive in d["p"]:
                if alive:
                    if tm == 1: x, y = W - x, W - y
                    Hs[g][min(int(y), W - 1), min(int(x), W - 1)] += 1
    for ci, g in enumerate(ROLES):
        H = Hs[g]
        Hb = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 0, H)
        Hb = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 1, Hb)
        img = heat(np.log1p(Hb) / max(1e-9, np.log1p(Hb.max())))
        s1 = pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))
        x0 = 8 + ci * (P + 8); y0 = 8 + ri * (P + 36) + 22
        surf.blit(font.render(f"{who} · {g} (n={cnt[g]})", True, (230, 230, 230)), (x0, y0 - 20))
        surf.blit(pygame.transform.scale(s1, (P, P)), (x0, y0))
pygame.image.save(surf, out)
print("ok", {g: cnt[g] for g in ROLES})
