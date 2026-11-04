"""Parser di AnimData.xml (formato PMD / SpriteCollab).

PURO: usa solo xml.etree, nessun pygame, così è testabile senza grafica.

Struttura tipica del file:

    <AnimData>
      <ShadowSize>1</ShadowSize>
      <Anims>
        <Anim>
          <Name>Walk</Name>
          <Index>1</Index>
          <FrameWidth>24</FrameWidth>
          <FrameHeight>32</FrameHeight>
          <Durations>
            <Duration>4</Duration>
            <Duration>4</Duration>
          </Durations>
        </Anim>
        <Anim>
          <Name>Idle</Name>
          <Index>0</Index>
          <CopyOf>Walk</CopyOf>
        </Anim>
      </Anims>
    </AnimData>

Nei fogli *-Anim.png le righe sono le 8 direzioni (vedi engine.vec.DIR_NAMES) e
le colonne i fotogrammi dell'animazione.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AnimInfo:
    name: str
    index: int = 0
    frame_width: int = 0
    frame_height: int = 0
    durations: list[int] = field(default_factory=list)  # durata di ogni frame (in tick)
    copy_of: str | None = None
    hit_frame: int = -1     # <HitFrame> del file (fotogramma del colpo), -1 = assente

    @property
    def frame_count(self) -> int:
        return len(self.durations)

    @property
    def sheet_filename(self) -> str:
        """Nome del foglio sprite associato (es. 'Walk' -> 'Walk-Anim.png')."""
        return f"{self.name}-Anim.png"


def _text_int(node, tag: str, default: int = 0) -> int:
    el = node.find(tag)
    if el is None or el.text is None:
        return default
    return int(el.text.strip())


def parse_anim_data(path: str | Path) -> dict[str, AnimInfo]:
    """Legge un AnimData.xml e ritorna {nome_anim: AnimInfo}.

    Risolve i riferimenti <CopyOf> copiando dimensioni e durate dall'anim
    sorgente.
    """
    root = ET.parse(str(path)).getroot()
    anims_node = root.find("Anims")
    if anims_node is None:
        return {}

    result: dict[str, AnimInfo] = {}
    for anim in anims_node.findall("Anim"):
        name_el = anim.find("Name")
        if name_el is None or name_el.text is None:
            continue
        name = name_el.text.strip()
        copy_el = anim.find("CopyOf")
        copy_of = copy_el.text.strip() if (copy_el is not None and copy_el.text) else None

        durations = [int(d.text.strip()) for d in anim.findall("Durations/Duration")
                     if d.text is not None]

        result[name] = AnimInfo(
            name=name,
            index=_text_int(anim, "Index", 0),
            frame_width=_text_int(anim, "FrameWidth", 0),
            frame_height=_text_int(anim, "FrameHeight", 0),
            durations=durations,
            copy_of=copy_of,
            hit_frame=_text_int(anim, "HitFrame", -1),
        )

    # Risolvi i CopyOf (anche a catena, con protezione dai cicli).
    for info in result.values():
        _resolve_copy(info, result, seen=set())
    return result


def _resolve_copy(info: AnimInfo, table: dict[str, AnimInfo], seen: set[str]) -> None:
    if info.copy_of is None or info.copy_of not in table:
        return
    if info.name in seen:
        return
    seen.add(info.name)
    src = table[info.copy_of]
    _resolve_copy(src, table, seen)
    if info.frame_width == 0:
        info.frame_width = src.frame_width
    if info.frame_height == 0:
        info.frame_height = src.frame_height
    if not info.durations:
        info.durations = list(src.durations)
    if info.hit_frame < 0:
        info.hit_frame = src.hit_frame
    # Il foglio da cui tagliare resta quello dell'anim sorgente.
    info.copy_of = src.name
