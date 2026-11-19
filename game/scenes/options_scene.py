"""Opzioni (menu principale): schermo, audio, controlli.

Righe: schermo intero, volumi (generale, musica, combattimento, interfaccia,
avvisi: barre da trascinare), limite FPS, velocità della camera,
lancio rapido (smart cast) e la pagina dei tasti. Frecce su/giù per scegliere,
sinistra/destra (o clic sulle frecce) per cambiare il valore, Invio/clic per
attivare. Tutto si salva subito in %APPDATA%/PokeMoba/options.json.
"""
from __future__ import annotations

import pygame

from .. import audio, keybinds
from ..app import _save_options
from .online_lobby_scene import BG, DIM, GOLD, TEXT, font
from .menu_scene import PANEL, PANEL_HI, BORDER

VOL_STEP = 0.05

# Righe del volume: chiave -> (etichetta, categoria audio o None = musica/generale,
# suono di prova).
VOLUMES = {"master": ("Volume generale", None, "ui_confirm"),
           "music": ("Musica", None, None),
           "combat": ("Effetti di combattimento", "combat", "hit_melee"),
           "ui": ("Interfaccia e menu", "ui", "ui_confirm"),
           "alert": ("Avvisi, ping e chat", "alert", "ping")}


def _row_box(surface, r, on, label, value=None, arrows=False, t=None):
    pygame.draw.rect(surface, PANEL_HI if on else PANEL, r, border_radius=8)
    pygame.draw.rect(surface, GOLD if on else BORDER, r, 2, border_radius=8)
    txt = t.render(label, True, GOLD if on else TEXT)
    if value is None:
        surface.blit(txt, (r.centerx - txt.get_width() // 2, r.centery - txt.get_height() // 2))
        return None, None
    surface.blit(txt, (r.x + 18, r.centery - txt.get_height() // 2))
    val = t.render(value, True, GOLD if on else TEXT)
    left = right = None
    if arrows:
        aw = 30
        right = pygame.Rect(r.right - 12 - aw, r.y + 5, aw, r.h - 10)
        vx = right.x - 10 - val.get_width()
        left = pygame.Rect(vx - 10 - aw, r.y + 5, aw, r.h - 10)
        for a, ch in ((left, "<"), (right, ">")):
            pygame.draw.rect(surface, (40, 44, 56), a, border_radius=5)
            g = t.render(ch, True, TEXT)
            surface.blit(g, (a.centerx - g.get_width() // 2, a.centery - g.get_height() // 2))
        surface.blit(val, (vx, r.centery - val.get_height() // 2))
    else:
        surface.blit(val, (r.right - 18 - val.get_width(), r.centery - val.get_height() // 2))
    return left, right


def _speaker(surface, x, y, s, col, muted):
    """Altoparlante pixel art (s = lato del pixel) con le onde, o la X se muto."""
    def px(cx, cy, w=1, h=1):
        pygame.draw.rect(surface, col, (x + cx * s, y + cy * s, w * s, h * s))
    px(0, 3, 2, 3)
    px(2, 2, 1, 5)
    px(3, 1, 1, 7)
    px(4, 0, 1, 9)
    if muted:
        for i in range(4):
            px(6 + i, 3 + i)
            px(9 - i, 3 + i)
    else:
        px(6, 3, 1, 3)
        px(8, 1, 1, 7)


def _slider_row(surface, r, on, label, vol, t, small):
    """Riga con la barra del volume: ritorna il rettangolo della barra."""
    pygame.draw.rect(surface, PANEL_HI if on else PANEL, r, border_radius=8)
    pygame.draw.rect(surface, GOLD if on else BORDER, r, 2, border_radius=8)
    txt = t.render(label, True, GOLD if on else TEXT)
    surface.blit(txt, (r.x + 18, r.centery - txt.get_height() // 2))
    pct = small.render(f"{round(vol * 100)}%", True, GOLD if on else TEXT)
    pw = small.size("100%")[0]
    surface.blit(pct, (r.right - 14 - pct.get_width(), r.centery - pct.get_height() // 2))
    ps = max(2, r.h // 16)
    sx = r.right - 14 - pw - 12 - 10 * ps
    _speaker(surface, sx, r.centery - 9 * ps // 2, ps, GOLD if on else DIM, vol <= 0.001)
    bh = max(4, r.h // 9)
    room = sx - 18 - (r.x + 18 + txt.get_width() + 24)   # mai sopra l'etichetta
    bw = max(60, min(int(r.w * 0.40), 340, room))
    bar = pygame.Rect(sx - 18 - bw, r.centery - bh, bw, 2 * bh)
    pygame.draw.rect(surface, (22, 24, 32), bar, border_radius=bh)
    fw = int(bar.w * vol)
    if fw > 0:
        fill = pygame.Rect(bar.x, bar.y, max(bar.h, fw), bar.h)
        pygame.draw.rect(surface, GOLD if on else (150, 128, 70), fill, border_radius=bh)
        hi = pygame.Rect(fill.x + 3, fill.y + 2, max(0, fill.w - 6), max(1, bar.h // 4))
        pygame.draw.rect(surface, (255, 236, 170) if on else (190, 170, 110), hi)
    for i in range(1, 10):                       # tacche ogni 10%
        tx = bar.x + bar.w * i // 10
        pygame.draw.line(surface, (70, 72, 86), (tx, bar.bottom + 2),
                         (tx, bar.bottom + 3 + (2 if i == 5 else 0)))
    pygame.draw.rect(surface, BORDER, bar, 1, border_radius=bh)
    kx = bar.x + fw                              # manopola
    kr = bh + 4
    pygame.draw.circle(surface, (14, 14, 20), (kx + 1, bar.centery + 2), kr)
    pygame.draw.circle(surface, (240, 230, 200) if on else (176, 172, 158), (kx, bar.centery), kr)
    pygame.draw.circle(surface, GOLD if on else BORDER, (kx, bar.centery), kr, 2)
    return bar


class OptionsScene:
    ROWS = ("fullscreen", "master", "music", "combat", "ui", "alert", "fps", "camera",
            "smart", "keys", "back")

    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.sel = 0
        self._rects: list = []       # (rect, key, delta) delta 0 = attiva
        self._bars: dict = {}        # chiave del volume -> rettangolo della barra
        self._drag = None            # volume che si sta trascinando

    def _back(self):
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    # --- volumi ----------------------------------------------------------------------
    @staticmethod
    def _vol(key):
        if key == "master":
            return audio.master_volume()
        if key == "music":
            return audio.music_volume()
        return audio.category_volume(VOLUMES[key][1])

    @staticmethod
    def _set_vol(key, v, test=True):
        v = max(0.0, min(1.0, round(v / VOL_STEP) * VOL_STEP))
        if key == "master":
            audio.set_master_volume(v)
        elif key == "music":
            audio.set_music_volume(v)
        else:
            audio.set_category_volume(VOLUMES[key][1], v)
        _save_options({f"{key}_volume": round(OptionsScene._vol(key), 3)})
        snd = VOLUMES[key][2]
        if test and snd:
            from .. import sfx
            sfx.play(snd)                            # prova del volume

    def _drag_to(self, key, x, test=False):
        bar = self._bars.get(key)
        if bar is not None:
            self._set_vol(key, (x - bar.x) / max(1, bar.w), test)

    # --- valori ----------------------------------------------------------------------
    def _value(self, key):
        if key == "fullscreen":
            return "SÌ" if self.app.fullscreen else "NO"
        if key in VOLUMES:
            return f"{round(self._vol(key) * 100)}%"
        if key == "fps":
            cap = getattr(self.app, "fps_cap", 120)
            return "senza limite" if not cap else f"{cap}"
        if key == "camera":
            return f"x{keybinds.camera_speed:.2f}".rstrip("0").rstrip(".")
        if key == "smart":
            return "SÌ" if keybinds.smart_cast else "NO"
        return None

    def _change(self, key, delta):
        if key == "fullscreen":
            self.app.set_fullscreen(not self.app.fullscreen)
        elif key in VOLUMES:
            v = self._vol(key)
            if delta == 0:                                # Invio: muto <-> 100%
                v = 1.0 if v <= 0.001 else 0.0
            else:
                v += delta * VOL_STEP
            self._set_vol(key, v)
        elif key == "fps":
            caps = keybinds.FPS_CAPS
            cur = getattr(self.app, "fps_cap", 120)
            i = caps.index(cur) if cur in caps else 2
            self.app.fps_cap = caps[(i + (delta or 1)) % len(caps)]
            _save_options({"fps_cap": self.app.fps_cap})
        elif key == "camera":
            sp = keybinds.CAM_SPEEDS
            cur = keybinds.camera_speed
            i = min(range(len(sp)), key=lambda k: abs(sp[k] - cur))
            keybinds.camera_speed = sp[(i + (delta or 1)) % len(sp)]
            _save_options(keybinds.to_options())
        elif key == "smart":
            keybinds.smart_cast = not keybinds.smart_cast
            _save_options(keybinds.to_options())
        elif key == "keys":
            self.next_scene = KeybindScene(self.app)
        elif key == "back":
            self._back()

    # --- ciclo -----------------------------------------------------------------------
    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                hit = next((k for k, b in self._bars.items()
                            if b.inflate(16, 20).collidepoint(ev.pos)), None)
                if hit is not None:
                    self._drag = hit
                    self.sel = self.ROWS.index(hit)
                    self._drag_to(hit, ev.pos[0])
                    continue
            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self._drag:
                self._drag_to(self._drag, ev.pos[0], test=True)
                self._drag = None
                continue
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
                for r, key, delta in self._rects:
                    if r.collidepoint(ev.pos):
                        if key in VOLUMES and delta == 0:
                            if ev.button == 3:            # destro: muto <-> 100%
                                self._change(key, 0)
                            break
                        if delta == 0 and ev.button == 3:
                            delta = -1
                        self._change(key, delta)
                        break
            elif ev.type == pygame.MOUSEWHEEL:
                key = self.ROWS[self.sel]
                if key in VOLUMES:
                    self._change(key, 1 if ev.y > 0 else -1)
            elif ev.type == pygame.KEYDOWN:
                key = self.ROWS[self.sel]
                if ev.key == pygame.K_ESCAPE:
                    self._back()
                elif ev.key in (pygame.K_DOWN, pygame.K_s):
                    self.sel = (self.sel + 1) % len(self.ROWS)
                elif ev.key in (pygame.K_UP, pygame.K_w):
                    self.sel = (self.sel - 1) % len(self.ROWS)
                elif ev.key in (pygame.K_LEFT, pygame.K_a) and self._value(key) is not None:
                    self._change(key, -1)
                elif ev.key in (pygame.K_RIGHT, pygame.K_d) and self._value(key) is not None:
                    self._change(key, 1)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self._change(key, 0)
            elif ev.type == pygame.MOUSEMOTION:
                if self._drag:
                    self._drag_to(self._drag, ev.pos[0])
                    continue
                for r, key, _d in self._rects:
                    if r.collidepoint(ev.pos):
                        self.sel = self.ROWS.index(key)
                        break

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, f):
        W, H = surface.get_size()
        surface.fill(BG)
        big = font(max(26, H // 22), True)
        t = font(max(15, H // 46), True)
        small = font(max(13, H // 54))
        ty = int(H * 0.035)
        title = big.render("Opzioni", True, GOLD)
        surface.blit(title, (W // 2 - title.get_width() // 2, ty))
        labels = {"fullscreen": "Schermo intero",
                  "fps": "Limite FPS", "camera": "Velocità camera (bordi)",
                  "smart": "Lancio rapido (smart cast)", "keys": "Tasti...",
                  "back": "Indietro"}
        gap = 6
        sec = small.get_height() + 6                 # spazio per l'intestazione "AUDIO"/"GIOCO"
        y0 = ty + title.get_height() + 12
        n = len(self.ROWS)
        foot = small.get_height() * 2 + 34
        bh = max(28, min(H // 15, (H - y0 - foot - 2 * sec) // n - gap))
        bw = min(int(W * 0.7), max(720, int(H * 0.85)))
        x0 = W // 2 - bw // 2
        self._rects = []
        self._bars = {}
        y = y0
        for i, key in enumerate(self.ROWS):
            if key in ("master", "fps"):                 # intestazione del gruppo
                h = small.render("AUDIO" if key == "master" else "GIOCO", True, DIM)
                surface.blit(h, (x0 + 4, y + 2))
                pygame.draw.line(surface, BORDER, (x0 + h.get_width() + 12, y + 2 + h.get_height() // 2),
                                 (x0 + bw, y + 2 + h.get_height() // 2))
                y += sec
            r = pygame.Rect(x0, y, bw, bh)
            y += bh + gap
            on = i == self.sel or key == self._drag
            if key in VOLUMES:
                self._bars[key] = _slider_row(surface, r, on, VOLUMES[key][0],
                                              self._vol(key), t, small)
                self._rects.append((r, key, 0))
                continue
            val = self._value(key)
            arrows = key in ("fps", "camera")
            left, right = _row_box(surface, r, on, labels[key], val, arrows, t)
            if left is not None:
                self._rects += [(left, key, -1), (right, key, 1)]
            self._rects.append((r, key, 0))
        notes = {"smart": "Lancio rapido: la mossa parte appena premi il tasto, verso il mouse "
                          "(Tiro Lungo e la R di Magnezone restano a mira).",
                 "fps": "Limite FPS: più basso = meno lavoro per la CPU (portatili).",
                 "camera": "Velocità dello scorrimento quando il mouse tocca il bordo.",
                 "master": "Volume generale: moltiplica musica ed effetti.",
                 "music": "Musica dei menu (in partita non suona).",
                 "combat": "Colpi, mosse, proiettili, torri e morti delle unità.",
                 "ui": "Clic e scorrimento dei menu, acquisti e vendite nel negozio.",
                 "alert": "Ping, chat rapida, voto di resa, livelli, evoluzioni, uccisioni, oro."}
        note = notes.get(self.ROWS[self.sel])
        if note:
            nn = small.render(note, True, DIM)
            surface.blit(nn, (W // 2 - nn.get_width() // 2, y + 4))
        hint = small.render("frecce: scegli e cambia    trascina la barra o rotella: volume    "
                            "Invio / clic destro: muto    ESC: menu", True, DIM)
        surface.blit(hint, (W // 2 - hint.get_width() // 2, H - hint.get_height() - 12))


class KeybindScene:
    """Tasti: clic (o Invio) su un'azione, poi premi il nuovo tasto. Se il tasto
    era già usato, le due azioni si scambiano. ESC annulla l'attesa o torna."""

    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.sel = 0
        self.waiting = None          # azione in attesa del nuovo tasto
        self.msg = ""
        self._rects: list = []

    def _items(self):
        return [a for a, _l, _k in keybinds.ACTIONS] + ["reset", "back"]

    def _activate(self, item):
        if item == "back":
            self.next_scene = OptionsScene(self.app)
            self.next_scene.sel = OptionsScene.ROWS.index("keys")
        elif item == "reset":
            keybinds.reset()
            _save_options(keybinds.to_options())
            self.msg = "Tasti predefiniti ripristinati."
        else:
            self.waiting = item
            self.msg = ""

    def handle_events(self, events):
        for ev in events:
            if self.waiting is not None:
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        self.waiting = None
                    else:
                        err = keybinds.assign(self.waiting, ev.key)
                        if err:
                            self.msg = err
                        else:
                            _save_options(keybinds.to_options())
                            self.msg = ""
                        self.waiting = None
                continue
            items = self._items()
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for r, item in self._rects:
                    if r.collidepoint(ev.pos):
                        self._activate(item)
                        break
            elif ev.type == pygame.MOUSEMOTION:
                for r, item in self._rects:
                    if r.collidepoint(ev.pos):
                        self.sel = items.index(item)
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self._activate("back")
                elif ev.key == pygame.K_DOWN:
                    self.sel = (self.sel + 1) % len(items)
                elif ev.key == pygame.K_UP:
                    self.sel = (self.sel - 1) % len(items)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._activate(items[self.sel])

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, f):
        W, H = surface.get_size()
        surface.fill(BG)
        big = font(max(26, H // 22), True)
        t = font(max(14, H // 46), True)
        small = font(max(13, H // 54))
        title = big.render("Tasti", True, GOLD)
        surface.blit(title, (W // 2 - title.get_width() // 2, int(H * 0.04)))
        items = self._items()
        bw = min(int(W * 0.6), 640)
        bh = max(30, min(44, (H - int(H * 0.16) - 90) // len(items) - 6))
        y0 = int(H * 0.13)
        self._rects = []
        for i, item in enumerate(items):
            r = pygame.Rect(W // 2 - bw // 2, y0 + i * (bh + 6), bw, bh)
            on = i == self.sel
            self._rects.append((r, item))
            if item == "reset":
                _row_box(surface, r, on, "Ripristina predefiniti", t=t)
            elif item == "back":
                _row_box(surface, r, on, "Indietro", t=t)
            else:
                val = "premi un tasto..." if self.waiting == item else keybinds.key_name(item)
                _row_box(surface, r, on or self.waiting == item, keybinds.LABELS[item], val, t=t)
        if self.msg:
            m = small.render(self.msg, True, GOLD)
            surface.blit(m, (W // 2 - m.get_width() // 2, H - 64))
        hint = small.render("clic/Invio: cambia tasto (poi premi il nuovo)     Ctrl + tasto mossa: "
                            "sale di grado     1-6 oggetti     ESC: indietro", True, DIM)
        surface.blit(hint, (W // 2 - hint.get_width() // 2, H - hint.get_height() - 12))
