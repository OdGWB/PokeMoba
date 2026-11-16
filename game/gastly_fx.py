"""Grafica della linea Gastly > Haunter > Gengar: effetti istantanei (handler
registrati in FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes
(sfera di gas spettrale, lingua di Leccata, globo e pozza di fango, scia dei
sogni di Mangiasogni, ombra di Furtivombra, occhi di Congiura, portale di
Spettrotuffo, sigillo e faccia della Maledizione), Palla Ombra e Ipnosi in volo
(world_fx.draw_projectiles) e i disegni sulle unità (cariche d'anima che
girano attorno, marchio della Maledizione, sonnolenza di Ipnosi).

Pixel art: forme piene a 3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

GHOST = ((44, 22, 78), (132, 82, 214), (214, 180, 255))     # contorno, corpo, luce
CORE = (22, 12, 36)                                         # cuore scuro della sfera
SLUDGE = ((46, 16, 54), (128, 52, 160), (196, 128, 226))    # fango velenoso
SLUDGE_HI = (226, 196, 244)
SLUDGE_MID = (82, 30, 100)                                  # corpo della pozza
PSY = ((96, 28, 82), (238, 112, 192), (255, 206, 238))      # Ipnosi, Mangiasogni
TONGUE = ((104, 28, 56), (232, 98, 140), (255, 184, 204))   # Leccata
EYE = ((70, 0, 10), (232, 36, 46), (255, 214, 120))         # occhi di Congiura
WHITE = (255, 255, 255)


def _al(f, k=2.0):
    return max(0, min(255, int(255 * min(1.0, f * k))))


def _bits(fx, c, n, cols, speed=1.6, life=(0.3, 0.6), up=0.7):
    for _ in range(n):
        a = random.uniform(0, math.tau)
        sp = random.uniform(0.3, 1.0) * speed
        fx._add(c[0], c[1], math.cos(a) * sp, math.sin(a) * sp * 0.6 - up,
                random.uniform(*life), random.choice(cols), 1)


def _shake(fx, ms):
    fx.shake_until_ms = max(getattr(fx, "shake_until_ms", 0), pygame.time.get_ticks() + ms)


# --- mattoni ---------------------------------------------------------------------------

def draw_gas_orb(surface, x, y, r, ang, alpha, ph=0.0, tail=1.0, cols=GHOST, core=CORE):
    """Sfera di gas spettrale: alone di gas viola che si sfilaccia all'indietro
    in tre ciuffi ondeggianti, cuore scuro, riflesso in alto a sinistra."""
    r = max(2.0, r)
    bx, by = -math.cos(ang), -math.sin(ang)
    px, py = -by, bx
    for lobe in (-1, 0, 1):   # ciuffi di gas dietro la sfera
        for i in range(5, 0, -1):
            u = i / 5
            d = r * (0.4 + 1.9 * u) * tail
            wob = (math.sin(ph * 1.3 + i * 1.1 + lobe * 2.0) * 0.35 + lobe * 0.45) * r * u
            rr = r * (0.75 - 0.5 * u)
            col = cols[0] if i > 3 else cols[1]
            pygame.draw.circle(surface, (*col, int(alpha * (1.0 - 0.55 * u))),
                               (int(x + bx * d + px * wob), int(y + by * d + py * wob)), max(1, int(rr)))
    pygame.draw.circle(surface, (*cols[0], alpha), (int(x), int(y)), int(r * 1.15))
    pygame.draw.circle(surface, (*cols[1], alpha), (int(x), int(y)), int(r))
    pygame.draw.circle(surface, (*core, alpha), (int(x + r * 0.08), int(y + r * 0.08)), max(1, int(r * 0.66)))
    pygame.draw.circle(surface, (*cols[2], alpha), (int(x - r * 0.42), int(y - r * 0.42)),
                       max(1, int(r * 0.24)))


def _spiral(surface, cx, cy, R, rot, alpha, cols=PSY, w=2, sq=1.0):
    """Spirale ipnotica a due bracci (contorno scuro + filo chiaro)."""
    for arm in range(2):
        pts = []
        for i in range(14):
            u = i / 13
            an = rot + arm * math.pi + u * 3.2 * math.pi
            rr = R * (0.12 + 0.88 * u)
            pts.append((cx + math.cos(an) * rr, cy + math.sin(an) * rr * sq))
        pygame.draw.lines(surface, (*cols[0], alpha), False, pts, w + 2)
        pygame.draw.lines(surface, (*cols[2], alpha), False, pts, w)


def _evil_eye(surface, cx, cy, s, side, alpha):
    """Occhio a mandorla inclinato verso il centro (Congiura): rosso con la
    pupilla a fessura."""
    sg = 1 if side > 0 else -1
    pts = [(cx - sg * s * 1.1, cy - s * 0.55), (cx + sg * s * 0.2, cy - s * 0.05),
           (cx + sg * s * 1.0, cy + s * 0.35), (cx - sg * s * 0.1, cy + s * 0.45)]
    out = [(cx + (x - cx) * 1.35, cy + (y - cy) * 1.5) for x, y in pts]
    pygame.draw.polygon(surface, (*EYE[0], alpha), out)
    pygame.draw.polygon(surface, (*EYE[1], alpha), pts)
    pygame.draw.line(surface, (*EYE[2], alpha), (int(cx), int(cy - s * 0.3)), (int(cx), int(cy + s * 0.35)), 1)


# --- forme -------------------------------------------------------------------------------

SHAPES = ("gastorb", "gastlick", "gastglob", "gastpuddle", "gastdrain", "gastshade",
          "gasteyes", "gastportal", "gastsigil", "gastface")
AA_TRAVEL = {"gastorb": 0.85}


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    age = s["maxlife"] - s["life"]
    if kind == "gastorb":
        # Sfera di gas da A a B (attacco base, Sciagura): la testa arriva a 0,85.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        if u >= 1.0:
            return
        lift = s.get("lift", 0.42) * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        ang = math.atan2(by - ay, bx - ax)
        al = 255 if "hom" in s else _al(f, 4.0)
        draw_gas_orb(overlay, x, y, s.get("sz", 0.15) * ts, ang, al, ph=age * 22 + s.get("seed", 0),
                     cols=s.get("cols", GHOST))
    elif kind == "gastlick":
        # Leccata: lingua rosa che esce dalla bocca lungo il cono, ondeggia e rientra.
        ox, oy = S(*s["o"])
        oy -= int(0.32 * ts)
        ang = s.get("ang", 0.0)
        ext = math.sin(math.pi * min(1.0, t)) ** 0.6
        L = s.get("rng", 2.4) * 0.85 * ts * ext
        if L < 3:
            return
        ca, sa = math.cos(ang), math.sin(ang) * 0.85
        pl, pr = [], []
        tip = (ox, oy)
        for i in range(11):
            u = i / 10
            d = L * u
            wav = math.sin(u * 3.4 - age * 22) * 0.14 * ts * u
            w = 0.15 * ts * (1.0 - 0.3 * u)
            cx, cy = ox + ca * d - sa * wav, oy + sa * d + ca * wav
            pl.append((cx - sa * w, cy + ca * w))
            pr.append((cx + sa * w, cy - ca * w))
            tip = (cx, cy)
        poly = pl + pr[::-1]
        out = [(x + 1, y + 1) for x, y in poly]
        pygame.draw.polygon(overlay, (*TONGUE[0], 255), out)
        pygame.draw.polygon(overlay, (*TONGUE[0], 255), poly, 0)
        pygame.draw.circle(overlay, (*TONGUE[0], 255), (int(tip[0] + 1), int(tip[1] + 1)), int(0.12 * ts) + 1)
        inner = [(x * 0.8 + px_ * 0.2, y * 0.8 + py_ * 0.2) for (x, y), (px_, py_) in zip(pl, pr)]
        inner += [(x * 0.8 + px_ * 0.2, y * 0.8 + py_ * 0.2) for (x, y), (px_, py_) in
                  zip(pr[::-1], pl[::-1])]
        pygame.draw.polygon(overlay, (*TONGUE[1], 255), inner)
        pygame.draw.circle(overlay, (*TONGUE[1], 255), (int(tip[0]), int(tip[1])), int(0.11 * ts))
        mid = [((x + px_) / 2, (y + py_) / 2) for (x, y), (px_, py_) in zip(pl, pr)]
        pygame.draw.lines(overlay, (*TONGUE[0], 160), False, mid[1:-1], 1)
        hi = [(x * 0.6 + (x + px_) / 2 * 0.4, y * 0.6 + (y + py_) / 2 * 0.4 - 1) for (x, y), (px_, py_) in
              zip(pl[1:8], pr[1:8])]
        pygame.draw.lines(overlay, (*TONGUE[2], 220), False, hi, 1)
    elif kind == "gastglob":
        # Globo di fango ad arco da A a B, con l'ombra a terra e due gocce dietro.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        fly = s.get("fly", 1.0)
        u = min(1.0, t / fly)
        if u >= 1.0:
            return
        lift = s.get("lift", 0.4) * ts
        h = s.get("h", 1.2) * ts
        r = s.get("sz", 0.2) * ts
        gx_, gy_ = ax + (bx - ax) * u, ay + (by - ay) * u
        sh = pygame.Rect(0, 0, int(r * 2.2), max(2, int(r * 0.8)))
        sh.center = (int(gx_), int(gy_))
        pygame.draw.ellipse(overlay, (10, 6, 14, 110), sh)
        for k in (2, 1, 0):
            uk = max(0.0, u - 0.06 * k)
            x = ax + (bx - ax) * uk
            y = ay + (by - ay) * uk - lift - 4 * h * uk * (1.0 - uk)
            rr = r * (1.0 - 0.3 * k)
            pygame.draw.circle(overlay, (*SLUDGE[0], 255), (int(x), int(y)), int(rr) + 1)
            pygame.draw.circle(overlay, (*SLUDGE[1], 255), (int(x - 0.5), int(y - 0.5)), max(1, int(rr)))
            if k == 0:
                pygame.draw.circle(overlay, (*SLUDGE[2], 255), (int(x - rr * 0.3), int(y - rr * 0.35)),
                                   max(1, int(rr * 0.45)))
                overlay.fill((*SLUDGE_HI, 255), pygame.Rect(int(x - rr * 0.45), int(y - rr * 0.5), 2, 2))
    elif kind == "gastpuddle":
        # Pozza di fango velenoso: lobi irregolari, bordo scuro, bolle che scoppiano.
        cx, cy = S(*s["c"])
        R = s.get("r", 1.0) * ts
        grow = min(1.0, age / 0.18)
        R *= 0.5 + 0.5 * grow
        al = int(255 * min(1.0, f / 0.35))
        rnd = random.Random(s.get("seed", 3))
        lobes = [(rnd.uniform(-0.45, 0.45), rnd.uniform(-0.3, 0.3), rnd.uniform(0.45, 0.7)) for _ in range(6)]
        lay = pygame.Surface((int(R * 3) + 4, int(R * 1.8) + 4), pygame.SRCALPHA)
        lx, ly = lay.get_width() / 2, lay.get_height() / 2
        for dx, dy, rr in lobes:   # bordo scuro
            e = pygame.Rect(0, 0, int(R * rr * 2 + 3), int(R * rr * 1.1 + 3))
            e.center = (int(lx + dx * R), int(ly + dy * R * 0.55))
            pygame.draw.ellipse(lay, (*SLUDGE[0], 235), e)
        for dx, dy, rr in lobes:   # corpo
            e = pygame.Rect(0, 0, int(R * rr * 2 - 1), int(R * rr * 1.1 - 1))
            e.center = (int(lx + dx * R), int(ly + dy * R * 0.55))
            pygame.draw.ellipse(lay, (*SLUDGE_MID, 190), e)
        for dx, dy, rr in lobes[3:]:   # chiazze scure dentro
            e = pygame.Rect(0, 0, max(2, int(R * rr * 0.9)), max(2, int(R * rr * 0.4)))
            e.center = (int(lx + dx * R * 0.7 + R * rr * 0.2), int(ly + dy * R * 0.4 + R * rr * 0.12))
            pygame.draw.ellipse(lay, (*SLUDGE[0], 150), e)
        for dx, dy, rr in lobes[:3]:   # riflessi in alto a sinistra
            e = pygame.Rect(0, 0, max(2, int(R * rr * 0.7)), max(1, int(R * rr * 0.22)))
            e.center = (int(lx + dx * R - R * rr * 0.35), int(ly + dy * R * 0.55 - R * rr * 0.2))
            pygame.draw.ellipse(lay, (*SLUDGE[1], 150), e)
        for k in range(s.get("n", 5)):   # bolle che si gonfiano e scoppiano
            per = rnd.uniform(0.45, 0.8)
            q = ((age + rnd.uniform(0, per)) % per) / per
            bx = lx + rnd.uniform(-0.6, 0.6) * R
            by = ly + rnd.uniform(-0.3, 0.3) * R * 0.55
            if q < 0.8:
                br = max(1, int((0.05 + 0.1 * q / 0.8) * ts))
                pygame.draw.circle(lay, (*SLUDGE[0], 255), (int(bx), int(by)), br + 1)
                pygame.draw.circle(lay, (*SLUDGE[1], 255), (int(bx), int(by)), br)
                lay.fill((*SLUDGE_HI, 255), pygame.Rect(int(bx - br * 0.5), int(by - br * 0.6), 1, 1))
            else:
                br = int((0.15 + 0.2 * (q - 0.8) / 0.2) * ts)
                pygame.draw.circle(lay, (*SLUDGE[2], 160), (int(bx), int(by)), max(2, br), 1)
        lay.set_alpha(int(al * 0.7))
        overlay.blit(lay, (int(cx - lx), int(cy - ly)))
    elif kind == "gastdrain":
        # Mangiasogni: fili di sogno rosa che volano dal bersaglio (A) a chi lo
        # mangia (B) su archi diversi.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        lift = 0.45 * ts
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        rnd = random.Random(s.get("seed", 5))
        n = s.get("n", 6)
        for k in range(n):
            off = rnd.uniform(-1.0, 1.0) * min(L * 0.35, 1.4 * ts)
            st = k * 0.06
            u = (t - st) / 0.6
            if u <= 0.0 or u >= 1.0:
                continue
            pts = []
            for j in range(4):
                uu = max(0.0, u - j * 0.06)
                bend = 4 * uu * (1.0 - uu) * off
                pts.append((ax + dx * uu + nx * bend, ay + dy * uu + ny * bend - lift))
            x, y = pts[0]
            for j in range(3, 0, -1):
                pygame.draw.circle(overlay, (*PSY[1], 120 - j * 25), (int(pts[j][0]), int(pts[j][1])),
                                   max(1, 3 - j // 2))
            pygame.draw.circle(overlay, (*PSY[0], 255), (int(x), int(y)), 3)
            pygame.draw.circle(overlay, (*PSY[1], 255), (int(x), int(y)), 2)
            overlay.fill((*PSY[2], 255), pygame.Rect(int(x - 1), int(y - 1), 1, 1))
    elif kind == "gastshade":
        # Furtivombra: fila di sbuffi d'ombra a terra da A a B che svaniscono
        # dalla coda verso la testa; due occhietti bianchi sulla testa.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        n = max(4, int(L / (0.32 * ts)))
        for i in range(n + 1):
            u = i / n
            q = min(1.0, max(0.0, (t * 1.6 - u * 0.9)))   # svanisce prima in coda
            k = 1.0 - q
            if k <= 0.03:
                continue
            w = (0.16 + 0.22 * u) * ts * (0.5 + 0.5 * k)
            wob = math.sin(i * 1.9 + age * 9) * 0.06 * ts
            cx, cy = ax + dx * u - uy * wob, ay + dy * u + ux * wob
            e = pygame.Rect(0, 0, int(w * 2), max(2, int(w * 0.9)))
            e.center = (int(cx), int(cy))
            pygame.draw.ellipse(overlay, (*GHOST[1], int(160 * k)), e.inflate(2, 2))
            pygame.draw.ellipse(overlay, (*CORE, int(200 * k)), e)
        if t < 0.6:
            al = _al(1.0 - t / 0.6, 3.0)
            hx, hy = bx, by
            px, py = -uy, ux * 0.55
            for sg in (-1, 1):   # occhietti bianchi a fessura
                ex = int(hx + ux * 0.1 * ts + px * sg * 0.13 * ts)
                ey = int(hy - 1 + py * sg * 0.13 * ts)
                overlay.fill((*WHITE, al), pygame.Rect(ex - 1, ey, 3, 1))
    elif kind == "gasteyes":
        # Congiura: due occhi rossi a mandorla che si aprono sopra chi la usa.
        cx, cy = S(*s["c"])
        cy -= int(s.get("h", 1.25) * ts)
        op = min(1.0, age / 0.12)
        al = _al(f, 3.0)
        sz = 0.2 * ts * (0.6 + 0.4 * op)
        for sg in (-1, 1):   # alone scuro piccolo dietro ogni occhio
            pygame.draw.circle(overlay, (*CORE, int(al * 0.45)), (int(cx + sg * sz * 1.6), int(cy)),
                               int(sz * 1.5))
        for sg in (-1, 1):
            _evil_eye(overlay, cx + sg * sz * 1.6, cy, sz, sg, al)
    elif kind == "gastportal":
        # Spettrotuffo: buco d'ombra a terra con il bordo viola e gas che gira.
        cx, cy = S(*s["c"])
        R = s.get("r", 0.8) * ts
        op = min(1.0, age / 0.15)
        cl = min(1.0, s["life"] / 0.2)
        k = op * cl
        if k <= 0.02:
            return
        R *= k
        rect = pygame.Rect(0, 0, int(2 * R), int(R * 0.9))
        rect.center = (int(cx), int(cy))
        pygame.draw.ellipse(overlay, (*GHOST[0], 230), rect.inflate(4, 3))
        pygame.draw.ellipse(overlay, (*CORE, 240), rect)
        rot = age * 5.0
        for arm in range(3):   # gas che gira verso il centro
            pts = []
            for i in range(7):
                u = i / 6
                an = rot + arm * math.tau / 3 + u * 2.2
                rr = R * (0.95 - 0.75 * u)
                pts.append((cx + math.cos(an) * rr, cy + math.sin(an) * rr * 0.45))
            pygame.draw.lines(overlay, (*GHOST[1], 200), False, pts, 2)
        pygame.draw.ellipse(overlay, (*GHOST[1], 255), rect, 2)
        pygame.draw.arc(overlay, (*GHOST[2], 255), rect, math.radians(100), math.radians(190), 1)
        for i in range(4):   # ciuffi che salgono dal bordo
            q = (age * 1.4 + i * 0.25) % 1.0
            an = i * 1.7 + 0.6
            x = cx + math.cos(an) * R * 0.9
            y = cy + math.sin(an) * R * 0.4 - q * 0.6 * ts
            pygame.draw.circle(overlay, (*GHOST[1], int(200 * (1 - q) * k)), (int(x), int(y)),
                               max(1, int(2.5 * (1 - q * 0.5))))
    elif kind == "gastsigil":
        # Sigillo a terra (Sciagura a segno, marchio della Maledizione): anello con
        # sei rune e un occhio al centro, che si apre e svanisce.
        cx, cy = S(*s["c"])
        R = s.get("r", 0.8) * ts * (0.55 + 0.45 * min(1.0, t * 5))
        al = _al(f, 2.5)
        rect = pygame.Rect(0, 0, int(2 * R), int(R))
        rect.center = (int(cx), int(cy))
        pygame.draw.ellipse(overlay, (*CORE, int(al * 0.45)), rect)
        pygame.draw.ellipse(overlay, (*GHOST[0], al), rect.inflate(2, 2), 3)
        pygame.draw.ellipse(overlay, (*GHOST[1], al), rect, 1)
        rot = s.get("rot", 0.0) + age * 1.5
        for i in range(6):
            an = rot + i * math.tau / 6
            x, y = cx + math.cos(an) * R * 0.78, cy + math.sin(an) * R * 0.39
            pygame.draw.line(overlay, (*GHOST[2], al), (int(x - 1), int(y - 2)), (int(x + 1), int(y + 1)), 1)
            overlay.fill((*GHOST[1], al), pygame.Rect(int(x + 1), int(y - 1), 1, 1))
        ew, eh = R * 0.55, R * 0.2   # occhio
        eye = [(cx - ew, cy), (cx, cy - eh), (cx + ew, cy), (cx, cy + eh)]
        pygame.draw.polygon(overlay, (*GHOST[2], al), eye)
        pygame.draw.circle(overlay, (*CORE, al), (int(cx), int(cy)), max(1, int(eh * 0.85)))
    elif kind == "gastface":
        # Maledizione che esplode: faccia spettrale (gas scuro, occhi e ghigno)
        # che sale dal bersaglio e si dissolve.
        cx, cy = S(*s["c"])
        R = s.get("r", 0.7) * ts * (0.6 + 0.6 * min(1.0, t * 3))
        cy -= int((0.6 + 0.9 * t) * ts)
        al = _al(f, 2.0)
        rnd = random.Random(s.get("seed", 7))
        for i in range(8):   # gas spinoso attorno
            an = i * math.tau / 8 + rnd.uniform(-0.2, 0.2) + age * 1.5
            rr = R * rnd.uniform(0.85, 1.15)
            pygame.draw.circle(overlay, (*GHOST[1], int(al * 0.75)),
                               (int(cx + math.cos(an) * rr), int(cy + math.sin(an) * rr)), max(2, int(R * 0.4)))
        pygame.draw.circle(overlay, (*GHOST[0], al), (int(cx), int(cy)), int(R * 1.02))
        pygame.draw.circle(overlay, (*CORE, al), (int(cx), int(cy)), int(R * 0.9))
        for sg in (-1, 1):   # occhi bianchi inclinati
            ex, ey = cx + sg * R * 0.36, cy - R * 0.2
            pts = [(ex - sg * R * 0.3, ey - R * 0.2), (ex + sg * R * 0.24, ey + R * 0.05),
                   (ex - sg * R * 0.18, ey + R * 0.16)]
            pygame.draw.polygon(overlay, (*WHITE, al), pts)
            overlay.fill((*CORE, al), pygame.Rect(int(ex), int(ey - 1), 2, 2))
        mouth = [(cx - R * 0.5, cy + R * 0.18), (cx + R * 0.5, cy + R * 0.18), (cx, cy + R * 0.58)]
        pygame.draw.polygon(overlay, (*EYE[1], al), mouth)
        for k in range(3):   # denti
            tx = cx - R * 0.33 + k * R * 0.33
            pygame.draw.polygon(overlay, (*WHITE, al), [(tx - 2, cy + R * 0.18), (tx + 2, cy + R * 0.18),
                                                        (tx, cy + R * 0.32)])


# --- effetti istantanei ---------------------------------------------------------------

def fx_gastorb(fx, e, col):
    """Attacco base: sfera di gas spettrale che vola sul bersaglio."""
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    life = 0.2 + L / 30.0
    fx._shape(kind="gastorb", a=tuple(a), b=tuple(b), col=GHOST[1], life=life, sz=0.15,
              seed=random.randrange(999))
    fx._shape(kind="flash", c=(b[0], b[1] - 0.42), r=0.3, col=GHOST[2], life=0.14, wait=life * 0.85)


def fx_gastlick(fx, e, col):
    """Leccata: lingua che esce e rientra + goccioline di saliva in punta."""
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    rng = float(e.get("range", 2.4))
    fx._shape(kind="gastlick", o=tuple(o), ang=math.atan2(d[1], d[0]), rng=rng, col=TONGUE[1], life=0.42)
    tip = (o[0] + d[0] * rng * 0.85, o[1] + d[1] * rng * 0.85 - 0.3)
    for _ in range(5):
        fx._add(tip[0], tip[1], random.uniform(-1.0, 1.0), random.uniform(-1.2, 0.2),
                random.uniform(0.3, 0.5), random.choice((TONGUE[2], WHITE, PSY[2])), 1)


def fx_gastshadowball(fx, e, col):
    """Palla Ombra al lancio: sbuffo di gas alla bocca (in volo la disegna
    world_fx.draw_projectiles)."""
    a = e.get("a")
    if a is None or e.get("kind") != "projectile":
        return
    b = e.get("b") or a
    m = (a[0] + (b[0] - a[0]) * 0.4, a[1] + (b[1] - a[1]) * 0.4 - 0.4)
    fx._shape(kind="flash", c=m, r=0.45, col=GHOST[1], life=0.16)
    _bits(fx, m, 6, (GHOST[1], GHOST[2], CORE), speed=1.4)


def fx_gastshadowballhit(fx, e, col):
    """Palla Ombra a segno: scoppio d'ombra, anello viola e gas che si sparge."""
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 0.4)
    fx._shape(kind="impactstar", c=top, r=0.6, n=7, rot=random.uniform(0, 1),
              cols=(CORE, GHOST[1], GHOST[2]), col=GHOST[1], life=0.24)
    fx._shape(kind="ring", c=top, r0=0.15, r1=0.7, col=GHOST[1], life=0.22, wd=0.06)
    _bits(fx, top, 10, (GHOST[1], GHOST[2], CORE), speed=2.4, life=(0.3, 0.6))


def fx_gastcursehit(fx, e, col):
    """Sciagura: sfera di gas veloce e grande + sigillo a terra sul colpito."""
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    life = 0.12 + L / 45.0
    fx._shape(kind="gastorb", a=tuple(a), b=tuple(b), col=GHOST[1], life=life, sz=0.22,
              seed=random.randrange(999))
    wait = life * 0.85
    fx._shape(kind="gastsigil", c=tuple(b), r=0.85, rot=random.uniform(0, 3), col=GHOST[1],
              life=0.6, wait=wait)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.42), r=0.42, col=GHOST[2], life=0.14, wait=wait)


def fx_gastsludgewave(fx, e, col):
    """Velenoshock: globo di fango ad arco sul bersaglio, poi una pozzetta."""
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fly = 0.18 + L / 28.0
    fx._shape(kind="gastglob", a=tuple(a), b=tuple(b), fly=1.0, h=0.25 + L * 0.12, sz=0.17,
              col=SLUDGE[1], life=fly)
    fx._shape(kind="gastpuddle", c=tuple(b), r=0.55, n=2, seed=random.randrange(999),
              col=SLUDGE[1], life=0.8, wait=fly)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.35), r=0.32, col=SLUDGE[2], life=0.12, wait=fly)


def fx_gastsludgebomb(fx, e, col):
    """Fangobomba: globo grosso ad arco dal lanciatore al punto, poi pozza che
    ribolle su tutta l'area."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 2.2))
    a = fx.pos_of(e["src"]) if (fx.pos_of is not None and e.get("src") is not None) else None
    fly = 0.0
    if a is not None:
        L = math.hypot(c[0] - a[0], c[1] - a[1])
        fly = 0.2 + L / 22.0
        fx._shape(kind="gastglob", a=tuple(a), b=tuple(c), fly=1.0, h=0.6 + L * 0.15, sz=0.3,
                  col=SLUDGE[1], life=fly)
    fx._shape(kind="gastpuddle", c=tuple(c), r=r * 0.85, n=6, seed=random.randrange(999),
              col=SLUDGE[1], life=1.5, wait=fly)
    fx._shape(kind="flash", c=(c[0], c[1] - 0.3), r=r * 0.4, col=SLUDGE[2], life=0.14, wait=fly)
    for _ in range(7):   # gocce di fango schizzate fuori
        an = random.uniform(0, math.tau)
        d = random.uniform(0.6, 1.0) * r
        end = (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.6)
        fx._shape(kind="gastglob", a=tuple(c), b=end, fly=1.0, h=random.uniform(0.4, 0.8), lift=0.1,
                  sz=random.uniform(0.06, 0.09), col=SLUDGE[1], life=random.uniform(0.3, 0.42), wait=fly)


def fx_gastdreameater(fx, e, col):
    """Mangiasogni: lampo rosa sul dormiente e fili di sogno che tornano a chi
    li mangia (cura)."""
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return
    fx._shape(kind="flash", c=(b[0], b[1] - 0.45), r=0.45, col=PSY[2], life=0.16)
    fx._shape(kind="gastdrain", a=tuple(b), b=tuple(a), n=6, seed=random.randrange(999),
              col=PSY[1], life=1.0)
    fx._shape(kind="twinkle", c=(a[0], a[1] - 0.9), r=0.3, col=PSY[2], life=0.35, wait=0.55)
    _bits(fx, (a[0], a[1] - 0.4), 6, (PSY[1], PSY[2]), speed=1.0, up=1.0)


def fx_gastsneak(fx, e, col):
    """Furtivombra: l'ombra scivola a terra fino all'arrivo."""
    a, b = e.get("a"), e.get("b")
    if a is None or b is None or e.get("kind") != "dash":
        return
    fx._shape(kind="gastshade", a=tuple(a), b=tuple(b), col=GHOST[1], life=0.55)
    _bits(fx, (b[0], b[1] - 0.2), 6, (GHOST[1], CORE), speed=1.2, life=(0.3, 0.5))


def fx_gasthypnosis(fx, e, col):
    """Ipnosi al lancio: anello rosa alla bocca (in volo la spirale la disegna
    world_fx.draw_projectiles)."""
    a = e.get("a")
    if a is None or e.get("kind") != "projectile":
        return
    fx._shape(kind="ring", c=(a[0], a[1] - 0.45), r0=0.15, r1=0.6, col=PSY[1], life=0.25, wd=0.08)


def fx_gasthypnosishit(fx, e, col):
    """Ipnosi a segno: anelli rosa che si chiudono sul colpito e una Z."""
    c = e.get("c")
    if c is None:
        return
    top = (c[0], c[1] - 0.5)
    for k in range(2):
        fx._shape(kind="ring", c=top, r0=1.0 - 0.3 * k, r1=0.15, col=PSY[1 + k], life=0.35,
                  wd=0.07, wait=0.08 * k)
    fx._shape(kind="zzz", c=(c[0] + 0.3, c[1] - 0.9), col=PSY[1], life=0.8, wait=0.2)


def fx_gastnastyplot(fx, e, col):
    """Congiura: occhi rossi che si aprono sopra, alone scuro e granelli che salgono."""
    c = e.get("c")
    if c is None:
        return
    fx._shape(kind="gasteyes", c=tuple(c), h=1.85, col=EYE[1], life=0.75)
    fx._shape(kind="groundring", c=tuple(c), r0=1.1, r1=0.2, cols=(CORE, GHOST[0], GHOST[1]),
              w=0.08, speed=2.2, col=GHOST[1], life=0.45)
    _bits(fx, (c[0], c[1] - 0.2), 12, (CORE, GHOST[0], GHOST[1]), speed=0.7, up=1.4,
          life=(0.5, 0.8))


def fx_gastcurse(fx, e, col):
    """Maledizione lanciata: sigillo a terra sotto il marchiato (il marchio
    durante l'attesa è in draw_unit_overlay)."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    fx._shape(kind="gastsigil", c=tuple(c), r=1.1, rot=random.uniform(0, 3), col=GHOST[1], life=0.7)
    fx._shape(kind="flash", c=(c[0], c[1] - 0.5), r=0.5, col=GHOST[1], life=0.16)


def fx_gastcursepop(fx, e, col):
    """Maledizione che esplode: faccia spettrale che sale, scoppio e scossa."""
    c = e.get("c")
    if c is None:
        return
    r = float(e.get("radius", 1.6))
    fx._shape(kind="impactstar", c=(c[0], c[1] - 0.4), r=0.8, n=8, rot=random.uniform(0, 1),
              cols=(CORE, GHOST[1], GHOST[2]), col=GHOST[1], life=0.25)
    fx._shape(kind="gastface", c=tuple(c), r=0.6, seed=random.randrange(999), col=GHOST[1], life=0.9)
    fx._shape(kind="ring", c=(c[0], c[1] - 0.4), r0=0.2, r1=r * 0.55, col=GHOST[1], life=0.25, wd=0.06)
    _bits(fx, (c[0], c[1] - 0.4), 14, (GHOST[1], GHOST[2], CORE), speed=2.8, life=(0.35, 0.7))
    _shake(fx, 150)


def fx_gastdive(fx, e, col):
    """Spettrotuffo: si tuffa in un portale d'ombra (che resta aperto fino al
    ritorno) ed esce da un altro; al ritorno il portale lo riprende."""
    a, b = e.get("a"), e.get("b")
    if a is None or b is None or e.get("kind") != "blink":
        return
    if e.get("ret"):
        for s in fx.shapes:   # il portale d'origine si richiude
            if s["kind"] == "gastportal" and s.get("hold"):
                s["life"] = min(s["life"], 0.2)
        fx._shape(kind="gastportal", c=tuple(a), r=0.7, col=GHOST[1], life=0.4)
        fx._shape(kind="flash", c=(b[0], b[1] - 0.4), r=0.5, col=GHOST[1], life=0.16)
        _bits(fx, (b[0], b[1] - 0.3), 10, (GHOST[1], GHOST[2], CORE), speed=1.8)
        return
    fx._shape(kind="gastportal", c=tuple(a), r=0.85, hold=1, col=GHOST[1], life=1.6)
    fx._shape(kind="gastportal", c=tuple(b), r=0.75, col=GHOST[1], life=0.5)
    fx._shape(kind="flash", c=(b[0], b[1] - 0.4), r=0.5, col=GHOST[1], life=0.16)
    for pt in (a, b):
        _bits(fx, (pt[0], pt[1] - 0.3), 8, (GHOST[1], GHOST[2], CORE), speed=1.8)


STYLES = {
    "gastorb": fx_gastorb, "gastlick": fx_gastlick,
    "gastshadowball": fx_gastshadowball, "gastshadowballhit": fx_gastshadowballhit,
    "gastcursehit": fx_gastcursehit, "gastsludgewave": fx_gastsludgewave,
    "gastsludgebomb": fx_gastsludgebomb, "gastdreameater": fx_gastdreameater,
    "gastsneak": fx_gastsneak, "gasthypnosis": fx_gasthypnosis,
    "gasthypnosishit": fx_gasthypnosishit, "gastnastyplot": fx_gastnastyplot,
    "gastcurse": fx_gastcurse, "gastcursepop": fx_gastcursepop, "gastdive": fx_gastdive,
}


# --- disegni persistenti ---------------------------------------------------------------

def draw_projectile(surface, camera, pr, now):
    """Palla Ombra e Ipnosi in volo (world_fx.draw_projectiles)."""
    ts = config.TILE_SIZE
    p = pr["pos"]
    gx, gy = camera.world_to_screen(p.x * ts, p.y * ts)
    r = max(4.0, pr.get("radius", 0.6) * ts * 0.62)
    lift = int(0.45 * ts)
    sh = pygame.Rect(0, 0, int(r * 1.6), int(r * 0.55))
    sh.center = (gx, gy + 2)
    pygame.draw.ellipse(surface, (16, 10, 22), sh)
    d = pr.get("dir")
    ang = math.atan2(d.y, d.x) if d is not None else 0.0
    layer = pygame.Surface((int(r * 8), int(r * 8)), pygame.SRCALPHA)
    cx = cy = r * 4
    if pr.get("fx") == "gasthypnosis":
        # globo rosa con la spirale che gira e un anello che pulsa
        pul = 0.5 + 0.5 * math.sin(now * 10)
        pygame.draw.circle(layer, (*PSY[1], 50), (int(cx), int(cy)), int(r * (1.5 + 0.3 * pul)))
        pygame.draw.circle(layer, (*PSY[0], 255), (int(cx), int(cy)), int(r * 1.02))
        pygame.draw.circle(layer, (*PSY[1], 255), (int(cx), int(cy)), int(r * 0.92))
        _spiral(layer, cx, cy, r * 0.82, -now * 7.0, 255, w=1)
        pygame.draw.circle(layer, (*WHITE, 255), (int(cx - r * 0.4), int(cy - r * 0.45)),
                           max(1, int(r * 0.16)))
    else:
        # Palla Ombra: sfera scura nel gas viola con un vortice che gira
        pygame.draw.circle(layer, (*GHOST[1], 55), (int(cx), int(cy)), int(r * 1.7))
        draw_gas_orb(layer, cx, cy, r, ang, 255, ph=now * 18, tail=0.8)
        rect = pygame.Rect(0, 0, int(r * 1.3), int(r * 1.3))
        rect.center = (int(cx + r * 0.06), int(cy + r * 0.06))
        rot = now * 9.0
        for k in range(2):
            a0 = rot + k * math.pi
            pygame.draw.arc(layer, (*GHOST[1], 230), rect, a0, a0 + 1.6, 2)
        pygame.draw.circle(layer, (*GHOST[2], 255), (int(cx - r * 0.42), int(cy - r * 0.42)),
                           max(1, int(r * 0.22)))
    surface.blit(layer, (gx - cx, gy - lift - cy))


# --- sulle unità ---------------------------------------------------------------------------

def _wisp(surface, x, y, s, alpha_k=1.0, now=0.0, ph=0.0):
    """Fiammella d'anima (3-4 px): punta che ondeggia in su, corpo viola, cuore chiaro."""
    sway = int(round(math.sin(now * 8 + ph)))
    pts = [(x - s, y), (x + s, y), (x + sway, y - s * 2.4)]
    k = alpha_k
    out = tuple(int(c * k + 20 * (1 - k)) for c in GHOST[0])
    body = tuple(int(c * k + 20 * (1 - k)) for c in GHOST[1])
    pygame.draw.circle(surface, out, (int(x), int(y)), s + 1)
    pygame.draw.polygon(surface, out, [(px_, py_ - 1) for px_, py_ in pts])
    pygame.draw.circle(surface, body, (int(x), int(y)), s)
    pygame.draw.polygon(surface, body, pts)
    if k > 0.7:
        surface.fill(GHOST[2], pygame.Rect(int(x - 1), int(y - 1), 2, 2))


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    r = int(getattr(u, "radius", 0.5) * ts)
    # Cariche d'anima di Corpofunesto: fiammelle che girano attorno (una ogni 25).
    souls = getattr(u, "soul_charges", 0)
    if souls > 0:
        n = min(4, 1 + (souls - 1) // 25)
        cy = gy - r * 1.0
        for i in range(n):
            an = now * 2.2 + i * math.tau / n
            x = gx + math.cos(an) * r * 1.35
            y = cy + math.sin(an) * r * 0.45
            _wisp(surface, x, y, 2, alpha_k=1.0 if math.sin(an) > -0.2 else 0.6, now=now, ph=i)
    # Maledizione in attesa: sigillo a terra con l'arco del tempo che si chiude
    # e un occhio che fluttua sopra la testa.
    cu = getattr(u, "curse_until", -1.0)
    if cu > now:
        left = max(0.0, min(1.0, (cu - now) / 3.0))
        R = r * 1.3
        lay = pygame.Surface((int(R * 2) + 6, int(R) + 6), pygame.SRCALPHA)
        rect = pygame.Rect(3, 3, int(R * 2), int(R))
        pygame.draw.ellipse(lay, (*CORE, 90), rect)
        pygame.draw.ellipse(lay, (*GHOST[0], 230), rect, 2)
        if left > 0.02:
            pygame.draw.arc(lay, (*GHOST[2], 255), rect, math.pi / 2, math.pi / 2 + math.tau * left, 2)
        surface.blit(lay, (gx - rect.w // 2 - 3, gy - rect.h // 2 - 3))
        blink = left > 0.3 or int(now * 8) % 2 == 0
        ex, ey = gx + r * 0.9, int(gy - r * 2.0 + math.sin(now * 3) * 2)
        if blink:
            pygame.draw.polygon(surface, GHOST[0], [(ex - 5, ey), (ex, ey - 4), (ex + 5, ey), (ex, ey + 4)])
            pygame.draw.polygon(surface, GHOST[2], [(ex - 4, ey), (ex, ey - 3), (ex + 4, ey), (ex, ey + 3)])
            pygame.draw.circle(surface, CORE, (int(ex), ey), 2)
            surface.fill(EYE[1], pygame.Rect(int(ex), ey, 1, 1))
    # Ipnosi: sonnolenza prima che il sonno scatti (spirale rosa sopra la testa).
    arm = getattr(u, "sleep_arm_at", -1.0)
    if arm > now and getattr(u, "sleep_until", -1.0) <= now:
        _spiral(surface, gx - r * 0.8, gy - r * 2.0, 5, -now * 9, 255, w=1)
