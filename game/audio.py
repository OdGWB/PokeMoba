"""Audio del client: musica di sottofondo e volumi (pygame.mixer).

La musica va in streaming da disco (pygame.mixer.music): niente decodifica del
file intero in RAM e costo per frame nullo (la riproduce il thread di SDL).
Volumi in [0, 1] salvati nelle opzioni: "master_volume" (generale), "music_volume",
e tre categorie di effetti: "combat_volume" (colpi, mosse, strutture), "ui_volume"
(clic dei menu, negozio) e "alert_volume" (ping, chat, livelli, uccisioni, esito).
Il vecchio "sfx_volume" fa da valore iniziale delle tre categorie se mancano.
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
_master_vol = 1.0
# categorie degli effetti sonori -> volume
CATEGORIES = ("combat", "ui", "alert")
_cat_vol = {"combat": 0.8, "ui": 0.8, "alert": 0.8}


def init(options: dict | None = None) -> bool:
    global _ok, _music_vol, _master_vol
    if options:
        _music_vol = _clamp(options.get("music_volume", _music_vol))
        _master_vol = _clamp(options.get("master_volume", _master_vol))
        old = options.get("sfx_volume")
        for c in CATEGORIES:
            v = options.get(f"{c}_volume", old)
            if v is not None:
                _cat_vol[c] = _clamp(v)
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
        pygame.mixer.music.set_volume(_music_vol * _master_vol)
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


def master_volume() -> float:
    return _master_vol


def category_volume(cat: str) -> float:
    return _cat_vol.get(cat, 0.8)


def sfx_volume(cat: str | None = None) -> float:
    """Volume effettivo degli effetti: generale x categoria (senza categoria: la
    piu' alta, usata solo per uscire presto quando e' tutto muto)."""
    c = _cat_vol.get(cat) if cat else max(_cat_vol.values())
    return _master_vol * (0.8 if c is None else c)


def _apply_music() -> None:
    if _ok:
        try:
            pygame.mixer.music.set_volume(_music_vol * _master_vol)
        except pygame.error:
            pass


def set_music_volume(v: float) -> None:
    global _music_vol
    _music_vol = _clamp(v)
    _apply_music()


def set_master_volume(v: float) -> None:
    global _master_vol
    _master_vol = _clamp(v)
    _apply_music()


def set_category_volume(cat: str, v: float) -> None:
    if cat in _cat_vol:
        _cat_vol[cat] = _clamp(v)


def scene_wants_menu_music(scene) -> bool:
    """La musica del menu suona su tutte le scene tranne le partite (che hanno
    una camera) e le schermate che la rifiutano esplicitamente (music=False)."""
    m = getattr(scene, "music", None)
    if m is not None:
        return bool(m)
    return getattr(scene, "camera", None) is None
