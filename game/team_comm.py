"""Ping sulla mappa e chat rapida di squadra (solo grafica e input: nessuna logica di gioco).

Ping: tieni premuto il tasto "ping" (G) o Alt e fai clic sulla mappa o sulla minimappa.
  - clic secco -> ping generico ("Attenzione"; con Alt "Pericolo");
  - clic e trascina -> RUOTA a 5 spicchi, al rilascio parte il ping dello spicchio.
Chat rapida: tasto "chat" (T) apre un menu di frasi, si sceglie con 1-8 o col clic.

ICONE pixel art auto esplicative (spillo colorato con il simbolo bianco, luce in alto a
sinistra, contorno scuro), in cache: punto esclamativo, teschio, freccia, punto di domanda,
scudo con la croce, spade incrociate. Nel mondo l'icona sta sopra due anelli a terra che si
allargano; fuori schermo resta un'icona sul bordo con la freccia; sulla minimappa l'icona
piccola + anello; a sinistra sopra la barra il FEED dei messaggi della squadra.

`send(kind, code, x, y)` (x, y in tile) e' None offline: il messaggio si mostra solo qui.
Online passa da Client.send_team e torna dall'host (anche a chi lo manda), quindi la scena
chiama `receive` per ogni messaggio ricevuto e NON lo mostra due volte.
"""
from __future__ import annotations

import math

import pygame

import config
from game import keybinds

KIND_PING = 0
KIND_CHAT = 1

# codice -> (id, etichetta, colore dello spillo, suono)
PINGS = (
    ("alert", "Attenzione qui", (58, 140, 220), "ping"),
    ("danger", "Pericolo! Indietro", (214, 58, 50), "ping_danger"),
    ("omw", "Sto arrivando", (58, 178, 88), "ping_omw"),
    ("missing", "Nemico sparito", (226, 186, 46), "ping_missing"),
    ("help", "Serve aiuto", (136, 92, 214), "ping_help"),
    ("attack", "Attacca qui", (232, 118, 40), "ping"),
)
P_ALERT, P_DANGER, P_OMW, P_MISSING, P_HELP, P_ATTACK = range(6)
# Spicchi della ruota, in senso orario partendo dall'ALTO (il centro = generico).
WHEEL = (P_ATTACK, P_OMW, P_HELP, P_MISSING, P_DANGER)

QUICK_CHAT = (
    "Raggruppiamoci!",
    "Ritirata!",
    "Spingiamo la lane!",
    "Prendiamo il leggendario",
    "Torno in base",
    "Attenti alla giungla",
    "Ben fatto!",
    "Grazie! Buona fortuna",
)

PING_LIFE = 3.2          # s di un ping nel mondo e sulla minimappa
FEED_LIFE = 8.0          # s di una riga del feed
FEED_MAX = 5
SPAM_N, SPAM_T = 5, 4.0  # al massimo 5 ping/frasi ogni 4 s (anche l'host taglia)
WHEEL_R = 66             # raggio della ruota (px finestra)
WHEEL_DEAD = 16          # entro questo trascinamento = clic secco

WHITE = (246, 242, 230)
INK = (16, 18, 22)

# Simboli 7x7: '#' bianco, 'o' scuro (colore dello spillo scurito).
_SYM = {
    "alert": ("..##...",
              "..##...",
              "..##...",
              "..##...",
              ".......",
              "..##...",
              "..##..."),
    "danger": (".#####.",
               "#######",
               "#oo#oo#",
               "#oo#oo#",
               ".##o##.",
               "..#.#..",
               "..###.."),
    "omw": ("...#...",
            "...##..",
            "######.",
            "#######",
            "######.",
            "...##..",
            "...#..."),
    "missing": (".####..",
                "##..##.",
                "....##.",
                "...##..",
                "..##...",
                ".......",
                "..##..."),
    "help": ("#######",
             "###o###",
             "#ooooo#",
             "###o###",
             ".##o##.",
             "..###..",
             "...#..."),
    "attack": ("##...##",
               ".##.##.",
               "..###..",
               "...#...",
               "..#.#..",
               ".##.##.",
               "##...##"),
}

_CACHE: dict = {}


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def icon(code: int, scale: int = 1, pin: bool = True) -> pygame.Surface:
    """Spillo (o solo disco) del ping `code`, pixel art 1x poi NEAREST x`scale`."""
    key = ("icon", code, scale, pin)
    s = _CACHE.get(key)
    if s is not None:
        return s
    pid, _lab, col, _snd = PINGS[code % len(PINGS)]
    R = 6                                   # disco 13x13
    W, H = 2 * R + 3, 2 * R + 3 + (4 if pin else 0)
    base = pygame.Surface((W, H), pygame.SRCALPHA)
    cx = cy = R + 1
    hi, mid, lo = _shade(col, 1.25), col, _shade(col, 0.68)
    shape = set()
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            inside = dx * dx + dy * dy <= R * R + 2
            if pin and not inside and y > cy:   # punta dello spillo (triangolo in basso)
                inside = abs(dx) <= (cy + R + 4 - y) * 0.75 and y <= cy + R + 3
            if inside:
                shape.add((x, y))
                # luce in alto a sinistra, ombra in basso a destra
                t = (dx + dy) / (2.0 * R)
                c = hi if t < -0.45 else (mid if t < 0.4 else lo)
                base.set_at((x, y), c + (255,))
    # simbolo bianco al centro (7x7)
    sym = _SYM[pid]
    ox, oy = cx - 3, cy - 3
    dark = _shade(col, 0.42)
    for j, row in enumerate(sym):
        for i, ch in enumerate(row):
            if ch == "#":
                base.set_at((ox + i, oy + j), WHITE + (255,))
            elif ch == "o":
                base.set_at((ox + i, oy + j), dark + (255,))
    # contorno scuro (4 vicini) + riflesso
    out = pygame.Surface((W + 2, H + 2), pygame.SRCALPHA)
    for (x, y) in shape:
        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + ddx, y + ddy)
            if q not in shape:
                out.set_at((q[0] + 1, q[1] + 1), INK + (255,))
    out.blit(base, (1, 1))
    out.set_at((cx - 3 + 1, cy - 4 + 1), _mix(hi, WHITE, 0.6) + (255,))
    if scale != 1:
        out = pygame.transform.scale(out, (out.get_width() * scale, out.get_height() * scale))
    _CACHE[key] = out
    return out


def _ring(r, col, w=1):
    """Anello schiacciato in prospettiva (a terra), in cache per raggio."""
    key = ("ring", r, col, w)
    s = _CACHE.get(key)
    if s is None:
        rx, ry = max(2, r), max(1, int(r * 0.55))
        s = pygame.Surface((2 * rx + 3, 2 * ry + 3), pygame.SRCALPHA)
        pygame.draw.ellipse(s, col, (1, 1, 2 * rx + 1, 2 * ry + 1), w)
        _CACHE[key] = s
    return s


def _edge_arrow(col):
    key = ("arrow", col)
    s = _CACHE.get(key)
    if s is None:
        s = pygame.Surface((7, 7), pygame.SRCALPHA)
        pygame.draw.polygon(s, INK, ((0, 0), (6, 3), (0, 6)))
        pygame.draw.polygon(s, col, ((1, 1), (4, 3), (1, 5)))
        _CACHE[key] = s
    return s


def label(m) -> str:
    if m["kind"] == KIND_PING:
        return PINGS[m["code"] % len(PINGS)][1]
    return QUICK_CHAT[m["code"] % len(QUICK_CHAT)]


class TeamComm:
    def __init__(self, send=None, my_name="Tu"):
        self.send = send
        self.my_name = my_name
        self.pings: list[dict] = []          # nel mondo / minimappa
        self.feed: list[dict] = []
        self._sent: list[float] = []
        self.key_held = False
        self.wheel = None                    # dict: c (pos finestra), w (x, y tile), alt
        self.chat_open = False
        self._chat_rects: list = []
        self._now = 0.0
        self.notice = None                   # (t, testo) avviso "troppi ping"
        # Resa: on_surrender(yes) manda il voto; vote = stato del voto della squadra
        # (Match.surrender_state o il suo gemello online), aggiornato da set_vote.
        self.on_surrender = None
        self.vote = None
        self._vote_mt = 0.0                  # tempo di PARTITA (i tempi del voto sono quelli)
        self._my_id = None
        self._name_of = None
        self._vote_rects: list = []

    # --- invio / ricezione ---------------------------------------------------------------
    def _emit(self, kind, code, x=0.0, y=0.0):
        now = self._now
        self._sent = [t for t in self._sent if now - t < SPAM_T]
        if len(self._sent) >= SPAM_N:
            self.notice = (now, "Troppi ping: aspetta un attimo")
            return
        self._sent.append(now)
        if self.send is None:                # offline: solo qui
            self.receive({"kind": kind, "code": code, "x": x, "y": y, "name": self.my_name})
        else:
            self.send(kind, code, x, y)

    def receive(self, m, now=None):
        """Messaggio (dict con kind, code, x, y, name) da mostrare e suonare."""
        from game import sfx
        now = self._now if now is None else now
        m = dict(m)
        m["t"] = now
        if m["kind"] == KIND_PING:
            m["code"] %= len(PINGS)
            self.pings.append(m)
            self.pings = self.pings[-24:]
            sfx.play(PINGS[m["code"]][3], 0.8)
        else:
            m["code"] %= len(QUICK_CHAT)
            sfx.play("chat", 0.8)
        self.feed.append(m)
        self.feed = self.feed[-FEED_MAX:]

    def update(self, now):
        self._now = now
        self.pings = [p for p in self.pings if now - p["t"] < PING_LIFE]
        self.feed = [m for m in self.feed if now - m["t"] < FEED_LIFE]

    # --- resa ----------------------------------------------------------------------------
    def set_vote(self, state, match_time, my_id, name_of=None):
        """Stato del voto di resa della propria squadra; suona all'apertura."""
        from game import sfx
        was = self.vote is not None and "end_at" in self.vote
        now_on = state is not None and "end_at" in state
        if now_on and not was:
            sfx.play("vote", 0.9)
        elif was and not now_on and state is not None and state.get("next_at", 0) > match_time:
            self.notice = (self._now, "Resa respinta")
        self.vote, self._vote_mt, self._my_id, self._name_of = state, match_time, my_id, name_of

    def vote_open(self):
        return self.vote is not None and "end_at" in self.vote

    def _voted(self):
        v = self.vote
        return (not self.vote_open()) or self._my_id in v["yes"] or self._my_id in v["no"]

    def _surrender(self, yes):
        if self.on_surrender is None:
            return
        if not self.vote_open():
            if not yes:
                return
            left = (self.vote or {}).get("next_at", 0.0) - self._vote_mt
            if left > 0:
                m, sec = divmod(int(left) + 1, 60)
                self.notice = (self._now, f"Resa possibile tra {m}:{sec:02d}")
                return
        elif self._voted():
            return
        self.on_surrender(yes)

    # --- input ---------------------------------------------------------------------------
    @staticmethod
    def _alt():
        return bool(pygame.key.get_mods() & pygame.KMOD_ALT)

    def _world_of(self, pos, camera, minimap):
        if minimap is not None and minimap.contains(pos):
            return minimap.to_world_tile(pos)
        wx, wy = camera.screen_window_to_world(*pos)
        return wx / config.TILE_SIZE, wy / config.TILE_SIZE

    def handle_event(self, ev, camera, minimap=None) -> bool:
        """True = evento consumato (non va al resto della scena)."""
        kp, kc = keybinds.key("ping"), keybinds.key("chat")
        if ev.type == pygame.KEYDOWN:
            if self.chat_open:
                if ev.key in (pygame.K_ESCAPE, kc):
                    self.chat_open = False
                    return True
                n = ev.key - pygame.K_1 if pygame.K_1 <= ev.key <= pygame.K_9 else (
                    ev.key - pygame.K_KP1 if pygame.K_KP1 <= ev.key <= pygame.K_KP9 else -1)
                if 0 <= n < len(QUICK_CHAT):
                    self.chat_open = False
                    self._emit(KIND_CHAT, n)
                    return True
                if n == len(QUICK_CHAT) and self.on_surrender is not None:
                    self.chat_open = False
                    self._surrender(True)
                    return True
                if pygame.K_0 <= ev.key <= pygame.K_9:
                    return True              # niente oggetti 1-6 col menu aperto
                return False
            if ev.key in (pygame.K_F5, pygame.K_F6) and not self._voted():
                self._surrender(ev.key == pygame.K_F5)
                return True
            if ev.key == kp:
                self.key_held = True
                return True
            if ev.key == kc:
                self.chat_open = True
                return True
        elif ev.type == pygame.KEYUP and ev.key == kp:
            self.key_held = False
            return True
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if not self._voted():
                for r, yes in self._vote_rects:
                    if r.collidepoint(ev.pos):
                        self._surrender(yes)
                        return True
            if self.chat_open:
                for r, n in self._chat_rects:
                    if r.collidepoint(ev.pos):
                        self.chat_open = False
                        if n == len(QUICK_CHAT):
                            self._surrender(True)
                        else:
                            self._emit(KIND_CHAT, n)
                        return True
            if self.key_held or self._alt():
                self.wheel = {"c": ev.pos, "w": self._world_of(ev.pos, camera, minimap),
                              "alt": self._alt() and not self.key_held, "m": ev.pos}
                return True
        elif ev.type == pygame.MOUSEMOTION and self.wheel is not None:
            self.wheel["m"] = ev.pos
            return True
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.wheel is not None:
            w, self.wheel = self.wheel, None
            code = self._wheel_pick(w, ev.pos)
            self._emit(KIND_PING, code, *w["w"])
            return True
        return False

    @staticmethod
    def _wheel_pick(w, pos):
        dx, dy = pos[0] - w["c"][0], pos[1] - w["c"][1]
        if dx * dx + dy * dy < WHEEL_DEAD * WHEEL_DEAD:
            return P_DANGER if w["alt"] else P_ALERT
        ang = (math.degrees(math.atan2(dx, -dy)) + 360 + 36) % 360   # 0 = alto, orario
        return WHEEL[int(ang // 72) % len(WHEEL)]

    # --- disegno nel mondo (bassa risoluzione) --------------------------------------------
    def draw_world(self, surface, camera):
        now = self._now
        W, H = surface.get_size()
        ts = config.TILE_SIZE
        for p in self.pings:
            age = now - p["t"]
            col = PINGS[p["code"]][2]
            sx, sy = camera.world_to_screen(p["x"] * ts, p["y"] * ts)
            if -8 <= sx <= W + 8 and -8 <= sy <= H + 8:
                # due anelli che si allargano dal punto (i primi 1,2 s), poi uno fisso
                for k in (0.0, 0.35):
                    a = age - k
                    if 0 <= a < 0.9:
                        r = int(4 + a * 26)
                        ring = _ring(r, col + (int(230 * (1 - a / 0.9)),), 1)
                        surface.blit(ring, (sx - ring.get_width() // 2,
                                            sy - ring.get_height() // 2))
                fade = 1.0 if age < PING_LIFE - 0.5 else (PING_LIFE - age) / 0.5
                ring = _ring(6, col + (int(170 * fade),), 1)
                surface.blit(ring, (sx - ring.get_width() // 2, sy - ring.get_height() // 2))
                ic = icon(p["code"])
                # cade dall'alto, rimbalza, poi ondeggia piano
                drop = max(0.0, 1 - age / 0.18)
                bob = int(round(math.sin(age * 4.0) * 1.0)) if age > 0.3 else 0
                y = sy - ic.get_height() - 2 - int(drop * 14) + bob
                if fade < 1.0:
                    ic = ic.copy()
                    ic.set_alpha(int(255 * fade))
                surface.blit(ic, (sx - ic.get_width() // 2, y))
            else:
                # fuori schermo: icona sul bordo con la freccia verso il ping
                # riquadro utile: sotto la striscia in alto, sopra barra e minimappa
                top, bot = 32, H - 112
                cx, cy = W / 2, (top + bot) / 2
                dx, dy = sx - cx, sy - cy
                k = min((W / 2 - 12) / max(1e-6, abs(dx)), ((bot - top) / 2) / max(1e-6, abs(dy)))
                ex, ey = int(cx + dx * k), int(cy + dy * k)
                ic = icon(p["code"], pin=False)
                surface.blit(ic, (ex - ic.get_width() // 2, ey - ic.get_height() // 2))
                ang = math.degrees(math.atan2(-dy, dx))
                ar = pygame.transform.rotate(_edge_arrow(col), ang)
                d = ic.get_width() // 2 + 3
                n = math.hypot(dx, dy) or 1
                surface.blit(ar, (ex + dx / n * d - ar.get_width() / 2,
                                  ey + dy / n * d - ar.get_height() / 2))

    # --- minimappa, ruota, menu, feed (piena risoluzione) ---------------------------------
    def draw_minimap(self, surface, minimap):
        if minimap is None:
            return
        now = self._now
        for p in self.pings:
            age = now - p["t"]
            mx, my = minimap._m(p["x"], p["y"])
            col = PINGS[p["code"]][2]
            if age < 1.2:
                r = int(3 + (age % 0.6) / 0.6 * 9)
                pygame.draw.circle(surface, col, (int(mx), int(my)), r, 1)
            ic = icon(p["code"])
            surface.blit(ic, (int(mx) - ic.get_width() // 2, int(my) - ic.get_height() + 1))

    def draw_overlay(self, surface, bar_top=None):
        from game import hud
        W, H = surface.get_size()
        if self.wheel is not None:
            self._draw_wheel(surface, self.wheel)
        if self.chat_open:
            self._draw_chat_menu(surface, bar_top or H - 140)
        self._vote_rects = []
        if self.vote_open():
            self._draw_vote(surface)
        # feed in basso a sinistra, sopra la barra
        y = (bar_top or H - 140) - 8
        now = self._now
        for m in reversed(self.feed):
            age = now - m["t"]
            a = 1.0 if age < FEED_LIFE - 1 else max(0.0, FEED_LIFE - age)
            name = m.get("name", "?")
            txt = label(m)
            f = hud.font(13, True)
            img_n = f.render(name + ":", True, (140, 190, 255))
            img_t = hud.font(13).render(txt, True, WHITE)
            ic = icon(m["code"], pin=False) if m["kind"] == KIND_PING else None
            w = img_n.get_width() + 6 + img_t.get_width() + (ic.get_width() + 6 if ic else 0) + 12
            h = 20
            y -= h + 2
            row = pygame.Surface((w, h), pygame.SRCALPHA)
            row.fill((10, 14, 12, 170))
            x = 6
            if ic is not None:
                row.blit(ic, (x, (h - ic.get_height()) // 2))
                x += ic.get_width() + 6
            row.blit(img_n, (x, 2))
            x += img_n.get_width() + 6
            row.blit(img_t, (x, 2))
            if a < 1.0:
                row.set_alpha(int(255 * a))
            surface.blit(row, (12, y))
        if self.notice and now - self.notice[0] < 1.5:
            hud.text(surface, self.notice[1], (W // 2, H // 2 + 70), 14, (255, 150, 120),
                     center=True)

    def _wheel_base(self):
        s = _CACHE.get("wheel")
        if s is None:
            R = WHEEL_R
            S = 2 * R + 60
            s = pygame.Surface((S, S), pygame.SRCALPHA)
            c = S // 2
            pygame.draw.circle(s, (8, 12, 10, 150), (c, c), R + 22)
            pygame.draw.circle(s, (235, 210, 90, 120), (c, c), R + 22, 1)
            for i in range(len(WHEEL)):        # divisori tra gli spicchi
                a = math.radians(i * 72 - 36)
                p0 = (c + math.sin(a) * 20, c - math.cos(a) * 20)
                p1 = (c + math.sin(a) * (R + 22), c - math.cos(a) * (R + 22))
                pygame.draw.line(s, (235, 210, 90, 70), p0, p1, 1)
            pygame.draw.circle(s, (20, 28, 24, 220), (c, c), 18)
            _CACHE["wheel"] = s
        return s

    def _draw_wheel(self, surface, w):
        from game import hud
        base = self._wheel_base()
        c = w["c"]
        surface.blit(base, (c[0] - base.get_width() // 2, c[1] - base.get_height() // 2))
        sel = self._wheel_pick(w, w["m"])
        # centro = generico
        center_code = P_DANGER if w["alt"] else P_ALERT
        ic = icon(center_code, 2, pin=False)
        big = sel == center_code
        if not big:
            ic = ic.copy(); ic.set_alpha(150)
        surface.blit(ic, (c[0] - ic.get_width() // 2, c[1] - ic.get_height() // 2))
        for i, code in enumerate(WHEEL):
            a = math.radians(i * 72)
            x, y = c[0] + math.sin(a) * WHEEL_R, c[1] - math.cos(a) * WHEEL_R
            on = sel == code
            ic = icon(code, 3 if on else 2, pin=False)
            if on:
                pygame.draw.circle(surface, PINGS[code][2], (int(x), int(y)),
                                   ic.get_width() // 2 + 4, 2)
            surface.blit(ic, (int(x) - ic.get_width() // 2, int(y) - ic.get_height() // 2))
        lab = PINGS[sel][1]
        hud.text(surface, lab, (c[0], c[1] + WHEEL_R + 30), 15, WHITE, bold=True, center=True)

    def _draw_chat_menu(self, surface, bar_top):
        from game import hud
        f = hud.font(14)
        rows = [f"{i + 1}  {t}" for i, t in enumerate(QUICK_CHAT)]
        if self.on_surrender is not None:
            rows.append(f"{len(QUICK_CHAT) + 1}  Proponi la resa")
        w = max(f.size(r)[0] for r in rows) + 28
        h = 30 + len(rows) * 22 + 8
        x, y = 12, bar_top - h - 130
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((10, 14, 12, 215))
        pygame.draw.rect(panel, (235, 210, 90), panel.get_rect(), 1)
        surface.blit(panel, (x, y))
        hud.text(surface, "Chat rapida (squadra)", (x + 10, y + 7), 14, (235, 210, 90), bold=True)
        self._chat_rects = []
        mp = pygame.mouse.get_pos()
        for i, r in enumerate(rows):
            rr = pygame.Rect(x + 4, y + 30 + i * 22, w - 8, 21)
            if rr.collidepoint(mp):
                pygame.draw.rect(surface, (40, 58, 46), rr)
            hud.text(surface, r, (x + 12, rr.y + 2), 14,
                     (255, 140, 120) if i == len(QUICK_CHAT) else WHITE)
            self._chat_rects.append((rr, i))

    def _draw_vote(self, surface):
        """Pannello del voto di resa, in alto a destra sotto la striscia."""
        from game import hud
        v = self.vote
        W = surface.get_width()
        w, h = 240, 96
        x, y = W - w - 12, 64
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((16, 10, 10, 225))
        pygame.draw.rect(panel, (214, 90, 70), panel.get_rect(), 1)
        surface.blit(panel, (x, y))
        hud.text(surface, "RESA?", (x + 10, y + 6), 15, (255, 140, 120), bold=True)
        by = self._name_of(v["by"]) if self._name_of else None
        if by:
            hud.text(surface, f"proposta da {by}", (x + w - 10, y + 8), 12, hud.DIM, right=True)
        # una casella per votante: verde si', rossa no, grigia in attesa
        n, need = v["n"], v["need"]
        ny, nn = len(v["yes"]), len(v["no"])
        for i in range(n):
            col = ((70, 190, 90) if i < ny else
                   (210, 70, 60) if i >= n - nn else (66, 66, 70))
            r = pygame.Rect(x + 10 + i * 22, y + 30, 18, 12)
            pygame.draw.rect(surface, col, r)
            pygame.draw.rect(surface, INK, r, 1)
        hud.text(surface, f"servono {need} su {n}", (x + w - 10, y + 29), 12, hud.DIM, right=True)
        # tempo che resta
        left = max(0.0, v["end_at"] - self._vote_mt)
        frac = min(1.0, left / 30.0)
        pygame.draw.rect(surface, (44, 36, 32), (x + 10, y + 50, w - 20, 4))
        pygame.draw.rect(surface, (226, 170, 72), (x + 10, y + 50, int((w - 20) * frac), 4))
        if not self._voted():
            mp = pygame.mouse.get_pos()
            bw = (w - 26) // 2
            for k, (lab, yes, col) in enumerate((("F5  Sì", True, (56, 146, 70)),
                                                 ("F6  No", False, (168, 58, 50)))):
                r = pygame.Rect(x + 10 + k * (bw + 6), y + 62, bw, 24)
                c = tuple(min(255, a + 30) for a in col) if r.collidepoint(mp) else col
                pygame.draw.rect(surface, c, r)
                pygame.draw.rect(surface, INK, r, 1)
                hud.text(surface, lab, (r.centerx, r.y + 4), 14, WHITE, bold=True, center=True)
                self._vote_rects.append((r, yes))
        else:
            mine = "Hai votato SÌ" if self._my_id in v["yes"] else "Hai votato NO"
            hud.text(surface, f"{mine}  -  {left:.0f} s", (x + w // 2, y + 68), 13, hud.DIM,
                     center=True)
