"""Selezione del personaggio (giocatore singolo).

Si arriva qui dal menu dopo aver scelto la mappa. Il giocatore sceglie il suo
Pokémon dal roster; tutti gli altri slot (alleati e avversari) ricevono un
Pokémon CASUALE dal pool, senza ripetizioni (lo fa MatchScene._bot_defs).

Comandi: frecce / clic per scegliere, INVIO o doppio clic / pulsante GIOCA per
iniziare, ESC per tornare alla scelta della mappa.
"""
from __future__ import annotations

import pygame

import config
from engine.content import load_pokemon_def
from .. import avatars as A
from .. import flor_fx
from ..sprites.animdata import parse_anim_data

COLS = 5
BG = (14, 20, 17)
PANEL = (24, 34, 29)
PANEL_HI = (38, 56, 44)
BORDER = (60, 84, 66)
GOLD = (235, 210, 90)
TEXT = (230, 232, 225)
DIM = (150, 160, 150)

TYPE_COLORS = {
    "Normal": (168, 168, 120), "Fire": (240, 128, 48), "Water": (104, 144, 240),
    "Grass": (120, 200, 80), "Electric": (248, 208, 48), "Ice": (152, 216, 216),
    "Fighting": (192, 48, 40), "Poison": (160, 64, 160), "Ground": (224, 192, 104),
    "Flying": (168, 144, 240), "Psychic": (248, 88, 136), "Bug": (168, 184, 32),
    "Rock": (184, 160, 56), "Ghost": (112, 88, 152), "Dragon": (112, 56, 248),
    "Dark": (112, 88, 72), "Steel": (184, 184, 208), "Fairy": (238, 153, 172),
}


def load_idle(sprite_dir):
    """Solo l'animazione Idle verso il basso (riga 0) di una cartella sprite PMD:
    lista di (frame ritagliato, durata). Più leggero di caricare tutte le anim."""
    from pathlib import Path
    d = config_root() / sprite_dir if sprite_dir else None
    if d is None or not (d / "AnimData.xml").is_file():
        return []
    try:
        infos = parse_anim_data(d / "AnimData.xml")
    except Exception:
        return []
    info = infos.get("Idle") or next(iter(infos.values()), None)
    if info is None:
        return []
    src = info.copy_of or info.name
    if src != info.name and src in infos:
        info = infos[src]
    path = Path(d) / f"{src}-Anim.png"
    if not path.is_file():
        return []
    sheet = pygame.image.load(str(path)).convert_alpha()
    fw, fh = info.frame_width, info.frame_height
    n = min(info.frame_count, max(1, sheet.get_width() // fw))
    frames = [sheet.subsurface(pygame.Rect(i * fw, 0, fw, fh)).copy() for i in range(n)]
    # Ritaglio comune a tutti i frame: l'animazione non "balla" nel riquadro.
    box = frames[0].get_bounding_rect()
    for f in frames[1:]:
        box = box.union(f.get_bounding_rect())
    frames = [f.subsurface(box).copy() for f in frames]
    durs = list(info.durations)[:n] or [10] * n
    return list(zip(frames, durs))


def config_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


def scale_nearest(img, side):
    """Scala NEAREST (pixel art) perché il lato maggiore sia `side`."""
    k = side / max(img.get_width(), img.get_height())
    return pygame.transform.scale(img, (max(1, int(img.get_width() * k)),
                                        max(1, int(img.get_height() * k))))


class CharSelectScene:
    def __init__(self, app, map_index: int):
        self.app = app
        self.map_index = map_index
        self.next_scene = None
        self.sel = 0
        self.t = 0.0
        self.loading = False
        self._drawn_loading = False
        self.defs = [load_pokemon_def(str(app.root / rel)) for rel in config.ROSTER]
        self.idle = [load_idle(d.sprite_dir) for d in self.defs]
        self._evo_idle: dict = {}
        self._cards: list = []       # (rect, indice) dell'ultimo frame disegnato
        self._play_rect = None
        self._back_rect = None
        self.flower_color = "red"    # Flabébé: colore dei fiori
        self._color_rects: list = []
        self._fonts = {}

    # --- input ---------------------------------------------------------------
    def handle_events(self, events):
        if self.loading:
            return
        n = len(self.defs)
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    from .menu_scene import MenuScene
                    m = MenuScene(self.app)
                    m.map_index = self.map_index
                    self.next_scene = m
                elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                    self.sel = (self.sel + 1) % n
                elif ev.key in (pygame.K_LEFT, pygame.K_a):
                    self.sel = (self.sel - 1) % n
                elif ev.key in (pygame.K_DOWN, pygame.K_s):
                    self.sel = min(n - 1, self.sel + COLS)
                elif ev.key in (pygame.K_UP, pygame.K_w):
                    self.sel = max(0, self.sel - COLS)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self._start()
                elif ev.key in flor_fx.COLOR_KEYS and self._has_colors():
                    self.flower_color = flor_fx.COLORS[flor_fx.COLOR_KEYS[ev.key]]
            elif ev.type == pygame.MOUSEMOTION:
                for r, i in self._cards:
                    if r.collidepoint(ev.pos):
                        self.sel = i
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                hit = next((c for r, c in self._color_rects if r.collidepoint(ev.pos)), None)
                if hit is not None and self._has_colors():
                    self.flower_color = hit
                    continue
                if self._play_rect and self._play_rect.collidepoint(ev.pos):
                    self._start()
                elif self._back_rect and self._back_rect.collidepoint(ev.pos):
                    from .menu_scene import MenuScene
                    m = MenuScene(self.app)
                    m.map_index = self.map_index
                    self.next_scene = m
                for r, i in self._cards:
                    if r.collidepoint(ev.pos):
                        if i == self.sel and getattr(ev, "clicks", 1) >= 2:
                            self._start()
                        self.sel = i

    def _has_colors(self) -> bool:
        return self.defs[self.sel].passive == "giardino"

    def _start(self):
        # La costruzione della partita richiede qualche secondo (mappa
        # pre-renderizzata): prima si disegna "Caricamento", poi si costruisce.
        self.loading = True
        self._drawn_loading = False

    def fixed_update(self):
        pass

    def update(self, dt):
        self.t += dt
        if self.loading and self._drawn_loading and self.next_scene is None:
            from .match_scene import MatchScene
            self.next_scene = MatchScene(
                str(self.app.root / config.MAPS[self.map_index][1]),
                str(self.app.root / config.ROSTER[self.sel]),
                flower_color=self.flower_color if self._has_colors() else None)

    # --- disegno -------------------------------------------------------------
    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.SysFont("consolas", size, bold=bold)
        return self._fonts[key]

    def _frame(self, frames, speed=1.0):
        """Frame corrente di un'animazione Idle (durate PMD in 1/60 s)."""
        if not frames:
            return None
        total = sum(d for _, d in frames)
        tick = int(self.t * 60 * speed) % max(1, total)
        for img, d in frames:
            if tick < d:
                return img
            tick -= d
        return frames[-1][0]

    def _evo_frames(self, sprite_dir):
        if sprite_dir not in self._evo_idle:
            self._evo_idle[sprite_dir] = load_idle(sprite_dir)
        return self._evo_idle[sprite_dir]

    def draw_fullres(self, surface, font):
        W, H = surface.get_size()
        surface.fill(BG)
        if self.loading:
            self._draw_loading(surface, W, H)
            return
        big = self._font(max(22, H // 24), bold=True)
        small = self._font(max(13, H // 50))
        mid = self._font(max(15, H // 40), bold=True)

        title = big.render("Scegli il tuo Pokémon", True, GOLD)
        surface.blit(title, (W // 2 - title.get_width() // 2, H // 28))
        mname = config.MAPS[self.map_index][0]
        ts = 3 if mname == "3v3" else 5
        sub = small.render(f"Mappa {mname}  -  gli altri {2 * ts - 1} sono bot: Pokémon a caso "
                           f"dal pool, senza ripetizioni, col nome del loro Pokémon", True, DIM)
        surface.blit(sub, (W // 2 - sub.get_width() // 2, H // 28 + title.get_height() + 6))

        # Griglia delle carte (a sinistra) + anteprima (a destra).
        top = H // 6
        grid_w = int(W * 0.56)
        gx = int(W * 0.04)
        gap = max(6, W // 160)
        cw = (grid_w - gap * (COLS - 1)) // COLS
        rows = (len(self.defs) + COLS - 1) // COLS
        ch = min(int(cw * 1.45), (H - top - H // 5) // rows - gap)
        self._grid_h = rows * (ch + gap) - gap
        self._cards = []
        for i, d in enumerate(self.defs):
            r = pygame.Rect(gx + (i % COLS) * (cw + gap), top + (i // COLS) * (ch + gap), cw, ch)
            self._cards.append((r, i))
            on = i == self.sel
            pygame.draw.rect(surface, PANEL_HI if on else PANEL, r, border_radius=6)
            pygame.draw.rect(surface, GOLD if on else BORDER, r, 3 if on else 1, border_radius=6)
            frames = self.idle[i]
            img = self._frame(frames) if on else (frames[0][0] if frames else None)
            if img is not None:
                pic = scale_nearest(img, int(min(cw, ch) * 0.62))
                surface.blit(pic, (r.centerx - pic.get_width() // 2,
                                   r.y + int(ch * 0.42) - pic.get_height() // 2))
            nm = mid.render(d.name, True, TEXT if on else (200, 205, 198))
            surface.blit(nm, (r.centerx - nm.get_width() // 2, r.bottom - int(ch * 0.27)))
            role = small.render(d.role or "", True, DIM)
            surface.blit(role, (r.centerx - role.get_width() // 2, r.bottom - int(ch * 0.13)))

        self._draw_preview(surface, W, H, top, big, mid, small)
        hint = small.render("Frecce/mouse: scegli  -  Invio o doppio clic: gioca  -  "
                            "Esc: mappe", True, DIM)
        surface.blit(hint, (gx, top + self._grid_h + 22))

    def _draw_preview(self, surface, W, H, top, big, mid, small):
        d = self.defs[self.sel]
        px = int(W * 0.63)
        pw = int(W * 0.33)
        panel = pygame.Rect(px, top, pw, self._grid_h)
        pygame.draw.rect(surface, PANEL, panel, border_radius=8)
        pygame.draw.rect(surface, BORDER, panel, 1, border_radius=8)

        # Tu: immagine profilo + nickname (i bot non ne hanno).
        prof = getattr(self.app, "profile", None) or {}
        side = 40 if panel.h < 520 else 80
        A.draw_avatar(surface, prof.get("avatar", 0), (panel.x + 12, panel.y + 12, side, side), GOLD)
        you = mid.render(prof.get("name", "Tu"), True, TEXT)
        surface.blit(you, (panel.x + 20 + side, panel.y + 12))
        surface.blit(small.render("sei tu", True, DIM),
                     (panel.x + 20 + side, panel.y + 16 + you.get_height()))

        img = self._frame(self.idle[self.sel])
        if img is not None:
            pic = scale_nearest(img, int(min(pw, panel.h) * 0.42))
            surface.blit(pic, (panel.centerx - pic.get_width() // 2,
                               panel.y + int(panel.h * 0.25) - pic.get_height() // 2))
        y = panel.y + int(panel.h * 0.48)
        nm = big.render(d.name, True, GOLD)
        surface.blit(nm, (panel.centerx - nm.get_width() // 2, y))
        y += nm.get_height() + 6

        # Tipi come pillole colorate.
        pills = [small.render(t, True, (20, 20, 20)) for t in d.types]
        tw = sum(p.get_width() + 16 for p in pills) + 8 * (len(pills) - 1)
        x = panel.centerx - tw // 2
        for t, p in zip(d.types, pills):
            r = pygame.Rect(x, y, p.get_width() + 16, p.get_height() + 6)
            pygame.draw.rect(surface, TYPE_COLORS.get(t, (180, 180, 180)), r, border_radius=9)
            surface.blit(p, (r.x + 8, r.y + 3))
            x = r.right + 8
        y += (pills[0].get_height() + 14) if pills else 0
        role = mid.render(f"Ruolo: {d.role}", True, TEXT)
        surface.blit(role, (panel.centerx - role.get_width() // 2, y))
        y += role.get_height() + 12

        # Linea evolutiva (tutte le forme; Eevee ne ha 8 a scelta).
        evos = [e for e in d.evolutions if e.get("sprite_dir")
                and e.get("sprite_dir") != d.sprite_dir]
        if evos:
            lab = small.render("Evoluzioni:", True, DIM)
            surface.blit(lab, (panel.x + 14, y))
            y += lab.get_height() + 4
            side = max(24, min(56, (pw - 28) // max(1, len(evos)) - 6))
            x = panel.x + 14
            for e in evos:
                fr = self._evo_frames(e["sprite_dir"])
                if fr:
                    pic = scale_nearest(fr[0][0], side)
                    surface.blit(pic, (x + (side - pic.get_width()) // 2,
                                       y + side - pic.get_height()))
                x += side + 6
                if x + side > panel.right - 8:
                    x = panel.x + 14
                    y += side + 4
            y += side + 6

        # Flabébé: scelta del colore dei fiori (resta per tutta la partita).
        self._color_rects = []
        if d.passive == "giardino":
            self._color_rects = flor_fx.draw_color_picker(
                surface, panel.x + 14, y, pw - 28, self.flower_color, small, small)

        # Pulsanti.
        bh = max(40, H // 14)
        self._play_rect = pygame.Rect(panel.x, panel.bottom + 14, int(pw * 0.62), bh)
        self._back_rect = pygame.Rect(self._play_rect.right + 10, panel.bottom + 14,
                                      pw - int(pw * 0.62) - 10, bh)
        hover = pygame.mouse.get_pos()
        for r, label, col in ((self._play_rect, "GIOCA  (Invio)", (70, 150, 80)),
                              (self._back_rect, "Indietro (Esc)", (70, 70, 80))):
            c = tuple(min(255, v + 25) for v in col) if r.collidepoint(hover) else col
            pygame.draw.rect(surface, c, r, border_radius=8)
            pygame.draw.rect(surface, (20, 20, 20), r, 2, border_radius=8)
            t = mid.render(label, True, TEXT)
            surface.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))

    def _draw_loading(self, surface, W, H):
        from .. import loading_screen
        loading_screen.draw(surface, self.t, "Caricamento della mappa...")
        self._drawn_loading = True
