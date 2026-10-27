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
                         TILE_RIVER, TILE_WALL)

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
# Muri di giungla come rilievi pseudo-3D (stile LoL): cima vegetata + parete di
# roccia + ombra lunga. Contorno scuro delle chiome (#12281A).
CANOPY_OUTLINE = (18, 40, 26)

# --- ERBA ALTA (cespugli, stile MOBA) -----------------------------------------
# Massa COMPATTA di erba alta: area dalla maschera organica (come i muri),
# riempita di fondo scuro pieno (niente terreno dentro) e texturizzata con file
# fitte di ciuffi sfalsate. Palette smeraldo fredda (distinta dalla chioma).
GB_FILL = (22, 64, 46)           # #16402E fondo pieno interno (niente terreno)
GB_OUT = (15, 42, 32)            # #0F2A20 contorno scuro
GB_DARK = (30, 90, 63)           # #1E5A3F ciuffi in ombra / fronte
GB_MID = (47, 125, 91)           # #2F7D5B ciuffi a mezza luce
GB_LIGHT = (79, 163, 110)        # #4FA36E ciuffi illuminati (alto-sinistra)
GB_TIP = (143, 208, 138)         # #8FD08A punte chiare (poche, qua e la')
GR_SHADOW = (0, 0, 0, 70)        # ombra morbida a terra

# --- FIUME (acqua resa a LIVELLO MAPPA, come muri/cespugli) --------------------
# La silhouette (maschera -> dischi -> blur -> soglia + rumore) smussa i bordi
# del fiume (autotiling implicito: niente scaletta per-tile). Il corpo d'acqua ha
# un gradiente di PROFONDITA' (centro scuro, bordi chiari), increspature di
# corrente, una riva sfumata (fango + canne), ninfee e sassi affioranti, e una
# sottile linea di schiuma ANIMATA (piu' fotogrammi pre-renderizzati).
RIV_EDGE = (96, 150, 170)        # bassofondo chiaro al bordo (riva)
RIV_MID = (54, 108, 150)         # acqua a mezza profondita
RIV_DEEP = (32, 72, 114)         # centro profondo, piu' scuro
RIV_FLOW = (124, 172, 196)       # increspature/riflessi di corrente (chiaro)
FOAM_COL = (204, 226, 232)       # schiuma chiara al bordo
SHORE_WET2 = (66, 86, 66)        # terra bagnata scura proprio al contatto
SHORE_MUD2 = (98, 104, 76)       # fango/sabbia bagnata sulla riva (lato terra)
REED_DK = (32, 56, 32)           # stelo canna in ombra / contorno
REED_MD = (56, 92, 46)           # canna a mezza luce
REED_TIP = (126, 156, 78)        # punta illuminata della canna
LILY_PAD = (46, 98, 64)          # foglia di ninfea
LILY_RIM = (24, 62, 40)          # bordo scuro della foglia
LILY_HI = (92, 150, 102)         # colpo di luce sulla foglia (alto-sinistra)
LILY_FLOWER = (224, 212, 224)    # fiore (raro)
ROCK_BASE = (88, 98, 106)        # sasso affiorante (grigio-blu desaturato)
ROCK_HI = (134, 144, 152)        # cupola illuminata (alto-sinistra)
ROCK_SH = (50, 58, 68)           # fondo in ombra
FOAM_FRAMES = 3                  # fotogrammi della schiuma animata
FOAM_MS = 240                    # durata di un fotogramma (ms)
FCELL = 256                      # lato cella per gli sprite di schiuma (memoria)

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
        self._tree_cache: dict = {}  # sprite albero per (R quantizzato, variante, palette)
        self._grass_cache: dict = {} # sprite ciuffo d'erba per (tier, variante)
        self._foam: list = []        # schiuma animata: [(ax, ay_layer, [surf per frame])]

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
        H = max(6, int(ts * 0.5))        # altezza di estrusione dei rilievi (cespugli)
        # Margine superiore: deve contenere l'estrusione piu alta, ovvero la
        # parete ~1 tile dei muri vegetati (RELIEF in _build_jungle_walls) -> cosi
        # la cima estrusa non viene tagliata al bordo alto della mappa.
        top = max(H, int(ts * 1.2))      # margine in alto per i rilievi di riga 0
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
                # I tile "alti" e il FIUME lasciano il suolo di giungla sotto: i
                # muri/cespugli si estrudono dopo (walls_base), il fiume si disegna
                # a livello mappa (_build_river) con bordi smussati e alfa che
                # sfuma sulla riva, cosi l'erba traspare al contatto con l'acqua.
                g = TILE_FLOOR if (t in TALL_TILES or t == TILE_RIVER) else t
                if g != TILE_FLOOR:
                    variant = (h >> 4) & 3
                    ground.blit(p._tile_surf(g, variant), (ax, ay))
                p._shore(decor, grid, tx, ty, ax, ay, g, t)
                if config.SHOW_GRID_LINES:
                    decor.blit(self._grid_line_sprite(), (ax, ay))

        # --- Sentieri di terra battuta: strisce continue (spline) camp->lane --
        self._stroke_paths(decor, grid, routes, p)

        # --- FIUME: corpo d'acqua a livello mappa (silhouette smussata, gradiente
        #     di profondita, riva sfumata con fango e canne, ninfee e sassi, piu'
        #     schiuma animata). Dopo i sentieri (che gia' evitano l'acqua).
        self._foam = []
        self._build_river(grid, decor)

        # --- SAGOMA DEI MURI DI GIUNGLA: maschera binaria a risoluzione tile ->
        #     blur gaussiano + soglia 0.5 + rumore -> silhouette morbida con
        #     diagonali vere e angoli tondi (niente scaletta per-tile). La
        #     collisione resta sulla griglia: la grafica puo sporgere/rientrare
        #     al massimo ~mezzo tile (clamp in _jungle_solid). Ombre e AO si
        #     ricalcolano da QUESTA maschera, non dai tile.
        solid = self._jungle_solid(grid)

        # --- Ombra proiettata a sud-est dalla SILHOUETTE (muro di giungla E muro
        #     di confine, ora unificati nella stessa sagoma vegetata: niente piu
        #     ombra per-tile della vecchia pietra).
        if solid is not None:
            self._build_jungle_shadow(grid, shadows, solid)

        # --- Ambient occlusion: gradiente morbido attorno ai corpi "alti"
        #     (silhouette dei muri + cespugli per-tile).
        self._build_ao(grid, shadows, solid)

        # --- CESPUGLI: massa COMPATTA di erba alta (stile MOBA). Area dalla
        #     maschera organica (blur+soglia+rumore come i muri), fondo pieno
        #     scuro + file fitte di ciuffi + fronte piu' lungo in basso. Disegnati
        #     PRIMA dei muri (z-order in walls_base): un muro sovrapposto li copre.
        bush_solid = self._bush_solid(grid)
        if bush_solid is not None:
            self._build_bushes(grid, walls, shadows, bush_solid)

        # --- Muri (giungla + confine) come rilievi vegetati: riempiono la
        #     silhouette, COPRENDO i cespugli sovrapposti.
        if solid is not None:
            self._build_jungle_walls(grid, walls, self.layers["canopy"], p, solid)

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
        dalla SILHOUETTE morbida dei muri di giungla/confine (non dai tile, cosi
        l'AO segue il contorno curvo) PIU i cespugli per-tile. La distanza
        euclidea e' calcolata con shifted-min, il falloff e' uno smoothstep (max a
        ridosso dell'ostacolo -> 0 a 1.5 tile), poi si upscala e si blitta."""
        ts = self.tile_size; top = self._top
        Wt, Ht = grid.width, grid.height
        W, H = Wt * ts, Ht * ts
        tiles = grid.tiles
        step = max(2, ts // 4)
        R = AO_RADIUS_TILES * ts / step              # raggio in celle low-res
        Rc = int(math.ceil(R))
        wl = (W + step - 1) // step; hl = (H + step - 1) // step
        tall = np.zeros((Ht, Wt), bool)               # cespugli per-tile
        for ty in range(Ht):
            trow = tiles[ty]
            for tx in range(Wt):
                if trow[tx] == TILE_BUSH:
                    tall[ty, tx] = True
        cx = np.minimum((np.arange(wl) * step) // ts, Wt - 1)
        cy = np.minimum((np.arange(hl) * step) // ts, Ht - 1)
        m = tall[cy][:, cx]
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
                if row[tx] in (TILE_JUNGLE_WALL, TILE_WALL):
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
        # NESSUN muro deve coprire un cespuglio: scavo attorno ai cespugli dal
        # campo dischi PRIMA del blur. NON per-tile (lascerebbe bordi DRITTI) ma
        # con un CAMPO DISTANZA dai centri-cespuglio -> la sagoma del muro si
        # CURVA attorno all'erba seguendo un contorno tondo, senza spigoli.
        bt = np.zeros((Ht, Wt), bool)
        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                if row[tx] == TILE_BUSH:
                    bt[ty, tx] = True
        if bt.any():
            bys, bxs = np.where(bt)
            bmask = np.zeros((hl, wl), bool)
            bbx = np.clip(((bxs + 0.5) * ts / s).astype(int), 0, wl - 1)
            bby = np.clip(((bys + 0.5) * ts / s).astype(int), 0, hl - 1)
            bmask[bby, bbx] = True
            bdist = self._dist_lo(bmask, int(math.ceil(ts * 0.9 / s)))
            carve = bdist <= (ts * 0.5 / s)              # disco tondo attorno al cespuglio
            disc[carve] = 0.0; core[carve] = False; allowed[carve] = False
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

    # --- CESPUGLI: massa compatta di erba alta (stile MOBA) ------------------
    def _bush_solid(self, grid):
        """Silhouette (H,W) bool dei CESPUGLI, stessa tecnica di _jungle_solid:
        maschera tile -> dischi sui centri -> blur -> soglia + rumore, clamp
        ~mezzo tile. Tile isolati -> blob tondi; vicini fusi (area organica)."""
        ts = self.tile_size
        Wt, Ht = grid.width, grid.height
        W, H = Wt * ts, Ht * ts
        tiles = grid.tiles
        tm = np.zeros((Ht, Wt), bool)
        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                if row[tx] == TILE_BUSH:
                    tm[ty, tx] = True
        if not tm.any():
            return None
        s = max(2, ts // 4)
        hl = (H + s - 1) // s; wl = (W + s - 1) // s
        ys, xs = np.where(tm)
        cmask = np.zeros((hl, wl), bool)
        ccx = np.clip(((xs + 0.5) * ts / s).astype(int), 0, wl - 1)
        ccy = np.clip(((ys + 0.5) * ts / s).astype(int), 0, hl - 1)
        cmask[ccy, ccx] = True
        dist = self._dist_lo(cmask, int(math.ceil(ts * 1.2 / s)))
        disc = (dist <= (ts * 0.72 / s)).astype(np.float32)
        core = dist <= (ts * 0.46 / s)
        allowed = dist <= (ts * 0.95 / s)
        bf = self._sep_blur(disc, max(1, int(ts * 0.5 / s)), passes=3)
        bf_full = self._upscale(bf, W, H, s)
        core_full = core[np.minimum(np.arange(H) // s, hl - 1)][:, np.minimum(np.arange(W) // s, wl - 1)]
        allow_full = allowed[np.minimum(np.arange(H) // s, hl - 1)][:, np.minimum(np.arange(W) // s, wl - 1)]
        solid = np.zeros((H, W), bool)
        TXf = (np.arange(W, dtype=np.float32) / ts)[None, :]
        STRIP = 300
        for y0 in range(0, H, STRIP):
            y1 = min(H, y0 + STRIP)
            TYf = (np.arange(y0, y1, dtype=np.float32) / ts)[:, None]
            nz = _np_vnoise(TXf / 1.2 + 5.0, TYf / 1.2 + 9.0) - 0.5
            b = bf_full[y0:y1]
            thr = np.where(b >= 0.78, True,
                           np.where(b <= 0.20, False, (b + nz * 0.40) > 0.5))
            solid[y0:y1] = (thr | core_full[y0:y1]) & allow_full[y0:y1]
        return solid

    # --- FIUME: acqua a livello mappa (silhouette smussata + profondita +
    #     riva + ninfee/sassi + schiuma animata) -------------------------------
    def _water_solid(self, grid):
        """Silhouette (H,W) bool del FIUME (TILE_RIVER), stessa tecnica di
        _jungle_solid/_bush_solid: maschera tile -> dischi sui centri -> blur ->
        soglia + rumore SOLO al bordo, clamp ~mezzo tile. Smussa le rive (bordi
        curvi: autotiling implicito, niente scaletta per-tile)."""
        ts = self.tile_size
        Wt, Ht = grid.width, grid.height
        W, H = Wt * ts, Ht * ts
        tiles = grid.tiles
        tm = np.zeros((Ht, Wt), bool)
        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                if row[tx] == TILE_RIVER:
                    tm[ty, tx] = True
        if not tm.any():
            return None
        s = max(2, ts // 4)
        hl = (H + s - 1) // s; wl = (W + s - 1) // s
        ys, xs = np.where(tm)
        cmask = np.zeros((hl, wl), bool)
        ccx = np.clip(((xs + 0.5) * ts / s).astype(int), 0, wl - 1)
        ccy = np.clip(((ys + 0.5) * ts / s).astype(int), 0, hl - 1)
        cmask[ccy, ccx] = True
        dist = self._dist_lo(cmask, int(math.ceil(ts * 1.2 / s)))
        disc = (dist <= (ts * 0.74 / s)).astype(np.float32)
        core = dist <= (ts * 0.44 / s)
        allowed = dist <= (ts * 1.0 / s)
        bf = self._sep_blur(disc, max(1, int(ts * 0.5 / s)), passes=3)
        bf_full = self._upscale(bf, W, H, s)
        core_full = core[np.minimum(np.arange(H) // s, hl - 1)][:, np.minimum(np.arange(W) // s, wl - 1)]
        allow_full = allowed[np.minimum(np.arange(H) // s, hl - 1)][:, np.minimum(np.arange(W) // s, wl - 1)]
        solid = np.zeros((H, W), bool)
        TXf = (np.arange(W, dtype=np.float32) / ts)[None, :]
        STRIP = 300
        for y0 in range(0, H, STRIP):
            y1 = min(H, y0 + STRIP)
            TYf = (np.arange(y0, y1, dtype=np.float32) / ts)[:, None]
            nz = _np_vnoise(TXf / 1.3 + 2.0, TYf / 1.3 + 4.0) - 0.5
            b = bf_full[y0:y1]
            thr = np.where(b >= 0.80, True,
                           np.where(b <= 0.22, False, (b + nz * 0.30) > 0.5))
            solid[y0:y1] = (thr | core_full[y0:y1]) & allow_full[y0:y1]
        return solid

    def _build_river(self, grid, decor) -> None:
        """Rende il fiume nel layer decor: corpo d'acqua con gradiente di
        PROFONDITA (centro scuro, bordi chiari) e increspature di corrente, riva
        sfumata (fango bagnato + canne), ninfee e sassi affioranti; la schiuma
        animata finisce in self._foam (blittata in draw)."""
        ts = self.tile_size; top = self._top
        Wt, Ht = grid.width, grid.height
        W, H = Wt * ts, Ht * ts
        solid = self._water_solid(grid)
        if solid is None:
            return
        s = max(2, ts // 4)
        hl = (H + s - 1) // s; wl = (W + s - 1) // s
        syc = np.minimum(np.arange(hl) * s, H - 1)
        sxc = np.minimum(np.arange(wl) * s, W - 1)
        wlo = solid[syc][:, sxc]                       # acqua a bassa risoluzione
        # Profondita = distanza dall'acqua alla TERRA (cresce verso il centro);
        # riva = distanza dalla terra all'ACQUA (cresce allontanandosi dal bordo).
        depth = self._dist_lo(~wlo, int(math.ceil(ts * 1.7 / s)))
        sdist = self._dist_lo(wlo, int(math.ceil(ts * 1.2 / s)))
        depth_full = self._upscale(depth, W, H, s) * s     # distanza in pixel
        sdist_full = self._upscale(sdist, W, H, s) * s
        # --- Corpo d'acqua + riva in un unico array RGBA (H,W), a strisce ------
        rgb = np.zeros((H, W, 3), np.uint8)
        alpha = np.zeros((H, W), np.uint8)
        STRIP = 300
        for y0 in range(0, H, STRIP):
            y1 = min(H, y0 + STRIP)
            inw = solid[y0:y1]
            WX = np.arange(W, dtype=np.float32)[None, :]
            WY = np.arange(y0, y1, dtype=np.float32)[:, None]
            dn = np.clip(depth_full[y0:y1] / (ts * 1.3), 0.0, 1.0)   # 0 riva ..1 centro
            t2 = dn * 2.0
            lo = dn < 0.5

            def mix(a, b, c):   # EDGE->MID (bordo) poi MID->DEEP (centro)
                return np.where(lo, a + (b - a) * t2, b + (c - b) * np.clip(t2 - 1.0, 0.0, 1.0))
            r = mix(RIV_EDGE[0], RIV_MID[0], RIV_DEEP[0])
            g = mix(RIV_EDGE[1], RIV_MID[1], RIV_DEEP[1])
            bch = mix(RIV_EDGE[2], RIV_MID[2], RIV_DEEP[2])
            # Increspature di corrente: SOTTILI linee diagonali ondulate (cresta
            # di un seno deformato da rumore) -> senso di flusso, non grandi
            # riflessi. Presenti a mezza/alta profondita, assenti sul bordo.
            wob = _np_vnoise(WX / (ts * 1.3) + 3.0, WY / (ts * 1.3) + 6.0)
            rip = np.sin((WX * 0.8 - WY * 1.4) / (ts * 0.5) + wob * 4.0)
            streak = (np.clip(rip, 0.0, 1.0) ** 3
                      * np.clip((dn - 0.12) / 0.3, 0.0, 1.0) * 0.30)
            r += (RIV_FLOW[0] - r) * streak
            g += (RIV_FLOW[1] - g) * streak
            bch += (RIV_FLOW[2] - bch) * streak
            wa = np.clip(depth_full[y0:y1] / 6.0, 0.0, 1.0) * 255.0   # sfuma la riva
            # Riva (lato terra): fango bagnato che sfuma sull'erba.
            sd = sdist_full[y0:y1]
            band = np.clip(1.0 - sd / (ts * 0.7), 0.0, 1.0) * (~inw)
            sw = np.clip(sd / (ts * 0.35), 0.0, 1.0)
            scr = SHORE_WET2[0] + (SHORE_MUD2[0] - SHORE_WET2[0]) * sw
            scg = SHORE_WET2[1] + (SHORE_MUD2[1] - SHORE_WET2[1]) * sw
            scb = SHORE_WET2[2] + (SHORE_MUD2[2] - SHORE_WET2[2]) * sw
            salp = (band ** 1.3) * 150.0
            rgb[y0:y1, :, 0] = np.clip(np.where(inw, r, scr), 0, 255).astype(np.uint8)
            rgb[y0:y1, :, 1] = np.clip(np.where(inw, g, scg), 0, 255).astype(np.uint8)
            rgb[y0:y1, :, 2] = np.clip(np.where(inw, bch, scb), 0, 255).astype(np.uint8)
            alpha[y0:y1] = np.clip(np.where(inw, wa, salp), 0, 255).astype(np.uint8)
        self._blit_blocks(decor, rgb, alpha, top)
        del rgb, alpha
        # --- Ninfee, sassi, canne: sprite vettoriali distribuiti irregolari ----
        deco = pygame.Surface((W, H), pygame.SRCALPHA)
        self._scatter_river(deco, solid, depth_full, sdist_full)
        for by in range(0, H, CHUNK):
            bh = min(CHUNK, H - by)
            for bx in range(0, W, CHUNK):
                bw = min(CHUNK, W - bx)
                sub = deco.subsurface(pygame.Rect(bx, by, bw, bh))
                if sub.get_bounding_rect(min_alpha=1).width > 0:
                    decor.blit(sub.copy(), (bx, by + top))
        # --- Schiuma animata (fotogrammi pre-renderizzati) ---------------------
        self._foam = self._build_foam(solid)

    def _scatter_river(self, deco, solid, depth_full, sdist_full) -> None:
        """Distribuisce in modo IRREGOLARE gli ornamenti del fiume: CANNE fitte
        nell'acqua bassa e sulla riva (griglia fine), NINFEE e SASSI RADI
        sull'acqua aperta (griglia larga: pochi, 'qualche'), con seme per punto +
        jitter -> niente pattern allineato."""
        ts = self.tile_size
        H, W = solid.shape
        ys, xs = np.where(solid)
        if not len(xs):
            return
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        p = self.painter
        # --- CANNE: griglia FINE lungo il bordo (acqua bassa + riva) ----------
        gap = max(6, int(ts * 0.75))
        for gy in range(y0, y1 + 1, gap):
            for gx in range(x0, x1 + 1, gap):
                rng = random.Random(((gx * 73856093) ^ (gy * 19349663) ^ 0x5EED) & 0xFFFFFFFF)
                x = gx + rng.randint(-gap // 2, gap // 2)
                y = gy + rng.randint(-gap // 2, gap // 2)
                if not (0 <= x < W and 0 <= y < H):
                    continue
                dp = float(depth_full[y, x]); sd = float(sdist_full[y, x])
                if solid[y, x]:
                    if 2.0 < dp <= ts * 0.5 and rng.random() < 0.42:
                        self._draw_reeds(deco, x, y, rng)
                elif sd < ts * 0.26 and rng.random() < 0.32:
                    self._draw_reeds(deco, x, y, rng)
        # --- NINFEE e SASSI: griglia LARGA -> radi (qualche elemento) ---------
        fgap = max(10, int(ts * 2.3))
        for gy in range(y0, y1 + 1, fgap):
            for gx in range(x0, x1 + 1, fgap):
                rng = random.Random(((gx * 2654435761) ^ (gy * 40503)) & 0xFFFFFFFF)
                x = gx + rng.randint(-fgap // 2, fgap // 2)
                y = gy + rng.randint(-fgap // 2, fgap // 2)
                if not (0 <= x < W and 0 <= y < H) or not solid[y, x]:
                    continue
                dp = float(depth_full[y, x])
                k = rng.random()
                if dp > ts * 0.55 and k < 0.38:
                    self._draw_lily(deco, x, y, rng)
                elif dp > ts * 0.4 and k < 0.62:
                    self._draw_rock(deco, x, y, rng, p)

    def _draw_reeds(self, deco, x, y, rng) -> None:
        """Ciuffo di canne: pochi steli sottili che salgono dalla base, contorno
        scuro + corpo verde + punta illuminata, leggermente inclinati verso la
        luce (alto-sinistra)."""
        H = deco.get_height()
        for _ in range(rng.randint(3, 6)):
            bx = x + rng.randint(-3, 3)
            hgt = rng.randint(5, 11)
            tipx = bx + rng.randint(-2, 1)           # inclina verso sinistra
            tipy = y - hgt
            pygame.draw.line(deco, (*REED_DK, 220), (bx, y), (tipx, tipy), 2)
            pygame.draw.line(deco, (*REED_MD, 235), (bx, y), (tipx, tipy), 1)
            if 0 <= tipx < deco.get_width() and 0 <= tipy < H:
                deco.set_at((tipx, tipy), (*REED_TIP, 255))

    def _draw_lily(self, deco, x, y, rng) -> None:
        """Foglia di ninfea: ellisse con bordo scuro, colpo di luce alto-sinistra,
        una tacca; raramente un fiorellino."""
        rw = rng.randint(3, 5); rh = rng.randint(2, 4)
        pygame.draw.ellipse(deco, (*LILY_PAD, 235), pygame.Rect(x - rw, y - rh, rw * 2, rh * 2))
        pygame.draw.ellipse(deco, (*LILY_RIM, 235), pygame.Rect(x - rw, y - rh, rw * 2, rh * 2), 1)
        pygame.draw.ellipse(deco, (*LILY_HI, 170), pygame.Rect(x - rw, y - rh, rw, rh))
        pygame.draw.line(deco, (*LILY_RIM, 235), (x, y), (x + rw, y + rh), 1)   # tacca
        if rng.random() < 0.22:
            pygame.draw.circle(deco, (*LILY_FLOWER, 255),
                               (x - rng.randint(0, 2), y - rng.randint(0, 2)), 2)

    def _draw_rock(self, deco, x, y, rng, p) -> None:
        """Sasso affiorante: masso tondo (riuso di Renderer._round_rock, luce
        alto-sinistra) con un anello di schiuma attorno alla base sull'acqua."""
        r = rng.randint(3, 5)
        pygame.draw.circle(deco, (*FOAM_COL, 55), (x, y + 1), r + 2, 1)   # anello tenue
        p._round_rock(deco, x, y, r, rng, ROCK_BASE, ROCK_HI, ROCK_SH)

    def _build_foam(self, solid):
        """Fotogrammi pre-renderizzati della schiuma: sottile linea chiara lungo
        il bordo INTERNO dell'acqua (anello ~2px), spezzata in trattini che
        SCORRONO tra un fotogramma e l'altro. Sprite piccoli per cella (memoria):
        in draw() si blitta solo il fotogramma corrente delle celle visibili."""
        import pygame.surfarray as sa
        ts = self.tile_size; top = self._top
        H, W = solid.shape

        def erode(m):
            o = m.copy()
            o[1:, :] &= m[:-1, :]; o[:-1, :] &= m[1:, :]
            o[:, 1:] &= m[:, :-1]; o[:, :-1] &= m[:, 1:]
            o[0, :] = False; o[-1, :] = False; o[:, 0] = False; o[:, -1] = False
            return o
        er = solid
        for _ in range(2):
            er = erode(er)
        band = solid & ~er                       # anello ~2px dentro il bordo
        if not band.any():
            return []
        foam = []
        for cy0 in range(0, H, FCELL):
            cy1 = min(H, cy0 + FCELL)
            for cx0 in range(0, W, FCELL):
                cx1 = min(W, cx0 + FCELL)
                sub = band[cy0:cy1, cx0:cx1]
                if not sub.any():
                    continue
                yy, xx = np.where(sub)
                ry0, ry1 = int(yy.min()), int(yy.max()) + 1
                rx0, rx1 = int(xx.min()), int(xx.max()) + 1
                bsub = sub[ry0:ry1, rx0:rx1]
                ah, aw = bsub.shape
                WX = (cx0 + rx0 + np.arange(aw, dtype=np.float32))[None, :]
                WY = (cy0 + ry0 + np.arange(ah, dtype=np.float32))[:, None]
                frames = []
                for f in range(FOAM_FRAMES):
                    ph = f * (2.0 / FOAM_FRAMES)
                    nz = _np_vnoise(WX / (ts * 0.45) + ph, WY / (ts * 0.45) + ph * 0.3)
                    a = (np.where(nz > 0.58, 150.0, 0.0) + 85.0) * bsub   # base + trattini
                    surf = pygame.Surface((aw, ah), pygame.SRCALPHA)
                    v3 = sa.pixels3d(surf)
                    v3[:, :, 0] = FOAM_COL[0]; v3[:, :, 1] = FOAM_COL[1]; v3[:, :, 2] = FOAM_COL[2]
                    del v3
                    va = sa.pixels_alpha(surf)
                    va[:] = np.clip(a, 0, 255).astype(np.uint8).T
                    del va
                    frames.append(surf)
                foam.append((cx0 + rx0, cy0 + ry0 + top, frames))
        return foam

    def _grass_tuft(self, tier, variant):
        """Sprite (cache) di un CIUFFO corto: 2-3 lame a punta col contorno scuro,
        corpo del tono `tier` e cappello piu' chiaro in cima; qualche punta GB_TIP.
        Piccolo (~11x12) e fitto: tante file sovrapposte leggono come MASSA, non
        come fili isolati. `tier`: 0 scuro, 1 medio, 2 chiaro."""
        key = (tier, variant)
        sp = self._grass_cache.get(key)
        if sp is not None:
            return sp
        body = (GB_DARK, GB_MID, GB_LIGHT)[tier]
        cap = (GB_MID, GB_LIGHT, GB_TIP)[tier]
        w, h = 11, 12
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        rng = random.Random((tier * 2654435761 ^ variant * 40503 ^ 0x7E) & 0xFFFFFFFF)
        bx = w // 2
        nb = 2 + (variant & 1)                     # 2-3 lame
        for i in range(nb):
            frac = (i - (nb - 1) / 2.0)
            cx = bx + int(round(frac * 2.4)) + rng.randint(-1, 1)
            bh = rng.randint(6, h - 1)
            lean = int(round(frac * 1.6))
            tipx = cx + lean
            tipy = h - 1 - bh
            pygame.draw.polygon(s, GB_OUT, ((cx - 2, h - 1), (cx + 2, h - 1), (tipx, tipy - 1)))
            pygame.draw.polygon(s, body, ((cx - 1, h - 1), (cx + 1, h - 1), (tipx, tipy + 1)))
            pygame.draw.line(s, cap, (tipx, tipy + 1), (tipx, tipy + max(1, bh // 3)))
            if tier == 2 and (variant & 2) and 0 <= tipx < w and 0 <= tipy < h:
                s.set_at((tipx, max(0, tipy)), GB_TIP)
        self._grass_cache[key] = s
        return s

    def _build_bushes(self, grid, walls, shadows, solid) -> None:
        """Riempie la silhouette con una MASSA compatta di erba alta:
          1) ombra morbida a terra (proiettata a sud-est);
          2) FRONTE: sotto il bordo inferiore, una fascia di fili piu' lunghi e
             SCURI che scende oltre il contorno -> altezza come la parete dei muri;
          3) FONDO pieno scuro (GB_FILL) sulla sagoma+fronte: niente terreno dentro,
             con contorno scuro (GB_OUT) tutt'intorno;
          4) SUPERFICIE: file di ciuffi ogni ~5px, sfalsate, dal fondo al davanti,
             piu' chiare verso l'alto e verso sinistra (luce alto-sx), punte chiare
             sparse."""
        ts = self.tile_size; top = self._top
        H, W = solid.shape
        s = max(2, ts // 4)
        hl = (H + s - 1) // s; wl = (W + s - 1) // s

        # (1) ombra morbida a terra (sagoma spostata a sud-est, corta e sfumata)
        sly = np.minimum(np.arange(hl) * s, H - 1); slx = np.minimum(np.arange(wl) * s, W - 1)
        sm = solid[sly][:, slx]
        L = max(2, int(ts * 0.5 / s))
        acc = np.zeros((hl, wl), np.float32)
        for k in range(1, L + 1):
            sh = np.zeros((hl, wl), bool)
            sh[k:, k:] = sm[:hl - k, :wl - k]
            np.maximum(acc, np.where(sh, 1.0 - (k - 1) / float(L + 1), 0.0), out=acc)
        acc[sm] = 0.0
        acc = self._sep_blur(acc, 1, passes=2)
        alpha_sh = np.clip(self._upscale(acc * 90.0, W, H, s), 0, 255).astype(np.uint8)
        self._blit_blocks(shadows, (0, 0, 0), alpha_sh, top)

        # (2) FRONTE: per ogni colonna, sotto il bordo inferiore della sagoma,
        #     aggiungo una fascia (skirt) di altezza variabile -> parete frontale.
        anyc = solid.any(axis=0)
        bottom = np.full(W, -1, np.int64)
        ys_idx = np.arange(H)[:, None]
        bottom[anyc] = (ys_idx * solid[:, anyc]).max(axis=0)
        skirt = np.zeros((H, W), bool)
        xs_all = np.where(anyc)[0]
        sk_noise = _np_vnoise((xs_all / 2.3 + 3.0).astype(np.float32),
                              np.full(xs_all.shape, 1.5, np.float32))
        sklen = (ts * 0.22 + ts * 0.3 * sk_noise).astype(np.int64)   # ~0.2..0.5 tile
        for j, x in enumerate(xs_all):
            by = bottom[x]
            if by < 0:
                continue
            y1 = min(H, by + 1 + int(sklen[j]))
            skirt[by + 1:y1, x] = True
        fillmask = solid | skirt

        # (3) FONDO pieno + contorno. Gradiente lieve (piu' scuro in basso = ombra
        #     interna); lo skirt e' piu' scuro (fronte, come la parete dei muri).
        dil = fillmask.copy()
        dil[1:, :] |= fillmask[:-1, :]; dil[:-1, :] |= fillmask[1:, :]
        dil[:, 1:] |= fillmask[:, :-1]; dil[:, :-1] |= fillmask[:, 1:]
        outline = dil & ~fillmask
        rgb = np.zeros((H, W, 3), np.uint8)
        fillc = np.array(GB_FILL, np.float32); darkc = np.array(GB_OUT, np.float32)
        gy = (np.arange(H, dtype=np.float32) / max(1, H - 1))[:, None]
        for c in range(3):
            base = fillc[c] + (darkc[c] - fillc[c]) * (0.12 + 0.20 * gy)
            rgb[:, :, c] = np.clip(base, 0, 255).astype(np.uint8)
        for c in range(3):
            ch = rgb[:, :, c]
            ch[skirt] = (ch[skirt].astype(np.float32) * 0.72).astype(np.uint8)
        ocol = np.array(GB_OUT, np.uint8)
        for c in range(3):
            rgb[:, :, c][outline] = ocol[c]
        alpha = np.where(fillmask | outline, np.uint8(255), np.uint8(0))
        self._blit_blocks(walls, rgb, alpha, top)

        # (4) SUPERFICIE: file di ciuffi sfalsate, dal fondo (y piccola) al davanti.
        #     Scansione per RIGA vettoriale (solo le celle della sagoma), seme da
        #     hash deterministico -> veloce anche su tutta la mappa.
        ys, xs = np.where(solid)
        y0, y1 = int(ys.min()), int(ys.max()); x0, x1 = int(xs.min()), int(xs.max())
        dy = max(1.0, y1 - y0); dx = max(1.0, x1 - x0)
        row_step = 5; col_step = 6
        for ry, y in enumerate(range(y0, y1 + 1, row_step)):
            xoff = (ry % 2) * (col_step // 2)
            xs_row = np.arange(x0 + xoff, x1 + 1, col_step)
            if xs_row.size == 0:
                continue
            xs_sel = xs_row[solid[y, xs_row]]            # solo celle di erba
            vf = 1.0 - (y - y0) / dy                     # 1 in cima
            for xi in xs_sel:
                xx = int(xi)
                h = ((xx * 2654435761) ^ (y * 40503)) & 0xFFFFFF
                hf = 1.0 - (xx - x0) / dx                # 1 a sinistra
                score = 0.55 * vf + 0.25 * hf + 0.20 * ((h & 0xFF) / 255.0)
                tier = 2 if score > 0.70 else 1 if score > 0.40 else 0
                variant = (h >> 8) & 3
                xj = xx + ((h >> 10) & 1) - ((h >> 11) & 1)   # jitter -1..1
                sp = self._grass_tuft(tier, variant)
                walls.blit(sp, (xj - sp.get_width() // 2, y - sp.get_height() + 3 + top))

        # (5) FRONTE: fili piu' lunghi e SCURI che SCENDONO oltre il bordo
        #     inferiore (sopra lo skirt) -> l'area ha ALTEZZA come la parete dei
        #     muri. Serpeggiano un filo e si scuriscono verso la punta.
        frng = random.Random((W * 2654435761 ^ H * 2246822519 ^ 0xF7) & 0xFFFFFFFF)
        for j in range(0, len(xs_all), 3):
            x = int(xs_all[j]); by = int(bottom[x])
            if by < 0:
                continue
            ln = int(sklen[j]) + 2
            cxf = float(x)
            for i in range(ln):
                yy = by + 1 + i
                if yy >= H:
                    break
                cxf += frng.uniform(-0.5, 0.5)
                px = int(round(cxf))
                f = i / max(1, ln - 1)                 # 0 radice .. 1 punta
                col = GB_MID if f < 0.25 else GB_DARK if f < 0.7 else GB_OUT
                if 0 <= px < W:
                    walls.blit(self._px1(col), (px, yy + top))
                    if f > 0.3 and px + 1 < W:          # spessore 2px verso valle
                        walls.blit(self._px1(GB_OUT), (px + 1, yy + top))

    def _px1(self, col):
        """1 pixel colorato in cache (per i fili del fronte)."""
        s = self._grass_cache.get(("px", col))
        if s is None:
            s = pygame.Surface((1, 1), pygame.SRCALPHA)
            s.set_at((0, 0), col)
            self._grass_cache[("px", col)] = s
        return s

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
        # Ombra LUNGA verso sud-est (muri piu alti -> ombra piu estesa): ~1.3 tile.
        L = max(3, int(ts * 1.3 / s))
        acc = np.zeros((hl, wl), np.float32)
        for k in range(1, L + 1):
            dy = k; dx = int(round(k * 0.7))
            sh = np.zeros((hl, wl), bool)
            sh[dy:, dx:] = sm[:hl - dy, :wl - dx]
            a = 1.0 - (k - 1) / float(L + 1)              # scema con la distanza
            np.maximum(acc, np.where(sh, np.float32(a), 0.0), out=acc)
        acc[sm] = 0.0                                     # niente ombra sotto il muro
        alpha = np.clip(self._upscale(acc * 105.0, W, H, s), 0, 255).astype(np.uint8)
        self._blit_blocks(shadows, (0, 0, 0), alpha, top)

    def _jungle_components(self, grid):
        """Etichette delle componenti connesse (8-vicini) dei tile muro-giungla:
        array (Ht,Wt) int, 0 = nessun muro. Ogni "muro" (massa connessa) ha un id
        -> da esso si deriva un SEED per variare forma/dimensione delle chiome."""
        Wt, Ht = grid.width, grid.height
        tiles = grid.tiles
        lab = np.zeros((Ht, Wt), np.int32)
        cur = 0
        walltypes = (TILE_JUNGLE_WALL, TILE_WALL)
        for y in range(Ht):
            for x in range(Wt):
                if tiles[y][x] in walltypes and lab[y, x] == 0:
                    cur += 1
                    dq = deque([(x, y)]); lab[y, x] = cur
                    while dq:
                        cx, cy = dq.popleft()
                        for oy in (-1, 0, 1):
                            for ox in (-1, 0, 1):
                                nx, ny = cx + ox, cy + oy
                                if (0 <= nx < Wt and 0 <= ny < Ht
                                        and tiles[ny][nx] in walltypes
                                        and lab[ny, nx] == 0):
                                    lab[ny, nx] = cur; dq.append((nx, ny))
        return lab

    @staticmethod
    def _draw_tree(surf, cx, cy, R, rng, pal) -> None:
        """Un ALBERO con VOLUME: 3-4 ciuffi interni, ognuno un piccolo RILIEVO a
        bande (base/ombra -> corpo -> cappello di luce verso alto-sinistra), non
        un disco piatto con un punto. I ciuffi in basso-destra usano toni piu
        scuri, quelli in alto-sinistra piu chiari -> l'albero intero legge come
        una cupola. `pal` = (SH, DK, MD, LT, HI, RF)."""
        SH, DK, MD, LT, HI, RF = pal
        R = max(3, int(R))
        k = rng.randint(3, 4)
        tufts = [(0.0, R * 0.05, R * 0.62)]              # corpo centrale
        for i in range(k):
            a = (i + rng.uniform(-0.28, 0.28)) / k * math.tau
            rad = R * 0.4
            tufts.append((math.cos(a) * rad, math.sin(a) * rad * 0.92,
                          R * (0.46 + rng.random() * 0.14)))
        tufts.sort(key=lambda t: (t[0] + t[1]), reverse=True)   # BR dietro, TL davanti
        for ox, oy, tr in tufts:
            tr = int(tr); x = int(cx + ox); y = int(cy + oy)
            li = -(ox + oy) / (R * 0.9)                  # -1 basso-dx .. +1 alto-sx
            if li < -0.18:   c0, c1, c2 = SH, DK, MD     # ciuffo in ombra
            elif li < 0.4:   c0, c1, c2 = DK, MD, LT     # corpo
            else:            c0, c1, c2 = MD, LT, HI      # ciuffo illuminato
            pygame.draw.circle(surf, c0, (x, y), tr)                        # base/ombra
            pygame.draw.circle(surf, c1, (x - int(tr * 0.22), y - int(tr * 0.22)), int(tr * 0.74))
            pygame.draw.circle(surf, c2, (x - int(tr * 0.4), y - int(tr * 0.4)), int(tr * 0.42))
            if c2 is HI:                                  # riflesso in alto-sinistra
                pygame.draw.circle(surf, RF, (x - int(tr * 0.5), y - int(tr * 0.5)), max(1, int(tr * 0.2)))

    def _tree_sprite(self, Rq, variant, pal, palid):
        """Sprite di un albero (cache): forma/volume dipendono solo da raggio
        quantizzato + variante + palette, non dalla posizione (la luce e' sempre
        da alto-sinistra). Cosi si DISEGNA l'albero poche decine di volte e poi si
        BLITTA a migliaia -> build molto piu veloce del draw per-pixel."""
        key = (Rq, variant, palid)
        s = self._tree_cache.get(key)
        if s is None:
            pad = 2
            D = 2 * Rq + 2 * pad
            s = pygame.Surface((D, D), pygame.SRCALPHA)
            rng = random.Random((variant * 2654435761 ^ palid * 40503 ^ Rq) & 0xFFFFFFFF)
            self._draw_tree(s, Rq + pad, Rq + pad, Rq, rng, pal)
            self._tree_cache[key] = s
        return s

    def _build_jungle_walls(self, grid, walls, canopy, p, solid) -> None:
        """Muri (giungla + confine) come RILIEVI pseudo-3D in stile LoL:
          - CIMA vegetata: chioma composta da ALBERI singoli di dimensioni diverse
            (grandi all'interno, piccoli sul bordo via distanza dal bordo), ognuno
            un gruppo di ciuffi a 3-4 toni (scuro basso-dx, chiaro+riflessi
            alto-sx); CONTORNO esterno scuro #12281A, mai verde chiaro;
          - PARETE frontale (sud): roccia ~1 tile con strati, crepe, muschio e
            RADICI che scendono dalla chioma, piu scura alla base;
          - le chiome del bordo SUD sporgono nel layer CANOPY (sopra le unita).
        Forma/dimensione variate da un SEED per muro (componente connessa)."""
        import pygame.surfarray as sa
        from game.renderer import (JW_CLIFF, JW_CLIFF_DK, JW_CLIFF_HI, JW_MOSS,
                                    JW_MOSS_DK, BUSH_SHADOW, BUSH_DARK, BUSH_MID,
                                    BUSH_LIGHT, BUSH_HILITE, BUSH_RIMLIGHT)
        ts = self.tile_size; top = self._top
        H, W = solid.shape
        RELIEF = max(self._H, int(ts * 1.12))   # parete frontale ~1 tile alta
        Hf = H + RELIEF
        comp = self._jungle_components(grid)     # etichette dei muri (per seed)
        up = np.zeros_like(solid); up[1:, :] = ~solid[:-1, :]; up[0, :] = True
        dn = np.zeros_like(solid); dn[:-1, :] = ~solid[1:, :]; dn[-1, :] = True
        lf = np.zeros_like(solid); lf[:, 1:] = ~solid[:, :-1]; lf[:, 0] = True
        rt = np.zeros_like(solid); rt[:, :-1] = ~solid[:, 1:]; rt[:, -1] = True
        boundary = solid & (up | dn | lf | rt)
        south = solid & dn
        tcx = np.clip(np.arange(W) // ts, 0, grid.width - 1)
        tcy = np.clip(np.arange(H) // ts, 0, grid.height - 1)
        comp_px = comp[tcy][:, tcx]                       # (H,W) label per pixel

        # Campo DISTANZA-DAL-BORDO (low-res): alberi grandi dentro, piccoli ai bordi.
        sdl = max(2, ts // 4)
        hl = (H + sdl - 1) // sdl; wl = (W + sdl - 1) // sdl
        sly = np.minimum(np.arange(hl) * sdl, H - 1)
        slx = np.minimum(np.arange(wl) * sdl, W - 1)
        sm_lo = solid[sly][:, slx]
        distlo = self._dist_lo(~sm_lo, int(math.ceil(2.6 * ts / sdl)))   # dist dal non-solido

        # --- (1) PARETE DI ROCCIA (cliff): sotto il bordo sud, segue la sagoma --
        cliff = np.zeros((Hf, W), bool)
        depth = np.zeros((Hf, W), np.int16)
        for k in range(1, RELIEF + 1):
            seg = cliff[k:H + k]
            newly = south & ~seg
            seg |= south
            depth[k:H + k][newly] = k
        solid_full = np.zeros((Hf, W), bool); solid_full[:H] = solid
        cliff &= ~solid_full
        CL = np.array(JW_CLIFF, np.float32)
        CLdk = np.array(JW_CLIFF_DK, np.float32)
        CLhi = np.array(JW_CLIFF_HI, np.float32)
        ms = pygame.Surface((W, Hf), pygame.SRCALPHA)
        c3 = sa.pixels3d(ms); ca = sa.pixels_alpha(ms)
        df = depth.astype(np.float32) / max(1, RELIEF)
        g = np.clip(df * 1.1, 0.0, 1.0)[..., None]
        clrgb = CLhi + (CL - CLhi) * g                   # spalla chiara -> pietra
        clrgb = clrgb + (CLdk - clrgb) * np.clip((df - 0.5) / 0.5, 0, 1)[..., None]  # base SCURA
        # DUE strati orizzontali tenui (sedimenti di roccia). Le crepe sono corte e
        # spezzate (sotto) -> strati+crepe leggono come roccia, non come steccato.
        s1 = RELIEF // 3; s2 = (2 * RELIEF) // 3
        band = ((depth == s1) | (depth == s2))[..., None]
        clrgb = clrgb * np.where(band, np.float32(0.84), np.float32(1.0))
        cmask3 = cliff[..., None]
        c3[:] = np.where(cmask3, clrgb, 0).astype(np.uint8).transpose(1, 0, 2)
        ca[:] = (cliff.T.astype(np.uint8) * 255)
        del c3, ca
        # Crepe corte spezzate, muschio sul bordo, e RADICI che scendono dalla
        # chioma (verde-brune, serpeggianti) lungo la parete.
        ys_c, xs_c = np.where(south)
        ROOT = (40, 44, 30); ROOT_D = (26, 30, 20)
        if len(xs_c):
            crng = random.Random(0xC1FF ^ (len(xs_c) & 0xFFFFFFFF))
            crack = tuple(int(v) for v in CLdk)
            for _ in range(min(3500, max(4, len(xs_c) // 13))):
                j = crng.randrange(len(xs_c))
                x = int(xs_c[j]); y0 = int(ys_c[j])
                k = crng.random()
                if k < 0.4:                               # crepa corta spezzata
                    yy = y0 + 1 + crng.randint(0, max(1, RELIEF // 2)); xx = x
                    for _s in range(crng.randint(2, max(3, RELIEF // 2))):
                        if 0 <= xx < W and 0 <= yy < Hf and cliff[yy, xx]:
                            ms.set_at((xx, yy), crack)
                        xx += crng.randint(-1, 1); yy += 1
                elif k < 0.7:                             # RADICE dalla chioma
                    yy = y0 + 1; xx = x
                    rc = ROOT if crng.random() < 0.6 else ROOT_D
                    for _s in range(crng.randint(RELIEF // 2, RELIEF)):
                        if 0 <= xx < W and 0 <= yy < Hf and cliff[yy, xx]:
                            ms.set_at((xx, yy), rc)
                        yy += 1
                        if crng.random() < 0.35:
                            xx += crng.randint(-1, 1)
                else:                                     # ciuffo di muschio sul bordo
                    mc = JW_MOSS if crng.random() < 0.55 else JW_MOSS_DK
                    pygame.draw.circle(ms, mc, (x, y0 + crng.randint(0, 2)),
                                       crng.randint(1, max(1, ts // 10)))
            ma = sa.pixels_alpha(ms)                      # ritaglia dettagli alla parete
            np.minimum(ma, cliff.T.astype(np.uint8) * 255, out=ma); del ma

        # --- (2) CIMA VEGETATA: ALBERI singoli, grandi dentro / piccoli al bordo -
        pal = (BUSH_SHADOW, BUSH_DARK, BUSH_MID, BUSH_LIGHT, BUSH_HILITE, BUSH_RIMLIGHT)
        fol = pygame.Surface((W, H), pygame.SRCALPHA)
        f3 = sa.pixels3d(fol); fa = sa.pixels_alpha(fol)
        # Base verde MEDIO-SCURO (#1F3B24 = BUSH_DARK), non quasi-nera: le fessure
        # tra le chiome restano verdi scure, non buchi neri (niente effetto pois).
        f3[solid.T] = np.array(BUSH_DARK, np.uint8); fa[solid.T] = 255
        del f3, fa
        sp = max(5, int(ts * 0.6))                        # passo fitto: alberi sovrapposti
        jcx = np.arange(0, W, sp); jcy = np.arange(0, H, sp)
        GY, GX = np.meshgrid(jcy, jcx, indexing="ij")     # nord->sud (ordine chiome)
        sel = solid[GY, GX]
        for gy, gx in zip(GY[sel].tolist(), GX[sel].tolist()):
            cid = int(comp_px[gy, gx])
            sseed = (cid * 2654435761) & 0xFFFFFFFF
            hh = ((gx * 374761393) ^ (gy * 668265263) ^ sseed) & 0xFFFFFFFF
            cx = int(min(W - 1, max(0, gx + (hh & 7) - 3)))
            cy = int(min(H - 1, max(0, gy + ((hh >> 3) & 7) - 3)))
            if not solid[cy, cx]:
                continue
            dtile = distlo[min(hl - 1, cy // sdl), min(wl - 1, cx // sdl)] * sdl / ts
            szf = 0.82 + 0.4 * (((sseed >> 10) & 0xFF) / 255.0)     # per muro
            R = ts * (0.40 + 0.34 * min(1.0, dtile / 2.2)) * szf    # grande dentro
            Rq = max(3, int(round(R / 2.0)) * 2)                    # quantizzato (cache)
            spr = self._tree_sprite(Rq, (hh >> 12) & 7, pal, 0)
            fol.blit(spr, (cx - Rq - 2, cy - Rq - 2))
        # Ritaglio alla sagoma + CONTORNO esterno scuro #12281A (tutto il bordo).
        fa = sa.pixels_alpha(fol)
        np.minimum(fa, solid.T.astype(np.uint8) * 255, out=fa); del fa
        f3 = sa.pixels3d(fol); fa = sa.pixels_alpha(fol)
        f3[boundary.T] = np.array(CANOPY_OUTLINE, np.uint8); fa[boundary.T] = 255
        del f3, fa
        ms.blit(fol, (0, 0))                              # cima sopra la parete

        # --- (3) blit LAZY per chunk nel layer walls (sotto le unita) ----------
        off_y = top - RELIEF                              # la cima e' estrusa su di RELIEF
        for by in range(0, Hf, CHUNK):
            bh = min(CHUNK, Hf - by)
            for bx in range(0, W, CHUNK):
                bw = min(CHUNK, W - bx)
                sub = ms.subsurface(pygame.Rect(bx, by, bw, bh))
                if sub.get_bounding_rect(min_alpha=1).width > 0:
                    walls.blit(sub.copy(), (bx, by + off_y))

        # --- (4) OVERHANG: chiome del bordo SUD che sporgono nel layer CANOPY,
        #     sopra le unita alla base del muro. Alberelli scuri (sotto-chioma in
        #     ombra) centrati alla BASE della parete, debordano un po' in basso.
        #     I centri stanno SOTTO la sagoma -> niente tagli orizzontali.
        pal_dk = (BUSH_SHADOW, BUSH_SHADOW, BUSH_DARK, BUSH_DARK, BUSH_MID, BUSH_MID)
        over = pygame.Surface((W, Hf), pygame.SRCALPHA)
        if len(xs_c):
            step_o = max(3, ts // 3)
            for j in range(0, len(xs_c), step_o):
                x = int(xs_c[j]); yb = int(ys_c[j])
                cid = int(comp_px[min(H - 1, yb), x])
                sseed = (cid * 2654435761) & 0xFFFFFFFF
                hh = ((x * 374761393) ^ (yb * 668265263) ^ sseed) & 0xFFFFFFFF
                szf = 0.7 + 0.5 * (((sseed >> 10) & 0xFF) / 255.0)
                R = ts * 0.3 * szf
                Rq = max(3, int(round(R / 2.0)) * 2)
                oy = yb + RELIEF - int(R * 0.4) + ((hh >> 7) & 3)  # alla base, deborda
                ox = x + ((hh >> 9) & 3) - 1
                spr = self._tree_sprite(Rq, (hh >> 12) & 7, pal_dk, 1)
                over.blit(spr, (ox - Rq - 2, oy - Rq - 2))
            for by in range(0, Hf, CHUNK):
                bh = min(CHUNK, Hf - by)
                for bx in range(0, W, CHUNK):
                    bw = min(CHUNK, W - bx)
                    sub = over.subsurface(pygame.Rect(bx, by, bw, bh))
                    if sub.get_bounding_rect(min_alpha=1).width > 0:
                        canopy.blit(sub.copy(), (bx, by + off_y))

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
        """Layer SOTTO le unita: ground, decor, ombre, muri/vegetazione base
        (l'erba alta e' dentro walls_base, disegnata prima dei muri)."""
        ox, oy = self._offset(camera)
        vw, vh = camera.view_w, camera.view_h
        self.layers["ground"].draw(screen, ox, oy, vw, vh)
        self.layers["ground_decor"].draw(screen, ox, oy, vw, vh)
        # Schiuma animata del fiume: SOPRA il corpo d'acqua, sotto le unita.
        self._draw_foam(screen, ox, oy, vw, vh)
        self.layers["shadows"].draw(screen, ox, oy, vw, vh)
        self.layers["walls_base"].draw(screen, ox, oy, vw, vh)

    def _draw_foam(self, screen, ox: int, oy: int, vw: int, vh: int) -> None:
        """Blitta il fotogramma corrente della schiuma per le celle visibili."""
        if not self._foam:
            return
        idx = (pygame.time.get_ticks() // FOAM_MS) % FOAM_FRAMES
        for ax, ay, frames in self._foam:
            sx = ax + ox; sy = ay + oy
            surf = frames[idx]
            w, h = surf.get_size()
            if sx + w <= 0 or sy + h <= 0 or sx >= vw or sy >= vh:
                continue
            screen.blit(surf, (sx, sy))

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
