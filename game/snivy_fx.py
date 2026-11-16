"""Grafica della linea Snivy > Servine > Serperior: effetti istantanei (handler
registrati in FXSystem._FX_STYLES), forme nuove per FXSystem._draw_shapes
(foglia-rasoio, liana che frusta, sfera d'energia, liana che si allunga e si
avvolge, cappio d'erba, ciuffi che spuntano, spine d'erba, campo erboso,
radici spinose, mirino della VerdeBufera, arco del Vasto Impatto) e il disegno
sulle unità (foglie in orbita: le cariche di Inversione).

Pixel art: forme piene a 3 strati (contorno scuro, colore, luce), niente
smoothscale; luce da in alto a sinistra.
"""
from __future__ import annotations

import math
import random

import pygame

LEAF = ((18, 52, 26), (78, 168, 76), (186, 236, 138))       # contorno, corpo, luce
VINE = ((16, 44, 22), (52, 128, 58), (150, 214, 110))       # liana (più scura della foglia)
STEEL = ((40, 46, 58), (156, 168, 186), (238, 244, 252))    # Codacciaio
ENERGY = ((22, 70, 30), (120, 214, 96), (232, 255, 196))    # EnergiPalla
DRAGON = ((34, 18, 70), (120, 82, 220), (212, 196, 255))    # Vasto Impatto
GOLD = ((96, 70, 12), (238, 200, 70), (255, 244, 176))      # sovraccarico di Inversione
FLOWER = ((236, 236, 220), (248, 214, 90), (238, 140, 170))
DIRT = ((52, 38, 24), (110, 84, 52), (160, 128, 86))
SHADE = (10, 24, 14)
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

def draw_leaf(surface, x, y, ang, s, alpha, cols=LEAF, thin=1.0):
    """Foglia appuntita ai due capi, nervatura chiara (come rowlet_fx)."""
    ca, sa = math.cos(ang), math.sin(ang)
    px, py = -sa, ca
    pts = []
    for i in range(17):
        an = i / 8 * math.pi
        d = math.cos(an) * s
        wv = math.sin(an) * s * 0.42 * thin
        pts.append((x + ca * d + px * wv, y + sa * d + py * wv))
    out = [(x + (qx - x) * 1.25 + 0.4, y + (qy - y) * 1.25 + 0.4) for qx, qy in pts]
    pygame.draw.polygon(surface, (*cols[0], alpha), out)
    pygame.draw.polygon(surface, (*cols[1], alpha), pts)
    pygame.draw.line(surface, (*cols[2], alpha), (x - ca * s * 0.8, y - sa * s * 0.8),
                     (x + ca * s * 0.8, y + sa * s * 0.8), 1)


def draw_vine(surface, pts, w, alpha, cols=VINE, leaves=True, thorns=False):
    """Liana affusolata lungo una spezzata: spessa alla base, sottile in punta.
    Tre passate (contorno, corpo, filo di luce in alto a sinistra); foglioline a
    coppie (o spine) ogni tanto lungo il tralcio."""
    n = len(pts)
    if n < 2:
        return
    for pas in range(3):
        for i in range(n - 1):
            k = 1.0 - i / (n - 1)
            ww = max(1.0, w * (0.35 + 0.65 * k))
            p0, p1 = pts[i], pts[i + 1]
            if pas == 0:
                pygame.draw.line(surface, (*cols[0], alpha), p0, p1, int(ww + 2))
            elif pas == 1:
                pygame.draw.line(surface, (*cols[1], alpha), p0, p1, int(ww))
            elif ww >= 3:
                o = ww * 0.25
                pygame.draw.line(surface, (*cols[2], alpha), (p0[0] - o, p0[1] - o), (p1[0] - o, p1[1] - o), 1)
    step = 3
    for i in range(2, n - 1, step):
        p0, p1 = pts[i - 1], pts[i]
        ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        k = 1.0 - i / (n - 1)
        if thorns:
            for sg in (-1, 1):
                an = ang + sg * 1.9
                L = 2 + 3 * k
                tip = (p1[0] + math.cos(an) * (w * 0.5 + L), p1[1] + math.sin(an) * (w * 0.5 + L))
                base = (p1[0] + math.cos(an) * w * 0.4, p1[1] + math.sin(an) * w * 0.4)
                pygame.draw.line(surface, (*DIRT[2], alpha), base, tip, 1)
        elif leaves:
            sg = 1 if (i // step) % 2 else -1
            an = ang + sg * 0.9
            s = 2.0 + 3.0 * k
            lx = p1[0] + math.cos(an) * (s + w * 0.4)
            ly = p1[1] + math.sin(an) * (s + w * 0.4)
            draw_leaf(surface, lx, ly, an, s, alpha, LEAF if cols is VINE else cols)


def _tuft(surface, x, y, h, alpha, cols=LEAF, n=3, lean=0.0):
    """Ciuffo d'erba: 3-4 lame SOTTILI e alte a V che partono dalla base (x, y),
    alte h px (lame larghe e basse sembravano casette)."""
    bw = max(1.0, h * 0.07)
    for i in range(n):
        u = (i / max(1, n - 1) - 0.5) if n > 1 else 0.0
        tx = x + u * h * 1.1 + lean * h
        ty = y - h * (1.0 - 0.2 * abs(u))
        bx = x + u * h * 0.3
        out = [(bx - bw - 1, y + 1), (tx, ty - 1), (bx + bw + 1, y + 1)]
        pygame.draw.polygon(surface, (*cols[0], alpha), out)
        pygame.draw.polygon(surface, (*cols[1 if u > 0 else 2], alpha), [(bx - bw, y), (tx, ty), (bx + bw, y)])


def _orb(surface, x, y, R, alpha, ph, cols=ENERGY):
    """Sfera d'energia: alone, guscio, spirale chiara che gira, nucleo bianco."""
    R = max(2.0, R)
    lay = pygame.Surface((int(R * 4), int(R * 4)), pygame.SRCALPHA)
    cx, cy = R * 2, R * 2
    pygame.draw.circle(lay, (*cols[1], 50), (int(cx), int(cy)), int(R * 1.7))
    pygame.draw.circle(lay, (*cols[0], 255), (int(cx), int(cy)), int(R) + 1)
    pygame.draw.circle(lay, (*cols[1], 255), (int(cx), int(cy)), int(R))
    for k in range(2):   # due bracci di spirale
        prev = None
        for i in range(9):
            u = i / 8
            an = ph + k * math.pi + u * 2.6
            rr = R * (0.15 + 0.7 * u)
            p = (cx + math.cos(an) * rr, cy + math.sin(an) * rr)
            if prev is not None:
                pygame.draw.line(lay, (*cols[2], 230), prev, p, 1)
            prev = p
    pygame.draw.circle(lay, (*cols[2], 255), (int(cx - R * 0.3), int(cy - R * 0.3)), max(1, int(R * 0.35)))
    lay.fill((*WHITE, 255), pygame.Rect(int(cx - R * 0.4), int(cy - R * 0.4), 1, 1))
    lay.set_alpha(alpha)
    surface.blit(lay, (x - cx, y - cy))


# --- forme -------------------------------------------------------------------------------

SHAPES = ("snvleaf", "snvwhip", "snvball", "snvreach", "snvwrap", "snvknot", "snvsprout",
          "snvspike", "snvfield", "snvroot", "snvmark", "snvarc")
AA_TRAVEL = {"snvleaf": 0.85}


def draw_shape(overlay, s, S, ts, f, a):
    kind = s["kind"]
    t = 1.0 - f
    age = s["maxlife"] - s["life"]
    if kind == "snvleaf":
        # Foglia-rasoio: rotea velocissima verso il bersaglio con una scia di foglie fantasma.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.85)
        if u >= 1.0:
            return
        lift = 0.4 * ts
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - lift
        al = 255 if "hom" in s else _al(f, 4.0)
        sz = s.get("sz", 0.2) * ts
        for k in (2, 1):
            uu = max(0.0, u - 0.07 * k)
            gx, gy = ax + (bx - ax) * uu, ay + (by - ay) * uu - lift
            draw_leaf(overlay, gx, gy, age * 22 - k * 0.7, sz * 0.75, al // (2 * k))
        draw_leaf(overlay, x, y, age * 22, sz, al)
    elif kind == "snvwhip":
        # Frustata / Codacciaio: la liana parte dal lanciatore e spazza il cono da
        # un lato all'altro; la punta lascia una scia chiara.
        ox, oy = S(*s["o"])
        oy -= 0.35 * ts
        ang = s["ang"]
        half = s.get("half", 0.33)
        L = s.get("r", 4.0) * ts
        prog = min(1.0, t / 0.55)
        e = prog * prog * (3 - 2 * prog)
        side = s.get("side", 1)
        head = ang - side * half + side * 2 * half * e
        reach = min(1.0, t / 0.18)
        cols = s.get("cols", VINE)
        al = _al(f, 3.0)
        # scia della punta: archetto di trattini chiari
        for j in range(5):
            aa = head - side * 0.09 * (j + 1)
            if (aa - (ang - half)) * side < -0.05:
                break
            r0 = L * reach * 0.9
            p0 = (ox + math.cos(aa) * r0, oy + math.sin(aa) * r0 * 0.85)
            p1 = (ox + math.cos(aa + side * 0.07) * r0, oy + math.sin(aa + side * 0.07) * r0 * 0.85)
            pygame.draw.line(overlay, (*cols[2], int(al * (0.6 - 0.1 * j))), p0, p1, max(1, 3 - j // 2))
        # tralcio: curva che si flette all'indietro rispetto al moto
        pts = []
        N = 14
        for i in range(N + 1):
            u = i / N
            bend = -side * 0.35 * math.sin(u * math.pi) * (1.0 - e * 0.6)
            an = head + bend * u
            rr = L * reach * u
            pts.append((ox + math.cos(an) * rr, oy + math.sin(an) * rr * 0.85))
        draw_vine(overlay, pts, s.get("w", 0.16) * ts, al, cols, leaves=cols is VINE)
    elif kind == "snvball":
        # EnergiPalla in volo: sfera verde con la spirale che gira e scia di granelli.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.9)
        if u >= 1.0:
            return
        x, y = ax + (bx - ax) * u, ay + (by - ay) * u - 0.45 * ts
        R = s.get("r", 0.26) * ts
        for k in range(1, 5):   # scia: palline sempre più piccole e tenui
            uu = max(0.0, u - 0.035 * k)
            gx, gy = ax + (bx - ax) * uu, ay + (by - ay) * uu - 0.45 * ts
            pygame.draw.circle(overlay, (*ENERGY[1], 150 - 30 * k), (int(gx), int(gy)), max(1, int(R * (0.7 - 0.12 * k))))
        pygame.draw.ellipse(overlay, (*SHADE, 70), pygame.Rect(int(x - R), int(y + 0.45 * ts - R * 0.3), int(R * 2), int(R * 0.6)))
        _orb(overlay, x, y, R, 255, age * 9)
    elif kind == "snvreach":
        # Liana che si allunga da A al colpito e poi si ritrae (Avvolgibotta).
        ax, ay = S(*s["a"])
        p = _track(s)
        bx, by = S(*(p if p is not None else s["b"]))
        ay -= 0.35 * ts
        by -= 0.35 * ts
        out = s.get("out", 0.5)
        ext = min(1.0, t / out) if t < out else max(0.0, 1.0 - (t - out) / (1.0 - out))
        if ext <= 0.01:
            return
        ang = math.atan2(by - ay, bx - ax)
        px, py = -math.sin(ang), math.cos(ang)
        L = math.hypot(bx - ax, by - ay) * ext
        pts = []
        N = 16
        for i in range(N + 1):
            u = i / N
            wv = math.sin(u * math.pi * 2.0 + age * 14) * 0.12 * ts * math.sin(u * math.pi)
            pts.append((ax + math.cos(ang) * L * u + px * wv, ay + math.sin(ang) * L * u + py * wv))
        draw_vine(overlay, pts, s.get("w", 0.14) * ts, 255)
    elif kind == "snvwrap":
        # Spire di liana avvolte attorno al colpito (lo seguono): metà dietro
        # più scura, metà davanti piena; si stringono e poi si sciolgono.
        p = _track(s)
        cx, cy = S(*(p if p is not None else s["c"]))
        r = s.get("r", 0.42) * ts
        squeeze = 1.0 - 0.15 * min(1.0, age / 0.2)
        al = _al(f, 4.0)
        for k in range(3):   # tre spire impilate
            yy = cy - r * (0.25 + 0.55 * k)
            rx = r * (1.05 - 0.12 * k) * squeeze
            ry = rx * 0.38
            ph = age * 2.0 + k * 0.8
            for half_ in (0, 1):   # 0 = dietro, 1 = davanti
                pts = []
                for i in range(13):
                    an = ph + (math.pi if half_ == 0 else 0) + i / 12 * math.pi
                    pts.append((cx + math.cos(an) * rx, yy + math.sin(an) * ry))
                cols = VINE if half_ else (VINE[0], VINE[0], VINE[1])
                draw_vine(overlay, pts, 0.1 * ts, al if half_ else al // 2, cols, leaves=False)
        if age < 0.25:   # foglioline strappate alla stretta
            k = age / 0.25
            for sg in (-1, 1):
                draw_leaf(overlay, cx + sg * r * (1.1 + 0.6 * k), cy - r * (0.8 + 0.8 * k), sg * 0.8 + age * 9,
                          0.09 * ts, int(255 * (1 - k)))
    elif kind == "snvknot":
        # Laccioerboso: cappio d'erba annodato attorno ai piedi del colpito.
        p = _track(s)
        cx, cy = S(*(p if p is not None else s["c"]))
        r = s.get("r", 0.5) * ts
        tight = 1.0 - 0.35 * min(1.0, age / 0.15)
        al = _al(f, 4.0)
        rect = pygame.Rect(0, 0, int(r * 2 * tight), int(r * 0.8 * tight))
        rect.center = (int(cx), int(cy + 0.05 * ts))
        pygame.draw.ellipse(overlay, (*VINE[0], al), rect.inflate(4, 4), 4)
        pygame.draw.ellipse(overlay, (*VINE[1], al), rect, 2)
        pygame.draw.arc(overlay, (*VINE[2], al), rect, math.pi * 0.55, math.pi * 0.95, 1)
        # nodo con due capi che spuntano
        kx, ky = rect.right - 2, rect.centery
        pygame.draw.circle(overlay, (*VINE[0], al), (kx, ky), 4)
        pygame.draw.circle(overlay, (*VINE[1], al), (kx, ky), 3)
        for sg in (-1, 1):
            _tuft(overlay, kx + sg * 3, ky + 1, 0.22 * ts, al, n=2, lean=sg * 0.3)
    elif kind == "snvsprout":
        # Ciuffo d'erba che spunta da terra, ondeggia e rientra.
        cx, cy = S(*s["c"])
        grow = min(1.0, age / 0.12)
        h = s.get("h", 0.32) * ts * grow * (0.6 + 0.4 * min(1.0, f * 3))
        if h < 1.5:
            return
        al = _al(f, 3.0)
        pygame.draw.ellipse(overlay, (*DIRT[0], al // 2), pygame.Rect(int(cx - h * 0.45), int(cy - 1), int(h * 0.9), 3))
        _tuft(overlay, cx, cy, h, al, n=s.get("n", 3), lean=math.sin(age * 6 + s.get("seed", 0)) * 0.12)
    elif kind == "snvspike":
        # Erbapatto: fascio di spine d'erba che erompe da terra e ricade.
        cx, cy = S(*s["c"])
        up = min(1.0, age / 0.08)
        down = min(1.0, f * 2.5)
        H = s.get("h", 0.8) * ts * up * down
        if H < 2:
            return
        al = _al(f, 3.0)
        pygame.draw.ellipse(overlay, (*DIRT[0], al), pygame.Rect(int(cx - 0.32 * ts), int(cy - 2), int(0.64 * ts), 5))
        rng = random.Random(s.get("seed", 0))
        for i in range(5):
            dx = (i - 2) * 0.09 * ts + rng.uniform(-1.5, 1.5)
            hh = H * (0.55 + 0.45 * (1 - abs(i - 2) / 2)) * rng.uniform(0.85, 1.0)
            lean = (i - 2) * 0.07 * ts
            bw = 0.06 * ts
            tri = [(cx + dx - bw, cy), (cx + dx + lean, cy - hh), (cx + dx + bw, cy)]
            pygame.draw.polygon(overlay, (*LEAF[0], al), [(tri[0][0] - 1, cy + 1), (tri[1][0], tri[1][1] - 1),
                                                          (tri[2][0] + 1, cy + 1)])
            pygame.draw.polygon(overlay, (*LEAF[2 if i < 2 else 1], al), tri)
        pygame.draw.ellipse(overlay, (*DIRT[1], al), pygame.Rect(int(cx - 0.22 * ts), int(cy - 1), int(0.44 * ts), 3))
    elif kind == "snvfield":
        # Campo Erboso: prato tondo (ellisse) che si allarga dal centro, con ciuffi
        # e fiorellini; bordo chiaro che svanisce. Sotto le unità ma è un overlay:
        # resta tenue.
        cx, cy = S(*s["c"])
        R = s.get("r", 3.0) * ts
        grow = min(1.0, age / 0.3)
        e = 1 - (1 - grow) ** 2
        al = _al(f, 3.0)
        rx, ry = R * e, R * 0.6 * e
        if rx < 2:
            return
        lay = pygame.Surface((int(rx * 2) + 6, int(ry * 2) + 6), pygame.SRCALPHA)
        rect = pygame.Rect(3, 3, int(rx * 2), int(ry * 2))
        pygame.draw.ellipse(lay, (*LEAF[1], 60), rect)
        pygame.draw.ellipse(lay, (*LEAF[0], 150), rect, 2)
        pygame.draw.ellipse(lay, (*LEAF[2], 120), rect.inflate(-6, -4), 1)
        lay.set_alpha(al)
        overlay.blit(lay, (cx - rect.centerx, cy - rect.centery))
        rng = random.Random(s.get("seed", 0))
        for i in range(int(s.get("n", 22))):
            an = rng.uniform(0, math.tau)
            d = math.sqrt(rng.random()) * 0.9
            if d > e:
                continue
            x = cx + math.cos(an) * d * R
            y = cy + math.sin(an) * d * R * 0.6
            if i % 5 == 0:   # fiorellino
                fc = FLOWER[1 + (i // 5) % 2]
                for k in range(4):
                    aa = k * math.pi / 2 + 0.4
                    overlay.fill((*fc, al), pygame.Rect(int(x + math.cos(aa) * 2) - 1, int(y + math.sin(aa) * 2) - 1, 2, 2))
                overlay.fill((*FLOWER[0], al), pygame.Rect(int(x), int(y), 1, 1))
            else:
                _tuft(overlay, x, y, 0.2 * ts * (0.7 + 0.3 * math.sin(age * 5 + i)), al, n=3,
                      lean=math.sin(age * 4 + i) * 0.15)
    elif kind == "snvroot":
        # VerdeBufera: radice spinosa che sbuca a terra ad arco, frusta e rientra.
        cx, cy = S(*s["c"])
        L = s.get("r", 0.9) * ts
        up = min(1.0, age / 0.12)
        down = min(1.0, f * 2.2)
        k = up * down
        if k < 0.05:
            return
        ang = s.get("ang", 0.0)
        side = 1 if math.cos(ang) >= 0 else -1
        al = _al(f, 3.0)
        pts = []
        N = 12
        for i in range(N + 1):
            u = i / N
            x = cx + side * L * 0.7 * u
            y = cy - math.sin(u * math.pi * 0.85) * L * k - u * 0.05 * ts
            pts.append((x, y))
        pygame.draw.ellipse(overlay, (*DIRT[0], al), pygame.Rect(int(cx - 5), int(cy - 2), 10, 5))
        draw_vine(overlay, pts, 0.17 * ts, al, VINE, leaves=False, thorns=True)
        if age < 0.2:   # zolle di terra che saltano
            q = age / 0.2
            for sg in (-1, 1):
                overlay.fill((*DIRT[2], int(255 * (1 - q))),
                             pygame.Rect(int(cx + sg * (3 + 6 * q)), int(cy - 7 * q + 6 * q * q), 2, 2))
    elif kind == "snvmark":
        # VerdeBufera: bordo della zona (ellisse tratteggiata che gira) con un
        # velo verde scuro, per tutta la durata.
        cx, cy = S(*s["c"])
        R = s["r"] * ts
        al = int(_al(f, 8.0) * min(1.0, age / 0.2))
        lay = pygame.Surface((int(R * 2) + 8, int(R * 1.2) + 8), pygame.SRCALPHA)
        rect = pygame.Rect(4, 4, int(R * 2), int(R * 1.2))
        pygame.draw.ellipse(lay, (*VINE[0], 60), rect)
        rot = age * 0.8
        n = max(16, int(R * 0.3)) // 2 * 2
        for i in range(0, n, 2):
            a0 = rot + i / n * math.tau
            a1 = a0 + math.tau / n
            p0 = (rect.centerx + math.cos(a0) * rect.w / 2, rect.centery + math.sin(a0) * rect.h / 2)
            p1 = (rect.centerx + math.cos(a1) * rect.w / 2, rect.centery + math.sin(a1) * rect.h / 2)
            pygame.draw.line(lay, (*VINE[0], 230), p0, p1, 3)
            pygame.draw.line(lay, (*LEAF[2], 230), p0, p1, 1)
        lay.set_alpha(al)
        overlay.blit(lay, (cx - rect.centerx, cy - rect.centery))
        # foglie che girano attorno al bordo interno
        for i in range(8):
            an = -age * 1.6 + i / 8 * math.tau
            rr = 0.8 + 0.1 * math.sin(age * 3 + i)
            x = cx + math.cos(an) * R * rr
            y = cy + math.sin(an) * R * 0.6 * rr - 0.25 * ts
            draw_leaf(overlay, x, y, an + math.pi / 2 + age * 6, 0.11 * ts, al)
    elif kind == "snvarc":
        # Vasto Impatto: arco viola del balzo da A a B con la testa luminosa.
        ax, ay = S(*s["a"])
        bx, by = S(*s["b"])
        u = min(1.0, t / 0.7)
        H = s.get("h", 1.6) * ts
        al = _al(f, 3.0)

        def at(v):
            return ax + (bx - ax) * v, ay + (by - ay) * v - math.sin(v * math.pi) * H - 0.4 * ts

        tail = max(0.0, u - 0.45)
        prev = at(tail)
        N = 14
        for i in range(1, N + 1):
            v = tail + (u - tail) * i / N
            p = at(v)
            k = i / N
            pygame.draw.line(overlay, (*DRAGON[0], int(al * k)), prev, p, max(1, int(1 + 6 * k)))
            pygame.draw.line(overlay, (*DRAGON[1], int(al * k)), prev, p, max(1, int(4 * k)))
            if k > 0.5:
                pygame.draw.line(overlay, (*DRAGON[2], int(al * k)), prev, p, 1)
            prev = p
        if u < 1.0:
            hx, hy = at(u)
            pygame.draw.circle(overlay, (*DRAGON[1], 120), (int(hx), int(hy)), int(0.3 * ts))
            pygame.draw.circle(overlay, (*DRAGON[2], 255), (int(hx), int(hy)), max(2, int(0.13 * ts)))


# --- effetti istantanei --------------------------------------------------------------------

def _leaf_burst(fx, c, wait, n=5, cols=LEAF, d=(0.4, 0.8)):
    for _ in range(n):   # foglioline che volano via (riuso della foglia di Rowlet)
        an = random.uniform(0, math.tau)
        dd = random.uniform(*d)
        fx._shape(kind="owlleaf", a=c, b=(c[0] + math.cos(an) * dd, c[1] + math.sin(an) * dd * 0.6 + 0.4),
                  sz=0.1, seed=random.uniform(0, 6), col=cols[1], life=random.uniform(0.3, 0.45), wait=wait)


def fx_snvleaf(fx, e, col):
    """Attacco base: foglia-rasoio che rotea verso il bersaglio."""
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fx._shape(kind="snvleaf", a=a, b=b, sz=0.2, col=LEAF[1], life=(0.06 + L / 22.0) / 0.85)


def _cone_args(e):
    o, d = e.get("o"), e.get("dir")
    if o is None or d is None:
        return None
    return tuple(o), math.atan2(d[1], d[0]), float(e.get("range", 4.0)), math.radians(float(e.get("angle", 38)))


def fx_snvvinelash(fx, e, col, steel=False):
    """Frustata (Codacciaio con la palette d'acciaio): la liana/coda spazza il
    cono; schiocco con stellina in punta a fine corsa."""
    if e.get("kind") != "cone":
        return
    ca = _cone_args(e)
    if ca is None:
        return
    o, ang, rng, ang_full = ca
    half = ang_full / 2
    side = random.choice((-1, 1))
    cols = STEEL if steel else VINE
    life = 0.42
    fx._shape(kind="snvwhip", o=o, ang=ang, half=half, r=rng * 0.92, side=side, cols=cols,
              w=0.2 if steel else 0.16, col=cols[1], life=life)
    tip_a = ang + side * half
    tip = (o[0] + math.cos(tip_a) * rng * 0.85, o[1] + math.sin(tip_a) * rng * 0.85 - 0.15)
    fx._shape(kind="impactstar", c=tip, r=0.24, n=6, rot=random.uniform(0, 1),
              cols=cols, col=cols[1], life=0.18, wait=life * 0.5)
    mid = (o[0] + math.cos(ang) * rng * 0.7, o[1] + math.sin(ang) * rng * 0.7 - 0.35)
    if steel:
        fx._shape(kind="flash", c=mid, r=0.35, col=STEEL[2], life=0.1, wait=life * 0.25)
        _bits(fx, tip, 8, (STEEL[2], (255, 236, 150), WHITE), speed=2.4, life=(0.15, 0.35))
    else:
        _leaf_burst(fx, tip, life * 0.5, n=3)


def fx_snvirontail(fx, e, col):
    fx_snvvinelash(fx, e, col, steel=True)


def fx_snvenergyball(fx, e, col):
    """EnergiPalla: sfera verde che vola; lampo, anello e foglioline all'impatto."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    life = (0.06 + L / 15.0) / 0.9
    fx._shape(kind="snvball", a=a, b=b, r=0.26, col=ENERGY[1], life=life)
    if e.get("hit"):
        w = life * 0.9
        top = (b[0], b[1] - 0.45)
        fx._shape(kind="flash", c=top, r=0.55, col=ENERGY[2], life=0.14, wait=w)
        fx._shape(kind="ring", c=top, r0=0.15, r1=0.75, col=ENERGY[1], life=0.25, wd=0.07, wait=w)
        _leaf_burst(fx, top, w, n=5)


def fx_snvtrail(fx, e, col, glide=False):
    """Apripista: ciuffi d'erba che spuntano lungo lo scatto (la pista).
    Erboscivolata: scivolata su una striscia d'erba più rada + folate corte."""
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
    n = max(3, int(L * (1.6 if glide else 2.4)))
    for i in range(n):
        u = (i + random.uniform(0.2, 0.8)) / n
        o = random.uniform(-0.35, 0.35)
        p = (a[0] + (b[0] - a[0]) * u + px * o, a[1] + (b[1] - a[1]) * u + py * o)
        fx._shape(kind="snvsprout", c=p, h=random.uniform(0.22, 0.36) * (0.8 if glide else 1.0),
                  n=random.choice((3, 3, 4)), seed=random.uniform(0, 6), col=LEAF[1],
                  life=random.uniform(0.6, 0.9), wait=u * 0.12)
    if glide:
        for k in (-1, 1):   # folate CORTE (lunghe sembravano righelli)
            u1 = random.uniform(0.6, 1.0)
            seg = min(L * u1, random.uniform(0.7, 1.0))
            e1 = (a[0] + ux * L * u1 + px * k * 0.28, a[1] + uy * L * u1 + py * k * 0.28 - 0.3)
            fx._shape(kind="windline", a=(e1[0] - ux * seg, e1[1] - uy * seg), b=e1, col=LEAF[2], life=0.25)
    else:
        for _ in range(4):
            u = random.uniform(0.3, 1.0)
            p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u - 0.3)
            _leaf_burst(fx, p, u * 0.12, n=1, d=(0.3, 0.6))
    if e.get("hit"):   # a segno: solo foglie che volano via (la stella copriva entrambi)
        _leaf_burst(fx, (b[0], b[1] - 0.4), 0.05, n=4, d=(0.4, 0.8))


def fx_snvglide(fx, e, col):
    fx_snvtrail(fx, e, col, glide=True)


def fx_snvterrain(fx, e, col):
    """Campo Erboso: prato che si allarga attorno (raggio vero della mossa) con
    ciuffi e fiori, e qualche foglia che sale."""
    c = e.get("c")
    if c is None or e.get("kind") != "buff":
        return
    c = tuple(c)
    fx._shape(kind="snvfield", c=c, r=3.0, n=26, seed=random.randrange(999), col=LEAF[1], life=2.2)
    for i in range(6):
        an = random.uniform(0, math.tau)
        d = random.uniform(0.3, 2.4)
        p = (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.6)
        fx._shape(kind="owlleaf", a=p, b=(p[0] + random.uniform(-0.3, 0.3), p[1] - 1.2), sz=0.1,
                  seed=random.uniform(0, 6), col=LEAF[1], life=random.uniform(0.6, 0.9),
                  wait=random.uniform(0.05, 0.4))


def fx_snvwrap(fx, e, col):
    """Avvolgibotta: la liana si allunga fino al colpito, poi le spire lo
    stringono per tutta la durata del rallentamento (2 s)."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fly = 0.06 + L / 13.0
    life = fly / 0.5 if e.get("hit") else fly / 0.5
    fx._shape(kind="snvreach", a=a, b=b, out=0.5, track=fx.pos_of if e.get("hit") else None,
              tid=e.get("hit_id"), w=0.14, col=VINE[1], life=life)
    if e.get("hit"):
        fx._shape(kind="snvwrap", c=b, r=0.42, track=fx.pos_of, tid=e.get("hit_id"),
                  col=VINE[1], life=2.0, wait=fly)
        fx._shape(kind="impactstar", c=(b[0], b[1] - 0.4), r=0.4, n=6, rot=random.uniform(0, 1),
                  cols=LEAF, col=LEAF[1], life=0.18, wait=fly)


def fx_snvgrassknot(fx, e, col):
    """Laccioerboso: ciuffi che corrono a terra verso il bersaglio, poi un
    cappio d'erba gli stringe i piedi (1 s)."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    fly = 0.06 + L / 13.0
    n = max(3, int(L * 1.6))
    for i in range(n):
        u = (i + 1) / (n + 1)
        p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        fx._shape(kind="snvsprout", c=p, h=0.24, n=3, seed=i, col=LEAF[1], life=0.4, wait=fly * u)
    if e.get("hit"):
        fx._shape(kind="snvknot", c=b, r=0.5, track=fx.pos_of, tid=e.get("hit_id"),
                  col=VINE[1], life=1.2, wait=fly)
        _bits(fx, b, 6, (DIRT[1], DIRT[2], LEAF[1]), speed=1.2, life=(0.2, 0.4))


def fx_snvpledge(fx, e, col):
    """Erbapatto: spine d'erba che erompono in fila da chi lancia al colpito."""
    if e.get("kind") != "projectile":
        return
    ab = _ab(e)
    if ab is None:
        return
    a, b = ab
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L < 1e-3:
        return
    fly = 0.06 + L / 16.0
    n = max(3, int(L / 0.8))
    for i in range(n):
        u = (i + 1) / n
        p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        last = i == n - 1
        fx._shape(kind="snvspike", c=p, h=1.15 if last else 0.6 + 0.2 * u, seed=random.randrange(999),
                  col=LEAF[1], life=0.55 if last else 0.4, wait=fly * u)
    if e.get("hit"):
        fx._shape(kind="impactstar", c=(b[0], b[1] - 0.5), r=0.55, n=7, rot=random.uniform(0, 1),
                  cols=LEAF, col=LEAF[1], life=0.22, wait=fly)
        fx._shape(kind="groundcrack", c=b, r=0.7, n=5, seed=random.randrange(999), col=DIRT[1],
                  life=0.5, wait=fly)
        _shake(fx, 90)


def fx_snvfrenzy(fx, e, col):
    """VerdeBufera. Al lancio (ha "src"): bordo della zona per tutta la durata.
    A ogni tick (senza "src"): radici spinose che sbucano dentro la zona."""
    c = e.get("c")
    if c is None or e.get("kind") != "zone":
        return
    c = tuple(c)
    r = float(e.get("radius", 3.0))
    if e.get("src") is not None:
        fx._shape(kind="snvmark", c=c, r=r, col=VINE[1], life=3.1)
        fx._shape(kind="ring", c=c, r0=0.3, r1=r, col=LEAF[2], life=0.35, wd=0.06)
        _shake(fx, 120)
    for _ in range(5):
        an = random.uniform(0, math.tau)
        d = math.sqrt(random.random()) * r * 0.85
        p = (c[0] + math.cos(an) * d, c[1] + math.sin(an) * d * 0.6)
        fx._shape(kind="snvroot", c=p, r=random.uniform(0.7, 1.1), ang=random.uniform(0, math.tau),
                  col=VINE[1], life=0.55, wait=random.uniform(0.0, 0.25))


def fx_snvvast(fx, e, col):
    """Vasto Impatto: arco viola del balzo, poi schianto (stella, onda,
    crepe, sassi, schermo che trema)."""
    kind = e.get("kind")
    if kind == "dash":
        ab = _ab(e)
        if ab is None:
            return
        a, b = ab
        fx._shape(kind="snvarc", a=a, b=b, h=1.8, col=DRAGON[1], life=0.4)
        return
    if kind != "area":
        return
    c = tuple(e["c"])
    r = float(e.get("radius", 3.2))
    w = 0.22
    # Niente crepe, sassi e lampo: sopra gli sprite sembravano rametti,
    # quadratini marroni e un disco bianco piatto.
    fx._shape(kind="impactstar", c=(c[0], c[1] - 0.3), r=0.7, n=8, rot=random.uniform(0, 1),
              cols=DRAGON, col=DRAGON[1], life=0.24, wait=w)
    # Anelli SOTTILI (il groundring spesso, appena nato, era una ciambella piena).
    fx._shape(kind="ring", c=c, r0=0.6, r1=r, col=DRAGON[1], life=0.4, wd=0.07, wait=w)
    fx._shape(kind="ring", c=c, r0=0.3, r1=r * 0.6, col=DRAGON[2], life=0.32, wd=0.05, wait=w + 0.08)
    _shake(fx, 260)


STYLES = {
    "snvleaf": fx_snvleaf, "snvvinelash": fx_snvvinelash, "snvirontail": fx_snvirontail,
    "snvenergyball": fx_snvenergyball, "snvtrail": fx_snvtrail, "snvglide": fx_snvglide,
    "snvterrain": fx_snvterrain, "snvwrap": fx_snvwrap, "snvgrassknot": fx_snvgrassknot,
    "snvpledge": fx_snvpledge, "snvfrenzy": fx_snvfrenzy, "snvvast": fx_snvvast,
}


# --- sulle unità ---------------------------------------------------------------------------

def draw_unit_overlay(surface, u, gx, gy, now, ts):
    """Inversione: foglioline in orbita attorno al busto, una ogni 10 cariche
    (verdi fino a 50, DORATE quelle oltre, in sovraccarico). Quelle dietro il
    corpo sono più tenui; visibili a tutti."""
    st = int(getattr(u, "inversion_stacks", 0) or 0)
    if st <= 0 or getattr(u, "dex", 0) not in (495, 496, 497):
        return
    n = min(10, (st + 9) // 10)
    r = getattr(u, "radius", 0.5) * ts
    rx, ry = r * 1.25, r * 0.45
    cy = gy - r * 0.9
    for i in range(n):
        an = now * 2.2 + i / n * math.tau
        x = gx + math.cos(an) * rx
        y = cy + math.sin(an) * ry
        behind = math.sin(an) < 0
        cols = GOLD if i >= 5 else LEAF
        draw_leaf(surface, x, y, an + math.pi / 2, max(2.5, 0.09 * ts), 120 if behind else 255, cols)
