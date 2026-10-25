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

    @property
    def frame_count(self) -> int:
        return len(self.durations)


class AnimationSet:
    """Tutte le animazioni di un Pokémon, pronte per il rendering."""

    def __init__(self, anims: dict[str, LoadedAnim]):
        self.anims = anims

    def has(self, name: str) -> bool:
        return name in self.anims

    def get(self, name: str) -> LoadedAnim | None:
        return self.anims.get(name)


def _source_sheet_name(info: AnimInfo) -> str:
    # Se l'anim è un CopyOf, il foglio è quello della sorgente.
    base = info.copy_of if info.copy_of else info.name
    return f"{base}-Anim.png"


def load_pokemon_animations(sprite_dir: str | Path) -> AnimationSet | None:
    """Carica le animazioni da una cartella sprite PMD.

    Ritorna None se la cartella o AnimData.xml non esistono: in tal caso il
    client userà il fallback a cerchio colorato.
    """
    d = Path(sprite_dir)
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
            loaded[info.name] = LoadedAnim(frames=frames, durations=list(info.durations))

    if not loaded:
        return None
    return AnimationSet(loaded)


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
