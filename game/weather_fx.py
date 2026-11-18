"""Atmosfera a schermo del METEO (pioggia, sole, vento): solo grafica.

Si disegna sopra mappa, unita' e particelle, sotto mirini, ping e UI. Tutto
quello che si puo' e' PRE-RENDERIZZATO una volta (per dimensione della vista) e a
ogni frame si fanno solo fill con blend e pochi blit:
  - PIOGGIA: tutta la scena piu' cupa e fredda (fill BLEND_RGB_MULT), due strati
    di gocce oblique (tessere pre-disegnate che scorrono, ancorate al mondo con
    parallasse) e piccoli schizzi a terra (sprite a 4 fotogrammi).
  - SOLE: scena piu' luminosa e calda (fill BLEND_RGB_ADD) + grande luce che
    entra dall'angolo in ALTO A SINISTRA (alone a gradini + fasci obliqui che
    ondeggiano piano), sommata in modo additivo.
  - VENTO: alone bianco ai bordi dello schermo e raffiche: sbuffi bianchi
    sottili e ricurvi che attraversano la vista da sinistra a destra.
Il cambio di meteo sfuma in FADE_S secondi (intensita' quantizzata a LEVELS
gradini: gli sprite a ogni gradino sono in cache, niente set_alpha per frame).
Pixel art: niente smoothscale, gli aloni sono costruiti a bassa risoluzione e
scalati NEAREST (bande nette).
"""
from __future__ import annotations

import math
import random

import numpy as np
import pygame

FADE_S = 1.6
LEVELS = 6                    # gradini d'intensita' durante la dissolvenza

# --- Pioggia ---------------------------------------------------------------
RAIN_MULT = (192, 200, 222)   # piu' buio e piu' freddo
RAIN_TILE = (96, 96)
RAIN_NEAR = dict(n=9, len=(7, 10), col=(190, 210, 232), a=(120, 170), spd=330, par=1.0)
RAIN_FAR = dict(n=14, len=(4, 6), col=(150, 172, 200), a=(70, 110), spd=210, par=0.6)
RAIN_DX = -0.32               # pendenza: cadono un filo verso sinistra
SPLASHES = 16
SPLASH_LIFE = 0.32
SPLASH_COL = (196, 214, 236)

# --- Sole --------------------------------------------------------------------
SUN_ADD = (16, 12, 3)
SUN_GLOW = (120, 92, 40)      # colore massimo dell'alone (additivo)
SUN_RAY = (46, 36, 14)

# --- Vento -------------------------------------------------------------------
WIND_ADD = (5, 7, 8)
WIND_AURA = (96, 104, 106)   # alone bianco ai bordi (additivo, massimo)
GUSTS = 9
GUST_COL = (232, 240, 240)

def _bands(v: np.ndarray, steps: int) -> np.ndarray:
    """Quantizza 0..1 in `steps` gradini netti (niente dithering: su un velo a
    tutto schermo il retino di Bayer si leggeva come una scacchiera)."""
    return np.clip(np.floor(v * steps) / steps, 0.0, 1.0)


def _add_surface(rgb: np.ndarray) -> pygame.Surface:
    """Surface RGB (senza alfa) da un array (h, w, 3) uint8, per BLEND_RGB_ADD."""
    surf = pygame.surfarray.make_surface(np.ascontiguousarray(rgb.transpose(1, 0, 2)))
    return surf.convert() if pygame.display.get_surface() else surf


class WeatherFx:
    def __init__(self):
        self.weather = "clear"      # meteo attualmente mostrato (anche in uscita)
        self.k = 0.0                # intensita' 0..1
        self._target = "clear"
        self._last_ms = None
        self._size = None
        self._cache: dict = {}
        self._rng = random.Random(7)
        self._gusts: list[list] = []
        self._splash: list[list] = []

    # ------------------------------------------------------------------ stato
    def set_weather(self, weather: str, now_ms: int) -> None:
        weather = weather if weather in ("rain", "sun", "wind") else "clear"
        self._target = weather
        dt = 0.0 if self._last_ms is None else max(0.0, min(0.1, (now_ms - self._last_ms) / 1000.0))
        self._last_ms = now_ms
        if self.weather == self._target:
            self.k = min(1.0, self.k + dt / FADE_S) if weather != "clear" else 0.0
        else:                       # prima si spegne quello vecchio, poi entra il nuovo
            self.k = max(0.0, self.k - dt / FADE_S)
            if self.k <= 0.0:
                self.weather = self._target
                self._gusts.clear(); self._splash.clear()
        self._dt = dt

    # ---------------------------------------------------------------- disegno
    def draw(self, surface: pygame.Surface, camera, weather: str) -> None:
        now = pygame.time.get_ticks()
        self.set_weather(weather, now)
        if self.weather == "clear" or self.k <= 0.0:
            return
        size = surface.get_size()
        if size != self._size:
            self._size = size; self._cache.clear()
        lvl = max(1, min(LEVELS, int(math.ceil(self.k * LEVELS))))
        t = now / 1000.0
        ox, oy = getattr(camera, "ox", 0), getattr(camera, "oy", 0)
        if self.weather == "rain":
            self._draw_rain(surface, lvl, t, ox, oy)
        elif self.weather == "sun":
            self._draw_sun(surface, lvl, t)
        else:
            self._draw_wind(surface, lvl, t, ox, oy)

    @staticmethod
    def _scale_col(col, f):
        return tuple(int(c * f) for c in col)

    # ------------------------------------------------------------------ pioggia
    def _rain_tile(self, spec, lvl, seed):
        """Tessera di gocce: RGB con colorkey + alfa di superficie + RLEACCEL, cosi'
        il blit salta i pixel vuoti (con l'alfa per pixel costava ~3,5 ms a frame)."""
        key = ("rt", seed, lvl)
        s = self._cache.get(key)
        if s is None:
            w, h = RAIN_TILE
            s = pygame.Surface((w, h))
            s.fill((0, 0, 0))
            rng = random.Random(seed)
            body = spec["col"]
            head = tuple(min(255, c + 40) for c in body)
            tail = tuple(int(c * 0.62) for c in body)
            for _ in range(spec["n"]):
                x = rng.randrange(w); y = rng.randrange(h)
                ln = rng.randint(*spec["len"])
                for i in range(ln):     # goccia obliqua di 1px: coda scura, testa chiara
                    px = int(round(x + RAIN_DX * i)) % w
                    py = (y + i) % h
                    c = tail if i < ln // 3 else (head if i >= ln - 2 else body)
                    s.set_at((px, py), c)
            s.set_colorkey((0, 0, 0), pygame.RLEACCEL)
            s.set_alpha(int(sum(spec["a"]) / 2 * lvl / LEVELS), pygame.RLEACCEL)
            self._cache[key] = s
        return s

    def _splash_frames(self, lvl):
        key = ("sp", lvl)
        fr = self._cache.get(key)
        if fr is None:
            fr = []
            f = lvl / LEVELS
            for i in range(4):          # anellino schiacciato che si allarga e svanisce
                rx, ry = 1 + i, 1 + i // 2
                s = pygame.Surface((2 * rx + 3, 2 * ry + 3), pygame.SRCALPHA)
                a = int((170 - 38 * i) * f)
                pygame.draw.ellipse(s, (*SPLASH_COL, a), (1, 1, 2 * rx + 1, 2 * ry + 1), 1)
                if i == 0:
                    s.set_at((rx + 1, 0), (*SPLASH_COL, a))
                fr.append(s)
            self._cache[key] = fr
        return fr

    def _draw_rain(self, surface, lvl, t, ox, oy):
        f = lvl / LEVELS
        # Velo cupo e freddo: BLIT di una superficie piena in cache (il fill con
        # special_flags in pygame non e' vettorizzato: ~2,5 ms contro ~0,07).
        key = ("veil", lvl)
        veil = self._cache.get(key)
        if veil is None:
            veil = pygame.Surface(self._size)
            veil.fill(tuple(int(255 - (255 - c) * f) for c in RAIN_MULT))
            self._cache[key] = veil
        surface.blit(veil, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        W, H = surface.get_size()
        # Schizzi a terra (ancorati al MONDO): posizioni nuove a ogni ciclo.
        fr = self._splash_frames(lvl)
        if len(self._splash) < SPLASHES:
            self._splash = [[0.0, 0.0, -self._rng.random() * SPLASH_LIFE] for _ in range(SPLASHES)]
        for sp in self._splash:
            sp[2] += self._dt
            if sp[2] >= SPLASH_LIFE or sp[2] < -SPLASH_LIFE:
                sp[0] = ox + self._rng.randrange(W); sp[1] = oy + self._rng.randrange(H)
                sp[2] = -self._rng.random() * 0.25
            if sp[2] < 0:
                continue
            img = fr[min(3, int(sp[2] / SPLASH_LIFE * 4))]
            surface.blit(img, (int(sp[0] - ox) - img.get_width() // 2,
                               int(sp[1] - oy) - img.get_height() // 2))
        # Gocce: due strati di tessere che scorrono (lontane piu' lente e tenui).
        tw, th = RAIN_TILE
        for spec, seed in ((RAIN_FAR, 11), (RAIN_NEAR, 23)):
            tile = self._rain_tile(spec, lvl, seed)
            fall = t * spec["spd"]
            sx = int(-ox * spec["par"] + fall * RAIN_DX) % tw
            sy = int(-oy * spec["par"] + fall) % th
            y = sy - th
            while y < H:
                x = sx - tw
                while x < W:
                    surface.blit(tile, (x, y))
                    x += tw
                y += th

    # --------------------------------------------------------------------- sole
    def _leveled(self, name, lvl, build):
        """Superficie additiva al gradino `lvl`: il campo (numpy, a 1/q della
        vista) si calcola UNA volta per dimensione; per gradino solo x f e scala."""
        key = (name, lvl)
        s = self._cache.get(key)
        if s is None:
            base = self._cache.get((name, "f"))
            if base is None:
                base = self._cache[(name, "f")] = build()
            rgb, q = base
            small = _add_surface(np.clip(rgb * (lvl / LEVELS), 0, 255).astype(np.uint8))
            h, w = rgb.shape[:2]
            s = self._cache[key] = pygame.transform.scale(small, (w * q, h * q))
        return s

    def _sun_glow(self, lvl):
        def build():
            W, H = self._size
            q = 2                                   # a meta' risoluzione, scalato NEAREST
            w, h = W // q + 4, H // q + 4      # margine: il sole ondeggia di qualche px
            ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
            # Alone: dall'angolo in alto a sinistra (fuori schermo), raggio ~1,1 vista.
            cx, cy = -0.12 * w, -0.25 * h
            d = np.hypot((xs - cx) / (1.15 * w), (ys - cy) / (1.0 * w))
            glow = np.clip(1.0 - d, 0.0, 1.0) ** 1.6
            glow = _bands(glow, 14)
            # Fasci obliqui (verso il basso a destra), larghi e tenui.
            u = (xs * 0.62 - ys * 0.78)             # coordinata perpendicolare al fascio
            ray = np.zeros_like(u)
            for c0, wid, amp in ((0.10, 0.07, 1.0), (0.28, 0.045, 0.7), (-0.05, 0.05, 0.6),
                                 (0.43, 0.035, 0.5)):
                ray += amp * np.clip(1.0 - np.abs(u / w - c0) / wid, 0.0, 1.0)
            ray *= np.clip(1.15 - d, 0.0, 1.0)      # i fasci si spengono lontano
            ray = _bands(np.clip(ray, 0, 1), 8)
            return (glow[..., None] * np.array(SUN_GLOW, np.float32)
                    + ray[..., None] * np.array(SUN_RAY, np.float32)
                    + np.array(SUN_ADD, np.float32)), q
        return self._leveled("sun", lvl, build)

    def _draw_sun(self, surface, lvl, t):
        glow = self._sun_glow(lvl)
        # I fasci respirano piano: piccolo ondeggiamento dell'intero alone.
        dx = int(round(3 * math.sin(t * 0.35))); dy = int(round(2 * math.sin(t * 0.27 + 1.0)))
        surface.blit(glow, (dx - 3, dy - 3), special_flags=pygame.BLEND_RGB_ADD)

    # -------------------------------------------------------------------- vento
    def _wind_aura(self, lvl):
        def build():
            q = 2                                   # a meta' risoluzione, scalato NEAREST
            W, H = self._size[0] // q + 2, self._size[1] // q + 2
            ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
            # Distanza ellittica dal centro: alone bianco morbido verso i bordi
            # (rettangolare sembrava una cornice).
            d = np.hypot((xs - W / 2) / (W / 2), (ys - H / 2) / (H / 2))
            e = np.clip((d - 0.62) / 0.75, 0.0, 1.0)
            e = _bands(e * e * (3 - 2 * e), 12)
            return (e[..., None] * np.array(WIND_AURA, np.float32)
                    + np.array(WIND_ADD, np.float32)), q
        return self._leveled("aura", lvl, build)

    def _gust_sprites(self, lvl):
        key = ("gust", lvl)
        g = self._cache.get(key)
        if g is None:
            g = []
            f = lvl / LEVELS
            rng = random.Random(5)
            for v in range(6):          # sbuffo: nastro ondulato di 2px, ricciolo in coda
                L = rng.randint(56, 96)
                amp = rng.uniform(2.0, 3.5); per = rng.uniform(26, 40)
                s = pygame.Surface((L + 12, 22), pygame.SRCALPHA)
                yc = 11
                for i in range(L):
                    y = int(round(yc + amp * math.sin(i / per * 2 * math.pi)))
                    edge = min(1.0, min(i, L - 1 - i) / (0.28 * L))
                    a = int(edge * 190 * f)
                    s.set_at((i + 4, y), (*GUST_COL, a))
                    if edge > 0.55:     # corpo spesso al centro, sottile ai capi
                        s.set_at((i + 4, y + 1), (*GUST_COL, a // 2))
                if v % 2 == 0:          # ricciolo finale (piccolo vortice)
                    cx = L + 3
                    cy = yc + amp * math.sin((L - 1) / per * 2 * math.pi) - 3
                    for j in range(16):
                        ang = math.pi / 2 - j * 0.40
                        x = cx + 3.5 * math.cos(ang); y = cy + 3.5 * math.sin(ang)
                        s.set_at((int(round(x)), int(round(y))),
                                 (*GUST_COL, int((150 - 6 * j) * f)))
                g.append(s)
            self._cache[key] = g
        return g

    def _draw_wind(self, surface, lvl, t, ox, oy):
        surface.blit(self._wind_aura(lvl), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        W, H = surface.get_size()
        sprites = self._gust_sprites(lvl)
        rng = self._rng
        if len(self._gusts) < GUSTS:
            self._gusts = [[ox + rng.uniform(-W, W), oy + rng.uniform(0, H),
                            rng.uniform(140, 230), rng.randrange(len(sprites)),
                            rng.uniform(0, 6.28)] for _ in range(GUSTS)]
        for gst in self._gusts:
            gst[0] += gst[2] * self._dt
            sx = gst[0] - ox
            sy = gst[1] - oy + 3 * math.sin(t * 2.2 + gst[4])
            img = sprites[gst[3]]
            if sx > W + 10 or sy < -20 or sy > H + 20 or sx < -W - 80:
                # riparte da sinistra, fuori vista, in un punto a caso del mondo visibile
                gst[0] = ox - img.get_width() - rng.uniform(0, W * 0.6)
                gst[1] = oy + rng.uniform(0, H)
                gst[2] = rng.uniform(140, 230); gst[3] = rng.randrange(len(sprites))
                continue
            surface.blit(img, (int(sx), int(sy)))
