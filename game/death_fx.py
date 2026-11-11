"""Morte rapida di minion e mostri della giungla + "+oro" dell'ultimo colpo.

Solo grafica, guidata da due eventi fx COSMETICI del motore:
  {"kind": "unit_death", "who": id, "c": (x, y), "big": bool}
      un minion o un neutrale e' morto (il motore lo toglie subito dal mondo);
  {"kind": "gold", "who": id_killer, "c": (x, y), "g": oro}
      oro preso con l'ultimo colpo (minion, campi della giungla).

Morte: l'animatore dell'unita' viene staccato dalla scena e riproduce Faint (se
lo sprite ce l'ha) o Hurt ACCELERATA, resta sull'ultima posa e svanisce in
~0,55 s (1,1 s i leggendari), con uno sbuffo di polvere ai piedi. Nessuna
Surface nuova a frame: sprite in cache e un blit per unita'.

Oro: "+N" in pixel art (cifre 3x5 disegnate a mano, contorno scuro, moneta a
sinistra) che sale e svanisce sopra la vittima. Lo vede SOLO chi ha preso l'oro
(come nei MOBA): FXSystem.me = id del proprio Pokemon.
"""
from __future__ import annotations

import pygame

DEATH_T = 0.55        # s: durata della morte (minion, campi)
DEATH_T_BIG = 1.1     # s: leggendari
FADE_FROM = 0.45      # frazione della durata da cui parte la dissolvenza
DIE_SPEED = 1.8       # accelerazione dell'animazione di morte
PUFF_T = 0.32
GOLD_T = 1.0
GOLD_RISE = 13        # px (bassa risoluzione) di salita
HEAD = 0.95           # tile sopra il punto a terra dove compare l'oro
MAX_DEATHS = 48
MAX_GOLD = 16

# Cifre 3x5 ("#" = pieno).
_GLYPHS = {
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", ".##", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", ".#.", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "###"),
    "+": ("...", ".#.", "###", ".#.", "..."),
}
_COIN = (".##.", "#XX#", "#XX#", ".##.")

GOLD_HI = (255, 244, 160)
GOLD = (255, 205, 60)
GOLD_DK = (196, 132, 24)
OUTLINE = (48, 30, 8)

_gold_cache: dict = {}
_puff_cache: dict = {}


def gold_sprite(amount: int) -> pygame.Surface:
    """"(moneta) +N" a risoluzione nativa, contorno scuro a 8 vicini."""
    s = _gold_cache.get(amount)
    if s is not None:
        return s
    text = f"+{amount}"
    # griglia logica: moneta 4x4 (centrata sulle cifre), spazio, cifre 3x5 + 1 di passo
    pts: dict = {}
    for y, row in enumerate(_COIN):
        for x, ch in enumerate(row):
            if ch != ".":
                pts[(x, y + 1)] = GOLD_HI if (ch == "X" and x == 1 and y == 1) else (
                    GOLD if ch == "X" else GOLD_DK)
    x0 = 6
    for ch in text:
        g = _GLYPHS.get(ch)
        if g is None:
            continue
        for y, row in enumerate(g):
            for x, c in enumerate(row):
                if c == "#":
                    pts[(x0 + x, y)] = GOLD_HI if y == 0 else (GOLD_DK if y == 4 else GOLD)
        x0 += 4
    w, h = x0 + 1, 7
    s = pygame.Surface((w + 2, h), pygame.SRCALPHA)
    for (x, y) in pts:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                s.set_at((x + 1 + dx, y + 1 + dy), (*OUTLINE, 255))
    for (x, y), col in pts.items():
        s.set_at((x + 1, y + 1), (*col, 255))
    _gold_cache[amount] = s
    return s


def puff_sprite(frame: int, big: bool) -> pygame.Surface:
    """Sbuffo di polvere a terra (ellisse di 5 batuffoli che si allarga)."""
    key = (frame, big)
    s = _puff_cache.get(key)
    if s is not None:
        return s
    R = (10, 14, 17, 19)[frame] if big else (6, 9, 11, 12)[frame]
    w, h = R * 2 + 8, R + 8
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w // 2, h // 2
    rb = max(2, (4, 4, 3, 2)[frame] + (2 if big else 0))
    body = (196, 186, 160, 255)
    shade = (128, 118, 98, 255)
    light = (232, 226, 206, 255)
    out = (60, 52, 40, 255)
    blobs = [(-1.0, 0.0), (-0.5, -0.45), (0.15, -0.55), (0.7, -0.3), (0.9, 0.2),
             (0.3, 0.45), (-0.45, 0.4)]
    for bx, by in blobs:
        x, y = int(cx + bx * R), int(cy + by * R * 0.5)
        pygame.draw.circle(s, out, (x, y), rb + 1)
    for bx, by in blobs:
        x, y = int(cx + bx * R), int(cy + by * R * 0.5)
        pygame.draw.circle(s, shade, (x, y), rb)
        pygame.draw.circle(s, body, (x - 1, y - 1), max(1, rb - 1))
        if rb >= 3:
            s.set_at((x - 2, y - 2), light)
    if frame >= 2:
        s.fill((255, 255, 255, 170 if frame == 2 else 90), None, pygame.BLEND_RGBA_MULT)
    _puff_cache[key] = s
    return s


class DeathFx:
    """Unita' in morte ([anim, x, y, t, durata, big]) e popup dell'oro."""

    def __init__(self):
        self.dying: list[list] = []
        self.golds: list[list] = []     # [x, y, t, importo]

    # --- eventi ----------------------------------------------------------------
    def from_events(self, events, animators) -> None:
        """Chiamata PRIMA che la scena butti gli animatori delle unita' rimosse:
        stacca l'animatore del morto e gli fa recitare la morte."""
        for e in events:
            if e.get("kind") != "unit_death" or e.get("who") is None:
                continue
            an = animators.pop(int(e["who"]), None)
            c = e.get("c")
            if an is None or not c:
                continue
            die = getattr(an, "die", None)
            if die is not None:
                die(DIE_SPEED)
            if len(self.dying) >= MAX_DEATHS:
                self.dying.pop(0)
            big = bool(e.get("big"))
            self.dying.append([an, float(c[0]), float(c[1]), 0.0,
                               DEATH_T_BIG if big else DEATH_T, big])

    def add_gold(self, e, me) -> None:
        if me is None or e.get("who") is None or int(e["who"]) != int(me):
            return
        g = int(round(float(e.get("g", 0))))
        c = e.get("c")
        if g <= 0 or not c:
            return
        if len(self.golds) >= MAX_GOLD:
            self.golds.pop(0)
        self.golds.append([float(c[0]), float(c[1]), 0.0, g])

    # --- tempo -----------------------------------------------------------------
    def update(self, dt: float) -> None:
        if self.dying:
            for d in self.dying:
                d[3] += dt
                d[0].update(dt, False, d[0].facing)
            self.dying = [d for d in self.dying if d[3] < d[4]]
        if self.golds:
            for g in self.golds:
                g[2] += dt
            self.golds = [g for g in self.golds if g[2] < GOLD_T]

    # --- disegno ---------------------------------------------------------------
    def draw_deaths(self, surface, camera, ts: int) -> None:
        for an, x, y, t, dur, big in self.dying:
            sx, sy = camera.world_to_screen(x * ts, y * ts)
            k = t / dur
            alpha = 255 if k < FADE_FROM else int(255 * max(0.0, 1.0 - (k - FADE_FROM)
                                                             / (1.0 - FADE_FROM)))
            if alpha > 0:
                an.draw(surface, sx, sy, alpha)
            tp = t - dur * FADE_FROM          # sbuffo quando inizia a svanire
            if 0.0 <= tp < PUFF_T:
                p = puff_sprite(min(3, int(tp / PUFF_T * 4)), big)
                offs = [(0, 0)] + [(dx, dy) for _c, dx, dy in getattr(an, "companions", ())]
                for dx, dy in offs:   # gruppi (3 Tangela...): uno sbuffo per membro
                    surface.blit(p, (sx + dx - p.get_width() // 2,
                                     sy + dy - p.get_height() // 2 - 1))

    def draw_gold(self, surface, camera, ts: int) -> None:
        for x, y, t, g in self.golds:
            sx, sy = camera.world_to_screen(x * ts, (y - HEAD) * ts)
            k = t / GOLD_T
            rise = int(GOLD_RISE * (1.0 - (1.0 - k) ** 3))   # ease-out
            spr = gold_sprite(g)
            if k < 0.08:                      # "pop" d'ingresso: un fotogramma x2
                spr = pygame.transform.scale(spr, (spr.get_width() * 2, spr.get_height() * 2))
            if k > 0.65:
                spr = spr.copy()
                spr.set_alpha(int(255 * (1.0 - (k - 0.65) / 0.35)))
            surface.blit(spr, (sx - spr.get_width() // 2, sy - rise - spr.get_height()))
