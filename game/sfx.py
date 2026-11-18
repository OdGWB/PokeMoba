"""Effetti sonori SINTETIZZATI in codice (numpy -> pygame.mixer.Sound).

Nessun file audio esterno (quindi niente da citare nei crediti): ogni suono e'
una piccola ricetta di onde (seno/quadra/rumore) con inviluppo, calcolata la
prima volta che serve e tenuta in cache. A frame solo play().

- play(name): suono d'interfaccia (menu, negozio, chat).
- play_at(name, pos, cam): suono nel mondo, attenuato con la distanza dal
  centro della camera e messo a destra/sinistra (stereo); fuori portata = muto.
- play_events(events, cam, me): traduce gli eventi fx cosmetici del motore.

Ogni suono ha un intervallo minimo tra due riproduzioni (THROTTLE): in una
mischia con 30 colpi nello stesso frame se ne sente uno, non 30 sovrapposti.
Se il mixer non c'e' (headless, nessuna scheda audio) tutto e' no-op.
"""
from __future__ import annotations

import math

import numpy as np
import pygame

from . import audio

RATE = 22050
_cache: dict = {}
_last: dict = {}
_ready = None
HEAR_TILES = 17.0          # oltre questa distanza dal centro dello schermo: muto
TILE = 24


def _init() -> bool:
    global _ready, RATE
    if _ready is not None:
        return _ready
    _ready = False
    if not audio.init():
        return False
    try:
        info = pygame.mixer.get_init()
        if not info:
            return False
        RATE = info[0]
        pygame.mixer.set_num_channels(32)
        _ready = True
    except pygame.error:
        _ready = False
    return _ready


# ---------------------------------------------------------------- sintesi
def _t(dur):
    return np.arange(int(RATE * dur)) / RATE


def _env(n, attack=0.005, decay_pow=1.0):
    """Inviluppo: salita lineare breve + discesa (1-x)^p."""
    a = max(1, int(RATE * attack))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    rest = n - a
    if rest > 0:
        e[a:] = (1 - np.linspace(0, 1, rest)) ** decay_pow
    return e


def _sweep(f0, f1, dur, wave="sine"):
    t = _t(dur)
    f = np.geomspace(max(1, f0), max(1, f1), len(t))
    ph = 2 * np.pi * np.cumsum(f) / RATE
    if wave == "square":
        return np.sign(np.sin(ph)) * 0.6
    if wave == "tri":
        return 2 / np.pi * np.arcsin(np.sin(ph))
    return np.sin(ph)


def _tone(f, dur, wave="sine"):
    return _sweep(f, f, dur, wave)


def _noise(dur, lp=1.0, seed=1):
    """Rumore bianco passato in un passa-basso a un polo (lp 0..1: 1 = nessun filtro)."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(-1, 1, int(RATE * dur))
    if lp < 1.0:
        y = np.empty_like(x)
        acc = 0.0
        # filtro a un polo vettoriale via lfilter manuale (numpy puro, durate brevi)
        for i in range(len(x)):
            acc += lp * (x[i] - acc)
            y[i] = acc
        x = y / max(1e-6, np.max(np.abs(y)))
    return x


def _seq(parts, gap=0.0):
    out = []
    for p in parts:
        out.append(p)
        if gap:
            out.append(np.zeros(int(RATE * gap)))
    return np.concatenate(out)


def _mix(*arrs):
    n = max(len(a) for a in arrs)
    out = np.zeros(n)
    for a in arrs:
        out[:len(a)] += a
    return out


def _note(f, dur, wave="tri", pow_=1.6, harm=0.25):
    s = _tone(f, dur, wave) + harm * _tone(f * 2, dur, "sine")
    return s * _env(len(s), 0.004, pow_)


def _recipe(name):
    if name == "ui_click":
        s = _tone(1250, 0.035, "square") * _env(int(RATE * 0.035), 0.002, 3)
        return s * 0.35
    if name == "ui_move":
        s = _tone(820, 0.025, "tri") * _env(int(RATE * 0.025), 0.002, 3)
        return s * 0.35
    if name == "ui_confirm":
        return _seq([_note(660, 0.06), _note(990, 0.12)]) * 0.45
    if name == "ui_back":
        return _seq([_note(700, 0.06), _note(470, 0.11)]) * 0.4
    if name == "ui_error":
        s = _tone(180, 0.14, "square") * _env(int(RATE * 0.14), 0.003, 1.2)
        return s * 0.3
    if name == "buy":
        return _mix(_note(1320, 0.18, "sine", 2.2), np.concatenate(
            [np.zeros(int(RATE * 0.06)), _note(1980, 0.22, "sine", 2.2)])) * 0.38
    if name == "sell":
        return _seq([_note(1320, 0.07, "sine"), _note(990, 0.14, "sine")]) * 0.35
    if name == "gold":
        return _mix(_note(1568, 0.16, "sine", 2.5), _note(2350, 0.12, "sine", 3) * 0.6) * 0.3
    # --- combattimento
    if name == "hit_melee":
        n = _noise(0.07, lp=0.35, seed=3) * _env(int(RATE * 0.07), 0.001, 2.5)
        thump = _sweep(220, 90, 0.07) * _env(int(RATE * 0.07), 0.001, 2)
        return (n * 0.55 + thump * 0.6) * 0.5
    if name == "hit_ranged":
        n = _noise(0.05, lp=0.5, seed=4) * _env(int(RATE * 0.05), 0.001, 3)
        return (n * 0.5 + _sweep(600, 250, 0.05) * _env(int(RATE * 0.05), 0.001, 2) * 0.4) * 0.45
    if name == "swing":
        n = _noise(0.09, lp=0.25, seed=5)
        e = np.sin(np.linspace(0, np.pi, len(n))) ** 2
        return n * e * 0.3
    if name == "shoot":
        s = _sweep(1100, 380, 0.08, "tri") * _env(int(RATE * 0.08), 0.002, 1.5)
        return s * 0.28
    if name == "minion_shot":
        s = _sweep(900, 500, 0.05, "tri") * _env(int(RATE * 0.05), 0.002, 2)
        return s * 0.18
    if name == "tower_shot":
        z = _sweep(520, 120, 0.28, "square") * _env(int(RATE * 0.28), 0.004, 1.4)
        n = _noise(0.28, lp=0.2, seed=6) * _env(int(RATE * 0.28), 0.002, 2.2)
        return (z * 0.3 + n * 0.35) * 0.55
    if name == "cast":
        n = _noise(0.22, lp=0.18, seed=7)
        e = np.sin(np.linspace(0, np.pi, len(n))) ** 1.5
        sh = _sweep(500, 1300, 0.22, "sine") * e * 0.25
        return (n * e * 0.5 + sh) * 0.4
    if name == "dash":
        n = _noise(0.18, lp=0.3, seed=8)
        e = np.sin(np.linspace(0, np.pi, len(n))) ** 2
        return n * e * 0.4
    if name == "boom":
        n = _noise(0.35, lp=0.08, seed=9) * _env(int(RATE * 0.35), 0.002, 1.8)
        lo = _sweep(140, 45, 0.35) * _env(int(RATE * 0.35), 0.002, 1.5)
        return (n * 0.6 + lo * 0.7) * 0.55
    if name == "buff":
        return _seq([_note(784, 0.07, "sine"), _note(1047, 0.07, "sine"),
                     _note(1319, 0.14, "sine")]) * 0.25
    if name == "beam":
        t = _t(0.35)
        s = (np.sign(np.sin(2 * np.pi * 180 * t)) * 0.4 + _noise(0.35, lp=0.4, seed=10) * 0.4)
        s *= (0.6 + 0.4 * np.sin(2 * np.pi * 30 * t)) * _env(len(t), 0.02, 1.2)
        return s * 0.35
    if name == "death":
        s = _sweep(500, 140, 0.18, "tri") * _env(int(RATE * 0.18), 0.002, 1.4)
        return s * 0.3
    if name == "death_big":
        s = _sweep(300, 50, 0.6, "square") * _env(int(RATE * 0.6), 0.004, 1.3)
        n = _noise(0.6, lp=0.1, seed=11) * _env(int(RATE * 0.6), 0.004, 1.6)
        return (s * 0.35 + n * 0.45) * 0.6
    # --- eventi del giocatore
    if name == "level_up":
        return _seq([_note(f, 0.075) for f in (523, 659, 784)] + [_note(1047, 0.25)]) * 0.42
    if name == "evolve":
        a = _seq([_note(f, 0.07, "tri", 1.2) for f in (392, 523, 659, 784, 1047)]
                 + [_note(1568, 0.5, "tri", 1.2)])
        sh = _tone(3136, len(a) / RATE, "sine") * 0.06 * np.sin(np.linspace(0, 40, len(a)))
        return (a + sh) * 0.4
    if name == "my_death":
        return _seq([_note(392, 0.16, "square", 1.3), _note(311, 0.16, "square", 1.3),
                     _note(233, 0.45, "square", 1.1)]) * 0.28
    if name == "kill":
        return _seq([_note(880, 0.06, "square", 2), _note(1319, 0.16, "square", 2)]) * 0.28
    if name == "structure_down":
        n = _noise(0.9, lp=0.06, seed=12) * _env(int(RATE * 0.9), 0.003, 1.3)
        lo = _sweep(110, 35, 0.9) * _env(int(RATE * 0.9), 0.003, 1.1)
        return (n * 0.7 + lo * 0.8) * 0.6
    if name == "victory":
        return _seq([_note(f, d, "square", 1.3) for f, d in
                     ((523, 0.13), (659, 0.13), (784, 0.13), (1047, 0.2), (784, 0.1), (1047, 0.55))]) * 0.3
    if name == "defeat":
        return _seq([_note(f, d, "tri", 1.2) for f, d in
                     ((523, 0.22), (466, 0.22), (415, 0.22), (349, 0.7))]) * 0.38
    # --- squadra
    if name == "ping":
        return _seq([_note(1760, 0.07, "sine", 2), _note(1760, 0.12, "sine", 2)], gap=0.03) * 0.35
    if name == "ping_danger":
        return _seq([_note(587, 0.09, "square", 1.5), _note(440, 0.16, "square", 1.5)]) * 0.3
    if name == "ping_omw":
        return _seq([_note(880, 0.05, "sine"), _note(1175, 0.05, "sine"),
                     _note(1568, 0.1, "sine")]) * 0.32
    if name == "ping_help":
        return _seq([_note(1047, 0.08, "tri"), _note(1047, 0.08, "tri"),
                     _note(1047, 0.12, "tri")], gap=0.04) * 0.32
    if name == "ping_missing":
        return _seq([_note(988, 0.08, "sine"), _note(740, 0.14, "sine")]) * 0.33
    if name == "chat":
        return _note(1400, 0.06, "sine", 3) * 0.3
    if name == "vote":
        return _mix(_note(880, 0.5, "sine", 1.5), _note(1320, 0.5, "sine", 1.8) * 0.5) * 0.35
    return None


# Intervallo minimo (s) tra due riproduzioni dello stesso suono.
THROTTLE = {"hit_melee": 0.05, "hit_ranged": 0.05, "swing": 0.06, "shoot": 0.06,
            "minion_shot": 0.09, "tower_shot": 0.1, "cast": 0.06, "dash": 0.08,
            "boom": 0.09, "buff": 0.12, "beam": 0.15, "death": 0.05, "gold": 0.04,
            "ui_move": 0.02, "ui_click": 0.02}

NAMES = ("ui_click", "ui_move", "ui_confirm", "ui_back", "ui_error", "buy", "sell", "gold",
         "hit_melee", "hit_ranged", "swing", "shoot", "minion_shot", "tower_shot", "cast",
         "dash", "boom", "buff", "beam", "death", "death_big", "level_up", "evolve",
         "my_death", "kill", "structure_down", "victory", "defeat", "ping", "ping_danger",
         "ping_omw", "ping_help", "ping_missing", "chat", "vote")


def samples(name):
    """Campioni float (mono, -1..1) del suono: usato dai test e da _sound."""
    s = _recipe(name)
    if s is None:
        return None
    return np.clip(s, -1.0, 1.0)


def _sound(name):
    snd = _cache.get(name)
    if snd is not None or name in _cache:
        return snd
    s = samples(name)
    snd = None
    if s is not None:
        try:
            info = pygame.mixer.get_init()
            ch = info[2] if info else 2
            data = (s * 32000).astype(np.int16)
            if ch > 1:
                data = np.repeat(data[:, None], ch, axis=1)
            snd = pygame.sndarray.make_sound(np.ascontiguousarray(data))
        except (pygame.error, ValueError):
            snd = None
    _cache[name] = snd
    return snd


def _now():
    return pygame.time.get_ticks() / 1000.0


def play(name: str, vol: float = 1.0, pan: float = 0.0) -> None:
    if not _init():
        return
    v = audio.sfx_volume() * vol
    if v <= 0.01:
        return
    now = _now()
    gap = THROTTLE.get(name, 0.0)
    if gap and now - _last.get(name, -9.0) < gap:
        return
    snd = _sound(name)
    if snd is None:
        return
    _last[name] = now
    try:
        chn = snd.play()
        if chn is not None:
            l = v * min(1.0, 1.0 - pan)
            r = v * min(1.0, 1.0 + pan)
            chn.set_volume(max(0.0, l), max(0.0, r))
    except pygame.error:
        pass


def _cam_center(cam):
    return ((cam.x + cam.view_w / 2) / TILE, (cam.y + cam.view_h / 2) / TILE)


def play_at(name: str, pos, cam, vol: float = 1.0) -> None:
    """Suono nel mondo: pos in tile. Muto oltre HEAR_TILES dal centro dello schermo."""
    if cam is None or pos is None:
        play(name, vol)
        return
    cx, cy = _cam_center(cam)
    dx, dy = pos[0] - cx, pos[1] - cy
    d = math.hypot(dx, dy)
    if d >= HEAR_TILES:
        return
    k = 1.0 - (d / HEAR_TILES) ** 1.5
    pan = max(-0.7, min(0.7, dx / 14.0))
    play(name, vol * k, pan)


_MOVE_SOUND = {"projectile": "shoot", "area": "boom", "cone": "swing", "beam": "beam",
               "dash": "dash", "blink": "dash", "buff": "buff", "zone": "cast",
               "pillar": "boom", "rockspike": "boom", "storm": "cast", "vortex": "cast",
               "thunderstrike": "boom", "push": "dash", "pull": "dash"}


def _pos(e):
    for k in ("c", "b", "a"):
        p = e.get(k)
        if p is not None and len(p) >= 2:
            return p
    return None


def play_events(events, cam, me=None) -> None:
    """Suoni per gli eventi fx del motore (cosmetici). Una sola passata, nessuna
    allocazione pesante: ogni evento e' un lookup + play_at (gia' limitato)."""
    if not events or not _init() or audio.sfx_volume() <= 0.01:
        return
    for e in events:
        kind = e.get("kind")
        if kind == "aa_hit":
            play_at("hit_melee" if e.get("melee") else "hit_ranged", _pos(e), cam,
                    1.0 if (e.get("src") == me or e.get("hit") == me) else 0.7)
        elif kind == "attack":
            if not e.get("melee", False):
                play_at("shoot", e.get("a"), cam, 0.8)
            elif e.get("src") is None:          # fendenti delle mosse in mischia
                play_at("swing", _pos(e), cam, 0.8)
        elif kind == "tower_shot":
            play_at("tower_shot", e.get("a"), cam)
        elif kind == "minion_shot":
            play_at("minion_shot", e.get("a"), cam)
        elif kind == "unit_death":
            play_at("death_big" if e.get("big") else "death", _pos(e), cam, 0.8)
        elif kind == "gold":
            if me is not None and e.get("who") == me:
                play("gold", 0.9)
        else:
            name = _MOVE_SOUND.get(kind)
            if name is not None:
                play_at(name, _pos(e), cam, 0.85)


def preload() -> None:
    """Calcola tutti i suoni (opzionale: al primo uso si calcolano da soli)."""
    if _init():
        for n in NAMES:
            _sound(n)


class Watcher:
    """Suoni dei cambi di stato del PROPRIO Pokemon e della partita, ricavati
    confrontando due fotografie consecutive (stessa logica offline e online:
    la scena passa i valori che ha). Il primo update registra soltanto."""

    def __init__(self):
        self.prev = None

    def update(self, *, level=None, form=None, alive=None, items=None, gold=None,
               kills=None, structures=None, result=None) -> list:
        cur = {"level": level, "form": form, "alive": alive,
               "items": tuple(items) if items is not None else None,
               "gold": gold, "kills": kills, "structures": structures, "result": result}
        prev, self.prev = self.prev, cur
        played = []
        if prev is None:
            return played

        def ch(k):
            return prev[k] is not None and cur[k] is not None and prev[k] != cur[k]

        if ch("result") or (prev["result"] is None and cur["result"] is not None):
            played.append("victory" if cur["result"] == "win" else "defeat")
        if ch("form"):
            played.append("evolve")
        elif ch("level") and cur["level"] > prev["level"]:
            played.append("level_up")
        if ch("alive") and not cur["alive"]:
            played.append("my_death")
        if ch("kills") and cur["kills"] > prev["kills"]:
            played.append("kill")
        if ch("items"):
            if ch("gold") and cur["gold"] > prev["gold"]:
                played.append("sell")
            else:
                played.append("buy")
        if ch("structures") and cur["structures"] < prev["structures"]:
            played.append("structure_down")
        for n in played:
            play(n)
        return played
