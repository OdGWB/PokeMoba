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
from engine.entities import Core, Pillar, Pokemon, Structure, Unit
from engine.grid import (TILE_BUSH, TILE_FLOOR, TILE_JUNGLE_WALL, TILE_LANE,
                         TILE_PUDDLE, TILE_RIVER, TILE_WALL)
from . import spirit_fx
from . import charcadet_fx, corvi_fx, eevee_fx, noivern_fx
from . import structure_gfx
from .fx import EMBER, ROCK_HI, ROCK_MID, ROCK_OUT, ROCK_SH, type_color
from .map_renderer import MapRenderer

# Palette greybox (sostituita dai tileset in futuro).
COL_BG = (18, 20, 24)
_TOWER_RANGE_DEFAULT = config.TOWER_RANGE   # tile: fallback gittata (es. in rete)
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
# Matrice di Bayer 4x4 (ordered dithering), valori in [0,1): soglia per-pixel per
# le transizioni a gradini (bordo lane<->erba) in stile pixel art.
_BAYER = [[v / 16.0 for v in row] for row in
          ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))]

# --- Palette "texture" procedurali (strada 1): niente asset esterni, solo
#     draw-call rese stabili con un seed per-tile e messe in cache. ------------
# Suolo di giungla: un terreno UNICO, cupo e desaturato, verso il verde-blu.
# Il colore (verde a due scale + chiazze di muschio/fango) è calcolato PER PIXEL
# in coordinate MONDO (non per tile): il MapRenderer campiona una maschera a
# bassa risoluzione e la scala con smoothscale -> chiazze organiche che
# attraversano i tile senza cuciture né "mattonelle", fango dai bordi irregolari.
# Palette giungla (cupa, desaturata).
JUNGLE_BASE = (46, 74, 51)       # #2E4A33 base
JUNGLE_DARK = (35, 59, 41)       # #233B29 avvallamento in ombra
JUNGLE_LIGHT = (58, 90, 60)      # #3A5A3C dosso illuminato
JUNGLE_MOSS = (74, 107, 58)      # #4A6B3A muschio
JUNGLE_DIRT = (90, 74, 53)       # #5A4A35 terra/sentiero
JUNGLE_MUD = (74, 61, 44)        # #4A3D2C fango (schiarito)
DIRT_DRY = (112, 93, 66)         # battuto secco e chiaro (nucleo calpestato)
GRASS_LO = JUNGLE_DARK           # avvallamento in ombra
GRASS_HI = JUNGLE_LIGHT          # dosso illuminato
GRASS_CELL = 4.0                 # scala fine della tinta (in tile)
GRASS_CELL2 = 9.0                # scala larga (seconda ottava) -> dossi ampi
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
# Corsia: terra battuta DESATURATA (tirata verso il grigio-bruno) così non
# stona con la giungla cupa; il bordo contro l'erba è reso irregolare in _shore.
LANE_BASE = (138, 126, 99)
LANE_SPECK_L = (156, 144, 116)
LANE_SPECK_D = (114, 103, 80)
PATH_EDGE = (108, 91, 65)        # terra battuta sul bordo erba -> lane
GRASS_FRINGE = (54, 86, 52)      # erba (giungla) che invade il bordo della lane
# Cespuglio (2.5D): chiome a cupola illuminate dall'alto-sinistra. Verdi
# saturi, dal fondo in ombra profonda alla cresta brillante.
# Chiome con toni di giungla (desaturati, niente verde-lime): dal fondo in ombra
# profonda alla cresta appena accesa. Rifacimento completo rimandato a un passo
# futuro; per ora si armonizzano con la nuova palette del suolo.
BUSH_SHADOW = (13, 29, 17)       # fondo chioma, in ombra profonda
BUSH_DARK = (31, 59, 36)         # base foglia (#1F3B24)
BUSH_MID = (46, 83, 47)          # foglia a mezza luce
BUSH_LIGHT = (62, 107, 58)       # foglia illuminata (#3E6B3A)
BUSH_HILITE = (84, 128, 74)      # colpo di luce sulla cupola
BUSH_RIMLIGHT = (104, 146, 86)   # cresta sul bordo alto esposto (giungla, non lime)
BUSH_RIM = (8, 20, 12)           # contorno/contatto scuro alla base
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

    def _moss_at(self, tx: float, ty: float) -> float:
        """Densità di muschio in coord MONDO (in tile), 0..1. Due ottave: una
        larga per la forma della chiazza + una fine che increspa il bordo ->
        contorni organici e irregolari (non cerchi). Campionata per pixel dal
        MapRenderer su una maschera a bassa risoluzione, poi smoothscaled."""
        a = self._vnoise((tx + 123) / 6.5, (ty + 77) / 6.5)
        b = self._vnoise((tx + 123) / 2.4, (ty + 77) / 2.4)
        n = a * 0.74 + b * 0.26
        return max(0.0, min(1.0, (n - 0.55) / 0.22))

    def _mud_at(self, tx: float, ty: float) -> float:
        """Densità di fango in coord MONDO (in tile), 0..1, con bordi irregolari
        e sfumati (ottava fine che deforma la soglia). Vedi _moss_at."""
        a = self._vnoise((tx + 311) / 7.5, (ty + 517) / 7.5)
        b = self._vnoise((tx + 311) / 2.7, (ty + 517) / 2.7)
        n = a * 0.72 + b * 0.28
        # Soglia alzata (0.70) e rampa più stretta -> chiazze più piccole e
        # sparse (~60% di area in meno rispetto a prima).
        return max(0.0, min(1.0, (n - 0.70) / 0.12))

    def _floor_color(self, tx: float, ty: float):
        """Colore del suolo in un punto MONDO (coord in tile): verde a due scale
        + chiazze di muschio e fango. Tutto continuo nello spazio mondo, quindi
        indipendente dalla griglia dei tile (nessuna cucitura)."""
        t = self._two_octave(tx, ty)
        r = GRASS_LO[0] + (GRASS_HI[0] - GRASS_LO[0]) * t
        g = GRASS_LO[1] + (GRASS_HI[1] - GRASS_LO[1]) * t
        b = GRASS_LO[2] + (GRASS_HI[2] - GRASS_LO[2]) * t
        mo = self._moss_at(tx, ty)
        if mo > 0:
            k = mo * 0.6
            r += (JUNGLE_MOSS[0] - r) * k; g += (JUNGLE_MOSS[1] - g) * k; b += (JUNGLE_MOSS[2] - b) * k
        mu = self._mud_at(tx, ty)
        if mu > 0:
            k = mu * 0.92
            r += (JUNGLE_MUD[0] - r) * k; g += (JUNGLE_MUD[1] - g) * k; b += (JUNGLE_MUD[2] - b) * k
        return (int(r), int(g), int(b))

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
        # TILE_WALL -> muro di confine in pietra costruita (i cespugli sono
        # erba alta, costruita in map_renderer._build_bushes).
        self._paint_stone_tall(surf, ts, H, rng, STONE_WALL)
        return surf

    # --- Massi/faccette di roccia: mattoni condivisi dal builder della
    #     SILHOUETTE dei muri di giungla (MapRenderer._build_jungle_walls).

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
        # Il FIUME (TILE_RIVER) e' ora reso a livello mappa (MapRenderer._build_river:
        # silhouette smussata + riva sfumata), quindi qui NON genera piu' la riva
        # per-tile. Resta la pozza (TILE_PUDDLE, dinamica con la Pioggia).
        water = (TILE_PUDDLE,)
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
                surface.blit(self._edge_overlay(side, "fringe", tx, ty), (sx, sy))
            elif ground == TILE_FLOOR and nb == TILE_LANE:
                surface.blit(self._edge_overlay(side, "path", tx, ty), (sx, sy))

    def _edge_overlay(self, side: str, kind: str, tx: int, ty: int) -> pygame.Surface:
        """Bordo lane<->erba IRREGOLARE e in stile pixel art, costruito con la
        posizione ASSOLUTA del tile: la frontiera segue un rumore in coordinate
        MONDO lungo il bordo -> è continua e mossa attraverso tutti i tile (mai
        dritta), diversa ovunque. La transizione è a GRADINI con dithering di
        Bayer (solido vicino all'erba, stipple verso la terra), più ciuffi d'erba
        che invadono la terra. kind='fringe' (erba che invade la lane) /
        'path' (terra battuta che invade l'erba)."""
        ts = self.tile_size
        s = pygame.Surface((ts, ts), pygame.SRCALPHA)
        base = PATH_EDGE if kind == "path" else GRASS_FRINGE
        A = 200
        maxd = max(3, int(ts * (0.85 if kind == "fringe" else 0.62)))

        def pt(along, into):
            if side == "N":
                return (along, into)
            if side == "S":
                return (along, ts - 1 - into)
            if side == "W":
                return (into, along)
            return (ts - 1 - into, along)           # E

        horiz = side in ("N", "S")
        rng = random.Random(((tx * 73856093) ^ (ty * 19349663)) & 0xFFFFFFFF)
        for along in range(ts):
            wc = (tx * ts + along) if horiz else (ty * ts + along)
            n = (self._vnoise(wc / 17.0, 7.3) * 0.68
                 + self._vnoise(wc / 5.5, 3.1) * 0.32)
            da = max(2, int(maxd * (0.3 + 0.62 * n)))
            for into in range(da):
                x, y = pt(along, into)
                cov = 1.0 - into / da                # 1 al bordo erba .. 0 frontiera
                cov = round(cov * 2) / 2.0           # 2-3 livelli a gradini
                wx, wy = tx * ts + x, ty * ts + y
                if _BAYER[wy % 4][wx % 4] < cov:
                    s.set_at((x, y), (base[0], base[1], base[2], A))
            if kind == "fringe" and rng.random() < 0.6:
                blade = rng.randint(2, 6)
                c = GRASS_TUFT_LIGHT if rng.random() < 0.5 else GRASS_FRINGE
                for into in range(da, min(maxd, da + blade)):
                    if rng.random() < 0.7:
                        x, y = pt(along, into)
                        s.set_at((x, y), (c[0], c[1], c[2], 170))
        return s

    def _shore_overlay(self, side: str, kind: str, variant: int = 0) -> pygame.Surface:
        """Striscia-riva sfumata perpendicolare al bordo `side` del tile.

        kind='water': schiuma al contatto -> bassofondo chiaro -> trasparente.
        kind='land' : terra bagnata scura al contatto -> sabbia -> trasparente.
        kind='path'/'fringe': bordo lane<->erba IRREGOLARE (frontiera ondulata +
          erba a ciuffi che invade la terra), diverso per `variant`.
        """
        ts = self.tile_size
        key = (ts, "shore", side, kind, variant)
        s = self._tile_cache.get(key)
        if s is not None:
            return s
        s = pygame.Surface((ts, ts), pygame.SRCALPHA)

        def pt(along, into):                   # coord dal bordo `side`
            if side == "N":
                return (along, into)
            if side == "S":
                return (along, ts - 1 - into)
            if side == "W":
                return (into, along)
            return (ts - 1 - into, along)       # E

        if kind in ("path", "fringe"):
            # Bordo lane<->erba irregolare: per ogni colonna una profondità
            # ondulata (seno + rumore) -> frontiera mossa, non una riga retta;
            # dentro, terra/erba che sfuma; oltre, ciuffi d'erba che si diradano.
            base = PATH_EDGE if kind == "path" else GRASS_FRINGE
            amax = 150 if kind == "path" else 180
            maxd = max(6, int(ts * (0.82 if kind == "fringe" else 0.6)))
            rng = random.Random((hash((side, kind, variant)) & 0xFFFFFFFF))
            ph = rng.uniform(0.0, math.tau); ph2 = rng.uniform(0.0, math.tau)
            for along in range(ts):
                # Frontiera molto ondulata (due seni a frequenze diverse + rumore).
                w = (0.42 + 0.30 * math.sin(along * 0.5 + ph)
                     + 0.16 * math.sin(along * 1.3 + ph2) + rng.random() * 0.22)
                da = max(1, int(maxd * max(0.1, min(1.0, w))))
                for into in range(da):
                    a = int(amax * (1 - into / da) ** 1.3)
                    if a <= 0:
                        continue
                    s.set_at(pt(along, into), (base[0], base[1], base[2], a))
                if kind == "fringe":
                    # Ciuffi d'erba che sconfinano oltre la frontiera (si diradano).
                    if rng.random() < 0.65:
                        blade = rng.randint(2, 6)
                        c = GRASS_TUFT_LIGHT if rng.random() < 0.5 else GRASS_FRINGE
                        for into in range(da, min(maxd, da + blade)):
                            fade = 1 - (into - da) / max(1, blade)
                            s.set_at(pt(along, into), (c[0], c[1], c[2], int(170 * fade)))
                else:
                    if rng.random() < 0.3:      # granello di terra sull'erba
                        s.set_at(pt(along, da + rng.randint(0, 2)), (base[0], base[1], base[2], 120))
            self._tile_cache[key] = s
            return s

        # kind water/land: fascia sfumata dritta (il contatto con l'acqua resta
        # morbido ma regolare).
        deep = True
        depth = max(5, int(ts * 0.55))
        for i in range(depth):
            f = i / depth
            if kind == "water":
                if i == 0:
                    col = (*WATER_FOAM, 170)
                elif i <= 1:
                    col = (*WATER_SHALLOW, 150)
                else:
                    col = (*WATER_SHALLOW, int(140 * (1 - f) ** 1.3))
            else:  # land
                if i <= 1:
                    col = (*SHORE_WET, int(185 * (1 - f)))
                else:
                    col = (*SHORE_SAND, int(165 * (1 - f) ** 1.25))
            if side == "N":
                pygame.draw.line(s, col, (0, i), (ts, i))
            elif side == "S":
                pygame.draw.line(s, col, (0, ts - 1 - i), (ts, ts - 1 - i))
            elif side == "W":
                pygame.draw.line(s, col, (i, 0), (i, ts))
            else:  # E
                pygame.draw.line(s, col, (ts - 1 - i, 0), (ts - 1 - i, ts))
        self._tile_cache[key] = s
        return s

    def _draw_dens(self, surface, camera, dens):
        ts = self.tile_size
        for name, (dx, dy) in dens.items():
            sx, sy = camera.world_to_screen(dx * ts, dy * ts)
            col = DEN_COLORS.get(name, (220, 220, 220))
            pygame.draw.circle(surface, col, (sx, sy), ts, 2)
            pygame.draw.circle(surface, col, (sx, sy), 3)

    # --- gittata delle torri nemiche -----------------------------------------
    def draw_tower_ranges(self, surface, camera, world, player_team, now=0.0,
                          player_pos=None, near=None):
        """Cerchio di pericolo attorno alle torri NEMICHE vive (stile LoL): mostra
        fin dove la torre spara, cosi sai dove fermarti. Con `near` appare solo
        quando il giocatore (player_pos) si avvicina a meno di `near` tile oltre il
        bordo della gittata, per non intasare lo schermo.

        Decalco a terra translucido (rosso pericolo) + anello pulsante: cosmetico,
        disegnato sopra la mappa. `near` None = sempre visibile.
        """
        ts = self.tile_size
        W, H = surface.get_size()
        overlay = None
        pulse = 0.5 + 0.5 * math.sin(now * 3.0)
        edge_a = int(70 + 60 * pulse)
        danger = (230, 70, 60)
        for s in world.structures():
            if (getattr(s, "kind", None) != "tower" or not getattr(s, "alive", False)
                    or s.team == player_team):
                continue
            # In rete le strutture non portano attack_range: usa il default della torre.
            rng = s.attack_range or _TOWER_RANGE_DEFAULT
            cx, cy = camera.world_to_screen(s.pos.x * ts, s.pos.y * ts)
            r = int(rng * ts)
            if cx + r < 0 or cx - r > W or cy + r < 0 or cy - r > H:
                continue   # fuori schermo
            if near is not None and player_pos is not None:
                # mostra solo se il giocatore e' vicino al bordo della gittata
                if player_pos.dist(s.pos) - rng > near:
                    continue
            if overlay is None:
                overlay = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.circle(overlay, (*danger, 26), (cx, cy), r)
            pygame.draw.circle(overlay, (*danger, edge_a), (cx, cy), r, 2)
            # breve tratteggio interno per leggibilita' del bordo
            pygame.draw.circle(overlay, (255, 180, 160, edge_a // 2), (cx, cy),
                               max(1, r - 3), 1)
        if overlay is not None:
            surface.blit(overlay, (0, 0))

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
                                      "sub", "blink", "storm", "leap", "rain",
                                      "rockwave", "spikes", "avalanche",
                                      "spiritbeam", "painsplit", "spiritcall",
                                      "swift", "wish", "thunder", "blizzard", "futuresight",
                                      "defog", "tailwind", "nightshade", "clearsmog",
                                      "armorcannon", "psychic", "grudgeblade"):
            pygame.draw.circle(surface, (90, 90, 90), S(ox, oy), int(rng * ts), 1)

        shape = move.shape
        if shape == "rockwave":   # Rocciotomba: corsia dell'onda + pilastro in fondo
            ex, ey = ox + nx * rng, oy + ny * rng
            pygame.draw.line(surface, col, S(ox, oy), S(ex, ey), max(2, int(move.radius * ts)))
            pygame.draw.rect(surface, (255, 255, 255),
                             pygame.Rect(S(ex, ey)[0] - ts // 2, S(ex, ey)[1] - ts // 2, ts, ts), 1)
            return
        if shape == "rockcharge":   # Pesobomba: carica a distanza fissa
            ex, ey = ox + nx * rng, oy + ny * rng
            pygame.draw.line(surface, col, S(ox, oy), S(ex, ey), max(3, int(move.radius * ts)))
            pygame.draw.circle(surface, col, S(ex, ey), int(move.radius * ts), 1)
            return
        if shape == "avalanche":   # Frana: punto di comparsa + percorso verso di sé
            d = max(float(move.effects.get("min_range", 4.0)), min(dist, rng))
            cx, cy = ox + nx * d, oy + ny * d
            pygame.draw.line(surface, col, S(cx, cy), S(ox, oy), 2)
            pygame.draw.circle(surface, (255, 255, 255), S(cx, cy), int(move.radius * ts), 2)
            return
        if shape == "spiritbeam":   # Stordiraggio: linea + tratto oltre il bersaglio
            ex, ey = ox + nx * rng, oy + ny * rng
            pygame.draw.line(surface, col, S(ox, oy), S(ex, ey), max(2, int(move.radius * ts)))
            pygame.draw.circle(surface, col, S(ex, ey), int(move.radius * ts), 1)
            return
        if shape == "painsplit":    # Malcomune: chi verrebbe legato e' quello vicino al mouse
            d = min(dist, rng)
            pygame.draw.circle(surface, col, S(ox + nx * d, oy + ny * d), max(4, int(0.6 * ts)), 1)
            return
        if shape == "spiritcall":   # Richiamo: gli spiriti raggiungibili li evidenzia la scena
            return
        if shape == "wish":         # Desiderio: l'alleato vicino al mouse (o Eevee)
            d = min(dist, rng)
            pygame.draw.circle(surface, (255, 226, 92), S(ox + nx * d, oy + ny * d),
                               max(4, int(0.7 * ts)), 1)
            return
        if shape == "swift":        # Comete: inseguono da sole il nemico più vicino
            return
        if shape == "tailwind":     # Ventoincoda: corsia del vento
            ex, ey = ox + nx * rng, oy + ny * rng
            r = max(2, int(move.radius * ts))
            for s in (1, -1):
                pygame.draw.line(surface, col, S(ox - ny * move.radius * s, oy + nx * move.radius * s),
                                 S(ex - ny * move.radius * s, ey + nx * move.radius * s), 1)
            pygame.draw.line(surface, (230, 245, 255), S(ox, oy), S(ex, ey), 1)
            return
        if shape == "taxi":         # Taxi Volante: alleato preso (3 tile) + atterraggio
            reach = float(move.effects.get("ally_range", 3.0))
            pygame.draw.circle(surface, (214, 240, 255), S(ox, oy), int(reach * ts), 1)
            d = min(dist, rng)
            cx, cy = S(ox + nx * d, oy + ny * d)
            pygame.draw.line(surface, (120, 170, 210), S(ox, oy), (cx, cy), 1)
            pygame.draw.circle(surface, col, (cx, cy), int(move.radius * ts), 2)
            return
        if shape in ("nightshade", "grudgeblade"):   # bersaglio: il nemico vicino al mirino
            d = min(dist, rng)
            cx, cy = S(ox + nx * d, oy + ny * d)
            pygame.draw.line(surface, col, S(ox, oy), (cx, cy), 1)
            pygame.draw.circle(surface, col, (cx, cy), int(2.0 * ts), 1)
            pygame.draw.circle(surface, (255, 255, 255), (cx, cy), max(3, int(0.3 * ts)), 1)
            return
        if shape in ("smackdown", "explosion", "spikes", "legion", "memento",
                     "thunder", "blizzard", "futuresight", "gleam", "defog",
                     "clearsmog", "psychic"):
            shape = "area"
        elif shape in ("sandboost", "endure", "moonlight", "acidarmor", "roost",
                       "floatarmor", "shadowclaw"):
            shape = "buff"
        elif shape == "armorcannon":
            shape = "projectile"
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
            if not (x0 - 4 <= s.pos.x <= x1 + 4 and y0 - 4 <= s.pos.y <= y1 + 6):
                continue
            if isinstance(s, Core):
                # La base e' una piattaforma PIATTA: si disegna prima di tutto,
                # cosi' chi ci sta sopra (respawn, negozio) resta visibile.
                gx, gy = camera.world_to_screen(s.pos.x * ts, s.pos.y * ts)
                structure_gfx.draw_base(surface, s, gx, gy, now, ts)
                if s.alive and config.SHOW_HP_BARS and s.hp < s.max_hp:
                    r = structure_gfx.base_radius_px(ts)
                    self._hp_bar(surface, gx, gy - r - 6, s.hp / s.max_hp,
                                 config.TEAM_COLORS.get(s.team, (200, 200, 200)), width=r)
            else:
                drawables.append(s)   # torri (anche distrutte: macerie)
        for u in world.alive_units():
            if not (x0 - 2 <= u.pos.x <= x1 + 2 and y0 - 2 <= u.pos.y <= y1 + 2):
                continue
            # Nebbia di guerra: non disegnare le unità nemiche non visibili.
            if (vision is not None and u.team != player_team
                    and not vision.is_enemy_visible(player_team, u.id)):
                continue
            drawables.append(u)
        # Pilastri di roccia temporanei (Rocciotomba): ordinati in profondità con
        # le unità, così chi passa dietro viene coperto e chi sta davanti no.
        for pl in getattr(world, "pillars", ()):
            if x0 - 2 <= pl.pos.x <= x1 + 2 and y0 - 2 <= pl.pos.y <= y1 + 2:
                drawables.append(pl)

        for e in sorted(drawables, key=lambda it: it.pos.y):
            gx, gy = camera.world_to_screen(e.pos.x * ts, e.pos.y * ts)
            if isinstance(e, Pillar):
                self._draw_pillar(surface, e, gx, gy, now)
            elif isinstance(e, Structure):
                self._draw_structure(surface, e, gx, gy, now)
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
                # Sollevamento in aria (Ribaltiro/Rimbalzo): ombra a terra + sprite
                # alzato, così il salto/lancio è visibile (non un teletrasporto).
                lift = int(getattr(e, "air_z", 0.0) * ts)
                if lift > 0:
                    self._draw_air_shadow(surface, e, gx, gy)
                    gy -= lift
                # Acidarmatura (Vaporeon): al posto dello sprite, una pozza.
                if isinstance(e, Pokemon) and e.puddle_until > now:
                    eevee_fx.draw_puddle(surface, e, gx, gy, now, ts)
                    self._draw_unit_hp(surface, e, gx, gy)
                    continue
                anim = animators.get(e.id)
                # Memento (Spiritomb): invisibile ai nemici; la sua squadra lo
                # vede come un'ombra traslucida.
                ghost = isinstance(e, Pokemon) and getattr(e, "invisible", False)
                if anim is not None:
                    if ghost:
                        anim.draw(surface, gx, gy, alpha=95)
                    else:
                        anim.draw(surface, gx, gy)
                if isinstance(e, Pokemon) and getattr(e, "spirit_awaken", 0) > 0:
                    spirit_fx.draw_aura(surface, camera, e, now, 110 if ghost else 255)
                if isinstance(e, Pokemon):   # ghiaccio, cuori, sabbia, Resistenza
                    eevee_fx.draw_unit_overlay(surface, e, gx, gy, now, ts)
                    corvi_fx.draw_unit_overlay(surface, e, gx, gy, now, ts)   # provocato, Trespolo
                    charcadet_fx.draw_unit_overlay(surface, e, gx, gy, now, ts)   # spallacci, artigli
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

    def _draw_air_shadow(self, surface, u, gx, gy):
        """Ombra ellittica a terra sotto un'unità sollevata in aria (più piccola
        e tenue man mano che sale)."""
        ts = self.tile_size
        r = max(3, int(u.radius * ts))
        z = getattr(u, "air_z", 0.0)
        scale = max(0.4, 1.0 - 0.18 * z)   # l'ombra si restringe con l'altezza
        w = int(r * 2 * scale)
        h = max(2, int(r * scale))
        sh = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 90), sh.get_rect())
        surface.blit(sh, (gx - w // 2, gy - h // 2))

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

    def _pillar_sprite(self, explosive: bool) -> pygame.Surface:
        """Pilastro di roccia pixel-art (cache): colonna irregolare un po'
        rastremata, faccia SINISTRA in luce e DESTRA in ombra (luce da
        alto-sinistra), cima più chiara, strati e crepe, sassi ai piedi.
        Pietrataglio (explosive): crepe incandescenti."""
        ts = self.tile_size
        key = (ts, "pillar", explosive)
        spr = self._tile_cache.get(key)
        if spr is not None:
            return spr
        W, H = int(ts * 1.0), int(ts * 1.75)
        spr = pygame.Surface((W, H), pygame.SRCALPHA)
        rng = random.Random(7 if explosive else 3)
        base = H - 3
        ridge = int(W * 0.46)
        top = [(int(W * 0.14), 7), (int(W * 0.3), 3), (int(W * 0.52), 1),
               (int(W * 0.72), 4), (int(W * 0.86), 8)]
        body = [(1, base), *top, (W - 2, base)]
        # Toni un filo più cupi delle schegge FX: il pilastro resta a lungo in
        # scena e deve stare nella palette scura della giungla (ma staccarsi).
        hi, mid, sh = (160, 146, 118), (114, 101, 83), (72, 63, 53)
        # facce: sinistra chiara, destra scura (diviso dallo spigolo centrale)
        pygame.draw.polygon(spr, mid, body)
        pygame.draw.polygon(spr, sh, [(ridge, 2), *top[3:], (W - 2, base), (ridge + 2, base)])
        pygame.draw.polygon(spr, hi, [(2, base - 2), *top[:2], (ridge - 1, 3),
                                      (ridge - 3, base - 4)])
        # cima: faccetta superiore illuminata
        pygame.draw.polygon(spr, (192, 178, 146), [top[0], top[1], top[2], (ridge, 7),
                                                   (int(W * 0.24), 9)])
        # strati orizzontali + crepe (spezzate, oblique)
        for yy in (int(H * 0.42), int(H * 0.68)):
            pygame.draw.line(spr, ROCK_OUT, (3, yy), (ridge - 2, yy + 1), 1)
            pygame.draw.line(spr, (64, 56, 46), (ridge + 1, yy + 1), (W - 4, yy - 1), 1)
        crack_col = EMBER if explosive else ROCK_OUT
        for _ in range(3 if explosive else 2):
            x = rng.randint(4, W - 5)
            y = rng.randint(10, base - 8)
            pts = [(x, y)]
            for _k in range(3):
                x += rng.choice((-1, 0, 1))
                y += rng.randint(2, 4)
                pts.append((x, min(base - 2, y)))
            pygame.draw.lines(spr, crack_col, False, pts, 1)
        pygame.draw.polygon(spr, ROCK_OUT, body, 1)
        # sassi ai piedi
        for sx, sr in ((3, 3), (W - 5, 3), (W // 2 + 3, 2)):
            pygame.draw.circle(spr, ROCK_OUT, (sx, base + 1), sr + 1)
            pygame.draw.circle(spr, ROCK_MID, (sx, base + 1), sr)
            pygame.draw.circle(spr, ROCK_HI, (sx - 1, base), max(1, sr - 2))
        self._tile_cache[key] = spr
        return spr

    def _draw_pillar(self, surface, pl, gx, gy, now):
        """Pilastro: spunta dal terreno (0.18s), resta, poi trema e si abbassa
        sbriciolandosi negli ultimi 0.35s. Ombra di contatto a basso-destra."""
        ts = self.tile_size
        spr = self._pillar_sprite(pl.explode is not None)
        W, H = spr.get_size()
        k = min(1.0, max(0.0, (now - pl.born) / 0.18))
        left = pl.until - now
        shake = 0
        if left < 0.35:
            k = min(k, max(0.0, left / 0.35))
            shake = random.choice((-1, 0, 1))
        foot = gy + int(ts * 0.42)
        sh = pygame.Surface((W + 6, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 95), sh.get_rect())
        surface.blit(sh, (gx - W // 2 + 2, foot - 4))
        vis = int(H * k)
        if vis <= 0:
            return
        surface.blit(spr, (gx - W // 2 + shake, foot - vis), pygame.Rect(0, 0, W, vis))
        if pl.explode is not None and k >= 1.0:   # Pietrataglio: le crepe pulsano
            glow = pygame.Surface((W, H), pygame.SRCALPHA)
            a = int(40 + 40 * (0.5 + 0.5 * math.sin(now * 8.0)))
            pygame.draw.ellipse(glow, (*EMBER, a), pygame.Rect(3, H // 4, W - 6, H // 2))
            surface.blit(glow, (gx - W // 2 + shake, foot - H))

    def _draw_structure(self, surface, s, gx, gy, now):
        """Torre 2.5D di pietra con la gemma di squadra (game/structure_gfx.py)."""
        ts = self.tile_size
        structure_gfx.draw_tower(surface, s, gx, gy, now, ts)
        if s.alive and config.SHOW_HP_BARS and s.hp < s.max_hp:
            col = config.TEAM_COLORS.get(s.team, (200, 200, 200))
            self._hp_bar(surface, gx, structure_gfx.tower_top_y(ts, gy),
                         s.hp / s.max_hp, col, width=int(1.6 * ts))

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
        if getattr(u, "airborne_until", -1) > now:
            pips.append((236, 214, 164))   # lanciato in aria (sabbia chiara)
        if getattr(u, "dashlock_until", -1) > now:
            pips.append((150, 120, 84))    # niente scatti (Abbattimento/Cucitombra: bruno)
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
        if isinstance(u, Pokemon) and noivern_fx.has_echo(u):   # cariche del ping
            noivern_fx.draw_echo_pips(surface, u, gx, top, w)

    def _hp_bar(self, surface, cx, top_y, frac, team_col, width):
        h = 3
        x = cx - width // 2
        pygame.draw.rect(surface, COL_HP_BG, pygame.Rect(x - 1, top_y - 1, width + 2, h + 2))
        pygame.draw.rect(surface, team_col, pygame.Rect(x, top_y, int(width * frac), h))
