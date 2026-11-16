"""Audio del client: musica di sottofondo e volumi (pygame.mixer).

La musica va in streaming da disco (pygame.mixer.music): niente decodifica del
file intero in RAM e costo per frame nullo (la riproduce il thread di SDL).
Volumi in [0, 1] salvati nelle opzioni ("music_volume", "sfx_volume").
Se l'audio non e' disponibile (nessuna scheda, headless) tutto diventa no-op.
"""
from __future__ import annotations

from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parents[1]
MENU_MUSIC = ROOT / "assets" / "audio" / "menu_music.mp3"
FADE_MS = 800

_ok = None            # None = non ancora inizializzato
_current = None       # percorso della musica in corso
_music_vol = 0.6
_sfx_vol = 0.8


def init(options: dict | None = None) -> bool:
    global _ok, _music_vol, _sfx_vol
    if options:
        _music_vol = _clamp(options.get("music_volume", _music_vol))
        _sfx_vol = _clamp(options.get("sfx_volume", _sfx_vol))
    if _ok is None:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            _ok = True
        except pygame.error:
            _ok = False
    return _ok


def _clamp(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.6


def play_music(path: Path = MENU_MUSIC, loop: bool = True) -> None:
    """Avvia (in dissolvenza) la musica, se non sta gia' suonando."""
    global _current
    if not _ok or _current == path:
        return
    try:
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.set_volume(_music_vol)
        pygame.mixer.music.play(-1 if loop else 0, fade_ms=FADE_MS)
        _current = path
    except (pygame.error, FileNotFoundError):
        _current = None


def stop_music(fade_ms: int = FADE_MS) -> None:
    global _current
    if not _ok or _current is None:
        return
    try:
        pygame.mixer.music.fadeout(fade_ms)
    except pygame.error:
        pass
    _current = None


def music_volume() -> float:
    return _music_vol


def sfx_volume() -> float:
    return _sfx_vol


def set_music_volume(v: float) -> None:
    global _music_vol
    _music_vol = _clamp(v)
    if _ok:
        try:
            pygame.mixer.music.set_volume(_music_vol)
        except pygame.error:
            pass


def set_sfx_volume(v: float) -> None:
    global _sfx_vol
    _sfx_vol = _clamp(v)


def scene_wants_menu_music(scene) -> bool:
    """La musica del menu suona su tutte le scene tranne le partite (che hanno
    una camera) e le schermate che la rifiutano esplicitamente (music=False)."""
    m = getattr(scene, "music", None)
    if m is not None:
        return bool(m)
    return getattr(scene, "camera", None) is None
