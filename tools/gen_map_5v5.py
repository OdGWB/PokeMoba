"""Generatore della mappa 5v5 (giungla stile LoL), 150x150.

Stessa logica della 3v3 (fiume con sponde murate e pozzi, alcove-campo con i
Pokémon minori, boschetti, corridoi) ma più grande: 3 torri per lane, 5 giocatori
per squadra e più campi di giungla. Simmetrica a 180°.

    python tools/gen_map_5v5.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "maps" / "map_5v5.json"

N = 150
FLOOR, WALL, LANE, RIVER, BUSH, JWALL, PUDDLE = 0, 1, 2, 3, 4, 5, 6

BASE0 = (18, 132)
BASE1 = (132, 18)
LANES = {
    "mid": [BASE0, (75, 75), BASE1],
    "top": [BASE0, (18, 18), BASE1],
    "bot": [BASE0, (132, 132), BASE1],
}
TOWER_FRACTIONS = {
    0: [("t3", 0.20, 3), ("t2", 0.33, 2), ("t1", 0.46, 1)],
    1: [("t3", 0.80, 3), ("t2", 0.67, 2), ("t1", 0.54, 1)],
}
DENS = {"low": [93, 93], "high": [56, 56]}

# Campi minori: definiti nella metà x>y (giungla squadra 1), due quadranti ai lati
# della mid, sparsi dal fiume alle lane/base. L'altra metà è il simmetrico a 180°.
CAMPS_HALF = [
    # quadrante "alto" (tra top-lane e mid): 2 campi + buff
    (70, 46, "small"), (88, 48, "big"), (110, 30, "small"),
    # quadrante "destro" (tra mid e bot-lane): 2 campi + buff
    (96, 70, "small"), (112, 86, "big"), (120, 60, "small"),
]


def mirror(x, y):
    return (N - x, N - y)


def point_at_fraction(poly, f):
    segs, total = [], 0.0
    for a, b in zip(poly, poly[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1]); segs.append((a, b, d)); total += d
    target = max(0.0, min(1.0, f)) * total
    acc = 0.0
    for a, b, d in segs:
        if acc + d >= target:
            t = (target - acc) / d if d > 0 else 0.0
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        acc += d
    return poly[-1]


def stamp_disk(tiles, cx, cy, r, value, only_floor=False):
    r2 = r * r
    for y in range(max(0, int(cy - r)), min(N, int(cy + r) + 1)):
        for x in range(max(0, int(cx - r)), min(N, int(cx + r) + 1)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                if only_floor and tiles[y][x] != FLOOR:
                    continue
                tiles[y][x] = value


def stamp_polyline(tiles, poly, r, value):
    for a, b in zip(poly, poly[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(d * 2))
        for i in range(steps + 1):
            t = i / steps
            stamp_disk(tiles, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, r, value)


def near_any(x, y, pts, d):
    return any((x - px) ** 2 + (y - py) ** 2 <= d * d for px, py in pts)


def flood(tiles, start):
    from collections import deque
    blocked = {WALL, JWALL}
    seen = {start}; dq = deque([start])
    while dq:
        x, y = dq.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < N and 0 <= ny < N and (nx, ny) not in seen \
                    and tiles[ny][nx] not in blocked:
                seen.add((nx, ny)); dq.append((nx, ny))
    return seen


def ensure_reachable(tiles, camps, src):
    seen = flood(tiles, src)
    c50 = N // 2
    for c in camps:
        x, y = c["pos"]
        if (x, y) in seen:
            continue
        cx, cy = x, y; steps = 0
        while (cx, cy) not in seen and steps < 220:
            for ox in (0, 1):
                for oy in (0, 1):
                    tx, ty = cx + ox, cy + oy
                    if 0 <= tx < N and 0 <= ty < N and tiles[ty][tx] in (WALL, JWALL):
                        tiles[ty][tx] = FLOOR
            if cx != c50:
                cx += 1 if cx < c50 else -1
            elif cy != c50:
                cy += 1 if cy < c50 else -1
            steps += 1
        seen = flood(tiles, src)


def alcove(tiles, cx, cy, bushes):
    cx, cy = int(cx), int(cy)
    ang = math.atan2(N // 2 - cy, N // 2 - cx)
    r = 5
    for a in range(0, 360, 10):
        rad = math.radians(a)
        da = abs(((math.degrees(rad) - math.degrees(ang) + 180) % 360) - 180)
        if da < 50:
            continue
        wx = cx + int(round(math.cos(rad) * r))
        wy = cy + int(round(math.sin(rad) * r))
        if 0 <= wx < N and 0 <= wy < N and tiles[wy][wx] == FLOOR:
            tiles[wy][wx] = JWALL
            for ox, oy in ((1, 0), (0, 1)):
                nx, ny = wx + ox, wy + oy
                if 0 <= nx < N and 0 <= ny < N and tiles[ny][nx] == FLOOR \
                        and (nx - cx) ** 2 + (ny - cy) ** 2 > (r - 1) ** 2:
                    tiles[ny][nx] = JWALL
    bx = cx + int(round(math.cos(ang) * (r + 2)))
    by = cy + int(round(math.sin(ang) * (r + 2)))
    bushes.append((bx, by))


def point_seg_dist(px, py, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


def lane_dist(px, py):
    return min(point_seg_dist(px, py, a, b)
               for poly in LANES.values() for a, b in zip(poly, poly[1:]))


def lane_walls(tiles, gaps):
    """Muro di giungla lungo le lane (banda 4.5..7.0), con pochi varchi: lane
    confinate e ingressi limitati alla giungla."""
    for y in range(N):
        for x in range(N):
            if tiles[y][x] != FLOOR:
                continue
            d = lane_dist(x, y)
            if 4.5 <= d <= 7.0 and not near_any(x, y, gaps, 5):
                tiles[y][x] = JWALL


def river_bank_walls(tiles, dens):
    gaps = [(N // 2, N // 2)] + [tuple(d) for d in dens.values()]
    for y in range(N):
        for x in range(N):
            if tiles[y][x] != FLOOR:
                continue
            if abs(x - y) in (7, 8):
                if near_any(x, y, gaps, 12):
                    continue
                if x < 26 or y < 26 or x > 124 or y > 124:
                    continue
                tiles[y][x] = JWALL


def build():
    tiles = [[FLOOR] * N for _ in range(N)]
    for y in range(N):
        for x in range(N):
            if abs(y - x) <= 4:
                tiles[y][x] = RIVER
    river_bank_walls(tiles, DENS)

    bush_pts, camps = [], []
    for (hx, hy, kind) in CAMPS_HALF:
        for (cx, cy) in ((hx, hy), mirror(hx, hy)):
            alcove(tiles, cx, cy, bush_pts)
            camps.append({"pos": [cx, cy], "type": kind})

    for poly in LANES.values():
        stamp_polyline(tiles, poly, r=2.6, value=LANE)

    # Muri lungo le lane (2 ingressi per lane) + dorsali interne (corridoi).
    gaps = [BASE0, BASE1] + [tuple(d) for d in DENS.values()]
    for poly in LANES.values():
        for f in (0.34, 0.66):
            gaps.append(point_at_fraction(poly, f))
    lane_walls(tiles, gaps)

    def ridge(a, b):
        steps = int(math.hypot(b[0] - a[0], b[1] - a[1]) * 2) + 1
        for i in range(steps + 1):
            t = i / steps
            stamp_disk(tiles, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                       1.4, JWALL, only_floor=True)
    for (a, b) in [((78, 58), (92, 72)), ((104, 66), (116, 80)), ((76, 36), (90, 44))]:
        ridge(a, b); ridge(mirror(*a), mirror(*b))

    for (bx, by) in bush_pts:
        stamp_disk(tiles, bx, by, 2.0, BUSH, only_floor=True)
    for (hx, hy) in [(60, 86), (86, 60), (42, 66), (108, 84)]:
        for (cx, cy) in ((hx, hy), mirror(hx, hy)):
            stamp_disk(tiles, cx, cy, 2.4, BUSH, only_floor=True)

    for base in (BASE0, BASE1):
        stamp_disk(tiles, base[0], base[1], 5, LANE)
    for d in DENS.values():
        stamp_disk(tiles, d[0], d[1], 2, FLOOR)

    for i in range(N):
        for t in (0, 1, N - 2, N - 1):
            tiles[t][i] = WALL
            tiles[i][t] = WALL

    structures = []
    for team, base in ((0, BASE0), (1, BASE1)):
        structures.append({"type": "core", "team": team, "pos": [base[0], base[1]]})
        for lane, poly in LANES.items():
            for name, frac, tier in TOWER_FRACTIONS[team]:
                px, py = point_at_fraction(poly, frac)
                px, py = round(px, 1), round(py, 1)
                stamp_disk(tiles, px, py, 3, LANE)
                structures.append({"type": "tower", "team": team, "lane": lane,
                                   "tier": tier, "name": name, "pos": [px, py]})

    ensure_reachable(tiles, camps, (BASE0[0], BASE0[1]))

    valid = []
    for c in camps:
        x, y = c["pos"]
        if tiles[y][x] in (FLOOR, BUSH):
            valid.append(c)
        else:
            print("  ! campo scartato:", c["pos"], "tile", tiles[y][x])
    camps = valid

    puddles = [[x, y] for y in range(N) for x in range(N)
               if tiles[y][x] == FLOOR and x % 9 == 4 and y % 9 == 4]

    data = {
        "name": "Giungla 5v5", "width": N, "height": N, "team_size": 5,
        "tiles": tiles, "puddles": puddles,
        "teams": {"0": {"base": list(BASE0)}, "1": {"base": list(BASE1)}},
        "lanes": {k: [[round(x, 1), round(y, 1)] for (x, y) in v] for k, v in LANES.items()},
        "structures": structures, "dens": DENS, "camps": camps,
        "spawns": {"team0": list(BASE0), "team1": list(BASE1)},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data), encoding="utf-8")
    print(f"Scritta {OUT}  ({N}x{N}, {len(structures)} strutture, {len(camps)} campi)")


if __name__ == "__main__":
    build()
