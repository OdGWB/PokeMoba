"""Editor di mappe a tile (pygame).

Carica un JSON di mappa (data/maps/*.json), lo fai modificare a mano con il
pennello e lo RISALVA nello stesso file. Pensato per rifinire la giungla:
disegni muri/cespugli/pozze, sposti i campi dei Pokémon minori, con mirror
automatico a 180° per tenere la mappa simmetrica.

Uso:
    python tools/map_editor.py                      # apre la 3v3
    python tools/map_editor.py data/maps/map_5v5.json
    python tools/map_editor.py --selftest           # test headless (no finestra)

Comandi (mostrati anche nel pannello a destra):
    Pennello tile:  0 Erba  1 Muro  2 Lane  3 Fiume  4 Cespuglio  5 MuroGiungla  6 Pozza
    Campi:          P = campo piccolo   G = campo grande (buff)   (click sx posa, click dx toglie)
    Meteo evoluto:  U = pozza grande (Pioggia)   V = varco del Vento   (click sx posa, dx toglie)
    Modo:           T = tile / C = campi / U = pozze / V = varchi (o scegli dalla palette)
    Mouse:          click sx dipinge/posa · click dx cancella (tile->erba, campi->rimuove)
    Mirror:         M attiva/disattiva lo specchio a 180°
    Pennello:       [ e ] cambiano la dimensione (tile)
    Vista:          frecce = scorri · rotella = zoom
    File:           S = salva   R = ricarica da file   ESC = esci
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FLOOR, WALL, LANE, RIVER, BUSH, JWALL, PUDDLE = 0, 1, 2, 3, 4, 5, 6
TILE_NAMES = {FLOOR: "Erba", WALL: "Muro", LANE: "Lane", RIVER: "Fiume",
              BUSH: "Cespuglio", JWALL: "Muro giungla", PUDDLE: "Pozza"}
TILE_COLORS = {
    FLOOR: (64, 104, 68), WALL: (60, 60, 68), LANE: (158, 140, 96),
    RIVER: (70, 118, 170), BUSH: (30, 70, 40), JWALL: (56, 66, 54),
    PUDDLE: (86, 150, 190),
}
PALETTE_ORDER = [FLOOR, WALL, LANE, RIVER, BUSH, JWALL, PUDDLE]


class MapModel:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.W = int(self.data["width"])
        self.H = int(self.data["height"])
        self.tiles = self.data["tiles"]
        self.camps = self.data.get("camps", [])
        self.structures = self.data.get("structures", [])
        self.dens = self.data.get("dens", {})
        self.spawns = self.data.get("spawns", {})
        self.puddle_spots = self.data.setdefault("puddle_spots", [])   # Pioggia
        self.wind_passages = self.data.setdefault("wind_passages", [])  # Vento

    # --- modifiche -----------------------------------------------------------
    def mirror(self, x, y):
        mx = min(self.W - 1, max(0, self.W - x))
        my = min(self.H - 1, max(0, self.H - y))
        return mx, my

    def in_bounds(self, x, y):
        return 0 <= x < self.W and 0 <= y < self.H

    def set_tile(self, x, y, v, mirror=False):
        if self.in_bounds(x, y):
            self.tiles[y][x] = v
        if mirror:
            mx, my = self.mirror(x, y)
            if self.in_bounds(mx, my):
                self.tiles[my][mx] = v

    def paint(self, cx, cy, radius, v, mirror=False):
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                    self.set_tile(x, y, v, mirror)

    def camp_at(self, x, y, r=3):
        best, bd = None, r * r + 1
        for c in self.camps:
            d = (c["pos"][0] - x) ** 2 + (c["pos"][1] - y) ** 2
            if d <= bd:
                best, bd = c, d
        return best

    def add_camp(self, x, y, kind, mirror=False):
        if not self.in_bounds(x, y) or self.camp_at(x, y, 2):
            pass
        else:
            self.camps.append({"pos": [x, y], "type": kind})
        if mirror:
            mx, my = self.mirror(x, y)
            if self.in_bounds(mx, my) and not self.camp_at(mx, my, 2):
                self.camps.append({"pos": [mx, my], "type": kind})

    def remove_camp(self, x, y, mirror=False):
        c = self.camp_at(x, y, 3)
        if c:
            self.camps.remove(c)
        if mirror:
            mx, my = self.mirror(x, y)
            c2 = self.camp_at(mx, my, 3)
            if c2 and c2 in self.camps:
                self.camps.remove(c2)

    # --- punti meteo (pozze grandi / varchi vento) ---------------------------
    @staticmethod
    def spot_at(lst, x, y, r=3):
        for s in lst:
            if (s["pos"][0] - x) ** 2 + (s["pos"][1] - y) ** 2 <= r * r:
                return s
        return None

    def add_spot(self, lst, x, y, rad, mirror=False):
        if self.in_bounds(x, y) and not self.spot_at(lst, x, y, 2):
            lst.append({"pos": [x, y], "r": rad})
        if mirror:
            mx, my = self.mirror(x, y)
            if self.in_bounds(mx, my) and not self.spot_at(lst, mx, my, 2):
                lst.append({"pos": [mx, my], "r": rad})

    def remove_spot(self, lst, x, y, mirror=False):
        s = self.spot_at(lst, x, y, 4)
        if s:
            lst.remove(s)
        if mirror:
            mx, my = self.mirror(x, y)
            s2 = self.spot_at(lst, mx, my, 4)
            if s2 and s2 in lst:
                lst.remove(s2)

    def save(self):
        # Le pozze della Pioggia ora sono dischi (puddle_spots); il reticolo
        # `puddles` resta solo come ripiego quando non ci sono dischi.
        if self.puddle_spots:
            puddles = self.data.get("puddles", [])
        else:
            puddles = [[x, y] for y in range(self.H) for x in range(self.W)
                       if self.tiles[y][x] == FLOOR and x % 3 == 1 and y % 3 == 1]
        self.data["puddle_spots"] = self.puddle_spots
        self.data["wind_passages"] = self.wind_passages
        self.data["tiles"] = self.tiles
        self.data["camps"] = self.camps
        self.data["puddles"] = puddles
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return len(self.camps), len(puddles)


# --------------------------------------------------------------------------- #
def run_selftest(path: Path):
    m = MapModel(path)
    before = sum(row.count(WALL) for row in m.tiles)
    m.paint(50, 50, 2, WALL, mirror=True)
    m.add_camp(40, 20, "big", mirror=True)
    m.remove_camp(40, 20, mirror=True)
    tmp = path.with_suffix(".selftest.json")
    m.path = tmp
    nc, npd = m.save()
    after = MapModel(tmp)
    ok = (sum(row.count(WALL) for row in after.tiles) >= before + 5)
    tmp.unlink(missing_ok=True)
    print(f"selftest: paint+mirror ok={ok}, camps={nc}, puddles={npd}")
    return 0 if ok else 1


def run_editor(path: Path):
    import pygame
    pygame.init()
    pygame.key.set_repeat(0)
    SW, SH = 1200, 820
    PANEL = 250
    screen = pygame.display.set_mode((SW, SH))
    pygame.display.set_caption(f"Map Editor — {path.name}")
    font = pygame.font.SysFont("consolas", 14)
    small = pygame.font.SysFont("consolas", 12)
    clock = pygame.time.Clock()

    m = MapModel(path)
    canvas_w = SW - PANEL
    zoom = max(3.0, min(canvas_w / m.W, SH / m.H))   # px per tile
    cam_x, cam_y = 0.0, 0.0                            # tile in alto-sx
    mode = "tile"           # "tile" | "camp"
    cur_tile = JWALL
    camp_kind = "small"
    brush = 1
    mirror = True
    status = "Pronto. S salva, R ricarica."

    def screen_to_tile(mx, my):
        return int(cam_x + mx / zoom), int(cam_y + my / zoom)

    def clamp_cam():
        nonlocal cam_x, cam_y
        vis_w = canvas_w / zoom
        vis_h = SH / zoom
        cam_x = max(0.0, min(m.W - vis_w, cam_x)) if m.W > vis_w else 0.0
        cam_y = max(0.0, min(m.H - vis_h, cam_y)) if m.H > vis_h else 0.0

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                if k == pygame.K_ESCAPE:
                    running = False
                elif k == pygame.K_s:
                    nc, npd = m.save()
                    status = f"Salvato: {m.path.name}  ({nc} campi, {npd} pozze)"
                elif k == pygame.K_r:
                    m = MapModel(path); status = "Ricaricato dal file."
                elif k == pygame.K_m:
                    mirror = not mirror; status = f"Mirror {'ON' if mirror else 'OFF'}"
                elif k == pygame.K_t:
                    mode = "tile"
                elif k == pygame.K_c:
                    mode = "camp"
                elif k == pygame.K_p:
                    mode = "camp"; camp_kind = "small"
                elif k == pygame.K_g:
                    mode = "camp"; camp_kind = "big"
                elif k == pygame.K_u:
                    mode = "puddle"   # pozza grande (Pioggia)
                elif k == pygame.K_v:
                    mode = "wind"     # varco del Vento
                elif k == pygame.K_LEFTBRACKET:
                    brush = max(1, brush - 1)
                elif k == pygame.K_RIGHTBRACKET:
                    brush = min(8, brush + 1)
                elif pygame.K_0 <= k <= pygame.K_6:
                    cur_tile = k - pygame.K_0; mode = "tile"
                elif k in (pygame.K_LEFT, pygame.K_a):
                    cam_x -= 6; clamp_cam()
                elif k in (pygame.K_RIGHT, pygame.K_d):
                    cam_x += 6; clamp_cam()
                elif k in (pygame.K_UP, pygame.K_w):
                    cam_y -= 6; clamp_cam()
                elif k == pygame.K_DOWN:
                    cam_y += 6; clamp_cam()
            elif ev.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if mx < canvas_w:
                    tx, ty = cam_x + mx / zoom, cam_y + my / zoom
                    zoom = max(3.0, min(40.0, zoom * (1.1 if ev.y > 0 else 0.9)))
                    cam_x, cam_y = tx - mx / zoom, ty - my / zoom
                    clamp_cam()
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
                mx, my = ev.pos
                if mx < canvas_w:
                    tx, ty = screen_to_tile(mx, my)
                    if mode == "camp":
                        if ev.button == 1:
                            m.add_camp(tx, ty, camp_kind, mirror)
                        else:
                            m.remove_camp(tx, ty, mirror)
                    elif mode == "puddle":
                        if ev.button == 1:
                            m.add_spot(m.puddle_spots, tx, ty, 5, mirror)
                        else:
                            m.remove_spot(m.puddle_spots, tx, ty, mirror)
                    elif mode == "wind":
                        if ev.button == 1:
                            m.add_spot(m.wind_passages, tx, ty, 3, mirror)
                        else:
                            m.remove_spot(m.wind_passages, tx, ty, mirror)

        # painting continuo (tile) finché il mouse è premuto
        mb = pygame.mouse.get_pressed()
        mx, my = pygame.mouse.get_pos()
        if mode == "tile" and mx < canvas_w and (mb[0] or mb[2]):
            tx, ty = screen_to_tile(mx, my)
            m.paint(tx, ty, brush - 1, cur_tile if mb[0] else FLOOR, mirror)

        # --- disegno --------------------------------------------------------
        screen.fill((16, 18, 22))
        x0 = max(0, int(cam_x)); y0 = max(0, int(cam_y))
        x1 = min(m.W, int(cam_x + canvas_w / zoom) + 1)
        y1 = min(m.H, int(cam_y + SH / zoom) + 1)
        for ty in range(y0, y1):
            row = m.tiles[ty]
            for tx in range(x0, x1):
                sx = (tx - cam_x) * zoom
                sy = (ty - cam_y) * zoom
                pygame.draw.rect(screen, TILE_COLORS.get(row[tx], (64, 104, 68)),
                                 pygame.Rect(sx, sy, zoom + 1, zoom + 1))
        # griglia ogni 10
        for gx in range((x0 // 10) * 10, x1 + 1, 10):
            sx = (gx - cam_x) * zoom
            pygame.draw.line(screen, (255, 255, 255, 40), (sx, 0), (sx, SH))
            screen.blit(small.render(str(gx), True, (230, 230, 150)), (sx + 1, 1))
        for gy in range((y0 // 10) * 10, y1 + 1, 10):
            sy = (gy - cam_y) * zoom
            pygame.draw.line(screen, (255, 255, 255, 40), (0, sy), (canvas_w, sy))
            screen.blit(small.render(str(gy), True, (230, 230, 150)), (1, sy + 1))
        # strutture + tane
        for s in m.structures:
            px, py = s["pos"]
            sx = (px - cam_x) * zoom; sy = (py - cam_y) * zoom
            if 0 <= sx < canvas_w:
                col = (90, 140, 230) if s.get("team") == 0 else (230, 90, 90)
                r = int(max(3, zoom * (0.9 if s["type"] == "core" else 0.5)))
                pygame.draw.rect(screen, col, pygame.Rect(sx - r, sy - r, r * 2, r * 2), border_radius=2)
                pygame.draw.rect(screen, (255, 255, 255), pygame.Rect(sx - r, sy - r, r * 2, r * 2), 1)
        for name, d in m.dens.items():
            sx = (d[0] - cam_x) * zoom; sy = (d[1] - cam_y) * zoom
            pygame.draw.circle(screen, (235, 190, 240), (int(sx), int(sy)), int(zoom), 2)
        # campi
        for c in m.camps:
            px, py = c["pos"]; big = c.get("type") == "big"
            sx = (px - cam_x) * zoom; sy = (py - cam_y) * zoom
            if 0 <= sx < canvas_w:
                col = (255, 210, 90) if big else (210, 230, 150)
                pygame.draw.circle(screen, col, (int(sx), int(sy)), int(max(4, zoom * (0.9 if big else 0.6))))
                pygame.draw.circle(screen, (20, 20, 20), (int(sx), int(sy)), int(max(4, zoom * (0.9 if big else 0.6))), 1)
        # punti meteo: pozze grandi (blu) e varchi vento (arancio)
        for sp, col in ((m.puddle_spots, (90, 170, 240)), (m.wind_passages, (240, 170, 70))):
            for s in sp:
                px, py = s["pos"]; rr = s.get("r", 4)
                sx = (px - cam_x) * zoom; sy = (py - cam_y) * zoom
                if 0 <= sx < canvas_w:
                    pygame.draw.circle(screen, col, (int(sx), int(sy)), int(rr * zoom), 2)
                    pygame.draw.circle(screen, col, (int(sx), int(sy)), 3)

        # cursore
        tx, ty = screen_to_tile(mx, my)
        if mx < canvas_w and m.in_bounds(tx, ty):
            sx = (tx - cam_x) * zoom; sy = (ty - cam_y) * zoom
            rad = (brush - 1)
            pygame.draw.rect(screen, (255, 255, 255),
                             pygame.Rect(sx - rad * zoom, sy - rad * zoom,
                                         zoom * (2 * rad + 1), zoom * (2 * rad + 1)), 1)
            if mirror:
                mxt, myt = m.mirror(tx, ty)
                sxm = (mxt - cam_x) * zoom; sym = (myt - cam_y) * zoom
                pygame.draw.rect(screen, (255, 180, 80),
                                 pygame.Rect(sxm - rad * zoom, sym - rad * zoom,
                                             zoom * (2 * rad + 1), zoom * (2 * rad + 1)), 1)

        # pannello
        panel = pygame.Rect(canvas_w, 0, PANEL, SH)
        pygame.draw.rect(screen, (28, 30, 36), panel)
        yy = 10
        def line(txt, col=(220, 220, 220), f=font):
            nonlocal yy
            screen.blit(f.render(txt, True, col), (canvas_w + 10, yy)); yy += 18
        line("MAP EDITOR", (255, 230, 120))
        line(path.name, (180, 200, 240))
        line(f"{m.W}x{m.H}   zoom {zoom:.1f}", (160, 160, 170), small)
        yy += 6
        mode_lbl = {"tile": "TILE", "camp": "CAMPI", "puddle": "POZZA", "wind": "VARCO"}[mode]
        line(f"Modo: {mode_lbl}", (160, 240, 160))
        line(f"Mirror: {'ON' if mirror else 'OFF'} (M)", (240, 180, 80) if mirror else (150, 150, 150))
        line(f"Pennello: {brush}  ([ ])", (200, 200, 200))
        yy += 6
        line("Tile (0-6):", (200, 200, 120))
        for i, t in enumerate(PALETTE_ORDER):
            r = pygame.Rect(canvas_w + 10, yy, 16, 16)
            pygame.draw.rect(screen, TILE_COLORS[t], r)
            if mode == "tile" and cur_tile == t:
                pygame.draw.rect(screen, (255, 255, 255), r.inflate(4, 4), 2)
            screen.blit(small.render(f"{t} {TILE_NAMES[t]}", True, (210, 210, 210)), (canvas_w + 32, yy + 1))
            yy += 20
        yy += 6
        line("Campi:", (200, 200, 120))
        line("P piccolo   G grande", (210, 230, 150), small)
        line(f"(ora: {camp_kind})", (255, 210, 90) if camp_kind == "big" else (210, 230, 150), small)
        line("click sx posa / dx toglie", (180, 180, 180), small)
        yy += 6
        line("Meteo evoluto:", (200, 200, 120))
        line("U pozza grande (Pioggia)", (90, 170, 240), small)
        line("V varco vento", (240, 170, 70), small)
        yy += 8
        line("S salva  R ricarica  ESC", (200, 160, 160), small)
        line("frecce scorri · rotella zoom", (170, 170, 180), small)
        # coord cursore
        pygame.draw.rect(screen, (20, 22, 28), pygame.Rect(canvas_w, SH - 26, PANEL, 26))
        screen.blit(font.render(f"cursore: {tx},{ty}", True, (230, 230, 150)), (canvas_w + 10, SH - 22))
        # status bar
        pygame.draw.rect(screen, (20, 22, 28), pygame.Rect(0, SH - 22, canvas_w, 22))
        screen.blit(font.render(status, True, (200, 220, 200)), (8, SH - 20))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    return 0


def main():
    args = [a for a in sys.argv[1:]]
    selftest = "--selftest" in args
    args = [a for a in args if not a.startswith("--")]
    path = Path(args[0]) if args else (ROOT / "data" / "maps" / "map_3v3.json")
    if not path.is_absolute():
        path = (ROOT / path) if not path.exists() else path
    if not path.exists():
        print("Mappa non trovata:", path); return 2
    if selftest:
        return run_selftest(path)
    return run_editor(path)


if __name__ == "__main__":
    raise SystemExit(main())
