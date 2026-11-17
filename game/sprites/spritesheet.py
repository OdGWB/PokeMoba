"""Taglio dei fogli sprite PMD in fotogrammi, con cache.

Usa pygame. Carica, per ogni animazione descritta in AnimData.xml, il relativo
foglio *-Anim.png e lo taglia in una matrice [direzione][frame].

I frame restano a risoluzione nativa: vengono disegnati sulla surface low-res,
che poi viene scalata in blocco (pixel nitidi), quindi non serve scalarli qui.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pygame

from .animdata import AnimInfo, parse_anim_data

NUM_DIRECTIONS = 8


@dataclass
class LoadedAnim:
    frames: list[list[pygame.Surface]]  # frames[direction][frame_idx]
    durations: list[int]                # durata (in unità) di ogni frame
    hit_frame: int = -1                 # <HitFrame> di AnimData.xml (-1 = assente)

    @property
    def frame_count(self) -> int:
        return len(self.durations)


class AnimationSet:
    """Tutte le animazioni di un Pokémon, pronte per il rendering."""

    def __init__(self, anims: dict[str, LoadedAnim], key: str | None = None):
        self.anims = anims
        # Nome della cartella sprite (es. "0856"): chiave delle regolazioni
        # dell'editor delle animazioni (game/anim_tuning.py).
        self.key = key

    def has(self, name: str) -> bool:
        return name in self.anims

    def get(self, name: str) -> LoadedAnim | None:
        return self.anims.get(name)


def _source_sheet_name(info: AnimInfo) -> str:
    # Se l'anim è un CopyOf, il foglio è quello della sorgente.
    base = info.copy_of if info.copy_of else info.name
    return f"{base}-Anim.png"


_ROOT = Path(__file__).resolve().parents[2]


def load_pokemon_animations(sprite_dir: str | Path) -> AnimationSet | None:
    """Carica le animazioni da una cartella sprite PMD.

    Ritorna None se la cartella o AnimData.xml non esistono: in tal caso il
    client userà il fallback a cerchio colorato.
    """
    d = Path(sprite_dir)
    if not d.is_absolute():
        # Relativa alla cartella del gioco, non a quella di avvio: nell'exe
        # (PyInstaller) gli asset stanno nella cartella estratta, non accanto.
        d = _ROOT / d
    xml_path = d / "AnimData.xml"
    if not d.is_dir() or not xml_path.is_file():
        return None

    try:
        infos = parse_anim_data(xml_path)
    except Exception:
        return None

    loaded: dict[str, LoadedAnim] = {}
    sheet_cache: dict[str, pygame.Surface] = {}

    for info in infos.values():
        if info.frame_width <= 0 or info.frame_height <= 0 or info.frame_count == 0:
            continue
        sheet_name = _source_sheet_name(info)
        sheet_path = d / sheet_name
        if not sheet_path.is_file():
            continue
        if sheet_name not in sheet_cache:
            try:
                sheet_cache[sheet_name] = pygame.image.load(str(sheet_path)).convert_alpha()
            except Exception:
                continue
        sheet = sheet_cache[sheet_name]
        frames = _cut_frames(sheet, info.frame_width, info.frame_height, info.frame_count)
        if frames:
            loaded[info.name] = LoadedAnim(frames=frames, durations=list(info.durations),
                                         hit_frame=info.hit_frame)

    if not loaded:
        return None
    return AnimationSet(loaded, key=d.name)


def _cut_frames(sheet: pygame.Surface, fw: int, fh: int, frame_count: int) -> list[list[pygame.Surface]]:
    """Taglia il foglio in [direzione][frame]. Le righe sono le 8 direzioni."""
    sheet_w, sheet_h = sheet.get_size()
    cols = max(1, sheet_w // fw)
    rows = max(1, sheet_h // fh)
    n_frames = min(frame_count, cols)
    n_dirs = min(NUM_DIRECTIONS, rows)

    out: list[list[pygame.Surface]] = []
    for row in range(n_dirs):
        row_frames: list[pygame.Surface] = []
        for col in range(n_frames):
            rect = pygame.Rect(col * fw, row * fh, fw, fh)
            frame = sheet.subsurface(rect).copy()
            row_frames.append(frame)
        out.append(row_frames)

    # Se il foglio ha meno di 8 righe, riusa l'ultima per le direzioni mancanti.
    while len(out) < NUM_DIRECTIONS and out:
        out.append(out[-1])
    return out


# Leggendari neutrali della giungla: (cartella sprite, scala).
_WILD_LEGEND_SPRITES = {
    "rain": ("assets/pokemon/0382", 1.3),   # Kyogre
    "sun": ("assets/pokemon/0383", 1.25),    # Groudon
    "wind": ("assets/pokemon/0384", 1.0),  # Rayquaza (sprite molto alto)
}
_ARCEUS_SPRITE = ("assets/pokemon/0493", 1.3)


# Campi della giungla (lato BLU, il ROSSO e' speculare) con sprite (tile del campo -> (cartella, scala)),
# 3v3 e 5v5: settore alto = Slowbro (blue buff, grosso) + Carnivine (piccolo a
# nord-ovest); settore basso = Magmortar (red buff, grosso).
_P = "assets/pokemon/"
_TANGELA = [(_P + "0114", 1.0, 0, 0), (_P + "0114", 1.0, -24, 6), (_P + "0114", 1.0, 24, 8)]
_HOPPIP = [(_P + "0187", 1.0, -12, -2), (_P + "0187", 1.0, 13, 6)]
_SPIDERS = [(_P + "0168", 1.0, 0, 0), (_P + "0167", 0.6, -22, 8),
            (_P + "0167", 0.6, 22, 7), (_P + "0167", 0.6, 1, 16)]
# Ogni membro: (cartella, scala, dx, dy in px dal punto del campo); il primo ancora
# l'unita'. Stessa disposizione su 3v3 e 5v5 (piccoli: tile del campo).
_BLUE_3V3 = {
    (29, 43): [(_P + "0080", 1.0, 0, 0)], (18, 37): [(_P + "0455", 1.0, 0, 0)],
    (57, 72): [(_P + "0467", 1.0, 0, 0)], (25, 53): _TANGELA,
    (63, 81): _HOPPIP, (47, 61): _SPIDERS,
}
_BLUE_5V5 = {
    (44, 64): [(_P + "0080", 1.0, 0, 0)], (27, 56): [(_P + "0455", 1.0, 0, 0)],
    (86, 108): [(_P + "0467", 1.0, 0, 0)], (38, 80): _TANGELA,
    (94, 122): _HOPPIP, (70, 92): _SPIDERS,
}


def _mirrored(blue: dict, size: int) -> dict:
    """Lato ROSSO: la mappa e' simmetrica rispetto al centro, (x, y) -> (W-x, H-y).
    Stessi Pokemon, e la disposizione del gruppo ruota di 180 gradi, cosi' ogni
    membro resta dallo stesso lato rispetto ai muri del suo campo."""
    return {(size - x, size - y): [(d, sc, -dx, -dy) for d, sc, dx, dy in g]
            for (x, y), g in blue.items()}


_CAMP_SPRITES = {**_BLUE_3V3, **_mirrored(_BLUE_3V3, 100),
                 **_BLUE_5V5, **_mirrored(_BLUE_5V5, 150)}


def wild_sprite_group(unit):
    """Membri di sprite [(cartella, scala, dx, dy), ...] di un neutrale (leggendari e
    campi con sprite), o None per gli altri (cerchio colorato)."""
    kind = getattr(unit, "kind", "")
    if kind == "camp":
        return _CAMP_SPRITES.get((int(unit.pos.x), int(unit.pos.y)))
    if kind == "arceus":
        d, sc = _ARCEUS_SPRITE
    elif kind == "meteo" and getattr(unit, "weather", "") in _WILD_LEGEND_SPRITES:
        d, sc = _WILD_LEGEND_SPRITES[unit.weather]
    else:
        return None
    return [(d, sc, 0, 0)]


def make_wild_animator(unit, load):
    """Animator di un neutrale con sprite (`load` = cache cartella->AnimationSet),
    o None. Con piu' membri ritorna un GroupAnimator."""
    from .animator import GroupAnimator, SpriteAnimator
    group = wild_sprite_group(unit)
    if not group:
        return None
    sets = [load(d) for d, _, _, _ in group]
    if sets[0] is None:
        return None
    comps = [(SpriteAnimator(a, scale=g[1]), g[2], g[3])
             for a, g in zip(sets[1:], group[1:]) if a is not None]
    return GroupAnimator(sets[0], scale=group[0][1], companions=comps)
