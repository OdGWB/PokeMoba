"""Grafica della linea ROGGENROLA > BOLDORE > GIGALITH (logica in engine/match.py).

Spostata da game/fx.py senza cambiare il disegno: palette della roccia, tempesta
di sabbia e Frana (disegni persistenti, chiamati da game/world_fx.py), stili delle
mosse e forme (rockspike, crack, fallrock, smackzone, spikefield, avwarn,
chargeglow). Le forme generiche (puff, ring, shard, flash, hexshell) e gli aiuti
FXSystem._dust/_debris restano in fx.py: li usano anche le altre linee.
"""
from __future__ import annotations

import math
import random

import pygame

import config


def _lighten(c, f=0.55):
    return (int(c[0] + (255 - c[0]) * f),
            int(c[1] + (255 - c[1]) * f),
            int(c[2] + (255 - c[2]) * f))


# Roccia (linea Roggenrola): palette a 4 toni con luce da ALTO-SINISTRA
# (facce a sinistra/in alto chiare, a destra/in basso scure) + sabbia/polvere.
ROCK_HI = (190, 174, 140)
ROCK_MID = (138, 122, 98)
ROCK_SH = (90, 78, 64)
ROCK_OUT = (44, 38, 32)
SAND = (216, 186, 124)
SAND_DK = (168, 136, 88)
DUST = (170, 152, 120)
EMBER = (255, 168, 72)


def _h01(i: int, salt: int) -> float:
    """Hash deterministico -> [0,1) (posizioni stabili dei granelli)."""
    h = (i * 374761393 + salt * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


_SAND_CACHE: dict = {}


def _sand_grains(n: int):
    """Granelli della tempesta (in cache per numero): raggio relativo, angolo di
    partenza, velocità angolare (più veloci verso il centro: vortice), colore,
    dimensione in pixel."""
    g = _SAND_CACHE.get(n)
    if g is None:
        g = []
        for i in range(n):
            rad = math.sqrt(_h01(i, 1))
            ang = _h01(i, 2) * math.tau
            w = 0.6 + 1.4 * (1.0 - rad) + 0.4 * _h01(i, 3)
            col = (SAND, SAND_DK, (236, 214, 164))[int(_h01(i, 4) * 3)]
            g.append((rad, ang, w, col, 1 + int(_h01(i, 5) * 2)))
        _SAND_CACHE[n] = g
    return g


def draw_sandstorm(surface, camera, center, radius: float, now: float) -> None:
    """Sabbiafiume: tempesta di sabbia PERMANENTE attorno a Gigalith. Velo
    sabbioso traslucido + granelli che turbinano attorno (vortice) + raffiche
    ad arco sul bordo. Pixel-art: granelli da 1-2 px, niente sfumature."""
    ts = config.TILE_SIZE
    r = radius * ts
    cx, cy = camera.world_to_screen(center.x * ts, center.y * ts)
    W, H = surface.get_size()
    if cx + r < 0 or cx - r > W or cy + r < 0 or cy - r > H:
        return
    size = int(r * 2) + 6
    ov = pygame.Surface((size, size), pygame.SRCALPHA)
    o = size // 2
    pygame.draw.circle(ov, (*SAND, 26), (o, o), int(r))
    pygame.draw.circle(ov, (*SAND_DK, 70), (o, o), int(r), 2)
    # Raffiche: archi che corrono lungo il bordo e a metà raggio.
    for k in range(10):
        rr = r * (0.55 + 0.45 * _h01(k, 7))
        a0 = _h01(k, 8) * math.tau + now * (1.6 + _h01(k, 9))
        pts = [(o + math.cos(a0 + j * 0.12) * rr, o + math.sin(a0 + j * 0.12) * rr)
               for j in range(5)]
        pygame.draw.lines(ov, (236, 214, 164, 110), False, pts, 1)
    for rad, ang, w, col, sz in _sand_grains(max(30, int(radius * radius * 7))):
        a = ang + now * w
        gx = o + int(math.cos(a) * rad * r)
        gy = o + int(math.sin(a) * rad * r)
        ov.fill((*col, 200), pygame.Rect(gx, gy, sz, sz))
    surface.blit(ov, (cx - o, cy - o))


def draw_avalanche(surface, camera, av, now: float) -> None:
    """Frana: un ammasso di massi che ROTOLA (i massi girano attorno al centro
    nel verso di marcia) con ombra a terra verso basso-destra. Luce fissa da
    alto-sinistra su ogni masso, così il rotolamento si legge senza ruotare le
    luci."""
    ts = config.TILE_SIZE
    cx, cy = camera.world_to_screen(av["pos"].x * ts, av["pos"].y * ts)
    R = av["radius"] * ts
    spin = av.get("spin", 0.0)
    sh = pygame.Surface((int(R * 2.2), int(R * 0.9)), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 100), sh.get_rect())
    surface.blit(sh, (int(cx - R * 1.1 + 4), int(cy - R * 0.45 + 5)))
    seed = int(av.get("born", 0.0) * 1000) & 0xFFFF
    rocks = []
    for i in range(7):
        ang = _h01(i, seed) * math.tau + spin * (0.5 if i % 2 else -0.4)
        d = R * (0.2 + 0.55 * _h01(i, seed + 1))
        rb = R * (0.24 + 0.2 * _h01(i, seed + 2))
        bob = abs(math.sin(spin * 1.3 + i)) * R * 0.14
        rocks.append((cx + math.cos(ang) * d, cy + math.sin(ang) * d * 0.55 - R * 0.4 - bob,
                      rb, i))
    rocks.sort(key=lambda t: t[1])
    hi, mid, shd = (164, 150, 122), (116, 103, 85), (74, 65, 55)
    for x, y, rb, i in rocks:
        # Masso SFACCETTATO: poligono irregolare che ruota col rotolamento; le
        # luci restano fisse in alto-sinistra (tre strati sfalsati).
        rot = spin * (1.0 + 0.3 * _h01(i, seed + 3))
        n = 7
        verts = []
        for k in range(n):
            a = rot + k * math.tau / n
            rr = rb * (0.8 + 0.35 * _h01(i * 13 + k, seed + 4))
            verts.append((math.cos(a) * rr, math.sin(a) * rr))

        def poly(scale, ox, oy):
            return [(x + vx * scale + ox, y + vy * scale + oy) for vx, vy in verts]

        pygame.draw.polygon(surface, shd, poly(1.0, 0, 0))
        pygame.draw.polygon(surface, mid, poly(0.78, -rb * 0.12, -rb * 0.12))
        pygame.draw.polygon(surface, hi, poly(0.4, -rb * 0.32, -rb * 0.34))
        pygame.draw.polygon(surface, ROCK_OUT, poly(1.0, 0, 0), 1)
        # spigolo/crepa che gira col masso
        pygame.draw.line(surface, ROCK_OUT, (int(x), int(y)),
                         (int(x + verts[2][0] * 0.8), int(y + verts[2][1] * 0.8)), 1)



# --- stili delle mosse (FXSystem._FX_STYLES via fx_lines) --------------------
def fx_rockspike(fx, e, col):
    """Rocciotomba / Levitoroccia: punte di roccia che SPUNTANO dal terreno
    dietro al fronte dell'onda, restano un attimo e poi si ritirano."""
    c = e.get("c")
    if c is None:
        return
    dx, dy = e.get("dir", (1.0, 0.0))
    px, py = -dy, dx
    r = float(e.get("radius", 0.8))
    for _ in range(random.randint(1, 2)):
        off = random.uniform(-r * 0.85, r * 0.85)
        back = random.uniform(-0.35, 0.1)
        x, y = c[0] + px * off + dx * back, c[1] + py * off + dy * back
        h = random.uniform(0.5, 0.9) * (1.0 - 0.35 * abs(off) / max(r, 1e-6))
        fx._shape(kind="rockspike", c=(x, y), h=h, w=random.uniform(0.24, 0.38),
                    lean=random.uniform(-0.12, 0.12), col=col,
                    life=random.uniform(0.6, 0.8))
    fx._dust(c, r * 0.6, n=3, speed=(0.4, 1.4))

def fx_pillar(fx, e, col):
    """Pilastro che spunta: anello di polvere alla base + sassolini."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=0.25, r1=1.0, col=DUST, life=0.4, wd=0.16)
    fx._dust(c, 0.6, n=12)
    if e.get("explosive"):
        fx._dust(c, 0.5, n=8, col=EMBER, speed=(1.5, 3.0))   # Pietrataglio: scintille

def fx_pillarbreak(fx, e, col):
    """Pilastro che si sbriciola a fine durata."""
    c = e.get("c")
    if c is None:
        return
    fx._debris(c, 0.9, 7, col=ROCK_MID, life=(0.25, 0.4), size=(0.12, 0.2))
    fx._dust(c, 0.6, n=12)

def fx_shockwave(fx, e, col):
    """Pesobomba contro un muro/pilastro: onda d'urto a terra + crepe
    radiali + detriti (stessa forma per il rilancio della valanga)."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.2))
    fx._shape(kind="ring", c=c, r0=0.3, r1=r, col=DUST, life=0.45, wd=0.3)
    fx._shape(kind="ring", c=c, r0=0.2, r1=r * 0.7, col=ROCK_HI, life=0.3, wd=0.14)
    cracks = []
    for k in range(7):
        ang = k * math.tau / 7 + random.uniform(-0.25, 0.25)
        pts, rr, a2 = [(0.0, 0.0)], 0.0, ang
        while rr < r * 0.8:
            rr += random.uniform(0.25, 0.45)
            a2 += random.uniform(-0.35, 0.35)
            pts.append((math.cos(a2) * rr, math.sin(a2) * rr * 0.75))
        cracks.append(pts)
    fx._shape(kind="crack", c=c, cracks=cracks, col=ROCK_OUT, life=0.9)
    fx._debris(c, r * 0.8, 8)
    fx._dust(c, r * 0.8, n=20)

def fx_rockburst(fx, e, col):
    """Esplosione di un pilastro (Pietrataglio) / valanga che si schianta."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.0))
    fx._shape(kind="ring", c=c, r0=0.2, r1=r, col=EMBER, life=0.35, wd=0.22)
    fx._shape(kind="ring", c=c, r0=0.2, r1=r * 0.8, col=ROCK_HI, life=0.45, wd=0.16)
    fx._debris(c, r, 12, life=(0.3, 0.55), size=(0.18, 0.3))
    fx._dust(c, r * 0.7, n=22)
    fx._dust(c, r * 0.4, n=10, col=EMBER, speed=(2.0, 4.0))

def fx_chargedust(fx, e, col):
    """Pesobomba: scia di polvere sollevata dietro la carica."""
    a = e.get("a")
    if a is None:
        return
    fx._dust(a, 0.35, n=3, speed=(0.3, 1.2))

def fx_knockup(fx, e, col):
    """Nemico lanciato in aria: sbuffo di polvere ai piedi."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="ring", c=c, r0=0.15, r1=0.75, col=DUST, life=0.3, wd=0.12)
    fx._dust(c, 0.35, n=8)

def fx_smackdown(fx, e, col):
    """Abbattimento: macigni che PIOMBANO dall'alto nell'area + onda a terra."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.4))
    n = max(3, int(r * 2.2))
    for i in range(n):
        ang = random.uniform(0, math.tau)
        d = r * math.sqrt(random.random()) * 0.85
        gx, gy = c[0] + math.cos(ang) * d, c[1] + math.sin(ang) * d * 0.8
        fall = random.uniform(0.18, 0.26)
        w = i * 0.035
        fx._shape(kind="fallrock", c=(gx, gy), h=4.0, sz=random.uniform(0.22, 0.34),
                    col=col, life=fall, wait=w)
        fx._shape(kind="ring", c=(gx, gy), r0=0.1, r1=0.6, col=DUST, life=0.3,
                    wd=0.1, wait=w + fall)
    fx._shape(kind="ring", c=c, r0=r * 0.4, r1=r, col=ROCK_HI, life=0.4, wd=0.2,
                wait=0.2)
    fx._dust(c, r * 0.8, n=18)

def fx_smackzone(fx, e, col):
    """Zona di Abbattimento ancora attiva: cerchio tratteggiato che ruota."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="smackzone", c=c, r=float(e.get("radius", 2.4)), col=ROCK_HI,
                life=float(e.get("dur", 2.0)))

def fx_spikefield(fx, e, col):
    """Levitoroccia: rocce aguzze che fluttuano basse sull'area per tutta la
    durata (posizioni fisse, oscillano piano)."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.4))
    stones = []
    n = max(8, int(r * r * 2.4))
    for _ in range(n):
        ang = random.uniform(0, math.tau)
        d = r * 0.92 * math.sqrt(random.random())
        stones.append((math.cos(ang) * d, math.sin(ang) * d * 0.8,
                       random.uniform(0.16, 0.26), random.uniform(0, math.tau),
                       random.uniform(-0.5, 0.5)))
    stones.sort(key=lambda s: s[1])   # dal fondo al davanti
    fx._shape(kind="spikefield", c=c, r=r, stones=stones, col=col,
                life=float(e.get("dur", 8.0)))

def fx_sandburst(fx, e, col):
    """Terrempesta: la tempesta si allarga di colpo (anello di sabbia)."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 6.0))
    fx._shape(kind="ring", c=c, r0=1.0, r1=r, col=SAND, life=0.6, wd=0.35)
    fx._shape(kind="ring", c=c, r0=0.5, r1=r * 0.7, col=SAND_DK, life=0.45, wd=0.2)
    fx._dust(c, r * 0.6, n=30, col=SAND, speed=(1.5, 4.0))

def fx_ironshell(fx, e, col):
    """Ferroscudo: guscio esagonale d'acciaio che si chiude sul Pokémon."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="hexshell", c=c, r=0.95, col=col, life=0.7)
    fx._rise(c, _lighten(col, 0.4))

def fx_avalanchewarn(fx, e, col):
    """Frana: telegraph del percorso (corsia + frecce che scorrono verso
    Gigalith) per il ritardo prima che la valanga parta."""
    c, b = e.get("c"), e.get("b")
    if c is None or b is None:
        return
    delay = float(e.get("delay", 0.6))
    fx._shape(kind="avwarn", a=c, b=b, r=float(e.get("radius", 1.5)), col=SAND_DK,
                life=delay + 0.35)
    fx._shape(kind="ring", c=c, r0=0.4, r1=float(e.get("radius", 1.5)),
                col=ROCK_HI, life=delay, wd=0.14)
    fx._dust(c, float(e.get("radius", 1.5)), n=16)

def fx_explodecharge(fx, e, col):
    """Esplosione in carica: telegraph rosso-arancio che pulsa sempre più
    forte attorno a Gigalith (ripetuto a ogni tick: aggiorna la stessa forma)."""
    c = e.get("c")
    if c is None:
        return
    t = float(e.get("t", 0.0))
    for s in fx.shapes:
        if s["kind"] == "chargeglow" and abs(s["c"][0] - c[0]) + abs(s["c"][1] - c[1]) < 1.5:
            s["c"], s["t"], s["life"] = tuple(c), t, 0.15
            return
    fx._shape(kind="chargeglow", c=tuple(c), r=float(e.get("radius", 3.0)), t=t,
                col=EMBER, life=0.15)

def fx_explosion(fx, e, col):
    """Esplosione: lampo, palla di fuoco che si espande, fumo e schegge."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 3.0))
    fx._shape(kind="flash", c=c, r=r * 0.8, col=(255, 240, 210), life=0.18)
    fx._shape(kind="ring", c=c, r0=0.4, r1=r, col=EMBER, life=0.45, wd=0.5)
    fx._shape(kind="ring", c=c, r0=0.3, r1=r * 1.1, col=(255, 220, 150), life=0.3,
                wd=0.2)
    fx._shape(kind="ring", c=c, r0=r * 0.5, r1=r * 1.15, col=DUST, life=0.6, wd=0.3,
                wait=0.1)
    fx._debris(c, r * 1.1, 16, life=(0.35, 0.6), size=(0.18, 0.32))
    fx._dust(c, r * 0.6, n=24, col=EMBER, speed=(2.5, 5.0))
    fx._dust(c, r * 0.9, n=34, col=(110, 100, 90), speed=(1.0, 3.5))


SHAPES = ("rockspike", "crack", "fallrock", "smackzone", "spikefield", "avwarn",
          "chargeglow")


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    col = s["col"]
    if kind == "rockspike":
        # Punta di roccia che spunta (0.08s), resta, poi rientra (ultimi
        # 0.25s). Due facce: sinistra chiara, destra in ombra + contorno.
        cx, cy = S(*s["c"])
        age = s["maxlife"] - s["life"]
        k = min(1.0, age / 0.08) * min(1.0, s["life"] / 0.25)
        h = s["h"] * ts * k
        if h >= 1.5:
            hw = s["w"] * ts * 0.5
            tx, ty = cx + s["lean"] * ts, cy - h
            left = [(cx - hw, cy), (tx, ty), (cx + hw * 0.15, cy + 1)]
            right = [(cx + hw * 0.15, cy + 1), (tx, ty), (cx + hw, cy)]
            pygame.draw.polygon(overlay, (*ROCK_HI, 255), left)
            pygame.draw.polygon(overlay, (*ROCK_SH, 255), right)
            pygame.draw.polygon(overlay, (*ROCK_OUT, 255),
                                [(cx - hw, cy), (tx, ty), (cx + hw, cy)], 1)
    elif kind == "crack":
        # Crepe a terra dell'onda d'urto (spezzate), che sbiadiscono.
        cx, cy = S(*s["c"])
        av = int(200 * min(1.0, f * 1.6))
        for pts in s["cracks"]:
            pp = [(cx + x * ts, cy + y * ts) for x, y in pts]
            if len(pp) > 1:
                pygame.draw.lines(overlay, (*col, av), False, pp, 2)
                pygame.draw.lines(overlay, (*ROCK_HI, av // 2), False,
                                  [(x - 1, y - 1) for x, y in pp], 1)
    elif kind == "fallrock":
        # Macigno che piomba dall'alto (accelera) + ombra che si stringe.
        gx, gy = S(*s["c"])
        t = 1 - f
        hz = s["h"] * (1 - t * t) * ts
        r = max(2, int(s["sz"] * ts))
        sh = max(2, int(r * (0.6 + 0.6 * t)))
        pygame.draw.ellipse(overlay, (0, 0, 0, int(60 + 60 * t)),
                            pygame.Rect(gx - sh, gy - sh // 2, sh * 2, sh))
        ry = int(gy - hz)
        pygame.draw.circle(overlay, (*ROCK_OUT, 255), (gx, ry), r + 1)
        pygame.draw.circle(overlay, (*ROCK_SH, 255), (gx, ry), r)
        pygame.draw.circle(overlay, (*ROCK_MID, 255), (gx - 1, ry - 1), max(1, r - 2))
        pygame.draw.circle(overlay, (*ROCK_HI, 255), (gx - r // 3, ry - r // 3),
                           max(1, r // 3))
    elif kind == "smackzone":
        # Abbattimento attivo: cerchio tratteggiato che ruota piano.
        cx, cy = S(*s["c"])
        r = s["r"] * ts
        age = s["maxlife"] - s["life"]
        vis = max(0.0, min(1.0, age / 0.2, s["life"] / 0.3))
        av = int(170 * vis)
        pygame.draw.ellipse(overlay, (*ROCK_SH, int(40 * vis)),
                            pygame.Rect(int(cx - r), int(cy - r * 0.8), int(r * 2), int(r * 1.6)))
        n = 16
        for i in range(n):
            if i % 2:
                continue
            a0 = age * 0.8 + i * math.tau / n
            a1 = a0 + math.tau / n
            pygame.draw.line(overlay, (*col, av),
                             (cx + math.cos(a0) * r, cy + math.sin(a0) * r * 0.8),
                             (cx + math.cos(a1) * r, cy + math.sin(a1) * r * 0.8), 2)
    elif kind == "spikefield":
        # Levitoroccia: punte di pietra sospese basse che oscillano;
        # ombra a terra sotto ognuna. Salgono all'inizio, calano alla fine.
        cx, cy = S(*s["c"])
        age = s["maxlife"] - s["life"]
        up = min(1.0, age / 0.3) * min(1.0, s["life"] / 0.5)
        for dx, dy, sz, ph, lean in s["stones"]:
            gx, gy = cx + dx * ts, cy + dy * ts
            r = max(2, int(sz * ts))
            pygame.draw.ellipse(overlay, (0, 0, 0, int(70 * up)),
                                pygame.Rect(int(gx - r), int(gy - r * 0.35), r * 2, max(2, int(r * 0.7))))
            hz = (0.22 + 0.06 * math.sin(age * 2.6 + ph)) * ts * up
            sx, sy = gx, gy - hz
            tipx, tipy = sx + lean * r, sy - r * 1.7
            base_l, base_r = (sx - r, sy), (sx + r, sy)
            bot = (sx, sy + r * 0.7)
            aa = int(255 * min(1.0, up * 1.5))
            pygame.draw.polygon(overlay, (*ROCK_HI, aa), [base_l, (tipx, tipy), (sx, sy)])
            pygame.draw.polygon(overlay, (*ROCK_MID, aa), [(sx, sy), (tipx, tipy), base_r])
            pygame.draw.polygon(overlay, (*ROCK_SH, aa), [base_l, (sx, sy), base_r, bot])
            pygame.draw.polygon(overlay, (*ROCK_OUT, aa),
                                [base_l, (tipx, tipy), base_r, bot], 1)
    elif kind == "avwarn":
        # Frana: corsia telegrafata + chevron che scorrono verso Gigalith.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        ang = math.atan2(by - ay, bx - ax)
        ca, sa = math.cos(ang), math.sin(ang)
        px, py = -sa, ca
        w = s["r"] * ts
        vis = min(1.0, s["life"] / 0.35)
        quad = [(ax + px * w, ay + py * w), (bx + px * w, by + py * w),
                (bx - px * w, by - py * w), (ax - px * w, ay - py * w)]
        pygame.draw.polygon(overlay, (*col, int(45 * vis)), quad)
        pygame.draw.polygon(overlay, (*_lighten(col, 0.3), int(140 * vis)), quad, 1)
        L = math.hypot(bx - ax, by - ay)
        age = s["maxlife"] - s["life"]
        step = 0.9 * ts
        off = (age * 3.0 * ts) % step
        d = off
        while d < L:
            mx, my = ax + ca * d, ay + sa * d
            hw = w * 0.55
            pygame.draw.lines(overlay, (*_lighten(col, 0.45), int(160 * vis)), False,
                              [(mx - ca * hw * 0.6 + px * hw, my - sa * hw * 0.6 + py * hw),
                               (mx, my),
                               (mx - ca * hw * 0.6 - px * hw, my - sa * hw * 0.6 - py * hw)], 2)
            d += step
    elif kind == "chargeglow":
        # Esplosione in carica: area telegrafata che si accende, anello
        # interno che si chiude, nucleo che pulsa e crepe che crescono.
        cx, cy = S(*s["c"])
        t = max(0.0, min(1.0, s["t"]))
        r = s["r"] * ts
        pulse = 0.5 + 0.5 * math.sin((s["maxlife"] - s["life"] + t * 9.0) * 12.0)
        pygame.draw.circle(overlay, (*col, int(25 + 45 * t)), (cx, cy), int(r))
        pygame.draw.circle(overlay, (*_lighten(col, 0.3), int(150 + 80 * pulse)),
                           (cx, cy), int(r), 2)
        ir = max(2, int(r * (1.0 - t)))
        pygame.draw.circle(overlay, (255, 230, 170, 200), (cx, cy), ir, 2)
        core = max(2, int((0.35 + 0.45 * t + 0.1 * pulse) * ts))
        pygame.draw.circle(overlay, (*col, int(60 + 50 * t)), (cx, cy - int(0.3 * ts)), core)
        pygame.draw.circle(overlay, (255, 245, 220, int(70 + 60 * pulse * t)),
                           (cx, cy - int(0.3 * ts)), max(1, core // 2))
        for k in range(6):
            a2 = k * math.tau / 6 + 0.4
            L = r * 0.55 * t
            mx = cx + math.cos(a2 + 0.2) * L * 0.5
            my = cy + math.sin(a2 + 0.2) * L * 0.4
            pygame.draw.lines(overlay, (255, 190, 100, int(220 * t)), False,
                              [(cx, cy), (mx, my),
                               (cx + math.cos(a2) * L, cy + math.sin(a2) * L * 0.8)], 2)


STYLES = {
    "rockspike": fx_rockspike,
    "pillar": fx_pillar,
    "pillarbreak": fx_pillarbreak,
    "shockwave": fx_shockwave,
    "rockburst": fx_rockburst,
    "chargedust": fx_chargedust,
    "knockup": fx_knockup,
    "smackdown": fx_smackdown,
    "smackzone": fx_smackzone,
    "spikefield": fx_spikefield,
    "sandburst": fx_sandburst,
    "ironshell": fx_ironshell,
    "avalanchewarn": fx_avalanchewarn,
    "explodecharge": fx_explodecharge,
    "explosion": fx_explosion,
}
