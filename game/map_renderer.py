"""Rendering della mappa STATICA in layer separati, pre-renderizzati una volta.

Tutta la parte di mappa che non cambia (terreno, decori, ombre, muri/vegetazione)
viene disegnata una sola volta in `build()`. A ogni frame `draw()` fa solo pochi
blit della porzione inquadrata: niente piu loop per-tile a ogni frame.

Memoria: ogni layer e diviso in CHUNK quadrati (es. 1024x1024). Un chunk viene
allocato SOLO se qualcosa ci viene disegnato dentro; nel draw si blittano solo i
chunk che cadono nell'inquadratura. Cosi i layer per lo piu vuoti (ombre, muri,
e i riservati canopy/lighting) non occupano RAM dove non c'e niente. Il layer
`ground` e opaco (niente SRCALPHA: copre tutto, non serve il canale alfa).

Ordine dei layer (dal basso):
  1 ground            - terreno piatto (erba / lane / acqua)  [opaco]
  2 ground_decor      - rive, bordi lane/erba, griglia di debug
  3 shadows           - AO + ombre proiettate dai muri sul terreno
  4 walls_base        - rilievi 2.5D (muri, altopiani, cespugli)
  [unita e oggetti dinamici: disegnati dal Renderer, TRA walls_base e canopy]
  5 canopy            - chiome/parti SOPRA le unita (riservato: resta vuoto)
  6 lighting_overlay  - velo di luce/atmosfera globale (riservato: resta vuoto)

Le prime quattro si disegnano sotto le unita (`draw`), le ultime due sopra
(`draw_canopy`). La generazione dei singoli sprite dei tile resta nel Renderer
(`painter`): qui li si compone soltanto nei layer, cosi la grafica e identica.
"""
from __future__ import annotations

import math
import random
from collections import deque

import numpy as np
import pygame
import pygame.surfarray

import config
from engine.grid import (TILE_BUSH, TILE_FLOOR, TILE_JUNGLE_WALL, TILE_LANE,
                         TILE_WALL)

COL_GRID = (0, 0, 0)
COL_BG = (18, 20, 24)            # sfondo (riempie il bordo del layer opaco)
CHUNK = 1024                     # lato del chunk in pixel

# --- Atmosfera (layer shadows e lighting_overlay) ------------------------------
# Ambient occlusion: ombra di contatto morbida vicino a muri/cespugli.
AO_COL = (15, 30, 26)            # #0F1E1A tono d'ombra
AO_MAXA = 110                    # alfa massima (a ridosso dell'ostacolo)
AO_RADIUS_TILES = 1.5            # raggio del gradiente
# Chioma: velo d'ombra sulla giungla (non sulle lane), con chiazze a bassa
# frequenza come luce filtrata dagli alberi.
CANOPY_DARK = (12, 22, 19)       # verde-nero freddo
CANOPY_BASE = 20                 # velo uniforme sulla giungla (giungla < lane)
CANOPY_AMP = 64                  # extra nelle chiazze di chioma densa
# Campi dei mostri: poche macchie di luce calda e tenue (radura illuminata).
CAMP_WARM = (220, 146, 92)       # luce calda, arancio chiaro (meno giallo-verde)
CAMP_WARM_A = 98                 # alfa al centro della macchia
CAMP_R_TILES = 3.0               # raggio della macchia di luce
# Quanto il velo di chioma e la luce calda SI RIDUCONO sulla cima dei muri:
# i muri devono restare ben piu chiari del terreno (leggibilita del calpestabile).
WALL_CANOPY_KEEP = 0.30          # la chioma sui muri resta al 30%
WALL_WARM_KEEP = 0.35            # la luce calda sui muri resta al 35%
# Vignettatura: leggero scurimento ai bordi dello SCHERMO (screen-space).
VIGNETTE_COL = (8, 14, 14)
VIGNETTE_A = 92

# Matrice di Bayer 4x4 (ordered dithering) in [0,1): soglia per-pixel con cui si
# "sgranano" i confini tra i livelli di colore -> transizioni a gradini in stile
# pixel art invece di sfumature morbide.
_BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                   [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) / 16.0


def _np_hash01(xi, yi):
    """Hash deterministico vettoriale (uguale a Renderer._h01) -> [0,1]."""
    h = (xi * 374761393 + yi * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFF).astype(np.float32) / 65535.0


def _np_vnoise(X, Y):
    """Value-noise bilineare vettoriale (uguale a Renderer._vnoise)."""
    x0 = np.floor(X).astype(np.int64); y0 = np.floor(Y).astype(np.int64)
    fx = (X - x0).astype(np.float32); fy = (Y - y0).astype(np.float32)
    sx = fx * fx * (3 - 2 * fx); sy = fy * fy * (3 - 2 * fy)
    a = _np_hash01(x0, y0); b = _np_hash01(x0 + 1, y0)
    c = _np_hash01(x0, y0 + 1); d = _np_hash01(x0 + 1, y0 + 1)
    top = a + (b - a) * sx; bot = c + (d - c) * sx
    return top + (bot - top) * sy


def _np_tone(TX, TY):      # verde a due scale (= Renderer._two_octave)
    return 0.62 * _np_vnoise(TX / 4.0, TY / 4.0) + 0.38 * _np_vnoise((TX + 40) / 9.0, (TY + 40) / 9.0)


def _np_moss(TX, TY):      # (= Renderer._moss_at)
    n = _np_vnoise((TX + 123) / 6.5, (TY + 77) / 6.5) * 0.74 + _np_vnoise((TX + 123) / 2.4, (TY + 77) / 2.4) * 0.26
    return np.clip((n - 0.55) / 0.22, 0.0, 1.0)


def _np_mud(TX, TY):       # (= Renderer._mud_at)
    n = _np_vnoise((TX + 311) / 7.5, (TY + 517) / 7.5) * 0.72 + _np_vnoise((TX + 311) / 2.7, (TY + 517) / 2.7) * 0.28
    return np.clip((n - 0.70) / 0.12, 0.0, 1.0)   # soglia alzata: chiazze più piccole/sparse


def _np_mudtone(TX, TY):   # variazione interna del fango (tono + pozzanghere)
    return _np_vnoise((TX + 90) / 3.2, (TY + 40) / 3.2).astype(np.float32)

# Tile "alti": resi come rilievi 2.5D estrusi verso l'alto (come nel Renderer).
TALL_TILES = (TILE_WALL, TILE_JUNGLE_WALL, TILE_BUSH)


class _Layer:
    """Un layer della mappa diviso in chunk allocati su richiesta.

    Si comporta come una Surface per quanto serve a MapRenderer: espone `blit`
    (instrada il disegno nei chunk giusti, creandoli solo se toccati). Nel draw
    blitta solo i chunk visibili.
    """

    def __init__(self, map_w: int, map_h: int, opaque: bool, bg=None):
        self.map_w = map_w
        self.map_h = map_h
        self.opaque = opaque
        self.bg = bg
        self.chunks: dict[tuple[int, int], pygame.Surface] = {}

    def _chunk_surf(self, cx: int, cy: int):
        key = (cx, cy)
        s = self.chunks.get(key)
        if s is None:
            w = min(CHUNK, self.map_w - cx * CHUNK)
            h = min(CHUNK, self.map_h - cy * CHUNK)
            if w <= 0 or h <= 0:
                return None
            if self.opaque:
                s = pygame.Surface((w, h)).convert()
                if self.bg is not None:
                    s.fill(self.bg)
            else:
                s = pygame.Surface((w, h), pygame.SRCALPHA).convert_alpha()
            self.chunks[key] = s
        return s

    def blit(self, source, dest) -> None:
        """Blitta `source` a `dest` (coord assolute di mappa), smistandolo nei
        chunk sovrapposti. Firma compatibile con Surface.blit (2 argomenti)."""
        ax, ay = int(dest[0]), int(dest[1])
        w, h = source.get_size()
        cx0, cx1 = ax // CHUNK, (ax + w - 1) // CHUNK
        cy0, cy1 = ay // CHUNK, (ay + h - 1) // CHUNK
        for cy in range(cy0, cy1 + 1):
            if cy < 0 or cy * CHUNK >= self.map_h:
                continue
            for cx in range(cx0, cx1 + 1):
                if cx < 0 or cx * CHUNK >= self.map_w:
                    continue
                s = self._chunk_surf(cx, cy)
                if s is not None:
                    s.blit(source, (ax - cx * CHUNK, ay - cy * CHUNK))

    def draw(self, screen, ox: int, oy: int, view_w: int, view_h: int) -> None:
        """Blitta i chunk visibili. Il pixel-layer (lx,ly) va a schermo in
        (lx+ox, ly+oy); si disegnano solo i chunk che intersecano la vista."""
        if not self.chunks:
            return
        cx0 = max(0, (-ox) // CHUNK)
        cy0 = max(0, (-oy) // CHUNK)
        cx1 = (-ox + view_w) // CHUNK
        cy1 = (-oy + view_h) // CHUNK
        chunks = self.chunks
        for cy in range(cy0, cy1 + 1):
            base_y = cy * CHUNK + oy
            for cx in range(cx0, cx1 + 1):
                s = chunks.get((cx, cy))
                if s is not None:
                    screen.blit(s, (cx * CHUNK + ox, base_y))

    def mem_bytes(self) -> int:
        return sum(s.get_bytesize() * s.get_width() * s.get_height()
                   for s in self.chunks.values())


class MapRenderer:
    LAYER_NAMES = ("ground", "ground_decor", "shadows", "walls_base",
                   "canopy", "lighting_overlay")
    BELOW = ("ground", "ground_decor", "shadows", "walls_base")   # sotto le unita
    ABOVE = ("canopy", "lighting_overlay")                        # sopra le unita

    def __init__(self, painter, tile_size: int = config.TILE_SIZE):
        # `painter` e il Renderer: fornisce i builder/cache degli sprite dei tile.
        self.painter = painter
        self.tile_size = tile_size
        self.layers: dict[str, _Layer] = {}
        self._grid = None            # griglia per cui i layer sono stati costruiti
        self._top = 0                # margine superiore (i rilievi sporgono di H)
        self._H = 0
        self._grid_sprite = None     # sprite riga griglia di debug (cache)
        self._camps: list[tuple[int, int]] = []   # centri dei campi (per i sentieri)
        self._vig = None             # vignettatura screen-space (cache per dimensione vista)

    def set_camps(self, camps) -> None:
        """Posizioni dei campi della giungla (da MapData): servono SOLO a tracciare
        i sentieri di terra verso le lane. Cosmetico, non tocca la logica. Se
        cambiano, i layer si ricostruiscono al prossimo draw."""
        norm = [tuple(c["pos"]) if isinstance(c, dict) else tuple(c[:2]) for c in (camps or [])]
        if norm != self._camps:
            self._camps = norm
            self.layers = {}         # forza ensure_built a ricostruire

    # --- costruzione (una volta) --------------------------------------------
    def ensure_built(self, grid) -> None:
        """Costruisce i layer se mancano o se la griglia e cambiata."""
        if self._grid is not grid or not self.layers:
            self.build(grid)

    def build(self, grid) -> None:
        ts = self.tile_size
        H = max(6, int(ts * 0.5))        # altezza di estrusione dei rilievi
        top = H                          # margine in alto per i rilievi di riga 0
        self._H = H
        self._top = top
        Wt, Ht = grid.width, grid.height
        map_w = Wt * ts
        map_h = Ht * ts + top
        # ground opaco; gli altri con alfa. canopy/lighting restano vuoti (nessun
        # chunk allocato) finche qualcuno non ci disegna dentro.
        self.layers = {
            "ground": _Layer(map_w, map_h, opaque=True, bg=COL_BG),
            "ground_decor": _Layer(map_w, map_h, opaque=False),
            "shadows": _Layer(map_w, map_h, opaque=False),
            "walls_base": _Layer(map_w, map_h, opaque=False),
            "canopy": _Layer(map_w, map_h, opaque=False),
            "lighting_overlay": _Layer(map_w, map_h, opaque=False),
        }
        ground = self.layers["ground"]
        decor = self.layers["ground_decor"]
        shadows = self.layers["shadows"]
        walls = self.layers["walls_base"]
        p = self.painter
        tiles = grid.tiles

        # --- Sentieri: calcolati PRIMA del suolo, così i fili d'erba non si
        #     disegnano sul tracciato (set dei tile coperti dai sentieri).
        routes, path_tiles = self._compute_paths(grid)

        # --- Passata 1a: suolo di giungla ORGANICO, calcolato per pixel in
        #     coordinate mondo (maschera a bassa risoluzione + smoothscale):
        #     un'unica immagine continua, senza cuciture di tile. I dettagli
        #     (ciuffi d'erba, fiocchi di muschio, granelli di fango) si disegnano
        #     sopra, saltando i tile dei sentieri.
        inner = self._inner_mask(grid)   # dentro l'anello delle lane (no fango fuori)
        floor_img = self._build_floor(grid, p, inner)
        self._scatter_detail(grid, floor_img, p, path_tiles, inner)
        ground.blit(floor_img, (0, top))

        # --- Passata 1b: tile speciali (lane/acqua) sopra il suolo + rive/bordi/
        #     griglia sul decor. I tile "alti" (muri/cespugli) lasciano il suolo
        #     sotto e si disegnano dopo in walls_base.
        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                ax = tx * ts
                ay = ty * ts + top
                t = row[tx]
                h = (tx * 73856093) ^ (ty * 19349663)
                g = TILE_FLOOR if t in TALL_TILES else t
                if g != TILE_FLOOR:
                    variant = (h >> 4) & 3
                    ground.blit(p._tile_surf(g, variant), (ax, ay))
                p._shore(decor, grid, tx, ty, ax, ay, g, t)
                if config.SHOW_GRID_LINES:
                    decor.blit(self._grid_line_sprite(), (ax, ay))

        # --- Sentieri di terra battuta: strisce continue (spline) camp->lane --
        self._stroke_paths(decor, grid, routes, p)

        # --- SAGOMA DEI MURI DI GIUNGLA: maschera binaria a risoluzione tile ->
        #     blur gaussiano + soglia 0.5 + rumore -> silhouette morbida con
        #     diagonali vere e angoli tondi (niente scaletta per-tile). La
        #     collisione resta sulla griglia: la grafica puo sporgere/rientrare
        #     al massimo ~mezzo tile (clamp in _jungle_solid). Ombre e AO si
        #     ricalcolano da QUESTA maschera, non dai tile.
        solid = self._jungle_solid(grid)

        # --- Passata ombre proiettate -----------------------------------------
        # (a) muro di confine in PIETRA (TILE_WALL): ombra per-tile come prima.
        def is_stone(x, y):
            return 0 <= x < Wt and 0 <= y < Ht and tiles[y][x] == TILE_WALL

        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                if row[tx] in TALL_TILES:
                    continue
                nw = ((1 if is_stone(tx, ty - 1) else 0)
                      | (2 if is_stone(tx - 1, ty) else 0))
                if nw:
                    shadows.blit(p._shadow_surf(nw), (tx * ts, ty * ts + top))

        # (b) muri di giungla: ombra proiettata a sud-est dalla SILHOUETTE.
        if solid is not None:
            self._build_jungle_shadow(grid, shadows, solid)

        # --- Ambient occlusion: gradiente morbido attorno ai tile "alti"
        #     (silhouette dei muri di giungla + cespugli + pietra).
        self._build_ao(grid, shadows, solid)

        # --- Muri di giungla: riempimento della silhouette (texture di roccia +
        #     massi sul contorno + parete 2.5D), PRIMA dei cespugli/pietra.
        if solid is not None:
            self._build_jungle_walls(grid, walls, p, solid)

        # --- Passata 2: rilievi 2.5D per-tile (cespugli e muro di pietra) ------
        def is_bush(x, y):
            return 0 <= x < Wt and 0 <= y < Ht and tiles[y][x] == TILE_BUSH

        def sym_seed(x, y, bits):
            px, py = Wt - 1 - x, Ht - 1 - y
            kx, ky = (x, y) if (x, y) <= (px, py) else (px, py)
            return (((kx * 73856093) ^ (ky * 19349663)) >> 4) & bits

        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                t = row[tx]
                if t not in TALL_TILES or t == TILE_JUNGLE_WALL:
                    continue
                ax = tx * ts
                ay = ty * ts - H + top
                if t == TILE_BUSH:
                    mask = ((1 if is_bush(tx, ty - 1) else 0)
                            | (2 if is_bush(tx + 1, ty) else 0)
                            | (4 if is_bush(tx, ty + 1) else 0)
                            | (8 if is_bush(tx - 1, ty) else 0))
                    variant = sym_seed(tx, ty, 15)
                    walls.blit(p._bush_surf(mask, variant, H), (ax, ay))
                else:
                    variant = (((tx * 73856093) ^ (ty * 19349663)) >> 6) & 7
                    walls.blit(p._tall_surf(t, variant, H), (ax, ay))

        # --- Velo d'atmosfera SOPRA le unita: ombre della chioma sulla giungla
        #     e macchie di luce calda vicino ai campi (lighting_overlay).
        self._build_lighting(grid, self.layers["lighting_overlay"])

        self._grid = grid

    def _inner_mask(self, grid):
        """Maschera (Ht,Wt) dei tile DENTRO l'anello delle lane. Flood-fill dal
        bordo mappa trattando le LANE come barriera: tutto ciò che si raggiunge
        da fuori è la zona ESTERNA (corridoio oltre le lane); il resto, racchiuso
        dall'anello, è l'interno. Serve a NON mettere fango fuori dalle lane."""
        Wt, Ht = grid.width, grid.height
        tiles = grid.tiles
        outer = np.zeros((Ht, Wt), bool)
        dq = deque()

        def push(x, y):
            if 0 <= x < Wt and 0 <= y < Ht and not outer[y, x] and tiles[y][x] != TILE_LANE:
                outer[y, x] = True
                dq.append((x, y))

        for x in range(Wt):
            push(x, 0); push(x, Ht - 1)
        for y in range(Ht):
            push(0, y); push(Wt - 1, y)
        while dq:
            x, y = dq.popleft()
            push(x + 1, y); push(x - 1, y); push(x, y + 1); push(x, y - 1)
        return ~outer

    # --- Atmosfera: ambient occlusion + velo di luce -------------------------
    @staticmethod
    def _upscale(lo, W: int, H: int, step: int):
        """Upscale bilineare di un campo low-res `lo` (hl, wl), dove ogni cella
        copre `step` pixel, a piena risoluzione (H, W). Niente smoothscale: solo
        interpolazione numpy (prima lungo X una volta, poi lungo Y)."""
        hl, wl = lo.shape
        fx = np.minimum(np.arange(W, dtype=np.float32) / step, wl - 1.0)
        x0 = np.floor(fx).astype(np.int64); x1 = np.minimum(x0 + 1, wl - 1)
        wx = (fx - x0)[None, :]
        colx = lo[:, x0] * (1 - wx) + lo[:, x1] * wx          # (hl, W)
        fy = np.minimum(np.arange(H, dtype=np.float32) / step, hl - 1.0)
        y0 = np.floor(fy).astype(np.int64); y1 = np.minimum(y0 + 1, hl - 1)
        wy = (fy - y0)[:, None]
        return colx[y0] * (1 - wy) + colx[y1] * wy            # (H, W)

    @staticmethod
    def _blit_blocks(layer, rgb, alpha, top: int) -> None:
        """Blitta un'immagine RGBA a piena mappa (array (H,W,3) uint8 + (H,W)
        uint8) nel layer, un blocco per CHUNK: i blocchi completamente
        trasparenti NON vengono creati (resta lazy come il resto dei layer).
        `rgb` puo essere una tupla colore costante o un array (H,W,3)."""
        import pygame.surfarray as sa
        H, W = alpha.shape
        const = not isinstance(rgb, np.ndarray)
        for by in range(0, H, CHUNK):
            bh = min(CHUNK, H - by)
            for bx in range(0, W, CHUNK):
                bw = min(CHUNK, W - bx)
                ba = alpha[by:by + bh, bx:bx + bw]
                if not ba.any():
                    continue
                surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
                v3 = sa.pixels3d(surf)
                if const:
                    v3[:, :, 0] = rgb[0]; v3[:, :, 1] = rgb[1]; v3[:, :, 2] = rgb[2]
                else:
                    v3[:] = rgb[by:by + bh, bx:bx + bw].transpose(1, 0, 2)
                del v3
                va = sa.pixels_alpha(surf); va[:] = ba.T; del va
                layer.blit(surf, (bx, by + top))

    def _build_ao(self, grid, shadows, solid=None) -> None:
        """Ambient occlusion: scurisce il terreno con un gradiente morbido entro
        ~1.5 tile dai corpi "alti". L'occupazione a BASSA risoluzione viene presa
        dalla SILHOUETTE morbida dei muri di giungla (non dai tile, cosi l'AO
        segue il contorno curvo) PIU i cespugli e il muro di pietra a livello
        tile. La distanza euclidea e' calcolata con shifted-min, il falloff e'
        uno smoothstep (max a ridosso dell'ostacolo -> 0 a 1.5 tile), poi si
        upscala e si blitta."""
        ts = self.tile_size; top = self._top
        Wt, Ht = grid.width, grid.height
        W, H = Wt * ts, Ht * ts
        tiles = grid.tiles
        tall = np.zeros((Ht, Wt), bool)               # cespugli + pietra (per-tile)
        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                if row[tx] in (TILE_BUSH, TILE_WALL):
                    tall[ty, tx] = True
        step = max(2, ts // 4)
        R = AO_RADIUS_TILES * ts / step              # raggio in celle low-res
        Rc = int(math.ceil(R))
        wl = (W + step - 1) // step; hl = (H + step - 1) // step
        cx = np.minimum((np.arange(wl) * step) // ts, Wt - 1)
        cy = np.minimum((np.arange(hl) * step) // ts, Ht - 1)
        m = tall[cy][:, cx]                           # (hl, wl) bool
        if solid is not None:                         # silhouette muri di giungla
            sy = np.minimum(np.arange(hl) * step, H - 1)
            sx = np.minimum(np.arange(wl) * step, W - 1)
            m = m | solid[sy][:, sx]
        if not m.any():
            return
        big = R + 1.0
        dist = np.full((hl, wl), big, np.float32)
        dist[m] = 0.0
        for dy in range(-Rc, Rc + 1):
            for dx in range(-Rc, Rc + 1):
                e = math.hypot(dx, dy)
                if e == 0.0 or e > R:
                    continue
                dy0 = max(0, -dy); dy1 = hl - max(0, dy)
                dx0 = max(0, -dx); dx1 = wl - max(0, dx)
                if dy1 <= dy0 or dx1 <= dx0:
                    continue
                src = m[dy0 + dy:dy1 + dy, dx0 + dx:dx1 + dx]
                sub = dist[dy0:dy1, dx0:dx1]
                np.minimum(sub, np.where(src, np.float32(e), big), out=sub)
        f = np.clip(1.0 - dist / R, 0.0, 1.0)
        f = f * f * (3.0 - 2.0 * f)                   # smoothstep
        a_lo = f * AO_MAXA
        alpha = np.clip(self._upscale(a_lo, W, H, step), 0, 255).astype(np.uint8)
        self._blit_blocks(shadows, AO_COL, alpha, top)

    # --- Muri di giungla come SILHOUETTE (maschera -> blur -> soglia) ---------
    @staticmethod
    def _box1d(a, r, axis):
        """Media mobile (box blur) 1D separabile via somme cumulate (O(N))."""
        if axis == 0:
            a = a.T
        H, W = a.shape
        c = np.zeros((H, W + 1), np.float32)
        np.cumsum(a, axis=1, out=c[:, 1:])
        idx = np.arange(W)
        lo = np.clip(idx - r, 0, W); hi = np.clip(idx + r + 1, 0, W)
        out = (c[:, hi] - c[:, lo]) / (hi - lo)[None, :].astype(np.float32)
        return out.T if axis == 0 else out

    @classmethod
    def _sep_blur(cls, a, r, passes=3):
        """Blur ~gaussiano: 3 passate di box blur separabile (teorema del limite
        centrale). `r` = raggio del box in pixel."""
        a = a.astype(np.float32)
        for _ in range(passes):
            a = cls._box1d(a, r, 1)
            a = cls._box1d(a, r, 0)
        return a

    @staticmethod
    def _dist_lo(mask, Rc):
        """Distanza euclidea (troncata a Rc) da ogni cella alle celle `mask` True,
        a bassa risoluzione, con shifted-min (come _build_ao)."""
        hl, wl = mask.shape
        big = Rc + 2.0
        d = np.full((hl, wl), big, np.float32); d[mask] = 0.0
        for dy in range(-Rc, Rc + 1):
            for dx in range(-Rc, Rc + 1):
                e = math.hypot(dx, dy)
                if e == 0.0 or e > Rc:
                    continue
                dy0 = max(0, -dy); dy1 = hl - max(0, dy)
                dx0 = max(0, -dx); dx1 = wl - max(0, dx)
                if dy1 <= dy0 or dx1 <= dx0:
                    continue
                src = mask[dy0 + dy:dy1 + dy, dx0 + dx:dx1 + dx]
                sub = d[dy0:dy1, dx0:dx1]
                np.minimum(sub, np.where(src, np.float32(e), big), out=sub)
        return d

    def _jungle_solid(self, grid):
        """Silhouette (H,W) bool dei muri di giungla a risoluzione pixel.

        1) maschera binaria a risoluzione TILE; 2) blur gaussiano (raggio ~0.6
        tile, a bassa risoluzione) + soglia 0.5 -> diagonali vere e angoli tondi;
        3) deformazione del bordo con rumore (non troppo liscio), contorno pixel
        art (soglia booleana, niente antialiasing). CLAMP mezzo tile: ogni cella
        entro ~0.4 tile da un centro-muro resta piena (i muri piccoli diventano
        BLOB tondi, non rettangoli, e non spariscono) e la sagoma non sborda oltre
        ~mezzo tile dal bordo di collisione. La collisione resta sulla griglia."""
        ts = self.tile_size
        Wt, Ht = grid.width, grid.height
        W, H = Wt * ts, Ht * ts
        tiles = grid.tiles
        tm = np.zeros((Ht, Wt), bool)
        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                if row[tx] == TILE_JUNGLE_WALL:
                    tm[ty, tx] = True
        if not tm.any():
            return None
        s = max(2, ts // 4)
        hl = (H + s - 1) // s; wl = (W + s - 1) // s
        # Campo da DISCHI sui centri-muro (NON dai quadrati dei tile): l'unione
        # di dischi sovrapposti non ha spigoli di griglia, cosi niente lati dritti
        # residui (le basi dei pilastri e i bordi inferiori diventano curvi).
        ys, xs = np.where(tm)
        cmask = np.zeros((hl, wl), bool)
        ccx = np.clip(((xs + 0.5) * ts / s).astype(int), 0, wl - 1)
        ccy = np.clip(((ys + 0.5) * ts / s).astype(int), 0, hl - 1)
        cmask[ccy, ccx] = True
        dist = self._dist_lo(cmask, int(math.ceil(ts * 1.25 / s)))
        disc = (dist <= (ts * 0.72 / s)).astype(np.float32)   # dischi uniti
        core = dist <= (ts * 0.42 / s)                   # sempre pieno (blob tondi)
        allowed = dist <= (ts * 1.0 / s)                 # sporgenza max ~mezzo tile
        bf = self._sep_blur(disc, max(1, int(ts * 0.55 / s)), passes=3)
        # upscala bf a piena risoluzione (una volta), poi soglia+rumore a strisce.
        bf_full = self._upscale(bf, W, H, s)
        core_full = core[np.minimum(np.arange(H) // s, hl - 1)][:, np.minimum(np.arange(W) // s, wl - 1)]
        allow_full = allowed[np.minimum(np.arange(H) // s, hl - 1)][:, np.minimum(np.arange(W) // s, wl - 1)]
        solid = np.zeros((H, W), bool)
        TXf = (np.arange(W, dtype=np.float32) / ts)[None, :]
        STRIP = 300
        for y0 in range(0, H, STRIP):
            y1 = min(H, y0 + STRIP)
            TYf = (np.arange(y0, y1, dtype=np.float32) / ts)[:, None]
            nz = _np_vnoise(TXf / 1.5 + 11.0, TYf / 1.5 + 7.0) - 0.5     # [-0.5,0.5]
            b = bf_full[y0:y1]
            # Rumore SOLO nella fascia di bordo: l'interno (b alto) resta SEMPRE
            # pieno -> niente buchi/fessure nere dentro il muro; l'esterno (b
            # basso) resta vuoto. Il contorno e' irregolare solo al bordo.
            thr = np.where(b >= 0.80, True,
                           np.where(b <= 0.22, False, (b + nz * 0.33) > 0.5))
            solid[y0:y1] = (thr | core_full[y0:y1]) & allow_full[y0:y1]
        return solid

    def _build_jungle_shadow(self, grid, shadows, solid) -> None:
        """Ombra proiettata dai muri di giungla, ricalcolata dalla SILHOUETTE:
        la sagoma spostata verso SUD-EST (luce da alto-sinistra) e non coperta
        dalla sagoma stessa, con alfa che scema con la distanza."""
        ts = self.tile_size; top = self._top
        H, W = solid.shape
        # A BASSA risoluzione: la sagoma spostata verso SUD-EST, accumulata con
        # alfa calante, poi upscalata (l'ombra e' morbida: la grana fine non serve).
        s = max(2, ts // 3)
        hl = (H + s - 1) // s; wl = (W + s - 1) // s
        sly = np.minimum(np.arange(hl) * s, H - 1); slx = np.minimum(np.arange(wl) * s, W - 1)
        sm = solid[sly][:, slx]                           # solid low-res
        L = max(2, int(ts * 0.5 / s))
        acc = np.zeros((hl, wl), np.float32)
        for k in range(1, L + 1):
            dy = k; dx = int(round(k * 0.75))
            sh = np.zeros((hl, wl), bool)
            sh[dy:, dx:] = sm[:hl - dy, :wl - dx]
            a = 1.0 - (k - 1) / float(L + 1)
            np.maximum(acc, np.where(sh, np.float32(a), 0.0), out=acc)
        acc[sm] = 0.0                                     # niente ombra sotto il muro
        alpha = np.clip(self._upscale(acc * 95.0, W, H, s), 0, 255).astype(np.uint8)
        self._blit_blocks(shadows, (0, 0, 0), alpha, top)

    def _build_jungle_walls(self, grid, walls, p, solid) -> None:
        """Riempie la silhouette con la texture di roccia esistente, disegna i
        massi lungo il NUOVO contorno e la parete 2.5D (cliff) che segue la
        sagoma. Tutto su un'unica Surface a piena mappa, poi blit LAZY per chunk
        (solo i blocchi con contenuto)."""
        import pygame.surfarray as sa
        from game.renderer import (JW_TOP, JW_TOP_HI, JW_TOP_SH, JW_MOSS,
                                    JW_MOSS_DK, JW_CLIFF, JW_CLIFF_HI,
                                    JW_HILITE, JW_RIM, JW_EDGE_SH)
        ts = self.tile_size; top = self._top; Hh = self._H
        H, W = solid.shape
        Hf = H + Hh
        # --- Facce/bordi dalla maschera (shift a 1px) -------------------------
        up = np.zeros_like(solid); up[1:, :] = ~solid[:-1, :]; up[0, :] = True
        dn = np.zeros_like(solid); dn[:-1, :] = ~solid[1:, :]; dn[-1, :] = True
        lf = np.zeros_like(solid); lf[:, 1:] = ~solid[:, :-1]; lf[:, 0] = True
        rt = np.zeros_like(solid); rt[:, :-1] = ~solid[:, 1:]; rt[:, -1] = True
        boundary = solid & (up | dn | lf | rt)

        # --- (1) CIMA: base roccia mottled + muschio, ritagliata alla sagoma ---
        TOPc = np.array(JW_TOP, np.float32); TOPhi = np.array(JW_TOP_HI, np.float32)
        TOPsh = np.array(JW_TOP_SH, np.float32); MOSSc = np.array(JW_MOSS, np.float32)
        MOSSdk = np.array(JW_MOSS_DK, np.float32)
        top_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        v3 = sa.pixels3d(top_surf)
        # Noise calcolato a BASSA risoluzione (STEP) e interpolato bilineare a
        # strisce (come _build_floor): stessa resa, molto piu veloce del per-pixel.
        # Niente macchie scure "piene" (sembravano buchi): la base e' solo roccia
        # chiaro/scuro + muschio; crepe e volume li danno le faccette (sotto).
        STEP = 4
        wl = W // STEP + 2; hl = H // STEP + 2
        TXl = (np.arange(wl, dtype=np.float32) * STEP / ts)[None, :]
        TYl = (np.arange(hl, dtype=np.float32) * STEP / ts)[:, None]
        mott_l = (_np_vnoise(TXl / 2.2, TYl / 2.2) * 0.6
                  + _np_vnoise(TXl / 0.8 + 5, TYl / 0.8 + 5) * 0.4).astype(np.float32)
        mo_l = _np_vnoise(TXl / 3.2 + 20, TYl / 3.2 + 20).astype(np.float32)
        fx = np.arange(W, dtype=np.float32) / STEP
        x0 = np.floor(fx).astype(np.int64); x1 = np.minimum(x0 + 1, wl - 1)
        wx = (fx - x0)[None, :]

        def up_x(f):
            return f[:, x0] * (1 - wx) + f[:, x1] * wx
        mott_x = up_x(mott_l); mo_x = up_x(mo_l)
        STRIP = 300
        for y0 in range(0, H, STRIP):
            y1 = min(H, y0 + STRIP)
            fy = np.arange(y0, y1, dtype=np.float32) / STEP
            y0i = np.floor(fy).astype(np.int64); y1i = np.minimum(y0i + 1, hl - 1)
            wy = (fy - y0i)[:, None]
            mott = mott_x[y0i] * (1 - wy) + mott_x[y1i] * wy
            t = np.clip((mott - 0.25) / 0.45, 0.0, 1.0)[..., None]
            col = TOPc + (TOPhi - TOPc) * t              # roccia illuminata
            col = col + (TOPsh - col) * np.clip((0.26 - mott) / 0.32, 0, 1)[..., None]  # avvallamenti (non neri)
            mo = mo_x[y0i] * (1 - wy) + mo_x[y1i] * wy
            mk = np.clip((mo - 0.56) / 0.22, 0.0, 1.0)[..., None]
            moss = MOSSdk + (MOSSc - MOSSdk) * t         # muschio chiaro/scuro
            col = col + (moss - col) * (mk * 0.8)
            v3[:, y0:y1, :] = np.clip(col, 0, 255).astype(np.uint8).transpose(1, 0, 2)
        del v3
        va = sa.pixels_alpha(top_surf); va[:] = (solid.T.astype(np.uint8) * 255); del va
        # Dettaglio di roccia sulla cima (densita' della vecchia texture): tante
        # FACCETTE spigolose (danno piatti + crepe nette + volume), qualche MASSO
        # tondo in rilievo e fiocchi di MUSCHIO. Tutto ritagliato alla sagoma.
        ys_s, xs_s = np.where(solid)
        if len(xs_s):
            frng = random.Random(0xF00D ^ (len(xs_s) & 0xFFFFFFFF))
            ntile = len(xs_s) / float(ts * ts)
            nf = min(16000, max(10, int(ntile * 2.4)))      # ~2-3 faccette per tile
            for _ in range(nf):
                j = frng.randrange(len(xs_s))
                fx = int(xs_s[j]); fy = int(ys_s[j])
                fr = frng.randint(max(2, ts // 5), max(4, int(ts * 0.42)))
                p._rock_facet(top_surf, fx, fy, fr, frng, JW_TOP, JW_HILITE, JW_TOP_SH)
            nb = min(4000, max(3, int(ntile * 0.5)))         # massi in rilievo
            for _ in range(nb):
                j = frng.randrange(len(xs_s))
                bx = int(xs_s[j]); by = int(ys_s[j])
                br = frng.randint(max(2, ts // 5), max(4, int(ts * 0.34)))
                p._round_rock(top_surf, bx, by, br, frng, JW_TOP, JW_HILITE, JW_TOP_SH)
            nm = min(6000, max(4, int(ntile * 1.2)))         # fiocchi di muschio
            for _ in range(nm):
                j = frng.randrange(len(xs_s))
                mx = int(xs_s[j]); my = int(ys_s[j])
                mc = JW_MOSS if frng.random() < 0.6 else JW_MOSS_DK
                pygame.draw.circle(top_surf, mc, (mx, my), frng.randint(1, max(1, ts // 8)))
            va2 = sa.pixels_alpha(top_surf)
            np.minimum(va2, solid.T.astype(np.uint8) * 255, out=va2); del va2

        # --- (2) CLIFF: parete sotto il bordo sud, segue la sagoma ------------
        south = solid & dn
        cliff = np.zeros((Hf, W), bool)
        depth = np.zeros((Hf, W), np.int16)
        for k in range(1, Hh + 1):
            seg = cliff[k:H + k]
            newly = south & ~seg
            seg |= south
            depth[k:H + k][newly] = k
        solid_full = np.zeros((Hf, W), bool); solid_full[:H] = solid
        cliff &= ~solid_full
        # Parete in tono di ROCCIA (non nera, cosi non sembra un buco): spalla
        # illuminata in alto (CLhi) che sfuma al grigio-pietra JW_CLIFF in basso.
        CL = np.array(JW_CLIFF, np.float32); CLhi = np.array(JW_CLIFF_HI, np.float32)
        ms = pygame.Surface((W, Hf), pygame.SRCALPHA)
        c3 = sa.pixels3d(ms); ca = sa.pixels_alpha(ms)
        dfrac = (depth.astype(np.float32) / max(1, Hh))[..., None]
        clrgb = CLhi + (CL - CLhi) * np.clip(dfrac * 1.1, 0, 1)
        cmask3 = cliff[..., None]
        c3[:] = np.where(cmask3, clrgb, 0).astype(np.uint8).transpose(1, 0, 2)
        ca[:] = (cliff.T.astype(np.uint8) * 255)
        del c3, ca
        # cima sopra la parete.
        ms.blit(top_surf, (0, 0))

        # --- (3) RIM chiaro/scuro lungo il NUOVO contorno (definizione) -------
        rim = pygame.Surface((W, H), pygame.SRCALPHA)
        r3 = sa.pixels3d(rim); ra = sa.pixels_alpha(rim)
        light = boundary & (up | lf)
        dark = boundary & (dn | rt) & ~light
        RIMc = np.array(JW_RIM, np.uint8); EDGEc = np.array(JW_EDGE_SH, np.uint8)
        r3[light.T] = RIMc; ra[light.T] = 200
        r3[dark.T] = EDGEc; ra[dark.T] = 160
        del r3, ra
        ms.blit(rim, (0, 0))

        # --- (4) MASSI lungo il contorno (massi tondi, luce alto-sinistra) ----
        ys, xs = np.where(boundary)
        if len(xs):
            rng = random.Random(0x5EED ^ (W * 2654435761 ^ H) & 0xFFFFFFFF)
            n = max(8, int(len(xs) / max(1.0, ts * 0.45)))
            er = max(2, int(ts * 0.22))
            sel = rng.sample(range(len(xs)), min(n, len(xs)))
            for i in sel:
                x = int(xs[i]); y = int(ys[i])
                jr = er + rng.randint(-1, 2)
                xx = x + rng.randint(-1, 1); yy = y + rng.randint(-1, 1)
                if up[y, x] or lf[y, x]:                  # verso la luce -> chiaro
                    p._round_rock(ms, xx, yy, jr, rng, JW_TOP, JW_HILITE, JW_TOP_SH)
                else:                                     # in ombra -> scuro
                    p._round_rock(ms, xx, yy, jr, rng, JW_TOP_SH, JW_TOP, JW_EDGE_SH)

        # --- (5) blit LAZY per chunk (solo blocchi con pixel) nel layer walls --
        off_y = top - Hh                                  # = 0: la cima e' estrusa su di H
        for by in range(0, Hf, CHUNK):
            bh = min(CHUNK, Hf - by)
            for bx in range(0, W, CHUNK):
                bw = min(CHUNK, W - bx)
                sub = ms.subsurface(pygame.Rect(bx, by, bw, bh))
                if sub.get_bounding_rect(min_alpha=1).width > 0:
                    walls.blit(sub.copy(), (bx, by + off_y))

    def _build_lighting(self, grid, light) -> None:
        """Velo d'atmosfera SOPRA le unita (lighting_overlay):
          - ombre della chioma: rumore a bassa frequenza, scuro e semitrasparente,
            SOLO sulla giungla (non sulle lane) -> giungla piu cupa delle lane;
          - macchie di luce calda e tenue vicino ai campi (radura illuminata),
            che "aprono" la chioma scurita;
          - alfe contenute, cosi le unita restano leggibili.
        Calcolato per strisce orizzontali (niente array a piena mappa)."""
        ts = self.tile_size; top = self._top
        Wt, Ht = grid.width, grid.height
        W, H = Wt * ts, Ht * ts
        tiles = grid.tiles
        # Giungla = tutto cio che NON e' lane (a livello tile). Muri a parte:
        # la loro CIMA va quasi esclusa dal velo (restano i rilievi piu chiari).
        jungle = np.ones((Ht, Wt), np.float32)
        wall_t = np.zeros((Ht, Wt), bool)
        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                if row[tx] == TILE_LANE:
                    jungle[ty, tx] = 0.0
                elif row[tx] in (TILE_WALL, TILE_JUNGLE_WALL):
                    wall_t[ty, tx] = True
        # Maschera dei muri a piena risoluzione: il muro e' estruso verso l'alto
        # di H, quindi la sua cima cade nella cella SOPRA -> marco anche quella
        # fascia (indicizzando la riga del muro sia da y//ts che da (y+H)//ts).
        Hx = self._H
        ry_base = np.clip(np.arange(H) // ts, 0, Ht - 1)
        ry_cap = np.clip((np.arange(H) + Hx) // ts, 0, Ht - 1)
        cx_tile = np.clip(np.arange(W) // ts, 0, Wt - 1)
        wall_px = (wall_t[ry_base][:, cx_tile] | wall_t[ry_cap][:, cx_tile])  # (H, W) bool
        # Rumore a bassa frequenza (chiome) per tile -> chiazze d'ombra densa.
        TX = np.arange(Wt, dtype=np.float32)[None, :]
        TY = np.arange(Ht, dtype=np.float32)[:, None]
        canopy = (_np_vnoise(TX / 6.5, TY / 6.5) * 0.6
                  + _np_vnoise((TX + 30) / 3.1, (TY + 30) / 3.1) * 0.4).astype(np.float32)
        sden = np.clip((canopy - 0.42) / 0.30, 0.0, 1.0)
        sden = sden * sden * (3.0 - 2.0 * sden)       # smoothstep
        camps_px = [((tx + 0.5) * ts, (ty + 0.5) * ts) for (tx, ty) in self._camps]
        Rpx = CAMP_R_TILES * ts
        Cd = np.array(CANOPY_DARK, np.float32)
        Cw = np.array(CAMP_WARM, np.float32)
        # Interpolazione lungo X, una volta (sden bilineare, giungla nearest).
        fx = np.arange(W, dtype=np.float32) / ts
        x0 = np.floor(fx).astype(np.int64); x1 = np.minimum(x0 + 1, Wt - 1)
        wx = (fx - x0)[None, :]
        sden_x = sden[:, x0] * (1 - wx) + sden[:, x1] * wx       # (Ht, W)
        jung_x = jungle[:, np.minimum(np.arange(W) // ts, Wt - 1)]  # (Ht, W) nearest
        px_x = np.arange(W, dtype=np.float32)[None, :]
        rgb_full = np.zeros((H, W, 3), np.uint8)
        a_full = np.zeros((H, W), np.uint8)
        STRIP = 256
        for yb in range(0, H, STRIP):
            ye = min(H, yb + STRIP)
            rows = np.arange(yb, ye)
            fy = rows.astype(np.float32) / ts
            y0 = np.floor(fy).astype(np.int64); y1 = np.minimum(y0 + 1, Ht - 1)
            wy = (fy - y0)[:, None]
            sden_px = sden_x[y0] * (1 - wy) + sden_x[y1] * wy    # (strip, W)
            jung_px = jung_x[np.minimum(rows // ts, Ht - 1)]     # (strip, W)
            # Luce dei campi: max dei falloff gaussiani (solo campi vicini alla striscia).
            w = np.zeros((len(rows), W), np.float32)
            ry = rows.astype(np.float32)[:, None] + 0.5
            for (cxp, cyp) in camps_px:
                if cyp < yb - 2.5 * Rpx or cyp > ye + 2.5 * Rpx:
                    continue
                dx = px_x - cxp; dy = ry - cyp
                np.maximum(w, np.exp(-(dx * dx + dy * dy) / (Rpx * Rpx)), out=w)
            # Sulla CIMA dei muri il velo si riduce quasi a zero e la luce calda
            # si attenua: i muri restano nettamente piu chiari del terreno.
            wpx = wall_px[yb:ye]
            keep_canopy = np.where(wpx, WALL_CANOPY_KEEP, 1.0).astype(np.float32)
            keep_warm = np.where(wpx, WALL_WARM_KEEP, 1.0).astype(np.float32)
            # Ombra della chioma (ridotta vicino ai campi) + luce calda, composite.
            ad = (CANOPY_BASE + CANOPY_AMP * sden_px) * jung_px * (1.0 - 0.85 * w) * keep_canopy
            aw = CAMP_WARM_A * w * keep_warm
            ad01 = ad / 255.0; aw01 = aw / 255.0
            out_a = aw01 + ad01 * (1.0 - aw01)
            denom = np.where(out_a > 1e-4, out_a, 1.0)
            for k in range(3):
                col = (Cw[k] * aw01 + Cd[k] * ad01 * (1.0 - aw01)) / denom
                rgb_full[yb:ye, :, k] = np.clip(col, 0, 255).astype(np.uint8)
            a_full[yb:ye, :] = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)
        self._blit_blocks(light, rgb_full, a_full, top)

    def _vignette(self, vw: int, vh: int):
        """Vignettatura screen-space: scurimento morbido ai bordi dello schermo.
        Costruita una volta per dimensione della vista (cache)."""
        if self._vig is not None and self._vig.get_size() == (vw, vh):
            return self._vig
        import pygame.surfarray as sa
        surf = pygame.Surface((vw, vh), pygame.SRCALPHA)
        xs = (np.arange(vw, dtype=np.float32) - (vw - 1) / 2) / (vw / 2)
        ys = (np.arange(vh, dtype=np.float32) - (vh - 1) / 2) / (vh / 2)
        d = np.sqrt(xs[:, None] ** 2 + ys[None, :] ** 2)     # distanza ellittica normalizzata
        t = np.clip((d - 0.65) / 0.5, 0.0, 1.0)
        t = t * t * (3.0 - 2.0 * t)
        a = (t * VIGNETTE_A).astype(np.uint8)
        v3 = sa.pixels3d(surf)
        v3[:, :, 0] = VIGNETTE_COL[0]; v3[:, :, 1] = VIGNETTE_COL[1]; v3[:, :, 2] = VIGNETTE_COL[2]
        del v3
        va = sa.pixels_alpha(surf); va[:] = a; del va
        self._vig = surf
        return surf

    # --- Suolo organico (rumore per pixel in coord mondo) --------------------
    def _build_floor(self, grid, p, inner) -> pygame.Surface:
        """Immagine del suolo di giungla a piena mappa, calcolata PER PIXEL in
        coordinate mondo con numpy (niente smoothscale). Il verde a due scale
        resta continuo; muschio e fango vengono QUANTIZZATI in 2-3 livelli e i
        confini sono sgranati con dithering di Bayer -> chiazze organiche che
        attraversano i tile ma con bordi a gradini in stile pixel art. Elaborata
        a strisce orizzontali per non allocare array enormi (mappe grandi)."""
        from game.renderer import GRASS_LO, GRASS_HI, JUNGLE_MOSS, JUNGLE_MUD
        ts = self.tile_size
        Wt, Ht = grid.width, grid.height
        W, H = Wt * ts, Ht * ts
        floor = pygame.Surface((W, H))
        GLO = np.array(GRASS_LO, np.float32); GHI = np.array(GRASS_HI, np.float32)
        MOSS = np.array(JUNGLE_MOSS, np.float32)
        # Fango SCHIARITO (#4A3D2C) con variazione interna: un rumore fine fa
        # oscillare il tono tra una versione chiara e una più scura (pozzanghere)
        # -> non più una macchia marrone uniforme che sembra un buco.
        MUD_L = np.array(JUNGLE_MUD, np.float32)            # #4A3D2C
        MUD_D = np.array((52, 42, 29), np.float32)          # pozzanghera più scura
        # Forza del livello di chiazza (0=niente .. pieno): pochi gradini netti.
        # Il muschio ha gradini PICCOLI (poco contrasto -> dithering discreto).
        MUD_STR = np.array([0.0, 0.5, 0.78, 1.0], np.float32)   # 3 livelli + 0
        MOSS_STR = np.array([0.0, 0.28, 0.48], np.float32)      # 2 livelli + 0

        # Le chiazze sono a BASSA frequenza: calcolo i campi di rumore (tinta,
        # muschio, fango) a risoluzione ridotta UNA volta, poi li interpolo
        # (bilineare) a piena risoluzione per strisce e quantizzo+dithero lì.
        # Molto più veloce del rumore per pixel, resa identica.
        STEP = 4
        wl = W // STEP + 2; hl = H // STEP + 2
        TXl = (np.arange(wl, dtype=np.float32) * STEP / ts)[None, :]
        TYl = (np.arange(hl, dtype=np.float32) * STEP / ts)[:, None]
        tone_l = _np_tone(TXl, TYl).astype(np.float32)
        moss_l = _np_moss(TXl, TYl).astype(np.float32)
        mud_l = _np_mud(TXl, TYl).astype(np.float32)
        mtone_l = _np_mudtone(TXl, TYl).astype(np.float32)   # variazione interna fango
        # Indici/pesi bilineari lungo X (una volta sola).
        fx = np.arange(W, dtype=np.float32) / STEP
        x0 = np.floor(fx).astype(np.int64); x1 = np.minimum(x0 + 1, wl - 1)
        wx = (fx - x0)[None, :]
        # Pre-interpola i campi lungo X (una volta sola): (hl, W) float32. Poi in
        # ogni striscia resta solo l'interpolazione in Y, cheap.
        def up_x(field):
            return field[:, x0] * (1 - wx) + field[:, x1] * wx
        tone_x = up_x(tone_l); moss_x = up_x(moss_l); mud_x = up_x(mud_l)
        mtone_x = up_x(mtone_l)
        colx = np.arange(W) % 4
        tx_cols = (np.arange(W) // ts)          # tile-x di ogni colonna (per inner)
        STRIP = 300
        dst = pygame.surfarray.pixels3d(floor)            # vista (W, H, 3) uint8
        for y0 in range(0, H, STRIP):
            y1 = min(H, y0 + STRIP)
            fy = np.arange(y0, y1, dtype=np.float32) / STEP
            y0i = np.floor(fy).astype(np.int64); y1i = np.minimum(y0i + 1, hl - 1)
            wy = (fy - y0i)[:, None]
            bay = _BAYER[(np.arange(y0, y1)[:, None]) % 4, colx[None, :]]

            def dlevel(valN, nmax):
                # Livello quantizzato con DITHERING solo in una FASCIA STRETTA
                # vicino al confine tra due livelli: così gran parte della chiazza
                # è a tinta piena e il retino a scacchiera resta sottile.
                lo = np.floor(valN)
                t = valN - lo
                tt = np.clip((t - 0.38) / 0.24, 0.0, 1.0)      # 0 pieno-basso .. 1 pieno-alto
                lvl = lo + (bay < tt)
                return np.clip(lvl, 0, nmax).astype(np.int64)

            tone = tone_x[y0i] * (1 - wy) + tone_x[y1i] * wy
            r = GLO[0] + (GHI[0] - GLO[0]) * tone
            g = GLO[1] + (GHI[1] - GLO[1]) * tone
            b = GLO[2] + (GHI[2] - GLO[2]) * tone
            moss = moss_x[y0i] * (1 - wy) + moss_x[y1i] * wy
            ms = MOSS_STR[dlevel(moss * 2.0, 2)]
            r += (MOSS[0] - r) * ms; g += (MOSS[1] - g) * ms; b += (MOSS[2] - b) * ms
            mud = mud_x[y0i] * (1 - wy) + mud_x[y1i] * wy
            mu = MUD_STR[dlevel(mud * 3.0, 3)]
            # Niente fango fuori dall'anello delle lane (zona esterna).
            inner_px = inner[(np.arange(y0, y1) // ts)][:, tx_cols]
            mu = mu * inner_px
            # Tono del fango variato dal rumore: pozzanghere scure dove mt è basso.
            mt = mtone_x[y0i] * (1 - wy) + mtone_x[y1i] * wy
            mcr = MUD_D[0] + (MUD_L[0] - MUD_D[0]) * mt
            mcg = MUD_D[1] + (MUD_L[1] - MUD_D[1]) * mt
            mcb = MUD_D[2] + (MUD_L[2] - MUD_D[2]) * mt
            r += (mcr - r) * mu; g += (mcg - g) * mu; b += (mcb - b) * mu
            dst[:, y0:y1, 0] = np.clip(r, 0, 255).T
            dst[:, y0:y1, 1] = np.clip(g, 0, 255).T
            dst[:, y0:y1, 2] = np.clip(b, 0, 255).T
        del dst
        return floor

    def _scatter_detail(self, grid, floor_img, p, path_tiles, inner) -> None:
        """Dettagli sul suolo (in coordinate MONDO, disegnati sull'immagine del
        suolo prima del blit): ciuffi d'erba sul verde (NON sui sentieri né sul
        fango nudo), fiocchi di muschio e, SOLO nel fango interno, granelli,
        qualche pozzanghera più scura e ciuffi d'erba lungo i bordi."""
        from game.renderer import (GRASS_TUFT_LIGHT, GRASS_TUFT_DARK,
                                    MOSS_FLECK_L, MOSS_FLECK_D, MUD_SPECK)
        MUD_PUDDLE = (46, 37, 25)        # pozzanghera scura (puntino)
        ts = self.tile_size
        Wt, Ht = grid.width, grid.height
        tiles = grid.tiles
        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                if row[tx] in TALL_TILES or row[tx] != TILE_FLOOR:
                    continue
                cx0, cy0 = tx * ts, ty * ts
                rng = random.Random(((tx * 73856093) ^ (ty * 19349663)) & 0xFFFFFFFF)
                is_inner = bool(inner[ty, tx])
                mu = p._mud_at(tx + 0.5, ty + 0.5) if is_inner else 0.0  # niente fango fuori
                mo = p._moss_at(tx + 0.5, ty + 0.5)
                on_path = (tx, ty) in path_tiles
                if not on_path and mu < 0.5:    # fili d'erba (non sul sentiero)
                    # Più fitti ai BORDI del fango (0.15<mu<0.5): l'erba invade.
                    n = rng.randint(2, 4) + (2 if 0.15 < mu < 0.5 else 0)
                    for _ in range(n):
                        x = cx0 + rng.randint(2, ts - 2)
                        y = cy0 + rng.randint(ts // 2, ts - 2)
                        hgt = rng.randint(2, max(3, ts // 4))
                        c = GRASS_TUFT_LIGHT if rng.random() < 0.6 else GRASS_TUFT_DARK
                        pygame.draw.line(floor_img, c, (x, y), (x, y - hgt), 1)
                if mo > 0.3:
                    for _ in range(rng.randint(1, 3)):
                        x = cx0 + rng.randint(1, ts - 2); y = cy0 + rng.randint(1, ts - 2)
                        floor_img.set_at((x, y), MOSS_FLECK_L if rng.random() < 0.5 else MOSS_FLECK_D)
                if mu > 0.35:
                    for _ in range(rng.randint(1, 3)):
                        x = cx0 + rng.randint(1, ts - 2); y = cy0 + rng.randint(1, ts - 2)
                        floor_img.set_at((x, y), MUD_SPECK)
                    if mu > 0.6 and rng.random() < 0.5:   # pozzanghera più scura
                        px = cx0 + rng.randint(3, ts - 4); py = cy0 + rng.randint(3, ts - 4)
                        pygame.draw.ellipse(floor_img, MUD_PUDDLE,
                                            pygame.Rect(px, py, rng.randint(3, 5), rng.randint(2, 3)))

    # --- Sentieri di terra battuta (strisce continue spline) -----------------
    def _compute_paths(self, grid):
        """Dijkstra multi-sorgente dai tile-lane -> per ogni campo il percorso
        verso la lane più vicina. Il costo PENALIZZA i tile adiacenti ai muri:
        così il sentiero preferisce il terreno aperto e, quando un muro è vicino,
        gli corre ACCANTO invece di infilarsi contro (o sotto). Aggira i muri ed
        evita l'acqua. Ritorna (routes, path_tiles): le rotte in tile e i tile
        coperti (centro + 1 anello) per non disegnarci i fili d'erba."""
        import heapq
        routes, path_tiles = [], set()
        if not self._camps:
            return routes, path_tiles
        Wt, Ht = grid.width, grid.height
        tiles = grid.tiles
        # Ostacoli che il sentiero deve AGGIRARE: muri e anche i cespugli (un
        # sentiero non passa sotto un cespuglio).
        obstacles = (TILE_WALL, TILE_JUNGLE_WALL, TILE_BUSH)

        def walk(x, y):
            return (0 <= x < Wt and 0 <= y < Ht
                    and tiles[y][x] in (TILE_FLOOR, TILE_LANE))

        def near_wall(x, y):
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    nx, ny = x + ox, y + oy
                    if 0 <= nx < Wt and 0 <= ny < Ht and tiles[ny][nx] in obstacles:
                        return True
            return False

        dist = {}
        parent = {}
        heap = []
        has_lane = False
        for y in range(Ht):
            row = tiles[y]
            for x in range(Wt):
                if row[x] == TILE_LANE:
                    has_lane = True
                    dist[(x, y)] = 0.0
                    parent[(x, y)] = None
                    heapq.heappush(heap, (0.0, x, y))
        if not has_lane:
            return routes, path_tiles
        NB = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
              (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142))
        WALL_PEN = 4.0
        while heap:
            d, cx, cy = heapq.heappop(heap)
            if d > dist.get((cx, cy), 1e18):
                continue
            for dx, dy, cost in NB:
                nx, ny = cx + dx, cy + dy
                if not walk(nx, ny):
                    continue
                if dx and dy and not (walk(cx + dx, cy) and walk(cx, cy + dy)):
                    continue
                nd = d + cost + (WALL_PEN if near_wall(nx, ny) else 0.0)
                if nd < dist.get((nx, ny), 1e18):
                    dist[(nx, ny)] = nd
                    parent[(nx, ny)] = (cx, cy)
                    heapq.heappush(heap, (nd, nx, ny))

        for camp_x, camp_y in self._camps:
            start = (int(camp_x), int(camp_y))
            if start not in parent:
                continue
            route, cur, guard = [], start, 0
            while cur is not None and guard < Wt * Ht:
                route.append(cur)
                cur = parent.get(cur)
                guard += 1
            if len(route) < 3:          # campo praticamente sulla lane: niente
                continue
            routes.append(route)
            for tx, ty in route:                 # centro + 1 anello -> larghezza
                for ox in (-1, 0, 1):
                    for oy in (-1, 0, 1):
                        path_tiles.add((tx + ox, ty + oy))
        return routes, path_tiles

    @staticmethod
    def _catmull(pts, spp):
        """Curva Catmull-Rom attraverso `pts` (passa per i punti), `spp` campioni
        per segmento -> una striscia morbida invece di una spezzata."""
        if len(pts) < 2:
            return list(pts)
        P = [pts[0]] + list(pts) + [pts[-1]]
        out = []
        for i in range(1, len(P) - 2):
            p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
            for s in range(spp):
                t = s / spp
                t2 = t * t; t3 = t2 * t
                x = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t
                           + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                           + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
                y = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t
                           + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                           + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
                out.append((x, y))
        out.append(pts[-1])
        return out

    def _stroke_paths(self, decor, grid, routes, p) -> None:
        """Disegna ogni rotta come una STRISCIA continua di terra battuta in stile
        pixel art: spline deformata con rumore, larghezza variabile (rumore), e
        profilo a 3 LIVELLI netti (bordo scuro, terra, nucleo secco) col BORDO
        ESTERNO sgranato a dithering di Bayer (niente sfumatura morbida). Sopra:
        ciuffi d'erba che invadono la terra, qualche sassolino e foglia. La terra
        resta solo sui tile d'erba (gli altri tile vengono ritagliati)."""
        if not routes:
            return
        import pygame.surfarray as sa
        from game.renderer import (JUNGLE_DIRT, DIRT_DRY, GRASS_TUFT_LIGHT,
                                    GRASS_FRINGE, BUSH_MID)
        ts = self.tile_size
        top = self._top
        Wt, Ht = grid.width, grid.height
        tiles = grid.tiles
        DIRT = np.array(JUNGLE_DIRT, np.float32)
        DRY = np.array(DIRT_DRY, np.float32)
        EDGE = (np.array(JUNGLE_DIRT, np.float32) * 0.82)   # bordo umido più scuro
        PEBBLE = ((72, 68, 62), (104, 98, 88))
        LEAF = (BUSH_MID, (96, 104, 60))

        # --- 1. Geometria di OGNI rotta (spline deformata + larghezza variabile)
        #     e relativi dischi. I dischi di TUTTE le rotte confluiscono in UN
        #     SOLO insieme: dove due sentieri si incrociano o condividono un
        #     tratto le maschere sono l'UNIONE -> un unico incrocio a bordi fusi,
        #     senza strisce sovrapposte né doppi bordi scuri. Ogni rotta termina
        #     sul suo CAMPO con una RADURA tonda di terra battuta, così il ramo
        #     "porta a un campo" e non svanisce nell'erba vicino a un muro.
        er_d = []; br_d = []; mr_d = []; cr_d = []   # dischi globali: (x, y, r)
        geoms = []                                   # per rotta, per decori/bbox
        for route in routes:
            pts = [(tx * ts + ts / 2, ty * ts + ts / 2) for (tx, ty) in route]
            ctrl = pts[::2]
            if ctrl[-1] != pts[-1]:
                ctrl.append(pts[-1])
            curve = self._catmull(ctrl, 8)
            if len(curve) < 2:
                continue
            seed = (hash(route[0]) & 0xFFFF)
            amp = ts * 0.45
            samp = []; perps = []; cr = []; er = []
            for i, (x, y) in enumerate(curve):
                px, py = curve[max(0, i - 1)]
                nx, ny = curve[min(len(curve) - 1, i + 1)]
                tgx, tgy = nx - px, ny - py
                tl = math.hypot(tgx, tgy) or 1.0
                perp = (-tgy / tl, tgx / tl)
                d = (p._vnoise(x / 34.0, y / 34.0) - 0.5) * 2.0 * amp
                sx, sy = x + perp[0] * d, y + perp[1] * d
                samp.append((sx, sy)); perps.append(perp)
                # Larghezza variabile lungo il percorso (rumore): ~1-2 tile.
                rm = 0.72 + 0.6 * p._vnoise(i * 0.5 + seed * 0.013, seed * 0.07)
                cri = max(1, int(ts * 0.30 * rm)); mri = max(1, int(ts * 0.52 * rm))
                eri = max(1, int(ts * 0.74 * rm))
                cr.append(cri); er.append(eri)
                er_d.append((sx, sy, eri)); br_d.append((sx, sy, (mri + eri) // 2))
                mr_d.append((sx, sy, mri)); cr_d.append((sx, sy, cri))
            # Radura del campo (route[0]): disco tondo centrato sul tile del campo
            # -> il sentiero finisce in uno slargo di terra, segno del campo.
            ctx, cty = route[0]
            ccx, ccy = ctx * ts + ts / 2, cty * ts + ts / 2
            ce = max(2, int(ts * 0.92)); cmd = max(2, int(ts * 0.64)); ccr = max(1, int(ts * 0.38))
            er_d.append((ccx, ccy, ce)); br_d.append((ccx, ccy, (cmd + ce) // 2))
            mr_d.append((ccx, ccy, cmd)); cr_d.append((ccx, ccy, ccr))
            xs = [q[0] for q in samp] + [ccx]; ys = [q[1] for q in samp] + [ccy]
            geoms.append((samp, perps, cr, er, xs, ys, hash(route[-1]) & 0xFFFFFFFF))
        if not geoms:
            return

        marg = int(ts * 1.4)

        def discs_in(lst, bx0, by0, bx1, by1):
            return [(x, y, r) for (x, y, r) in lst
                    if x + r >= bx0 and x - r <= bx1 and y + r >= by0 and y - r <= by1]

        # --- 2. Rasterizza ogni rotta nella sua bbox, ma con l'UNIONE di TUTTI i
        #     dischi che la toccano (fusione degli incroci). Le bbox che si
        #     sovrappongono ricompongono gli STESSI pixel (stesse maschere, stesso
        #     dithering in coord assolute) -> idempotente, nessun doppio strato.
        for (samp, perps, cr, er, xs, ys, dseed) in geoms:
            bx0 = max(0, int(min(xs)) - marg); by0 = max(0, int(min(ys)) - marg)
            bx1 = min(Wt * ts, int(max(xs)) + marg); by1 = min(Ht * ts, int(max(ys)) + marg)
            bw, bh = bx1 - bx0, by1 - by0
            if bw <= 0 or bh <= 0:
                continue

            # Maschere piene dei raggi (unione di TUTTI i dischi nella bbox).
            temp = pygame.Surface((bw, bh))

            def mask(lst):
                temp.fill((0, 0, 0))
                for (x, y, r) in discs_in(lst, bx0, by0, bx1, by1):
                    pygame.draw.circle(temp, (255, 255, 255), (int(x - bx0), int(y - by0)), r)
                return sa.array_red(temp) > 127

            em = mask(er_d); bm = mask(br_d); mm = mask(mr_d); cm = mask(cr_d)
            ax = (bx0 + np.arange(bw))[:, None]
            ay = (by0 + np.arange(bh))[None, :]
            bay = _BAYER[ay % 4, ax % 4]            # soglia di dithering per pixel
            rgb = np.zeros((bw, bh, 3), np.float32)
            alpha = np.zeros((bw, bh), np.float32)
            edge_in = bm & ~mm                       # bordo interno: dither denso
            edge_out = em & ~bm                      # bordo esterno: dither rado
            mid_only = mm & ~cm
            rgb[edge_in] = EDGE; alpha[edge_in & (bay < 0.62)] = 255
            rgb[edge_out] = EDGE; alpha[edge_out & (bay < 0.32)] = 255
            rgb[mid_only] = DIRT; alpha[mid_only] = 255
            rgb[cm] = DRY; alpha[cm] = 255
            ribbon = pygame.Surface((bw, bh), pygame.SRCALPHA)
            v3 = sa.pixels3d(ribbon); v3[:] = np.clip(rgb, 0, 255).astype(np.uint8); del v3
            va = sa.pixels_alpha(ribbon); va[:] = alpha.astype(np.uint8); del va

            # Ciuffi d'erba che invadono la terra dal bordo + sassolini e foglie.
            rng = random.Random(dseed)
            for i in range(0, len(samp), 2):
                x, y = samp[i]; pxp, pyp = perps[i]
                if rng.random() < 0.5:               # ciuffo d'erba dal bordo verso l'interno
                    side = 1 if rng.random() < 0.5 else -1
                    ex = x + pxp * er[i] * side; ey = y + pyp * er[i] * side
                    bl = rng.randint(2, 5)
                    c = GRASS_TUFT_LIGHT if rng.random() < 0.5 else GRASS_FRINGE
                    pygame.draw.line(ribbon, c, (int(ex - bx0), int(ey - by0)),
                                     (int(ex - pxp * bl * side - bx0), int(ey - pyp * bl * side - by0)), 1)
                if rng.random() < 0.45:              # sassolino o foglia sul battuto
                    jx = rng.randint(-cr[i], cr[i]); jy = rng.randint(-cr[i], cr[i])
                    qx, qy = int(x + jx - bx0), int(y + jy - by0)
                    if 0 <= qx < bw and 0 <= qy < bh:
                        if rng.random() < 0.6:
                            pygame.draw.circle(ribbon, rng.choice(PEBBLE), (qx, qy), 1)
                        else:
                            lf = rng.choice(LEAF)
                            pygame.draw.ellipse(ribbon, lf, pygame.Rect(qx, qy, 3, 2))

            # Ritaglio: la terra resta solo sui tile d'erba (via gli altri).
            tx0, ty0 = bx0 // ts, by0 // ts
            tx1, ty1 = (bx1 - 1) // ts + 1, (by1 - 1) // ts + 1
            clear = (0, 0, 0, 0)
            for ty in range(ty0, ty1):
                for tx in range(tx0, tx1):
                    if not (0 <= tx < Wt and 0 <= ty < Ht) or tiles[ty][tx] != TILE_FLOOR:
                        ribbon.fill(clear, pygame.Rect(tx * ts - bx0, ty * ts - by0, ts, ts))
            decor.blit(ribbon, (bx0, by0 + top))

    def _grid_line_sprite(self):
        if self._grid_sprite is None:
            ts = self.tile_size
            s = pygame.Surface((ts, ts), pygame.SRCALPHA)
            pygame.draw.rect(s, COL_GRID, pygame.Rect(0, 0, ts, ts), 1)
            self._grid_sprite = s
        return self._grid_sprite

    # --- disegno per frame (solo blit dei chunk visibili) -------------------
    def _offset(self, camera):
        # Usa l'offset INTERO della camera (camera.ox/oy, arrotondato una volta
        # per frame): lo stesso che usano le unita in world_to_screen -> mappa e
        # unita si muovono insieme, niente tremolio di 1px tra le due.
        return (-camera.ox, -camera.oy - self._top)

    def draw(self, screen, camera) -> None:
        """Layer SOTTO le unita: ground, decor, ombre, muri/vegetazione base."""
        ox, oy = self._offset(camera)
        vw, vh = camera.view_w, camera.view_h
        for n in self.BELOW:
            self.layers[n].draw(screen, ox, oy, vw, vh)

    def draw_canopy(self, screen, camera) -> None:
        """Layer SOPRA le unita: chiome e velo di luce (vuoti per ora)."""
        ox, oy = self._offset(camera)
        vw, vh = camera.view_w, camera.view_h
        for n in self.ABOVE:
            self.layers[n].draw(screen, ox, oy, vw, vh)
        # Vignettatura: ultima, ai bordi della VISTA (screen-space, non mappa).
        screen.blit(self._vignette(vw, vh), (0, 0))

    # --- introspezione (per benchmark/report) -------------------------------
    def mem_report(self) -> dict:
        return {n: lyr.mem_bytes() for n, lyr in self.layers.items()}
