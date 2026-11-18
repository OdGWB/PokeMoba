"""TUTORIAL guidato sulla mappa d'allenamento (sottoclasse di TrainingScene).

Charmander fisso, livello 1, ricariche e oro NORMALI. Una scheda in alto al centro
spiega un passo alla volta; il passo si completa da solo quando il giocatore fa
la cosa richiesta (controlli sullo stato della partita, nessuna logica nuova).
Un cerchio dorato a terra indica dove andare. "Salta" (clic) passa oltre.
"""
from __future__ import annotations

import math

import pygame

import config
from engine.vec import Vec2

from .. import hud, sfx
from .training_scene import ROOT, TrainingScene

CHARMANDER = ROOT / "data" / "pokemon" / "charmander.json"
CARD_W = 560

# (titolo, testo, obiettivo a terra o None)
STEPS = [
    ("Benvenuto!", "Questo e' il campo d'allenamento: impari le basi passo per passo. "
     "Ogni passo si completa da solo quando fai quello che chiede. Premi INVIO per iniziare.",
     None),
    ("Il negozio", "Sei in base: solo qui si compra. Premi P per aprire il negozio, "
     "clicca un oggetto per comprarlo, poi chiudi con P o ESC.", None),
    ("Muoversi", "Clic DESTRO sul terreno per muoverti. Raggiungi il cerchio dorato "
     "nella radura a nord, dove ti aspettano i manichini.", (21.5, 9.5)),
    ("Attacco base", "Clic SINISTRO su un manichino per attaccarlo. Il tuo Pokemon "
     "si avvicina da solo e colpisce finche' non gli dai un altro ordine.", None),
    ("Sbloccare una mossa", "Hai un punto mossa: tieni CTRL e premi Q (o clicca il + "
     "sulla casella) per sbloccare Braciere. Ogni livello ti da' un punto.", None),
    ("Usare una mossa", "Punta il mouse su un manichino e premi Q: Braciere parte verso "
     "il mouse. Dopo il lancio la casella mostra i secondi di ricarica.", None),
    ("Ping alla squadra", "Tieni premuto G e clicca: lasci un segnale che vede la tua "
     "squadra. Trascinando con G premuto si apre la ruota dei ping.", None),
    ("Minion e torre", "Ora arrivano le ondate di minion lungo la lane. Dai l'ULTIMO "
     "colpo a un minion nemico per prendere l'oro. Attento al cerchio rosso della torre "
     "nemica: dentro, la torre ti spara.", (24.5, 16.5)),
    ("La giungla", "A sud ci sono i campi neutrali: danno oro ed esperienza. Entra dal "
     "varco e sconfiggi il campo piccolo (a sinistra).", (13.5, 25.5)),
    ("Tornare in base", "Premi B e resta fermo qualche secondo: torni in base, ti curi "
     "e puoi comprare. Muoverti o venire colpito interrompe il richiamo.", None),
    ("Tutorial completato!", "Ora conosci le basi. INVIO = Allenamento libero con "
     "Charmander, ESC = torna al menu. Nell'Enciclopedia trovi tutte le mosse e le "
     "passive di ogni linea.", None),
]
LAST = len(STEPS) - 1


class TutorialScene(TrainingScene):
    def __init__(self, back=None):
        self.step = 0
        self._step_t = 0.0
        self._base_gold = 0
        self._cs0 = 0
        self._wild_near: set = set()
        self._was_far = False
        self._skip_rect = None
        self._dmg0 = 0.0
        self._ordered = False
        super().__init__(str(CHARMANDER), start_level=1, back=back)
        m = self.match
        m.no_cd = False
        m.inf_gold = False
        m.waves_on = False
        self.player.gold = max(self.player.gold, 1200.0)   # basta per un oggetto
        self.panel_open = False

    # --- passi ---------------------------------------------------------------
    def _advance(self):
        if self.step >= LAST:
            return
        self.step += 1
        self._step_t = 0.0
        sfx.play("level_up" if self.step == LAST else "ui_confirm")
        p, m = self.player, self.match
        if self.step == 3:
            self._dmg0 = m.dmg_total
            self._ordered = False
        elif self.step == 7:                 # minion e torre
            m.waves_on = True
            self._cs0 = p.stat_cs
        elif self.step == 8:
            self._wild_near = set()
        elif self.step == 9:
            self._was_far = p.pos.dist(p.spawn_pos) > 4.0

    def _check(self) -> bool:
        p, m, s = self.player, self.match, self.step
        if s == 1:
            return bool(p.items) and not self.shop.open
        if s == 2:
            return p.pos.dist(Vec2(*STEPS[2][2])) < 2.0
        if s == 3:
            # Serve l'ORDINE d'attacco (clic sinistro): l'auto-attacco non vale.
            if p.order == "attack" and p.order_target_id in m.dummy_ids:
                self._ordered = True
            return self._ordered and m.dmg_total > self._dmg0
        if s == 4:
            return any(ms.rank > 0 for ms in p.moveset.values())
        if s == 5:
            return any(ms.cooldown_remaining > 0 for ms in p.moveset.values())
        if s == 6:
            return bool(self.comm.pings)
        if s == 7:
            return p.stat_cs > self._cs0
        if s == 8:
            # Un neutrale vicino al giocatore che sparisce = campo sconfitto.
            alive = {w.id for w in self.world.wilds() if w.alive}
            gone = self._wild_near - alive
            self._wild_near = {w.id for w in self.world.wilds()
                               if w.alive and w.pos.dist(p.pos) < 7.0}
            return bool(gone) and p.alive
        if s == 9:
            if p.pos.dist(p.spawn_pos) > 4.0:
                self._was_far = True
            return self._was_far and p.alive and p.pos.dist(p.spawn_pos) < 2.5
        return False

    # --- ciclo ---------------------------------------------------------------
    def handle_events(self, events) -> None:
        rest = []
        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.step == 0:
                    self._advance()
                    continue
                if self.step == LAST:
                    self._to_training()
                    continue
            if (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1
                    and self._skip_rect is not None and self._skip_rect.collidepoint(ev.pos)):
                if self.step == LAST:
                    self._to_training()
                else:
                    self._advance()
                continue
            # I tasti del pannello d'allenamento qui non servono.
            if ev.type == pygame.KEYDOWN and (ev.key in self.KEYS or ev.key == pygame.K_F4):
                continue
            rest.append(ev)
        super().handle_events(rest)

    def update(self, dt: float) -> None:
        super().update(dt)
        self._step_t += dt
        if 0 < self.step < LAST and self._step_t > 0.4 and self._check():
            self._advance()

    def _to_training(self):
        sfx.play("ui_confirm")
        nxt = TrainingScene(str(CHARMANDER), back=self._back_factory)
        nxt.app = getattr(self, "app", None)
        self.next_scene = nxt

    # --- disegno -------------------------------------------------------------
    def draw(self, surface) -> None:
        super().draw(surface)
        goal = STEPS[self.step][2]
        if goal is None:
            return
        # Cerchio dorato a terra (bassa risoluzione: pixel art), che pulsa.
        sx, sy = self.camera.world_to_screen(goal[0] * config.TILE_SIZE,
                                             goal[1] * config.TILE_SIZE)
        t = pygame.time.get_ticks() / 1000.0
        r = int(config.TILE_SIZE * (1.1 + 0.12 * math.sin(t * 4)))
        rect = pygame.Rect(0, 0, r * 2, int(r * 1.2))
        rect.center = (sx, sy)
        pygame.draw.ellipse(surface, (40, 30, 8), rect.move(1, 1), 2)
        pygame.draw.ellipse(surface, (250, 210, 90), rect, 2)
        # Freccia che rimbalza sopra il cerchio.
        ay = sy - r - 6 - int(3 * abs(math.sin(t * 3)))
        pts = [(sx - 5, ay - 6), (sx + 5, ay - 6), (sx, ay)]
        pygame.draw.polygon(surface, (40, 30, 8), [(x + 1, y + 1) for x, y in pts])
        pygame.draw.polygon(surface, (250, 210, 90), pts)

    def _draw_panel(self, surface):
        """Al posto del pannello d'allenamento: la scheda del passo corrente."""
        self._btns = []
        title, body, _goal = STEPS[self.step]
        f = hud.font(14)
        lines = _wrap(body, f, CARD_W - 28)
        h = 40 + len(lines) * 18 + 34
        W = surface.get_width()
        R = pygame.Rect((W - CARD_W) // 2, 60, CARD_W, h)
        hud.panel(surface, R)
        self._btns.append((R, "-"))
        n = f"{self.step}/{LAST}" if 0 < self.step < LAST else ""
        hud.text(surface, title.upper(), (R.x + 14, R.y + 10), 15, hud.GOLD, bold=True)
        if n:
            hud.text(surface, "Passo " + n, (R.right - 14, R.y + 12), 12, hud.DIM, right=True)
        for i, ln in enumerate(lines):
            hud.text(surface, ln, (R.x + 14, R.y + 36 + i * 18), 14, hud.TEXT)
        # Barra dei passi + pulsante.
        by = R.bottom - 22
        seg = (R.w - 140) / LAST
        for i in range(LAST):
            x0 = R.x + 14 + int(i * seg)
            c = (220, 180, 70) if i < self.step else (60, 60, 70)
            pygame.draw.rect(surface, c, (x0, by + 6, max(2, int(seg) - 3), 4))
        label = {0: "Inizia  [Invio]", LAST: "Allenamento  [Invio]"}.get(self.step, "Salta  >")
        br = pygame.Rect(R.right - 118, by - 2, 106, 20)
        hov = br.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surface, (58, 50, 26) if hov else (36, 32, 22), br, border_radius=3)
        pygame.draw.rect(surface, hud.TRIM_HI if hov else hud.TRIM, br, 1, border_radius=3)
        hud.text(surface, label, (br.centerx, br.y + 3), 12, hud.TEXT, center=True)
        self._skip_rect = br


def _wrap(text, f, width):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if f.size(t)[0] <= width:
            cur = t
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out
