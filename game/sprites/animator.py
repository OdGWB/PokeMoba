"""Animatore a stati per un'entità, con fallback a cerchio colorato.

Espone due classi intercambiabili (stessa interfaccia update/draw):
  - SpriteAnimator: usa un AnimationSet caricato da SpriteCollab.
  - FallbackAnimator: disegna un cerchio col muso rivolto nella direzione, usato
    quando mancano gli sprite.

`draw(surface, sx, sy)` riceve la posizione a terra dell'unità in pixel sulla
surface low-res; l'animatore gestisce da sé l'ancoraggio.
"""
from __future__ import annotations

import math

import pygame

from engine.vec import DIR_VECTORS

from .. import anim_tuning
from .spritesheet import AnimationSet

# Un'unità di durata PMD vale circa 1/30 di secondo (ritmo d'animazione).
DURATION_UNIT = 1.0 / 30.0


class SpriteAnimator:
    def __init__(self, anim_set: AnimationSet, scale: float = 1.0):
        self.anim_set = anim_set
        self.scale = scale          # <1 per rimpicciolire (es. minion)
        self._scaled: dict = {}     # cache dei frame scalati
        self._bboxes: dict = {}     # cache del riquadro del contenuto (pixel non trasparenti)
        self.state = "Idle"
        self.frame = 0
        self.timer = 0.0
        self.facing = 0
        self.oneshot: str | None = None   # animazione "una tantum" (Attack/Shoot/Hurt)
        self.oneshot_speed = 1.0          # moltiplicatore di velocità (es. Hop veloce)
        self.frozen = False               # True = resta fermo sul frame corrente (morte)
        self.pose: str | None = None      # posa continua al posto di Idle/Walk (es. Sleep)
        # Regolazioni dell'editor delle animazioni (anim_tuning): solo visive.
        self._cfg = None            # voce dell'azione in corso (o None)
        self._action = None         # "idle" | "walk" | "aa" | "move:<id>" | None
        self._lo, self._hi = 0, None   # fotogrammi tenuti dopo il taglio
        self._tv = -1               # versione della tabella in cache
        self._tune: dict = {}

    def _tuning(self, action):
        if not action:
            return None
        if self._tv != anim_tuning.version:
            self._tv = anim_tuning.version
            self._tune = anim_tuning.table(getattr(self.anim_set, "key", None))
        return self._tune.get(action)

    def _set_range(self, cfg, anim) -> None:
        n = anim.frame_count if anim is not None else 0
        self._lo, self._hi = anim_tuning.frame_range(cfg, n)

    def play_once(self, name: str, speed: float = 1.0, action: str | None = None) -> None:
        """Riproduce un'animazione una sola volta (a `speed`x), poi torna a Idle/Walk.
        `action` ("aa" o "move:<id>") applica le regolazioni dell'editor."""
        cfg = self._tuning(action)
        if cfg:
            if cfg.get("anim") and self.anim_set.has(cfg["anim"]):
                name = cfg["anim"]
            speed *= anim_tuning.speed_of(cfg)
        if name and self.anim_set.has(name) and self.oneshot != name:
            self.oneshot = name
            self.oneshot_speed = max(0.05, speed)
            self.state = name
            self._cfg, self._action = cfg, action
            self._set_range(cfg, self.anim_set.get(name))
            self.frame = self._lo
            self.timer = 0.0

    def snap_release(self) -> None:
        """Il colpo e' partito: se l'animazione non e' ancora al fotogramma del
        proiettile (regolato nell'editor), ci salta subito."""
        if not self.oneshot or not self._cfg:
            return
        anim = self.anim_set.get(self.state)
        r = anim_tuning.release_frame(self._cfg, anim.frame_count if anim else 0)
        if r is not None and self.frame < r:
            self.frame = r
            self.timer = 0.0

    def freeze(self, name: str) -> None:
        """Blocca l'animatore sull'ultimo frame di `name` (usato alla morte: la
        posa Hurt resta ferma mentre l'unità si dissolve)."""
        if self.anim_set.has(name):
            self.state = name
            self.oneshot = None
            self.frozen = True
            anim = self.anim_set.get(name)
            self._cfg, self._action = None, None
            self._set_range(None, anim)
            self.frame = max(0, anim.frame_count - 1)

    def _frame_surface(self, state, direction, idx, frame):
        if self.scale == 1.0:
            return frame
        key = (state, direction, idx)
        s = self._scaled.get(key)
        if s is None:
            w = max(1, int(frame.get_width() * self.scale))
            h = max(1, int(frame.get_height() * self.scale))
            s = pygame.transform.scale(frame, (w, h))
            self._scaled[key] = s
        return s

    def _resolve_state(self, moving: bool) -> str:
        if self.pose and self.anim_set.has(self.pose):
            return self.pose   # addormentato: resta nella posa finché dura
        want = "Walk" if moving else "Idle"
        if self.anim_set.has(want):
            return want
        # Ripieghi ragionevoli se mancano certe animazioni.
        for alt in ("Idle", "Walk"):
            if self.anim_set.has(alt):
                return alt
        # Qualsiasi animazione disponibile.
        return next(iter(self.anim_set.anims.keys()))

    def update(self, dt: float, moving: bool, facing: int) -> None:
        self.facing = facing
        if self.frozen:            # morte: nessun avanzamento, resta sulla posa Hurt
            return
        if self.oneshot:
            target, action, cfg = self.oneshot, self._action, self._cfg
        else:
            target = self._resolve_state(moving)
            posed = bool(self.pose) and target == self.pose
            action = None if posed else ("walk" if moving else "idle")
            cfg = self._tuning(action)
            if cfg and cfg.get("anim") and self.anim_set.has(cfg["anim"]):
                target = cfg["anim"]
        if target != self.state or action != self._action:
            self.state = target
            self._cfg, self._action = cfg, action
            self._set_range(cfg, self.anim_set.get(target))
            self.frame = self._lo
            self.timer = 0.0

        anim = self.anim_set.get(self.state)
        if anim is None or anim.frame_count == 0:
            self.oneshot = None
            return
        lo = min(self._lo, anim.frame_count - 1)
        hi = anim.frame_count - 1 if self._hi is None else min(self._hi, anim.frame_count - 1)
        speed = self.oneshot_speed if self.oneshot else anim_tuning.speed_of(self._cfg)
        self.timer += dt * speed
        # Avanza finché il tempo accumulato copre la durata del frame corrente.
        while True:
            cur_dur = max(1, anim.durations[self.frame % anim.frame_count]) * DURATION_UNIT
            if self.timer < cur_dur:
                break
            self.timer -= cur_dur
            self.frame += 1
            if self.frame > hi:
                if self.oneshot:              # una tantum finita: torna a Idle/Walk
                    self.oneshot = None
                    self.frame = hi
                    self.timer = 0.0
                    break
                self.frame = lo               # animazione normale: in loop
        self.frame %= anim.frame_count

    def draw(self, surface: pygame.Surface, sx: int, sy: int, alpha: int = 255,
             grow: float = 1.0) -> None:
        anim = self.anim_set.get(self.state)
        if anim is None or anim.frame_count == 0:
            return
        direction = self.facing % len(anim.frames)
        frames = anim.frames[direction]
        if not frames:
            return
        idx = self.frame % len(frames)
        frame = self._frame_surface(self.state, direction, idx, frames[idx])
        if grow != 1.0:   # ingrandito a tempo (Luna Piena): scala NEAREST, in cache
            g = round(grow, 2)
            gkey = (self.state, direction, idx, g)
            big = self._scaled.get(gkey)
            if big is None:
                big = pygame.transform.scale(frame, (max(1, int(frame.get_width() * g)),
                                                     max(1, int(frame.get_height() * g))))
                self._scaled[gkey] = big
                self._bboxes[gkey] = big.get_bounding_rect()
            bb = self._bboxes[gkey]
            if bb.width == 0:
                return
            if alpha < 255:
                big = big.copy()
                big.fill((255, 255, 255, max(0, alpha)), None, pygame.BLEND_RGBA_MULT)
            surface.blit(big, (sx - bb.centerx, sy - bb.bottom))
            return
        # Ancora il BORDO INFERIORE del contenuto reale (non del riquadro, che ha
        # margini trasparenti) al punto a terra, centrato orizzontalmente su di esso.
        key = (self.state, direction, idx)
        bb = self._bboxes.get(key)
        if bb is None:
            bb = frame.get_bounding_rect()
            self._bboxes[key] = bb
        if bb.width == 0:
            return
        if alpha < 255:   # dissolvenza (morte): moltiplica il canale alpha
            frame = frame.copy()
            frame.fill((255, 255, 255, max(0, alpha)), None, pygame.BLEND_RGBA_MULT)
        surface.blit(frame, (sx - bb.centerx, sy - bb.bottom))


class GroupAnimator(SpriteAnimator):
    """Gruppo di sprite per UN neutrale (es. 3 Tangela su un campo): il principale
    e' questo animator (primo membro, ancora la posizione), gli altri sono
    compagni cosmetici a offset fissi in pixel. L'unita' resta una sola."""

    def __init__(self, anim_set, scale=1.0, companions=()):
        super().__init__(anim_set, scale)
        self.companions = list(companions)   # [(SpriteAnimator, dx, dy)]

    def play_once(self, name, speed=1.0, action=None):
        super().play_once(name, speed, action)
        for c, _, _ in self.companions:
            c.play_once(name, speed, action)

    def update(self, dt, moving, facing):
        super().update(dt, moving, facing)
        for c, _, _ in self.companions:
            c.update(dt, moving, facing)

    def draw(self, surface, sx, sy, alpha=255):
        # Dal fondo al davanti: chi sta piu' in alto sullo schermo si disegna prima.
        items = [(dy, c, dx) for c, dx, dy in self.companions] + [(0, self, 0)]
        for dy, c, dx in sorted(items, key=lambda it: it[0]):
            if c is self:
                SpriteAnimator.draw(self, surface, sx, sy, alpha)
            else:
                c.draw(surface, sx + dx, sy + dy, alpha)


class FallbackAnimator:
    """Cerchio colorato con indicatore di direzione, per quando mancano gli sprite."""

    def __init__(self, color: tuple[int, int, int], radius_px: int):
        self.color = color
        self.radius = max(4, radius_px)
        self.facing = 0

    def play_once(self, name: str, speed: float = 1.0, action=None) -> None:
        pass

    def snap_release(self) -> None:
        pass

    def update(self, dt: float, moving: bool, facing: int) -> None:
        self.facing = facing

    def draw(self, surface: pygame.Surface, sx: int, sy: int, alpha: int = 255) -> None:
        cy = sy - self.radius  # centra il cerchio sopra il punto a terra
        # Ombra.
        shadow = pygame.Surface((self.radius * 2, self.radius), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 90), shadow.get_rect())
        surface.blit(shadow, (sx - self.radius, sy - self.radius // 2))
        # Corpo.
        pygame.draw.circle(surface, self.color, (sx, cy), self.radius)
        pygame.draw.circle(surface, (20, 20, 20), (sx, cy), self.radius, 1)
        # Indicatore di direzione (muso).
        dv = DIR_VECTORS[self.facing % 8]
        dl = math.hypot(dv.x, dv.y) or 1.0
        nx, ny = dv.x / dl, dv.y / dl
        tip = (int(sx + nx * self.radius), int(cy + ny * self.radius))
        pygame.draw.circle(surface, (255, 255, 255), tip, max(2, self.radius // 3))
