"""Profilo del giocatore: NICKNAME e IMMAGINE PROFILO (ritratto di un leggendario).

Il profilo si salva sul PC del giocatore, FUORI dalla cartella del gioco
(%APPDATA%/PokeMoba/profile.json), così mandare lo zip del gioco agli amici non
si porta dietro il tuo nome. Al primo avvio non esiste e il gioco lo chiede.

Le immagini sono i ritratti "Normal" di PMD Sprite Collab (CC BY-NC 4.0),
scaricati da tools/fetch_avatars.py in assets/avatars/<dex>.png con i crediti
per autore in assets/avatars/credits.json. In rete l'avatar viaggia come numero
di Pokédex (u16, 0 = nessuno): i BOT non hanno avatar e si chiamano come il
loro Pokémon.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parent.parent
AVATAR_DIR = ROOT / "assets" / "avatars"
NAME_MAX = 16

# Leggendari (non i misteriosi), in ordine di Pokédex.
AVATARS: list[tuple[int, str]] = [
    (144, "Articuno"), (145, "Zapdos"), (146, "Moltres"), (150, "Mewtwo"),
    (243, "Raikou"), (244, "Entei"), (245, "Suicune"), (249, "Lugia"), (250, "Ho-Oh"),
    (377, "Regirock"), (378, "Regice"), (379, "Registeel"), (380, "Latias"),
    (381, "Latios"), (382, "Kyogre"), (383, "Groudon"), (384, "Rayquaza"),
    (480, "Uxie"), (481, "Mesprit"), (482, "Azelf"), (483, "Dialga"), (484, "Palkia"),
    (485, "Heatran"), (486, "Regigigas"), (487, "Giratina"), (488, "Cresselia"),
    (638, "Cobalion"), (639, "Terrakion"), (640, "Virizion"), (641, "Tornadus"),
    (642, "Thundurus"), (643, "Reshiram"), (644, "Zekrom"), (645, "Landorus"),
    (646, "Kyurem"),
    (716, "Xerneas"), (717, "Yveltal"), (718, "Zygarde"),
    (772, "Tipo Zero"), (773, "Silvally"), (785, "Tapu Koko"), (786, "Tapu Lele"),
    (787, "Tapu Bulu"), (788, "Tapu Fini"), (789, "Cosmog"), (790, "Cosmoem"),
    (791, "Solgaleo"), (792, "Lunala"), (800, "Necrozma"),
    (888, "Zacian"), (889, "Zamazenta"), (890, "Eternatus"), (891, "Kubfu"),
    (892, "Urshifu"), (894, "Regieleki"), (895, "Regidrago"), (896, "Glastrier"),
    (897, "Spectrier"), (898, "Calyrex"), (905, "Enamorus"),
    (1001, "Wo-Chien"), (1002, "Chien-Pao"), (1003, "Ting-Lu"), (1004, "Chi-Yu"),
    (1007, "Koraidon"), (1008, "Miraidon"), (1014, "Okidogi"), (1015, "Munkidori"),
    (1016, "Fezandipiti"), (1017, "Ogerpon"), (1024, "Terapagos"),
]
AVATAR_NAMES = dict(AVATARS)


# --- profilo salvato -------------------------------------------------------------------
def profile_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "PokeMoba" / "profile.json"


def clean_name(text) -> str:
    """Nickname mostrato agli altri: stampabile, senza spazi ai lati, max 16."""
    text = "".join(ch for ch in str(text) if ch.isprintable())
    return " ".join(text.split())[:NAME_MAX]


def _legacy_profile_path() -> Path:
    """Cartella usata quando il gioco si chiamava PokrLOL (il profilo si porta dietro)."""
    return profile_path().parent.parent / "PokrLOL" / "profile.json"


def load_profile(path=None):
    """{"name", "avatar"} oppure None se manca o è rotto (= va chiesto)."""
    p = Path(path or profile_path())
    if path is None and not p.is_file() and _legacy_profile_path().is_file():
        p = _legacy_profile_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        name = clean_name(data.get("name", ""))
        avatar = int(data.get("avatar", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if not name:
        return None
    return {"name": name, "avatar": avatar if avatar in AVATAR_NAMES else 0}


def save_profile(name, avatar, path=None) -> None:
    p = Path(path or profile_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"name": clean_name(name), "avatar": int(avatar)},
                            ensure_ascii=False), encoding="utf-8")


# --- immagini --------------------------------------------------------------------------
def available() -> list[tuple[int, str]]:
    """I leggendari di cui c'è davvero il ritratto (tools/fetch_avatars.py)."""
    return [(d, n) for d, n in AVATARS if (AVATAR_DIR / f"{d:04d}.png").is_file()]


_cache: dict = {}


def avatar_image(dex, side):
    """Ritratto del Pokédex `dex` scalato NEAREST a side x side (None = nessuno)."""
    if not dex:
        return None
    key = (int(dex), int(side))
    if key not in _cache:
        img = None
        path = AVATAR_DIR / f"{int(dex):04d}.png"
        if path.is_file():
            try:
                img = pygame.transform.scale(pygame.image.load(str(path)).convert_alpha(),
                                             (side, side))
            except pygame.error:
                img = None
        _cache[key] = img
    return _cache[key]


def draw_avatar(surface, dex, rect, border=(60, 84, 66)):
    """Riquadro dell'avatar; senza immagine (bot) un riquadro vuoto con '?'."""
    rect = pygame.Rect(rect)
    pygame.draw.rect(surface, (10, 14, 12), rect)
    img = avatar_image(dex, rect.w)
    if img is not None:
        surface.blit(img, rect.topleft)
    pygame.draw.rect(surface, border, rect, 1)


def load_credits() -> dict:
    try:
        return json.loads((AVATAR_DIR / "credits.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
