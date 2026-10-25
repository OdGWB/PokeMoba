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

import pygame

import config
from engine.grid import (TILE_BUSH, TILE_FLOOR, TILE_JUNGLE_WALL, TILE_LANE,
                         TILE_WALL)

COL_GRID = (0, 0, 0)
COL_BG = (18, 20, 24)            # sfondo (riempie il bordo del layer opaco)
CHUNK = 1024                     # lato del chunk in pixel

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
        floor_img = self._build_floor(grid, p)
        self._scatter_detail(grid, floor_img, p, path_tiles)
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

        # --- Passata ombre: un muro proietta ombra a sud/est sul terreno ------
        def is_wall(x, y):
            return (0 <= x < Wt and 0 <= y < Ht
                    and tiles[y][x] in (TILE_WALL, TILE_JUNGLE_WALL))

        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                if row[tx] in TALL_TILES:
                    continue
                nw = ((1 if is_wall(tx, ty - 1) else 0)
                      | (2 if is_wall(tx - 1, ty) else 0))
                if nw:
                    shadows.blit(p._shadow_surf(nw), (tx * ts, ty * ts + top))

        # --- Passata 2: rilievi 2.5D (walls_base), dall'alto in basso ---------
        def is_jw(x, y):
            return 0 <= x < Wt and 0 <= y < Ht and tiles[y][x] == TILE_JUNGLE_WALL

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
                if t not in TALL_TILES:
                    continue
                ax = tx * ts
                ay = ty * ts - H + top
                if t == TILE_JUNGLE_WALL:
                    mask = ((1 if is_jw(tx, ty - 1) else 0)
                            | (2 if is_jw(tx + 1, ty) else 0)
                            | (4 if is_jw(tx, ty + 1) else 0)
                            | (8 if is_jw(tx - 1, ty) else 0))
                    variant = sym_seed(tx, ty, 31)
                    walls.blit(p._jwall_surf(mask, variant, H), (ax, ay))
                elif t == TILE_BUSH:
                    mask = ((1 if is_bush(tx, ty - 1) else 0)
                            | (2 if is_bush(tx + 1, ty) else 0)
                            | (4 if is_bush(tx, ty + 1) else 0)
                            | (8 if is_bush(tx - 1, ty) else 0))
                    variant = sym_seed(tx, ty, 15)
                    walls.blit(p._bush_surf(mask, variant, H), (ax, ay))
                else:
                    variant = (((tx * 73856093) ^ (ty * 19349663)) >> 6) & 7
                    walls.blit(p._tall_surf(t, variant, H), (ax, ay))

        self._grid = grid

    # --- Suolo organico (rumore per pixel in coord mondo) --------------------
    def _build_floor(self, grid, p) -> pygame.Surface:
        """Immagine del suolo di giungla a piena mappa: colore (verde + muschio +
        fango) calcolato a BASSA RISOLUZIONE in coordinate mondo e poi scalato
        con smoothscale. Così le chiazze sono organiche e attraversano i tile
        senza cuciture; la bassa risoluzione tiene il costo basso (una volta)."""
        ts = self.tile_size
        Wt, Ht = grid.width, grid.height
        k = 2                              # campioni per tile (poi smoothscale)
        sw, sh = Wt * k + 1, Ht * k + 1
        small = pygame.Surface((sw, sh))
        for sy in range(sh):
            ty = sy / k
            for sx in range(sw):
                small.set_at((sx, sy), p._floor_color(sx / k, ty))
        return pygame.transform.smoothscale(small, (Wt * ts, Ht * ts))

    def _scatter_detail(self, grid, floor_img, p, path_tiles) -> None:
        """Dettagli sul suolo (in coordinate MONDO, disegnati sull'immagine del
        suolo prima del blit): ciuffi d'erba sul verde (NON sui sentieri né sul
        fango nudo), fiocchi di muschio e granelli di fango dove le chiazze sono
        dense."""
        from game.renderer import (GRASS_TUFT_LIGHT, GRASS_TUFT_DARK,
                                    MOSS_FLECK_L, MOSS_FLECK_D, MUD_SPECK)
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
                mu = p._mud_at(tx + 0.5, ty + 0.5)
                mo = p._moss_at(tx + 0.5, ty + 0.5)
                on_path = (tx, ty) in path_tiles
                if not on_path and mu < 0.5:    # fili d'erba (non sul sentiero)
                    for _ in range(rng.randint(2, 4)):
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

    # --- Sentieri di terra battuta (strisce continue spline) -----------------
    def _compute_paths(self, grid):
        """BFS multi-sorgente dai tile-lane -> per ogni campo il percorso più
        corto alla lane (aggira i muri, evita l'acqua). Ritorna (routes,
        path_tiles): le rotte in tile e l'insieme dei tile coperti (centro + 1
        anello) per non disegnarci sopra i fili d'erba."""
        routes, path_tiles = [], set()
        if not self._camps:
            return routes, path_tiles
        Wt, Ht = grid.width, grid.height
        tiles = grid.tiles

        def walk(x, y):
            return (0 <= x < Wt and 0 <= y < Ht
                    and tiles[y][x] in (TILE_FLOOR, TILE_LANE, TILE_BUSH))

        parent = {}
        dq = deque()
        has_lane = False
        for y in range(Ht):
            row = tiles[y]
            for x in range(Wt):
                if row[x] == TILE_LANE:
                    has_lane = True
                    parent[(x, y)] = None
                    dq.append((x, y))
        if not has_lane:
            return routes, path_tiles
        NB = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
        while dq:
            cx, cy = dq.popleft()
            for dx, dy in NB:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in parent or not walk(nx, ny):
                    continue
                if dx and dy and not (walk(cx + dx, cy) and walk(cx, cy + dy)):
                    continue
                parent[(nx, ny)] = (cx, cy)
                dq.append((nx, ny))

        for camp_x, camp_y in self._camps:
            start = (int(camp_x), int(camp_y))
            if start not in parent:
                continue
            route, cur, guard = [], start, 0
            while cur is not None and guard < Wt * Ht:
                route.append(cur)
                cur = parent.get(cur)
                guard += 1
            if len(route) < 2:
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
        """Disegna ogni rotta come una STRISCIA continua di terra battuta: spline
        tra i punti, deformata con rumore; profilo sfumato (nucleo pieno + bordi
        trasparenti, largo 1-2 tile). La terra resta solo sui tile d'erba (i tile
        non-erba vengono ritagliati dalla striscia)."""
        if not routes:
            return
        from game.renderer import JUNGLE_DIRT, DIRT_DRY
        ts = self.tile_size
        top = self._top
        Wt, Ht = grid.width, grid.height
        tiles = grid.tiles
        # Profilo del pennello: (raggio in frazioni di tile, colore, alpha), dal
        # bordo morbido al nucleo secco. Disegnati dal largo al stretto: i cerchi
        # stretti (opachi) coprono il centro, quelli larghi restano ai bordi.
        prof = [(0.95, JUNGLE_DIRT, 55), (0.66, JUNGLE_DIRT, 140),
                (0.45, DIRT_DRY, 205), (0.28, DIRT_DRY, 240)]

        for route in routes:
            # Punti di controllo: centri tile, sottocampionati, + estremo lane.
            pts = [(tx * ts + ts / 2, ty * ts + ts / 2) for (tx, ty) in route]
            ctrl = pts[::2]
            if ctrl[-1] != pts[-1]:
                ctrl.append(pts[-1])
            curve = self._catmull(ctrl, 8)
            if len(curve) < 2:
                continue
            # Deformazione con rumore: sposta ogni punto in perpendicolare.
            amp = ts * 0.45
            samp = []
            for i, (x, y) in enumerate(curve):
                px, py = curve[max(0, i - 1)]
                nx, ny = curve[min(len(curve) - 1, i + 1)]
                tgx, tgy = nx - px, ny - py
                tl = math.hypot(tgx, tgy) or 1.0
                perp = (-tgy / tl, tgx / tl)
                d = (p._vnoise(x / 34.0, y / 34.0) - 0.5) * 2.0 * amp
                samp.append((x + perp[0] * d, y + perp[1] * d))
            # Bounding box + margine per il pennello.
            marg = int(ts * 1.1)
            xs = [q[0] for q in samp]; ys = [q[1] for q in samp]
            bx0 = max(0, int(min(xs)) - marg); by0 = max(0, int(min(ys)) - marg)
            bx1 = min(Wt * ts, int(max(xs)) + marg); by1 = min(Ht * ts, int(max(ys)) + marg)
            bw, bh = bx1 - bx0, by1 - by0
            if bw <= 0 or bh <= 0:
                continue
            ribbon = pygame.Surface((bw, bh), pygame.SRCALPHA)
            ph = (hash(route[0]) & 0xFFFF) / 0xFFFF * math.tau
            for frac, col, a in prof:
                rgba = (col[0], col[1], col[2], a)
                for i, (x, y) in enumerate(samp):
                    # Larghezza variabile lungo il percorso (1-2 tile).
                    wscale = 0.8 + 0.4 * (0.5 + 0.5 * math.sin(i * 0.12 + ph))
                    r = max(1, int(ts * frac * wscale))
                    pygame.draw.circle(ribbon, rgba, (int(x - bx0), int(y - by0)), r)
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

    # --- introspezione (per benchmark/report) -------------------------------
    def mem_report(self) -> dict:
        return {n: lyr.mem_bytes() for n, lyr in self.layers.items()}
