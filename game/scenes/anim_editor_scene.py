"""Editor delle ANIMAZIONI dei Pokémon (menu principale -> Animazioni).

Si sceglie un Pokémon (tutte le cartelle di assets/pokemon e assets/minions),
poi cosa cambiare: Fermo, Camminata, Attacco base o una delle sue mosse. Per
ognuna si regola, SOLO VISIVAMENTE (la logica di gioco non cambia):
  - quale animazione dello sprite usare (Idle, Walk, Attack, Shoot, ...);
  - la velocità dell'animazione (x0,10 .. x5,00);
  - il taglio: primo e ultimo fotogramma tenuti;
  - per attacco base e mosse: il fotogramma in cui parte il proiettile e il
    punto dello sprite da cui parte (clic sull'anteprima).

Le regolazioni vanno in data/anim_overrides.json (formato in game/anim_tuning.py)
e valgono in partita, offline e online.

Comandi: Spazio = play/pausa, frecce sx/dx = fotogramma, su/giu = direzione,
Ctrl+S = salva, Esc = indietro. Rotella sulle liste per scorrere; per cercare
un Pokémon basta scrivere il nome.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pygame

from engine.match import CAST_ANIMS
from engine.vec import DIR_NAMES, DIR_VECTORS

from .. import anim_tuning as T
from ..sprites.spritesheet import load_pokemon_animations

ROOT = Path(__file__).resolve().parents[2]

BG = (14, 20, 17)
PANEL = (24, 34, 29)
PANEL_HI = (38, 56, 44)
BORDER = (60, 84, 66)
GOLD = (235, 210, 90)
TEXT = (230, 232, 225)
DIM = (150, 160, 150)
RED = (220, 90, 80)
CYAN = (110, 210, 230)

DIR_IT = ["Giu", "Giu-dx", "Destra", "Su-dx", "Su", "Su-sx", "Sinistra", "Giu-sx"]

# Nomi delle cartelle sprite che non sono forme del roster (campi, leggendari).
EXTRA_NAMES = {
    "0080": "Slowbro", "0114": "Tangela", "0167": "Spinarak", "0168": "Ariados",
    "0187": "Hoppip", "0382": "Kyogre", "0383": "Groudon", "0384": "Rayquaza",
    "0455": "Carnivine", "0467": "Magmortar", "0493": "Arceus", "0292": "Shedinja",
    "0_melee": "Minion blu (mischia)", "0_caster": "Minion blu (distanza)",
    "0_cannon": "Minion blu (cannone)", "1_melee": "Minion rosso (mischia)",
    "1_caster": "Minion rosso (distanza)", "1_cannon": "Minion rosso (cannone)",
}
SLOT_ORDER = {"Q": 0, "W": 1, "E": 2, "R": 3}
PAUSE_ONESHOT = 0.45   # pausa in anteprima tra una ripetizione e l'altra di un colpo


def _collect_moves(node, slot="", out=None):
    """Tutte le mosse (dict con id+shape) sotto `node`, con lo slot Q/W/E/R."""
    if out is None:
        out = []
    if isinstance(node, dict):
        if "id" in node and "shape" in node and "name" in node:
            out.append((slot, node))
        for k, v in node.items():
            _collect_moves(v, k if k in SLOT_ORDER else slot, out)
    elif isinstance(node, list):
        for v in node:
            _collect_moves(v, slot, out)
    return out


def build_catalog():
    """[(cartella, percorso, nome, [mosse])]: prima le linee del roster, poi il resto.
    mosse = [(slot, id, nome, shape)]."""
    import config
    forms, moves_of = {}, {}
    order = []
    for rel in config.ROSTER:
        try:
            with open(ROOT / rel, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        base = _collect_moves(d.get("moves", {}))
        evos = d.get("evolutions") or []
        dirs = [(d.get("sprite_dir"), d.get("name"), None)]
        dirs += [(e.get("sprite_dir"), e.get("name"), e) for e in evos]
        if d.get("dex") == 290:   # Nincada: anche Shedinja (forma della Muta)
            dirs.append(("assets/pokemon/0292", "Shedinja", None))
        for sd, name, evo in dirs:
            if not sd:
                continue
            key = Path(sd).name
            mv = list(base)
            if evo is not None and evo.get("moves"):
                mv += _collect_moves(evo["moves"])
            seen, lst = set(), []
            for slot, m in mv:
                if m["id"] in seen:
                    continue
                seen.add(m["id"])
                lst.append((slot, m["id"], m["name"], m.get("shape", "")))
            lst.sort(key=lambda t: SLOT_ORDER.get(t[0], 9))
            if key not in forms:
                forms[key] = (sd, name)
                order.append(key)
            moves_of.setdefault(key, [])
            have = {m[1] for m in moves_of[key]}
            moves_of[key] += [m for m in lst if m[1] not in have]
    out = [(k, forms[k][0], forms[k][1], moves_of.get(k, [])) for k in order]
    for base_dir in ("assets/pokemon", "assets/minions"):
        p = ROOT / base_dir
        if not p.is_dir():
            continue
        for sub in sorted(p.iterdir()):
            if sub.name in forms or not (sub / "AnimData.xml").is_file():
                continue
            out.append((sub.name, f"{base_dir}/{sub.name}",
                        EXTRA_NAMES.get(sub.name, f"#{sub.name}"), []))
    return out


def default_anim(action, shape=""):
    if action == "idle":
        return "Idle"
    if action == "walk":
        return "Walk"
    if action == "aa":
        return "Attack"
    return CAST_ANIMS.get(shape)


class AnimEditorScene:
    def __init__(self, app, back=None):
        self.app = app
        self.back = back
        self.next_scene = None
        self.t = 0.0
        self._fonts: dict = {}
        self._hits: list = []          # (rect, callback, tasto) del frame disegnato
        self.catalog = build_catalog()
        self.work = copy.deepcopy(T.data())   # regolazioni in modifica (non salvate)
        self.dirty = False
        self.status = ""
        self.status_t = 0.0
        self.search = ""
        self.list_scroll = 0
        self.act_scroll = 0
        self._sets: dict = {}
        self._scaled: dict = {}
        self._thumbs: dict = {}
        self._zoom: dict = {}
        self.sel = 0
        self.action = "idle"
        self.facing = 2               # rivolto a destra (come si misura il punto)
        self.playing = True
        self.frame = 0
        self.timer = 0.0
        self.pause = 0.0
        self.shots: list = []          # proiettili dell'anteprima [t, x, y]
        self._preview_rect = pygame.Rect(0, 0, 1, 1)
        self._anchor = (0, 0)
        self._zoom_now = 1
        self._list_w = self._act_w = 240
        self._esc_armed = False
        self._select(0)

    # --- dati ---------------------------------------------------------------------
    def _aset(self, idx=None):
        key, path, _, _ = self.catalog[self.sel if idx is None else idx]
        if key not in self._sets:
            self._sets[key] = load_pokemon_animations(ROOT / path)
        return self._sets[key]

    def _actions(self):
        """[(azione, etichetta, shape)] del Pokémon scelto."""
        _, _, _, moves = self.catalog[self.sel]
        acts = [("idle", "Fermo", ""), ("walk", "Camminata", ""), ("aa", "Attacco base", "")]
        for slot, mid, name, shape in moves:
            acts.append((f"move:{mid}", f"{slot or '-'}  {name}", shape))
        return acts

    def _shape(self):
        for a, _, sh in self._actions():
            if a == self.action:
                return sh
        return ""

    def _key(self):
        return self.catalog[self.sel][0]

    def _entry(self, create=False):
        key = self._key()
        acts = self.work.get(key)
        if acts is None:
            if not create:
                return {}
            acts = self.work[key] = {}
        e = acts.get(self.action)
        if e is None:
            if not create:
                return {}
            e = acts[self.action] = {}
        return e

    def _anim_name(self):
        aset = self._aset()
        if aset is None:
            return None
        e = self._entry()
        if e.get("anim") and aset.has(e["anim"]):
            return e["anim"]
        d = default_anim(self.action, self._shape())
        if d and aset.has(d):
            return d
        if self.action in ("idle", "walk", "aa"):
            for alt in ("Idle", "Walk"):
                if aset.has(alt):
                    return alt
            return next(iter(aset.anims))
        return None      # mossa senza animazione di default

    def _anim(self):
        name = self._anim_name()
        aset = self._aset()
        return aset.get(name) if (aset is not None and name) else None

    def _is_shot(self):
        return self.action != "idle" and self.action != "walk"

    def _changed(self, e=None):
        """Pulisce i valori uguali al default e segna le modifiche."""
        e = self._entry() if e is None else e
        anim = self._anim()
        n = anim.frame_count if anim else 0
        if e.get("anim") == default_anim(self.action, self._shape()):
            e.pop("anim", None)
        if abs(float(e.get("speed", 1.0)) - 1.0) < 1e-6:
            e.pop("speed", None)
        if not e.get("start"):
            e.pop("start", None)
        if e.get("end") is not None and n and int(e["end"]) >= n - 1:
            e.pop("end", None)
        if e.get("release") is None:
            e.pop("release", None)
        if not e.get("origin"):
            e.pop("origin", None)
        key = self._key()
        if key in self.work:
            if not e:
                self.work[key].pop(self.action, None)
            if not self.work[key]:
                self.work.pop(key, None)
        self.dirty = True
        self._esc_armed = False
        self._restart()

    # --- selezione ----------------------------------------------------------------
    def _filtered(self):
        s = self.search.lower().strip()
        return [i for i, (k, _, name, _) in enumerate(self.catalog)
                if not s or s in name.lower() or s in k]

    def _select(self, idx):
        self.sel = idx
        self.action = "idle"
        self.act_scroll = 0
        self._restart()

    def _set_action(self, a):
        self.action = a
        self._restart()

    def _restart(self):
        anim = self._anim()
        lo, _ = T.frame_range(self._entry(), anim.frame_count if anim else 0)
        self.frame = lo
        self.timer = 0.0
        self.pause = 0.0
        self.shots = []
        if anim is not None and self._is_shot():
            r = T.release_frame(self._entry(), anim.frame_count)
            if r == lo:
                self._fire()

    # --- modifiche ----------------------------------------------------------------
    def _set_anim(self, name):
        e = self._entry(create=True)
        e["anim"] = name
        # Un taglio/proiettile pensato per un'altra animazione non ha senso qui.
        for k in ("start", "end", "release"):
            e.pop(k, None)
        self._changed(e)

    def _speed(self, d):
        e = self._entry(create=True)
        v = round(T.speed_of(e) + d, 2)
        e["speed"] = max(T.SPEED_MIN, min(T.SPEED_MAX, v))
        self._changed(e)

    def _bound(self, which, d=None, value=None):
        anim = self._anim()
        if anim is None:
            return
        n = anim.frame_count
        e = self._entry(create=True)
        lo, hi = T.frame_range(e, n)
        if which == "start":
            v = lo + d if value is None else value
            e["start"] = max(0, min(hi, v))
        else:
            v = hi + d if value is None else value
            e["end"] = max(lo, min(n - 1, v))
        r = e.get("release")
        if r is not None:
            lo, hi = T.frame_range(e, n)
            e["release"] = max(lo, min(hi, r))
        self._changed(e)

    def _release(self, d=None, value=None, clear=False):
        anim = self._anim()
        if anim is None:
            return
        e = self._entry(create=True)
        if clear:
            e.pop("release", None)
        else:
            lo, hi = T.frame_range(e, anim.frame_count)
            cur = e.get("release")
            v = value if value is not None else ((lo if cur is None else cur + d))
            e["release"] = max(lo, min(hi, v))
        self._changed(e)

    def _origin_clear(self):
        e = self._entry(create=True)
        e.pop("origin", None)
        self._changed(e)

    def _reset_action(self):
        key = self._key()
        if key in self.work:
            self.work[key].pop(self.action, None)
            if not self.work[key]:
                self.work.pop(key, None)
        self.dirty = True
        self._restart()

    def _save(self):
        try:
            T.save(self.work)
        except OSError as ex:
            self._say(f"Errore nel salvataggio: {ex}")
            return
        self.work = copy.deepcopy(T.data())
        self.dirty = False
        self._say("Salvato in data/anim_overrides.json")

    def _say(self, msg):
        self.status, self.status_t = msg, 3.0

    def _go_back(self):
        if self.dirty and not self._esc_armed:
            self._esc_armed = True
            self._say("Modifiche non salvate: premi di nuovo per uscire senza salvare")
            return
        if self.back is not None:
            self.next_scene = self.back
        else:
            from .menu_scene import MenuScene
            self.next_scene = MenuScene(self.app)

    def _step(self, d):
        anim = self._anim()
        if anim is None:
            return
        self.playing = False
        lo, hi = T.frame_range(self._entry(), anim.frame_count)
        self.frame = lo + (self.frame - lo + d) % (hi - lo + 1)

    # --- input --------------------------------------------------------------------
    def handle_events(self, events):
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for r, cb in reversed(self._hits):
                    if r.collidepoint(ev.pos):
                        cb()
                        break
                else:
                    if self._preview_rect.collidepoint(ev.pos):
                        self._click_origin(ev.pos)
            elif ev.type == pygame.MOUSEWHEEL:
                mx, _ = pygame.mouse.get_pos()
                if mx < self._list_w:
                    self.list_scroll = max(0, self.list_scroll - ev.y * 3)
                elif mx < self._list_w + self._act_w:
                    self.act_scroll = max(0, self.act_scroll - ev.y * 2)
            elif ev.type == pygame.KEYDOWN:
                mods = pygame.key.get_mods()
                if ev.key == pygame.K_s and mods & pygame.KMOD_CTRL:
                    self._save()
                elif ev.key == pygame.K_ESCAPE:
                    if self.search:
                        self.search = ""
                    elif self.dirty and not self._esc_armed:
                        self._esc_armed = True
                        self._say("Modifiche non salvate: Esc di nuovo per uscire senza salvare")
                    else:
                        self._go_back()
                elif ev.key == pygame.K_SPACE:
                    self.playing = not self.playing
                elif ev.key == pygame.K_LEFT:
                    self._step(-1)
                elif ev.key == pygame.K_RIGHT:
                    self._step(1)
                elif ev.key == pygame.K_UP:
                    self.facing = (self.facing + 1) % 8
                elif ev.key == pygame.K_DOWN:
                    self.facing = (self.facing - 1) % 8
                elif ev.key == pygame.K_BACKSPACE:
                    self.search = self.search[:-1]
                    self.list_scroll = 0
                elif ev.unicode and (ev.unicode.isalnum() or ev.unicode in " -_") \
                        and not mods & pygame.KMOD_CTRL and ev.key != pygame.K_SPACE:
                    self.search += ev.unicode
                    self.list_scroll = 0
                    fl = self._filtered()
                    if fl and self.sel not in fl:
                        self._select(fl[0])

    def _click_origin(self, pos):
        """Clic sull'anteprima: il proiettile partira' da li'."""
        if not self._is_shot() or self._anim() is None:
            return
        ax, ay = self._anchor
        z = self._zoom_now
        cx, cy = (pos[0] - ax) / z, (pos[1] - ay) / z
        dv = DIR_VECTORS[self.facing]
        ln = math.hypot(dv.x, dv.y)
        ux, uy = dv.x / ln, dv.y / ln
        e = self._entry(create=True)
        old = e.get("origin") or [0, 0]
        if abs(ux) > 0.3:
            fwd = cx / ux
        else:              # rivolto su/giu: "avanti" non si vede in orizzontale
            fwd = old[0]
        up = uy * fwd - cy
        e["origin"] = [int(round(fwd)), int(round(up))]
        self._changed(e)

    # --- aggiornamento ------------------------------------------------------------
    def fixed_update(self):
        pass

    def hud_lines(self):
        return []

    def update(self, dt):
        self.t += dt
        if self.status_t > 0:
            self.status_t -= dt
        for s in self.shots:
            s[0] += dt
        self.shots = [s for s in self.shots if s[0] < 0.5]
        anim = self._anim()
        if anim is None or not self.playing:
            return
        e = self._entry()
        lo, hi = T.frame_range(e, anim.frame_count)
        if self.pause > 0:
            self.pause -= dt
            if self.pause <= 0:
                self._restart()
            return
        self.timer += dt * T.speed_of(e)
        rel = T.release_frame(e, anim.frame_count) if self._is_shot() else None
        while True:
            dur = max(1, anim.durations[self.frame % anim.frame_count]) * T.DURATION_UNIT
            if self.timer < dur:
                break
            self.timer -= dur
            if self.frame >= hi:
                if self._is_shot():          # colpo: fine, pausa, si ripete
                    self.pause = PAUSE_ONESHOT
                    self.timer = 0.0
                    break
                self.frame = lo
            else:
                self.frame += 1
            if rel is not None and self.frame == rel:
                self._fire()

    def _fire(self):
        self.shots.append([0.0, self.facing])

    def draw(self, surface):
        surface.fill(BG)

    # --- disegno ------------------------------------------------------------------
    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.SysFont("consolas", size, bold=bold)
        return self._fonts[key]

    def _text(self, surface, txt, pos, col=TEXT, size=16, bold=False):
        img = self._font(size, bold).render(txt, True, col)
        surface.blit(img, pos)
        return img.get_width()

    def _button(self, surface, rect, label, cb, on=False, enabled=True, size=15):
        r = pygame.Rect(rect)
        hover = r.collidepoint(pygame.mouse.get_pos()) and enabled
        bg = PANEL_HI if (on or hover) else PANEL
        pygame.draw.rect(surface, bg, r, border_radius=5)
        pygame.draw.rect(surface, GOLD if on else (BORDER if enabled else (40, 50, 44)),
                         r, 2 if on else 1, border_radius=5)
        img = self._font(size, bold=on).render(label, True,
                                               (GOLD if on else TEXT) if enabled else (90, 96, 90))
        surface.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2))
        if enabled:
            self._hits.append((r, cb))
        return r

    def draw_fullres(self, surface, _font):
        W, H = surface.get_size()
        surface.fill(BG)
        self._hits = []
        self._list_w = max(200, int(W * 0.15))
        self._act_w = max(210, int(W * 0.165))
        self._draw_list(surface, H)
        self._draw_actions(surface, H)
        x0 = self._list_w + self._act_w + 16
        self._draw_editor(surface, pygame.Rect(x0, 12, W - x0 - 16, H - 24))

    def _draw_list(self, surface, H):
        w = self._list_w
        pygame.draw.rect(surface, (18, 26, 22), (0, 0, w, H))
        pygame.draw.line(surface, BORDER, (w - 1, 0), (w - 1, H))
        self._text(surface, "Pokémon", (14, 12), GOLD, 20, True)
        box = pygame.Rect(12, 42, w - 24, 28)
        pygame.draw.rect(surface, PANEL, box, border_radius=4)
        pygame.draw.rect(surface, BORDER, box, 1, border_radius=4)
        cur = "_" if int(self.t * 2) % 2 == 0 else " "
        self._text(surface, ("Cerca: " + self.search + cur) if self.search
                   else "scrivi per cercare", (box.x + 8, box.y + 5),
                   TEXT if self.search else DIM, 15)
        items = self._filtered()
        row = 30
        top = 80
        vis = max(1, (H - top - 10) // row)
        self.list_scroll = min(self.list_scroll, max(0, len(items) - vis))
        for n, i in enumerate(items[self.list_scroll:self.list_scroll + vis]):
            key, _, name, _ = self.catalog[i]
            r = pygame.Rect(8, top + n * row, w - 16, row - 3)
            on = i == self.sel
            mod = key in self.work
            self._button(surface, r, "", lambda i=i: self._select(i), on=on)
            self._text(surface, name, (r.x + 10, r.y + 5), GOLD if on else TEXT, 15, on)
            tag = key + (" *" if mod else "")
            tw = self._font(13).size(tag)[0]
            self._text(surface, tag, (r.right - tw - 8, r.y + 7), CYAN if mod else DIM, 13)
        if len(items) > vis:
            frac = self.list_scroll / max(1, len(items) - vis)
            bh = max(30, (H - top) * vis // len(items))
            y = top + int((H - top - 10 - bh) * frac)
            pygame.draw.rect(surface, BORDER, (w - 6, y, 3, bh))

    def _draw_actions(self, surface, H):
        x, w = self._list_w, self._act_w
        pygame.draw.rect(surface, (20, 29, 24), (x, 0, w, H))
        pygame.draw.line(surface, BORDER, (x + w - 1, 0), (x + w - 1, H))
        key, _, name, _ = self.catalog[self.sel]
        self._text(surface, name, (x + 14, 12), GOLD, 20, True)
        self._text(surface, "cosa vuoi cambiare?", (x + 14, 44), DIM, 14)
        acts = self._actions()
        tun = self.work.get(key, {})
        row = 34
        top = 74
        vis = max(1, (H - top - 10) // row)
        self.act_scroll = min(self.act_scroll, max(0, len(acts) - vis))
        for n, (a, label, _) in enumerate(acts[self.act_scroll:self.act_scroll + vis]):
            r = pygame.Rect(x + 8, top + n * row, w - 16, row - 4)
            on = a == self.action
            self._button(surface, r, "", lambda a=a: self._set_action(a), on=on)
            lab = label if len(label) <= 24 else label[:23] + "."
            self._text(surface, lab, (r.x + 10, r.y + 6), GOLD if on else TEXT, 15, on)
            if a in tun:
                self._text(surface, "mod.", (r.right - 40, r.y + 8), CYAN, 13)
            if n == 2 and len(acts) > 3 and self.act_scroll == 0:
                yy = r.bottom + 1
                pygame.draw.line(surface, BORDER, (x + 14, yy), (x + w - 14, yy))

    def _draw_editor(self, surface, area):
        aset = self._aset()
        y = area.y
        _, label, _ = next(((a, l, s) for a, l, s in self._actions() if a == self.action),
                           (None, self.action, None))
        self._text(surface, label.strip(), (area.x, y), GOLD, 22, True)
        if self.dirty:
            self._text(surface, "modifiche non salvate", (area.right - 220, y + 4), RED, 15)
        y += 36
        if aset is None:
            self._text(surface, "Nessuno sprite in questa cartella.", (area.x, y), RED, 16)
            self._bottom_bar(surface, area)
            return
        anim = self._anim()
        e = self._entry()
        # Anteprima a sinistra, controlli a destra, fotogrammi in basso.
        tl_h = 84
        tl_y = area.bottom - 52 - tl_h
        pw = max(160, min(int(area.w * 0.44), tl_y - y - 12))
        prev = pygame.Rect(area.x, y, pw, pw)
        self._draw_preview(surface, prev, anim, e)
        cx = prev.right + 18
        self._draw_controls(surface, pygame.Rect(cx, y, area.right - cx, tl_y - y - 8),
                            aset, anim, e)
        self._draw_timeline(surface, pygame.Rect(area.x, tl_y, area.w, tl_h), anim, e)
        self._bottom_bar(surface, area)

    def _zoom_for(self, aset, box):
        key = (self._key(), box.w)
        if key not in self._zoom:
            mw = mh = 1
            for a in aset.anims.values():
                for f in a.frames[2]:
                    bb = f.get_bounding_rect()
                    mw, mh = max(mw, bb.w), max(mh, bb.h)
            self._zoom[key] = max(1, min(8, int(box.h * 0.62) // mh, int(box.w * 0.7) // mw))
        return self._zoom[key]

    def _frame(self, anim_name, anim, d, idx, z):
        k = (self._key(), anim_name, d, idx, z)
        s = self._scaled.get(k)
        if s is None:
            f = anim.frames[d][idx]
            bb = f.get_bounding_rect()
            s = (pygame.transform.scale(f, (f.get_width() * z, f.get_height() * z)), bb)
            if len(self._scaled) > 600:
                self._scaled.clear()
            self._scaled[k] = s
        return s

    def _draw_preview(self, surface, box, anim, e):
        pygame.draw.rect(surface, (20, 30, 25), box, border_radius=6)
        # griglia tenue del terreno
        for gx in range(box.x + 16, box.right, 32):
            pygame.draw.line(surface, (26, 38, 32), (gx, box.y + 4), (gx, box.bottom - 4))
        for gy in range(box.y + 16, box.bottom, 32):
            pygame.draw.line(surface, (26, 38, 32), (box.x + 4, gy), (box.right - 4, gy))
        pygame.draw.rect(surface, BORDER, box, 1, border_radius=6)
        self._preview_rect = box
        aset = self._aset()
        z = self._zoom_for(aset, box)
        self._zoom_now = z
        ax, ay = box.centerx, box.bottom - int(box.h * 0.2)
        self._anchor = (ax, ay)
        # ombra a terra
        sh = pygame.Surface((14 * z, 5 * z), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 90), sh.get_rect())
        surface.blit(sh, (ax - sh.get_width() // 2, ay - sh.get_height() // 2))
        if anim is None:
            msg = "Questa mossa non ha animazione: scegline una a destra"
            img = self._font(14).render(msg, True, DIM)
            surface.blit(img, (box.centerx - img.get_width() // 2, box.y + 12))
            anim = aset.get("Idle") or next(iter(aset.anims.values()))
            name, idx = "Idle", 0
        else:
            name, idx = self._anim_name(), self.frame % anim.frame_count
        d = self.facing % len(anim.frames)
        idx = min(idx, len(anim.frames[d]) - 1)
        img, bb = self._frame(name, anim, d, idx, z)
        if bb.w:
            surface.blit(img, (ax - bb.centerx * z, ay - bb.bottom * z))
        # punto a terra
        pygame.draw.line(surface, (90, 110, 95), (ax - 6, ay), (ax + 6, ay))
        pygame.draw.line(surface, (90, 110, 95), (ax, ay - 6), (ax, ay + 6))
        if self._is_shot():
            ox, oy = T.origin_offset(e, self.facing, 1.0, 1)
            px, py = ax + ox * z, ay + oy * z
            col = GOLD if e.get("origin") else (150, 150, 150)
            pygame.draw.circle(surface, col, (int(px), int(py)), 6, 2)
            pygame.draw.line(surface, col, (px - 10, py), (px + 10, py))
            pygame.draw.line(surface, col, (px, py - 10), (px, py + 10))
            dv = DIR_VECTORS[self.facing]
            ln = math.hypot(dv.x, dv.y)
            for t, f in self.shots:
                fv = DIR_VECTORS[f]
                dist = t * box.w * 1.1
                sx = px + fv.x / ln * dist
                sy = py + fv.y / ln * dist
                if box.collidepoint(sx, sy):
                    pygame.draw.circle(surface, (255, 240, 170), (int(sx), int(sy)), 7)
                    pygame.draw.circle(surface, (255, 180, 60), (int(sx), int(sy)), 7, 2)
        # direzione
        bw = 34
        self._button(surface, (box.x + 8, box.bottom - 40, bw, 30), "<",
                     lambda: setattr(self, "facing", (self.facing - 1) % 8))
        self._button(surface, (box.x + 8 + bw + 120, box.bottom - 40, bw, 30), ">",
                     lambda: setattr(self, "facing", (self.facing + 1) % 8))
        lab = DIR_IT[self.facing]
        tw = self._font(15).size(lab)[0]
        self._text(surface, lab, (box.x + 8 + bw + 60 - tw // 2, box.bottom - 33), TEXT, 15)
        self._button(surface, (box.right - 104, box.bottom - 40, 96, 30),
                     "Pausa" if self.playing else "Play",
                     lambda: setattr(self, "playing", not self.playing))
        if self._is_shot():
            hint = "clic qui: punto di partenza del proiettile"
            self._text(surface, hint, (box.x + 10, box.y + 8), DIM, 13)

    def _draw_controls(self, surface, area, aset, anim, e):
        x, y = area.x, area.y
        is_default = not e.get("anim")
        dname = default_anim(self.action, self._shape())
        self._text(surface, "Animazione", (x, y), GOLD, 17, True)
        y += 26
        cur = self._anim_name()
        bx = x
        for name in aset.anims:
            w = self._font(14).size(name)[0] + 18
            if bx + w > area.right:
                bx = x
                y += 30
            lab = name + ("*" if name == dname else "")
            self._button(surface, (bx, y, w + 6, 26), lab,
                         lambda n=name: self._set_anim(n), on=name == cur, size=14)
            bx += w + 12
        y += 32
        self._text(surface, ("* = animazione di default" + ("" if is_default else
                    "   (cambiata)")), (x, y), DIM, 13)
        y += 26
        n = anim.frame_count if anim else 0
        lo, hi = T.frame_range(e, n)
        sp = T.speed_of(e)
        en = anim is not None
        # Velocita'
        self._text(surface, "Velocità", (x, y + 4), GOLD, 17, True)
        sx = x + 100
        self._button(surface, (sx, y, 32, 28), "--", lambda: self._speed(-0.25))
        self._button(surface, (sx + 36, y, 28, 28), "-", lambda: self._speed(-0.05))
        self._text(surface, f"x{sp:.2f}", (sx + 72, y + 4), TEXT, 17, True)
        self._button(surface, (sx + 136, y, 28, 28), "+", lambda: self._speed(0.05))
        self._button(surface, (sx + 168, y, 32, 28), "++", lambda: self._speed(0.25))
        y += 32
        if anim is not None:
            orig = sum(max(1, d) for d in anim.durations) * T.DURATION_UNIT
            now = sum(max(1, d) for d in anim.durations[lo:hi + 1]) * T.DURATION_UNIT / sp
            self._text(surface, f"durata {now:.2f} s  (originale {orig:.2f} s)",
                       (x, y), DIM, 13)
        y += 26
        # Taglio
        self._text(surface, "Taglio", (x, y), GOLD, 17, True)
        self._text(surface, f"fotogrammi tenuti {lo + 1}-{hi + 1} di {n}", (x + 100, y + 3),
                   DIM, 13)
        y += 24
        self._text(surface, "inizio", (x, y + 5), DIM, 14)
        self._button(surface, (x + 58, y, 28, 28), "-", lambda: self._bound("start", -1), enabled=en)
        self._text(surface, f"{lo + 1:>2}", (x + 92, y + 4), TEXT, 17, True)
        self._button(surface, (x + 120, y, 28, 28), "+", lambda: self._bound("start", 1), enabled=en)
        fx = x + 168
        self._text(surface, "fine", (fx, y + 5), DIM, 14)
        self._button(surface, (fx + 42, y, 28, 28), "-", lambda: self._bound("end", -1), enabled=en)
        self._text(surface, f"{hi + 1:>2}", (fx + 76, y + 4), TEXT, 17, True)
        self._button(surface, (fx + 104, y, 28, 28), "+", lambda: self._bound("end", 1), enabled=en)
        y += 32
        self._button(surface, (x, y, 150, 26), "inizio = questo",
                     lambda: self._bound("start", value=self.frame), enabled=en, size=13)
        self._button(surface, (x + 158, y, 140, 26), "fine = questo",
                     lambda: self._bound("end", value=self.frame), enabled=en, size=13)
        y += 38
        if not self._is_shot():
            self._wrap(surface, "Cambia solo la grafica: velocità di movimento e di "
                       "attacco restano quelle del gioco.", (x, y), area.w, DIM, 13)
            return
        # Proiettile
        rel = T.release_frame(e, n)
        self._text(surface, "Proiettile", (x, y), GOLD, 17, True)
        y += 24
        self._text(surface, "fotogramma", (x, y + 5), DIM, 14)
        rx = x + 100
        self._button(surface, (rx, y, 28, 28), "-", lambda: self._release(-1), enabled=en)
        self._text(surface, "--" if rel is None else f"{rel + 1:>2}", (rx + 34, y + 4),
                   TEXT, 17, True)
        self._button(surface, (rx + 62, y, 28, 28), "+", lambda: self._release(1), enabled=en)
        self._button(surface, (rx + 98, y, 90, 28), "nessuno",
                     lambda: self._release(clear=True), enabled=en and rel is not None, size=13)
        y += 32
        self._button(surface, (x, y, 170, 26), "proiettile = questo",
                     lambda: self._release(value=self.frame), enabled=en, size=13)
        if anim is not None and anim.hit_frame >= 0:
            hf = anim.hit_frame
            self._button(surface, (x + 178, y, 160, 26), f"colpo del file: {hf + 1}",
                         lambda: self._release(value=hf), enabled=en, size=13)
        y += 32
        o = e.get("origin")
        self._text(surface, "punto", (x, y + 5), DIM, 14)
        self._text(surface, (f"avanti {o[0]}, su {o[1]} px" if o else "piedi (default)"),
                   (x + 58, y + 4), TEXT, 15)
        self._button(surface, (x + 250, y, 80, 26), "azzera", self._origin_clear,
                     enabled=bool(o), size=13)
        y += 34
        if self.action == "aa":
            info = ("Attacco base: quando il gioco rilascia il colpo l'animazione "
                    "salta al fotogramma del proiettile se non ci è ancora arrivata.")
        elif rel is not None and anim is not None:
            dl = min(T.MAX_DELAY, T.release_delay(anim.durations, e))
            info = (f"Mossa: l'effetto visivo parte {dl:.2f} s dopo il lancio "
                    f"(max {T.MAX_DELAY:.1f} s); il danno resta quello del gioco.")
        else:
            info = "Mossa: senza fotogramma l'effetto visivo parte subito, come prima."
        self._wrap(surface, info, (x, y), area.w, DIM, 13)

    def _wrap(self, surface, text, pos, width, col, size):
        f = self._font(size)
        x, y = pos
        line = ""
        for w in text.split():
            t = (line + " " + w).strip()
            if f.size(t)[0] > width and line:
                surface.blit(f.render(line, True, col), (x, y))
                y += size + 4
                line = w
            else:
                line = t
        if line:
            surface.blit(f.render(line, True, col), (x, y))

    def _thumb(self, name, anim, d, idx, h):
        k = (self._key(), name, d, idx, h)
        s = self._thumbs.get(k)
        if s is None:
            f = anim.frames[d][idx]
            bb = f.get_bounding_rect()
            if bb.w == 0:
                s = pygame.Surface((1, 1), pygame.SRCALPHA)
            else:
                sub = f.subsurface(bb)
                z = max(1, h // max(1, bb.h))
                if bb.h > h:
                    zz = h / bb.h
                    s = pygame.transform.scale(sub, (max(1, int(bb.w * zz)), h))
                else:
                    s = pygame.transform.scale(sub, (bb.w * z, bb.h * z))
            if len(self._thumbs) > 800:
                self._thumbs.clear()
            self._thumbs[k] = s
        return s

    def _draw_timeline(self, surface, area, anim, e):
        if anim is None:
            return
        n = anim.frame_count
        lo, hi = T.frame_range(e, n)
        rel = T.release_frame(e, n) if self._is_shot() else None
        name = self._anim_name()
        d = self.facing % len(anim.frames)
        gap = 4
        bw = max(18, min(70, (area.w - gap * (n - 1)) // max(1, n)))
        bh = area.h - 18
        for i in range(n):
            r = pygame.Rect(area.x + i * (bw + gap), area.y, bw, bh)
            kept = lo <= i <= hi
            pygame.draw.rect(surface, PANEL if kept else (16, 20, 18), r, border_radius=4)
            if i < len(anim.frames[d]):
                th = self._thumb(name, anim, d, i, bh - 18)
                if th.get_width() > bw - 4:
                    zz = (bw - 4) / th.get_width()
                    th = pygame.transform.scale(th, (bw - 4, max(1, int(th.get_height() * zz))))
                surface.blit(th, (r.centerx - th.get_width() // 2, r.bottom - 16 - th.get_height()))
            if not kept:
                veil = pygame.Surface(r.size, pygame.SRCALPHA)
                veil.fill((0, 0, 0, 150))
                surface.blit(veil, r)
                pygame.draw.line(surface, RED, r.topleft, r.bottomright, 1)
            col = (BORDER if kept else (40, 46, 42))
            wd = 1
            if i == self.frame % n:
                col, wd = TEXT, 2
            if i == rel:
                col, wd = GOLD, 3
            pygame.draw.rect(surface, col, r, wd, border_radius=4)
            self._text(surface, str(i + 1), (r.x + 3, r.bottom - 15), DIM, 12)
            dur = anim.durations[i]
            self._text(surface, str(dur), (r.right - 3 - self._font(11).size(str(dur))[0],
                                           r.bottom - 15), (110, 120, 110), 11)
            self._hits.append((r, lambda i=i: self._pick_frame(i)))
        y = area.y + bh + 4
        legend = ("clic = vedi il fotogramma  |  oro = parte il proiettile  |  "
                  "scuri = tagliati  |  in basso a dx = durata (1/30 s)")
        self._text(surface, legend, (area.x, y), DIM, 12)

    def _pick_frame(self, i):
        self.playing = False
        self.frame = i

    def _bottom_bar(self, surface, area):
        y = area.bottom - 40
        x = area.x
        self._button(surface, (x, y, 170, 36), "Salva (Ctrl+S)", self._save, on=self.dirty)
        self._button(surface, (x + 180, y, 190, 36), "Ripristina azione", self._reset_action,
                     enabled=self.action in self.work.get(self._key(), {}))
        self._button(surface, (x + 380, y, 164, 36), "Indietro (Esc)", self._go_back)
        if self.status_t > 0:
            self._wrap(surface, self.status, (x + 556, y + 2), area.right - x - 556, CYAN, 14)
        else:
            self._wrap(surface, "Spazio play/pausa, frecce sx/dx fotogramma, su/giu direzione",
                       (x + 556, y + 2), area.right - x - 556, DIM, 13)
