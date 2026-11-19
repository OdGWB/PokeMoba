"""Anteprima animata di una mossa (enciclopedia): prima la MIRA, poi il LANCIO.

Solo grafica, nessuna logica di gioco: la forma dell'anteprima si ricava dai
campi del JSON della mossa (target, shape, range, radius, angle). Si disegna a
BASSA risoluzione (LW x LH px logici) e si scala NEAREST nel pannello, come il
resto della pixel art. Il fondo (terreno) e' pre-renderizzato una volta; a ogni
frame si ridisegnano solo poche primitive sulla superficie piccola, che si
scala in una Surface di destinazione in cache (nessuna allocazione a frame).

Ciclo di CYCLE ms: 0-AIM mira (indicatore + cursore che va sul punto), AIM-CAST
lancio (proiettile, cono, area, scatto, balzo...), poi una pausa in cui
l'effetto svanisce.
"""
from __future__ import annotations

import math
import random

import pygame

LW, LH = 176, 104
AIM, CAST, CYCLE = 900, 1800, 2500

LEAP_SHAPES = {"leap", "fly", "taxi", "cliffambush", "fullmoon", "blink", "voltdash", "sub",
               "bounce"}
DASH_SHAPES = {"dash", "jumpkick", "rockcharge", "scywing", "takedown", "bodyslam",
               "incinropes", "dashback", "chain"}
CC_KEYS = ("stun", "root", "confuse", "sleep", "blind", "taunt", "fear", "freeze", "silence",
           "paralyze", "para", "airborne", "slam_stun", "crash_stun")

KIND_IT = {"line": "Linea", "cone": "Cono", "point": "Area sul punto", "self_area": "Area attorno",
           "buff": "Su di sé", "dash": "Scatto", "leap": "Balzo", "unit": "Bersaglio",
           "ally": "Alleato"}


def classify(m) -> str:
    """Forma dell'anteprima di una mossa (vedi KIND_IT)."""
    tg = m.get("target", "direction")
    sh = str(m.get("shape") or "projectile")
    if tg == "self":
        r = m.get("radius")
        try:
            big = r is not None and float(r) >= 1.5
        except (TypeError, ValueError):
            big = False
        return "self_area" if big and sh != "buff" else "buff"
    if tg == "unit":
        return "unit"
    if tg == "ally":
        return "ally"
    if tg == "point":
        if sh in LEAP_SHAPES or "leap" in sh or "jump" in sh:
            return "leap"
        return "point"
    if sh in ("cone", "fan") or "angle" in m:
        return "cone"
    if sh in DASH_SHAPES or "dash" in sh:
        return "dash"
    return "line"


def _f(v, default):
    if isinstance(v, list):
        v = v[-1] if v else default
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


# --- risorse in cache ------------------------------------------------------------------------
_ground = None


def _ground_surf():
    """Terreno di giungla della scenetta (una volta)."""
    global _ground
    if _ground is None:
        s = pygame.Surface((LW, LH))
        s.fill((34, 56, 40))
        rnd = random.Random(7)
        for _ in range(140):
            x, y = rnd.randrange(LW), rnd.randrange(LH)
            c = rnd.choice([(30, 50, 36), (42, 66, 46), (46, 72, 48), (38, 60, 42)])
            s.fill(c, (x, y, rnd.randint(2, 6), rnd.randint(1, 3)))
        for _ in range(26):            # fili d'erba
            x, y = rnd.randrange(LW), rnd.randrange(8, LH)
            s.fill((60, 92, 56), (x, y - 2, 1, 2))
            s.fill((52, 82, 50), (x + 1, y - 1, 1, 1))
        _ground = s
    return _ground


def _ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _lighter(c, k=0.5):
    return tuple(int(v + (255 - v) * k) for v in c[:3])


def _darker(c, k=0.5):
    return tuple(int(v * (1 - k)) for v in c[:3])


class MovePreview:
    """Disegna l'anteprima animata di UNA mossa; un'istanza per scena."""

    def __init__(self):
        self.low = pygame.Surface((LW, LH))
        self.over = pygame.Surface((LW, LH), pygame.SRCALPHA)
        self._big = None            # destinazione dello scale NEAREST
        self._text = {}

    # --- geometria della scenetta --------------------------------------------------------
    def _layout(self, m, kind):
        rng = max(1.0, _f(m.get("range"), 5))
        rad = max(0.5, _f(m.get("radius"), 1))
        half = math.radians(min(85.0, _f(m.get("angle"), 45)))
        cx, cy = 26, 64
        if kind in ("buff", "self_area"):
            cx, cy = LW // 2 - 6, 60
            ppt = min(16.0, 40.0 / rad) if kind == "self_area" else 12.0
            return dict(cx=cx, cy=cy, ppt=ppt, rng=rng, rad=rad, half=half,
                        tx=cx + rad * ppt * 0.6, ty=cy - 4, ax=cx, ay=cy)
        if kind in ("point", "leap"):
            dp = min(rng, 8.0) * 0.75
            ppt = max(3.0, min(16.0, 132.0 / (dp + rad), 40.0 / rad))
            ax, ay = cx + dp * ppt, cy - 6
            return dict(cx=cx, cy=cy, ppt=ppt, rng=rng, rad=rad, half=half,
                        tx=ax + rad * ppt * 0.35, ty=ay + 2, ax=ax, ay=ay)
        ppt = max(3.0, min(16.0, 136.0 / rng))
        if kind == "cone":
            ppt = max(3.0, min(ppt, 46.0 / max(0.2, rng * math.sin(min(half, math.pi / 2)))))
        L = rng * ppt
        frac = {"cone": 0.7, "dash": 0.55, "line": 0.85}.get(kind, 0.8)
        tx = cx + L * frac
        return dict(cx=cx, cy=cy, ppt=ppt, rng=rng, rad=rad, half=half, L=L,
                    tx=tx, ty=cy, ax=cx + L, ay=cy)

    # --- disegno ----------------------------------------------------------------------------
    def render_low(self, m, kind, sprite, t):
        """Disegna la scenetta sulla superficie piccola al tempo t (ms nel ciclo)."""
        g = self._layout(m, kind)
        col = m.get("_col") or (200, 200, 200)
        low, ov = self.low, self.over
        low.blit(_ground_surf(), (0, 0))
        ov.fill((0, 0, 0, 0))
        a = _ease(t / AIM)                       # mira 0..1
        c = (t - AIM) / (CAST - AIM)             # lancio 0..1 (negativo durante la mira)
        p = max(0.0, (t - CAST) / (CYCLE - CAST))  # pausa 0..1
        cx, cy = g["cx"], g["cy"]
        ppt = g["ppt"]
        eff = m.get("effects") or {}
        foe = kind != "ally"
        has_target = kind != "buff"
        hit_at = None                            # istante (ms) del colpo
        px, py = cx, cy                          # posizione del lanciatore
        lift = 0
        ind = min(1.0, a * 2.5) * (1.0 if c < 0 else max(0.0, 1 - c * 1.6))
        ia = int(255 * ind)

        def A(alpha):                            # alfa dell'indicatore
            return max(0, min(255, int(alpha * ind)))

        # ---------- INDICATORE (mira) ----------
        if kind in ("line", "dash", "unit", "ally", "cone") and ia:
            L = g.get("L", g["rng"] * ppt)
            if kind == "cone":
                h = g["half"]
                pts = [(cx, cy)] + [(cx + L * math.cos(-h + 2 * h * i / 10),
                                     cy + L * math.sin(-h + 2 * h * i / 10)) for i in range(11)]
                pygame.draw.polygon(ov, (*col, A(70)), pts)
                pygame.draw.lines(ov, (*_lighter(col), A(200)), True, pts, 1)
            elif kind in ("line", "dash"):
                w = max(4, min(14, int(_f(m.get("radius"), 0.6) * ppt))) if kind == "line" else 8
                r = pygame.Rect(cx, cy - w // 2, int(L), w)
                ov.fill((*col, A(70)), r)
                pygame.draw.rect(ov, (*_lighter(col), A(190)), r, 1)
                if kind == "dash":          # punta di freccia
                    ex = cx + L
                    pygame.draw.polygon(ov, (*_lighter(col), A(220)),
                                        [(ex + 6, cy), (ex - 2, cy - 7), (ex - 2, cy + 7)])
            else:                            # unit / ally: cerchio della gittata
                pygame.draw.circle(ov, (255, 255, 255, A(60)), (cx, cy), int(L), 1)
                rc = (230, 70, 60) if foe else (90, 220, 140)
                pygame.draw.circle(ov, (*rc, A(220)), (int(g["tx"]), int(g["ty"]) + 3), 8, 1)
        elif kind in ("point", "leap") and ia:
            pygame.draw.circle(ov, (255, 255, 255, A(55)), (cx, cy), int(g["rng"] * ppt), 1)
            rr = max(3, int(g["rad"] * ppt))
            pygame.draw.circle(ov, (*col, A(70)), (int(g["ax"]), int(g["ay"])), rr)
            pygame.draw.circle(ov, (*_lighter(col), A(210)), (int(g["ax"]), int(g["ay"])), rr, 1)
        elif kind == "self_area" and ia:
            rr = max(4, int(g["rad"] * ppt))
            pygame.draw.circle(ov, (*col, A(55)), (cx, cy), rr)
            pygame.draw.circle(ov, (*_lighter(col), A(200)), (cx, cy), rr, 1)
        elif kind == "buff" and ia:
            pygame.draw.ellipse(ov, (*_lighter(col), A(200)), (cx - 14, cy - 2, 28, 10), 1)

        # ---------- LANCIO ----------
        if c >= 0:
            ms = t - AIM
            dur = CAST - AIM
            if kind == "line":
                L = g["L"]
                travel = 0.55 * dur
                hit_at = AIM + travel * (g["tx"] - cx) / L
                q = min(1.0, ms / travel)
                bx = cx + L * q
                if t < hit_at or kind == "line" and bool(m.get("pierce")):
                    if q < 1:
                        for i in range(4):     # scia
                            sx = bx - (i + 1) * 4
                            if sx > cx:
                                pygame.draw.circle(ov, (*col, 150 - i * 35), (int(sx), cy - 4), 3 - i // 2)
                        pygame.draw.circle(ov, _darker(col, 0.5), (int(bx), cy - 4), 4)
                        pygame.draw.circle(ov, col, (int(bx), cy - 4), 3)
                        pygame.draw.circle(ov, _lighter(col, 0.7), (int(bx) - 1, cy - 5), 1)
            elif kind == "cone":
                L, h = g["L"], g["half"]
                q = _ease(ms / (0.45 * dur))
                hit_at = AIM + 0.45 * dur * 0.6
                if q > 0 and c < 0.85:
                    al = int(150 * (1 - max(0.0, c - 0.45) / 0.4))
                    rr = L * q
                    # ventaglio pieno del colore del tipo che si allarga
                    fan = [(cx, cy)] + [(cx + rr * math.cos(-h + 2 * h * i / 12),
                                         cy + rr * math.sin(-h + 2 * h * i / 12)) for i in range(13)]
                    if rr > 3:
                        pygame.draw.polygon(ov, (*col, int(al * 0.75)), fan)
                        inner = [(cx, cy)] + [(cx + rr * 0.55 * math.cos(-h * 0.8 + 1.6 * h * i / 8),
                                               cy + rr * 0.55 * math.sin(-h * 0.8 + 1.6 * h * i / 8))
                                              for i in range(9)]
                        pygame.draw.polygon(ov, (*_lighter(col, 0.45), int(al * 0.6)), inner)
                    # particelle che corrono lungo il cono
                    for i in range(14):
                        ang = -h + 2 * h * ((i * 0.618) % 1.0)
                        d = ((ms / 380.0 + i * 0.137) % 1.0) * rr
                        sx, sy = cx + d * math.cos(ang), cy + d * math.sin(ang)
                        sz = 1 + (i % 3 == 0)
                        ov.fill((*_lighter(col, 0.6), al), (int(sx), int(sy), sz + 1, sz))
                    for k2 in range(3):
                        rk = rr - k2 * 6
                        if rk <= 2:
                            continue
                        pts = [(cx + rk * math.cos(-h + 2 * h * i / 12),
                                cy + rk * math.sin(-h + 2 * h * i / 12)) for i in range(13)]
                        pygame.draw.lines(ov, (*_lighter(col, 0.3 * k2), max(0, al - k2 * 40)),
                                          False, pts, 3 - k2 if k2 < 2 else 1)
            elif kind in ("point", "self_area"):
                ox, oy = (g["ax"], g["ay"]) if kind == "point" else (cx, cy)
                rr = max(3, g["rad"] * ppt)
                fall = 0.4 * dur
                hit_at = AIM + fall
                if ms < fall:
                    q = ms / fall
                    r1 = rr * (1.6 - 0.6 * q) if kind == "point" else rr * _ease(q)
                    pygame.draw.circle(ov, (*_lighter(col), 220), (int(ox), int(oy)), max(2, int(r1)), 2)
                    if kind == "point":   # colpo che cade dall'alto
                        yy = oy - 40 * (1 - q)
                        pygame.draw.circle(ov, col, (int(ox), int(yy)), 3)
                        pygame.draw.circle(ov, _lighter(col, 0.7), (int(ox) - 1, int(yy) - 1), 1)
            elif kind == "buff":
                q = min(1.0, ms / dur)
                for i in range(3):
                    r1 = 8 + ((q * 3 + i / 3) % 1.0) * 14
                    al = int(180 * (1 - (r1 - 8) / 14) * (1 - p))
                    pygame.draw.ellipse(ov, (*_lighter(col), al),
                                        (cx - r1, cy - r1 * 0.35 + 2, r1 * 2, r1 * 0.7), 1)
            elif kind == "dash":
                L = g["L"]
                q = _ease(ms / (0.45 * dur))
                px = cx + L * 0.9 * q
                hit_at = AIM + 0.45 * dur * 0.55
                if q < 1:
                    for i in range(4):
                        yy = cy - 10 + i * 5
                        pygame.draw.line(ov, (*_lighter(col), 170), (px - 18 - i * 3, yy), (px - 6, yy), 1)
            elif kind == "leap":
                q = _ease(ms / (0.6 * dur))
                hit_at = AIM + 0.6 * dur
                px = cx + (g["ax"] - cx) * q
                py = cy + (g["ay"] - cy) * q
                lift = int(math.sin(math.pi * min(1.0, q)) * 26)
                if t >= hit_at:
                    px, py, lift = g["ax"], g["ay"], 0
            elif kind in ("unit", "ally"):
                travel = 0.45 * dur
                hit_at = AIM + travel
                q = min(1.0, ms / travel)
                if q < 1:
                    bx = cx + (g["tx"] - cx) * q
                    by = cy - 4 + (g["ty"] - cy) * q - math.sin(math.pi * q) * 10
                    pygame.draw.circle(ov, _darker(col, 0.5), (int(bx), int(by)), 4)
                    pygame.draw.circle(ov, col, (int(bx), int(by)), 3)
                    pygame.draw.circle(ov, _lighter(col, 0.7), (int(bx) - 1, int(by) - 1), 1)

        # lanciatore e bersaglio, ordinati per y
        hit = hit_at is not None and t >= hit_at
        hit_age = (t - hit_at) if hit else -1
        if has_target:
            self._dummy(low, g["tx"], g["ty"], foe, hit_age if any(m.get("power") or []) or
                        not foe else -1, any(k in eff for k in CC_KEYS) and hit)
        # ombra + sprite del lanciatore
        pygame.draw.ellipse(low, (20, 34, 26), (px - 9, py - 1, 18, 6))
        if kind == "buff" and c >= 0:
            pygame.draw.ellipse(low, _darker(col, 0.25), (px - 12, py - 3, 24, 9), 1)
        if sprite is not None:
            low.blit(sprite, (int(px) - sprite.get_width() // 2, int(py) - sprite.get_height() + 2 - lift))
        else:
            pygame.draw.circle(low, (200, 200, 220), (int(px), int(py) - 8 - lift), 7)
        # alone del potenziamento sopra lo sprite (scintille che salgono)
        if kind == "buff" and c >= 0:
            for i in range(6):
                ph = (t / 600.0 + i / 6) % 1.0
                sx = px - 10 + (i * 37 % 21)
                sy = py - 4 - ph * 26
                al = int(230 * (1 - ph) * (1 - p))
                ov.fill((*_lighter(col, 0.6), al), (int(sx), int(sy), 2 if i % 2 else 1, 2 if i % 2 else 1))

        # colpo: lampo + stella a 4 raggi
        if hit and has_target and hit_age < 450:
            q = hit_age / 450.0
            hx, hy = int(g["tx"]), int(g["ty"]) - 8
            if kind in ("point", "self_area") and hit_age < 300:
                ox, oy = (g["ax"], g["ay"]) if kind == "point" else (cx, cy)
                rr = max(3, int(g["rad"] * ppt))
                pygame.draw.circle(ov, (*_lighter(col, 0.4), int(140 * (1 - hit_age / 300))),
                                   (int(ox), int(oy)), rr)
            if kind == "ally":
                for i in range(4):          # crocette verdi che salgono
                    sx = hx - 8 + i * 5
                    sy = hy - q * 12 - (i % 2) * 4
                    al = int(255 * (1 - q))
                    ov.fill((120, 240, 150, al), (sx, int(sy) - 1, 3, 1))
                    ov.fill((120, 240, 150, al), (sx + 1, int(sy) - 2, 1, 3))
            else:
                n = int(4 + 6 * (1 - q))
                al = int(255 * (1 - q))
                lc = (*_lighter(col, 0.6), al)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    pygame.draw.line(ov, lc, (hx, hy), (hx + dx * n, hy + dy * n), 1)
                pygame.draw.circle(ov, (255, 255, 255, al), (hx, hy), max(1, int(3 * (1 - q))))
        if lift:                                   # ombra del balzo che resta a terra
            pass
        low.blit(ov, (0, 0))
        if c < 0:
            self._cursor(low, g, kind, a)
        return low

    def _dummy(self, low, x, y, foe, hit_age, cc):
        """Bersaglio di prova: ombra, corpo tondo, barra della vita (scende al colpo)."""
        x, y = int(x), int(y)
        body = (196, 84, 74) if foe else (86, 170, 214)
        flash = 0 <= hit_age < 120
        pygame.draw.ellipse(low, (20, 34, 26), (x - 8, y - 1, 16, 5))
        pygame.draw.circle(low, (24, 20, 26), (x, y - 7), 7)
        pygame.draw.circle(low, (255, 255, 255) if flash else body, (x, y - 7), 6)
        if not flash:
            pygame.draw.circle(low, _lighter(body, 0.4), (x - 2, y - 9), 2)
            low.fill((30, 24, 30), (x - 2, y - 8, 1, 2))
            low.fill((30, 24, 30), (x + 2, y - 8, 1, 2))
        hp = 1.0
        if hit_age >= 0:
            hp = 1.0 - 0.3 * min(1.0, hit_age / 150) if foe else 1.0
        low.fill((16, 16, 20), (x - 9, y - 19, 18, 4))
        low.fill((220, 70, 60) if foe else (80, 210, 120), (x - 8, y - 18, int(16 * hp), 2))
        if cc:                                  # stelline che girano: controllo
            tt = pygame.time.get_ticks() / 260.0
            for i in range(3):
                an = tt + i * 2.09
                low.fill((250, 230, 120), (int(x + math.cos(an) * 6), int(y - 22 + math.sin(an) * 2), 2, 1))

    def _cursor(self, low, g, kind, a):
        """Cursore del mouse che va sul punto di mira."""
        if kind in ("buff", "self_area"):
            return
        sx, sy = g["cx"] + 18, g["cy"] - 30
        if kind in ("point", "leap"):
            ex, ey = g["ax"], g["ay"]
        elif kind in ("unit", "ally"):
            ex, ey = g["tx"], g["ty"] - 6
        else:
            ex, ey = g["cx"] + g.get("L", 60) * 0.8, g["cy"] - 3
        x = int(sx + (ex - sx) * a)
        y = int(sy + (ey - sy) * a)
        arrow = [(0, 0), (0, 8), (2, 6), (4, 9), (5, 8), (3, 5), (6, 5)]
        pygame.draw.polygon(low, (20, 20, 24), [(x + px - 1, y + py) for px, py in arrow])
        pygame.draw.polygon(low, (20, 20, 24), [(x + px + 1, y + py + 1) for px, py in arrow])
        pygame.draw.polygon(low, (250, 250, 250), [(x + px, y + py) for px, py in arrow])

    # --- pannello a piena risoluzione ------------------------------------------------------
    def _txt(self, f, s, col):
        key = (id(f), s, col)
        if key not in self._text:
            if len(self._text) > 200:
                self._text.clear()
            self._text[key] = f.render(s, True, col)
        return self._text[key]

    def draw(self, surface, m, sprite, t, mouse, view_h, k, fonts, colors, avoid=None):
        """Pannello vicino al mouse con la scenetta scalata NEAREST.

        `avoid` = riquadro (coordinate schermo) della scheda della mossa: il pannello
        si mette di fianco, sopra o sotto, mai sopra il testo che si sta leggendo."""
        kind = classify(m)
        sc = max(2, int(round(2 * k)))
        bw, bh = LW * sc, LH * sc
        f_b, f_s = fonts
        gold, text, dim, panel, line = colors
        pad = max(6, int(8 * k))
        head = f_b.get_linesize() + pad
        foot = f_s.get_linesize() + pad // 2
        pw, ph = bw + 2 * pad, bh + head + foot + pad
        W = surface.get_width()
        mx, my = mouse
        r = None
        if avoid is not None:
            yc = max(8, min(avoid.centery - ph // 2, view_h - ph - 8))
            for cand in ((avoid.right + 12, yc), (avoid.x - 12 - pw, yc),
                         (avoid.right - pw - 16, avoid.bottom + 10), (avoid.right - pw - 16, avoid.y - ph - 10)):
                c = pygame.Rect(cand, (pw, ph))
                c.x = max(8, min(c.x, W - pw - 8))
                if c.y >= 8 and c.bottom <= view_h - 8 and c.x >= 8 and not c.colliderect(avoid):
                    r = c
                    break
        if r is None:
            x = mx + 22 if mx + 22 + pw < W - 8 else mx - 22 - pw
            x = max(8, x)
            y = max(8, min(my - ph // 2, view_h - ph - 8))
            r = pygame.Rect(x, y, pw, ph)
        sh = r.move(4, 4)
        pygame.draw.rect(surface, (6, 8, 10), sh, border_radius=8)
        pygame.draw.rect(surface, panel, r, border_radius=8)
        pygame.draw.rect(surface, gold, r, 2, border_radius=8)
        nm = self._txt(f_b, m.get("name", "?"), text)
        surface.blit(nm, (r.x + pad, r.y + pad // 2 + 2))
        aim = t < AIM
        pill = self._txt(f_s, "1 · MIRA" if aim else "2 · LANCIO", (20, 20, 20))
        pr = pygame.Rect(0, 0, pill.get_width() + 14, pill.get_height() + 4)
        pr.topright = (r.right - pad, r.y + pad // 2 + 2)
        pygame.draw.rect(surface, (240, 200, 90) if aim else (120, 210, 140), pr, border_radius=pr.h // 2)
        surface.blit(pill, (pr.x + 7, pr.y + 2))
        low = self.render_low(m, kind, sprite, t)
        if self._big is None or self._big.get_size() != (bw, bh):
            self._big = pygame.Surface((bw, bh))
        pygame.transform.scale(low, (bw, bh), self._big)
        surface.blit(self._big, (r.x + pad, r.y + head))
        pygame.draw.rect(surface, line, (r.x + pad - 1, r.y + head - 1, bw + 2, bh + 2), 1)
        info = KIND_IT.get(kind, "")
        rng = _f(m.get("range"), 5)
        if kind not in ("buff", "self_area"):
            info += f" · gittata {rng:g}".replace(".", ",")
        if kind in ("point", "leap", "self_area") or kind == "cone":
            if kind == "cone":
                info += f" · {2 * _f(m.get('angle'), 45):g}°"
            elif m.get("radius"):
                info += f" · raggio {_f(m.get('radius'), 1):g}".replace(".", ",")
        surface.blit(self._txt(f_s, info, dim), (r.x + pad, r.y + head + bh + pad // 2))
        return r


# --- descrizione a parole ------------------------------------------------------------------
def _s(v):
    """Numero leggibile (ultimo grado se lista), virgola decimale."""
    x = _f(v, 0)
    return f"{x:g}".replace(".", ",")


def _join(parts):
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " e " + parts[-1]


_STATUS = [("stun", "stordisce"), ("root", "immobilizza"), ("confuse", "confonde"),
           ("sleep", "addormenta"), ("blind", "acceca"), ("taunt", "provoca"),
           ("fear", "spaventa"), ("freeze", "congela"), ("silence", "silenzia"),
           ("paralyze", "paralizza"), ("para", "paralizza"), ("airborne", "lancia in aria"),
           ("burn", "scotta"), ("healcut", "riduce le cure"),
           ("itemlock", "disattiva gli oggetti"), ("dashlock", "blocca gli scatti")]
_BUFFS = [("atk", "Attacco"), ("def", "Difesa"), ("spatk", "Att. Sp."), ("spdef", "Dif. Sp."),
          ("all_stats", "tutte le statistiche")]


def _dur_of(v):
    if isinstance(v, dict):
        v = v.get("duration")
    if v is None or isinstance(v, (dict, str, bool)):
        return ""
    x = _f(v, 0)
    return f" per {_s(x)} s" if x > 0 else ""


def describe_move(m, overrides=None) -> str:
    """Frase che spiega cosa fa la mossa (testo a mano in encyclopedia.json se c'e')."""
    if overrides and m.get("id") in overrides:
        o = overrides[m["id"]]
        return o if isinstance(o, str) else o.get("text", "")
    kind = classify(m)
    eff = m.get("effects") or {}
    rng = _s(m.get("range", 5))
    rad = _s(m.get("radius", 1))
    head = {
        "line": f"Lancia un colpo in linea retta fino a {rng} tile",
        "cone": f"Colpisce in un cono di {_s(2 * _f(m.get('angle'), 45))}° davanti a sé "
                f"(portata {rng} tile)",
        "point": f"Agisce in un'area di raggio {rad} tile sul punto scelto (fino a {rng} tile)",
        "self_area": f"Agisce in un'area di raggio {rad} tile attorno a sé",
        "buff": "Potenzia sé stesso",
        "dash": f"Scatta in avanti di {rng} tile",
        "leap": f"Balza sul punto scelto (fino a {rng} tile)",
        "unit": f"Prende di mira un nemico entro {rng} tile",
        "ally": f"Agisce su un alleato entro {rng} tile",
    }[kind]
    if kind == "leap" and m.get("radius"):
        head += f" e colpisce chi sta entro {rad} tile dall'atterraggio"
    cl = []
    pre = ""
    if "delay" in eff and _f(eff["delay"], 0) > 0:
        pre = f"dopo {_s(eff['delay'])} s "
    if "channel" in eff and _f(eff["channel"], 0) > 0:
        pre = f"dopo una carica di {_s(eff['channel'])} s "
    if any(m.get("power") or []):
        t = "infligge danno " + ("speciale" if m.get("category") == "special" else "fisico")
        if "interval" in eff and isinstance(eff.get("duration"), (int, float, list)):
            t += f" ogni {_s(eff['interval'])} s per {_s(eff['duration'])} s"
        cl.append(t)
    for k, verb in _STATUS:
        if k in eff:
            cl.append(verb + _dur_of(eff[k]))
    if "slow" in eff:
        s = eff["slow"]
        mult = s.get("mult") if isinstance(s, dict) else s
        p = int(round((1 - _f(mult, 1)) * 100))
        cl.append((f"rallenta del {p}%" if 0 < p < 100 else "rallenta") + _dur_of(s))
    if "poison" in eff:
        cl.append("avvelena" + _dur_of(eff["poison"]))
    if "push" in eff or "knockback" in eff:
        cl.append("respinge i nemici")
    if "heal" in eff:
        cl.append("cura" + (" l'alleato" if kind == "ally" else ""))
    if "heal_self_ratio" in eff:
        cl.append("ti cura di una parte del danno inflitto")
    if "shield" in eff:
        sh = eff["shield"]
        cl.append("dà uno scudo" + (_dur_of(sh) if isinstance(sh, dict) else ""))
    for k, lab in _BUFFS:
        if k in eff:
            v = eff[k]
            mult = v.get("mult") if isinstance(v, dict) else v
            p = int(round((_f(mult, 1) - 1) * 100))
            if p > 0:
                cl.append(f"+{p}% {lab}" + _dur_of(v))
            elif p < 0:
                cl.append(f"{p}% {lab}" + _dur_of(v))
    if "speed" in eff:
        v = eff["speed"]
        mult = v.get("mult") if isinstance(v, dict) else 1 + _f(v, 0)
        p = int(round((_f(mult, 1) - 1) * 100))
        if p:
            cl.append(f"{'+' if p > 0 else ''}{p}% velocità" + _dur_of(v))
    if "attack_speed" in eff:
        v = eff["attack_speed"]
        x = _f(v.get("mult") if isinstance(v, dict) else v, 0)
        p = int(round((x - 1) * 100 if x > 1 else x * 100))
        if p:
            cl.append(f"+{p}% velocità d'attacco" + _dur_of(v))
    if "def_debuff" in eff:
        cl.append("riduce la Difesa" + _dur_of(eff["def_debuff"]))
    if "spdef_debuff" in eff:
        cl.append("riduce la Dif. Sp." + _dur_of(eff["spdef_debuff"]))
    if "recoil" in eff:
        cl.append("ti costa un po' di vita (contraccolpo)")
    if "untargetable" in eff:
        cl.append("ti rende non bersagliabile" + _dur_of(eff["untargetable"]))
    if "chain" in eff:
        cl.append("rimbalza tra più bersagli")
    if m.get("pierce"):
        cl.append("attraversa i nemici")
    if m.get("charges"):
        cl.append(f"ha {m['charges']} cariche")
    if not cl:
        if kind == "buff":
            return "Potenzia sé stesso per un breve periodo."
        return head + "."
    if kind == "buff":
        return "Su di sé: " + pre + _join(cl) + "."
    return head + ": " + pre + _join(cl) + "."
