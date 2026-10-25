"""Rendering della partita su una surface a bassa risoluzione.

Disegna solo i tile ed entità visibili nella camera (culling) e ordina tutte le
entità (unità e strutture) per coordinata Y, così la sovrapposizione nella
visuale 3/4 è corretta.
"""
from __future__ import annotations

import pygame

import math
import random

import config
from engine.entities import Core, Pokemon, Structure, Unit
from engine.grid import (TILE_BUSH, TILE_FLOOR, TILE_JUNGLE_WALL, TILE_LANE,
                         TILE_PUDDLE, TILE_RIVER, TILE_WALL)
from .fx import type_color
from .map_renderer import MapRenderer

# Palette greybox (sostituita dai tileset in futuro).
COL_BG = (18, 20, 24)
TILE_COLORS = {
    0: (58, 92, 62),     # erba / giungla
    TILE_LANE: (150, 134, 92),    # strada
    TILE_RIVER: (64, 110, 160),   # fiume
    TILE_BUSH: (34, 74, 44),      # cespuglio (più scuro)
    TILE_WALL: (44, 46, 52),
    TILE_JUNGLE_WALL: (52, 60, 50),  # muro di giungla (verdastro)
    TILE_PUDDLE: (70, 120, 150),     # pozza (pioggia)
}
COL_WALL_TOP = (64, 66, 74)
COL_GRID = (0, 0, 0)

# --- Palette "texture" procedurali (strada 1): niente asset esterni, solo
#     draw-call rese stabili con un seed per-tile e messe in cache. ------------
# Suolo di giungla: un terreno UNICO, cupo e desaturato, verso il verde-blu.
# Il colore varia con rumore a DUE scale campionato sugli ANGOLI dei tile
# (condivisi coi vicini): la tinta è continua attraverso i bordi -> niente
# "mattonelle"; a questo si sommano chiazze organiche di muschio e di fango.
# Palette giungla (cupa, desaturata).
JUNGLE_BASE = (46, 74, 51)       # #2E4A33 base
JUNGLE_DARK = (35, 59, 41)       # #233B29 avvallamento in ombra
JUNGLE_LIGHT = (58, 90, 60)      # #3A5A3C dosso illuminato
JUNGLE_MOSS = (74, 107, 58)      # #4A6B3A muschio
JUNGLE_DIRT = (90, 74, 53)       # #5A4A35 terra/sentiero
JUNGLE_MUD = (62, 53, 39)        # #3E3527 fango
DIRT_DRY = (112, 93, 66)         # battuto secco e chiaro (nucleo calpestato)
GRASS_LO = JUNGLE_DARK           # avvallamento in ombra
GRASS_HI = JUNGLE_LIGHT          # dosso illuminato
GRASS_CELL = 4.0                 # scala fine delle chiazze di tinta (in tile)
GRASS_CELL2 = 9.0                # scala larga (seconda ottava) -> dossi ampi
PATCH_CELL = 6.5                 # scala delle chiazze di muschio/fango (in tile)
GRASS_QUANT = 9                  # livelli di tinta (passi piccoli -> no banding)
MOSS_QUANT = 4                   # livelli di densità del muschio
MUD_QUANT = 4                    # livelli di densità del fango
GRASS_TUFT_LIGHT = (84, 116, 70)
GRASS_TUFT_DARK = (30, 54, 38)
MOSS_FLECK_L = (96, 128, 66)     # fiocco di muschio chiaro
MOSS_FLECK_D = (54, 82, 46)      # fiocco di muschio scuro
MUD_SPECK = (74, 64, 48)         # sassolino/granello sul fango
# Acqua: fiume continuo. Colore quasi piatto (pochi seam) + corrente diagonale.
WATER_DEEP = (40, 86, 128)
WATER_MID = (52, 104, 146)
WATER_FLOW = (96, 150, 186)      # increspature di corrente
WATER_FOAM = (176, 206, 220)     # schiuma chiara
WATER_SHALLOW = (92, 156, 170)   # bassofondo chiaro verso la riva
SHORE_SAND = (112, 130, 96)      # fango/sabbia bagnata sulla riva (lato terra)
SHORE_WET = (74, 104, 86)        # terra bagnata scura proprio al contatto
# Corsia.
LANE_BASE = (150, 134, 92)
LANE_SPECK_L = (170, 154, 110)
LANE_SPECK_D = (126, 110, 74)
PATH_EDGE = (126, 116, 80)       # terra battuta sul bordo erba -> lane
GRASS_FRINGE = (58, 98, 60)      # erba che invade il bordo della lane
# Cespuglio (2.5D): chiome a cupola illuminate dall'alto-sinistra. Verdi
# saturi, dal fondo in ombra profonda alla cresta brillante.
BUSH_SHADOW = (10, 30, 16)       # fondo chioma, in ombra profonda
BUSH_DARK = (18, 52, 28)         # base foglia
BUSH_MID = (36, 84, 42)          # foglia a mezza luce
BUSH_LIGHT = (78, 140, 66)       # foglia illuminata
BUSH_HILITE = (134, 196, 104)    # colpo di luce sulla cupola
BUSH_RIMLIGHT = (158, 212, 128)  # cresta brillante sul bordo alto esposto
BUSH_RIM = (6, 22, 13)           # contorno/contatto scuro alla base
BUSH_CONTACT = (0, 0, 0, 110)    # ombra proiettata sull'erba (radica a terra)
# Muro di confine (TILE_WALL): pietra grigia fredda (resta un muro costruito).
STONE_WALL = ((118, 120, 130), (70, 72, 82), (40, 42, 50), (52, 54, 62))
# --- Altopiano roccioso della giungla (reso neighbor-aware: un blocco connesso
#     = un'unica formazione con cima illuminata e parete/cliff sui bordi). ------
JW_TOP = (94, 104, 88)        # cima (roccia muschiata illuminata)
JW_TOP_HI = (124, 134, 112)
JW_MOSS = (70, 102, 60)       # muschio/arbusti sulla cima
JW_MOSS_DK = (46, 76, 44)
JW_CLIFF = (54, 60, 50)       # parete frontale (in ombra)
JW_CLIFF_DK = (34, 40, 34)
JW_CLIFF_HI = (86, 94, 76)    # riflesso appena sotto il bordo cima
JW_RIM = (148, 158, 130)      # bordo-luce in alto (nord)
JW_EDGE_SH = (32, 38, 32)     # bordo-ombra (est)
JW_TOP_SH = (52, 58, 48)      # sotto-faccia in ombra (più contrasto)
JW_HILITE = (158, 168, 140)   # luce forte sugli spigoli esposti
JW_BOULDER = (108, 116, 100)  # masso in rilievo che sporge sulla cima
JW_BOULDER_HI = (150, 160, 134)
JW_CONTACT = (0, 0, 0, 70)    # ombra di contatto alla base, sull'erba
# Ombra proiettata a terra dai rilievi.
PROP_SHADOW = (0, 0, 0, 90)
COL_PATH = (255, 230, 120)
COL_SELECT = (255, 255, 255)
COL_HP_BG = (20, 20, 20)
COL_HP_GOOD = (90, 210, 90)
DEN_COLORS = {"low": (240, 150, 60), "high": (180, 120, 230)}


class Renderer:
    def __init__(self, tile_size: int = config.TILE_SIZE):
        self.tile_size = tile_size
        self._tile_cache: dict = {}   # (ts, tile_type, variant) -> Surface
        # Mappa statica in layer pre-renderizzati (costruiti al primo draw).
        self.map = MapRenderer(self, tile_size)

    def draw(self, surface, world, camera, animators, selected_path=None,
             selected_id=None, dens=None, respawning=None, vision=None, player_team=0,
             now=1e9):
        surface.fill(COL_BG)
        camera.snap()   # offset intero del frame, condiviso da mappa e unita
        # Mappa statica: costruita una volta in layer, poi solo blit.
        self.map.ensure_built(world.grid)
        self.map.draw(surface, camera)            # ground, decor, ombre, muri base
        if dens:
            self._draw_dens(surface, camera, dens)
        if config.SHOW_PATH and selected_path:
            self._draw_path(surface, selected_path, camera)
        self._draw_entities(surface, camera, world, animators, selected_id,
                            vision, player_team, now)
        self.map.draw_canopy(surface, camera)     # chiome/luce sopra le unita
        if respawning:
            self._draw_respawns(surface, camera, respawning)
        if vision is not None:
            self._draw_fog(surface, camera, world.grid, vision, player_team)

    # --- mappa ---------------------------------------------------------------
    # La composizione della mappa statica (3 passate: terreno, ombre, rilievi
    # 2.5D) e stata spostata in MapRenderer.build, che la pre-renderizza una
    # volta in layer separati. Qui restano solo i builder dei singoli sprite dei
    # tile (riusati da MapRenderer), invariati.
    def _tile_surf(self, t: int, variant: int) -> pygame.Surface:
        """Superficie texturizzata del tile piatto, costruita una volta e messa in cache."""
        ts = self.tile_size
        key = (ts, t, variant)
        surf = self._tile_cache.get(key)
        if surf is None:
            surf = self._build_tile(t, variant, ts)
            self._tile_cache[key] = surf
        return surf

    def _shadow_surf(self, nw: int) -> pygame.Surface:
        """Ombra proiettata dal muro sul terreno adiacente (cache). Bit 1=muro a
        nord (ombra in alto), 2=muro a ovest (ombra a sinistra); sfuma verso il
        centro del tile."""
        ts = self.tile_size
        key = (ts, "shd", nw)
        s = self._tile_cache.get(key)
        if s is None:
            s = pygame.Surface((ts, ts), pygame.SRCALPHA)
            shd = max(5, int(ts * 0.72)); amax = 150
            if nw & 1:
                g = pygame.Surface((ts, shd), pygame.SRCALPHA)
                for y in range(shd):
                    pygame.draw.line(g, (0, 0, 0, int(amax * (1 - y / shd))), (0, y), (ts, y))
                s.blit(g, (0, 0))
            if nw & 2:
                g = pygame.Surface((shd, ts), pygame.SRCALPHA)
                for x in range(shd):
                    pygame.draw.line(g, (0, 0, 0, int(amax * (1 - x / shd))), (x, 0), (x, ts))
                s.blit(g, (0, 0))
            self._tile_cache[key] = s
        return s

    def _tall_surf(self, t: int, variant: int, H: int) -> pygame.Surface:
        """Sprite del rilievo 2.5D (ts x (ts+H)), con cache."""
        ts = self.tile_size
        key = (ts, "tall", t, variant, H)
        surf = self._tile_cache.get(key)
        if surf is None:
            surf = self._build_tall(t, variant, ts, H)
            self._tile_cache[key] = surf
        return surf

    # --- Erba: prato unico con rumore a bassa frequenza sugli angoli ---------
    @staticmethod
    def _h01(x: int, y: int) -> float:
        """Hash deterministico di un punto del reticolo -> [0,1]."""
        h = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
        h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
        h ^= h >> 16
        return (h & 0xFFFF) / 65535.0

    def _vnoise(self, fx: float, fy: float) -> float:
        """Value-noise bilineare (smoothstep) su reticolo intero."""
        ix, iy = math.floor(fx), math.floor(fy)
        dx, dy = fx - ix, fy - iy
        sx = dx * dx * (3 - 2 * dx)
        sy = dy * dy * (3 - 2 * dy)
        a = self._h01(ix, iy); b = self._h01(ix + 1, iy)
        c = self._h01(ix, iy + 1); d = self._h01(ix + 1, iy + 1)
        top = a + (b - a) * sx
        bot = c + (d - c) * sx
        return top + (bot - top) * sy

    def _two_octave(self, cx: int, cy: int) -> float:
        """Rumore a due scale: una fine (dossi stretti) + una larga (ondulazioni
        ampie). Combinate -> variazione organica, senza pattern a griglia."""
        n1 = self._vnoise(cx / GRASS_CELL, cy / GRASS_CELL)
        n2 = self._vnoise((cx + 40) / GRASS_CELL2, (cy + 40) / GRASS_CELL2)
        return 0.62 * n1 + 0.38 * n2

    def _grass_corner(self, cx: int, cy: int):
        """Firma del suolo a un ANGOLO di tile: (tinta verde, muschio, fango),
        tutte quantizzate. Gli angoli sono condivisi tra tile adiacenti ->
        colore e chiazze continui attraverso i bordi (nessun seam); la
        quantizzazione tiene piccola la cache degli sprite."""
        tint = int(round(self._two_octave(cx, cy) * GRASS_QUANT))
        # Muschio e fango: rumore a bassa frequenza con soglia -> chiazze larghe
        # e sparse invece di una coltre uniforme; i bordi sfumano da soli grazie
        # all'interpolazione bilineare tra gli angoli nel build.
        m = self._vnoise((cx + 123) / PATCH_CELL, (cy + 77) / PATCH_CELL)
        moss = int(round(max(0.0, (m - 0.56) / 0.44) * MOSS_QUANT))
        d = self._vnoise((cx + 311) / (PATCH_CELL + 1.5), (cy + 517) / (PATCH_CELL + 1.5))
        mud = int(round(max(0.0, (d - 0.60) / 0.40) * MUD_QUANT))
        return (tint, moss, mud)

    def _grass_surf(self, c00: int, c10: int, c01: int, c11: int) -> pygame.Surface:
        ts = self.tile_size
        key = (ts, "grass", c00, c10, c01, c11)
        s = self._tile_cache.get(key)
        if s is None:
            s = self._build_grass(ts, c00, c10, c01, c11)
            self._tile_cache[key] = s
        return s

    def _build_grass(self, ts, q00, q10, q01, q11) -> pygame.Surface:
        """Tile di suolo: gradiente verde (tinta a due scale) + chiazze di
        muschio e fango, il tutto interpolato dai 4 angoli -> bordi sfumati e
        continuità coi tile vicini. Ogni angolo è (tinta, muschio, fango)."""
        def green(q):
            f = q / GRASS_QUANT
            return tuple(GRASS_LO[i] + (GRASS_HI[i] - GRASS_LO[i]) * f for i in range(3))
        g00, g10, g01, g11 = (green(q00[0]), green(q10[0]), green(q01[0]), green(q11[0]))
        mo = (q00[1], q10[1], q01[1], q11[1])   # muschio ai 4 angoli
        mu = (q00[2], q10[2], q01[2], q11[2])   # fango ai 4 angoli
        surf = pygame.Surface((ts, ts))
        den = max(1, ts - 1)
        for y in range(ts):
            fy = y / den
            lr = tuple(g00[i] + (g01[i] - g00[i]) * fy for i in range(3))
            rr = tuple(g10[i] + (g11[i] - g10[i]) * fy for i in range(3))
            moL = mo[0] + (mo[2] - mo[0]) * fy; moR = mo[1] + (mo[3] - mo[1]) * fy
            muL = mu[0] + (mu[2] - mu[0]) * fy; muR = mu[1] + (mu[3] - mu[1]) * fy
            for x in range(ts):
                fx = x / den
                r = lr[0] + (rr[0] - lr[0]) * fx
                g = lr[1] + (rr[1] - lr[1]) * fx
                b = lr[2] + (rr[2] - lr[2]) * fx
                mossf = (moL + (moR - moL) * fx) / MOSS_QUANT
                if mossf > 0:
                    k = mossf * 0.65
                    r += (JUNGLE_MOSS[0] - r) * k
                    g += (JUNGLE_MOSS[1] - g) * k
                    b += (JUNGLE_MOSS[2] - b) * k
                mudf = (muL + (muR - muL) * fx) / MUD_QUANT
                if mudf > 0:
                    k = mudf * 0.9
                    r += (JUNGLE_MUD[0] - r) * k
                    g += (JUNGLE_MUD[1] - g) * k
                    b += (JUNGLE_MUD[2] - b) * k
                surf.set_at((x, y), (int(r), int(g), int(b)))
        rng = random.Random(hash((q00, q10, q01, q11)) & 0xFFFFFFFF)
        avg_mud = sum(mu) / (4 * MUD_QUANT)
        avg_moss = sum(mo) / (4 * MOSS_QUANT)
        # Ciuffetti sottili d'erba: vita sul verde, ma spariscono sul fango nudo.
        if avg_mud < 0.5:
            for _ in range(rng.randint(3, 5)):
                x = rng.randint(2, ts - 2)
                y = rng.randint(ts // 2, ts - 2)
                hgt = rng.randint(2, max(3, ts // 4))
                c = GRASS_TUFT_LIGHT if rng.random() < 0.6 else GRASS_TUFT_DARK
                pygame.draw.line(surf, c, (x, y), (x, y - hgt), 1)
        # Fiocchi di muschio dove la chiazza è densa; granelli dove c'è fango.
        if avg_moss > 0.25:
            for _ in range(rng.randint(2, 4)):
                x = rng.randint(1, ts - 2); y = rng.randint(1, ts - 2)
                c = MOSS_FLECK_L if rng.random() < 0.5 else MOSS_FLECK_D
                pygame.draw.circle(surf, c, (x, y), 1)
        if avg_mud > 0.3:
            for _ in range(rng.randint(2, 4)):
                x = rng.randint(1, ts - 2); y = rng.randint(1, ts - 2)
                pygame.draw.circle(surf, MUD_SPECK, (x, y), 1)
        return surf

    # --- Sentiero di terra battuta: pennello morbido e irregolare ------------
    def _dirt_stamp(self, r: int, variant: int) -> pygame.Surface:
        """Macchia di terra battuta con bordo IRREGOLARE e sfumato (cache per
        (raggio, variante)). Usata a timbro lungo i sentieri camp->lane: dischi
        sovrapposti -> una striscia continua ma dal profilo mosso, non una
        riga retta."""
        ts = self.tile_size
        key = (ts, "dirt", r, variant)
        s = self._tile_cache.get(key)
        if s is not None:
            return s
        d = 2 * r + 1
        s = pygame.Surface((d, d), pygame.SRCALPHA)
        rng = random.Random((variant * 2654435761 ^ 0x9E) & 0xFFFFFFFF)
        p1 = rng.uniform(0, math.tau); p2 = rng.uniform(0, math.tau)
        for y in range(d):
            dy = y - r
            for x in range(d):
                dx = x - r
                dist = math.hypot(dx, dy)
                if dist < 1e-3:
                    ang = 0.0
                else:
                    ang = math.atan2(dy, dx)
                # Raggio modulato dall'angolo -> contorno bitorzoluto (no cerchio).
                rr = r * (1.0 + 0.20 * math.sin(ang * 3 + p1) + 0.12 * math.sin(ang * 5 + p2))
                if dist > rr:
                    continue
                f = dist / rr                      # 0 centro .. 1 bordo
                a = int(228 * (1 - f) ** 1.35)     # nucleo pieno, sfuma al bordo
                if a <= 0:
                    continue
                # Terra battuta: nucleo secco e chiaro (calpestato), poi terra più
                # scura verso il bordo umido -> stacca dall'erba, bordi morbidi.
                base = DIRT_DRY if f < 0.45 else JUNGLE_DIRT
                j = rng.randint(-7, 7)
                col = (max(0, min(255, base[0] + j)),
                       max(0, min(255, base[1] + j)),
                       max(0, min(255, base[2] + j)), a)
                s.set_at((x, y), col)
        # Qualche sassolino/granello sul battuto.
        for _ in range(rng.randint(3, 6)):
            px = rng.randint(1, d - 2); py = rng.randint(1, d - 2)
            if math.hypot(px - r, py - r) > r * 0.8:
                continue
            c = MUD_SPECK if rng.random() < 0.5 else (JUNGLE_DIRT[0] + 14,
                                                      JUNGLE_DIRT[1] + 12, JUNGLE_DIRT[2] + 10)
            s.set_at((px, py), (c[0], c[1], c[2], 150))
        self._tile_cache[key] = s
        return s

    # --- Cespuglio connesso (neighbor-aware): un blocco = un'unica chioma -----
    def _bush_surf(self, mask: int, variant: int, H: int) -> pygame.Surface:
        ts = self.tile_size
        key = (ts, "bush", mask, variant, H)
        s = self._tile_cache.get(key)
        if s is None:
            s = self._build_bush(mask, variant, ts, H)
            self._tile_cache[key] = s
        return s

    @staticmethod
    def _sphere(surf, cx, cy, r, sh_col, hi_col):
        """Sfera illuminata da alto-sinistra: anelli concentrici dal colore
        d'ombra (bordo) al colpo di luce (centro spostato in alto-sinistra).
        È il mattone 3D delle chiome: dà volume vero, non un cerchio piatto."""
        for i in range(r, 0, -1):
            f = (i / r) ** 0.85                       # 1 bordo .. 0 centro
            col = (int(hi_col[0] + (sh_col[0] - hi_col[0]) * f),
                   int(hi_col[1] + (sh_col[1] - hi_col[1]) * f),
                   int(hi_col[2] + (sh_col[2] - hi_col[2]) * f))
            off = int((r - i) * 0.42)                 # luce verso alto-sinistra
            pygame.draw.circle(surf, col, (cx - off, cy - off), i)

    def _build_bush(self, mask: int, variant: int, ts: int, H: int) -> pygame.Surface:
        """Un tile come pezzo di un'unica chioma.

        mask bit: 1=N 2=E 4=S 8=W (anch'esso cespuglio). Sui lati INTERNI la
        chioma riempie a filo del bordo e i lobi di foglie sconfinano -> la
        massa è continua coi vicini; sui lati ESPOSTI si arrotonda con stacco
        netto dal terreno (contorno scuro + ombra di contatto).
        """
        n = bool(mask & 1); e = bool(mask & 2); s = bool(mask & 4); w = bool(mask & 8)
        surf = pygame.Surface((ts, ts + H), pygame.SRCALPHA)
        rng = random.Random((variant * 2654435761 ^ 0xB5) & 0xFFFFFFFF)
        L, R = 0, ts
        Ctop = 0 if n else max(1, int(H * 0.5))
        B = ts + H                      # terra
        span = max(1, B - Ctop)
        cx, cy = (L + R) // 2, (Ctop + B) // 2
        # Lato alto-sinistra esposto = cresta illuminata; basso-destra = fianco
        # in ombra -> i tile insieme leggono come UN'UNICA cupola 3D.

        def shape(target, color):
            """Silhouette: tonda sui lati ESPOSTI (N/E/W), a filo su quelli
            interni; base SEMPRE piatta (il cespuglio appoggia a terra)."""
            pygame.draw.ellipse(target, color, pygame.Rect(L, Ctop, R - L, B - Ctop))
            pygame.draw.rect(target, color, pygame.Rect(L, cy, R - L, B - cy))  # base piatta
            if n:
                pygame.draw.rect(target, color, pygame.Rect(L, Ctop, R - L, cy - Ctop))
            if w:
                pygame.draw.rect(target, color, pygame.Rect(L, Ctop, cx - L, B - Ctop))
            if e:
                pygame.draw.rect(target, color, pygame.Rect(cx, Ctop, R - cx, B - Ctop))

        # (1) Ombra di contatto sull'erba (stacco netto dal pavimento).
        if not (n and e and s and w):
            sh = pygame.Surface((ts, ts + H), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, BUSH_CONTACT,
                                pygame.Rect(1, B - int(ts * 0.42), ts - 2, int(ts * 0.5)))
            surf.blit(sh, (0, 0))

        # La chioma si disegna a parte e poi si RITAGLIA sulla silhouette tonda.
        canopy = pygame.Surface((ts, ts + H), pygame.SRCALPHA)
        shape(canopy, BUSH_DARK)        # massa base

        # (2) GRAPPOLI: pochi, grandi, ognuno una SFERA illuminata (vero 3D). La
        #     luce è come i muretti: VERTICALE (cima chiara, base in ombra), con
        #     un filo di bias a sinistra. Il tono dipende dalla posizione nel
        #     grappolo (non per-tile) -> niente cuciture tra tile vicine.
        tiers = ((BUSH_SHADOW, BUSH_DARK),     # 0: fondo/fronte in ombra
                 (BUSH_DARK, BUSH_MID),        # 1: corpo
                 (BUSH_MID, BUSH_LIGHT),       # 2: cupola a mezza luce
                 (BUSH_LIGHT, BUSH_HILITE))    # 3: cresta illuminata
        clumps = []
        base_r = int(ts * 0.4)
        for gyq in range(3):
            for gxq in range(3):
                if (gxq + gyq) % 2 and rng.random() < 0.45:
                    continue
                px = L + int((gxq + 0.5) / 3 * (R - L)) + rng.randint(-3, 3)
                py = Ctop + int((gyq + 0.4) / 3 * span) + rng.randint(-3, 3)
                r = base_r + rng.randint(-ts // 8, ts // 10)
                clumps.append((px, py, max(4, r)))
        # dal fondo alla cima: i grappoli alti coprono quelli bassi (profondità).
        clumps.sort(key=lambda c: c[1], reverse=True)
        # Bias globale sul grappolo (non per-tile): così una colonna di tile è
        # un gradiente unico cima->base, senza cuciture tra una tile e l'altra.
        vbias = (0.34 if (s and not n) else -0.30 if (n and not s) else 0.0)
        hbias = (0.10 if (e and not w) else -0.10 if (w and not e) else 0.0)
        for px, py, r in clumps:
            hn = (py - Ctop) / span                 # 0 cima .. 1 base
            xn = max(0.0, min(1.0, px / ts))
            score = (1.0 - hn) + vbias + hbias       # dominante: l'altezza
            score += (0.15 * (1.0 - xn)) if not w else 0.0
            if not s:
                score -= 0.22 * hn                   # la base esposta va in ombra
            ti = 3 if score > 0.74 else 2 if score > 0.48 else 1 if score > 0.24 else 0
            sh_col, hi_col = tiers[ti]
            self._sphere(canopy, px, py, r, sh_col, hi_col)

        # (3) FRONTE in ombra alla base esposta (sud): come la parete dei muretti
        #     dà ALTEZZA. Solo se il lato sud è esposto (non spezza il grappolo).
        if not s:
            hf = int(span * 0.5)
            grad = pygame.Surface((ts, hf), pygame.SRCALPHA)
            for yy in range(hf):
                a = int(120 * (yy / max(1, hf - 1)) ** 1.5)
                pygame.draw.line(grad, (0, 0, 0, a), (0, yy), (ts, yy))
            canopy.blit(grad, (0, B - hf))

        # (4) Luce di cupola additiva sulla CIMA esposta (nord): accende la cresta.
        if not n:
            hf = int(span * 0.55)
            glow = pygame.Surface((ts, hf), pygame.SRCALPHA)
            for yy in range(hf):
                v = int(42 * (1 - yy / max(1, hf - 1)) ** 1.2)
                pygame.draw.line(glow, (v, int(v * 1.2), int(v * 0.7)), (0, yy), (ts, yy))
            canopy.blit(glow, (0, Ctop), special_flags=pygame.BLEND_RGB_ADD)

        # (5) Ritaglio sulla silhouette tonda (azzera ciò che sborda).
        masks = pygame.Surface((ts, ts + H), pygame.SRCALPHA)
        shape(masks, (255, 255, 255, 255))
        canopy.blit(masks, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(canopy, (0, 0))

        # (6) CRESTA DI LUCE sul profilo alto esposto (il cue "cupola che sporge
        #     verso l'alto", come la cima chiara dei muretti). Salto i lati interni.
        fw = max(2, int(ts * 0.14))
        for x in range(L, R):
            top_y = None
            for y in range(Ctop, cy + 1):
                if masks.get_at((x, y))[3] > 0:
                    top_y = y
                    break
            if top_y is None or (n and top_y <= Ctop + 1):
                continue
            if (w and x < fw) or (e and x >= R - fw):
                continue
            surf.set_at((x, top_y), BUSH_RIMLIGHT)
            if top_y + 1 < B:
                surf.set_at((x, top_y + 1), BUSH_HILITE)

        # (7) Base scura di contatto a terra sul lato sud esposto.
        if not s:
            pygame.draw.line(surf, BUSH_RIM, (L, B - 1), (R, B - 1), 2)
        return surf

    def _build_tile(self, t: int, variant: int, ts: int) -> pygame.Surface:
        surf = pygame.Surface((ts, ts))
        rng = random.Random((t << 4) | variant)
        if t == TILE_LANE:
            self._paint_lane(surf, ts, rng)
        elif t in (TILE_RIVER, TILE_PUDDLE):
            self._paint_water(surf, ts, t, rng)
        else:
            surf.fill(TILE_COLORS.get(t, TILE_COLORS[0]))
        return surf

    def _build_tall(self, t: int, variant: int, ts: int, H: int) -> pygame.Surface:
        surf = pygame.Surface((ts, ts + H), pygame.SRCALPHA)
        rng = random.Random((t << 8) | (variant << 2) | 1)
        # Ombra proiettata a terra (ellisse morbida sulla base).
        sh = pygame.Surface((ts, ts), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, PROP_SHADOW,
                            pygame.Rect(ts // 8, H + ts // 2, ts - ts // 4, ts // 2))
        surf.blit(sh, (0, 0))
        # TILE_WALL -> muro di confine in pietra costruita (il cespuglio ha il
        # suo builder neighbor-aware, _build_bush).
        self._paint_stone_tall(surf, ts, H, rng, STONE_WALL)
        return surf

    # --- Altopiano roccioso della giungla (neighbor-aware) -------------------
    def _jwall_surf(self, mask: int, variant: int, H: int) -> pygame.Surface:
        ts = self.tile_size
        key = (ts, "jw", mask, variant, H)
        surf = self._tile_cache.get(key)
        if surf is None:
            surf = self._build_jwall(mask, variant, ts, H)
            self._tile_cache[key] = surf
        return surf

    def _build_jwall(self, mask: int, variant: int, ts: int, H: int):
        """Un tile come pezzo di un unico altopiano roccioso.

        mask bit: 1=N 2=E 4=S 8=W (vicino anch'esso muro-giungla). La cima è
        continua tra tile adiacenti; la parete (cliff) e i bordi-luce/ombra si
        disegnano solo sui lati ESPOSTI, così un blocco connesso legge come una
        formazione sola invece di tanti blocchi.
        """
        n = bool(mask & 1); e = bool(mask & 2); s = bool(mask & 4); w = bool(mask & 8)
        surf = pygame.Surface((ts, ts + H), pygame.SRCALPHA)
        rng = random.Random(variant * 2654435761 & 0xFFFFFFFF)
        top_h = ts                      # la cima occupa [0, ts]; il cliff [ts, ts+H]

        # (1) CIMA: facce rocciose grosse e spigolose + massi in rilievo.
        pygame.draw.rect(surf, JW_TOP, pygame.Rect(0, 0, ts, top_h))
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, 0, ts, top_h))
        for _ in range(rng.randint(2, 4)):
            fcx = rng.randint(-ts // 4, ts + ts // 4)
            fcy = rng.randint(-ts // 5, top_h + ts // 5)
            fr = rng.randint(max(4, ts // 3), max(7, int(ts * 0.62)))
            self._rock_facet(surf, fcx, fcy, fr, rng, JW_TOP, JW_HILITE, JW_TOP_SH)
        for _ in range(rng.randint(2, 4)):     # muschio nelle fessure
            mx = rng.randint(1, ts - 2); my = rng.randint(1, top_h - 2)
            mc = JW_MOSS if rng.random() < 0.6 else JW_MOSS_DK
            pygame.draw.circle(surf, mc, (mx, my), rng.randint(1, max(2, ts // 8)))
        for _ in range(1 if (variant % 2 == 0) else 0):   # masso in rilievo
            bx = rng.randint(ts // 4, 3 * ts // 4)
            by = rng.randint(top_h // 3, 2 * top_h // 3)
            br = rng.randint(max(4, ts // 3), max(6, int(ts * 0.5)))
            self._boulder(surf, bx, by, br, rng)
        surf.set_clip(clip)

        # (2) BORDI ESPOSTI: su OGNI lato che tocca un altro terreno la roccia
        # non è uno spigolo dritto ma una fila di massi tondi che "rotolano"
        # oltre il bordo e bombano in fuori (la roccia vera curva, non è verticale).
        er = max(3, int(ts * 0.3))             # raggio dei massi di bordo
        step = max(4, int(ts * 0.5))
        if not n:                              # bordo nord (verso la luce -> chiaro)
            for bx in range(0, ts + 1, step):
                self._round_rock(surf, bx + rng.randint(-2, 2), rng.randint(-1, 2),
                                  er, rng, JW_TOP, JW_HILITE, JW_TOP_SH)
        if not w:                              # bordo ovest (verso la luce -> chiaro)
            for by in range(0, top_h + 1, step):
                self._round_rock(surf, rng.randint(-1, 2), by + rng.randint(-2, 2),
                                  er, rng, JW_TOP, JW_HILITE, JW_TOP_SH)
        if not e:                              # bordo est (in ombra)
            for by in range(0, top_h + 1, step):
                self._round_rock(surf, ts - 1 + rng.randint(-2, 1), by + rng.randint(-2, 2),
                                  er, rng, JW_TOP_SH, JW_TOP, JW_EDGE_SH)

        # (3) FRONTE SUD: la parete che il giocatore vede. Non un muro verticale
        # ma grossi massi arrotondati che partono da terra, bombano in fuori e
        # curvano rotolando sopra lo spigolo della cima.
        if not s:
            cy0, cy1 = top_h, ts + H
            pygame.draw.rect(surf, JW_CLIFF_DK, pygame.Rect(0, cy0 + 1, ts, cy1 - cy0 - 1))
            nb = rng.randint(2, 3)
            for i in range(nb + 2):
                bx = int(i * ts / (nb + 1)) + rng.randint(-3, 3)
                br = rng.randint(int(ts * 0.3), int(ts * 0.42))
                # cupola che bomba in fuori e rotola appena oltre lo spigolo cima
                by = cy1 - int(br * 0.6) + rng.randint(-1, 2)
                self._round_rock(surf, bx, by, br, rng, JW_CLIFF, JW_CLIFF_HI, JW_CLIFF_DK)
            # ombreggiatura verticale: più scuro verso il basso (dà la curvatura)
            grad = pygame.Surface((ts, cy1 - cy0), pygame.SRCALPHA)
            h2 = cy1 - cy0
            for yy in range(h2):
                a = int(80 * (yy / max(1, h2 - 1)) ** 1.4)
                pygame.draw.line(grad, (0, 0, 0, a), (0, yy), (ts, yy))
            surf.blit(grad, (0, cy0))
            # ombra di contatto sull'erba, alla base.
            contact = pygame.Surface((ts, 3), pygame.SRCALPHA)
            contact.fill(JW_CONTACT)
            surf.blit(contact, (0, cy1 - 2))
        return surf

    def _rock_facet(self, surf, cx, cy, r, rng, base_col, hi_col, sh_col):
        """Faccia di roccia irregolare e spigolosa (poligono) con fessura netta
        e forte luce/ombra direzionale (luce da alto-sinistra)."""
        nv = rng.randint(4, 6)                       # pochi lati = spigoloso
        a0 = rng.random() * math.tau
        pts = []
        for k in range(nv):
            a = a0 + k * (math.tau / nv)
            rr = r * (0.58 + rng.random() * 0.6)     # raggio molto variabile
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        d = rng.randint(-14, 16)
        base = tuple(max(0, min(255, base_col[j] + d)) for j in range(3))
        pygame.draw.polygon(surf, base, pts)
        pygame.draw.polygon(surf, sh_col, pts, 1)    # fessura/contorno scuro
        # Spigoli verso la luce = chiari e spessi; verso l'ombra = scuri.
        for k in range(nv):
            ax, ay = pts[k]
            bx, by = pts[(k + 1) % nv]
            mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
            if mx <= cx and my <= cy:
                pygame.draw.line(surf, hi_col, (ax, ay), (bx, by), 2)
            elif mx >= cx and my >= cy:
                pygame.draw.line(surf, sh_col, (ax, ay), (bx, by), 2)

    def _round_rock(self, surf, cx, cy, r, rng, base_col, hi_col, sh_col):
        """Masso tondo: corpo + cupola illuminata (alto-sx) + fondo in ombra.
        Il profilo curvo evita l'effetto 'colonna verticale' sui bordi."""
        base = self._jitter(base_col, rng, 7)
        pygame.draw.circle(surf, base, (int(cx), int(cy)), r)
        # fondo/bordo in ombra (mezzaluna bassa-destra) -> curvatura
        pygame.draw.arc(surf, sh_col, pygame.Rect(int(cx) - r, int(cy) - r, r * 2, r * 2),
                        math.pi * 1.05, math.pi * 1.95, max(1, r // 3))
        # cupola illuminata (verso la luce)
        pygame.draw.circle(surf, hi_col, (int(cx) - r // 3, int(cy) - r // 3), max(1, r // 2))

    def _boulder(self, surf, cx, cy, r, rng):
        """Masso tondeggiante che SPORGE sulla cima: ombra proiettata + cupola
        illuminata, per dare rilievo 3D vero."""
        # ombra proiettata (verso basso-destra, lato opposto alla luce)
        sh = pygame.Surface((r * 3, r * 3), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 80),
                            pygame.Rect(r, int(r * 1.3), int(r * 1.9), int(r * 1.2)))
        surf.blit(sh, (cx - r, cy - r))
        # corpo
        pygame.draw.circle(surf, JW_BOULDER, (cx, cy), r)
        # cupola illuminata alto-sinistra
        pygame.draw.circle(surf, JW_BOULDER_HI, (cx - r // 3, cy - r // 3), max(1, r // 2))
        # bordo in ombra basso-destra
        pygame.draw.arc(surf, JW_CLIFF_DK,
                        pygame.Rect(cx - r, cy - r, r * 2, r * 2), math.pi * 1.1, math.pi * 1.9, 2)

    @staticmethod
    def _jitter(col, rng, amt=8):
        return tuple(max(0, min(255, c + rng.randint(-amt, amt))) for c in col)

    def _paint_lane(self, surf, ts, rng):
        surf.fill(LANE_BASE)
        for _ in range(rng.randint(6, 10)):
            x, y = rng.randint(0, ts - 1), rng.randint(0, ts - 1)
            col = LANE_SPECK_L if rng.random() < 0.5 else LANE_SPECK_D
            pygame.draw.circle(surf, col, (x, y), 1)

    def _paint_water(self, surf, ts, t, rng):
        # Colore quasi uniforme: così i tile adiacenti si fondono e sembra un
        # corso d'acqua unico, non "mattonelle blu".
        surf.fill(WATER_MID)
        # Profondità a macchie morbide (niente bande per-tile).
        for _ in range(3):
            lighter = (WATER_MID[0] + 10, WATER_MID[1] + 12, WATER_MID[2] + 12)
            col = WATER_DEEP if rng.random() < 0.55 else lighter
            cx, cy = rng.randint(0, ts), rng.randint(0, ts)
            pygame.draw.circle(surf, col, (cx, cy), rng.randint(ts // 3, ts // 2 + 2))
        veil = pygame.Surface((ts, ts), pygame.SRCALPHA)
        veil.fill((*WATER_MID, 120))
        surf.blit(veil, (0, 0))
        # Corrente: trattini diagonali che attraversano il tile (senso di flusso).
        for _ in range(rng.randint(3, 5)):
            x = rng.randint(-ts // 3, ts - ts // 3)
            y = rng.randint(2, ts - 2)
            ln = rng.randint(ts // 2, ts)
            col = WATER_FOAM if rng.random() < 0.28 else WATER_FLOW
            pygame.draw.line(surf, col, (x, y), (x + ln, y - ln // 4), 1)

    def _paint_stone_tall(self, surf, ts, H, rng, pal):
        """Muro di confine in pietra 2.5D: cima chiara, fronte con giunti di malta.

        `pal` = (cima, fronte, ombra, malta).
        """
        top, face, shadow, line = pal
        top_h = H + max(2, ts // 6)          # cima illuminata
        fy = ts + H                          # fondo
        pygame.draw.rect(surf, face, pygame.Rect(0, top_h, ts, fy - top_h))
        sb = max(2, ts // 8)
        pygame.draw.rect(surf, shadow, pygame.Rect(ts - sb, top_h, sb, fy - top_h))
        pygame.draw.rect(surf, shadow, pygame.Rect(0, fy - 2, ts, 2))
        pygame.draw.rect(surf, top, pygame.Rect(0, 0, ts, top_h))
        hi = tuple(min(255, c + 22) for c in top)
        pygame.draw.line(surf, hi, (0, 0), (ts, 0))
        pygame.draw.line(surf, hi, (0, 0), (0, top_h))
        row_h = max(3, (fy - top_h) // 3)
        y = top_h
        r = 0
        while y < fy:
            pygame.draw.line(surf, line, (0, y), (ts, y), 1)
            off = (ts // 2) if (r % 2) else 0
            vx = off
            while vx < ts:
                pygame.draw.line(surf, line, (vx, y), (vx, min(fy, y + row_h)), 1)
                vx += ts // 2
            y += row_h
            r += 1

    def _shore(self, surface, grid, tx, ty, sx, sy, ground, t):
        """Riva graduale dove fiume e terra si incontrano: bassofondo chiaro sul
        lato acqua + fango/sabbia bagnata sul lato terra. Passaggio morbido (non
        un bordo netto), così acqua e giungla sembrano comunicare."""
        water = (TILE_RIVER, TILE_PUDDLE)
        is_water = t in water
        land_ground = ground in (TILE_FLOOR, TILE_LANE)
        if not (is_water or land_ground):
            return
        for side, dx, dy in (("N", 0, -1), ("E", 1, 0), ("S", 0, 1), ("W", -1, 0)):
            nb = grid.tile_at(tx + dx, ty + dy)
            nb_water = nb in water
            if is_water and not nb_water:
                surface.blit(self._shore_overlay(side, "water"), (sx, sy))
            elif land_ground and nb_water:
                surface.blit(self._shore_overlay(side, "land"), (sx, sy))
            # Lane <-> erba: bordo sfumato (terra battuta sull'erba, erba che
            # invade la lane) -> il sentiero si fonde con la giungla.
            elif t == TILE_LANE and nb == TILE_FLOOR:
                surface.blit(self._shore_overlay(side, "fringe"), (sx, sy))
            elif ground == TILE_FLOOR and nb == TILE_LANE:
                surface.blit(self._shore_overlay(side, "path"), (sx, sy))

    def _shore_overlay(self, side: str, kind: str) -> pygame.Surface:
        """Striscia-riva sfumata perpendicolare al bordo `side` del tile.

        kind='water': schiuma al contatto -> bassofondo chiaro -> trasparente.
        kind='land' : terra bagnata scura al contatto -> sabbia -> trasparente.
        """
        ts = self.tile_size
        key = (ts, "shore", side, kind)
        s = self._tile_cache.get(key)
        if s is not None:
            return s
        s = pygame.Surface((ts, ts), pygame.SRCALPHA)
        deep = kind in ("water", "land")
        depth = max(5, int(ts * (0.55 if deep else 0.42)))
        rng = random.Random(hash((side, kind)) & 0xFFFF)
        for i in range(depth):                 # i = distanza dal bordo
            f = i / depth                      # 0 al bordo .. 1 all'interno
            if kind == "water":
                if i == 0:
                    col = (*WATER_FOAM, 170)
                elif i <= 1:
                    col = (*WATER_SHALLOW, 150)
                else:
                    col = (*WATER_SHALLOW, int(140 * (1 - f) ** 1.3))
            elif kind == "land":
                if i <= 1:
                    col = (*SHORE_WET, int(185 * (1 - f)))
                else:
                    col = (*SHORE_SAND, int(165 * (1 - f) ** 1.25))
            elif kind == "path":        # bordo erba: terra battuta che sfuma
                col = (*PATH_EDGE, int(135 * (1 - f) ** 1.3))
            else:                       # "fringe" -> erba che invade la lane
                col = (*GRASS_FRINGE, int(150 * (1 - f) ** 1.4))
            if side == "N":
                pygame.draw.line(s, col, (0, i), (ts, i))
            elif side == "S":
                pygame.draw.line(s, col, (0, ts - 1 - i), (ts, ts - 1 - i))
            elif side == "W":
                pygame.draw.line(s, col, (i, 0), (i, ts))
            else:  # E
                pygame.draw.line(s, col, (ts - 1 - i, 0), (ts - 1 - i, ts))

        # Bordo irregolare lane<->erba: ciuffi/granelli che rompono la linea
        # retta, così il passaggio sembra naturale e non una fascia netta.
        if kind in ("path", "fringe"):
            def pt(along, into):               # coord dal bordo `side`
                if side == "N":
                    return (along, into)
                if side == "S":
                    return (along, ts - 1 - into)
                if side == "W":
                    return (into, along)
                return (ts - 1 - into, along)   # E
            for _ in range(rng.randint(5, 8)):
                a = rng.randint(0, ts - 1)
                into = rng.randint(1, depth)
                if kind == "fringe":           # ciuffo d'erba verso la lane
                    c = GRASS_TUFT_LIGHT if rng.random() < 0.5 else GRASS_FRINGE
                    x0, y0 = pt(a, into)
                    x1, y1 = pt(a, max(0, into - rng.randint(2, 3)))
                    pygame.draw.line(s, c, (x0, y0), (x1, y1), 1)
                else:                          # granello di terra sull'erba
                    pygame.draw.circle(s, PATH_EDGE, pt(a, into), 1)
        self._tile_cache[key] = s
        return s

    def _draw_dens(self, surface, camera, dens):
        ts = self.tile_size
        for name, (dx, dy) in dens.items():
            sx, sy = camera.world_to_screen(dx * ts, dy * ts)
            col = DEN_COLORS.get(name, (220, 220, 220))
            pygame.draw.circle(surface, col, (sx, sy), ts, 2)
            pygame.draw.circle(surface, col, (sx, sy), 3)

    # --- percorso di debug ---------------------------------------------------
    def draw_aim(self, surface, camera, origin, mouse_tile, move):
        """Indicatore di mira mentre si tiene premuto il tasto mossa.

        Mostra la gittata e l'area reale di colpo (linea/cono/cerchio/scatto).
        """
        ts = self.tile_size
        col = type_color(move.type)
        ox, oy = origin.x, origin.y
        mx, my = mouse_tile
        dx, dy = mx - ox, my - oy
        dist = math.hypot(dx, dy) or 1.0
        nx, ny = dx / dist, dy / dist
        rng = move.range

        def S(wx, wy):
            return camera.world_to_screen(wx * ts, wy * ts)

        # Gittata (cerchio attorno al lanciatore) quando ha senso.
        if rng > 0 and move.shape in ("projectile", "bubble", "area", "dash", "cone",
                                      "sub", "blink", "storm", "leap", "rain"):
            pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)

        shape = move.shape
        if shape in ("projectile", "bubble"):
            ex, ey = ox + nx * rng, oy + ny * rng
            pygame.draw.line(surface, col, S(ox, oy), S(ex, ey), max(1, int(move.radius * ts)))
            if shape == "bubble":
                pygame.draw.circle(surface, col, S(ex, ey), int(move.radius * ts), 1)
        elif shape in ("dash", "sub"):
            d = min(dist, rng)
            pygame.draw.line(surface, col, S(ox, oy), S(ox + nx * d, oy + ny * d),
                             max(2, int(move.radius * ts)))
            pygame.draw.circle(surface, col, S(ox + nx * d, oy + ny * d), int(move.radius * ts), 1)
        elif shape == "blink":
            d = min(dist, rng)
            ex, ey = ox + nx * d, oy + ny * d
            pygame.draw.circle(surface, col, S(ex, ey), max(4, int(0.6 * ts)))      # dove apparirai
            pygame.draw.circle(surface, (255, 255, 255), S(ex, ey), max(4, int(0.6 * ts)), 1)
            pygame.draw.line(surface, col, S(ex - 0.4, ey), S(ex + 0.4, ey), 1)
            pygame.draw.line(surface, col, S(ex, ey - 0.4), S(ex, ey + 0.4), 1)
        elif shape == "cone":
            base = math.atan2(ny, nx)
            half = math.radians(move.angle)
            for a in (base - half, base + half):
                pygame.draw.line(surface, col, S(ox, oy),
                                 S(ox + math.cos(a) * rng, oy + math.sin(a) * rng), 1)
        elif shape in ("area", "storm", "leap", "rain"):
            d = min(dist, rng)
            cx, cy = (ox, oy) if move.target == "self" or rng <= 0 else (ox + nx * d, oy + ny * d)
            # cerchio pieno/alone per la zona d'impatto (più evidente per le AoE larghe)
            r = int(move.radius * ts)
            glow = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*col, 45), (r + 2, r + 2), r)
            sx, sy = S(cx, cy)
            surface.blit(glow, (sx - r - 2, sy - r - 2))
            pygame.draw.circle(surface, col, (sx, sy), r, 2)
        elif shape == "buff":
            r = int((move.radius if move.radius > 0 else 1.5) * ts)
            pygame.draw.circle(surface, col, S(ox, oy), r, 1)

    def _draw_fog(self, surface, camera, grid, vision, team):
        """Nebbia di guerra: scuro dove non visibile, penombra dove esplorato."""
        ts = self.tile_size
        x0, y0, x1, y1 = camera.visible_tile_bounds(ts, grid.width, grid.height)
        fog = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        fog.fill((6, 7, 12, 235))                       # non esplorato (quasi nero)
        vis = vision.visible_tiles.get(team, set())
        exp = vision.explored.get(team, set())
        for ty in range(y0, y1):
            for tx in range(x0, x1):
                sx, sy = camera.world_to_screen(tx * ts, ty * ts)
                rect = pygame.Rect(sx, sy, ts, ts)
                if (tx, ty) in vis:
                    fog.fill((0, 0, 0, 0), rect)          # pienamente visibile
                elif (tx, ty) in exp:
                    fog.fill((8, 10, 16, 110), rect)      # esplorato: penombra
        surface.blit(fog, (0, 0))

    def _draw_respawns(self, surface, camera, respawning):
        """Marcatore di respawn alla base: un anello che si riempie col tempo."""
        ts = self.tile_size
        for (pos, team, progress) in respawning:
            sx, sy = camera.world_to_screen(pos.x * ts, pos.y * ts)
            base = config.TEAM_COLORS.get(team, (200, 200, 200))
            dim = tuple(c // 2 for c in base)
            r = int(0.5 * ts)
            # Anello esterno (posto del respawn).
            pygame.draw.circle(surface, dim, (sx, sy - r), r, 1)
            # Disco interno che cresce fino al respawn.
            fill_r = max(1, int(r * max(0.0, min(1.0, progress))))
            pygame.draw.circle(surface, dim, (sx, sy - r), fill_r)

    def _draw_path(self, surface, path, camera):
        ts = self.tile_size
        pts = [camera.world_to_screen(p.x * ts, p.y * ts) for p in path]
        if len(pts) >= 2:
            pygame.draw.lines(surface, COL_PATH, False, pts, 1)
        for p in pts:
            pygame.draw.circle(surface, COL_PATH, p, 2)

    # --- entità --------------------------------------------------------------
    def _draw_entities(self, surface, camera, world, animators, selected_id,
                       vision=None, player_team=0, now=1e9):
        ts = self.tile_size
        # Culling: solo ciò che è nel riquadro visibile (con margine).
        x0, y0, x1, y1 = camera.visible_tile_bounds(ts, world.grid.width, world.grid.height)

        drawables = []
        for s in world.structures():
            if s.alive and x0 - 2 <= s.pos.x <= x1 + 2 and y0 - 2 <= s.pos.y <= y1 + 2:
                drawables.append(s)
        for u in world.alive_units():
            if not (x0 - 2 <= u.pos.x <= x1 + 2 and y0 - 2 <= u.pos.y <= y1 + 2):
                continue
            # Nebbia di guerra: non disegnare le unità nemiche non visibili.
            if (vision is not None and u.team != player_team
                    and not vision.is_enemy_visible(player_team, u.id)):
                continue
            drawables.append(u)

        for e in sorted(drawables, key=lambda it: it.pos.y):
            gx, gy = camera.world_to_screen(e.pos.x * ts, e.pos.y * ts)
            if isinstance(e, Structure):
                self._draw_structure(surface, e, gx, gy)
            else:
                if e.id == selected_id:
                    r = int(e.radius * ts)
                    pygame.draw.ellipse(surface, COL_SELECT,
                                        pygame.Rect(gx - r, gy - r // 2, r * 2, r), 1)
                if isinstance(e, Pokemon) and getattr(e, "submerged", False):
                    self._draw_submerged(surface, e, gx, gy)
                    continue
                # "Sei nascosto": il tuo campione dentro un cespuglio viene
                # velato di verde (gli altri non ti vedono, vision.py).
                in_bush = (e.team == player_team and isinstance(e, Pokemon)
                           and world.grid.tile_at(int(e.pos.x), int(e.pos.y)) == TILE_BUSH)
                anim = animators.get(e.id)
                if anim is not None:
                    anim.draw(surface, gx, gy)
                if in_bush:
                    self._draw_hidden_hint(surface, e, gx, gy, now)
                self._draw_unit_hp(surface, e, gx, gy)
                if isinstance(e, Pokemon):
                    self._draw_status(surface, e, gx, gy, now)

    def _draw_hidden_hint(self, surface, u, gx, gy, now):
        """Velo verde traslucido sul campione nascosto in un cespuglio."""
        ts = self.tile_size
        r = int(u.radius * ts) + 4
        veil = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pulse = int(30 + 18 * (0.5 + 0.5 * math.sin(now * 3.0)))
        pygame.draw.circle(veil, (40, 90, 48, pulse), (r, r), r)
        pygame.draw.circle(veil, (70, 130, 72, 90), (r, r), r, 2)
        surface.blit(veil, (gx - r, gy - r))
        # Qualche fogliolina sospesa.
        for i in range(3):
            ang = now * 1.5 + i * 2.1
            lx = gx + int(math.cos(ang) * r * 0.7)
            ly = gy - int(abs(math.sin(ang)) * r * 0.6)
            pygame.draw.circle(surface, (90, 150, 80), (lx, ly), 1)

    def _draw_submerged(self, surface, u, gx, gy):
        """Unità sott'acqua (SUB): mostra solo un vortice/pozza, non lo sprite."""
        ts = self.tile_size
        r = int(u.radius * ts)
        ripple = pygame.Surface((r * 4, r * 2), pygame.SRCALPHA)
        rc = ripple.get_rect()
        for i, alpha in ((0, 150), (1, 90), (2, 50)):
            rr = pygame.Rect(0, 0, rc.w - i * r, rc.h - i * (r // 2))
            rr.center = rc.center
            pygame.draw.ellipse(ripple, (70, 130, 180, alpha), rr, 2)
        surface.blit(ripple, (gx - rc.w // 2, gy - rc.h // 2))
        # Piccolo anello della squadra per riconoscere la posizione.
        col = config.TEAM_COLORS.get(u.team, (200, 200, 200))
        pygame.draw.circle(surface, col, (gx, gy), max(2, r // 2), 1)

    def _draw_structure(self, surface, s, gx, gy):
        ts = self.tile_size
        col = getattr(s, "color", (180, 180, 180))
        r = int(s.radius * ts)
        if isinstance(s, Core):
            pygame.draw.rect(surface, col, pygame.Rect(gx - r, gy - r, r * 2, r * 2),
                             border_radius=4)
            pygame.draw.rect(surface, (255, 255, 255),
                             pygame.Rect(gx - r, gy - r, r * 2, r * 2), 1, border_radius=4)
        else:
            # Torre: base + fusto.
            pygame.draw.rect(surface, (40, 40, 46),
                             pygame.Rect(gx - r, gy - r // 2, r * 2, r))
            pygame.draw.rect(surface, col,
                             pygame.Rect(gx - r + 2, gy - r * 2, r * 2 - 4, int(r * 1.8)))
            pygame.draw.rect(surface, (255, 255, 255),
                             pygame.Rect(gx - r + 2, gy - r * 2, r * 2 - 4, int(r * 1.8)), 1)
        if config.SHOW_HP_BARS and s.hp < s.max_hp:
            self._hp_bar(surface, gx, gy - int(s.radius * ts) - 6,
                         s.hp / s.max_hp, col, width=r * 2)

    def _draw_status(self, surface, u, gx, gy, now):
        """Pallini di stato sopra l'unità (sonno/veleno/paralisi/rallentamento)."""
        pips = []
        if getattr(u, "sleep_until", -1) > now:
            pips.append((150, 210, 255))   # sonno (azzurro)
        if getattr(u, "poison_until", -1) > now:
            pips.append((170, 90, 210))    # veleno (viola)
        if getattr(u, "root_until", -1) > now:
            pips.append((230, 150, 60))    # paralisi (arancio)
        if getattr(u, "curse_until", -1) > now:
            pips.append((110, 90, 160))    # maledizione (viola scuro)
        elif getattr(u, "slow_until", -1) > now:
            pips.append((120, 160, 220))   # rallentamento (azzurrino)
        if not pips:
            return
        r = int(u.radius * self.tile_size)
        top = gy - 2 * r - 14
        for i, col in enumerate(pips):
            pygame.draw.circle(surface, col, (gx - len(pips) * 3 + i * 6, top), 3)
            pygame.draw.circle(surface, (15, 15, 15), (gx - len(pips) * 3 + i * 6, top), 3, 1)

    def _draw_unit_hp(self, surface, u, gx, gy):
        if not config.SHOW_HP_BARS:
            return
        if u.hp >= u.max_hp and not isinstance(u, Pokemon):
            return
        col = config.TEAM_COLORS.get(u.team, (200, 200, 200))
        r = int(u.radius * self.tile_size)
        top = gy - 2 * r - 8
        w = max(14, r * 2)
        self._hp_bar(surface, gx, top, max(0.0, u.hp / u.max_hp), col, width=w)

    def _hp_bar(self, surface, cx, top_y, frac, team_col, width):
        h = 3
        x = cx - width // 2
        pygame.draw.rect(surface, COL_HP_BG, pygame.Rect(x - 1, top_y - 1, width + 2, h + 2))
        pygame.draw.rect(surface, team_col, pygame.Rect(x, top_y, int(width * frac), h))
