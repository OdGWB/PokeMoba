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

        # --- Passata 1: terreno piatto (ground) + rive/bordi/griglia (decor) --
        for ty in range(Ht):
            row = tiles[ty]
            for tx in range(Wt):
                ax = tx * ts
                ay = ty * ts + top
                t = row[tx]
                h = (tx * 73856093) ^ (ty * 19349663)
                g = TILE_FLOOR if t in TALL_TILES else t
                if g == TILE_FLOOR:
                    c00 = p._grass_corner(tx, ty)
                    c10 = p._grass_corner(tx + 1, ty)
                    c01 = p._grass_corner(tx, ty + 1)
                    c11 = p._grass_corner(tx + 1, ty + 1)
                    ground.blit(p._grass_surf(c00, c10, c01, c11), (ax, ay))
                else:
                    variant = (h >> 4) & 3
                    ground.blit(p._tile_surf(g, variant), (ax, ay))
                p._shore(decor, grid, tx, ty, ax, ay, g, t)
                if config.SHOW_GRID_LINES:
                    decor.blit(self._grid_line_sprite(), (ax, ay))

        # --- Sentieri di terra battuta: dai campi della giungla alle lane -----
        self._paint_paths(grid, decor, p)

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

    def _paint_paths(self, grid, decor, p) -> None:
        """Traccia sentieri di terra battuta che collegano ogni campo alla lane
        più vicina. Il percorso segue il terreno (aggira i muri, evita l'acqua),
        quindi è naturalmente irregolare; la terra si timbra solo sui tile
        d'erba, con pennelli morbidi sovrapposti (bordi sfumati, largo 1-2 tile).
        È puramente grafico: i tipi di tile non cambiano."""
        if not self._camps:
            return
        from collections import deque
        ts = self.tile_size
        top = self._top
        Wt, Ht = grid.width, grid.height
        tiles = grid.tiles

        def walk(x, y):
            # Terreno su cui un sentiero può correre: erba, lane (sorgenti),
            # cespugli. L'acqua e i muri NO -> la terra resta sulla terra.
            return (0 <= x < Wt and 0 <= y < Ht
                    and tiles[y][x] in (TILE_FLOOR, TILE_LANE, TILE_BUSH))

        # BFS multi-sorgente da TUTTI i tile-lane: per ogni tile raggiungibile
        # memorizza il passo verso la lane più vicina (gradiente di distanza).
        parent = {}
        dq = deque()
        has_lane = False
        for y in range(Ht):
            row = tiles[y]
            for x in range(Wt):
                if row[x] == TILE_LANE:
                    has_lane = True
                    parent[(x, y)] = None     # sorgente
                    dq.append((x, y))
        if not has_lane:
            return
        NB = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
        while dq:
            cx, cy = dq.popleft()
            for dx, dy in NB:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in parent or not walk(nx, ny):
                    continue
                if dx and dy:   # niente taglio d'angolo tra i muri
                    if not (walk(cx + dx, cy) and walk(cx, cy + dy)):
                        continue
                parent[(nx, ny)] = (cx, cy)
                dq.append((nx, ny))

        hashed = 0
        for ci, (camp_x, camp_y) in enumerate(self._camps):
            start = (int(camp_x), int(camp_y))
            if start not in parent:
                continue
            # Risali il gradiente fino a una lane: ecco il sentiero.
            route = []
            cur = start
            guard = 0
            while cur is not None and guard < Wt * Ht:
                route.append(cur)
                cur = parent.get(cur)
                guard += 1
            for tx, ty in route:
                if tiles[ty][tx] != TILE_FLOOR:
                    continue        # terra solo sull'erba (non su lane/cespuglio)
                h = ((tx * 73856093) ^ (ty * 19349663)) & 0x7FFFFFFF
                r = int(ts * (0.78 + 0.22 * ((h >> 3) & 1)))   # 0.78..1.0 tile
                variant = (h >> 5) & 7
                jx = ((h >> 8) & 3) - 1
                jy = ((h >> 10) & 3) - 1
                stamp = p._dirt_stamp(r, variant)
                cx = tx * ts + ts // 2 + jx
                cy = ty * ts + ts // 2 + top + jy
                decor.blit(stamp, (cx - r, cy - r))
                hashed += 1

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
