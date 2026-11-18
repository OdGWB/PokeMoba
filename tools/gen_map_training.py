"""Generatore della mappa di ALLENAMENTO / TUTORIAL (piccola, 48x32).

Produce data/maps/map_training.json: una sola lane orizzontale corta tra le due
basi (una torre per squadra), una radura a nord con i MANICHINI, una giungla a sud
con due campi (piccolo e grande), un laghetto e qualche cespuglio. Serve solo per
la modalita' Allenamento e per il Tutorial (game/scenes/training_scene.py).

Le "tane" (dens) dei leggendari stanno dentro il muro d'angolo: nell'allenamento
i leggendari sono spenti (engine/training.py), ma Jungle sigilla comunque un anello
attorno alla tana alta, quindi deve finire su tile gia' muro.

Uso:  python tools/gen_map_training.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "maps" / "map_training.json"

W, H = 48, 32
FLOOR, WALL, LANE, RIVER, BUSH, JWALL = 0, 1, 2, 3, 4, 5

BASE0 = (6, 16)
BASE1 = (41, 16)
LANE_PTS = [BASE0, (24, 16), BASE1]
TOWERS = {0: (15, 16), 1: (32, 16)}
CAMPS = [{"pos": [13, 26], "type": "small"}, {"pos": [31, 26], "type": "big"}]
# Posizioni dei manichini (radura a nord), lette anche da engine/training.py.
DUMMIES = [[16, 6], [21, 5], [26, 7]]
DENS = {"low": [1, 1], "high": [1, 30]}


def disk(t, cx, cy, r, v, only=None):
    for y in range(max(0, int(cy - r - 1)), min(H, int(cy + r + 2))):
        for x in range(max(0, int(cx - r - 1)), min(W, int(cx + r + 2))):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                if only is None or t[y][x] in only:
                    t[y][x] = v


def line(t, a, b, r, v, only=None):
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, int(d * 2))
    for i in range(n + 1):
        s = i / n
        disk(t, a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, r, v, only)


def alcove(t, cx, cy, open_ang, r=3.6):
    """Muro di giungla a C attorno a un campo, aperto verso `open_ang` (gradi)."""
    for a in range(0, 360, 10):
        da = abs(((a - open_ang + 180) % 360) - 180)
        if da < 55:
            continue
        rad = math.radians(a)
        disk(t, cx + math.cos(rad) * r, cy + math.sin(rad) * r, 0.9, JWALL, only=(FLOOR,))


def build():
    t = [[FLOOR] * W for _ in range(H)]

    # Muri di giungla fra la lane e le due zone (radura nord, giungla sud), con varchi.
    for x in range(10, 38):
        if x in (19, 20, 21, 22, 23):            # varco verso la radura dei manichini
            continue
        for y in (11, 12):
            t[y][x] = JWALL
    for x in range(10, 38):
        if x in (11, 12, 13, 22, 23, 24, 25, 34, 35):   # tre ingressi alla giungla
            continue
        for y in (20, 21):
            t[y][x] = JWALL

    # Giungla sud: due alcove-campo, un laghetto, una dorsale e cespugli.
    alcove(t, 13, 26, -60)
    alcove(t, 31, 26, -120)
    disk(t, 22.5, 26.5, 2.6, RIVER)
    line(t, (19, 29), (26, 29), 0.8, JWALL, only=(FLOOR,))
    for (bx, by, r) in [(17, 23, 1.4), (27, 23, 1.4), (8, 25, 1.6), (39, 25, 1.6)]:
        disk(t, bx, by, r, BUSH, only=(FLOOR,))

    # Radura nord: qualche masso e cespugli ai lati (i manichini stanno al centro).
    for (bx, by, r) in [(11, 5, 1.6), (31, 5, 1.6)]:
        disk(t, bx, by, r, BUSH, only=(FLOOR,))
    for (bx, by) in [(35, 7), (8, 8)]:
        disk(t, bx, by, 1.5, JWALL, only=(FLOOR,))

    # Lane (sopra i muri: apre il passaggio) + spiazzi di basi e torri.
    for a, b in zip(LANE_PTS, LANE_PTS[1:]):
        line(t, a, b, 2.2, LANE)
    for bx, by in (BASE0, BASE1):
        disk(t, bx, by, 4.2, LANE)
    for tx, ty in TOWERS.values():
        disk(t, tx, ty, 2.6, LANE)

    # Bordo spesso e angoli arrotondati (le tane finiscono dentro il muro).
    for y in range(H):
        for x in range(W):
            edge = min(x, y, W - 1 - x, H - 1 - y)
            cx = min(x, W - 1 - x)
            cy = min(y, H - 1 - y)
            if edge < 2 or (cx < 6 and cy < 6 and math.hypot(6 - cx, 6 - cy) > 5.2):
                t[y][x] = WALL

    for c in CAMPS + [{"pos": p} for p in DUMMIES]:
        x, y = c["pos"]
        assert t[y][x] in (FLOOR, BUSH), ("posizione murata", c)

    structures = []
    for team, base in ((0, BASE0), (1, BASE1)):
        structures.append({"type": "core", "team": team, "pos": [base[0], base[1]]})
        tx, ty = TOWERS[team]
        structures.append({"type": "tower", "team": team, "lane": "mid", "tier": 1,
                           "name": "outer", "pos": [tx + 0.5, ty + 0.5]})

    data = {
        "name": "Campo d'allenamento",
        "width": W, "height": H, "tiles": t, "puddles": [],
        "teams": {"0": {"base": list(BASE0)}, "1": {"base": list(BASE1)}},
        "lanes": {"mid": [list(p) for p in LANE_PTS]},
        "structures": structures, "dens": DENS, "camps": CAMPS,
        "spawns": {"team0": list(BASE0), "team1": list(BASE1)},
        "dummies": DUMMIES, "team_size": 1,
    }
    OUT.write_text(json.dumps(data), encoding="utf-8")
    print(f"Scritta {OUT}  ({W}x{H}, {len(structures)} strutture, {len(CAMPS)} campi)")


if __name__ == "__main__":
    build()
