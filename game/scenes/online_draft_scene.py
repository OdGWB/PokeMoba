"""DRAFT della partita online: si sceglie il Pokémon a turno (net/draft.py).

Arriva qui chi è nella lobby online (host e amici) quando l'host avvia. L'host
decide tutto (turno, tempo, Pokémon liberi); questa scena mostra lo stato che
manda e, quando tocca a te, ti fa scegliere:
- 3v3: uno a testa, comincia il primo BLU;
- 5v5: B1, R1 R2, B2 B3, R3 R4, B4 B5, R5.
I turni dei bot si saltano: quando tutti gli umani hanno scelto, i bot prendono
insieme un Pokémon a caso fra i rimasti. Nessun Pokémon si ripete.

Comandi: frecce / mouse per guardare, INVIO o doppio clic per confermare
(solo al tuo turno; prima di confermare gli altri vedono la tua anteprima),
ESC per uscire (l'host chiude la partita per tutti).
"""
from __future__ import annotations

import pygame

import config
from engine.content import load_pokemon_def
from net import client as C

from .. import avatars as A
from .char_select_scene import PANEL, PANEL_HI, TYPE_COLORS, load_idle, scale_nearest
from .online_lobby_scene import BG, BORDER, DIM, GOLD, RED, TEXT, Buttons, font

COLS = 5
TEAM_NAME = ("BLU", "ROSSA")


class OnlineDraftScene:
    def __init__(self, app, session, host=None):
        self.app = app
        self.session = session
        self.host = host
        self.next_scene = None
        self.defs = [load_pokemon_def(str(app.root / rel)) for rel in config.ROSTER]
        self.idle = [load_idle(d.sprite_dir) for d in self.defs]
        self.sel = 0
        self.t = 0.0
        self.buttons = Buttons()
        self._cards: list = []
        self._sent_hover = None
        self._was_turn = False
        self._loading_drawn = False

    # --- input ------------------------------------------------------------------------
    def handle_events(self, events):
        n = len(self.defs)
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self._leave()
                elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                    self.sel = (self.sel + 1) % n
                elif ev.key in (pygame.K_LEFT, pygame.K_a):
                    self.sel = (self.sel - 1) % n
                elif ev.key in (pygame.K_DOWN, pygame.K_s):
                    self.sel = min(n - 1, self.sel + COLS)
                elif ev.key in (pygame.K_UP, pygame.K_w):
                    self.sel = max(0, self.sel - COLS)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self._lock()
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self.buttons.click(ev.pos):
                    continue
                for r, i in self._cards:
                    if r.collidepoint(ev.pos):
                        if i == self.sel and getattr(ev, "clicks", 1) >= 2:
                            self._lock()
                        self.sel = i

    def _can_lock(self) -> bool:
        s = self.session
        return s.phase == C.DRAFT and s.draft_my_turn() and self.sel not in s.draft_taken()

    def _lock(self):
        if self._can_lock():
            self.session.send_pick(self.sel, lock=True)

    def _leave(self):
        if self.host is not None:
            self.host.shutdown()
        else:
            self.session.close()
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    # --- logica -----------------------------------------------------------------------
    def fixed_update(self):
        pass

    def update(self, dt):
        self.t += dt
        s = self.session
        s.poll()
        if s.phase == C.LOADING and s.start_info:
            # Prima si disegna la schermata di caricamento, poi si costruisce la partita.
            if self._loading_drawn:
                from .online_match_scene import OnlineMatchScene
                self.next_scene = OnlineMatchScene(self.app, s, host=self.host)
            return
        turn = s.phase == C.DRAFT and s.draft_my_turn()
        if turn and not self._was_turn:
            # Tocca a me: parto da un Pokémon ancora libero.
            taken = s.draft_taken()
            if self.sel in taken:
                self.sel = next((i for i in range(len(self.defs)) if i not in taken), self.sel)
            self._sent_hover = None
        self._was_turn = turn
        if turn and self.sel != self._sent_hover and self.sel not in s.draft_taken():
            s.send_pick(self.sel, lock=False)        # anteprima: la vedono tutti
            self._sent_hover = self.sel

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def _frame(self, frames):
        if not frames:
            return None
        total = sum(d for _, d in frames)
        tick = int(self.t * 60) % max(1, total)
        for img, d in frames:
            if tick < d:
                return img
            tick -= d
        return frames[-1][0]

    # --- disegno ------------------------------------------------------------------------
    def draw_fullres(self, surface, f):
        W, H = surface.get_size()
        if self.session.phase == C.LOADING:
            from .. import loading_screen
            loading_screen.draw(surface, self.t, "Caricamento della mappa...")
            self._loading_drawn = True
            return
        surface.fill(BG)
        self.buttons.clear()
        s = self.session
        d = s.draft
        big = font(max(24, H // 24), True)
        mid = font(max(15, H // 42), True)
        sm = font(max(13, H // 54))
        title = big.render("DRAFT", True, GOLD)
        surface.blit(title, (W // 2 - title.get_width() // 2, H // 40))
        y = H // 40 + title.get_height() + 4
        if s.phase in (C.LOST, C.ENDED):
            msg = s.lost_reason or (s.end_info or {}).get("message", "Connessione chiusa.")
            t = mid.render(msg[:90], True, RED)
            surface.blit(t, (W // 2 - t.get_width() // 2, y))
            hint = sm.render("ESC: torna al menu", True, DIM)
            surface.blit(hint, (W // 2 - hint.get_width() // 2, y + 40))
            return
        if d is None:
            return
        entries = d["entries"]
        surface.blit(*self._status(d, mid, W, y))
        y += mid.get_height() + 10
        y = self._draw_order(surface, entries, d, W, y, sm) + 12

        # Squadre ai lati, carte al centro.
        side_w = int(W * 0.22)
        self._draw_team(surface, entries, d, 0, pygame.Rect(16, y, side_w, H - y - 60), mid, sm)
        self._draw_team(surface, entries, d, 1,
                        pygame.Rect(W - 16 - side_w, y, side_w, H - y - 60), mid, sm)
        gx, gw = 16 + side_w + 20, W - 2 * (16 + side_w + 20)
        self._draw_grid(surface, d, pygame.Rect(gx, y, gw, H - y - 60), mid, sm)
        hint = sm.render("Frecce/mouse: guarda  -  INVIO o doppio clic: conferma (al tuo turno)"
                         "  -  ESC: esci", True, DIM)
        surface.blit(hint, (W // 2 - hint.get_width() // 2, H - hint.get_height() - 14))

    def _status(self, d, f, W, y):
        s = self.session
        secs = int(s.draft_time_left() + 0.99)
        if d["done"]:
            txt, col = "Draft completo: i bot hanno preso i loro Pokémon. Si parte...", GOLD
        elif s.draft_my_turn():
            txt, col = f"TOCCA A TE!  Scegli e conferma con INVIO   ({secs} s)", GOLD
        else:
            e = d["entries"][d["turn"]]
            txt = f"Sceglie {e['name'] or '?'} (squadra {TEAM_NAME[e['team']]})   ({secs} s)"
            col = config.TEAM_COLORS[e["team"]]
        t = f.render(txt, True, col)
        return t, (W // 2 - t.get_width() // 2, y)

    def _draw_order(self, surface, entries, d, W, y, f):
        """Striscia con l'ordine di scelta: B1 R1 R2 B2 ... (il turno attuale in oro)."""
        bw, gap = max(44, W // 26), 6
        x = W // 2 - (len(entries) * (bw + gap) - gap) // 2
        for k, e in enumerate(entries):
            r = pygame.Rect(x + k * (bw + gap), y, bw, bw)
            col = config.TEAM_COLORS[e["team"]]
            pygame.draw.rect(surface, (20, 28, 24), r, border_radius=4)
            if e["poke"] is not None:
                img = self._frame(self.idle[e["poke"]])
                if img is not None:
                    pic = scale_nearest(img, bw - 8)
                    surface.blit(pic, (r.centerx - pic.get_width() // 2,
                                       r.centery - pic.get_height() // 2))
            else:
                lab = f.render(f"{TEAM_NAME[e['team']][0]}{e['pos'] + 1}", True,
                               col if e["slot"] is not None else (90, 96, 92))
                surface.blit(lab, (r.centerx - lab.get_width() // 2, r.centery - lab.get_height() // 2))
            now = k == d["turn"]
            pygame.draw.rect(surface, GOLD if now else col, r, 3 if now else 1, border_radius=4)
        return y + bw

    def _draw_team(self, surface, entries, d, team, rect, mid, sm):
        col = config.TEAM_COLORS[team]
        surface.blit(mid.render(f"Squadra {TEAM_NAME[team]}", True, col), (rect.x, rect.y))
        mine = sorted((k, e) for k, e in enumerate(entries) if e["team"] == team)
        mine.sort(key=lambda ke: ke[1]["pos"])
        n = max(1, len(mine))
        row = min(96, (rect.h - mid.get_height() - 8) // n)
        y = rect.y + mid.get_height() + 8
        av = max(24, min(48, row - 18))
        for k, e in mine:
            r = pygame.Rect(rect.x, y, rect.w, row - 6)
            now = k == d["turn"]
            pygame.draw.rect(surface, PANEL_HI if now else PANEL, r, border_radius=6)
            pygame.draw.rect(surface, GOLD if now else BORDER, r, 2 if now else 1, border_radius=6)
            # Immagine profilo (i bot non ne hanno) + nome.
            A.draw_avatar(surface, e["avatar"] if e["slot"] is not None else 0,
                          (r.x + 6, r.y + 6, av, av), col)
            poke = e["poke"] if e["poke"] is not None else (d["hover"] if now else None)
            if e["slot"] is None:
                name = self.defs[e["poke"]].name if e["poke"] is not None else "bot"
            else:
                name = e["name"] + ("  (tu)" if e["slot"] == self.session.slot else "")
            surface.blit(sm.render(name[:20], True, TEXT if e["slot"] is not None else DIM),
                         (r.x + av + 12, r.y + 6))
            if e["slot"] is None:
                what, wcol = ("bot" if e["poke"] is not None
                              else "sceglie a caso dopo i giocatori"), DIM
            elif e["poke"] is not None:
                what, wcol = self.defs[e["poke"]].name, col
            elif now and poke is not None:
                what, wcol = f"{self.defs[poke].name}?", DIM
            else:
                what, wcol = ("sta scegliendo..." if now else "-"), DIM
            surface.blit(sm.render(what, True, wcol), (r.x + av + 12, r.y + 8 + sm.get_height()))
            if poke is not None:
                img = self._frame(self.idle[poke])
                if img is not None:
                    pic = scale_nearest(img, r.h - 10)
                    if e["poke"] is None:              # solo anteprima: più tenue
                        pic = pic.copy()
                        pic.set_alpha(120)
                    surface.blit(pic, (r.right - pic.get_width() - 6,
                                       r.centery - pic.get_height() // 2))
            y += row

    def _draw_grid(self, surface, d, rect, mid, sm):
        taken = {}
        for e in d["entries"]:
            if e["poke"] is not None:
                taken[e["poke"]] = e["team"]
        gap = 8
        n = len(self.defs)
        rows = (n + COLS - 1) // COLS
        cw = (rect.w - gap * (COLS - 1)) // COLS
        ch = min(int(cw * 1.3), (rect.h - 110) // rows - gap)
        self._cards = []
        for i, pd in enumerate(self.defs):
            r = pygame.Rect(rect.x + (i % COLS) * (cw + gap), rect.y + (i // COLS) * (ch + gap),
                            cw, ch)
            self._cards.append((r, i))
            on = i == self.sel
            pygame.draw.rect(surface, PANEL_HI if on else PANEL, r, border_radius=6)
            frames = self.idle[i]
            img = self._frame(frames) if on else (frames[0][0] if frames else None)
            if img is not None:
                pic = scale_nearest(img, int(min(cw, ch) * 0.6))
                surface.blit(pic, (r.centerx - pic.get_width() // 2,
                                   r.y + int(ch * 0.42) - pic.get_height() // 2))
            nm = sm.render(pd.name, True, TEXT if on else (200, 205, 198))
            surface.blit(nm, (r.centerx - nm.get_width() // 2, r.bottom - nm.get_height() - 6))
            if i in taken:
                veil = pygame.Surface(r.size, pygame.SRCALPHA)
                veil.fill((8, 10, 9, 170))
                surface.blit(veil, r.topleft)
                band = pygame.Rect(r.x, r.centery - 11, r.w, 22)
                pygame.draw.rect(surface, config.TEAM_COLORS[taken[i]], band)
                t = sm.render(f"preso ({TEAM_NAME[taken[i]]})", True, (16, 16, 16))
                surface.blit(t, (band.centerx - t.get_width() // 2,
                                 band.centery - t.get_height() // 2))
            pygame.draw.rect(surface, GOLD if on else BORDER, r, 3 if on else 1, border_radius=6)

        # Sotto le carte: dettagli del Pokémon guardato + pulsante di conferma.
        y = rect.y + rows * (ch + gap) + 6
        pd = self.defs[self.sel]
        nm = mid.render(pd.name, True, GOLD)
        surface.blit(nm, (rect.x, y))
        x = rect.x + nm.get_width() + 14
        for t in pd.types:
            p = sm.render(t, True, (20, 20, 20))
            pr = pygame.Rect(x, y + 2, p.get_width() + 14, p.get_height() + 4)
            pygame.draw.rect(surface, TYPE_COLORS.get(t, (180, 180, 180)), pr, border_radius=8)
            surface.blit(p, (pr.x + 7, pr.y + 2))
            x = pr.right + 6
        surface.blit(sm.render(f"Ruolo: {pd.role}", True, DIM), (x + 8, y + 3))
        y += mid.get_height() + 12
        bh = mid.get_height() + 16
        if self.session.draft_my_turn() and not d["done"]:
            label = "Conferma  (INVIO)" if self._can_lock() else "Già preso: scegline un altro"
            self.buttons.draw(surface, (rect.centerx - 150, y, 300, bh), label, self._lock, mid,
                              enabled=self._can_lock())
