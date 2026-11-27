import json, sys, os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import numpy as np, pygame
pygame.init()
res = json.load(open(sys.argv[1])); out = sys.argv[2]
W = 150; S = 4; P = W * S
font = pygame.font.SysFont("consolas", 16)
surf = pygame.Surface((P * 3 + 40, P * 2 + 80)); surf.fill((16, 18, 22))
def heat(v):
    v = np.clip(v, 0, 1); r = np.clip(v * 3, 0, 1); g = np.clip(v * 3 - 1, 0, 1); b = np.clip(v * 3 - 2, 0, 1)
    return (np.stack([r, g, b], -1) * 255).astype(np.uint8)
for ci, role in enumerate(("cand", "base")):
    H = np.zeros((W, W)); camps = []
    for r in res:
        tm = r["side"] if role == "cand" else 1 - r["side"]
        for t, x, y, alive, lv in r["log"]["pos"][str(tm)]:
            if alive:
                if tm == 1: x, y = W - x, W - y
                H[min(int(y), W - 1), min(int(x), W - 1)] += 1
        for c in r["log"]["camps"]:
            if c[4].get(str(tm), 999) < 8:
                x, y = (c[2], c[3]) if tm == 0 else (W - c[2], W - c[3])
                camps.append((c[0] / 60, x, y))
    oy = 40 + ci * (P + 20)
    # heatmap (log, sfocata a blocchi 3x3)
    k = np.ones(3) / 3
    Hb = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 0, H)
    Hb = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 1, Hb)
    img = heat(np.log1p(Hb) / np.log1p(Hb.max()))
    s1 = pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))
    surf.blit(pygame.transform.scale(s1, (P, P)), (10, oy))
    # campi
    pygame.draw.rect(surf, (28, 32, 38), (P + 20, oy, P, P))
    for m, x, y in camps:
        f = min(m / 14, 1); col = (int(255 * f), int(220 - 120 * f), int(255 * (1 - f)))
        pygame.draw.circle(surf, col, (P + 20 + int(x * S), oy + int(y * S)), 4)
    # curva campi cumulati
    cx = 2 * P + 30
    pygame.draw.rect(surf, (28, 32, 38), (cx, oy, P, P))
    ts = sorted(c[0] for c in camps); n = len(res)
    pts = [(cx + int(t / 14 * P), oy + P - int((i + 1) / n / 24 * P)) for i, t in enumerate(ts)]
    if len(pts) > 1: pygame.draw.lines(surf, (120, 220, 255), False, pts, 2)
    for g in range(0, 25, 4):
        yy = oy + P - int(g / 24 * P); pygame.draw.line(surf, (60, 66, 76), (cx, yy), (cx + P, yy))
        surf.blit(font.render(str(g), True, (160, 170, 180)), (cx + 4, yy - 16))
    for mn in range(0, 15, 2):
        xx = cx + int(mn / 14 * P); surf.blit(font.render(f"{mn}m", True, (160, 170, 180)), (xx, oy + P + 2))
    for j, txt in enumerate((f"{role}: posizioni del jungler (log, lato blu)", f"{role}: campi uccisi (rosso = tardi)",
                             f"{role}: campi cumulati/partita ({len(ts)/n:.1f} totali)")):
        surf.blit(font.render(txt, True, (230, 230, 230)), (10 + j * (P + 10), oy - 22))
pygame.image.save(surf, out)
