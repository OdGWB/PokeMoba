"""Effetti visivi delle mosse: forme geometriche + particelle, colorate per tipo.

Sistema separato dalla logica: legge gli "eventi FX" prodotti dalla simulazione
(engine/match.py, lista fx_events) e li trasforma in effetti puramente cosmetici.

Due livelli:
  - FORME (self.shapes): getti/fasci, anelli d'urto, coni, fendenti — ben visibili,
    disegnati con trasparenza su un overlay e dissolti nel tempo. Sono la parte
    "leggibile" dell'effetto (il getto d'acqua della Pistolacqua, ecc.).
  - PARTICELLE (self.particles): spruzzi/scie di contorno che danno vita.
"""
from __future__ import annotations

import math
import random

import pygame

import config

# Colore per tipo (per le particelle).
TYPE_COLORS = {
    "Normal": (200, 200, 180), "Fire": (240, 120, 50), "Water": (80, 160, 245),
    "Electric": (240, 210, 70), "Grass": (110, 200, 100), "Ice": (150, 220, 230),
    "Fighting": (200, 90, 70), "Poison": (170, 90, 200), "Ground": (210, 170, 100),
    "Flying": (160, 190, 240), "Psychic": (240, 120, 170), "Bug": (170, 200, 80),
    "Rock": (190, 160, 110), "Ghost": (120, 90, 180), "Dragon": (120, 100, 230),
    "Dark": (150, 120, 160), "Steel": (170, 180, 195), "Fairy": (240, 170, 210),
}
MAX_PARTICLES = 1200
MAX_SHAPES = 120

# Colori dei proiettili per SQUADRA (non per tipo): blu = squadra 0, rosso = 1.
# Usati dai pallini dei minion a distanza e dalla sfera d'energia delle torri.
MINION_SHOT_COLORS = {0: (90, 170, 255), 1: (255, 110, 95)}
TOWER_SHOT_COLORS = {0: (120, 205, 255), 1: (255, 135, 70)}

# Stile d'attacco di default per ciascun tipo: usato per i colpi da tiro quando la
# mossa non dichiara un "fx" esplicito. Un "fx" sulla mossa (o "attack_fx" sul
# Pokémon) ha sempre la precedenza. Gli stili sono definiti in FXSystem._FX_STYLES.
TYPE_DEFAULT_FX = {
    "Fire": "flame",   "Water": "jet",    "Electric": "bolt",  "Grass": "leaf",
    "Ice": "shard",    "Rock": "shard",   "Ground": "shard",   "Steel": "shard",
    "Poison": "orb",   "Psychic": "orb",  "Ghost": "orb",      "Fairy": "orb",
    "Dragon": "orb",   "Dark": "orb",     "Bug": "orb",        "Normal": "orb",
    "Fighting": "orb", "Flying": "orb",
}


def type_color(t: str):
    return TYPE_COLORS.get(t, (230, 230, 230))


def _lighten(c, f=0.55):
    return (int(c[0] + (255 - c[0]) * f),
            int(c[1] + (255 - c[1]) * f),
            int(c[2] + (255 - c[2]) * f))


class FXSystem:
    def __init__(self):
        self.particles: list[list] = []  # [x, y, vx, vy, life, maxlife, (r,g,b), size]
        self.shapes: list[dict] = []     # forme geometriche animate

    # --- creazione -----------------------------------------------------------
    def _add(self, x, y, vx, vy, life, color, size):
        if len(self.particles) >= MAX_PARTICLES:
            return
        self.particles.append([x, y, vx, vy, life, life, color, size])

    def _shape(self, **kw):
        if len(self.shapes) >= MAX_SHAPES:
            return
        kw["maxlife"] = kw["life"]
        self.shapes.append(kw)

    def spawn_events(self, events: list[dict]) -> None:
        for e in events:
            col = type_color(e.get("mtype", "Normal"))
            kind = e.get("kind")
            # LIBRERIA STILI: se la mossa/Pokémon dichiara un "fx", disegna la forma
            # dedicata (ricolorata per tipo) invece del raggio/cerchio generico.
            # Aggiungere un effetto nuovo = una voce qui + (se serve) un ramo di
            # disegno in _draw_shapes. Vedi _FX_STYLES in fondo alla classe.
            style = e.get("fx")
            # Se la mossa non dichiara uno stile, per i colpi "da tiro" (proiettili e
            # auto-attacchi a distanza) si usa lo stile di default del TIPO: così ogni
            # Pokémon nuovo prende da solo un effetto a tema, senza doverlo taggare.
            if not style and (kind == "projectile"
                              or (kind == "attack" and not e.get("melee", False))):
                style = TYPE_DEFAULT_FX.get(e.get("mtype", "Normal"))
            handler = self._FX_STYLES.get(style) if style else None
            if handler is not None:
                handler(self, e, col)
                continue
            if kind == "projectile":
                self._beam(e["a"], e["b"], col, width=0.5, life=0.30)
                self._splash(e["b"], 0.6, col, n=10)
            elif kind == "attack":                       # auto-attacco
                if e.get("melee", False):
                    self._slash(e["a"], e["b"], col)
                else:
                    self._beam(e["a"], e["b"], col, width=0.3, life=0.20)
                    self._splash(e["b"], 0.4, col, n=6)
            elif kind == "dash":
                self._beam(e["a"], e["b"], col, width=0.8, life=0.28)
                self._splash(e["b"], 0.8, col, n=14)
            elif kind == "area":
                r = e.get("radius", 1.5)
                self._shape(kind="ring", c=e["c"], r0=r * 0.25, r1=r, col=col, life=0.45, wd=0.22)
                self._splash(e["c"], r, col, n=26)
            elif kind == "zone":
                # Zona persistente (VerdeBufera): anelli lunghi che si sovrappongono
                # tick dopo tick, così il campo resta visibile e "vivo".
                r = e.get("radius", 2.5)
                self._shape(kind="ring", c=e["c"], r0=r * 0.7, r1=r, col=col, life=0.9, wd=0.26)
                self._shape(kind="ring", c=e["c"], r0=r * 0.3, r1=r * 0.65,
                            col=_lighten(col, 0.25), life=0.7, wd=0.18)
                self._splash(e["c"], r * 0.95, col, n=22)
            elif kind == "dive":
                self._shape(kind="ring", c=e["c"], r0=0.2, r1=1.4, col=type_color("Water"),
                            life=0.5, wd=0.18)
                self._splash(e["c"], 1.0, type_color("Water"), n=16)
            elif kind == "blink":   # teletrasporto: poof ai due capi
                for pt in (e["a"], e["b"]):
                    self._shape(kind="ring", c=pt, r0=0.1, r1=1.0, col=col, life=0.35, wd=0.16)
                    self._splash(pt, 0.8, col, n=12)
            elif kind == "cone":
                self._shape(kind="arc", o=e["o"], base=math.atan2(e["dir"][1], e["dir"][0]),
                            half=math.radians(e.get("angle", 45)), rng=e.get("range", 4),
                            col=col, life=0.28)
                self._cone(e["o"], e["dir"], e.get("range", 4), e.get("angle", 45), col)
            elif kind == "buff":
                self._shape(kind="ring", c=e["c"], r0=1.4, r1=0.3, col=col, life=0.5, wd=0.2)
                self._rise(e["c"], col)
            elif kind == "minion_shot":
                self._minion_shot(e)
            elif kind == "tower_shot":
                self._tower_shot(e)

    def _minion_shot(self, e) -> None:
        """Pallino d'energia dei minion a distanza: piccolo (caster) o un po' piu
        grosso (cannone), blu o rosso per squadra, che vola verso il bersaglio."""
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg
        col = MINION_SHOT_COLORS.get(e.get("team", 0), (230, 230, 230))
        big = e.get("big", False)
        self._shape(kind="orb", a=(ax, ay), b=(bx, by), col=col,
                    life=0.26, sz=0.22 if big else 0.15)
        self._splash((bx, by), 0.25 if big else 0.18, col, n=5 if big else 3)

    def _tower_shot(self, e) -> None:
        """Sfera d'energia della torre (stile LoL): proiettile piu grande e
        luminoso, colorato per squadra, con un piccolo impatto sul bersaglio."""
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg
        col = TOWER_SHOT_COLORS.get(e.get("team", 0), (230, 230, 230))
        self._shape(kind="orb", a=(ax, ay), b=(bx, by), col=col, life=0.34, sz=0.5)
        self._splash((bx, by), 0.6, col, n=10)

    # --- libreria stili d'attacco (ricolorabili) ----------------------------
    # Ogni stile è un metodo (self, evento, colore) che traduce un evento della
    # sim in forme/particelle. Il colore arriva già tinto per tipo, quindi la
    # stessa forma si "ricolora" da sola a seconda della mossa che la usa.
    @staticmethod
    def _ab(e):
        """Estremi (a, b) di un evento da tiro, con fallback a bruciapelo."""
        a, b = e.get("a"), e.get("b")
        if a is None or b is None:
            return None
        ax, ay = a
        bx, by = b
        if (bx - ax) ** 2 + (by - ay) ** 2 < 1e-4:
            bx, by = ax + 0.6, ay       # colpo a bruciapelo: dai comunque una direzione
        return ax, ay, bx, by

    def _emit_arrow(self, e, col, scale=1.0):
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg
        base = 0.22 if e.get("melee", False) or e.get("kind") == "attack" else 0.32
        self._shape(kind="arrow", a=(ax, ay), b=(bx, by), col=col,
                    life=base * (1.0 + 0.5 * (scale - 1)), ln=0.9 * scale, sc=scale)
        self._splash((bx, by), 0.35 * scale, col, n=int(6 * scale))

    def _fx_arrow(self, e, col):
        """Freccia scoccata: un dardo che vola da A a B (tiro o auto-attacco), con un
        piccolo impatto all'arrivo. Usata dalla linea di Decidueye (arcieri)."""
        self._emit_arrow(e, col, scale=1.0)

    def _fx_arrow_big(self, e, col):
        """Freccia enorme stile ultimate (Cucitombra): dardo lungo e spesso con scia."""
        self._emit_arrow(e, col, scale=2.6)

    def _emit_travel(self, e, col, kind, spin=False, trail=0, size=0.5, life=0.32):
        """Proiettile generico che viaggia da A a B con una forma dedicata (kind).
        Base comune per leaf/flame/orb/shard: cambia solo il disegno in _draw_shapes."""
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg
        self._shape(kind=kind, a=(ax, ay), b=(bx, by), col=col, life=life,
                    sz=size, spin=spin)
        if trail:
            ang = math.atan2(by - ay, bx - ax)
            for i in range(trail):
                t = i / max(1, trail)
                x = ax + (bx - ax) * t
                y = ay + (by - ay) * t
                self._add(x + random.uniform(-0.1, 0.1), y + random.uniform(-0.1, 0.1),
                          -math.cos(ang) * random.uniform(0.3, 1.0),
                          -math.sin(ang) * random.uniform(0.3, 1.0),
                          random.uniform(0.15, 0.3), _lighten(col, 0.35), random.randint(2, 3))
        self._splash((bx, by), 0.4 * (size / 0.5), col, n=8)

    def _fx_leaf(self, e, col):
        """Erba (default): foglia/lama rotante che plana sul bersaglio."""
        self._emit_travel(e, col, "leaf", spin=True, trail=4, size=0.42)

    def _fx_flame(self, e, col):
        """Fuoco (default): cometa infuocata con scia di braci."""
        self._emit_travel(e, col, "flame", trail=8, size=0.55)

    def _fx_orb(self, e, col):
        """Sfera di energia (default per Spettro/Psico/Drago/Veleno…)."""
        self._emit_travel(e, col, "orb", trail=5, size=0.5)

    def _fx_shard(self, e, col):
        """Scheggia cristallina (default per Ghiaccio/Roccia/Terra/Acciaio)."""
        self._emit_travel(e, col, "shard", spin=True, trail=3, size=0.45)

    def _fx_bolt(self, e, col):
        """Elettro (default): saetta spezzata istantanea da A a B + scintille."""
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg
        self._shape(kind="bolt", a=(ax, ay), b=(bx, by), col=col, life=0.22)
        self._splash((bx, by), 0.45, col, n=10)

    def _fx_drain(self, e, col):
        """Assorbimento (Gigassorbimento): particelle/motes che risalgono dal
        bersaglio fino al lanciatore, come la cura "a risucchio" dei giochi.
        L'evento è un proiettile (a=lanciatore, b=bersaglio): qui si inverte il
        flusso, dai motes che partono da B e convergono su A."""
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg                       # a = lanciatore, b = bersaglio
        ang = math.atan2(ay - by, ax - bx)
        px, py = -math.sin(ang), math.cos(ang)     # perpendicolare al flusso
        self._splash((bx, by), 0.45, col, n=8)     # tocco iniziale sul bersaglio
        for _ in range(12):
            off = random.uniform(-0.55, 0.55)      # ventaglio dal lato del bersaglio
            sx, sy = bx + px * off, by + py * off
            self._shape(kind="orb", a=(sx, sy), b=(ax, ay), col=col,
                        life=random.uniform(0.35, 0.65),
                        sz=random.uniform(0.13, 0.22))
        self._rise((ax, ay), _lighten(col, 0.3))   # scintilla di cura sul lanciatore

    def _fx_jet(self, e, col):
        """Acqua (default): getto spesso (raggio migliorato) con spruzzi."""
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg
        self._beam((ax, ay), (bx, by), col, width=0.45, life=0.26)
        self._splash((bx, by), 0.6, col, n=12)

    def _arrow_fall(self, cx, cy, radius, col, n, height=5.0):
        """Gruppo di frecce che cadono dentro un cerchio (pioggia di frecce)."""
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            r = random.uniform(0, radius)
            gx = cx + math.cos(ang) * r
            gy = cy + math.sin(ang) * r
            sx = gx + random.uniform(-0.6, 0.6)
            sy = gy - height - random.uniform(0, 1.2)       # parte dall'alto
            self._shape(kind="arrow", a=(sx, sy), b=(gx, gy),
                        col=col, life=random.uniform(0.35, 0.55), ln=0.8)

    def _fx_arrow_rain(self, e, col):
        """Pioggia di Frecce: cerchio bersaglio a terra + frecce che piovono."""
        c = e.get("c")
        if c is None:
            return
        r = e.get("radius", 2.0)
        self._shape(kind="ring", c=c, r0=r, r1=r, col=col, life=0.5, wd=0.14)
        self._arrow_fall(c[0], c[1], r, col, n=max(4, int(r * 4)))
        self._splash(c, r, col, n=14)

    def _beam(self, a, b, col, width, life):
        self._shape(kind="beam", a=a, b=b, col=col, w=width, life=life)
        # goccioline lungo il getto
        ax, ay = a
        bx, by = b
        n = 10
        for i in range(n):
            t = i / n
            x = ax + (bx - ax) * t
            y = ay + (by - ay) * t
            self._add(x + random.uniform(-0.1, 0.1), y + random.uniform(-0.1, 0.1),
                      random.uniform(-0.8, 0.8), random.uniform(-0.8, 0.8),
                      random.uniform(0.15, 0.35), _lighten(col, 0.3), random.randint(2, 3))

    def _slash(self, a, b, col):
        """Fendente dell'auto-attacco corpo a corpo: arco breve sul bersaglio."""
        ax, ay = a
        bx, by = b
        ang = math.atan2(by - ay, bx - ax)
        self._shape(kind="slash", c=b, ang=ang, col=_lighten(col, 0.25), life=0.20, rng=0.9)
        self._splash(b, 0.5, col, n=8)

    def _fx_slash(self, e, col):
        """Fendente stretto davanti al lanciatore (Frustata/Codacciaio): un arco
        deciso proprio di fronte, non un cono pieno."""
        o = e.get("o")
        if o is None:
            return
        dx, dy = e.get("dir", (1.0, 0.0))
        rng = float(e.get("range", 3.0))
        ang = math.atan2(dy, dx)
        reach = rng * 0.55
        c = (o[0] + dx * reach, o[1] + dy * reach)
        self._shape(kind="slash", c=c, ang=ang, col=_lighten(col, 0.3),
                    life=0.26, rng=max(1.0, rng * 0.55))
        self._splash(c, rng * 0.4, col, n=10)

    def _splash(self, c, radius, col, n=14):
        cx, cy = c
        for _ in range(n):
            a = random.uniform(0, math.tau)
            r = random.uniform(0, radius)
            sp = random.uniform(1.5, 4.5)
            self._add(cx + math.cos(a) * r, cy + math.sin(a) * r,
                      math.cos(a) * sp, math.sin(a) * sp,
                      random.uniform(0.25, 0.5), col, random.randint(2, 3))

    def _cone(self, o, d, rng, angle, col):
        ox, oy = o
        base = math.atan2(d[1], d[0])
        half = math.radians(angle)
        for _ in range(24):
            a = base + random.uniform(-half, half)
            r = random.uniform(0, rng)
            sp = random.uniform(2.0, 5.0)
            self._add(ox + math.cos(a) * r, oy + math.sin(a) * r,
                      math.cos(a) * sp, math.sin(a) * sp,
                      random.uniform(0.2, 0.45), col, random.randint(2, 3))

    def _rise(self, c, col):
        cx, cy = c
        for _ in range(20):
            self._add(cx + random.uniform(-0.9, 0.9), cy + random.uniform(-0.3, 0.3),
                      random.uniform(-0.3, 0.3), random.uniform(-1.8, -0.8),
                      random.uniform(0.4, 0.75), _lighten(col, 0.3), random.randint(2, 3))

    # --- aggiornamento / disegno --------------------------------------------
    def update(self, dt: float) -> None:
        alive = []
        for pt in self.particles:
            pt[4] -= dt
            if pt[4] <= 0:
                continue
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[2] *= 0.90
            pt[3] *= 0.90
            alive.append(pt)
        self.particles = alive
        sh = []
        for s in self.shapes:
            s["life"] -= dt
            if s["life"] > 0:
                sh.append(s)
        self.shapes = sh

    def draw(self, surface, camera) -> None:
        ts = config.TILE_SIZE
        if self.shapes:
            self._draw_shapes(surface, camera, ts)
        bg = (18, 20, 24)
        for x, y, _vx, _vy, life, maxlife, col, size in self.particles:
            sx, sy = camera.world_to_screen(x * ts, y * ts)
            f = max(0.0, min(1.0, life / maxlife))
            c = (int(bg[0] + (col[0] - bg[0]) * f),
                 int(bg[1] + (col[1] - bg[1]) * f),
                 int(bg[2] + (col[2] - bg[2]) * f))
            pygame.draw.circle(surface, c, (sx, sy), size)

    def _draw_shapes(self, surface, camera, ts):
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)

        def S(wx, wy):
            return camera.world_to_screen(wx * ts, wy * ts)

        for s in self.shapes:
            f = max(0.0, min(1.0, s["life"] / s["maxlife"]))
            a = int(230 * f)
            col = s["col"]
            kind = s["kind"]
            if kind == "beam":
                ax, ay = S(*s["a"])
                bx, by = S(*s["b"])
                w = max(2, int(s["w"] * ts))
                pygame.draw.line(overlay, (*col, a // 3), (ax, ay), (bx, by), w + 5)
                pygame.draw.line(overlay, (*col, a), (ax, ay), (bx, by), w)
                pygame.draw.line(overlay, (*_lighten(col), a), (ax, ay), (bx, by), max(2, w // 2))
            elif kind == "ring":
                cx, cy = S(*s["c"])
                r = int((s["r0"] + (s["r1"] - s["r0"]) * (1 - f)) * ts)
                wd = max(2, int(s.get("wd", 0.18) * ts))
                pygame.draw.circle(overlay, (*_lighten(col), a), (cx, cy), max(1, r), wd)
            elif kind == "arc":
                ox, oy = S(*s["o"])
                base, half, rng = s["base"], s["half"], s["rng"] * ts
                pts = [(ox, oy)]
                steps = 12
                for i in range(steps + 1):
                    ang = base - half + (2 * half) * (i / steps)
                    pts.append((ox + math.cos(ang) * rng, oy + math.sin(ang) * rng))
                pygame.draw.polygon(overlay, (*col, a // 2), pts)
                pygame.draw.polygon(overlay, (*_lighten(col), a), pts, 2)
            elif kind == "slash":
                cx, cy = S(*s["c"])
                rng = s["rng"] * ts
                perp = s["ang"] + math.pi / 2
                grow = (1 - f) * 0.5 + 0.6
                dx, dy = math.cos(perp) * rng * grow, math.sin(perp) * rng * grow
                pygame.draw.line(overlay, (*col, a), (cx - dx, cy - dy), (cx + dx, cy + dy),
                                 max(2, int(0.18 * ts)))
            elif kind == "arrow":
                ax, ay = S(*s["a"])
                bx, by = S(*s["b"])
                sc = s.get("sc", 1.0)
                ang = math.atan2(by - ay, bx - ax)
                t = 1 - f                                   # avanzamento 0->1 nel tempo
                tipx = ax + (bx - ax) * t
                tipy = ay + (by - ay) * t
                ca, sa = math.cos(ang), math.sin(ang)
                px, py = -sa, ca                            # versore perpendicolare
                shaft = s.get("ln", 0.9) * ts
                tailx, taily = tipx - ca * shaft, tipy - sa * shaft
                lite = _lighten(col)
                if sc > 1.5:   # frecce grandi (ulti): alone/scia luminosa dietro la punta
                    pygame.draw.line(overlay, (*col, a // 3),
                                     (tailx, taily), (tipx, tipy), max(3, int(0.26 * sc * ts)))
                # asta
                pygame.draw.line(overlay, (*col, a), (tailx, taily), (tipx, tipy),
                                 max(2, int(0.08 * sc * ts)))
                # punta (triangolo)
                hl, hw = 0.30 * sc * ts, 0.17 * sc * ts
                basex, basey = tipx - ca * hl, tipy - sa * hl
                pygame.draw.polygon(overlay, (*lite, a), [
                    (tipx, tipy),
                    (basex + px * hw, basey + py * hw),
                    (basex - px * hw, basey - py * hw)])
                # impennaggio (due alette alla coda)
                fw, fb = 0.15 * sc * ts, 0.22 * sc * ts
                for sgn in (1, -1):
                    pygame.draw.line(overlay, (*lite, a), (tailx, taily),
                                     (tailx - ca * fb + px * fw * sgn,
                                      taily - sa * fb + py * fw * sgn),
                                     max(1, int(0.05 * sc * ts)))
            elif kind in ("leaf", "flame", "orb", "shard"):
                # Proiettili che viaggiano da A a B; la punta avanza nel tempo.
                ax, ay = S(*s["a"])
                bx, by = S(*s["b"])
                t = 1 - f
                cx = ax + (bx - ax) * t
                cy = ay + (by - ay) * t
                r = max(2, int(s.get("sz", 0.5) * ts))
                lite = _lighten(col)
                ang = math.atan2(by - ay, bx - ax)
                if s.get("spin"):
                    ang += (1 - f) * 10.0                   # rotazione nel volo
                ca, sa = math.cos(ang), math.sin(ang)
                px, py = -sa, ca
                if kind == "orb":
                    pygame.draw.circle(overlay, (*col, a // 3), (int(cx), int(cy)), int(r * 1.8))
                    pygame.draw.circle(overlay, (*col, a), (int(cx), int(cy)), r)
                    pygame.draw.circle(overlay, (*lite, a), (int(cx), int(cy)), max(1, r // 2))
                elif kind == "flame":
                    # cometa: alone + testa + lingua di fuoco all'indietro
                    pygame.draw.circle(overlay, (*col, a // 3), (int(cx), int(cy)), int(r * 1.9))
                    tail = [(cx + ca * r, cy + sa * r),
                            (cx + px * r * 0.7, cy + py * r * 0.7),
                            (cx - ca * r * 2.2, cy - sa * r * 2.2),
                            (cx - px * r * 0.7, cy - py * r * 0.7)]
                    pygame.draw.polygon(overlay, (*col, a), tail)
                    pygame.draw.circle(overlay, (*lite, a), (int(cx), int(cy)), max(1, int(r * 0.7)))
                elif kind == "leaf":
                    # foglia: rombo appuntito (lama)
                    pts = [(cx + ca * r * 1.6, cy + sa * r * 1.6),
                           (cx + px * r * 0.6, cy + py * r * 0.6),
                           (cx - ca * r * 1.6, cy - sa * r * 1.6),
                           (cx - px * r * 0.6, cy - py * r * 0.6)]
                    pygame.draw.polygon(overlay, (*col, a), pts)
                    pygame.draw.polygon(overlay, (*lite, a), pts, 2)
                else:  # shard: cristallo angolare
                    pts = [(cx + ca * r * 1.5, cy + sa * r * 1.5),
                           (cx + px * r * 0.8, cy + py * r * 0.8),
                           (cx - ca * r * 0.8, cy - sa * r * 0.8),
                           (cx - px * r * 0.8, cy - py * r * 0.8)]
                    pygame.draw.polygon(overlay, (*lite, a), pts)
                    pygame.draw.polygon(overlay, (*col, a), pts, 2)
            elif kind == "bolt":
                # saetta: polilinea spezzata da A a B (istantanea)
                ax, ay = S(*s["a"])
                bx, by = S(*s["b"])
                ang = math.atan2(by - ay, bx - ax)
                px, py = -math.sin(ang), math.cos(ang)
                dist = math.hypot(bx - ax, by - ay)
                seg = max(3, int(dist / (0.6 * ts) + 1))
                pts = []
                for i in range(seg + 1):
                    u = i / seg
                    jitter = 0 if i in (0, seg) else random.uniform(-0.22, 0.22) * ts
                    pts.append((ax + (bx - ax) * u + px * jitter,
                                ay + (by - ay) * u + py * jitter))
                lite = _lighten(col)
                pygame.draw.lines(overlay, (*col, a // 3), False, pts, max(3, int(0.22 * ts)))
                pygame.draw.lines(overlay, (*lite, a), False, pts, max(2, int(0.08 * ts)))
        surface.blit(overlay, (0, 0))

    # Registro degli stili d'attacco: nome ("fx" nel JSON / "attack_fx") -> handler.
    # Questa è la "libreria": per aggiungerne uno, scrivi un _fx_* qui sopra, una voce
    # qui, e (se è una forma nuova) un ramo di disegno in _draw_shapes.
    _FX_STYLES = {
        "arrow": _fx_arrow,
        "arrow_big": _fx_arrow_big,
        "arrow_rain": _fx_arrow_rain,
        "leaf": _fx_leaf,
        "flame": _fx_flame,
        "orb": _fx_orb,
        "shard": _fx_shard,
        "bolt": _fx_bolt,
        "jet": _fx_jet,
        "drain": _fx_drain,
        "slash": _fx_slash,
    }
