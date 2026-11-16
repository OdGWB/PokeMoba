"""Grafica della linea Rowlet > Dartrix > Decidueye: effetti istantanei (handler
registrati in FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes
(freccia piumata, foglia che rotea, lama di foglia, piuma che cade, freccia
d'ombra di Cucitombra col filo che lega il colpito, fantasmino di Sgomento,
fascio di luce di Sintesi, mirino e frecce della Pioggia di Frecce) e i disegni
sulle unità (spavento, Att. ridotto da Danzadipiume, Granvoce).

Pixel art: forme piene a 3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

LEAF = ((20, 50, 24), (88, 170, 70), (196, 236, 132))       # contorno, corpo, luce
WOOD = ((48, 30, 18), (138, 96, 54), (204, 160, 102))       # asta della freccia
GHOST = ((34, 16, 58), (124, 80, 196), (212, 182, 255))     # Decidueye, Cucitombra
SHADE = (18, 10, 30)
FEATHER = ((78, 62, 44), (226, 212, 178), (255, 250, 230))  # piume color crema
SUN = ((128, 86, 22), (250, 214, 100), (255, 248, 204))     # Sintesi
GOLD = ((96, 64, 10), (238, 192, 66), (255, 242, 172))      # colpo furtivo (Distacco)
SOUND = ((70, 40, 20), (238, 150, 70), (255, 222, 170))     # Granvoce
FEAR = ((40, 16, 60), (170, 120, 240), (240, 226, 255))
WHITE = (255, 255, 255)

# palette della freccia: (punta, impennaggio)
_ARROW_PAL = {
    "leaf": (LEAF, LEAF),
    "ghost": (GHOST, GHOST),
    "sneak": (GOLD, LEAF),
    "dark": (GHOST, ((20, 10, 34), (70, 40, 120), (150, 110, 220))),
}


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


def _ghostly(e):
    """Decidueye (Erba/Spettro) scocca frecce d'ombra; Rowlet e Dartrix di foglia."""
    return e.get("mtype") == "Ghost"


# --- mattoni ---------------------------------------------------------------------------

def draw_arrow(surface, x, y, ang, L, alpha, pal="leaf", w=1):
    """Freccia piumata con la punta (x, y): asta di legno, punta a foglia,
    impennaggio a V in coda. L = lunghezza in px, w = spessore dell'asta."""
    head, fl = _ARROW_PAL.get(pal, _ARROW_PAL["leaf"])
    ca, sa = math.cos(ang), math.sin(ang)
    px, py = -sa, ca
    tx, ty = x - ca * L, y - sa * L
    # asta: contorno + legno + filo di luce sul lato in alto
    pygame.draw.line(surface, (*WOOD[0], alpha), (tx, ty), (x, y), w + 2)
    pygame.draw.line(surface, (*WOOD[1], alpha), (tx, ty), (x, y), w)
    # impennaggio: due alette a V in coda
    fw = max(2.0, L * 0.16)
    for k in (0.0, 0.16):
        bx, by = tx + ca * L * k, ty + sa * L * k
        for sg in (-1, 1):
            pts = [(bx + ca * fw * 1.4, by + sa * fw * 1.4), (bx - ca * fw * 0.2 + px * fw * sg,
                   by - sa * fw * 0.2 + py * fw * sg), (bx, by)]
            pygame.draw.polygon(surface, (*fl[0], alpha), pts)
            inner = [(bx + ca * fw * 1.1, by + sa * fw * 1.1),
                     (bx + px * fw * 0.65 * sg, by + py * fw * 0.65 * sg), (bx + ca * fw * 0.2, by + sa * fw * 0.2)]
            pygame.draw.polygon(surface, (*(fl[1] if sg < 0 else fl[2]), alpha), inner)
    # punta a foglia
    h = max(3.0, L * 0.26)
    hw = h * 0.42
    pts = [(x + ca * h * 0.55, y + sa * h * 0.55), (x - ca * h * 0.2 + px * hw, y - sa * h * 0.2 + py * hw),
           (x - ca * h * 0.55, y - sa * h * 0.55), (x - ca * h * 0.2 - px * hw, y - sa * h * 0.2 - py * hw)]
    out = [(x + (qx - x) * 1.35, y + (qy - y) * 1.35) for qx, qy in pts]
    pygame.draw.polygon(surface, (*head[0], alpha), out)
    pygame.draw.polygon(surface, (*head[1], alpha), pts)
    pygame.draw.line(surface, (*head[2], alpha), (x - ca * h * 0.35, y - sa * h * 0.35),
                     (x + ca * h * 0.3, y + sa * h * 0.3), 1)


def draw_leaf(surface, x, y, ang, s, alpha, cols=LEAF, thin=1.0):
    """Foglia appuntita ai due capi (rombo curvo), nervatura chiara."""
    ca, sa = math.cos(ang), math.sin(ang)
    px, py = -sa, ca
    pts = []
    for i in range(9):
        u = i / 8
        an = u * math.pi
        d = math.cos(an) * s
        wv = math.sin(an) * s * 0.42 * thin
        pts.append((x + ca * d + px * wv, y + sa * d + py * wv))
    for i in range(1, 8):
        u = i / 8
        an = math.pi + u * math.pi
        d = math.cos(an) * s
        wv = math.sin(an) * s * 0.42 * thin
        pts.append((x + ca * d + px * wv, y + sa * d + py * wv))
    out = [(x + (qx - x) * 1.25 + 0.4, y + (qy - y) * 1.25 + 0.4) for qx, qy in pts]
    pygame.draw.polygon(surface, (*cols[0], alpha), out)
    pygame.draw.polygon(surface, (*cols[1], alpha), pts)
    pygame.draw.line(surface, (*cols[2], alpha), (x - ca * s * 0.8, y - sa * s * 0.8),
                     (x + ca * s * 0.8, y + sa * s * 0.8), 1)


def draw_feather(surface, x, y, ang, s, alpha, cols=FEATHER):
    """Piuma: rachide scuro e vessillo a goccia, luce sul lato sinistro."""
    ca, sa = math.cos(ang), math.sin(ang)
    px, py = -sa, ca
    pts = []
    for i in range(11):
        u = i / 10
        d = (u - 0.5) * 2 * s
        wv = math.sin(u * math.pi) ** 0.8 * s * 0.38 * (1.0 - 0.3 * u)
        pts.append((x + ca * d + px * wv, y + sa * d + py * wv))
    for i in range(10, -1, -1):
        u = i / 10
        d = (u - 0.5) * 2 * s
        wv = math.sin(u * math.pi) ** 0.8 * s * 0.38 * (1.0 - 0.3 * u)
        pts.append((x + ca * d - px * wv, y + sa * d - py * wv))
    out = [(x + (qx - x) * 1.22, y + (qy - y) * 1.22) for qx, qy in pts]
    pygame.draw.polygon(surface, (*cols[0], alpha), out)
    pygame.draw.polygon(surface, (*cols[1], alpha), pts)
    hx, hy = x - px * s * 0.15, y - py * s * 0.15
    pygame.draw.line(surface, (*cols[2], alpha), (hx - ca * s * 0.6, hy - sa * s * 0.6),
                     (hx + ca * s * 0.3, hy + sa * s * 0.3), 1)
    pygame.draw.line(surface, (*cols[0], alpha), (x - ca * s * 1.25, y - sa * s * 1.25),
                     (x + ca * s * 0.9, y + sa * s * 0.9), 1)


def _boo(surface, x, y, s, alpha, ph=0.0):
    """Fantasmino a lenzuolo con occhi e bocca spalancata (Sgomento)."""
    pts = []
    for i in range(13):   # testa tonda
        an = math.pi + i / 12 * math.pi
        pts.append((x + math.cos(an) * s, y + math.sin(an) * s))
    for i in range(7):    # orlo ondulato in basso
        u = i / 6
        pts.append((x + s - u * 2 * s, y + s * (1.05 + 0.25 * math.sin(u * 3 * math.tau + ph))))
    out = [(x + (qx - x) * 1.15, y + (qy - y) * 1.12 + 0.5) for qx, qy in pts]
    pygame.draw.polygon(surface, (*FEAR[0], alpha), out)
    pygame.draw.polygon(surface, (*FEAR[2], alpha), pts)
    pygame.draw.polygon(surface, (*FEAR[1], alpha), [(x + (qx - x) * 0.9 + s * 0.12, y + (qy - y) * 0.9 + s * 0.1)
                                                      for qx, qy in pts[13:]] + [(x + s * 0.9, y + s * 0.2)])
    for sg in (-1, 1):
        pygame.draw.ellipse(surface, (*SHADE, alpha),
                            pygame.Rect(int(x + sg * s * 0.38 - s * 0.16), int(y - s * 0.35), max(2, int(s * 0.32)),
                                        max(3, int(s * 0.5))))
    pygame.draw.ellipse(surface, (*SHADE, alpha),
                        pygame.Rect(int(x - s * 0.22), int(y + s * 0.25), max(2, int(s * 0.44)), max(3, int(s * 0.5))))


# --- forme -------------------------------------------------------------------------------

SHAPES = ("owlarrow", "owlleaf", "owlblade", "owlfeather", "owlstitch", "owlboo",
          "owlsun", "owlrainmark", "owlfall", "owldrain")
AA_TRAVEL = {"owlarrow": 0.85}


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    age = s["maxlife"] - s["life"]
    if kind == "owlarrow":
        # Freccia da A a B: la punta arriva a 0,85 della vita, con una scia sottile.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        if u >= 1.0:
            return
        lift = s.get("lift", 0.4) * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        ang = math.atan2(by - ay, bx - ax)
        al = 255 if "hom" in s else _al(f, 4.0)
        L = s.get("sz", 0.62) * ts
        tr = min(L * 1.6, math.hypot(x - ax, y - ay + lift))
        if tr > 2:   # scia d'aria: filo chiaro che svanisce
            ca, sa = math.cos(ang), math.sin(ang)
            col = _ARROW_PAL.get(s.get("pal", "leaf"))[0][2]
            pygame.draw.line(overlay, (*col, al // 3), (x - ca * (L + tr), y - sa * (L + tr)),
                             (x - ca * L, y - sa * L), 1)
        draw_arrow(overlay, x, y, ang, L, al, s.get("pal", "leaf"), w=s.get("w", 1))
    elif kind == "owlleaf":
        # Fogliame: foglia che rotea in volo con un leggero serpeggio.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        if u >= 1.0:
            return
        ang = math.atan2(by - ay, bx - ax)
        wob = math.sin(u * math.pi * 2 + s.get("seed", 0)) * 0.18 * ts * math.sin(u * math.pi)
        x = ax + (bx - ax) * u - math.sin(ang) * wob
        y = ay + (by - ay) * u + math.cos(ang) * wob - 0.4 * ts
        for k in (2, 1):   # due foglie fantasma dietro
            uu = max(0.0, u - 0.06 * k)
            gx = ax + (bx - ax) * uu
            gy = ay + (by - ay) * uu - 0.4 * ts
            draw_leaf(overlay, gx, gy, age * 16 - k * 0.6, s.get("sz", 0.22) * ts * 0.8, 70 // k)
        draw_leaf(overlay, x, y, age * 16, s.get("sz", 0.22) * ts, _al(f, 5.0))
    elif kind == "owlblade":
        # Foglielama: lama di foglia sottile e lunga lungo la direzione + fendente.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.8)
        ang = math.atan2(by - ay, bx - ax)
        ca, sa = math.cos(ang), math.sin(ang)
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - 0.4 * ts
        al = _al(f, 4.0)
        tl = min(0.9 * ts, math.hypot(bx - ax, by - ay) * u)
        if tl > 2:   # scia verde chiara affusolata
            for i in range(4):
                k = i / 4
                pygame.draw.line(overlay, (*LEAF[2 if i < 2 else 1], int(al * (0.5 - 0.1 * i))),
                                 (x - ca * tl * k, y - sa * tl * k), (x - ca * tl * (k + 0.25), y - sa * tl * (k + 0.25)),
                                 max(1, 3 - i))
        if u < 1.0:
            draw_leaf(overlay, x, y, ang, s.get("sz", 0.3) * ts, al, thin=0.45)
    elif kind == "owlfeather":
        # Piuma che cade dondolando (Danzadipiume, Retromarcia).
        c = S(*s["c"])
        fall = s.get("fall", 0.8) * ts
        sw = math.sin(age * s.get("fq", 5.0) + s.get("seed", 0))
        x = c[0] + sw * 0.22 * ts + s.get("dx", 0.0) * ts * t
        y = c[1] - s.get("h", 1.0) * ts + fall * t
        draw_feather(overlay, x, y, math.pi * 0.5 + sw * 0.7, s.get("sz", 0.16) * ts, _al(f, 3.0))
    elif kind == "owlstitch":
        # Cucitombra: freccia d'ombra piantata nell'ombra del colpito e un filo
        # d'ombra cucito che lo lega mentre resta inchiodato (niente scatti).
        cx, cy = S(*s["c"])
        p = None
        tr = s.get("track")
        if tr is not None:
            try:
                p = tr(s["tid"])
            except Exception:
                p = None
        if p is None:
            p = s["c"]
        ux, uy = S(*p)
        al = _al(f, 6.0)
        pin = min(1.0, age / 0.12)
        # ombra della freccia piantata (in diagonale, dall'alto a sinistra)
        ang = math.radians(62)
        L = 0.8 * ts
        hx, hy = cx, cy
        sx, sy = hx - math.cos(ang) * L * pin, hy - math.sin(ang) * L * pin
        # filo cucito: punti alterni chiari e scuri lungo una curva che pende
        n = 12
        for i in range(n):
            u0, u1 = i / n, (i + 1) / n
            sag = 0.25 * ts
            x0 = cx + (ux - cx) * u0
            y0 = cy + (uy - cy) * u0 + math.sin(u0 * math.pi) * sag - 0.05 * ts
            x1 = cx + (ux - cx) * u1
            y1 = cy + (uy - cy) * u1 + math.sin(u1 * math.pi) * sag - 0.05 * ts
            pygame.draw.line(overlay, (*SHADE, al), (x0, y0), (x1, y1), 3)
            if i % 2 == 0:
                pygame.draw.line(overlay, (*GHOST[1 + (int(age * 6 + i) % 2)], al), (x0, y0), (x1, y1), 1)
        # anello d'ombra a terra sotto il legato
        R = 0.5 * ts
        rect = pygame.Rect(0, 0, int(R * 2), int(R))
        rect.center = (int(ux), int(uy + 0.05 * ts))
        pygame.draw.ellipse(overlay, (*SHADE, al // 2), rect)
        pygame.draw.ellipse(overlay, (*GHOST[1], al), rect, 1)
        draw_arrow(overlay, hx, hy, ang, L * pin, al, "dark", w=2)
        pygame.draw.ellipse(overlay, (*SHADE, al), pygame.Rect(int(hx - 4), int(hy - 1), 9, 4))
    elif kind == "owlboo":
        # Sgomento: fantasmino che spunta dietro al colpito, si gonfia e svanisce.
        c = S(*s["c"])
        pop = min(1.0, age / 0.12)
        sc = (0.6 + 0.4 * pop) * s.get("r", 0.2) * ts
        y = c[1] - 1.55 * ts - age * 0.5 * ts
        _boo(overlay, c[0] - 0.55 * ts + math.sin(age * 9) * 2, y, sc, _al(f, 3.0), ph=age * 8)
    elif kind == "owlsun":
        # Sintesi: fascio di luce dall'alto sul lanciatore, foglioline che salgono.
        c = S(*s["c"])
        R = s.get("r", 0.7) * ts
        H = 2.6 * ts
        al = int(_al(f, 3.0) * min(1.0, age / 0.15))
        lay = pygame.Surface((int(R * 3), int(H + R)), pygame.SRCALPHA)
        w = lay.get_width()
        for i, (k, aa) in enumerate(((1.0, 40), (0.7, 55), (0.38, 80))):
            half = R * k
            pygame.draw.polygon(lay, (*SUN[1 if i < 2 else 2], aa),
                                [(w / 2 - half * 0.55, 0), (w / 2 + half * 0.55, 0),
                                 (w / 2 + half, H), (w / 2 - half, H)])
        rect = pygame.Rect(0, 0, int(R * 2), int(R * 0.8))
        rect.center = (w // 2, int(H))
        pygame.draw.ellipse(lay, (*SUN[2], 90), rect)
        lay.set_alpha(al)
        overlay.blit(lay, (c[0] - w // 2, c[1] - H))
        for i in range(5):
            u = (age * 0.8 + i / 5) % 1.0
            lx = c[0] + math.sin(i * 2.3 + age * 3) * R * 0.7
            ly = c[1] - u * H * 0.8
            draw_leaf(overlay, lx, ly, age * 5 + i, 0.12 * ts, int(al * (1.0 - u)))
    elif kind == "owlrainmark":
        # Pioggia di Frecce: mirino a terra (ellisse tratteggiata che gira e si
        # riempie durante il ritardo), poi resta il bordo mentre piove.
        cx, cy = S(*s["c"])
        R = s["r"] * ts
        delay = s.get("delay", 1.0)
        al = _al(f, 6.0)
        fill = min(1.0, age / max(0.05, delay))
        lay = pygame.Surface((int(R * 2) + 8, int(R * 1.2) + 8), pygame.SRCALPHA)
        rect = pygame.Rect(4, 4, int(R * 2), int(R * 1.2))
        pygame.draw.ellipse(lay, (*LEAF[0], int(70 * fill)), rect)
        if fill < 1.0:
            inner = rect.inflate(-int(rect.w * (1 - fill)), -int(rect.h * (1 - fill)))
            pygame.draw.ellipse(lay, (*LEAF[1], 60), inner, 2)
        rot = age * 1.2
        n = max(12, int(R * 0.35))
        for i in range(n):
            if i % 2:
                continue
            a0 = rot + i / n * math.tau
            a1 = a0 + math.tau / n
            p0 = (rect.centerx + math.cos(a0) * rect.w / 2, rect.centery + math.sin(a0) * rect.h / 2)
            p1 = (rect.centerx + math.cos(a1) * rect.w / 2, rect.centery + math.sin(a1) * rect.h / 2)
            pygame.draw.line(lay, (*LEAF[0], 220), p0, p1, 3)
            pygame.draw.line(lay, (*LEAF[2], 220), p0, p1, 1)
        # croce di mira al centro
        cxl, cyl = rect.center
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pygame.draw.line(lay, (*LEAF[2], 200), (cxl + dx * 4, cyl + dy * 3), (cxl + dx * 9, cyl + dy * 6), 1)
        lay.set_alpha(al)
        overlay.blit(lay, (cx - rect.centerx, cy - rect.centery))
    elif kind == "owlfall":
        # Freccia che piove dall'alto (in diagonale, dall'alto a sinistra), si
        # pianta a terra con due granelli e resta un attimo.
        cx, cy = S(*s["c"])
        ang = math.radians(s.get("ang", 70))
        drop = s.get("drop", 0.35)
        L = s.get("sz", 0.55) * ts
        ca, sa = math.cos(ang), math.sin(ang)
        if age < drop:
            u = age / drop
            H = 4.0 * ts * (1.0 - u)
            x, y = cx - ca * H, cy - sa * H
            pygame.draw.line(overlay, (*LEAF[2], 90), (x - ca * L * 2.2, y - sa * L * 2.2), (x - ca * L, y - sa * L), 1)
            draw_arrow(overlay, x, y, ang, L, 255, s.get("pal", "leaf"))
        else:
            al = _al(f, 3.0)
            dep = L * 0.25   # la punta è affondata
            pygame.draw.ellipse(overlay, (*SHADE, al // 2),
                                pygame.Rect(int(cx - 3), int(cy - 1), 8, 3))
            draw_arrow(overlay, cx - ca * dep, cy - sa * dep, ang, L * 0.75, al, s.get("pal", "leaf"))
            if age - drop < 0.12:
                k = (age - drop) / 0.12
                for sg in (-1, 1):
                    overlay.fill((*WOOD[2], int(255 * (1 - k))),
                                 pygame.Rect(int(cx + sg * (2 + 4 * k)), int(cy - 3 * k), 1, 1))
    elif kind == "owldrain":
        # Gigassorbimento: granelli verdi che serpeggiano dal colpito a chi lancia.
        p0 = S(*s["a"])
        p1 = S(*s["b"])
        tr = s.get("track")
        if tr is not None and s.get("sid") is not None:
            try:
                q = tr(s["sid"])
            except Exception:
                q = None
            if q is not None:
                p1 = S(*q)
        rng = random.Random(s.get("seed", 0))
        for i in range(s.get("n", 8)):
            off = rng.uniform(0, 0.5)
            u = (t * 1.4 - off)
            if u <= 0 or u >= 1:
                continue
            e = u * u * (3 - 2 * u)
            wig = math.sin(u * math.pi * 2 + i) * 0.35 * ts * math.sin(u * math.pi)
            ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
            x = p0[0] + (p1[0] - p0[0]) * e - math.sin(ang) * wig
            y = p0[1] + (p1[1] - p0[1]) * e + math.cos(ang) * wig - 0.45 * ts
            r = 3 if i % 3 == 0 else 2
            pygame.draw.circle(overlay, LEAF[0], (int(x), int(y)), r + 1)
            pygame.draw.circle(overlay, LEAF[1 if i % 2 else 2], (int(x), int(y)), r)
            if r == 3:
                overlay.fill(WHITE, pygame.Rect(int(x - 1), int(y - 1), 1, 1))


# --- effetti istantanei --------------------------------------------------------------------

def _arrow_shot(fx, a, b, pal, sz=0.62, speed=34.0, w=1, lift=0.4):
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    life = (0.08 + L / speed) / 0.85
    fx._shape(kind="owlarrow", a=a, b=b, pal=pal, sz=sz, w=w, lift=lift, col=LEAF[1], life=life)
    return life * 0.85


def _hit_leaf(fx, b, wait, cols=LEAF, n=6):
    top = (b[0], b[1] - 0.4)
    fx._shape(kind="impactstar", c=top, r=0.45, n=6, rot=random.uniform(0, 1),
              cols=cols, col=cols[1], life=0.2, wait=wait)
    for _ in range(n):   # foglioline/schegge che volano via
        an = random.uniform(0, math.tau)
        d = random.uniform(0.4, 0.8)
        fx._shape(kind="owlleaf", a=top, b=(top[0] + math.cos(an) * d, top[1] + math.sin(an) * d * 0.6 + 0.4),
                  sz=0.1, seed=random.uniform(0, 6), col=cols[1], life=random.uniform(0.3, 0.45), wait=wait)


def fx_owlarrow(fx, e, col):
    """Attacco base: freccia piumata (d'ombra per Decidueye, dorata per il
    colpo furtivo di Distacco) che insegue il bersaglio."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    pal = "sneak" if e.get("sneak") else ("ghost" if _ghostly(e) else "leaf")
    _arrow_shot(fx, a, b, pal, sz=0.75 if e.get("sneak") else 0.62, w=2 if e.get("sneak") else 1)


def fx_owlleafage(fx, e, col):
    """Fogliame: foglia che rotea verso il bersaglio; foglioline all'impatto."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    life = (0.08 + L / 26.0) / 0.85
    fx._shape(kind="owlleaf", a=a, b=b, sz=0.24, seed=random.uniform(0, 6), col=LEAF[1], life=life)
    if e.get("hit"):
        _hit_leaf(fx, b, life * 0.85)


def fx_owlleafblade(fx, e, col):
    """Foglielama (tre per lancio, a ventaglio): lame di foglia sottili."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    life = (0.06 + L / 34.0) / 0.8
    fx._shape(kind="owlblade", a=a, b=b, sz=0.32, col=LEAF[1], life=life)
    if e.get("hit"):
        _hit_leaf(fx, b, life * 0.8, n=3)


def fx_owlgigadrain(fx, e, col):
    """Gigassorbimento: freccia di foglia; se va a segno, granelli verdi che
    tornano a chi la scocca (la cura)."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fly = _arrow_shot(fx, a, b, "leaf", sz=0.66)
    if e.get("hit"):
        _hit_leaf(fx, b, fly, n=3)
        fx._shape(kind="owldrain", a=b, b=a, n=10, seed=random.randrange(999), track=fx.pos_of,
                  sid=e.get("src"), col=LEAF[1], life=0.9, wait=fly)
        fx._shape(kind="twinkle", c=(a[0], a[1] - 0.9), r=0.28, col=LEAF[2], life=0.3, wait=fly + 0.6)


def fx_owlastonish(fx, e, col):
    """Sgomento: freccia d'ombra; il colpito si spaventa (fantasmino che spunta)."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fly = _arrow_shot(fx, a, b, "ghost")
    if e.get("hit"):
        fx._shape(kind="owlboo", c=b, r=0.22, col=FEAR[1], life=0.7, wait=fly)
        fx._shape(kind="flash", c=(b[0], b[1] - 0.4), r=0.32, col=GHOST[2], life=0.12, wait=fly)


def fx_owlphantom(fx, e, col):
    """Sbigoattacco: la freccia sparisce nell'ombra a metà volo e ricompare
    davanti al bersaglio (sbuffi d'ombra) con un colpo viola più forte."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    mid = (a[0] + (b[0] - a[0]) * 0.45, a[1] + (b[1] - a[1]) * 0.45)
    ln = (b[0] - a[0], b[1] - a[1])
    n = max(1e-6, L)
    re = (b[0] - ln[0] / n * min(1.2, L * 0.3), b[1] - ln[1] / n * min(1.2, L * 0.3))
    f1 = _arrow_shot(fx, a, mid, "ghost", speed=40.0)
    for pt, w in ((mid, f1), (re, f1 + 0.12)):
        fx._shape(kind="ring", c=(pt[0], pt[1] - 0.4), r0=0.1, r1=0.45, col=GHOST[1], life=0.22, wd=0.06, wait=w)
    L2 = math.hypot(b[0] - re[0], b[1] - re[1])
    life2 = (0.04 + L2 / 40.0) / 0.85
    fx._shape(kind="owlarrow", a=re, b=b, pal="ghost", sz=0.7, w=2, lift=0.4, col=GHOST[1],
              life=life2, wait=f1 + 0.12)
    if e.get("hit"):
        w = f1 + 0.12 + life2 * 0.85
        top = (b[0], b[1] - 0.4)
        fx._shape(kind="impactstar", c=top, r=0.6, n=7, rot=random.uniform(0, 1),
                  cols=(SHADE, GHOST[1], GHOST[2]), col=GHOST[1], life=0.24, wait=w)


def fx_owlsynthesis(fx, e, col):
    """Sintesi: fascio di sole dall'alto + foglioline che salgono (cura)."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    fx._shape(kind="owlsun", c=tuple(c), r=0.75, col=SUN[1], life=1.0)
    fx._shape(kind="twinkle", c=(c[0] - 0.3, c[1] - 1.2), r=0.3, col=SUN[2], life=0.35, wait=0.2)
    fx._shape(kind="twinkle", c=(c[0] + 0.35, c[1] - 0.8), r=0.22, col=SUN[2], life=0.3, wait=0.45)


def fx_owlfeatherdance(fx, e, col):
    """Danzadipiume: nuvola di piume che piove sull'area (Att. ridotto)."""
    c = e.get("c")
    if c is None or e.get("kind") != "area":
        return
    r = float(e.get("radius", 2.2))
    fx._shape(kind="ring", c=tuple(c), r0=r * 0.3, r1=r, col=FEATHER[1], life=0.35, wd=0.05)
    for i in range(16):
        an = random.uniform(0, math.tau)
        d = math.sqrt(random.random()) * r * 0.9
        p = (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.7)
        fx._shape(kind="owlfeather", c=p, h=random.uniform(0.9, 1.9), fall=random.uniform(0.7, 1.2),
                  dx=random.uniform(-0.3, 0.3), sz=random.uniform(0.13, 0.2), fq=random.uniform(4, 7),
                  seed=random.uniform(0, 6), col=FEATHER[1], life=random.uniform(1.0, 1.5),
                  wait=random.uniform(0.0, 0.25))


def fx_owluturn(fx, e, col):
    """Retromarcia: picchiata in avanti (folate + piume); il rimbalzo
    all'indietro ("ret") lascia una scia e piume più rade."""
    if e.get("kind") != "dash":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 1e-3:
        return
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    px, py = -uy, ux
    for k in (-1, 0, 1):   # folate CORTE a distanze diverse (lunghe sembravano righelli)
        o = k * 0.3
        u1 = random.uniform(0.55, 1.0)
        seg = min(L * u1, random.uniform(0.7, 1.1))
        e1 = (a[0] + ux * L * u1 + px * o, a[1] + uy * L * u1 + py * o - 0.35)
        e0 = (e1[0] - ux * seg, e1[1] - uy * seg)
        fx._shape(kind="windline", a=e0, b=e1, col=FEATHER[2], life=0.25 + 0.05 * abs(k))
    for i in range(3 if e.get("ret") else 5):
        u = random.uniform(0.2, 1.0)
        p = (a[0] + (b[0] - a[0]) * u + random.uniform(-0.3, 0.3), a[1] + (b[1] - a[1]) * u)
        fx._shape(kind="owlfeather", c=p, h=random.uniform(0.5, 1.0), fall=0.6, sz=0.13,
                  fq=6.0, seed=random.uniform(0, 6), col=FEATHER[1], life=0.8, wait=u * 0.15)
    if e.get("hit"):
        top = (b[0] + ux * 0.4, b[1] + uy * 0.4 - 0.4)
        fx._shape(kind="impactstar", c=top, r=0.55, n=6, rot=random.uniform(0, 1),
                  cols=((60, 70, 20), (170, 190, 60), (230, 240, 160)), col=(170, 190, 60), life=0.22)


def fx_owlboomburst(fx, e, col):
    """Granvoce: grido a onde concentriche attorno (Att. aumentato)."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    top = (c[0], c[1] - 0.45)
    for k in range(3):   # tre onde concentriche che si allargano, una dopo l'altra
        fx._shape(kind="soundarc", c=top, ang=0.0, r0=0.3, r1=1.6 - 0.2 * k, half=math.pi,
                  w=0.07, jag=0.0, speed=1.0, cols=SOUND, col=SOUND[1], life=0.4, wait=0.11 * k)
    fx._shape(kind="flash", c=top, r=0.4, col=SOUND[2], life=0.12)
    _shake(fx, 120)


def fx_owlshackle(fx, e, col):
    """Cucitombra: freccia d'ombra enorme e veloce; se va a segno resta
    piantata nell'ombra del colpito col filo che lo lega (3 s)."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    fx._shape(kind="flash", c=(a[0], a[1] - 0.4), r=0.45, col=GHOST[1], life=0.14)
    _bits(fx, (a[0], a[1] - 0.4), 6, (GHOST[1], GHOST[2], SHADE), speed=1.6)
    fly = _arrow_shot(fx, a, b, "ghost", sz=1.25, speed=48.0, w=3)
    # scia d'ombra che resta un attimo lungo il tiro
    fx._shape(kind="windline", a=(a[0], a[1] - 0.4), b=(b[0], b[1] - 0.4), col=GHOST[1], life=0.4)
    if e.get("hit"):
        top = (b[0], b[1] - 0.4)
        fx._shape(kind="impactstar", c=top, r=0.85, n=8, rot=random.uniform(0, 1),
                  cols=(SHADE, GHOST[1], GHOST[2]), col=GHOST[1], life=0.26, wait=fly)
        fx._shape(kind="owlstitch", c=(b[0] - 0.55, b[1] + 0.35), track=fx.pos_of, tid=e.get("hit_id"),
                  col=GHOST[1], life=3.0, wait=fly)
        _bits(fx, top, 10, (GHOST[1], GHOST[2], SHADE), speed=2.4)
        _shake(fx, 140)


def fx_owlrain(fx, e, col):
    """Pioggia di Frecce. Al lancio (ha "src"): frecce scoccate in alto e
    mirino che si riempie nel ritardo, poi resta il bordo per tutta la pioggia.
    A ogni colpo (senza "src"): frecce che piovono nell'area e si piantano."""
    c = e.get("c")
    if c is None or e.get("kind") != "area":
        return
    if e.get("src") is not None:
        r = float(e.get("radius", 3.0))
        fx._shape(kind="owlrainmark", c=tuple(c), r=r, delay=1.0, col=LEAF[1], life=4.0)
        a = fx.pos_of(e["src"]) if fx.pos_of is not None else None
        if a is not None:   # tre frecce scoccate verso il cielo
            for k in (-1, 0, 1):
                top = (a[0] + k * 0.3 + 0.6, a[1] - 3.5)
                fx._shape(kind="owlarrow", a=(a[0], a[1]), b=top, pal="leaf", sz=0.55, lift=0.5,
                          col=LEAF[1], life=0.3, wait=0.05 * (k + 1))
        return
    r = float(e.get("radius", 1.5)) * 2.0   # i colpi riportano metà raggio
    for _ in range(7):
        an = random.uniform(0, math.tau)
        d = math.sqrt(random.random()) * r * 0.92
        p = (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.6)
        fx._shape(kind="owlfall", c=p, ang=random.uniform(64, 76), drop=0.3, sz=0.55,
                  pal="ghost" if _ghostly(e) else "leaf", col=LEAF[1], life=0.9,
                  wait=random.uniform(0.0, 0.4))


STYLES = {
    "owlarrow": fx_owlarrow, "owlleafage": fx_owlleafage, "owlleafblade": fx_owlleafblade,
    "owlgigadrain": fx_owlgigadrain, "owlastonish": fx_owlastonish, "owlphantom": fx_owlphantom,
    "owlsynthesis": fx_owlsynthesis, "owlfeatherdance": fx_owlfeatherdance,
    "owluturn": fx_owluturn, "owlboomburst": fx_owlboomburst, "owlshackle": fx_owlshackle,
    "owlrain": fx_owlrain,
}


# --- sulle unità ---------------------------------------------------------------------------

_ICON_CACHE: dict = {}


def _icon(name):
    """Iconcine pixel art 7x7 (in cache): spavento (fantasmino) e piuma (Att. giù)."""
    s = _ICON_CACHE.get(name)
    if s is not None:
        return s
    if name == "fear":
        rows = ["..###..", ".#####.", "##.#.##", "#######", "##...##", "#######", "#.#.#.#"]
        col = FEAR[2]
    else:
        rows = ["....##.", "...###.", "..####.", ".####..", ".###...", "##.....", "#......"]
        col = FEATHER[1]
    s = pygame.Surface((9, 9), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#":
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    if s.get_at((x + 1 + dx, y + 1 + dy))[3] == 0:
                        s.set_at((x + 1 + dx, y + 1 + dy), (*FEAR[0], 255) if name == "fear" else (*FEATHER[0], 255))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#":
                s.set_at((x + 1, y + 1), (*col, 255))
    if name == "fear":   # occhi scuri
        s.set_at((3, 3), (*SHADE, 255))
        s.set_at((5, 3), (*SHADE, 255))
    _ICON_CACHE[name] = s
    return s


def draw_unit_overlay(surface, u, gx, gy, now, ts):
    r = int(getattr(u, "radius", 0.5) * ts)
    # Spavento: fantasmino che trema sopra la testa (Sgomento e altri).
    if getattr(u, "fear_until", -1.0) > now:
        ic = _icon("fear")
        jx = int(round(math.sin(now * 40) * 1))
        surface.blit(ic, (gx - r - 6 + jx, gy - r * 2 - 8))
    # Att. ridotto da Danzadipiume: piuma che dondola accanto alla testa.
    if getattr(u, "atk_debuff_until", -1.0) > now:
        ic = _icon("feather")
        sw = int(round(math.sin(now * 4) * 2))
        surface.blit(ic, (gx + r + sw, gy - r * 2 - 4 + abs(sw) // 2))
    # Granvoce (solo la linea di Rowlet): onde che pulsano attorno al busto.
    if getattr(u, "dex", 0) in (722, 723, 724) and getattr(u, "atk_until", -1.0) > now:
        ph = (now * 1.8) % 1.0
        R = int(r * (0.9 + 0.7 * ph))
        rect = pygame.Rect(0, 0, R * 2, int(R * 1.2))
        rect.center = (gx, int(gy - r * 0.9))
        a = int(200 * (1.0 - ph))
        lay = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(lay, (*SOUND[1], a), lay.get_rect(), 2)
        surface.blit(lay, rect.topleft)
