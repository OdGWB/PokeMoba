"""Lobby ONLINE con signaling manuale (WebRTC).

HOST:  ogni slot ha il suo codice OFFERTA (pulsante "Copia"), il suo campo
       per incollare la RISPOSTA dell'amico e lo stato in tempo reale
       (libero / preparo il codice / in attesa / connessione / connesso / fallito).
AMICO: incolla l'offerta, preme "Genera risposta", copia il codice e lo
       rimanda all'host. Poi sceglie squadra e Pokémon come nella lobby LAN.
"""
from __future__ import annotations

import socket
import time

import pygame

import config
from net import client as C
from net.host import (S_CONNECTED, S_CONNECTING, S_DISCONNECTED, S_EMPTY, S_FAILED,
                      S_GATHERING, S_WAITING, HostSession)

from .. import clipboard
from .lobby_scene import ROSTER_NAMES

BG = (14, 20, 17)
PANEL = (24, 34, 29)
BORDER = (60, 84, 66)
GOLD = (235, 210, 90)
TEXT = (230, 232, 225)
DIM = (150, 160, 150)
RED = (240, 120, 110)
GREEN = (130, 220, 140)

STATUS_TXT = {
    S_EMPTY: ("libero", DIM),
    S_GATHERING: ("preparo il codice... (max 3 s)", GOLD),
    S_WAITING: ("codice pronto: mandalo e incolla la risposta", GOLD),
    S_CONNECTING: ("connessione in corso...", GOLD),
    S_CONNECTED: ("CONNESSO", GREEN),
    S_FAILED: ("FALLITO", RED),
    S_DISCONNECTED: ("DISCONNESSO: crea un nuovo codice per farlo rientrare", RED),
}

_fonts = {}


def font(size, bold=False):
    if (size, bold) not in _fonts:
        _fonts[(size, bold)] = pygame.font.SysFont("consolas", size, bold=bold)
    return _fonts[(size, bold)]


def player_name() -> str:
    return (socket.gethostname() or "Giocatore")[:16]


# --- widget minimi ----------------------------------------------------------------------
class TextField:
    """Campo di testo a una riga: clic per il focus, Ctrl+V incolla, INVIO conferma."""

    def __init__(self, placeholder="", limit=4000):
        self.text = ""
        self.placeholder = placeholder
        self.focused = False
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.limit = limit

    def handle_event(self, ev):
        """Ritorna "submit" su INVIO, True se l'evento è stato consumato."""
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.focused = self.rect.collidepoint(ev.pos)
            return self.focused
        if not self.focused or ev.type != pygame.KEYDOWN:
            return False
        if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return "submit"
        if ev.key == pygame.K_ESCAPE:
            self.focused = False
            return True
        if ev.key == pygame.K_BACKSPACE:
            self.text = "" if ev.mod & pygame.KMOD_CTRL else self.text[:-1]
        elif ev.key == pygame.K_v and ev.mod & pygame.KMOD_CTRL:
            self.text = (self.text + clipboard.paste().strip())[:self.limit]
        elif ev.unicode and ev.unicode.isprintable():
            self.text = (self.text + ev.unicode)[:self.limit]
        return True

    def draw(self, surface, rect, f):
        self.rect = pygame.Rect(rect)
        pygame.draw.rect(surface, (12, 16, 14), self.rect, border_radius=4)
        pygame.draw.rect(surface, GOLD if self.focused else BORDER, self.rect, 1, border_radius=4)
        shown = self.text or self.placeholder
        col = TEXT if self.text else (110, 118, 110)
        # Mostra la FINE del testo (un codice lungo non entra tutto).
        while shown and f.size(shown)[0] > self.rect.w - 12:
            shown = "…" + shown[2:]
        if self.focused and int(time.monotonic() * 2) % 2 == 0:
            shown += "_"
        surface.blit(f.render(shown, True, col), (self.rect.x + 6, self.rect.y + 5))


class Buttons:
    """Pulsanti ridisegnati a ogni frame: rect -> azione."""

    def __init__(self):
        self.items = []

    def clear(self):
        self.items = []

    def draw(self, surface, rect, label, action, f, enabled=True):
        r = pygame.Rect(rect)
        pygame.draw.rect(surface, (44, 66, 52) if enabled else (30, 36, 32), r, border_radius=4)
        pygame.draw.rect(surface, GOLD if enabled else BORDER, r, 1, border_radius=4)
        t = f.render(label, True, TEXT if enabled else DIM)
        surface.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))
        if enabled:
            self.items.append((r, action))
        return r

    def click(self, pos):
        for r, action in self.items:
            if r.collidepoint(pos):
                action()
                return True
        return False


# --- pannello degli slot (host) ------------------------------------------------------------
class SlotPanel:
    """Gli slot dell'host: codice offerta, campo risposta, stato. In partita
    (in_match) serve a far rientrare chi è caduto (F2)."""

    def __init__(self, host: HostSession, in_match=False):
        self.host = host
        self.in_match = in_match
        self.fields = {}
        self.errors = {}
        self.copied = {}
        self.buttons = Buttons()

    def field(self, i):
        if i not in self.fields:
            self.fields[i] = TextField("incolla la risposta (Ctrl+V)")
        return self.fields[i]

    def any_focus(self):
        return any(f.focused for f in self.fields.values())

    def handle_event(self, ev) -> bool:
        for i, f in self.fields.items():
            r = f.handle_event(ev)
            if r == "submit":
                self._submit(i)
                return True
            if r:
                return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            return self.buttons.click(ev.pos)
        return False

    def _submit(self, i):
        f = self.field(i)
        err = self.host.submit_answer(i, f.text)
        self.errors[i] = err or ""
        if not err:
            f.text = ""
            f.focused = False

    def _copy(self, i, code):
        self.copied[i] = time.monotonic() if clipboard.copy(code) else -1.0

    def _open(self, i):
        self.errors[i] = ""
        self.host.open_slot(i)

    def update(self):
        pass

    def draw(self, surface, f, rect=None):
        W, H = surface.get_size()
        if rect is None:
            rect = pygame.Rect(W // 2 - 470, 60, 940, H - 120)
            bg = pygame.Surface(rect.size, pygame.SRCALPHA)
            bg.fill((14, 20, 17, 240))
            surface.blit(bg, rect)
            pygame.draw.rect(surface, BORDER, rect, 1)
            surface.blit(font(18, True).render("SLOT DEI GIOCATORI  (F2/ESC chiude)", True, GOLD),
                         (rect.x + 14, rect.y + 10))
            rect = rect.inflate(-28, -50).move(0, 18)
        self.buttons.clear()
        view = self.host.view
        n = self.host.max_players
        rows = [v for v in view[:n] if not v["local"]]
        row_h = max(52, min(70, rect.h // max(1, len(rows))))
        sm = font(14)
        now = time.monotonic()
        for k, v in enumerate(rows):
            i = v["index"]
            y = rect.y + k * row_h
            pygame.draw.rect(surface, PANEL, (rect.x, y, rect.w, row_h - 4), border_radius=4)
            label, col = STATUS_TXT.get(v["status"], (v["status"], DIM))
            who = f"  {v['name']}" if v["joined"] or v["status"] == S_DISCONNECTED else ""
            surface.blit(font(15, True).render(f"Slot {i}{who}", True, TEXT), (rect.x + 8, y + 4))
            # Riga 1: titolo + pulsanti. Riga 2: stato (o errore) a tutta larghezza.
            surface.blit(sm.render(label, True, col), (rect.x + 8, y + 31))
            err = self.errors.get(i) or v["error"]
            if err:
                surface.blit(sm.render(err[:120], True, RED), (rect.x + 8, y + 31 + 17))
            bx = rect.x + 220
            st = v["status"]
            can_open = st in (S_EMPTY, S_FAILED, S_DISCONNECTED) and (
                not self.in_match or v["entity_id"])
            if can_open:
                self.buttons.draw(surface, (bx, y + 3, 150, 25),
                                  "Crea codice" if st == S_EMPTY else "Nuovo codice",
                                  lambda i=i: self._open(i), sm)
            if st == S_WAITING and v["code"]:
                ok = self.copied.get(i)
                lab = ("Copiato!" if ok and ok > 0 and now - ok < 1.5 else
                       "Errore appunti" if ok == -1.0 else f"Copia codice ({len(v['code'])})")
                self.buttons.draw(surface, (bx, y + 3, 190, 25), lab,
                                  lambda i=i, c=v["code"]: self._copy(i, c), sm)
                fr = pygame.Rect(bx + 200, y + 3, rect.right - bx - 390, 25)
                self.field(i).draw(surface, fr, sm)
                self.buttons.draw(surface, (fr.right + 8, y + 3, 96, 25), "Conferma",
                                  lambda i=i: self._submit(i), sm)
            if st not in (S_EMPTY,) and not self.in_match:
                self.buttons.draw(surface, (rect.right - 70, y + 3, 62, 25), "Chiudi",
                                  lambda i=i: self.host.close_slot(i), sm)


# --- scena dell'host ---------------------------------------------------------------------------
class OnlineHostLobbyScene:
    def __init__(self, app, map_index=0):
        self.app = app
        self.next_scene = None
        self.host = HostSession(map_index, player_name())
        self.host.start()
        self.session = self.host.local
        self.panel = SlotPanel(self.host)
        self.chat = TextField("chat (INVIO per mandare)", limit=120)
        self.buttons = Buttons()
        self.team, self.pokemon, self.ready = 0, 0, False
        self._sent = False

    def _send_choice(self):
        self.session.send_choice(self.team, self.pokemon, self.ready)

    def handle_events(self, events):
        for ev in events:
            r = self.chat.handle_event(ev)
            if r == "submit":
                self.session.send_chat(self.chat.text)
                self.chat.text = ""
                continue
            if r or self.panel.handle_event(ev):
                continue
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self.buttons.click(ev.pos)
                continue
            if ev.type != pygame.KEYDOWN:
                continue
            if ev.key == pygame.K_ESCAPE:
                self.host.shutdown()
                from .menu_scene import MenuScene
                self.next_scene = MenuScene(self.app)
            elif ev.key == pygame.K_t:
                self.team ^= 1; self._send_choice()
            elif ev.key == pygame.K_COMMA:
                self.pokemon = (self.pokemon - 1) % len(config.ROSTER); self._send_choice()
            elif ev.key == pygame.K_PERIOD:
                self.pokemon = (self.pokemon + 1) % len(config.ROSTER); self._send_choice()
            elif ev.key == pygame.K_SPACE:
                self.ready = not self.ready; self._send_choice()
            elif ev.key == pygame.K_m:
                self.host.set_map((self.host.map_index + 1) % len(config.MAPS))
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.host.request_start()

    def fixed_update(self):
        pass

    def update(self, dt):
        self.session.poll()
        if not self._sent and self.session.phase == C.LOBBY:
            self._send_choice(); self._sent = True
        if self.session.phase == C.LOADING and self.session.start_info:
            from .online_match_scene import OnlineMatchScene
            self.next_scene = OnlineMatchScene(self.app, self.session, host=self.host)

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, f):
        W, H = surface.get_size()
        surface.fill(BG)
        self.buttons.clear()
        h = self.host
        surface.blit(font(24, True).render("LOBBY ONLINE  (sei l'host)", True, GOLD), (24, 18))
        mapname = config.MAPS[h.map_index][0]
        surface.blit(font(15).render(f"Mappa: {mapname}  (M cambia)    giocatori max: "
                                     f"{h.max_players}    INVIO = avvia    ESC = chiudi",
                                     True, DIM), (24, 52))
        # Colonna sinistra: giocatori e scelta personale.
        x, y = 24, 90
        surface.blit(font(16, True).render("Giocatori", True, TEXT), (x, y)); y += 26
        for p in (self.session.lobby or {}).get("players", []):
            col = config.TEAM_COLORS[p["team"]]
            poke = ROSTER_NAMES[p["pokemon"]] if p["pokemon"] < len(ROSTER_NAMES) else "?"
            tag = "PRONTO" if p["ready"] else "..."
            if p["conn"] == 3:
                tag = "caduto"
            surface.blit(font(14).render(f"{p['slot']}. {p['name'][:12]}  {poke[:10]}  [{tag}]",
                                         True, col), (x, y)); y += 20
        y += 14
        surface.blit(font(16, True).render("La tua scelta", True, TEXT), (x, y)); y += 24
        for line in (f"Squadra: {'BLU' if self.team == 0 else 'ROSSA'}  (T)",
                     f"Pokemon: {ROSTER_NAMES[self.pokemon]}  (, .)",
                     f"Stato:   {'PRONTO' if self.ready else 'non pronto'}  (SPAZIO)"):
            surface.blit(font(14).render(line, True, TEXT), (x, y)); y += 20
        if h.message:
            y += 10
            surface.blit(font(14).render(h.message[:40], True, RED), (x, y))
        # Chat.
        cy = H - 150
        for name, text in list(self.session.chat)[-5:]:
            surface.blit(font(13).render(f"{name}: {text}"[:48], True, DIM), (x, cy)); cy += 18
        self.chat.draw(surface, (x, H - 52, 330, 28), font(14))
        # Slot a destra.
        self.panel.draw(surface, font(14), pygame.Rect(380, 90, W - 404, H - 120))


# --- scena dell'amico ----------------------------------------------------------------------------
class OnlineJoinScene:
    def __init__(self, app):
        self.app = app
        self.next_scene = None
        self.offer = TextField("incolla qui il codice dell'host (Ctrl+V)")
        self.chat = TextField("chat (INVIO per mandare)", limit=120)
        self.buttons = Buttons()
        self._reset()

    def _reset(self):
        self.peer = None
        self.session = None
        self.future = None
        self.answer_code = ""
        self.error = ""
        self.started_at = 0.0
        self.copied = 0.0
        self.team, self.pokemon, self.ready = 0, 0, False
        self._sent = False

    def _generate(self):
        from net import rtc
        from net.signaling import ANSWER, ManualSignaling, SignalingError, SignalMessage
        try:
            msg = ManualSignaling.decode(self.offer.text)
        except SignalingError as e:
            self.error = str(e)
            return
        if msg.kind != "O":
            self.error = "Questo è un codice RISPOSTA: serve l'OFFERTA che ti ha mandato l'host."
            return
        if not rtc.available():
            self.error = "Manca aiortc: installa con  pip install aiortc"
            return
        self.error = ""
        self._msg = msg
        self.peer = rtc.RtcPeer()
        rtc.patient_answerer()           # l'host potrebbe incollare la risposta dopo minuti
        self.future = self.peer.accept_offer(msg.sdp)
        self.session = None              # si crea quando la risposta è pronta
        self.started_at = time.monotonic()
        self._encode = lambda sdp: ManualSignaling.encode(
            SignalMessage(ANSWER, msg.slot, msg.session, sdp))

    def _copy(self):
        self.copied = time.monotonic() if clipboard.copy(self.answer_code) else -1.0

    def _leave(self):
        if self.session is not None:
            self.session.close()
        elif self.peer is not None:
            self.peer.close()
        from .menu_scene import MenuScene
        self.next_scene = MenuScene(self.app)

    def handle_events(self, events):
        for ev in events:
            if self.session is not None and self.session.phase == C.LOBBY:
                r = self.chat.handle_event(ev)
                if r == "submit":
                    self.session.send_chat(self.chat.text)
                    self.chat.text = ""
                    continue
                if r:
                    continue
            elif self.answer_code == "" and self.future is None:
                r = self.offer.handle_event(ev)
                if r == "submit":
                    self._generate()
                    continue
                if r:
                    continue
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self.buttons.click(ev.pos)
                continue
            if ev.type != pygame.KEYDOWN:
                continue
            if ev.key == pygame.K_ESCAPE:
                self._leave()
            elif self.session is not None and self.session.phase == C.LOBBY:
                if ev.key == pygame.K_t:
                    self.team ^= 1; self._choice()
                elif ev.key == pygame.K_COMMA:
                    self.pokemon = (self.pokemon - 1) % len(config.ROSTER); self._choice()
                elif ev.key == pygame.K_PERIOD:
                    self.pokemon = (self.pokemon + 1) % len(config.ROSTER); self._choice()
                elif ev.key == pygame.K_SPACE:
                    self.ready = not self.ready; self._choice()

    def _choice(self):
        self.session.send_choice(self.team, self.pokemon, self.ready)

    def fixed_update(self):
        pass

    def update(self, dt):
        from net.client import ClientSession
        from net.transport import FAILED
        if self.future is not None and self.future.done():
            f, self.future = self.future, None
            try:
                self.answer_code = self._encode(f.result())
                self.session = ClientSession(self.peer, player_name())
            except Exception as e:
                self.error = f"Offerta non valida: {e}"
                self.peer.close()
                self.peer = None
        if self.peer is not None and self.peer.state == FAILED and not self.error:
            self.error = self.peer.error
        if self.session is not None:
            self.session.poll()
            ph = self.session.phase
            if ph == C.LOBBY and self.session.slot is not None and not self._sent:
                self.team = 1 if self.session.slot % 2 else 0
                self._choice(); self._sent = True
            if ph == C.LOADING and self.session.start_info:
                from .online_match_scene import OnlineMatchScene
                self.next_scene = OnlineMatchScene(self.app, self.session)
            if ph in (C.LOST, C.ENDED) and not self.error:
                self.error = self.session.lost_reason or (self.session.end_info or {}).get(
                    "message", "Connessione chiusa.")

    def draw(self, surface):
        surface.fill(BG)

    def hud_lines(self):
        return []

    def draw_fullres(self, surface, f):
        W, H = surface.get_size()
        surface.fill(BG)
        self.buttons.clear()
        sm, md = font(15), font(17, True)
        x, y = 40, 24
        surface.blit(font(24, True).render("UNISCITI ONLINE", True, GOLD), (x, y)); y += 46
        s = self.session
        if s is not None and s.phase == C.LOBBY:
            self._draw_lobby(surface, x, y)
            return
        surface.blit(md.render("1. Incolla il codice che ti ha mandato l'host", True, TEXT), (x, y))
        y += 30
        busy = self.future is not None or bool(self.answer_code)
        self.offer.draw(surface, (x, y, W - 2 * x - 330, 30), sm)
        self.buttons.draw(surface, (W - x - 320, y, 150, 30), "Incolla",
                          lambda: setattr(self.offer, "text", clipboard.paste().strip()),
                          sm, enabled=not busy)
        self.buttons.draw(surface, (W - x - 160, y, 160, 30), "Genera risposta",
                          self._generate, sm, enabled=not busy and bool(self.offer.text))
        y += 50
        if self.future is not None:
            surface.blit(sm.render("Preparo la risposta... (max 3 s)", True, GOLD), (x, y))
        if self.answer_code:
            surface.blit(md.render("2. Manda questo codice all'host (Discord/WhatsApp)", True,
                                   TEXT), (x, y)); y += 30
            code = self.answer_code
            shown = code if len(code) < 110 else code[:60] + " … " + code[-40:]
            surface.blit(sm.render(shown, True, DIM), (x, y)); y += 28
            ok = self.copied
            lab = ("Copiato!" if ok > 0 and time.monotonic() - ok < 1.5 else
                   "Errore appunti" if ok == -1.0 else f"Copia risposta ({len(code)} caratteri)")
            self.buttons.draw(surface, (x, y, 280, 30), lab, self._copy, sm); y += 50
            state = self.peer.state if self.peer else "?"
            label = {"connecting": "3. In attesa che l'host incolli la risposta...",
                     "connected": "Connesso! Entro nella lobby...",
                     "gathering": "Preparo..."}.get(state, state)
            surface.blit(md.render(label, True, GOLD), (x, y)); y += 34
        if self.error:
            for i, line in enumerate(_wrap(self.error, 95)[:4]):
                surface.blit(sm.render(line, True, RED), (x, y + i * 22))
            y += 100
            self.buttons.draw(surface, (x, y, 140, 30), "Riprova",
                              lambda: (self.peer and self.peer.close(), self._reset()), sm)
        surface.blit(sm.render("ESC = torna al menu", True, DIM), (x, H - 40))

    def _draw_lobby(self, surface, x, y):
        s = self.session
        W, H = surface.get_size()
        lob = s.lobby or {}
        mapname = config.MAPS[lob.get("map_index", 0)][0] if lob else "?"
        surface.blit(font(15).render(f"Connesso come slot {s.slot}   Mappa: {mapname}   "
                                     f"ping {s.clock.rtt * 1000:.0f} ms" if s.clock.rtt else
                                     f"Connesso come slot {s.slot}   Mappa: {mapname}",
                                     True, DIM), (x, y)); y += 32
        for p in lob.get("players", []):
            col = config.TEAM_COLORS[p["team"]]
            poke = ROSTER_NAMES[p["pokemon"]] if p["pokemon"] < len(ROSTER_NAMES) else "?"
            tag = "PRONTO" if p["ready"] else "..."
            surface.blit(font(15).render(f"  {p['name']}  -  {poke}  [{tag}]", True, col), (x, y))
            y += 22
        y += 18
        for line in (f"Squadra: {'BLU' if self.team == 0 else 'ROSSA'}   (T)",
                     f"Pokemon: {ROSTER_NAMES[self.pokemon]}   (, .)",
                     f"Stato: {'PRONTO' if self.ready else 'non pronto'}   (SPAZIO)",
                     "La partita la avvia l'host quando tutti sono pronti."):
            surface.blit(font(15).render(line, True, TEXT), (x, y)); y += 22
        cy = H - 160
        for name, text in list(s.chat)[-5:]:
            surface.blit(font(14).render(f"{name}: {text}"[:80], True, DIM), (x, cy)); cy += 20
        self.chat.draw(surface, (x, H - 56, 460, 28), font(14))


def _wrap(text, n):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines
