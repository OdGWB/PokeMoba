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

from . import (arch_fx, charcadet_fx, corvi_fx, eevee_fx, hatt_fx, mag_fx, mien_fx, noivern_fx,
               sneasel_fx, swine_fx, ursa_fx)
from . import structure_gfx

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
MAX_SHAPES = 240

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


def _darken(c, f=0.5):
    return (int(c[0] * (1 - f)), int(c[1] * (1 - f)), int(c[2] * (1 - f)))


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
# Spiritomb: spiriti verde lime, Buio violetto.
SPIRIT = (160, 236, 52)
SPIRIT_HI = (214, 255, 128)
SPIRIT_DK = (70, 140, 30)
DARKV = (96, 58, 140)
DARKV_DK = (40, 26, 58)

_PUFF_CACHE: dict = {}


def _smoke_puff(r: int, shade: int):
    """Nuvoletta di fumo grigio scuro in cache: strati concentrici a gradini (bordo
    morbido semitrasparente -> centro piu' scuro e opaco) + lobo chiaro in alto a
    sinistra per dare volume. Pixel-art: niente gradienti continui."""
    key = (r, shade)
    spr = _PUFF_CACHE.get(key)
    if spr is None:
        spr = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        c = r + 1
        g = 46 + 9 * shade
        for i, (f, al, dg) in enumerate(((1.0, 70, 0), (0.86, 120, 4), (0.7, 170, 9),
                                         (0.52, 205, 14))):
            pygame.draw.circle(spr, (g + dg, g + dg, g + dg + 6, al), (c, c), max(2, int(r * f)))
        _PUFF_CACHE[key] = spr
    return spr


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
        grosso (cannone), blu o rosso per squadra, che vola verso il bersaglio.
        Pallino OPACO e netto (niente particelle che lo seguono)."""
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg
        col = MINION_SHOT_COLORS.get(e.get("team", 0), (230, 230, 230))
        big = e.get("big", False)
        life = 0.26
        self._shape(kind="energy", a=(ax, ay), b=(bx, by), col=col, life=life,
                    sz=0.2 if big else 0.15, lift_a=0.45, lift_b=0.45, trail=4)
        self._impact((bx, by - 0.45), col, 0.35 if big else 0.25, life)

    def _tower_shot(self, e) -> None:
        """Sfera d'energia della torre (stile LoL): proiettile OPACO molto piu
        grande, colorato per squadra, con un alone luminoso. Niente particelle."""
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg
        col = TOWER_SHOT_COLORS.get(e.get("team", 0), (230, 230, 230))
        life = 0.36
        # parte dalla GEMMA in cima alla torre e colpisce il bersaglio al busto
        self._shape(kind="energy", a=(ax, ay), b=(bx, by), col=col, life=life,
                    sz=0.3, lift_a=structure_gfx.gem_height_tiles(), lift_b=0.45, trail=7)
        self._impact((bx, by - 0.45), col, 0.7, life)

    def _impact(self, c, col, r, wait) -> None:
        """Lampo + anello d'impatto, che compaiono quando il colpo arriva."""
        self._shape(kind="flash", c=c, r=r, col=col, life=0.16, wait=wait)
        self._shape(kind="ring", c=c, r0=r * 0.3, r1=r * 1.4, col=col, life=0.2,
                    wd=0.07, wait=wait)

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

    def _fx_arcbubble(self, e, col):
        """Bolla: una vera bolla che vola in ARCO (sale e ridiscende) verso il
        punto mirato, con un cerchio-bersaglio TELEGRAFATO che si chiude mentre la
        bolla è in volo; all'atterraggio (evento 'area' separato) fa il botto."""
        a, b = e.get("a"), e.get("b")
        if a is not None and b is not None:
            r = float(e.get("radius", 1.6))
            delay = float(e.get("delay", 0.55))
            self._shape(kind="target", c=b, r=r, col=col, life=delay)
            self._shape(kind="bubbleorb", a=a, b=b, col=col, life=delay,
                        sz=0.5, arc=2.6)
        else:   # impatto all'atterraggio
            c = e.get("c")
            if c is None:
                return
            r = float(e.get("radius", 1.6))
            self._shape(kind="ring", c=c, r0=r * 0.2, r1=r,
                        col=_lighten(col, 0.25), life=0.42, wd=0.2)
            self._splash(c, r * 0.75, col, n=18)

    def _fx_vortex(self, e, col):
        """Mulinello: vortice PERSISTENTE a terra per tutta la durata (un'unica
        forma che gira), con un tocco di spruzzi iniziali."""
        c = e.get("c")
        if c is None:
            return
        r = float(e.get("radius", 2.0))
        dur = float(e.get("dur", 1.5))
        self._shape(kind="vortex", c=c, r=r, col=col, life=dur)
        self._splash(c, r * 0.6, col, n=12)

    def _fx_smoke(self, e, col):
        """Muro di Fumo: nube grigia soffice e persistente (indipendente dal tipo).
        Anelli morbidi + sbuffi che oscurano la zona per tutta la durata."""
        c = e.get("c")
        if c is None:
            return
        r = float(e.get("radius", 2.5))
        # L'evento si ripete ogni tick: rinnova la nuvola solo quando la precedente
        # sta per sparire (niente sfarfallio di nuvolette ricreate a caso).
        for s in self.shapes:
            if (s["kind"] == "smokecloud" and s["c"] == tuple(c)
                    and s["life"] > 0.8):
                return
        puffs = []
        n = max(18, int(r * r * 4))
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            rad = r * 0.75 * math.sqrt(random.random())
            puffs.append((math.cos(ang) * rad, math.sin(ang) * rad * 0.85,
                          random.uniform(0.85, 1.25) * (1.1 - 0.3 * rad / r),
                          random.uniform(0, math.tau), random.uniform(0.0, 1.0)))
        self._shape(kind="smokecloud", c=tuple(c), col=(70, 70, 76), life=1.2,
                    puffs=puffs)

    def _fx_flurry(self, e, col):
        """Zuffa: raffica di PUGNI che volano attorno al lanciatore (sfalsati nel
        tempo), più un'onda d'urto. Rende visibile l'attivazione della mossa."""
        c = e.get("c") or e.get("o")
        if c is None:
            return
        cx, cy = c
        r = float(e.get("radius", 2.0))
        lite = _lighten(col, 0.25)
        self._shape(kind="ring", c=c, r0=0.3, r1=r, col=lite, life=0.4, wd=0.22)
        n = max(6, int(r * 4))
        for i in range(n):
            ang = random.uniform(0, math.tau)
            dist = random.uniform(r * 0.4, r)
            bx, by = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist
            self._shape(kind="punch", a=(cx, cy), b=(bx, by), col=col,
                        life=0.22, sz=0.42, wait=i * 0.03)
        self._splash(c, r * 0.8, col, n=16)

    # --- linea Roggenrola: roccia, sabbia, onde d'urto ----------------------
    def _dust(self, c, radius, n=10, col=DUST, speed=(0.8, 2.6)):
        """Sbuffi di polvere TRASLUCIDI che si allargano e svaniscono (forme
        'puff': le particelle normali sfumano verso il nero, sembrerebbero
        puntini scuri). Circa uno sbuffo ogni due unità di `n`."""
        cx, cy = c
        for _ in range(max(2, n // 2)):
            a = random.uniform(0, math.tau)
            r = random.uniform(0, radius)
            sp = random.uniform(*speed) * 0.5
            self._shape(kind="puff", c=(cx + math.cos(a) * r, cy + math.sin(a) * r * 0.7),
                        v=(math.cos(a) * sp, math.sin(a) * sp * 0.6 - 0.25),
                        r0=random.uniform(0.12, 0.2), r1=random.uniform(0.3, 0.5),
                        col=col, life=random.uniform(0.45, 0.8))

    def _debris(self, c, radius, n, col=ROCK_MID, life=(0.3, 0.5), size=(0.16, 0.26)):
        """Schegge di roccia che volano via dal centro (forme 'shard')."""
        cx, cy = c
        for _ in range(n):
            a = random.uniform(0, math.tau)
            d = random.uniform(radius * 0.5, radius)
            self._shape(kind="shard", a=(cx, cy), b=(cx + math.cos(a) * d, cy + math.sin(a) * d),
                        col=col, life=random.uniform(*life), sz=random.uniform(*size), spin=True)

    def _fx_rockspike(self, e, col):
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
            self._shape(kind="rockspike", c=(x, y), h=h, w=random.uniform(0.24, 0.38),
                        lean=random.uniform(-0.12, 0.12), col=col,
                        life=random.uniform(0.6, 0.8))
        self._dust(c, r * 0.6, n=3, speed=(0.4, 1.4))

    def _fx_pillar(self, e, col):
        """Pilastro che spunta: anello di polvere alla base + sassolini."""
        c = e.get("c")
        if c is None:
            return
        self._shape(kind="ring", c=c, r0=0.25, r1=1.0, col=DUST, life=0.4, wd=0.16)
        self._dust(c, 0.6, n=12)
        if e.get("explosive"):
            self._dust(c, 0.5, n=8, col=EMBER, speed=(1.5, 3.0))   # Pietrataglio: scintille

    def _fx_pillarbreak(self, e, col):
        """Pilastro che si sbriciola a fine durata."""
        c = e.get("c")
        if c is None:
            return
        self._debris(c, 0.9, 7, col=ROCK_MID, life=(0.25, 0.4), size=(0.12, 0.2))
        self._dust(c, 0.6, n=12)

    def _fx_shockwave(self, e, col):
        """Pesobomba contro un muro/pilastro: onda d'urto a terra + crepe
        radiali + detriti (stessa forma per il rilancio della valanga)."""
        c = e.get("c")
        if c is None:
            return
        r = float(e.get("radius", 2.2))
        self._shape(kind="ring", c=c, r0=0.3, r1=r, col=DUST, life=0.45, wd=0.3)
        self._shape(kind="ring", c=c, r0=0.2, r1=r * 0.7, col=ROCK_HI, life=0.3, wd=0.14)
        cracks = []
        for k in range(7):
            ang = k * math.tau / 7 + random.uniform(-0.25, 0.25)
            pts, rr, a2 = [(0.0, 0.0)], 0.0, ang
            while rr < r * 0.8:
                rr += random.uniform(0.25, 0.45)
                a2 += random.uniform(-0.35, 0.35)
                pts.append((math.cos(a2) * rr, math.sin(a2) * rr * 0.75))
            cracks.append(pts)
        self._shape(kind="crack", c=c, cracks=cracks, col=ROCK_OUT, life=0.9)
        self._debris(c, r * 0.8, 8)
        self._dust(c, r * 0.8, n=20)

    def _fx_rockburst(self, e, col):
        """Esplosione di un pilastro (Pietrataglio) / valanga che si schianta."""
        c = e.get("c")
        if c is None:
            return
        r = float(e.get("radius", 2.0))
        self._shape(kind="ring", c=c, r0=0.2, r1=r, col=EMBER, life=0.35, wd=0.22)
        self._shape(kind="ring", c=c, r0=0.2, r1=r * 0.8, col=ROCK_HI, life=0.45, wd=0.16)
        self._debris(c, r, 12, life=(0.3, 0.55), size=(0.18, 0.3))
        self._dust(c, r * 0.7, n=22)
        self._dust(c, r * 0.4, n=10, col=EMBER, speed=(2.0, 4.0))

    def _fx_chargedust(self, e, col):
        """Pesobomba: scia di polvere sollevata dietro la carica."""
        a = e.get("a")
        if a is None:
            return
        self._dust(a, 0.35, n=3, speed=(0.3, 1.2))

    def _fx_knockup(self, e, col):
        """Nemico lanciato in aria: sbuffo di polvere ai piedi."""
        c = e.get("c")
        if c is None:
            return
        self._shape(kind="ring", c=c, r0=0.15, r1=0.75, col=DUST, life=0.3, wd=0.12)
        self._dust(c, 0.35, n=8)

    def _fx_smackdown(self, e, col):
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
            self._shape(kind="fallrock", c=(gx, gy), h=4.0, sz=random.uniform(0.22, 0.34),
                        col=col, life=fall, wait=w)
            self._shape(kind="ring", c=(gx, gy), r0=0.1, r1=0.6, col=DUST, life=0.3,
                        wd=0.1, wait=w + fall)
        self._shape(kind="ring", c=c, r0=r * 0.4, r1=r, col=ROCK_HI, life=0.4, wd=0.2,
                    wait=0.2)
        self._dust(c, r * 0.8, n=18)

    def _fx_smackzone(self, e, col):
        """Zona di Abbattimento ancora attiva: cerchio tratteggiato che ruota."""
        c = e.get("c")
        if c is None:
            return
        self._shape(kind="smackzone", c=c, r=float(e.get("radius", 2.4)), col=ROCK_HI,
                    life=float(e.get("dur", 2.0)))

    def _fx_spikefield(self, e, col):
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
        self._shape(kind="spikefield", c=c, r=r, stones=stones, col=col,
                    life=float(e.get("dur", 8.0)))

    def _fx_sandburst(self, e, col):
        """Terrempesta: la tempesta si allarga di colpo (anello di sabbia)."""
        c = e.get("c")
        if c is None:
            return
        r = float(e.get("radius", 6.0))
        self._shape(kind="ring", c=c, r0=1.0, r1=r, col=SAND, life=0.6, wd=0.35)
        self._shape(kind="ring", c=c, r0=0.5, r1=r * 0.7, col=SAND_DK, life=0.45, wd=0.2)
        self._dust(c, r * 0.6, n=30, col=SAND, speed=(1.5, 4.0))

    def _fx_ironshell(self, e, col):
        """Ferroscudo: guscio esagonale d'acciaio che si chiude sul Pokémon."""
        c = e.get("c")
        if c is None:
            return
        self._shape(kind="hexshell", c=c, r=0.95, col=col, life=0.7)
        self._rise(c, _lighten(col, 0.4))

    def _fx_avalanchewarn(self, e, col):
        """Frana: telegraph del percorso (corsia + frecce che scorrono verso
        Gigalith) per il ritardo prima che la valanga parta."""
        c, b = e.get("c"), e.get("b")
        if c is None or b is None:
            return
        delay = float(e.get("delay", 0.6))
        self._shape(kind="avwarn", a=c, b=b, r=float(e.get("radius", 1.5)), col=SAND_DK,
                    life=delay + 0.35)
        self._shape(kind="ring", c=c, r0=0.4, r1=float(e.get("radius", 1.5)),
                    col=ROCK_HI, life=delay, wd=0.14)
        self._dust(c, float(e.get("radius", 1.5)), n=16)

    def _fx_explodecharge(self, e, col):
        """Esplosione in carica: telegraph rosso-arancio che pulsa sempre più
        forte attorno a Gigalith (ripetuto a ogni tick: aggiorna la stessa forma)."""
        c = e.get("c")
        if c is None:
            return
        t = float(e.get("t", 0.0))
        for s in self.shapes:
            if s["kind"] == "chargeglow" and abs(s["c"][0] - c[0]) + abs(s["c"][1] - c[1]) < 1.5:
                s["c"], s["t"], s["life"] = tuple(c), t, 0.15
                return
        self._shape(kind="chargeglow", c=tuple(c), r=float(e.get("radius", 3.0)), t=t,
                    col=EMBER, life=0.15)

    def _fx_explosion(self, e, col):
        """Esplosione: lampo, palla di fuoco che si espande, fumo e schegge."""
        c = e.get("c")
        if c is None:
            return
        r = float(e.get("radius", 3.0))
        self._shape(kind="flash", c=c, r=r * 0.8, col=(255, 240, 210), life=0.18)
        self._shape(kind="ring", c=c, r0=0.4, r1=r, col=EMBER, life=0.45, wd=0.5)
        self._shape(kind="ring", c=c, r0=0.3, r1=r * 1.1, col=(255, 220, 150), life=0.3,
                    wd=0.2)
        self._shape(kind="ring", c=c, r0=r * 0.5, r1=r * 1.15, col=DUST, life=0.6, wd=0.3,
                    wait=0.1)
        self._debris(c, r * 1.1, 16, life=(0.35, 0.6), size=(0.18, 0.32))
        self._dust(c, r * 0.6, n=24, col=EMBER, speed=(2.5, 5.0))
        self._dust(c, r * 0.9, n=34, col=(110, 100, 90), speed=(1.0, 3.5))

    # --- Spiritomb: spiriti verde lime, Buio ----------------------------------
    def _wisps(self, c, radius, n, col=SPIRIT, rise=1.4):
        """Fiammelle-sbuffo che salgono (sbuffi traslucidi verdi che derivano in su)."""
        cx, cy = c
        for _ in range(n):
            a = random.uniform(0, math.tau)
            r = random.uniform(0, radius)
            self._shape(kind="puff", c=(cx + math.cos(a) * r, cy + math.sin(a) * r * 0.6),
                        v=(math.cos(a) * 0.3, -random.uniform(0.6, rise)),
                        r0=random.uniform(0.08, 0.14), r1=random.uniform(0.2, 0.34),
                        col=col, life=random.uniform(0.4, 0.75))

    def _fx_spiritshot(self, e, col):
        """Auto-attacco di Spiritomb: fiammella verde che vola al bersaglio."""
        seg = self._ab(e)
        if seg is None:
            return
        ax, ay, bx, by = seg
        self._shape(kind="shot", a=(ax, ay), b=(bx, by), col=SPIRIT, life=0.24, sz=0.2,
                    glow=0.45)
        self._wisps((bx, by), 0.25, 2)

    def _fx_spiritpick(self, e, col):
        """Spirito raccolto: lampo verde e fiammelle che salgono."""
        c = e.get("c")
        if c is None:
            return
        self._shape(kind="flash", c=c, r=0.5, col=SPIRIT_HI, life=0.16)
        self._shape(kind="ring", c=c, r0=0.15, r1=0.9, col=SPIRIT, life=0.35, wd=0.12)
        self._wisps(c, 0.4, 7, rise=2.2)

    def _fx_spiritawaken(self, e, col):
        """Risveglio (36/72/108): colonna di spiriti attorno a Spiritomb."""
        c = e.get("c")
        if c is None:
            return
        lvl = int(e.get("lvl", 1))
        self._shape(kind="flash", c=c, r=1.0 + 0.3 * lvl, col=SPIRIT_HI, life=0.25)
        for k in range(3):
            self._shape(kind="ring", c=c, r0=0.3, r1=1.4 + 0.5 * lvl, col=SPIRIT,
                        life=0.5, wd=0.16, wait=k * 0.12)
        self._wisps(c, 1.0 + 0.3 * lvl, 14 + 6 * lvl, rise=3.0)

    def _fx_spiritburst(self, e, col):
        """Spirito Vagante: gli spiriti esplodono attorno al bersaglio."""
        c = e.get("c")
        if c is None:
            return
        r = float(e.get("radius", 1.0))
        self._shape(kind="ring", c=c, r0=0.2, r1=r, col=SPIRIT, life=0.35, wd=0.18)
        self._shape(kind="ring", c=c, r0=0.1, r1=r * 0.6, col=SPIRIT_HI, life=0.25, wd=0.1)
        self._wisps(c, r * 0.8, 6 + int(r * 4))

    def _fx_spiritbeamhit(self, e, col):
        """Stordiraggio/Neropulsar/Finta: colpo sul bersaglio o contro un muro."""
        c = e.get("c")
        if c is None:
            return
        tint = SPIRIT if e.get("mtype") == "Ghost" else DARKV
        self._shape(kind="flash", c=c, r=0.45, col=_lighten(tint, 0.4), life=0.14)
        self._shape(kind="ring", c=c, r0=0.1, r1=0.8 if e.get("wall") else 0.6, col=tint,
                    life=0.3, wd=0.12)
        self._wisps(c, 0.3, 4, col=tint)

    def _fx_spiritbind(self, e, col):
        """Combo di Stordiraggio: stelline di stordimento su entrambi i bersagli."""
        for pt in e.get("pts", []):
            self._shape(kind="ring", c=pt, r0=0.7, r1=0.2, col=(250, 230, 120), life=0.4,
                        wd=0.14)
            self._wisps(pt, 0.3, 4, col=(250, 230, 120))
        if len(e.get("pts", [])) < 2:   # contro un muro: crepa di luce sul muro
            self._shape(kind="flash", c=e["c"], r=0.6, col=SPIRIT_HI, life=0.18)

    def _fx_painlink(self, e, col):
        c = e.get("c")
        if c is not None:
            self._shape(kind="ring", c=c, r0=0.2, r1=1.0, col=SPIRIT, life=0.3, wd=0.1)

    def _fx_painsplit(self, e, col):
        """Fine di Malcomune: gli HP si dividono (lampo su tutti i legati)."""
        for pt in e.get("pts", []):
            self._shape(kind="flash", c=pt, r=0.5, col=(240, 200, 255), life=0.2)
            self._shape(kind="ring", c=pt, r0=0.9, r1=0.2, col=(200, 120, 230), life=0.35,
                        wd=0.12)
            self._wisps(pt, 0.35, 5, col=(200, 140, 240))

    def _fx_spiritwarp(self, e, col):
        """Teletrasporto di Richiamo degli Spiriti / ritorno da Memento."""
        for i, key in enumerate(("a", "b")):
            pt = e.get(key)
            if pt is None:
                continue
            self._shape(kind="ring", c=pt, r0=0.1 if i else 0.9, r1=0.9 if i else 0.1,
                        col=SPIRIT, life=0.35, wd=0.14)
            self._wisps(pt, 0.5, 9, rise=2.4)

    def _fx_legioncast(self, e, col):
        c = e.get("c")
        if c is None:
            return
        self._shape(kind="flash", c=c, r=1.4, col=SPIRIT_HI, life=0.22)
        self._wisps(c, 1.0, 18, rise=2.8)

    def _fx_legionally(self, e, col):
        c = e.get("c")
        if c is not None:
            self._shape(kind="ring", c=c, r0=0.9, r1=0.3, col=SPIRIT_HI, life=0.4, wd=0.12)
            self._wisps(c, 0.4, 5)

    def _fx_legionfear(self, e, col):
        c = e.get("c")
        if c is not None:
            self._shape(kind="ring", c=c, r0=0.2, r1=0.9, col=DARKV, life=0.35, wd=0.14)
            self._wisps(c, 0.4, 6, col=DARKV)

    def _fx_memento(self, e, col):
        """Memento: Spiritomb si dissolve in un'onda d'ombra."""
        c = e.get("c")
        if c is None:
            return
        r = float(e.get("radius", 4.0))
        self._shape(kind="ring", c=c, r0=0.3, r1=r, col=DARKV, life=0.5, wd=0.3)
        self._shape(kind="ring", c=c, r0=0.2, r1=r * 0.7, col=SPIRIT, life=0.4, wd=0.12)
        self._wisps(c, 0.6, 12, col=DARKV_DK, rise=1.8)
        self._wisps(c, r * 0.8, 14, col=DARKV)

    def _fx_mementocurse(self, e, col):
        c = e.get("c")
        if c is not None:
            self._wisps(c, 0.35, 6, col=DARKV_DK, rise=1.0)
            self._shape(kind="ring", c=c, r0=0.8, r1=0.2, col=DARKV, life=0.4, wd=0.12)

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

    def _fx_xscissor(self, e, col):
        """Forbice X: due fendenti incrociati a forma di X, centrati sul Pokémon."""
        c = e.get("c") or e.get("o")
        if c is None:
            return
        rng = float(e.get("radius", 2.0))
        lite = _lighten(col, 0.3)
        for ang in (math.pi / 4.0, -math.pi / 4.0):   # le due lame della X
            self._shape(kind="slash", c=c, ang=ang, col=lite, life=0.32, rng=rng)
        self._splash(c, rng * 0.8, col, n=20)

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
            if s.get("wait", 0.0) > 0.0:   # forma in attesa (stagger, es. raffica di pugni)
                s["wait"] -= dt
                sh.append(s)
                continue
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
            if s.get("wait", 0.0) > 0.0:   # non ancora comparsa (stagger)
                continue
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
            elif kind == "shot":
                # Proiettile OPACO (minion/torre): sfera piena netta che avanza
                # da A a B. Niente scia di particelle; dissolve solo a fine volo.
                ax, ay = S(*s["a"])
                bx, by = S(*s["b"])
                t = 1 - f
                cx = int(ax + (bx - ax) * t)
                cy = int(ay + (by - ay) * t)
                r = max(2, int(s.get("sz", 0.2) * ts))
                aa = 255 if f > 0.22 else int(255 * max(0.0, f / 0.22))
                glow = s.get("glow", 0.0)
                if glow > 0.0:
                    pygame.draw.circle(overlay, (*col, int(aa * 0.35 * glow)),
                                       (cx, cy), int(r * 1.8))
                    pygame.draw.circle(overlay, (*col, int(aa * 0.45 * glow)),
                                       (cx, cy), int(r * 1.35))
                pygame.draw.circle(overlay, (*_darken(col, 0.45), aa), (cx, cy), r)
                pygame.draw.circle(overlay, (*col, aa), (cx, cy), max(1, r - max(1, r // 5)))
                # luce in alto-sinistra (coerente con l'illuminazione del gioco)
                hr = max(1, r // 2)
                pygame.draw.circle(overlay, (*_lighten(col, 0.6), aa),
                                   (cx - r // 3, cy - r // 3), hr)
            elif kind == "energy":
                # Proiettile d'ENERGIA (minion/torre): testa luminosa a 3 strati
                # (alone, corpo, nucleo quasi bianco) che tremola, coda a cometa
                # e una scia di bolle che si spengono. Vola da A (sollevato di
                # lift_a tile, es. la gemma della torre) a B (lift_b, il busto).
                t = 1 - f
                la, lb = s.get("lift_a", 0.0), s.get("lift_b", 0.0)
                ax, ay = s["a"]
                bx, by = s["b"]

                def at(tt):
                    return S(ax + (bx - ax) * tt, ay - la + (by - lb - ay + la) * tt)

                cx, cy = at(t)
                r = max(2, int(s.get("sz", 0.2) * ts))
                lite = _lighten(col, 0.5)
                core = _lighten(col, 0.85)
                ex, ey = bx - ax, (by - lb) - (ay - la)
                n = math.hypot(ex, ey) or 1.0
                ux, uy = ex / n, ey / n
                # scia: bolle che rimpiccioliscono e sbiadiscono all'indietro
                trail = s.get("trail", 4)
                for i in range(trail, 0, -1):
                    tt = t - i * 0.045
                    if tt <= 0:
                        continue
                    px_, py_ = at(tt)
                    k_ = 1 - i / (trail + 1)
                    pygame.draw.circle(overlay, (*col, int(150 * k_)), (px_, py_),
                                       max(1, int(r * 0.75 * k_)))
                # alone che tremola
                fl = 1.0 + 0.12 * math.sin(s["life"] * 90.0)
                pygame.draw.circle(overlay, (*col, 70), (cx, cy), int(r * 2.0 * fl))
                pygame.draw.circle(overlay, (*col, 120), (cx, cy), int(r * 1.45 * fl))
                # coda a cometa dietro la testa
                pxu, pyu = -uy, ux
                tail = [(cx + pxu * r * 0.9, cy + pyu * r * 0.9),
                        (cx - ux * r * 3.2, cy - uy * r * 3.2),
                        (cx - pxu * r * 0.9, cy - pyu * r * 0.9)]
                pygame.draw.polygon(overlay, (*col, 210), tail)
                pygame.draw.circle(overlay, (*col, 255), (cx, cy), r)
                pygame.draw.circle(overlay, (*lite, 255), (cx, cy), max(1, int(r * 0.7)))
                pygame.draw.circle(overlay, (*core, 255),
                                   (cx - max(0, r // 5), cy - max(0, r // 5)),
                                   max(1, int(r * 0.38)))
                # due scintille che girano attorno alla testa
                for j in (0, math.pi):
                    sa_ = s["life"] * 40.0 + j
                    overlay.fill((*core, 230), pygame.Rect(
                        cx + int(math.cos(sa_) * r * 1.5), cy + int(math.sin(sa_) * r * 1.5), 1, 1))
            elif kind == "flash":
                # lampo d'impatto: disco chiaro che si allarga e svanisce
                cx, cy = S(*s["c"])
                rr = max(2, int(s["r"] * ts * (1.0 + 0.6 * (1 - f))))
                pygame.draw.circle(overlay, (*col, int(110 * f)), (cx, cy), rr)
                pygame.draw.circle(overlay, (*_lighten(col, 0.6), int(170 * f)), (cx, cy),
                                   max(1, rr // 2))
            elif kind == "target":
                # Cerchio-bersaglio telegrafato (Bolla): disco traslucido + anello
                # esterno fisso + anello interno che si chiude verso l'impatto.
                cx, cy = S(*s["c"])
                r = max(2, int(s["r"] * ts))
                lite = _lighten(col)
                pygame.draw.circle(overlay, (*col, int(55 * f)), (cx, cy), r)
                pygame.draw.circle(overlay, (*lite, a), (cx, cy), r, max(2, int(0.1 * ts)))
                ir = max(1, int(r * (1 - f)))   # 1-f = avanzamento verso l'atterraggio
                pygame.draw.circle(overlay, (*lite, a), (cx, cy), ir, max(2, int(0.08 * ts)))
            elif kind == "bubbleorb":
                # Bolla in ARCO: posizione a terra lerp A->B, altezza a parabola
                # (sale e ridiscende). Ombra a terra + bolla traslucida con riflesso.
                ax, ay = s["a"]
                bx, by = s["b"]
                t = 1 - f
                wx = ax + (bx - ax) * t
                wy = ay + (by - ay) * t
                hz = s.get("arc", 2.5) * 4.0 * t * (1 - t)   # altezza in tile (0 ai capi)
                gx, gy = S(wx, wy)                 # ombra a terra
                bxs, bys = S(wx, wy - hz)          # bolla sollevata
                r = max(3, int(s.get("sz", 0.5) * ts))
                lite = _lighten(col, 0.5)
                sh = pygame.Surface((r * 3, r * 2), pygame.SRCALPHA)
                pygame.draw.ellipse(sh, (0, 0, 0, int(70 * f)), sh.get_rect())
                overlay.blit(sh, (gx - r * 3 // 2, gy - r))
                pygame.draw.circle(overlay, (*_lighten(col, 0.25), 150), (bxs, bys), r)
                pygame.draw.circle(overlay, (*lite, 230), (bxs, bys), r, 2)
                pygame.draw.circle(overlay, (255, 255, 255, 220),
                                   (bxs - r // 3, bys - r // 3), max(1, r // 4))
            elif kind == "vortex":
                # Vortice che GIRA per tutta la durata: 3 braccia a spirale + anello
                # esterno + centro scuro, leggermente schiacciate (imbuto a terra).
                cx, cy = S(*s["c"])
                r = s["r"] * ts
                age = s["maxlife"] - s["life"]
                phase = age * 7.0
                vis = min(1.0, age / 0.15, s["life"] / 0.25)   # dissolvenza in/out
                av = int(200 * max(0.0, vis))
                lite = _lighten(col, 0.35)
                sq = 0.75   # schiacciamento verticale
                pygame.draw.ellipse(overlay, (*_darken(col, 0.4), int(av * 0.5)),
                                    pygame.Rect(int(cx - r), int(cy - r * sq),
                                                int(r * 2), int(r * 2 * sq)))
                for k in range(3):
                    pts = []
                    for i in range(11):
                        u = i / 10.0
                        rad = r * (0.12 + 0.88 * u)
                        ang = phase + k * (math.tau / 3) + u * 2.6
                        pts.append((cx + math.cos(ang) * rad,
                                    cy + math.sin(ang) * rad * sq))
                    if len(pts) > 1:
                        pygame.draw.lines(overlay, (*lite, av), False, pts,
                                          max(2, int(0.12 * ts)))
                pygame.draw.ellipse(overlay, (*lite, av),
                                    pygame.Rect(int(cx - r), int(cy - r * sq),
                                                int(r * 2), int(r * 2 * sq)),
                                    max(2, int(0.08 * ts)))
                pygame.draw.circle(overlay, (*_darken(col, 0.5), av),
                                   (cx, cy), max(2, int(r * 0.12)))
            elif kind == "smokecloud":
                # Nuvola di fumo: tante nuvolette grigio scuro tondeggianti che si
                # sovrappongono, ognuna con corpo scuro, mezzatinta e un lobo piu'
                # chiaro in alto a sinistra (luce); ondeggiano piano.
                cx, cy = S(*s["c"])
                age = s["maxlife"] - s["life"]
                vis = max(0.0, min(1.0, age / 0.35, s["life"] / 0.45))
                for dx, dy, pr, ph, sh in s["puffs"]:
                    wob = math.sin(age * 2.2 + ph)
                    px = cx + int((dx + 0.1 * wob) * ts)
                    py = cy + int((dy - 0.07 * math.cos(age * 1.7 + ph) - age * 0.1) * ts)
                    rr = max(6, int(pr * ts * (1.0 + 0.07 * wob)))
                    spr = _smoke_puff(rr - rr % 3, int(sh * 3))
                    spr.set_alpha(int(235 * vis))
                    overlay.blit(spr, (px - spr.get_width() // 2, py - spr.get_height() // 2))
            elif kind == "punch":
                # Pugno che vola: scia + nucleo chiaro, con stella d'impatto a fine corsa.
                ax, ay = S(*s["a"])
                bx, by = S(*s["b"])
                t = 1 - f
                cx = ax + (bx - ax) * t
                cy = ay + (by - ay) * t
                r = max(2, int(s.get("sz", 0.4) * ts))
                ang = math.atan2(by - ay, bx - ax)
                ca, sa = math.cos(ang), math.sin(ang)
                lite = _lighten(col, 0.55)
                tailx, taily = cx - ca * r * 2.2, cy - sa * r * 2.2
                pygame.draw.line(overlay, (*col, a), (tailx, taily), (cx, cy),
                                 max(2, int(0.12 * ts)))
                pygame.draw.circle(overlay, (*col, a), (int(cx), int(cy)), r)
                pygame.draw.circle(overlay, (*lite, a), (int(cx), int(cy)), max(1, r // 2))
                if t > 0.55:   # impatto: piccola stella
                    for sa2 in range(6):
                        aa2 = sa2 * math.tau / 6
                        ex = cx + math.cos(aa2) * r * 1.9
                        ey = cy + math.sin(aa2) * r * 1.9
                        pygame.draw.line(overlay, (*lite, a),
                                         (int(cx), int(cy)), (int(ex), int(ey)), 2)
            elif kind == "rockspike":
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
            elif kind == "hexshell":
                # Ferroscudo: esagono metallico che si stringe sul Pokémon e brilla.
                cx, cy = S(*s["c"])
                t = 1 - f
                r = s["r"] * ts * (1.4 - 0.4 * min(1.0, t * 3))
                pts = [(cx + math.cos(k * math.tau / 6 + math.pi / 6) * r,
                        cy - 0.25 * ts + math.sin(k * math.tau / 6 + math.pi / 6) * r)
                       for k in range(6)]
                pygame.draw.polygon(overlay, (*col, int(60 * f)), pts)
                pygame.draw.polygon(overlay, (*_lighten(col, 0.5), a), pts, 2)
                k = int(t * 6) % 6   # bagliore che corre sui lati
                pygame.draw.line(overlay, (255, 255, 255, a), pts[k], pts[(k + 1) % 6], 2)
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
            elif kind == "puff":
                # Sbuffo di polvere: si allarga, deriva frenando e sbiadisce.
                age = s["maxlife"] - s["life"]
                u = age / s["maxlife"]
                drift = age * (1.0 - 0.5 * u)
                px, py = S(s["c"][0] + s["v"][0] * drift, s["c"][1] + s["v"][1] * drift)
                rr = max(1, int((s["r0"] + (s["r1"] - s["r0"]) * u) * ts))
                av = int(120 * f * min(1.0, age / 0.06))
                pygame.draw.circle(overlay, (*col, av), (px, py), rr)
                pygame.draw.circle(overlay, (*_lighten(col, 0.25), av // 2),
                                   (px - rr // 3, py - rr // 3), max(1, rr // 2))
            elif kind == "flash":
                cx, cy = S(*s["c"])
                pygame.draw.circle(overlay, (*col, int(230 * f)), (cx, cy), int(s["r"] * ts * (1.2 - 0.4 * f)))
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
            elif kind in eevee_fx.SHAPES:   # linea Eevee: denti di Morso, stelline
                eevee_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in corvi_fx.SHAPES:   # linea Rookidee: becco, piume, ali, "!"
                corvi_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in charcadet_fx.SHAPES:   # linea Charcadet: fuoco, lava, artigli, lame
                charcadet_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in noivern_fx.SHAPES:   # linea Noibat: onde sonore, lame d'aria, meteore
                noivern_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in ursa_fx.SHAPES:   # linea Teddiursa: artigli, pugno, crepe, sassi, luna
                ursa_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in sneasel_fx.SHAPES:   # linea Sneasel: scheggia, fendente, monete, stelle
                sneasel_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in mien_fx.SHAPES:   # linea Mienfoo: manica, palmo, occhio, nastri
                mien_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in arch_fx.SHAPES:   # linea Duraludon: palla d'acciaio, fulmini, raggio
                arch_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in hatt_fx.SHAPES:   # linea Hatenna: increspature, Psicoraggio, note, ciocche
                hatt_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in mag_fx.SHAPES:   # linea Magnemite: saette, linee di campo, cariche
                mag_fx.draw_shape(overlay, s, S, ts, f, a)
            elif kind in swine_fx.SHAPES:   # linea Swinub: neve, rocce, cristalli
                swine_fx.draw_shape(overlay, s, S, ts, f, a)
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
        "arcbubble": _fx_arcbubble,
        "vortex": _fx_vortex,
        "smoke": _fx_smoke,
        "flurry": _fx_flurry,
        "drain": _fx_drain,
        "slash": _fx_slash,
        "xscissor": _fx_xscissor,
        # linea Roggenrola
        "rockspike": _fx_rockspike,
        "pillar": _fx_pillar,
        "pillarbreak": _fx_pillarbreak,
        "shockwave": _fx_shockwave,
        "rockburst": _fx_rockburst,
        "chargedust": _fx_chargedust,
        "knockup": _fx_knockup,
        "smackdown": _fx_smackdown,
        "smackzone": _fx_smackzone,
        "spikefield": _fx_spikefield,
        "sandburst": _fx_sandburst,
        "ironshell": _fx_ironshell,
        "avalanchewarn": _fx_avalanchewarn,
        "explodecharge": _fx_explodecharge,
        "explosion": _fx_explosion,
        # Spiritomb
        "spiritshot": _fx_spiritshot,
        "spiritpick": _fx_spiritpick,
        "spiritawaken": _fx_spiritawaken,
        "spiritburst": _fx_spiritburst,
        "spiritbeamhit": _fx_spiritbeamhit,
        "spiritbind": _fx_spiritbind,
        "painlink": _fx_painlink,
        "painsplit": _fx_painsplit,
        "spiritwarp": _fx_spiritwarp,
        "legioncast": _fx_legioncast,
        "legionally": _fx_legionally,
        "legionfear": _fx_legionfear,
        "memento": _fx_memento,
        "mementocurse": _fx_mementocurse,
        # linea Eevee (game/eevee_fx.py)
        **eevee_fx.STYLES,
        # linea Rookidee (game/corvi_fx.py)
        **corvi_fx.STYLES,
        # linea Charcadet (game/charcadet_fx.py)
        **charcadet_fx.STYLES,
        # linea Noibat (game/noivern_fx.py)
        **noivern_fx.STYLES,
        # linea Teddiursa (game/ursa_fx.py)
        **ursa_fx.STYLES,
        # linea Sneasel (game/sneasel_fx.py)
        **sneasel_fx.STYLES,
        # linea Mienfoo (game/mien_fx.py)
        **mien_fx.STYLES,
        # linea Duraludon (game/arch_fx.py)
        **arch_fx.STYLES,
        # linea Hatenna (game/hatt_fx.py)
        **hatt_fx.STYLES,
        **mag_fx.STYLES,
        **swine_fx.STYLES,
    }
