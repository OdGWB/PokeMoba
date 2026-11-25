"""Enciclopedia in gioco: mosse e passive di ogni linea del roster.

Due viste:
- GRIGLIA delle linee (config.ROSTER): ritratto Idle NEAREST, nome, ruolo;
  filtro per ruolo/corsia (Tab / Maiusc+Tab o clic) e ricerca scrivendo il nome.
- SCHEDA della linea: forme (livello, tipi, ruolo, requisito d'evoluzione),
  come si gioca e consigli, passive, poi le mosse per casella Q/W/E/R
  (iniziale, potenziamenti a scelta, mosse proprie di una forma).

I NUMERI delle mosse si leggono dai JSON del roster (data/pokemon/*.json): sono
sempre quelli del gioco. I testi (riassunto, consigli, passive) stanno in
data/encyclopedia.json. La scheda si dipinge UNA volta su una tela alta (in
cache per dimensione della finestra); a ogni frame solo un blit della parte
visibile. Solo lettura: nessuna logica di gioco.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pygame

import config
from .. import ui_theme as UI
from ..move_preview import CYCLE, MovePreview, describe_move
from .. import status_glossary as SG


class _StatusPage:
    """Segnaposto per la pagina "Stati ed effetti" (al posto di una linea aperta)."""
    stem = "_status"


STATUS_PAGE = _StatusPage()
from .char_select_scene import (TYPE_COLORS, draw_role_chips, evo_line, lanes_label, load_idle, role_matches,
                                scale_nearest, ROLES, config_root)

GOLD, TEXT, DIM = UI.GOLD, UI.TEXT, UI.DIM

TYPE_IT = {
    "Normal": "Normale", "Fire": "Fuoco", "Water": "Acqua", "Grass": "Erba",
    "Electric": "Elettro", "Ice": "Ghiaccio", "Fighting": "Lotta", "Poison": "Veleno",
    "Ground": "Terra", "Flying": "Volante", "Psychic": "Psico", "Bug": "Coleottero",
    "Rock": "Roccia", "Ghost": "Spettro", "Dragon": "Drago", "Dark": "Buio",
    "Steel": "Acciaio", "Fairy": "Folletto",
}
CAT_IT = {"physical": "Fisica", "special": "Speciale", "none": "Stato"}
ITEM_IT = {"king_rock": "Roccia di Re", "metal_coat": "Metalcoperta",
           "black_augurite": "Augite Nera"}
SLOT_IT = {"Q": "Q", "W": "W", "E": "E", "R": "R  (ultimate, dal liv. 8)"}


# --- dati ---------------------------------------------------------------------------
def _load_json(rel):
    try:
        with open(config_root() / rel, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_lines():
    """Le linee del roster come SimpleNamespace (name, role, raw, stem, enc)."""
    enc = _load_json("data/encyclopedia.json").get("lines", {})
    out = []
    for rel in config.ROSTER:
        raw = _load_json(rel)
        if not raw:
            continue
        stem = rel.rsplit("/", 1)[-1][:-5]
        out.append(SimpleNamespace(name=raw.get("name", stem), role=raw.get("role", ""),
                                   raw=raw, stem=stem, enc=enc.get(stem, {}),
                                   sprite_dir=raw.get("sprite_dir"),
                                   evolutions=raw.get("evolutions", [])))
    return out


def _dur(v):
    if isinstance(v, dict):
        v = v.get("duration")
    if isinstance(v, list):
        v = v[-1] if v else None
    if isinstance(v, (int, float)) and v:
        return f" {_num(v)} s"
    return ""


def _num(v):
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def _nums(v):
    if isinstance(v, list):
        return "/".join(_num(x) for x in v)
    return _num(v)


def _pct(m):
    if isinstance(m, list):
        m = m[-1] if m else 1
    try:
        return int(round((float(m) - 1) * 100))
    except (TypeError, ValueError):
        return 0


def _buff(label, v):
    """Effetto {mult, duration} -> "+25% Attacco 5 s"."""
    m = v.get("mult") if isinstance(v, dict) else v
    p = _pct(m) if isinstance(m, (int, float, list)) and (not isinstance(m, (int, float)) or m > 0.0) else 0
    if isinstance(m, (int, float)) and m < 1 and label != "Velocita' d'attacco":
        p = int(round(m * 100))
    sign = "+" if p >= 0 else ""
    return f"{sign}{p}% {label}{_dur(v)}" if p else f"{label}{_dur(v)}"


def effect_tags(m):
    """Le voci leggibili degli effetti di una mossa (solo quelle note)."""
    eff = m.get("effects") or {}
    tags = []
    simple = [("stun", "Stordisce"), ("root", "Immobilizza"), ("confuse", "Confonde"),
              ("sleep", "Addormenta"), ("blind", "Acceca"), ("taunt", "Provoca"),
              ("fear", "Spaventa"), ("freeze", "Congela"), ("silence", "Silenzia"),
              ("paralyze", "Paralizza"), ("para", "Paralizza"), ("airborne", "Lancia in aria"),
              ("untargetable", "Non bersagliabile"), ("burn", "Scotta"),
              ("healcut", "Cure ridotte"), ("itemlock", "Disattiva gli oggetti"),
              ("self_root", "Resti fermo"), ("dashlock", "Blocca gli scatti")]
    for k, lab in simple:
        if k in eff:
            tags.append(lab + _dur(eff[k]))
    if "slow" in eff:
        s = eff["slow"]
        mult = s.get("mult") if isinstance(s, dict) else s
        try:
            tags.append(f"Rallenta {int(round((1 - float(mult)) * 100))}%{_dur(s)}")
        except (TypeError, ValueError):
            tags.append("Rallenta")
    if "poison" in eff:
        p = eff["poison"]
        tags.append(f"Avvelena{_dur(p)}" + (f" ({_nums(p['dps'])}/s)" if isinstance(p, dict) and "dps" in p else ""))
    if "push" in eff:
        tags.append(f"Respinge {_num(eff['push'])} tile" if isinstance(eff["push"], (int, float)) else "Respinge")
    if "knockback" in eff:
        tags.append("Respinge")
    if "heal" in eff:
        tags.append(f"Cura {_nums(eff['heal'])}")
    if "shield" in eff:
        s = eff["shield"]
        tags.append(f"Scudo {_nums(s.get('amount', '')) if isinstance(s, dict) else _nums(s)}{_dur(s)}")
    if "atk" in eff:
        tags.append(_buff("Attacco", eff["atk"]))
    if "def" in eff:
        tags.append(_buff("Difesa", eff["def"]))
    if "all_stats" in eff:
        tags.append(_buff("a tutte le statistiche", eff["all_stats"]))
    if "speed" in eff:
        tags.append(_buff("Velocita'", eff["speed"]) if isinstance(eff["speed"], dict)
                    else f"+{int(round(float(eff['speed']) * 100))}% Velocita'")
    if "attack_speed" in eff:
        a = eff["attack_speed"]
        if isinstance(a, (int, float)):
            tags.append(f"+{int(round(a * 100))}% Velocita' d'attacco")
    if "spdef_debuff" in eff:
        tags.append("Riduce la Dif. Sp." + _dur(eff["spdef_debuff"]))
    if "def_debuff" in eff:
        tags.append("Riduce la Difesa" + _dur(eff["def_debuff"]))
    if "recoil" in eff:
        tags.append("Contraccolpo")
    if "channel" in eff:
        tags.append(f"Carica {_num(eff['channel'])} s")
    if "delay" in eff:
        tags.append(f"Ritardo {_num(eff['delay'])} s")
    if "duration" in eff and isinstance(eff["duration"], (int, float)) and not tags:
        tags.append(f"Dura {_num(eff['duration'])} s")
    return tags


SHAPE_IT = {"cone": "cono", "projectile": "proiettile", "dash": "scatto", "area": "area",
            "buff": "potenziamento"}
TARGET_IT = {"direction": "in una direzione", "point": "su un punto", "self": "su di se'",
             "ally": "su un alleato", "unit": "su un bersaglio"}


def move_lines(m):
    """[(testo, colore)] con le statistiche di una mossa (tutte righe brevi)."""
    out = []
    shape = SHAPE_IT.get(m.get("shape"))
    how = (shape.capitalize() + " " + TARGET_IT.get(m.get("target"), "")).strip() if shape \
        else TARGET_IT.get(m.get("target"), "").capitalize()
    geo = []
    if m.get("range"):
        geo.append(f"gittata {_num(m['range'])}")
    if m.get("radius") and m.get("shape") != "projectile":
        geo.append(f"raggio {_num(m['radius'])}")
    if m.get("angle"):
        geo.append(f"angolo {_num(m['angle'])}°")
    if m.get("charges"):
        geo.append(f"{m['charges']} cariche")
    out.append(((how + ("  ·  " if how and geo else "") + ", ".join(geo)), UI.SOFT))
    pw = m.get("power") or []
    stat = "Dif" if m.get("scale") == "defense" else ("Att. Sp." if m.get("category") == "special" else "Att.")
    if pw and any(pw):
        txt = "Potenza " + _nums(pw)
        if m.get("ratio"):
            txt += f"  (+{_num(m['ratio'])} x {stat})"
        out.append((txt, TEXT))
    if m.get("cooldown"):
        out.append(("Ricarica " + _nums(m["cooldown"]) + " s", DIM))
    tags = effect_tags(m)
    if tags:
        out.append(("Effetti: " + ", ".join(tags), (190, 210, 150)))
    return out


def requirement(line, evo, siblings):
    """Testo del requisito di una forma ("liv. 8 · con Roccia di Re")."""
    raw = line.raw
    req = evo.get("requires") or {}
    parts = [f"liv. {evo.get('level', 1)}"]
    if "armature" in req:
        parts.append("barra Fausta di Armature piu' alta")
    elif "choices" in req:
        ch = []
        for slot in ("Q", "W", "E"):
            ups = (raw.get("moves", {}).get(slot) or {}).get("upgrades", [])
            i = req["choices"].get(slot, 0)
            if i < len(ups):
                ch.append(f"{slot} {ups[i].get('name', '?')}")
        parts.append("scelte " + ", ".join(ch))
    elif "has_item" in req:
        parts.append("con " + ITEM_IT.get(req["has_item"], req["has_item"]))
    elif "evo_item" in req:
        parts.append("comprando " + ITEM_IT.get(req["evo_item"], req["evo_item"]))
    elif "oro" in req:
        parts.append("piu' oro dai neutrali")
    elif len(siblings) > 1:
        parts.append("altrimenti")
    return " · ".join(parts)


# --- font e testo -----------------------------------------------------------------------
def _wrap(f, text, width):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if f.size(t)[0] <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


_portraits: dict = {}


def portrait(sprite_dir, side):
    """Primo fotogramma Idle scalato NEAREST (in cache)."""
    key = (sprite_dir, side)
    if key not in _portraits:
        frames = load_idle(sprite_dir) if sprite_dir else []
        _portraits[key] = scale_nearest(frames[0][0], side) if frames else None
    return _portraits[key]


def type_chip(surface, x, y, t, f):
    col = TYPE_COLORS.get(t, (120, 120, 120))
    tx = f.render(TYPE_IT.get(t, t), True, (20, 20, 20))
    r = pygame.Rect(x, y, tx.get_width() + 12, tx.get_height() + 4)
    pygame.draw.rect(surface, col, r, border_radius=r.h // 2)
    surface.blit(tx, (r.x + 6, r.y + 2))
    return r


# --- scena --------------------------------------------------------------------------------
class EncyclopediaScene:
    def __init__(self, app, back=None):
        self.app = app
        self.back = back
        self.next_scene = None
        self.lines = load_lines()
        self.role = None
        self.query = ""
        self.sel = 0
        self.open = None            # linea aperta (scheda) o None (griglia)
        self.scroll = 0
        self._canvas = None         # (chiave, Surface, altezza usata)
        self._cards = []
        self._chips = []
        self._back_rect = None
        self._status_btn = None     # pulsante "Stati ed effetti" nella griglia
        self.move_text = _load_json("data/encyclopedia.json").get("moves", {}) or {}
        self._move_rects = []       # (Rect sulla tela, mossa, cartella sprite)
        self._mouse = None
        self._hover = None          # id della mossa sotto il mouse
        self._hover_t0 = 0
        self._preview = MovePreview()

    # --- elenco filtrato -----------------------------------------------------------------
    def _shown(self):
        q = self.query.lower()
        return [ln for ln in self.lines if role_matches(ln, self.role)
                and (not q or q in ln.name.lower() or any(
                    q in (e.get("name") or "").lower() for e in ln.raw.get("evolutions", [])))]

    def _go_back(self):
        if self.open is not None:
            self.open = None
            self._canvas = None
            return
        if self.back is not None:
            self.next_scene = self.back
        else:
            from .menu_scene import MenuScene
            self.next_scene = MenuScene(self.app)

    def _open(self, ln):
        self.open = ln
        self.scroll = 0
        self._canvas = None

    # --- input -------------------------------------------------------------------------
    def handle_events(self, events):
        shown = self._shown()
        cols = 5
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self._back_rect and self._back_rect.collidepoint(ev.pos):
                    self._go_back()
                    continue
                if self.open is None:
                    if self._status_btn and self._status_btn.collidepoint(ev.pos):
                        self._open(STATUS_PAGE)
                        continue
                    for r, ro in self._chips:
                        if r.collidepoint(ev.pos):
                            self.role, self.sel = ro, 0
                    for r, i in self._cards:
                        if r.collidepoint(ev.pos) and i < len(shown):
                            self.sel = i
                            self._open(shown[i])
            elif ev.type == pygame.MOUSEMOTION and self.open is not None:
                self._mouse = ev.pos
            elif ev.type == pygame.MOUSEMOTION and self.open is None:
                for r, i in self._cards:
                    if r.collidepoint(ev.pos):
                        self.sel = i
            elif ev.type == pygame.MOUSEWHEEL and self.open is not None:
                self.scroll -= ev.y * 70
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self._go_back()
                elif self.open is not None:
                    page = self.app.screen.get_height() - 120 if hasattr(self.app, "screen") else 500
                    if ev.key in (pygame.K_DOWN, pygame.K_s):
                        self.scroll += 60
                    elif ev.key in (pygame.K_UP, pygame.K_w):
                        self.scroll -= 60
                    elif ev.key in (pygame.K_PAGEDOWN, pygame.K_SPACE):
                        self.scroll += page
                    elif ev.key == pygame.K_PAGEUP:
                        self.scroll -= page
                    elif ev.key == pygame.K_HOME:
                        self.scroll = 0
                    elif ev.key == pygame.K_END:
                        self.scroll = 10 ** 6
                    elif (ev.key in (pygame.K_LEFT, pygame.K_RIGHT) and shown
                          and self.open is not STATUS_PAGE):
                        # scorri tra le linee senza tornare alla griglia
                        i = next((j for j, ln in enumerate(shown) if ln is self.open), 0)
                        i = (i + (1 if ev.key == pygame.K_RIGHT else -1)) % len(shown)
                        self.sel = i
                        self._open(shown[i])
                else:
                    if ev.key == pygame.K_F1:
                        self._open(STATUS_PAGE)
                    elif ev.key == pygame.K_TAB:
                        opts = [None] + ROLES
                        d = -1 if ev.mod & pygame.KMOD_SHIFT else 1
                        self.role = opts[(opts.index(self.role) + d) % len(opts)]
                        self.sel = 0
                    elif ev.key == pygame.K_BACKSPACE:
                        self.query = self.query[:-1]
                        self.sel = 0
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if shown:
                            self._open(shown[min(self.sel, len(shown) - 1)])
                    elif ev.key == pygame.K_RIGHT:
                        self.sel = min(len(shown) - 1, self.sel + 1)
                    elif ev.key == pygame.K_LEFT:
                        self.sel = max(0, self.sel - 1)
                    elif ev.key == pygame.K_DOWN:
                        self.sel = min(len(shown) - 1, self.sel + cols)
                    elif ev.key == pygame.K_UP:
                        self.sel = max(0, self.sel - cols)
                    elif ev.unicode and ev.unicode.isprintable() and len(self.query) < 16:
                        self.query += ev.unicode
                        self.sel = 0

    def fixed_update(self):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(UI.BG)

    def hud_lines(self):
        return []

    # --- disegno --------------------------------------------------------------------------
    def draw_fullres(self, surface, font):
        W, H = surface.get_size()
        surface.fill(UI.BG)
        UI.top_glow(surface, W, H)
        if self.open is None:
            self._draw_grid(surface, W, H)
        else:
            self._draw_detail(surface, W, H)

    def _draw_grid(self, surface, W, H):
        k = H / 720
        S = lambda v: int(v * k)                    # noqa: E731
        self._back_rect = UI.back_button(surface, "Menu", S(40), S(24))
        mp = pygame.mouse.get_pos() if pygame.mouse.get_focused() else (-1, -1)
        bw, bh = max(190, S(230)), max(34, S(38))
        br = pygame.Rect(W - S(40) - bw, S(24), bw, bh)
        self._status_btn = UI.primary_button(surface, br, "Stati ed effetti", key="F1",
                                             hover=br.collidepoint(mp), size=max(13, S(15)))
        r = UI.title(surface, "Enciclopedia", S(40), S(70), max(30, S(40)), shadow=max(2, S(3)))
        sub = UI.font(max(12, S(13))).render(
            "mosse e passive di ogni linea · numeri presi dal gioco", True, DIM)
        surface.blit(sub, (r.right + S(18), r.bottom - sub.get_height() - S(6)))
        self._chips = draw_role_chips(surface, S(40), S(132), self.role, self.lines, k)
        # ricerca
        qf = UI.font(max(12, S(13)))
        q = qf.render(("Cerca: " + self.query + "_") if self.query else "Scrivi per cercare...",
                      True, TEXT if self.query else UI.FAINT)
        surface.blit(q, (W - S(40) - q.get_width(), S(138)))

        shown = self._shown()
        self.sel = max(0, min(self.sel, len(shown) - 1))
        cols = 5
        gap = S(8)
        x0, y0 = S(40), S(176)
        cw = (W - 2 * x0 - gap * (cols - 1)) // cols
        ch = S(86)
        nf = UI.font(max(13, S(16)), bold=True)
        rf = UI.font(max(10, S(12)))
        self._cards = []
        for i, ln in enumerate(shown):
            cx = x0 + (i % cols) * (cw + gap)
            cy = y0 + (i // cols) * (ch + gap)
            if cy + ch > H - S(40):
                break
            rr = pygame.Rect(cx, cy, cw, ch)
            on = i == self.sel
            pygame.draw.rect(surface, UI.SEL if on else UI.CARD, rr, border_radius=8)
            pygame.draw.rect(surface, GOLD if on else UI.CARD_LINE, rr, 1, border_radius=8)
            self._cards.append((rr, i))
            img = portrait(ln.sprite_dir, S(64))
            if img:
                surface.blit(img, (rr.x + S(10) + (S(64) - img.get_width()) // 2,
                                   rr.centery - img.get_height() // 2))
            tx = rr.x + S(84)
            t = nf.render(ln.name, True, GOLD if on else TEXT)
            surface.blit(t, (tx, rr.y + S(14)))
            surface.blit(rf.render(ln.role, True, DIM), (tx, rr.y + S(40)))
            yy = rr.y + S(62)
            xx = tx
            for ty in ln.raw.get("types", []):
                c = type_chip(surface, xx, yy, ty, UI.font(max(9, S(10)), bold=True))
                xx = c.right + S(4)
        if not shown:
            t = UI.font(max(13, S(15))).render("Nessuna linea trovata.", True, DIM)
            surface.blit(t, (x0, y0 + S(20)))
        UI.hints(surface, [("Invio", "apri"), ("Tab", "ruolo"), ("F1", "stati"), ("Esc", "menu")],
                 S(40), H - S(32) - 6)

    # --- scheda ----------------------------------------------------------------------------
    def _draw_detail(self, surface, W, H):
        key = (self.open.stem, W, H)
        status = self.open is STATUS_PAGE
        if self._canvas is None or self._canvas[0] != key:
            canvas = pygame.Surface((W, H * 8))
            canvas.fill(UI.BG)
            if status:
                self._move_rects = []
                end = self._paint_status(canvas, W, H)
            else:
                end = self._paint(canvas, self.open, W, H)
            self._canvas = (key, canvas, end)
        _, canvas, end = self._canvas
        k = H / 720
        bar = int(56 * k)
        view_h = H - bar
        self.scroll = max(0, min(self.scroll, max(0, end - view_h)))
        surface.blit(canvas, (0, 0), pygame.Rect(0, self.scroll, W, view_h))
        if end > view_h:          # barra di scorrimento
            th = max(30, int(view_h * view_h / end))
            ty = int((view_h - th) * self.scroll / max(1, end - view_h))
            pygame.draw.rect(surface, UI.LINE, (W - 10, 0, 4, view_h), border_radius=2)
            pygame.draw.rect(surface, GOLD, (W - 10, ty, 4, th), border_radius=2)
        # barra fissa in basso
        pygame.draw.rect(surface, UI.PANEL, (0, H - bar, W, bar))
        pygame.draw.line(surface, UI.LINE, (0, H - bar), (W, H - bar))
        self._back_rect = UI.back_button(surface, "Elenco", int(40 * k), H - bar + (bar - 34) // 2)
        UI.hints(surface, [("↑↓", "scorri")] + ([] if status else [("←→", "linea")])
                 + [("Esc", "elenco")],
                 self._back_rect.right + int(30 * k), H - bar + (bar - 22) // 2)
        if end > view_h and self.scroll < end - view_h - 4:
            t = UI.font(12).render("▼ scorri per altre informazioni", True, DIM)
            surface.blit(t, (W - t.get_width() - 24, H - bar + (bar - t.get_height()) // 2))
        self._draw_hover(surface, view_h, k)

    def _draw_hover(self, surface, view_h, k):
        """Mossa sotto il mouse: bordo d'oro + finestrella con mira e lancio."""
        hit = None
        if self._mouse is not None and self._mouse[1] < view_h:
            mx, my = self._mouse[0], self._mouse[1] + self.scroll
            for r, m, sd in self._move_rects:
                if r.collidepoint(mx, my):
                    hit = (r, m, sd)
                    break
        if hit is None:
            self._hover = None
            return
        r, m, sd = hit
        now = pygame.time.get_ticks()
        hid = (m.get("id"), id(m))
        if hid != self._hover:
            self._hover = hid
            self._hover_t0 = now
            self._hover_m = dict(m, _col=TYPE_COLORS.get(m.get("type"), (200, 200, 200)))
        on = r.move(0, -self.scroll).clip(pygame.Rect(0, 0, surface.get_width(), view_h))
        pygame.draw.rect(surface, GOLD, on, 2, border_radius=6)
        self._preview.draw(surface, self._hover_m, portrait(sd, 24), (now - self._hover_t0) % CYCLE,
                           self._mouse, view_h, k,
                           (UI.font(max(13, int(15 * k)), bold=True), UI.font(max(11, int(12 * k)))),
                           (GOLD, TEXT, DIM, UI.PANEL, UI.LINE), avoid=on)

    def _paint(self, cv, ln, W, H):
        """Dipinge la scheda sulla tela; ritorna l'altezza usata."""
        k = H / 720
        S = lambda v: int(v * k)                    # noqa: E731
        raw, enc = ln.raw, ln.enc
        self._move_rects = []
        x0 = S(48)
        inner = W - 2 * x0
        f_h = UI.font(max(15, S(19)), bold=True)
        f_b = UI.font(max(13, S(15)), bold=True)
        f_t = UI.font(max(12, S(14)))
        f_s = UI.font(max(11, S(13)))
        f_c = UI.font(max(9, S(11)), bold=True)
        lh = f_t.get_linesize()
        y = S(28)

        # intestazione
        img = portrait(ln.sprite_dir, S(96))
        if img:
            cv.blit(img, (x0 + (S(96) - img.get_width()) // 2, y + (S(96) - img.get_height()) // 2))
        hx = x0 + S(120)
        r = UI.title(cv, ln.name, hx, y, max(28, S(36)), shadow=max(2, S(3)))
        cv.blit(f_t.render(evo_line(ln), True, UI.SOFT), (hx, r.bottom + S(6)))
        yy = r.bottom + S(6) + lh + S(4)
        cv.blit(f_s.render("Ruolo: " + lanes_label(ln) + "   ·   Categoria: " + raw.get("role", ""),
                            True, DIM), (hx, yy))
        y += S(112)

        def section(title_txt, y):
            t = f_h.render(title_txt, True, GOLD)
            cv.blit(t, (x0, y))
            yb = y + t.get_height() + S(4)
            pygame.draw.line(cv, UI.LINE, (x0, yb), (x0 + inner, yb))
            return yb + S(10)

        def para(text, y, x=x0, width=inner, col=TEXT, f=f_t):
            for line in _wrap(f, text, width):
                cv.blit(f.render(line, True, col), (x, y))
                y += f.get_linesize()
            return y

        # come si gioca
        if enc.get("summary") or enc.get("tips"):
            y = section("Come si gioca", y)
            if enc.get("summary"):
                y = para(enc["summary"], y) + S(6)
            for tip in enc.get("tips", []):
                pygame.draw.rect(cv, GOLD, (x0 + S(4), y + lh // 2 - 2, 4, 4))
                y = para(tip, y, x=x0 + S(18), width=inner - S(18), col=UI.SOFT)
            y += S(14)

        # forme
        evos = raw.get("evolutions") or [{"name": raw.get("name"), "level": 1,
                                         "types": raw.get("types", []), "role": raw.get("role"),
                                         "sprite_dir": raw.get("sprite_dir")}]
        y = section("Forme", y)
        cw, chh, gap = S(270), S(108), S(10)
        per_row = max(1, (inner + gap) // (cw + gap))
        for i, e in enumerate(evos):
            sib = [o for o in evos if o.get("stage") == e.get("stage")]
            cx = x0 + (i % per_row) * (cw + gap)
            cy = y + (i // per_row) * (chh + gap)
            rr = pygame.Rect(cx, cy, cw, chh)
            pygame.draw.rect(cv, UI.CARD, rr, border_radius=8)
            pygame.draw.rect(cv, UI.CARD_LINE, rr, 1, border_radius=8)
            im = portrait(e.get("sprite_dir"), S(56))
            if im:
                cv.blit(im, (rr.x + S(8) + (S(56) - im.get_width()) // 2,
                             rr.centery - im.get_height() // 2))
            tx = rr.x + S(72)
            cv.blit(f_b.render(e.get("name", "?"), True, TEXT), (tx, rr.y + S(8)))
            xx = tx
            for ty in e.get("types", []):
                c = type_chip(cv, xx, rr.y + S(32), ty, f_c)
                xx = c.right + S(4)
            cv.blit(f_s.render(e.get("role") or raw.get("role", ""), True, DIM), (xx + S(4), rr.y + S(32)))
            req = requirement(ln, e, sib)
            rl = _wrap(f_s, req, cw - S(80))[:3]
            for j, line in enumerate(rl):
                cv.blit(f_s.render(line, True, UI.SOFT), (tx, rr.y + S(54) + j * f_s.get_linesize()))
        y += ((len(evos) + per_row - 1) // per_row) * (chh + gap) + S(14)

        # passive
        pids = []
        for e in [raw] + list(raw.get("evolutions", [])):
            p = e.get("passive")
            if p and p not in pids:
                pids.append(p)
        y = section("Passive", y)
        texts = enc.get("passives", {})
        for pid in pids:
            info = texts.get(pid, {})
            owners = [e.get("name") for e in raw.get("evolutions", []) if e.get("passive") == pid]
            t = f_b.render(info.get("name", pid), True, (150, 220, 170))
            cv.blit(t, (x0, y))
            if owners and len(pids) > 1:
                cv.blit(f_s.render("  " + ", ".join(dict.fromkeys(owners)), True, DIM),
                        (x0 + t.get_width(), y + (t.get_height() - f_s.get_height()) // 2))
            y += t.get_height() + S(2)
            y = para(info.get("text", "Descrizione non disponibile."), y, x=x0 + S(18),
                     width=inner - S(18), col=UI.SOFT) + S(10)
        y += S(6)

        # mosse
        y = section("Mosse", y)
        note = ("Ogni casella parte dalla mossa iniziale; salendo di livello scegli UNO dei "
                "potenziamenti. I numeri sono per grado (1/2/3/4; la R ha 3 gradi). "
                "Passa il mouse su una mossa per vedere come si mira e come parte.")
        y = para(note, y, col=DIM, f=f_s) + S(10)
        base_moves = raw.get("moves", {})
        for slot in ("Q", "W", "E", "R"):
            groups = []
            s = base_moves.get(slot) or {}
            if s.get("base"):
                groups.append(("Iniziale", [s["base"]], ln.sprite_dir))
            if s.get("upgrades"):
                groups.append(("Potenziamenti (a scelta)", s["upgrades"], ln.sprite_dir))
            seen = {m.get("id") for _, ms, _ in groups for m in ms}
            for e in raw.get("evolutions", []):
                es = (e.get("moves") or {}).get(slot) or {}
                own = [m for m in ([es.get("base")] if es.get("base") else []) + es.get("upgrades", [])
                       if m and m.get("id") not in seen]
                if own:
                    seen |= {m.get("id") for m in own}
                    groups.append((f"Solo {e.get('name')}", own, e.get("sprite_dir") or ln.sprite_dir))
            if not groups:
                continue
            # casella del tasto
            kr = pygame.Rect(x0, y, S(34), S(34))
            pygame.draw.rect(cv, UI.PANEL_HI, kr, border_radius=6)
            pygame.draw.rect(cv, GOLD, kr, 1, border_radius=6)
            kt = f_h.render(slot, True, GOLD)
            cv.blit(kt, (kr.centerx - kt.get_width() // 2, kr.centery - kt.get_height() // 2))
            st = f_s.render(SLOT_IT[slot][1:].strip(), True, DIM) if slot == "R" else None
            if st:
                cv.blit(st, (kr.right + S(10), kr.centery - st.get_height() // 2))
            y = kr.bottom + S(8)
            for label, ms, sd in groups:
                cv.blit(f_s.render(label.upper(), True, UI.FAINT), (x0 + S(46), y))
                y += f_s.get_linesize() + S(4)
                for m in ms:
                    y = self._paint_move(cv, m, x0 + S(46), y, inner - S(46), S, f_b, f_s, f_c, sd)
            y += S(12)
        return y + S(30)

    def _paint_status(self, cv, W, H):
        """Pagina "Stati ed effetti": ogni stato con nome colorato e spiegazione."""
        k = H / 720
        S = lambda v: int(v * k)                    # noqa: E731
        x0 = S(48)
        inner = W - 2 * x0
        f_h = UI.font(max(15, S(19)), bold=True)
        f_b = UI.font(max(13, S(15)), bold=True)
        f_t = UI.font(max(12, S(14)))
        y = S(28)
        r = UI.title(cv, "Stati ed effetti", x0, y, max(28, S(36)), shadow=max(2, S(3)))
        y = r.bottom + S(8)
        for line in _wrap(f_t, "Cosa subisce un Pokémon colpito. Nelle schede delle mosse la riga "
                          "\"Sul bersaglio\" dice quali di questi stati infligge ogni mossa.",
                          inner):
            cv.blit(f_t.render(line, True, DIM), (x0, y))
            y += f_t.get_linesize()
        y += S(14)
        name_w = S(300)
        for key, name, col, text in SG.GLOSSARY:
            if col is None:            # intestazione di gruppo
                y += S(8)
                t = f_h.render(name, True, GOLD)
                cv.blit(t, (x0, y))
                yb = y + t.get_height() + S(4)
                pygame.draw.line(cv, UI.LINE, (x0, yb), (x0 + inner, yb))
                y = yb + S(6)
                for line in _wrap(f_t, text, inner):
                    cv.blit(f_t.render(line, True, DIM), (x0, y))
                    y += f_t.get_linesize()
                y += S(8)
                continue
            body = _wrap(f_t, text, inner - name_w - S(28))
            hh = max(f_b.get_linesize(), len(body) * f_t.get_linesize()) + S(16)
            card = pygame.Rect(x0, y, inner, hh)
            pygame.draw.rect(cv, UI.CARD, card, border_radius=6)
            pygame.draw.rect(cv, col, (card.x, card.y, S(4), card.h),
                             border_top_left_radius=6, border_bottom_left_radius=6)
            pygame.draw.circle(cv, col, (card.x + S(20), card.y + S(8) + f_b.get_linesize() // 2),
                               max(3, S(5)))
            cv.blit(f_b.render(name, True, col), (card.x + S(34), card.y + S(8)))
            ty = card.y + S(8)
            for line in body:
                cv.blit(f_t.render(line, True, TEXT), (card.x + name_w + S(14), ty))
                ty += f_t.get_linesize()
            y = card.bottom + S(6)
        return y + S(30)

    def _paint_move(self, cv, m, x, y, width, S, f_b, f_s, f_c, sprite_dir=None):
        """Una mossa: nome, tipo, categoria, cosa fa, poi le righe delle statistiche."""
        desc = describe_move(m, self.move_text, getattr(self.open, "stem", None))
        lines = [(desc, TEXT)]
        raw = getattr(self.open, "raw", None) or {}
        own = [raw.get("name", "")] + [e.get("name", "") for e in raw.get("evolutions", [])]
        tgt = SG.target_line(m, desc, own)
        if tgt:
            lines.append(("Sul bersaglio: " + tgt, (235, 165, 120)))
        lines += move_lines(m)
        wrapped = []
        for txt, col in lines:
            for ln in _wrap(f_s, txt, width - S(24)):
                wrapped.append((ln, col))
        h = S(10) + f_b.get_linesize() + S(6) + len(wrapped) * f_s.get_linesize() + S(8)
        rr = pygame.Rect(x, y, width, h)
        pygame.draw.rect(cv, UI.CARD, rr, border_radius=6)
        col = TYPE_COLORS.get(m.get("type"), (120, 120, 120))
        pygame.draw.rect(cv, col, (rr.x, rr.y + 4, 3, rr.h - 8))
        tx = rr.x + S(14)
        t = f_b.render(m.get("name", "?"), True, TEXT)
        cv.blit(t, (tx, rr.y + S(8)))
        cx = tx + t.get_width() + S(10)
        if m.get("type"):
            c = type_chip(cv, cx, rr.y + S(8) + (t.get_height() - f_c.get_height() - 4) // 2, m["type"], f_c)
            cx = c.right + S(6)
        cat = CAT_IT.get(m.get("category"), "")
        if cat:
            cv.blit(f_s.render(cat, True, DIM), (cx, rr.y + S(8) + (t.get_height() - f_s.get_height()) // 2))
        yy = rr.y + S(10) + f_b.get_linesize() + S(4)
        for txt, c in wrapped:
            cv.blit(f_s.render(txt, True, c), (tx, yy))
            yy += f_s.get_linesize()
        self._move_rects.append((rr.copy(), m, sprite_dir))
        return rr.bottom + S(6)
