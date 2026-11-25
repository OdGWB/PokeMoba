"""Selezione del personaggio (giocatore singolo) — redesign.

Si arriva qui dal menu dopo aver scelto la mappa. Il giocatore sceglie il suo
Pokémon dal roster; tutti gli altri slot (alleati e avversari) ricevono un
Pokémon CASUALE dal pool, senza ripetizioni (lo fa MatchScene._bot_defs).

Comandi: frecce / clic per scegliere, Tab (o clic sulle pillole) per filtrare
per ruolo, INVIO o doppio clic / pulsante GIOCA per iniziare, ESC per tornare
alla scelta della mappa.
"""
from __future__ import annotations

import pygame

import config
from engine.content import load_pokemon_def
from .. import avatars as A
from .. import flor_fx
from .. import ui_theme as UI
from ..sprites.animdata import parse_anim_data

COLS = 6
# Colori storici: li importano anche altre schermate (draft, tier list).
BG = UI.BG
PANEL = UI.PANEL
PANEL_HI = UI.PANEL_HI
BORDER = UI.BORDER
GOLD = UI.GOLD
TEXT = UI.TEXT
DIM = UI.DIM

# Filtro per RUOLO = corsia (top, giungla, mid, bottom, support). La CATEGORIA
# dei JSON ("combattente", "mago"...) resta scritta sulle carte di selezione.
ROLES = ["top", "giungla", "mid", "bottom", "support"]
ROLE_LABELS = {"top": "Top", "giungla": "Giungla", "mid": "Mid", "bottom": "Bottom",
               "support": "Support"}
# Corsie di ogni linea (per nome della forma base). Chi manca non passa nessun filtro.
LANES = {
    "Litten": ("top",),
    "Scyther": ("top",),
    "Mienfoo": ("top", "mid"),
    "Roggenrola": ("top",),
    "Snivy": ("top", "mid"),
    "Charcadet": ("top", "mid", "bottom"),
    "Rookidee": ("top", "support"),
    "Totodile": ("top", "giungla"),
    "Poliwag": ("top", "support"),
    "Nincada": ("giungla",),
    "Swinub": ("giungla",),
    "Sneasel": ("giungla", "mid"),
    "Teddiursa": ("giungla",),
    "Charmander": ("mid",),
    "Gastly": ("mid",),
    "Hatenna": ("mid",),
    "Magnemite": ("mid",),
    "Eevee": ("mid", "bottom", "support"),
    "Rowlet": ("bottom",),
    "Noibat": ("bottom",),
    "Venonat": ("bottom",),
    "Remoraid": ("bottom",),
    "Delibird": ("bottom",),
    "Duraludon": ("support",),
    "Flabébé": ("support",),
    "Spiritomb": ("support",),
}
# Linee da jungler (le usa anche chi deve sapere solo questo).
JUNGLERS = {n for n, ls in LANES.items() if "giungla" in ls}


def lanes_of(d) -> tuple:
    return LANES.get(d.name, ())


def lanes_label(d) -> str:
    """"Top · Mid" (o "-" se la linea non ha corsie)."""
    return " · ".join(ROLE_LABELS[r] for r in lanes_of(d)) or "-"


def role_matches(d, role) -> bool:
    """Il Pokémon `d` passa il filtro `role` (corsia; None = tutti)?"""
    return role is None or role in lanes_of(d)


def draw_role_chips(surface, x, y, role, defs, k=1.0, max_w=None):
    """Pillole del filtro per ruolo; ritorna [(rect, ruolo)] (ruolo None = Tutti).
    Con max_w vanno a capo se non ci stanno in una riga."""
    S = lambda v: int(v * k)                      # noqa: E731
    x0 = x
    cf = UI.font(max(11, S(12)))
    nf = UI.font(max(9, S(10)))
    out = []
    for ro in [None] + ROLES:
        label = "Tutti" if ro is None else ROLE_LABELS[ro]
        cnt = sum(role_matches(d, ro) for d in defs)
        on = ro == role
        t = cf.render(label, True, GOLD if on else UI.SOFT)
        n = nf.render(str(cnt), True, GOLD if on else DIM)
        r = pygame.Rect(x, y, S(9) * 2 + t.get_width() + S(5) + n.get_width(), S(28))
        if max_w and r.right > x0 + max_w and x > x0:
            x, y = x0, y + S(28) + S(6)
            r.topleft = (x, y)
        if on:
            UI.alpha_rect(surface, (*GOLD, 30), r, radius=r.h // 2)
        pygame.draw.rect(surface, (150, 135, 70) if on else UI.LINE, r, 1, border_radius=r.h // 2)
        surface.blit(t, (r.x + S(9), r.centery - t.get_height() // 2))
        surface.blit(n, (r.x + S(9) + t.get_width() + S(5), r.centery - n.get_height() // 2 + 1))
        out.append((r, ro))
        x = r.right + S(6)
    return out


def evo_line(d) -> str:
    """"Totodile → Croconaw → Feraligatr" (rami: "Weavile o Sneasler")."""
    stages: dict = {}
    for e in d.evolutions:
        stages.setdefault(e.get("stage", 0), [])
        if e.get("name") and e["name"] not in stages[e.get("stage", 0)]:
            stages[e.get("stage", 0)].append(e["name"])
    stages.setdefault(0, [d.name])
    if len(stages) <= 1:
        return "Non si evolve"
    parts = []
    for st in sorted(stages):
        names = stages[st] or [d.name]
        parts.append(f"{len(names)} evoluzioni a scelta" if len(names) > 3 else " o ".join(names))
    return " → ".join(parts)

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


_glow_cache: dict = {}


def _glow(color, w, h):
    """Alone ellittico morbido del colore del tipo (dietro lo sprite grande)."""
    key = (color, w, h)
    if key not in _glow_cache:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        steps = 24
        for i in range(steps):
            f = 1 - i / steps
            a = int(56 * (i / steps) ** 1.5)
            r = pygame.Rect(0, 0, int(w * f), int(h * f))
            r.center = (w // 2, h // 2)
            pygame.draw.ellipse(s, (*color, a), r)
        _glow_cache[key] = s
    return _glow_cache[key]


class CharSelectScene:
    def __init__(self, app, map_index: int):
        self.app = app
        self.map_index = map_index
        self.next_scene = None
        self.sel = 0
        self.role = None             # filtro per ruolo (None = tutti)
        self.t = 0.0
        self.loading = False
        self._drawn_loading = False
        self.defs = [load_pokemon_def(str(app.root / rel)) for rel in config.ROSTER]
        self.idle = [load_idle(d.sprite_dir) for d in self.defs]
        self._evo_idle: dict = {}
        self._scaled: dict = {}
        self._cards: list = []       # (rect, indice) dell'ultimo frame disegnato
        self._chips: list = []       # (rect, ruolo)
        self._play_rect = None
        self._back_rect = None
        self.flower_color = "red"    # Flabébé: colore dei fiori
        self._color_rects: list = []

    # --- filtro -------------------------------------------------------------
    def _visible(self):
        return [i for i, d in enumerate(self.defs) if role_matches(d, self.role)]

    def _set_role(self, role):
        self.role = role
        vis = self._visible()
        if vis and self.sel not in vis:
            self.sel = vis[0]

    def _back(self):
        from .play_scene import PlayScene
        self.next_scene = PlayScene(self.app, self.map_index)

    # Ganci per le sottoclassi (Allenamento): testi dell'intestazione, scena da
    # costruire, controlli in piu' a destra del titolo.
    PLAY_LABEL = "Gioca"
    HINTS = [("frecce", "scegli"), ("Tab", "ruolo"), ("doppio clic", "gioca subito")]

    def _header(self):
        mname = config.MAPS[self.map_index][0]
        ts = 3 if mname == "3v3" else 5
        return ("Mappe", "Scegli il tuo Pokémon",
                f"Mappa {mname} · gli altri {2 * ts - 1} sono bot con un Pokémon a caso")

    def _build_scene(self):
        from .match_scene import MatchScene
        return MatchScene(
            str(self.app.root / config.MAPS[self.map_index][1]),
            str(self.app.root / config.ROSTER[self.sel]),
            flower_color=self.flower_color if self._has_colors() else None)

    def _extra_key(self, ev) -> bool:
        return False

    def _extra_click(self, pos) -> bool:
        return False

    def _draw_extra(self, surface, ox, S, mouse):
        pass

    # --- input ---------------------------------------------------------------
    def handle_events(self, events):
        if self.loading:
            return
        for ev in events:
            vis = self._visible()
            pos = vis.index(self.sel) if self.sel in vis else 0
            if ev.type == pygame.KEYDOWN:
                if self._extra_key(ev):
                    continue
                if ev.key == pygame.K_ESCAPE:
                    self._back()
                elif ev.key == pygame.K_TAB:
                    opts = [None] + ROLES
                    step = -1 if ev.mod & pygame.KMOD_SHIFT else 1
                    self._set_role(opts[(opts.index(self.role) + step) % len(opts)])
                elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                    self.sel = vis[(pos + 1) % len(vis)]
                elif ev.key in (pygame.K_LEFT, pygame.K_a):
                    self.sel = vis[(pos - 1) % len(vis)]
                elif ev.key in (pygame.K_DOWN, pygame.K_s):
                    self.sel = vis[min(len(vis) - 1, pos + COLS)]
                elif ev.key in (pygame.K_UP, pygame.K_w):
                    self.sel = vis[max(0, pos - COLS)]
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self._start()
                elif ev.key in flor_fx.COLOR_KEYS and self._has_colors():
                    self.flower_color = flor_fx.COLORS[flor_fx.COLOR_KEYS[ev.key]]
            elif ev.type == pygame.MOUSEMOTION:
                for r, i in self._cards:
                    if r.collidepoint(ev.pos):
                        self.sel = i
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self._extra_click(ev.pos):
                    continue
                hit = next((c for r, c in self._color_rects if r.collidepoint(ev.pos)), None)
                if hit is not None and self._has_colors():
                    self.flower_color = hit
                    continue
                chip = next((ro for r, ro in self._chips if r.collidepoint(ev.pos)), "none")
                if chip != "none":
                    self._set_role(chip)
                    continue
                if self._play_rect and self._play_rect.collidepoint(ev.pos):
                    self._start()
                elif self._back_rect and self._back_rect.collidepoint(ev.pos):
                    self._back()
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
            self.next_scene = self._build_scene()
            self.next_scene.app = self.app   # "Torna al menu" a fine partita

    # --- disegno -------------------------------------------------------------
    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

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

    def _sc(self, img, side):
        key = (id(img), side)
        if key not in self._scaled:
            self._scaled[key] = scale_nearest(img, side)
        return self._scaled[key]

    def draw_fullres(self, surface, font):
        W, H = surface.get_size()
        surface.fill(BG)
        if self.loading:
            self._draw_loading(surface, W, H)
            return
        k = min(W / 1280, H / 720)
        ox = (W - int(1280 * k)) // 2
        S = lambda v: int(v * k)                      # noqa: E731
        mouse = pygame.mouse.get_pos()
        UI.top_glow(surface, W, H)

        # Intestazione: indietro + titolo + sottotitolo.
        back_label, title, subtitle = self._header()
        self._back_rect = UI.back_button(surface, back_label, ox + S(48), S(28),
                                         hover=self._back_rect is not None
                                         and self._back_rect.collidepoint(mouse))
        tx = self._back_rect.right + S(22)
        tr = UI.title(surface, title, tx, S(20), max(22, S(30)))
        sub = UI.font(max(11, S(12))).render(subtitle, True, DIM)
        surface.blit(sub, (tx, tr.bottom + 2))
        self._draw_extra(surface, ox, S, mouse)

        # Pillole dei ruoli (filtro).
        gx, gy = ox + S(48), S(100)
        self._chips = draw_role_chips(surface, gx, gy, self.role, self.defs, k, max_w=S(700))

        # Griglia delle carte (6 colonne).
        top = self._chips[-1][0].bottom + S(12)
        gap = S(8)
        cw = (S(700) - gap * (COLS - 1)) // COLS
        ch = S(86)
        mid = UI.font(max(10, S(12)), bold=True)
        self._cards = []
        for n_, i in enumerate(self._visible()):
            d = self.defs[i]
            r = pygame.Rect(gx + (n_ % COLS) * (cw + gap), top + (n_ // COLS) * (ch + gap), cw, ch)
            self._cards.append((r, i))
            on = i == self.sel
            pygame.draw.rect(surface, UI.SEL if on else UI.CARD, r, border_radius=S(9))
            pygame.draw.rect(surface, GOLD if on else UI.CARD_LINE, r, 2 if on else 1,
                             border_radius=S(9))
            dot = pygame.Rect(r.x + S(7), r.y + S(7), max(5, S(7)), max(5, S(7)))
            pygame.draw.rect(surface, TYPE_COLORS.get(d.types[0], DIM), dot, border_radius=2)
            frames = self.idle[i]
            img = self._frame(frames) if on else (frames[0][0] if frames else None)
            nm = mid.render(d.name, True, GOLD if on else UI.SOFT)
            if img is not None:
                pic = self._sc(img, S(46))
                area_h = r.h - nm.get_height() - S(12)
                surface.blit(pic, (r.centerx - pic.get_width() // 2,
                                   r.y + S(4) + area_h // 2 - pic.get_height() // 2))
            surface.blit(nm, (r.centerx - nm.get_width() // 2, r.bottom - S(9) - nm.get_height()))

        self._draw_preview(surface, ox, S, mouse)
        UI.hints(surface, self.HINTS,
                 gx, H - S(24) - 22)

    def _draw_preview(self, surface, ox, S, mouse):
        d = self.defs[self.sel]
        panel = pygame.Rect(ox + S(780), S(100), S(452), S(540))
        pygame.draw.rect(surface, UI.CARD, panel, border_radius=S(14))
        pygame.draw.rect(surface, UI.CARD_LINE, panel, 1, border_radius=S(14))
        colors = d.passive == "giardino"
        stage_h = S(210 if colors else 260)

        # Alone del tipo + ombra a terra + sprite grande animato.
        tc = TYPE_COLORS.get(d.types[0], (180, 180, 180))
        g = _glow(tc, int(panel.w * 0.9), int(stage_h * 0.95))
        surface.blit(g, (panel.centerx - g.get_width() // 2, panel.y + stage_h // 2 - g.get_height() // 2 + S(14)))
        img = self._frame(self.idle[self.sel])
        foot = panel.y + stage_h - S(30)
        sh = pygame.Rect(0, 0, S(150), S(18))
        sh.center = (panel.centerx, foot)
        UI.alpha_rect(surface, (0, 0, 0, 90), sh, radius=sh.h // 2)
        if img is not None:
            pic = self._sc(img, S(130 if colors else 150))
            surface.blit(pic, (panel.centerx - pic.get_width() // 2, foot - pic.get_height() + S(4)))

        # Tu: immagine profilo + nickname.
        prof = getattr(self.app, "profile", None) or {}
        f12 = UI.font(max(10, S(12)), bold=True)
        f11 = UI.font(max(10, S(11)))
        you = f12.render(prof.get("name", "Tu"), True, TEXT)
        st = f11.render("sei tu", True, DIM)
        chip = pygame.Rect(panel.x + S(14), panel.y + S(14), S(4) + S(26) + S(8) + you.get_width()
                           + S(8) + st.get_width() + S(10), S(34))
        UI.alpha_rect(surface, (*BG, 150), chip, radius=S(8))
        A.draw_avatar(surface, prof.get("avatar", 0), (chip.x + S(4), chip.y + S(4), S(26), S(26)), GOLD)
        surface.blit(you, (chip.x + S(38), chip.centery - you.get_height() // 2))
        surface.blit(st, (chip.x + S(46) + you.get_width(), chip.centery - st.get_height() // 2))

        # Nome, tipi, ruolo.
        y = panel.y + stage_h + S(4)
        nr = UI.title(surface, d.name, panel.centerx, y, max(24, S(36)), center=True, shadow=0)
        y = nr.bottom + S(10)
        pf = UI.font(max(10, S(11)), bold=True)
        pills = [pf.render(t, True, (20, 20, 20)) for t in d.types]
        tw = sum(p.get_width() + S(20) for p in pills) + S(6) * (len(pills) - 1)
        x = panel.centerx - tw // 2
        for t, p in zip(d.types, pills):
            r = pygame.Rect(x, y, p.get_width() + S(20), S(22))
            pygame.draw.rect(surface, TYPE_COLORS.get(t, (180, 180, 180)), r, border_radius=r.h // 2)
            surface.blit(p, (r.centerx - p.get_width() // 2, r.centery - p.get_height() // 2))
            x = r.right + S(6)
        y += S(22) + S(10)
        rf = UI.font(max(11, S(13)))
        a = rf.render("Ruolo · ", True, UI.SOFT)
        b = UI.font(max(11, S(13)), bold=True).render(
            f"{lanes_label(d)}  ({d.role or '-'})", True, TEXT)
        rx = panel.centerx - (a.get_width() + b.get_width()) // 2
        surface.blit(a, (rx, y))
        surface.blit(b, (rx + a.get_width(), y))
        y += a.get_height() + S(14)

        # Linea evolutiva (sprite fermi, centrati).
        evos = [e for e in d.evolutions if e.get("sprite_dir")
                and e.get("sprite_dir") != d.sprite_dir]
        if evos:
            side = max(22, min(S(40), (panel.w - S(40)) // len(evos) - S(8)))
            total = len(evos) * side + (len(evos) - 1) * S(8)
            x = panel.centerx - total // 2
            for e in evos:
                fr = self._evo_frames(e["sprite_dir"])
                if fr:
                    pic = self._sc(fr[0][0], side)
                    surface.blit(pic, (x + (side - pic.get_width()) // 2, y + side - pic.get_height()))
                x += side + S(8)
            y += side + S(6)
        ev = UI.font(max(10, S(12))).render(evo_line(d), True, DIM)
        surface.blit(ev, (panel.centerx - ev.get_width() // 2, y))
        y += ev.get_height() + S(12)

        # Flabébé: scelta del colore dei fiori (resta per tutta la partita).
        self._color_rects = []
        if colors:
            self._color_rects = flor_fx.draw_color_picker(
                surface, panel.x + S(20), y, panel.w - S(40), self.flower_color,
                UI.font(max(11, S(12))), UI.font(max(11, S(12))))

        # Pulsante Gioca in fondo al pannello.
        br = pygame.Rect(panel.x + S(20), panel.bottom - S(20) - S(52), panel.w - S(40), S(52))
        self._play_rect = UI.primary_button(surface, br, self.PLAY_LABEL, "Invio",
                                            hover=br.collidepoint(mouse), size=max(14, S(17)))

    def _draw_loading(self, surface, W, H):
        from .. import loading_screen
        loading_screen.draw(surface, self.t, "Caricamento della mappa...")
        self._drawn_loading = True
