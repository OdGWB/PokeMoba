"""Genera i punti delle giungle evolute a partire dalla base disegnata.

- puddle_spots: 2 pozze GRANDI per quadrante (dischi), solo su erba.
- wind_passages: 2-3 varchi per quadrante (dischi che aprono i muri di giungla),
  agganciati ai muri esistenti così aprono davvero un passaggio.

Simmetrico a 180°. Scrive i campi `puddle_spots` e `wind_passages` nel JSON.

    python tools/gen_weather_spots.py                     # 3v3
    python tools/gen_weather_spots.py data/maps/map_5v5.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR, JWALL = 0, 5

# Candidati nella metà x>y (team1); l'altra metà è lo specchio a 180°.
# (cx, cy) in frazione del lato, così vale per 3v3 e 5v5.
PUDDLE_F = [  # 2 per quadrante
    (0.44, 0.28), (0.34, 0.20),      # quadrante alto
    (0.70, 0.52), (0.80, 0.66),      # quadrante destro
]
WIND_F = [    # 2-3 per quadrante
    (0.50, 0.26), (0.40, 0.32), (0.56, 0.38),   # quadrante alto
    (0.62, 0.44), (0.72, 0.54), (0.82, 0.62),   # quadrante destro
]
PUDDLE_R = 5
WIND_R = 3


def nearest(tiles, N, cx, cy, want, rad):
    best, bd = None, (rad + 1) ** 2
    for y in range(max(0, cy - rad), min(N, cy + rad + 1)):
        for x in range(max(0, cx - rad), min(N, cx + rad + 1)):
            if tiles[y][x] == want:
                d = (x - cx) ** 2 + (y - cy) ** 2
                if d < bd:
                    best, bd = (x, y), d
    return best


def build(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    N = int(data["width"])
    tiles = data["tiles"]

    def mir(x, y):
        return (min(N - 1, max(0, N - x)), min(N - 1, max(0, N - y)))

    puddles, winds = [], []
    for (fx, fy) in PUDDLE_F:
        cx, cy = int(fx * N), int(fy * N)
        p = nearest(tiles, N, cx, cy, FLOOR, 6) or (cx, cy)
        for (x, y) in (p, mir(*p)):
            puddles.append({"pos": [x, y], "r": PUDDLE_R})
    for (fx, fy) in WIND_F:
        cx, cy = int(fx * N), int(fy * N)
        w = nearest(tiles, N, cx, cy, JWALL, 8) or (cx, cy)
        for (x, y) in (w, mir(*w)):
            winds.append({"pos": [x, y], "r": WIND_R})

    data["puddle_spots"] = puddles
    data["wind_passages"] = winds
    path.write_text(json.dumps(data), encoding="utf-8")
    print(f"{path.name}: {len(puddles)} pozze grandi, {len(winds)} varchi vento")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "data/maps/map_3v3.json"
    p = Path(arg)
    if not p.is_absolute():
        p = ROOT / arg
    build(p)
