"""Grafica della linea Totodile > Croconaw > Feraligatr: effetti istantanei
(handler registrati in FXSystem._FX_STYLES), forme nuove per
FXSystem._draw_shapes (getto d'acqua, bollicine, fauci che si chiudono, occhi
minacciosi, aura di Dragodanza, scia dell'Acquagetto, colonna d'acqua), la
bolla di Idropulsar in volo (world_fx.draw_projectiles) e il disegno sulle
unità (Oltraggio: fiamme rosse che tremolano attorno al corpo).

Pixel art: forme piene a 3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

import config

WATER = ((16, 44, 96), (58, 132, 222), (196, 236, 255))     # contorno, corpo, luce
FOAM = ((70, 120, 170), (178, 222, 248), (255, 255, 255))
JAW = ((40, 14, 26), (150, 46, 66), (232, 110, 120))        # gengiva
TOOTH = ((60, 56, 70), (238, 236, 228), (255, 255, 255))
DARKJ = ((22, 12, 34), (86, 52, 120), (176, 140, 220))      # Sgranocchio (Buio)
ICE = ((30, 70, 110), (150, 214, 245), (240, 252, 255))
SCARE = ((40, 8, 12), (196, 40, 44), (255, 150, 120))       # Visotruce
DRAGON = ((34, 18, 70), (110, 86, 230), (196, 186, 255))    # Dragodanza
RAGE = ((70, 10, 10), (228, 54, 40), (255, 186, 110))       # Oltraggio
STAR = ((120, 90, 20), (250, 220, 80))
SHADE = (8, 18, 30)
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


def _ab(e):
    a, b = e.get("a"), e.get("b")
    if a is None or b is None:
        return None
    return tuple(a), tuple(b)


def _track(s, key="tid"):
    tr = s.get("track")
    if tr is None or s.get(key) is None:
        return None
    try:
        return tr(s[key])
    except Exception:
        return None


# --- mattoni ---------------------------------------------------------------------------

def draw_bubble(surface, x, y, r, alpha):
    """Bolla trasparente: bordo chiaro, velo azzurro, riflesso in alto a sinistra."""
    r = max(1.5, r)
    ir = int(r)
    if ir <= 1:
        surface.fill((*FOAM[1], alpha), pygame.Rect(int(x), int(y), 2, 2))
        return
    pygame.draw.circle(surface, (*WATER[1], alpha // 4), (int(x), int(y)), ir)
    pygame.draw.circle(surface, (*FOAM[1], alpha), (int(x), int(y)), ir, 1)
    hx, hy = int(x - r * 0.4), int(y - r * 0.4)
    surface.fill((*WHITE, alpha), pygame.Rect(hx, hy, max(1, ir // 3), max(1, ir // 3)))


def draw_drop(surface, x, y, s, alpha):
    """Goccia (punta in alto): contorno, corpo, puntino di luce."""
    pts = [(x, y - s * 1.5), (x + s, y), (x, y + s), (x - s, y)]
    pygame.draw.polygon(surface, (*WATER[0], alpha), [(px + (px - x) * 0.3, py + (py - y) * 0.3) for px, py in pts])
    pygame.draw.polygon(surface, (*WATER[1], alpha), pts)
    surface.fill((*WATER[2], alpha), pygame.Rect(int(x - s * 0.4), int(y - s * 0.3), 1, 1))


def _flame(surface, x, y, h, w, alpha, cols, lean=0.0):
    """Lingua di fuoco a goccia: base tonda, punta che sale (e si piega)."""
    pts = [(x - w, y), (x - w * 0.6, y - h * 0.45), (x + lean, y - h), (x + w * 0.6, y - h * 0.45), (x + w, y),
           (x, y + w * 0.5)]
    pygame.draw.polygon(surface, (*cols[0], alpha), [(px + (px - x) * 0.25, py + (py - y + h * 0.4) * 0.12)
                                                      for px, py in pts])
    pygame.draw.polygon(surface, (*cols[1], alpha), pts)
    inner = [(x - w * 0.45, y), (x + lean * 0.6, y - h * 0.62), (x + w * 0.45, y)]
    pygame.draw.polygon(surface, (*cols[2], alpha), inner)


# --- forme -------------------------------------------------------------------------------

SHAPES = ("totojet", "totobubble", "totojaws", "totoeyes", "totoaura", "totowake", "totosplash")
AA_TRAVEL = {}


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    age = s["maxlife"] - s["life"]
    if kind == "totojet":
        # Pistolacqua / Idropompa: getto che parte dalla bocca e corre al
        # bersaglio; bordo che ondeggia, nucleo bianco, goccioline in testa.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        lift = 0.38 * ts
        ay -= lift
        by -= lift
        u = min(1.0, t / 0.6)
        tail = max(0.0, (t - 0.45) / 0.55)
        if tail >= u:
            return
        ang = math.atan2(by - ay, bx - ax)
        px, py = -math.sin(ang), math.cos(ang)
        w = s.get("w", 0.13) * ts
        N = 16
        pts = []
        for i in range(N + 1):
            v = tail + (u - tail) * i / N
            wv = math.sin(v * 18 + age * 30) * w * 0.25
            pts.append((ax + (bx - ax) * v + px * wv, ay + (by - ay) * v + py * wv, v))
        for pas in range(3):
            for i in range(N):
                x0, y0, v0 = pts[i]
                x1, y1, _ = pts[i + 1]
                k = 0.55 + 0.45 * (i / N)   # più spesso verso la testa
                ww = w * k
                if pas == 0:
                    pygame.draw.line(overlay, (*WATER[0], 255), (x0, y0), (x1, y1), int(ww * 2 + 2))
                elif pas == 1:
                    pygame.draw.line(overlay, (*WATER[1], 255), (x0, y0), (x1, y1), max(1, int(ww * 2)))
                else:
                    o = ww * 0.35
                    pygame.draw.line(overlay, (*WATER[2], 255), (x0 - o * 0.5, y0 - o), (x1 - o * 0.5, y1 - o),
                                     max(1, int(ww * 0.5)))
        if u < 1.0:   # testa: goccia tonda + spruzzi
            hx, hy = pts[-1][0], pts[-1][1]
            pygame.draw.circle(overlay, (*WATER[0], 255), (int(hx), int(hy)), int(w * 0.95) + 1)
            pygame.draw.circle(overlay, (*WATER[1], 255), (int(hx), int(hy)), int(w * 0.95))
            pygame.draw.circle(overlay, (*WATER[2], 255), (int(hx - w * 0.4), int(hy - w * 0.4)), max(1, int(w * 0.3)))
            rng = random.Random(int(age * 40))
            for _ in range(3):
                draw_drop(overlay, hx - math.cos(ang) * rng.uniform(0, w * 3) + px * rng.uniform(-w * 2, w * 2),
                          hy - math.sin(ang) * rng.uniform(0, w * 3) + py * rng.uniform(-w * 2, w * 2),
                          max(1.5, w * 0.35), 220)
    elif kind == "totobubble":
        # Bollicina che sale ondeggiando e scoppia.
        cx, cy = S(*s["c"])
        r = s.get("r", 0.1) * ts
        y = cy - s.get("rise", 0.6) * ts * t
        x = cx + math.sin(age * 8 + s.get("seed", 0)) * 0.08 * ts
        if f > 0.15:
            draw_bubble(overlay, x, y, r * (0.8 + 0.2 * t), _al(f, 3.0))
        else:   # scoppio: quattro schizzi
            k = 1.0 - f / 0.15
            for i in range(4):
                an = i * math.pi / 2 + 0.6
                overlay.fill((*FOAM[1], int(255 * (1 - k))),
                             pygame.Rect(int(x + math.cos(an) * r * (0.8 + k)), int(y + math.sin(an) * r * (0.8 + k)), 1, 1))
    elif kind == "totojaws":
        # Fauci: due mascelle a MEZZALUNA (gengiva curva, denti lungo l'arco
        # rivolti verso il centro) che si chiudono di scatto sul colpito.
        p = _track(s)
        cx, cy = S(*(p if p is not None else s["c"]))
        cy -= s.get("lift", 0.4) * ts
        r = s.get("r", 0.3) * ts
        gums = s.get("gums", JAW)
        teeth = s.get("teeth", TOOTH)
        close = min(1.0, t / 0.35)
        close = close * close * (3 - 2 * close)
        gap = (1.0 - close) * r * 0.75
        al = 255 if f > 0.3 else int(255 * f / 0.3)
        n = s.get("n", 5)
        ry = r * 0.62
        for row in (-1, 1):   # -1 = sopra (denti in giù), +1 = sotto (denti in su)
            oy = cy + row * gap
            outer, inner = [], []
            for i in range(11):
                an = math.pi * i / 10            # da sinistra a destra lungo l'arco
                c, sn = -math.cos(an), math.sin(an)
                outer.append((cx + c * r, oy + row * sn * ry))
                inner.append((cx + c * r * 0.8, oy + row * sn * ry * 0.55))
            poly = outer + inner[::-1]
            pygame.draw.polygon(overlay, (*gums[0], al), poly, 0)
            pygame.draw.lines(overlay, (*gums[0], al), True, poly, 3)
            mid = [((ox + ix) / 2, (oy2 + iy) / 2) for (ox, oy2), (ix, iy) in zip(outer, inner)]
            pygame.draw.lines(overlay, (*gums[1], al), False, mid, max(2, int(r * 0.2)))
            hl = mid[2:6] if row < 0 else mid[1:4]   # luce in alto a sinistra
            pygame.draw.lines(overlay, (*gums[2], al), False, [(x, y - 1) for x, y in hl], 1)
            # denti lungo l'arco interno, verso il centro della bocca
            for k in range(n):
                v = (k + (0.5 if row < 0 else 1.0)) / (n + (0.0 if row < 0 else 1.0))
                if not 0.08 < v < 0.92:
                    continue
                an = math.pi * v
                c, sn = -math.cos(an), math.sin(an)
                bx, by = cx + c * r * 0.8, oy + row * sn * ry * 0.55
                L = r * (0.22 + 0.2 * sn)
                tip = (bx - c * L * 0.15, by - row * L)
                hw = r * 0.08 + 1
                tri = [(bx - hw, by), tip, (bx + hw, by)]
                pygame.draw.polygon(overlay, (*teeth[0], al), [(bx - hw - 1, by + row), (tip[0], tip[1] - row),
                                                               (bx + hw + 1, by + row)])
                pygame.draw.polygon(overlay, (*teeth[1], al), tri)
                overlay.fill((*teeth[2], al), pygame.Rect(int(bx - hw * 0.5), int(by - row), 1, 1))
    elif kind == "totoeyes":
        # Visotruce: due occhi cattivi (bianco, pupilla rossa, sopracciglio a V)
        # che si spalancano sopra la testa di chi lancia.
        p = _track(s)
        cx, cy = S(*(p if p is not None else s["c"]))
        cy -= s.get("lift", 1.25) * ts
        op = min(1.0, age / 0.12)
        al = _al(f, 3.0)
        ew, eh = 0.16 * ts, 0.1 * ts * op
        for sg in (-1, 1):
            x = cx + sg * 0.2 * ts
            rect = pygame.Rect(0, 0, int(ew * 2), max(2, int(eh * 2)))
            rect.center = (int(x), int(cy))
            pygame.draw.ellipse(overlay, (*SCARE[0], al), rect.inflate(4, 4))
            pygame.draw.ellipse(overlay, (*WHITE, al), rect)
            if op > 0.5:
                pr = max(1, int(eh * 0.7))
                pygame.draw.circle(overlay, (*SCARE[1], al), (int(x - sg * ew * 0.2), int(cy)), pr)
                pygame.draw.circle(overlay, (*SCARE[0], al), (int(x - sg * ew * 0.2), int(cy)), max(1, pr // 2))
            # sopracciglio inclinato verso il centro (rabbia)
            pygame.draw.line(overlay, (*SCARE[0], al), (x + sg * ew * 1.1, cy - eh - 0.08 * ts),
                             (x - sg * ew * 0.9, cy - eh + 0.02 * ts), max(2, int(0.06 * ts)))
    elif kind == "totoaura":
        # Dragodanza: lingue di fuoco viola-blu che salgono attorno a chi danza.
        p = _track(s)
        cx, cy = S(*(p if p is not None else s["c"]))
        r = s.get("r", 0.5) * ts
        cols = s.get("cols", DRAGON)
        al = _al(f, 3.0)
        n = 7
        for i in range(n):
            an = age * 3.0 + i / n * math.tau
            x = cx + math.cos(an) * r * 1.05
            yb = cy + math.sin(an) * r * 0.4
            ph = (age * 2.4 + i * 0.37) % 1.0
            h = (0.35 + 0.35 * math.sin(ph * math.pi)) * ts
            front = math.sin(an) > 0
            _flame(overlay, x, yb - ph * 0.5 * ts, h, 0.07 * ts, al if front else al // 2, cols,
                   lean=math.sin(age * 9 + i) * 0.06 * ts)
    elif kind == "totowake":
        # Acquagetto: scia d'acqua bassa a V dietro la testa che corre da A a B.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.55)
        L = math.hypot(bx - ax, by - ay)
        if L < 1:
            return
        ux, uy = (bx - ax) / L, (by - ay) / L
        px, py = -uy, ux
        hx, hy = ax + (bx - ax) * u, ay + (by - ay) * u
        al = _al(f, 2.5)
        back = min(L * u, 1.6 * ts)
        for sg in (-1, 1):   # due baffi di schiuma che si aprono all'indietro
            pts = []
            for i in range(9):
                v = i / 8
                d = back * v
                spread = sg * (0.08 + 0.32 * v) * ts
                wob = math.sin(v * 9 + age * 20) * 1.5
                pts.append((hx - ux * d + px * (spread + wob), hy - uy * d + py * (spread + wob) * 0.7))
            pygame.draw.lines(overlay, (*WATER[0], al // 2), False, [(x, y + 1) for x, y in pts], 3)
            pygame.draw.lines(overlay, (*FOAM[1], al), False, pts, 2)
        pygame.draw.ellipse(overlay, (*FOAM[2], al), pygame.Rect(int(hx - 0.18 * ts), int(hy - 0.06 * ts),
                                                                 int(0.36 * ts), int(0.12 * ts)), 1)
    elif kind == "totosplash":
        # Colonna d'acqua: sale (o, con down=True, si richiude verso il basso
        # nel tuffo), cresta di schiuma e gocce che ricadono.
        cx, cy = S(*s["c"])
        H = s.get("h", 1.4) * ts
        W = s.get("w", 0.3) * ts
        if s.get("down"):
            k = max(0.0, 1.0 - t / 0.7)
        else:
            k = min(1.0, t / 0.18) * min(1.0, f * 2.2)
        h = H * k
        al = _al(f, 3.0)
        if h >= 2:
            ab = int(al * 0.7)   # acqua traslucida: lo sprite dietro si intravede
            body = [(cx - W, cy), (cx - W * 0.55, cy - h * 0.5), (cx - W * 0.4, cy - h),
                    (cx + W * 0.4, cy - h), (cx + W * 0.55, cy - h * 0.5), (cx + W, cy)]
            pygame.draw.lines(overlay, (*WATER[0], al), False, body, 2)
            pygame.draw.polygon(overlay, (*WATER[1], ab), body)
            for j in range(3):   # strisce chiare che scorrono verso l'alto
                yy = cy - ((age * 3.5 + j / 3) % 1.0) * h
                xx = cx - W * 0.25 + j * W * 0.22
                pygame.draw.line(overlay, (*WATER[2], al), (xx, yy), (xx, min(cy, yy + h * 0.18)), 1)
            for j in range(4):   # cresta: corona di sbuffi di schiuma
                bx = cx + (j - 1.5) * W * 0.32
                by = cy - h - math.sin(age * 14 + j * 1.7) * W * 0.12 - (W * 0.12 if j in (1, 2) else 0)
                rr = max(2, int(W * (0.24 if j in (1, 2) else 0.18)))
                pygame.draw.circle(overlay, (*WATER[0], al), (int(bx), int(by)), rr + 1)
                pygame.draw.circle(overlay, (*FOAM[1], al), (int(bx), int(by)), rr)
                overlay.fill((*WHITE, al), pygame.Rect(int(bx - rr * 0.4), int(by - rr * 0.4), 1, 1))
        pygame.draw.ellipse(overlay, (*FOAM[1], al), pygame.Rect(int(cx - W * 1.4), int(cy - W * 0.3),
                                                                 int(W * 2.8), int(W * 0.6)), 1)
        rng = random.Random(s.get("seed", 0))
        for i in range(s.get("drops", 6)):   # gocce a parabola dalla cresta
            an = rng.uniform(-1.0, 1.0)
            v = rng.uniform(0.6, 1.4) * W * 3
            x = cx + an * v * t
            y = cy - H * 0.8 * min(1.0, t / 0.18) - v * 1.4 * t + 3.5 * ts * t * t
            if y < cy:
                draw_drop(overlay, x, y, max(1.5, 0.05 * ts), al)


# --- effetti istantanei --------------------------------------------------------------------

def _sh(fx, **kw):
    fx._shape(**kw)


def _bubbles(fx, c, n, wait=0.0, r=(0.06, 0.12), spread=0.35, rise=(0.4, 0.9)):
    for _ in range(n):
        p = (c[0] + random.uniform(-spread, spread), c[1] + random.uniform(-spread, spread) * 0.6)
        _sh(fx, kind="totobubble", c=p, r=random.uniform(*r), rise=random.uniform(*rise),
            seed=random.uniform(0, 6), col=FOAM[1], life=random.uniform(0.4, 0.7),
            wait=wait + random.uniform(0.0, 0.1))


def _spray(fx, c, wait=0.0, n=8):
    """Spruzzo d'arrivo: anello sottile + gocce."""
    _sh(fx, kind="ring", c=c, r0=0.12, r1=0.6, col=FOAM[1], life=0.22, wd=0.05, wait=wait)
    _sh(fx, kind="totosplash", c=(c[0], c[1] + 0.4), h=0.0, w=0.12, drops=n, seed=random.randrange(999),
        col=WATER[1], life=0.45, wait=wait)


def fx_totonip(fx, e, col):
    """Attacco base (in mischia): fauci piccole che si chiudono sul bersaglio."""
    ab = _ab(e)
    if ab is None:
        return
    _, b = ab
    _sh(fx, kind="totojaws", c=b, r=0.27, n=4, lift=0.55, track=fx.pos_of, tid=e.get("tgt"),
        col=TOOTH[1], life=0.38)
    _bits(fx, (b[0], b[1] - 0.4), 3, (WATER[1], FOAM[1]), speed=1.2, life=(0.15, 0.3))


def _jet(fx, e, w, speed, big=False):
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fly = 0.06 + L / speed
    _sh(fx, kind="totojet", a=a, b=b, w=w, col=WATER[1], life=fly / 0.6)
    _bubbles(fx, (a[0], a[1] - 0.35), 2 if not big else 4, r=(0.04, 0.08), spread=0.15)
    if e.get("hit"):
        top = (b[0], b[1] - 0.4)
        _spray(fx, top, wait=fly, n=10 if big else 6)
        if big:
            _sh(fx, kind="ring", c=b, r0=0.3, r1=1.0, col=WATER[1], life=0.3, wd=0.06, wait=fly)
            _shake(fx, 90)


def fx_totowatergun(fx, e, col):
    """Pistolacqua: getto sottile."""
    _jet(fx, e, 0.11, 11.0)


def fx_totohydropump(fx, e, col):
    """Idropompa: getto spesso, spruzzo grande e un colpo di scossa."""
    _jet(fx, e, 0.2, 13.0, big=True)


def fx_totopulse(fx, e, col):
    """Idropulsar al lancio: bollicine alla bocca (la bolla in volo la disegna
    world_fx.draw_projectiles)."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    _bubbles(fx, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 0.3), 4, r=(0.05, 0.09), spread=0.25)


def fx_totopulsehit(fx, e, col):
    """Idropulsar a segno: la bolla scoppia (anello sottile, bollicine, gocce)
    e stelline della confusione sulla testa del colpito."""
    c = e.get("c")
    if c is None:
        return
    c = tuple(c)
    top = (c[0], c[1] - 0.45)
    _sh(fx, kind="ring", c=top, r0=0.2, r1=0.85, col=FOAM[1], life=0.25, wd=0.05)
    _bubbles(fx, top, 6, r=(0.05, 0.11), spread=0.45, rise=(0.3, 0.7))
    _bits(fx, top, 8, (WATER[1], FOAM[1], WHITE), speed=2.0, life=(0.2, 0.4))
    _sh(fx, kind="dizzy", c=(c[0], c[1] - 1.05), r=0.3, cols=((140, 200, 255), WHITE), col=FOAM[1],
        life=0.9, wait=0.05)


def _hit_points(e):
    h = e.get("hits")
    if not h:
        return []
    return [(h[i], h[i + 1]) for i in range(0, len(h) - 1, 2)]


def _bite(fx, e, r, gums, teeth=TOOTH, n=5, extra=None):
    if e.get("kind") != "cone":
        return
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    pts = _hit_points(e)
    if not pts:   # a vuoto: il morso schiocca davanti
        rng = float(e.get("range", 2.3)) * 0.6
        L = math.hypot(d[0], d[1]) or 1.0
        pts = [(o[0] + d[0] / L * rng, o[1] + d[1] / L * rng)]
        hit = False
    else:
        hit = True
    for p in pts:
        _sh(fx, kind="totojaws", c=p, r=r, n=n, gums=gums, teeth=teeth, lift=0.45,
            col=teeth[1], life=0.34)
        if hit:
            _sh(fx, kind="impactstar", c=(p[0], p[1] - 0.45), r=0.2, n=6, rot=random.uniform(0, 1),
                cols=(gums[0], teeth[1], WHITE), col=teeth[1], life=0.16, wait=0.12)
            if extra:
                extra(p)


def fx_totobite(fx, e, col):
    """Morso: fauci con la gengiva rossa su ogni colpito."""
    _bite(fx, e, 0.3, JAW)


def fx_totocrunch(fx, e, col):
    """Sgranocchio: fauci più grandi e scure (Buio) + schegge viola."""
    def extra(p):
        _bits(fx, (p[0], p[1] - 0.45), 6, (DARKJ[1], DARKJ[2]), speed=1.8, life=(0.2, 0.35))
    _bite(fx, e, 0.38, DARKJ, n=6, extra=extra)


def fx_totoicefang(fx, e, col):
    """Gelodenti: le zanne di ghiaccio di Swinub su ogni colpito + brina."""
    if e.get("kind") != "cone":
        return
    pts = _hit_points(e)
    if not pts:
        o, d = e.get("o"), e.get("dir")
        if o is None or d is None:
            return
        L = math.hypot(d[0], d[1]) or 1.0
        rng = float(e.get("range", 2.6)) * 0.6
        pts = [(o[0] + d[0] / L * rng, o[1] + d[1] / L * rng)]
    for p in pts:
        top = (p[0], p[1] - 0.45)
        _sh(fx, kind="icefangs", c=top, col=ICE[1], life=0.4)
        if e.get("hits"):
            _bits(fx, top, 7, (ICE[1], ICE[2], WHITE), speed=1.6, life=(0.25, 0.45))


def fx_totoscary(fx, e, col):
    """Visotruce: occhi cattivi sopra la testa + onde rosse nel cono."""
    if e.get("kind") != "cone":
        return
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return
    ang = math.atan2(d[1], d[0])
    _sh(fx, kind="incinroar", o=o, ang=ang, half=math.radians(e.get("angle", 60)) * 0.55,
        rng=e.get("range", 4.2) * 0.5, cols=SCARE, col=SCARE[1], life=0.45)
    _sh(fx, kind="totoeyes", c=o, track=fx.pos_of, tid=e.get("src"), col=SCARE[1], life=0.7)
    for p in _hit_points(e):   # sul colpito: goccia di sudore freddo
        _bits(fx, (p[0], p[1] - 0.9), 2, (FOAM[1],), speed=0.6, life=(0.3, 0.5), up=-0.2)


def fx_totodragondance(fx, e, col):
    """Dragodanza: fiamme viola-blu che girano e salgono attorno a chi danza."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    c = tuple(c)
    _sh(fx, kind="totoaura", c=c, r=0.55, track=fx.pos_of, tid=e.get("src"), col=DRAGON[1], life=1.4)
    _sh(fx, kind="ring", c=c, r0=0.2, r1=1.1, col=DRAGON[2], life=0.3, wd=0.05)
    _bits(fx, (c[0], c[1] - 0.5), 8, (DRAGON[1], DRAGON[2]), speed=1.2, life=(0.4, 0.7), up=1.4)


def fx_totoaquajet(fx, e, col):
    """Acquagetto: scia d'acqua a V lungo lo scatto, gocce; spruzzo se a segno."""
    if e.get("kind") != "dash":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    _sh(fx, kind="totowake", a=a, b=b, col=FOAM[1], life=0.45)
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    for i in range(max(2, int(L * 1.2))):
        u = random.uniform(0.1, 1.0)
        p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u - 0.15)
        _bits(fx, p, 2, (WATER[1], FOAM[1]), speed=0.9, life=(0.2, 0.35))
    if e.get("hit"):
        _spray(fx, (b[0], b[1] - 0.4), wait=0.12, n=8)


def fx_totodig(fx, e, col):
    """Sub (R): tuffo = colonna che si richiude verso il basso + anelli;
    riemersione = geyser alto, gocce, anelli sottili e scossa."""
    kind = e.get("kind")
    c = e.get("c")
    if c is None:
        return
    c = tuple(c)
    if kind == "dive":
        _sh(fx, kind="totosplash", c=c, h=0.8, w=0.24, down=True, drops=6, seed=random.randrange(999),
            col=WATER[1], life=0.5)
        _sh(fx, kind="ring", c=c, r0=0.2, r1=1.0, col=FOAM[1], life=0.35, wd=0.05)
        _sh(fx, kind="ring", c=c, r0=0.1, r1=0.6, col=WATER[1], life=0.3, wd=0.04, wait=0.1)
        return
    if kind != "area":
        return
    r = float(e.get("radius", 2.3))
    _sh(fx, kind="totosplash", c=c, h=1.6, w=0.3, drops=12, seed=random.randrange(999),
        col=WATER[1], life=0.7)
    _sh(fx, kind="ring", c=c, r0=0.4, r1=r, col=FOAM[1], life=0.4, wd=0.06)
    _sh(fx, kind="ring", c=c, r0=0.2, r1=r * 0.6, col=WATER[1], life=0.32, wd=0.05, wait=0.08)
    for _ in range(6):
        an = random.uniform(0, math.tau)
        d = random.uniform(0.5, r * 0.9)
        _bubbles(fx, (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.6), 1, wait=0.1)
    _shake(fx, 160)


def fx_totooutrage(fx, e, col):
    """Oltraggio: esplosione di rabbia rossa (poi l'overlay sull'unità per la
    durata)."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    c = tuple(c)
    top = (c[0], c[1] - 0.5)
    _sh(fx, kind="impactstar", c=top, r=0.4, n=8, rot=random.uniform(0, 1), cols=RAGE, col=RAGE[1], life=0.18)
    _sh(fx, kind="ring", c=c, r0=0.3, r1=1.4, col=RAGE[1], life=0.32, wd=0.06)
    _bits(fx, top, 10, (RAGE[1], RAGE[2]), speed=2.2, life=(0.3, 0.5))
    _shake(fx, 120)


STYLES = {
    "totonip": fx_totonip, "totowatergun": fx_totowatergun, "totohydropump": fx_totohydropump,
    "totopulse": fx_totopulse, "totopulsehit": fx_totopulsehit, "totobite": fx_totobite,
    "totocrunch": fx_totocrunch, "totoicefang": fx_totoicefang, "totoscary": fx_totoscary,
    "totodragondance": fx_totodragondance, "totoaquajet": fx_totoaquajet, "totodig": fx_totodig,
    "totooutrage": fx_totooutrage,
}


# --- Idropulsar in volo ----------------------------------------------------------------------

def draw_projectile(surface, camera, pr, now):
    """Bolla di Idropulsar in volo (world_fx.draw_projectiles): grossa bolla
    trasparente che ondeggia, riflesso, bollicine dietro e ombra a terra."""
    ts = config.TILE_SIZE
    p = pr["pos"]
    gx, gy = camera.world_to_screen(p.x * ts, p.y * ts)
    r = max(4.0, pr.get("radius", 0.7) * ts * 0.6)
    lift = int(0.45 * ts)
    sh = pygame.Rect(0, 0, int(r * 1.6), int(r * 0.5))
    sh.center = (gx, gy + 2)
    pygame.draw.ellipse(surface, SHADE, sh)
    d = pr.get("dir")
    dx, dy = (d.x, d.y) if d is not None else (1.0, 0.0)
    layer = pygame.Surface((int(r * 8), int(r * 8)), pygame.SRCALPHA)
    cx = cy = r * 4
    for k in range(1, 4):   # bollicine dietro
        bx = cx - dx * r * (1.1 + 0.55 * k) + math.sin(now * 9 + k) * 2
        by = cy - dy * r * (1.1 + 0.55 * k) + math.cos(now * 7 + k) * 2
        draw_bubble(layer, bx, by, r * (0.32 - 0.07 * k), 220)
    wob = math.sin(now * 14)
    rect = pygame.Rect(0, 0, int(r * 2 * (1 + 0.08 * wob)), int(r * 2 * (1 - 0.08 * wob)))
    rect.center = (int(cx), int(cy))
    pygame.draw.ellipse(layer, (*WATER[1], 90), rect)
    pygame.draw.ellipse(layer, (*WATER[0], 255), rect.inflate(2, 2), 2)
    pygame.draw.ellipse(layer, (*FOAM[1], 255), rect, 1)
    inner = rect.inflate(-int(r * 0.7), -int(r * 0.7))
    pygame.draw.arc(layer, (*FOAM[1], 200), inner, math.pi * 1.1, math.pi * 1.6, 1)
    pygame.draw.circle(layer, (*WHITE, 255), (int(cx - r * 0.4), int(cy - r * 0.45)), max(1, int(r * 0.2)))
    layer.fill((*WHITE, 255), pygame.Rect(int(cx + r * 0.35), int(cy + r * 0.3), 2, 2))
    surface.blit(layer, (gx - cx, gy - lift - cy))


# --- sulle unità ---------------------------------------------------------------------------

def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Oltraggio: fiamme rosse che tremolano attorno al corpo e sbuffi di
    vapore dalla testa finché dura la furia; visibile a tutti."""
    if getattr(u, "rampage_until", -1.0) <= now or getattr(u, "dex", 0) not in (158, 159, 160):
        return
    r = getattr(u, "radius", 0.5) * ts
    left = getattr(u, "rampage_until", now) - now
    k = min(1.0, left / 0.4)
    al = int(170 * k)
    for i in range(5):
        an = i / 5 * math.tau + now * 1.5
        x = gx + math.cos(an) * r * 0.95
        yb = gy + math.sin(an) * r * 0.3 - 2
        fl = 0.5 + 0.5 * math.sin(now * 17 + i * 2.1)
        h = r * (0.4 + 0.3 * fl)
        front = math.sin(an) > 0
        _flame(surface, x, yb, h, max(2.0, r * 0.11), al if front else al // 2, RAGE,
               lean=math.sin(now * 11 + i) * r * 0.12)
    for j in range(2):   # vapore che sale dalla testa
        ph = (now * 1.2 + j * 0.5) % 1.0
        x = gx + (j - 0.5) * r * 0.6 + math.sin(now * 3 + j) * 2
        y = gy - r * 1.7 - ph * r * 0.9
        rr = max(2, int(r * (0.12 + 0.18 * ph)))
        pygame.draw.circle(surface, (226, 214, 214, int(150 * (1 - ph) * k)) if surface.get_flags() & pygame.SRCALPHA
                           else (226, 214, 214), (int(x), int(y)), rr)
