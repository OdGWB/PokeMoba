"""Particelle d'atmosfera leggere per le zone di giungla.

Tre tipi, puramente COSMETICI (nessuna collisione, nessun effetto sulla logica):
  - lucciole: puntini caldi che fluttuano piano e PULSANO lentamente;
  - polline: minuscoli granelli chiari che derivano nell'aria;
  - foglie: qualche foglia che CADE ondeggiando.

Vincoli (come da richiesta):
  - al massimo ~60 particelle a schermo (MAX_PARTICLES);
  - aggiornate SOLO dentro la camera: si generano nel rettangolo visibile e,
    appena ne escono (oltre un piccolo margine), vengono riciclate. Quando la
    vista inquadra soprattutto lane/acqua (poca giungla) se ne generano meno,
    perche' nascono solo sui tile di giungla (TILE_FLOOR / TILE_BUSH).

Costo trascurabile: niente allocazioni per-frame (gli sprite sono pre-renderizzati
una volta e ri-blittati con un alfa variabile), aggiornamento O(n) con n<=60.
"""
from __future__ import annotations

import math
import random

import pygame

import config
from engine.grid import TILE_BUSH, TILE_FLOOR

MAX_PARTICLES = 60
MARGIN = 20                 # px-mondo oltre la vista prima di riciclare
SPAWN_ATTEMPTS = 6          # tentativi di spawn per frame (costo limitato)

# Pesi dei tipi (somma 1): soprattutto polline, qualche lucciola, poche foglie.
_W_FIREFLY = 0.30
_W_POLLEN = 0.50
_W_LEAF = 0.20

# Solo le zone di giungla ricevono particelle (non lane, acqua, muri).
_JUNGLE = (TILE_FLOOR, TILE_BUSH)

# Palette (luce calda per le lucciole, chiara per il polline, foglie autunnali/verdi).
FIREFLY_COL = (208, 226, 138)
POLLEN_COL = (224, 230, 194)
LEAF_COLS = ((150, 100, 46), (124, 88, 44), (74, 112, 56), (98, 106, 58))


class _P:
    """Una particella. Campi minimi, __slots__ per memoria/accesso veloci."""
    __slots__ = ("kind", "x", "y", "vx", "vy", "phase", "age", "life", "cidx")

    def __init__(self, kind, x, y, vx, vy, phase, life, cidx=0):
        self.kind = kind; self.x = x; self.y = y
        self.vx = vx; self.vy = vy
        self.phase = phase; self.age = 0.0; self.life = life; self.cidx = cidx


class ParticleSystem:
    GLOW_LEVELS = 6            # gradini di luminosita' pre-renderizzati (lucciola)

    def __init__(self):
        self._ps: list[_P] = []
        self._rng = random.Random(0xA17B)
        # Alone della lucciola a LIVELLI di luminosita' pre-renderizzati: si
        # blitta direttamente il livello giusto (blit SRCALPHA veloce), senza
        # set_alpha su una superficie per-pixel (percorso di blend lento).
        self._glow = [self._make_glow(FIREFLY_COL, (i + 1) / self.GLOW_LEVELS)
                      for i in range(self.GLOW_LEVELS)]
        # Polline a livelli (come l'alone): evita set_alpha sul blit.
        self._pollen = [self._make_dot(POLLEN_COL, (i + 1) / self.GLOW_LEVELS)
                        for i in range(self.GLOW_LEVELS)]
        self._leaf_cache: dict = {}                      # (cidx, angstep) -> sprite ruotato

    # --- sprite pre-renderizzati (una volta) --------------------------------
    @staticmethod
    def _make_glow(col, bright):
        """Alone radiale morbido (lucciola) a una data luminosita' `bright` in
        (0,1]: cerchi concentrici d'alfa calante + nucleo quasi bianco."""
        r = 4
        s = pygame.Surface((r * 2 + 1, r * 2 + 1), pygame.SRCALPHA)
        for rr in range(r, 0, -1):
            a = int(150 * bright * (1.0 - rr / (r + 1)) ** 2)
            pygame.draw.circle(s, (*col, a), (r, r), rr)
        s.set_at((r, r), (255, 255, 225, int(255 * bright)))
        return s

    @staticmethod
    def _make_dot(col, bright):
        """Granello 3x3 morbido (polline) a luminosita' `bright` in (0,1]."""
        s = pygame.Surface((3, 3), pygame.SRCALPHA)
        s.set_at((1, 1), (*col, int(220 * bright)))
        a = int(90 * bright)
        for p in ((0, 1), (2, 1), (1, 0), (1, 2)):
            s.set_at(p, (*col, a))
        return s

    def _leaf_sprite(self, cidx, ang):
        """Sprite di una foglia (ellisse con nervatura e contorno), ruotato e messo
        in cache per angolo QUANTIZZATO (16 passi) -> niente rotate per-frame."""
        step = int(round(ang / (math.pi / 8))) % 16
        key = (cidx, step)
        spr = self._leaf_cache.get(key)
        if spr is None:
            col = LEAF_COLS[cidx]
            out = (max(0, col[0] - 50), max(0, col[1] - 45), max(0, col[2] - 30))
            base = pygame.Surface((7, 5), pygame.SRCALPHA)
            pygame.draw.ellipse(base, (*out, 235), pygame.Rect(0, 0, 7, 5))
            pygame.draw.ellipse(base, (*col, 240), pygame.Rect(1, 1, 5, 3))
            pygame.draw.line(base, (*out, 220), (1, 2), (5, 2))      # nervatura
            spr = pygame.transform.rotate(base, math.degrees(step * (math.pi / 8)))
            self._leaf_cache[key] = spr
        return spr

    # --- aggiornamento (solo dentro la camera) ------------------------------
    def update(self, dt: float, camera, grid) -> None:
        if dt <= 0.0:
            dt = 1e-3
        vx0 = camera.x; vy0 = camera.y
        vx1 = vx0 + camera.view_w; vy1 = vy0 + camera.view_h
        lo_x = vx0 - MARGIN; hi_x = vx1 + MARGIN
        lo_y = vy0 - MARGIN; hi_y = vy1 + MARGIN

        alive = []
        add = alive.append
        sin = math.sin; cos = math.cos
        for p in self._ps:
            a = p.age + dt
            p.age = a
            k = p.kind; ph = p.phase
            if k == "firefly":
                p.x += (p.vx + cos(a * 0.7 + ph) * 5.0) * dt
                p.y += (p.vy + sin(a * 0.9 + ph * 1.3) * 4.0) * dt
            elif k == "pollen":
                p.x += (p.vx + sin(a * 0.6 + ph) * 3.0) * dt
                p.y += p.vy * dt
            else:  # leaf: cade ondeggiando
                p.x += (p.vx + sin(a * 1.6 + ph) * 9.0) * dt
                p.y += p.vy * dt
            # Riciclo: fuori dalla vista (+ margine) o vita finita.
            px = p.x; py = p.y
            if a < p.life and lo_x <= px <= hi_x and lo_y <= py <= hi_y:
                add(p)
        self._ps = alive

        # Rimpiazzo fino a MAX: spawn SOLO su tile di giungla dentro la vista.
        deficit = MAX_PARTICLES - len(self._ps)
        if deficit <= 0:
            return
        ts = config.TILE_SIZE
        tiles = grid.tiles
        Wt, Ht = grid.width, grid.height
        rng = self._rng
        attempts = min(SPAWN_ATTEMPTS, deficit)
        for _ in range(attempts):
            x = rng.uniform(vx0, vx1)
            y = rng.uniform(vy0, vy1)
            tx = int(x // ts); ty = int(y // ts)
            if not (0 <= tx < Wt and 0 <= ty < Ht) or tiles[ty][tx] not in _JUNGLE:
                continue
            self._ps.append(self._spawn(x, y, vy0, rng))

    def _spawn(self, x, y, vy0, rng):
        k = rng.random()
        ph = rng.uniform(0.0, math.tau)
        if k < _W_FIREFLY:
            return _P("firefly", x, y, rng.uniform(-6, 6), rng.uniform(-5, 5),
                      ph, rng.uniform(6.0, 12.0))
        if k < _W_FIREFLY + _W_POLLEN:
            return _P("pollen", x, y, rng.uniform(-4, 8), rng.uniform(-6, -1),
                      ph, rng.uniform(5.0, 10.0))
        # Foglia: nasce nella meta' alta della vista e cade; colore casuale.
        y = min(y, vy0 + camera_h_bias())
        return _P("leaf", x, y, rng.uniform(-5, 10), rng.uniform(16, 30),
                  ph, rng.uniform(4.0, 8.0), cidx=rng.randrange(len(LEAF_COLS)))

    # --- disegno -------------------------------------------------------------
    def draw(self, surface, camera) -> None:
        if not self._ps:
            return
        vw, vh = camera.view_w, camera.view_h
        glow = self._glow; nlev = self.GLOW_LEVELS
        gc = glow[0].get_width() // 2
        pollen = self._pollen
        blit = surface.blit
        ox = camera.ox; oy = camera.oy          # offset intero del frame (inline world_to_screen)
        sin = math.sin
        for p in self._ps:
            sx = round(p.x) - ox; sy = round(p.y) - oy
            if sx < -8 or sy < -8 or sx > vw + 8 or sy > vh + 8:
                continue
            fade = _fade(p.age, p.life)
            if p.kind == "firefly":
                pulse = 0.5 + 0.5 * sin(p.age * 2.2 + p.phase)          # pulsazione lenta
                lv = int(pulse * fade * nlev)                           # livello pre-renderizzato
                if lv <= 0:
                    continue
                blit(glow[min(lv, nlev) - 1], (sx - gc, sy - gc))
            elif p.kind == "pollen":
                lv = int(fade * nlev)
                if lv <= 0:
                    continue
                blit(pollen[min(lv, nlev) - 1], (sx - 1, sy - 1))
            else:
                spr = self._leaf_sprite(p.cidx, p.phase + p.age * 1.1)
                spr.set_alpha(255 if fade >= 0.98 else int(235 * fade))   # set_alpha solo in dissolvenza
                blit(spr, (sx - spr.get_width() // 2, sy - spr.get_height() // 2))


def _fade(age, life):
    """Dissolvenza in entrata (0.6s) e in uscita (ultimi 0.8s) -> niente 'pop'."""
    fin = min(1.0, age / 0.6)
    fout = min(1.0, max(0.0, (life - age) / 0.8))
    return fin * fout


def camera_h_bias():
    """Meta' alta della vista per lo spawn delle foglie (devono avere spazio per
    cadere). Costante indipendente dalla camera: usa l'altezza low-res."""
    return config.LOWRES_HEIGHT * 0.5
