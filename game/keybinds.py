"""Tasti personalizzabili e preferenze di controllo (Opzioni).

Stato a livello di modulo, caricato da App all'avvio (options.json) e letto
dalle scene a ogni evento: le ricerche sono dizionari piccoli in cache, quindi
nessun costo per frame. Senza App (test, launcher) valgono i predefiniti.
"""
from __future__ import annotations

import pygame

# (azione, etichetta, tasto predefinito)
ACTIONS = [
    ("Q", "Mossa Q", pygame.K_q),
    ("W", "Mossa W", pygame.K_w),
    ("E", "Mossa E", pygame.K_e),
    ("R", "Mossa R (ultimate)", pygame.K_r),
    ("stop", "Fermati", pygame.K_s),
    ("recall", "Richiamo in base", pygame.K_b),
    ("smite", "Punizione", pygame.K_d),
    ("shop", "Negozio", pygame.K_p),
    ("camera", "Blocca la camera", pygame.K_y),
    ("score", "Tabellone (tieni premuto)", pygame.K_TAB),
    ("ping", "Ping (tieni + clic, trascina)", pygame.K_g),
    ("chat", "Chat rapida", pygame.K_t),
]
DEFAULTS = {a: k for a, _l, k in ACTIONS}
LABELS = {a: l for a, l, _k in ACTIONS}
SLOTS = ("Q", "W", "E", "R")
# Tasti riservati: non si possono assegnare (menu, schermo intero, oggetti 1-6).
RESERVED = {pygame.K_ESCAPE, pygame.K_F11, pygame.K_f, pygame.K_F2, pygame.K_F3,
            pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_1, pygame.K_2, pygame.K_3,
            pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_LCTRL, pygame.K_RCTRL,
            pygame.K_LSHIFT, pygame.K_RSHIFT}

FPS_CAPS = (30, 60, 120, 144, 240, 0)          # 0 = senza limite
CAM_SPEEDS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)

_keys = dict(DEFAULTS)
_slot_of: dict = {}
smart_cast = False        # lancio rapido: la mossa parte alla PRESSIONE del tasto
camera_speed = 1.0        # moltiplicatore dello scorrimento ai bordi
show_aa_range = True      # linea della gittata dell'attacco base attorno al proprio Pokémon


def _rebuild():
    _slot_of.clear()
    for s in SLOTS:
        _slot_of[_keys[s]] = s


def load(options: dict | None) -> None:
    global smart_cast, camera_speed, show_aa_range
    _keys.clear()
    _keys.update(DEFAULTS)
    opts = options or {}
    saved = opts.get("keys") or {}
    if isinstance(saved, dict):
        used = set()
        for a in DEFAULTS:
            k = saved.get(a)
            if isinstance(k, int) and k not in RESERVED and k not in used:
                _keys[a] = k
            used.add(_keys[a])
        # due azioni sullo stesso tasto (file modificato a mano): si torna ai predefiniti
        if len(set(_keys.values())) != len(_keys):
            _keys.clear()
            _keys.update(DEFAULTS)
    smart_cast = bool(opts.get("smart_cast", False))
    show_aa_range = bool(opts.get("show_aa_range", True))
    try:
        camera_speed = max(0.25, min(3.0, float(opts.get("camera_speed", 1.0))))
    except (TypeError, ValueError):
        camera_speed = 1.0
    _rebuild()


def key(action: str) -> int:
    return _keys.get(action, DEFAULTS.get(action, 0))


def slot_for(keycode: int):
    """Slot Q/W/E/R del tasto premuto, o None."""
    return _slot_of.get(keycode)


def key_name(action: str) -> str:
    return pygame.key.name(key(action)).upper() or "?"


def assign(action: str, keycode: int) -> str | None:
    """Assegna un tasto. Se era di un'altra azione, le due si SCAMBIANO.
    Ritorna un messaggio d'errore o None."""
    if keycode in RESERVED:
        return f"Il tasto {pygame.key.name(keycode).upper()} è riservato."
    old = _keys[action]
    for a, k in _keys.items():
        if k == keycode and a != action:
            _keys[a] = old
    _keys[action] = keycode
    _rebuild()
    return None


def reset() -> None:
    _keys.clear()
    _keys.update(DEFAULTS)
    _rebuild()


def to_options() -> dict:
    return {"keys": dict(_keys), "smart_cast": smart_cast, "camera_speed": camera_speed,
            "show_aa_range": show_aa_range}


_rebuild()
