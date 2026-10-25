"""Generatore della mappa 3v3 (giungla stile LoL).

Produce data/maps/map_3v3.json: griglia 100x100 con 3 lane, un fiume in diagonale
(con sponde murate e due "pozzi"/tane come Drago e Barone), e una vera giungla
scavata nei muri: alcove-campo con i Pokémon neutrali minori, boschetti (bush) e
corridoi. Simmetrica a 180° rispetto al centro.

Le 3 giungle "speciali" (Sole/Pioggia/Vento) nascono da questa base via
engine/jungle.apply_weather: il Sole secca i boschetti, la Pioggia allaga, il
Vento apre i muri di giungla (quindi più muri qui = Vento più incisivo).

Uso:  python tools/gen_map_3v3.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "maps" / "map_3v3.json"

N = 100
FLOOR, WALL, LANE, RIVER, BUSH, JWALL, PUDDLE = 0, 1, 2, 3, 4, 5, 6

BASE0 = (12, 88)   # blu, basso-sinistra
BASE1 = (88, 12)   # rosso, alto-destra

LANES = {
    "mid": [BASE0, (50, 50), BASE1],
    "top": [BASE0, (12, 12), BASE1],
    "bot": [BASE0, (88, 88), BASE1],
}
TOWER_FRACTIONS = {
    0: [("inner", 0.28, 2), ("outer", 0.44, 1)],
    1: [("inner", 0.72, 2), ("outer", 0.56, 1)],
}
# Pozzi sul fiume: tana bassa = leggendario meteo; tana alta = Arceus.
DENS = {"low": [62, 62], "high": [37, 37]}

# Campi dei Pokémon minori. Definiti nella metà del fiume lato x>y (giungla della
# squadra 1); l'altra metà è il simmetrico a 180° (giungla squadra 0). Per lato ci
# sono DUE quadranti ai lati della mid-lane, con campi sparsi dal fiume alle lane
# (come in LoL), non attaccati al fiume. type: "big" (buff) o "small".
CAMPS_HALF = [
    # quadrante "alto" (tra top-lane e mid): 2 campi + buff
    (46, 30, "small"),
    (50, 38, "big"),     # buff spostato "verso il 50" (mirror team0 -> 50,62)
    (36, 26, "small"),   # spostato (mirror team0 -> 64,74)
    # quadrante "destro" (tra mid e bot-lane): 2 campi + buff
    (64, 46, "small"),
    (74, 56, "big"),
    (80, 40, "small"),
]


def mirror(x, y):
    return (N - x, N - y)


def point_at_fraction(poly, f):
    segs, total = [], 0.0
    for a, b in zip(poly, poly[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append((a, b, d)); total += d
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
            x = a[0] + (b[0] - a[0]) * t
            y = a[1] + (b[1] - a[1]) * t
            stamp_disk(tiles, x, y, r, value)


def near_any(x, y, pts, d):
    return any((x - px) ** 2 + (y - py) ** 2 <= d * d for px, py in pts)


def flood(tiles, start):
    from collections import deque
    blocked = {WALL, JWALL}
    seen = {start}
    dq = deque([start])
    while dq:
        x, y = dq.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < N and 0 <= ny < N and (nx, ny) not in seen \
                    and tiles[ny][nx] not in blocked:
                seen.add((nx, ny)); dq.append((nx, ny))
    return seen


def ensure_reachable(tiles, camps, src):
    """Garantisce che ogni campo sia raggiungibile: se è murato, scava un
    corridoio verso il centro finché non tocca la zona già raggiungibile."""
    seen = flood(tiles, src)
    for c in camps:
        x, y = c["pos"]
        if (x, y) in seen:
            continue
        cx, cy = x, y
        steps = 0
        while (cx, cy) not in seen and steps < 160:
            # pulisci un blocco 2x2 (evita i tagli d'angolo della pathfinding)
            for ox in (0, 1):
                for oy in (0, 1):
                    tx, ty = cx + ox, cy + oy
                    if 0 <= tx < N and 0 <= ty < N and tiles[ty][tx] in (WALL, JWALL):
                        tiles[ty][tx] = FLOOR
            if cx != 50:                 # un passo ORTOGONALE verso il centro
                cx += 1 if cx < 50 else -1
            elif cy != 50:
                cy += 1 if cy < 50 else -1
            steps += 1
        seen = flood(tiles, src)


def alcove(tiles, cx, cy, camps_bushes):
    """Scava un'alcova-campo: muro di giungla a C (3 lati) aperto verso il centro
    mappa, con il Pokémon neutrale dentro e un boschetto accanto all'ingresso."""
    cx, cy = int(cx), int(cy)
    # L'apertura guarda verso il centro mappa (50,50).
    ang = math.atan2(50 - cy, 50 - cx)
    r = 4
    for a in range(0, 360, 12):
        rad = math.radians(a)
        # salta un settore di ~90° verso il centro (l'ingresso)
        da = abs(((math.degrees(rad) - math.degrees(ang) + 180) % 360) - 180)
        if da < 50:
            continue
        wx = cx + int(round(math.cos(rad) * r))
        wy = cy + int(round(math.sin(rad) * r))
        if 0 <= wx < N and 0 <= wy < N and tiles[wy][wx] == FLOOR:
            tiles[wy][wx] = JWALL
            # ispessisci un po' il muro
            for ox, oy in ((1, 0), (0, 1)):
                nx, ny = wx + ox, wy + oy
                if 0 <= nx < N and 0 <= ny < N and tiles[ny][nx] == FLOOR \
                        and (nx - cx) ** 2 + (ny - cy) ** 2 > (r - 1) ** 2:
                    tiles[ny][nx] = JWALL
    # boschetto accanto all'ingresso (verso il centro)
    bx = cx + int(round(math.cos(ang) * (r + 2)))
    by = cy + int(round(math.sin(ang) * (r + 2)))
    camps_bushes.append((bx, by))


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
    """Muro di giungla che costeggia le lane (banda a distanza 4..5.5 dal centro
    lane), con varchi solo in pochi punti: le lane diventano confinate e la
    giungla ha ingressi limitati, come in LoL."""
    for y in range(N):
        for x in range(N):
            if tiles[y][x] != FLOOR:
                continue
            d = lane_dist(x, y)
            if 3.8 <= d <= 6.0 and not near_any(x, y, gaps, 4):
                tiles[y][x] = JWALL


def point_along_from(poly, from_start, dist):
    """Punto sulla polilinea a distanza `dist` dall'estremo (base)."""
    pts = poly if from_start else list(reversed(poly))
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if acc + d >= dist:
            t = (dist - acc) / d if d > 0 else 0.0
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        acc += d
    return pts[-1]


def base_defense(tiles, structures):
    """Base murata (grigio, permanente) con UN varco per lane difeso da una torre
    base: 3 torri all'ingresso come in LoL/Wild Rift."""
    for team, base in ((0, BASE0), (1, BASE1)):
        bx, by = base
        for y in range(N):
            for x in range(N):
                if 9.0 <= math.hypot(x - bx, y - by) <= 10.5 and lane_dist(x, y) > 3.0:
                    if tiles[y][x] in (FLOOR, JWALL, RIVER, BUSH):
                        tiles[y][x] = WALL
        for lane, poly in LANES.items():
            from_start = (poly[0][0] == bx and poly[0][1] == by)
            px, py = point_along_from(poly, from_start, 10.5)
            px, py = round(px, 1), round(py, 1)
            stamp_disk(tiles, px, py, 2.5, LANE)   # spiazzo torre: apre il varco
            structures.append({"type": "tower", "team": team, "lane": lane,
                               "tier": 3, "name": "base", "pos": [px, py]})


def seal_corners(tiles):
    """Chiude gli angoli del fiume fuori dalla mappa: niente fughe off-map."""
    for y in range(N):
        for x in range(N):
            if x + y <= 6 or x + y >= 2 * N - 8:
                tiles[y][x] = WALL


def river_bank_walls(tiles, dens):
    """Mura le due sponde del fiume (|x-y| in {5,6}) lasciando varchi presso i
    pozzi (tane), il centro e gli angoli: così il fiume ha ingressi come in LoL."""
    gaps = [(50, 50)] + [tuple(d) for d in dens.values()]
    for y in range(N):
        for x in range(N):
            if tiles[y][x] != FLOOR:
                continue
            band = abs(x - y)
            if band in (5, 6):
                if near_any(x, y, gaps, 8):        # varco al pozzo / centro
                    continue
                if x < 18 or y < 18 or x > 82 or y > 82:  # varchi agli angoli (lane)
                    continue
                tiles[y][x] = JWALL


def build():
    tiles = [[FLOOR] * N for _ in range(N)]

    # 1) Fiume diagonale.
    for y in range(N):
        for x in range(N):
            if abs(y - x) <= 3:
                tiles[y][x] = RIVER

    # 2) Sponde del fiume murate (con varchi).
    river_bank_walls(tiles, DENS)

    # 3) Alcove-campo (muri di giungla a C) + raccolta boschetti d'ingresso.
    bush_pts = []
    camps = []
    for (hx, hy, kind) in CAMPS_HALF:
        for (cx, cy) in (( hx, hy), mirror(hx, hy)):
            alcove(tiles, cx, cy, bush_pts)
            camps.append({"pos": [cx, cy], "type": kind})

    # 4) Massi di copertura sparsi (texture da giungla a labirinto), lontano dai campi.
    camp_pts = [tuple(c["pos"]) for c in camps]
    for (hx, hy) in [(50, 22), (68, 60), (30, 34), (72, 44), (60, 62), (46, 40)]:
        for (cx, cy) in ((hx, hy), mirror(hx, hy)):
            if not near_any(cx, cy, camp_pts, 7):
                stamp_disk(tiles, cx, cy, 2, JWALL, only_floor=True)

    # 5) Lane (sopra fiume e muri: creano i varchi dove le attraversano).
    for poly in LANES.values():
        stamp_polyline(tiles, poly, r=2.2, value=LANE)

    # 5b) Muri lungo le lane con pochi ingressi alla giungla (lane confinate).
    gaps = [BASE0, BASE1] + [tuple(d) for d in DENS.values()]
    for poly in LANES.values():
        for f in (0.26, 0.42, 0.58, 0.74):   # più ingressi alla giungla (verde chiaro)
            gaps.append(point_at_fraction(poly, f))
    lane_walls(tiles, gaps)

    # 5c) Dorsali interne: muri/corridoi dentro la giungla (solo su floor).
    def ridge(a, b):
        steps = int(math.hypot(b[0] - a[0], b[1] - a[1]) * 2) + 1
        for i in range(steps + 1):
            t = i / steps
            stamp_disk(tiles, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                       1.0, JWALL, only_floor=True)
    for (a, b) in [((52, 38), (62, 46)), ((70, 44), (78, 54)), ((50, 24), (58, 30))]:
        ridge(a, b); ridge(mirror(*a), mirror(*b))

    # 6) Boschetti: d'ingresso alle alcove + due file lungo le lane (simmetrici).
    for (bx, by) in bush_pts:
        stamp_disk(tiles, bx, by, 1.6, BUSH, only_floor=True)
    for (hx, hy) in [(40, 58), (58, 40), (28, 46), (72, 54)]:
        for (cx, cy) in ((hx, hy), mirror(hx, hy)):
            stamp_disk(tiles, cx, cy, 2, BUSH, only_floor=True)

    # 7) Spiazzi calpestabili attorno a basi e tane.
    for base in (BASE0, BASE1):
        stamp_disk(tiles, base[0], base[1], 4, LANE)
    for d in DENS.values():
        stamp_disk(tiles, d[0], d[1], 2, FLOOR, only_floor=False)

    # 8) Bordo della mappa + chiusura angoli fiume (no fughe off-map).
    for i in range(N):
        for t in (0, 1, N - 2, N - 1):
            tiles[t][i] = WALL
            tiles[i][t] = WALL
    seal_corners(tiles)

    # --- strutture -----------------------------------------------------------
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

    # 8b) Base murata con 3 torri all'ingresso (stile LoL/Wild Rift).
    base_defense(tiles, structures)

    # 9) Garantisci che ogni campo sia raggiungibile (scava se murato).
    ensure_reachable(tiles, camps, (BASE0[0], BASE0[1]))

    # 10) Valida i campi: il centro deve restare calpestabile.
    valid = []
    for c in camps:
        x, y = c["pos"]
        if tiles[y][x] in (FLOOR, BUSH):
            valid.append(c)
        else:
            print("  ! campo scartato (non su floor):", c["pos"], "tile", tiles[y][x])
    camps = valid

    # Pozze della Pioggia: più dense nella giungla (su floor).
    puddles = [[x, y] for y in range(N) for x in range(N)
               if tiles[y][x] == FLOOR and x % 7 == 3 and y % 7 == 3]

    data = {
        "name": "Giungla 3v3",
        "width": N, "height": N, "tiles": tiles, "puddles": puddles,
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
