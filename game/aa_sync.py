"""Sincronizzazione VISIVA dell'animazione dell'attacco base col motore.

Nessuna logica di gioco: il motore (engine/basic_attack.py) decide caricamento,
rilascio e danno. Qui si decide solo COME scorre l'animazione dello sprite
perché il fotogramma del colpo (HitFrame di AnimData.xml, o quello scelto da
tools/aa_anim_sync.py) cada ESATTAMENTE quando il motore rilascia il colpo.

Stile MOBA: l'animazione intera segue la velocità d'attacco.
  - fase 1, CARICAMENTO: dall'inizio al fotogramma del colpo in `windup` secondi
    (velocità s1). Se servirebbe una velocità assurda (attack speed altissima) si
    TAGLIANO i fotogrammi di preparazione iniziali invece di far lampeggiare tutto;
    se al contrario l'animazione è corta, rallenta fino a S1_MIN e poi TIENE la
    posa del colpo (anticipazione) finché il motore non rilascia.
  - fase 2, RECUPERO: dal colpo alla fine nel tempo rimasto del ciclo (s2), mai
    più lenta del naturale né molto più lenta della fase 1 (niente moviola).

Tabella: data/aa_anims.json, generata dal tool:
    { "<cartella sprite>": {"anim": "Shoot", "hit": 4, "melee": false}, ... }
Le regolazioni dell'editor (data/anim_overrides.json, azione "aa") vincono.
Puro: nessun pygame.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "aa_anims.json"

DURATION_UNIT = 1.0 / 30.0
S1_MAX = 4.0      # oltre si tagliano i fotogrammi di preparazione
S1_MIN = 0.6      # sotto si tiene la posa del colpo
S2_MAX = 6.0
HOLD_MAX = 0.35   # s: posa del colpo tenuta al massimo (se il rilascio non arriva)

# Animazioni candidate (in ordine) se la tabella non dice nulla.
MELEE_ANIMS = ("Attack", "Strike", "Swing", "Shoot")
RANGED_ANIMS = ("Shoot", "Attack", "Charge", "Strike")

_data: dict | None = None


def table() -> dict:
    global _data
    if _data is None:
        try:
            with open(PATH, encoding="utf-8") as f:
                raw = json.load(f)
            _data = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            _data = {}
    return _data


def entry(key) -> dict | None:
    return table().get(key) if key else None


def ticks(durations, lo: int, hi: int) -> int:
    """Durata (in unità PMD) dei fotogrammi lo..hi-1."""
    return sum(max(1, d) for d in durations[lo:hi])


def plan(durations, hit: int, windup: float, cycle: float, lo: int = 0, hi=None):
    """(primo fotogramma, s1, s2) per far cadere `hit` dopo `windup` secondi e
    finire l'animazione entro il ciclo. `lo`/`hi` = taglio dell'editor."""
    n = len(durations)
    if n == 0:
        return 0, 1.0, 1.0
    hi = n - 1 if hi is None else max(0, min(n - 1, hi))
    hit = max(lo, min(hi, hit))
    windup = max(0.03, windup)
    start = lo
    pre = ticks(durations, start, hit) * DURATION_UNIT
    # Troppo veloce: salta la preparazione (si tiene almeno un fotogramma prima del colpo).
    while pre / windup > S1_MAX and start < hit - 1:
        start += 1
        pre = ticks(durations, start, hit) * DURATION_UNIT
    s1 = max(S1_MIN, min(S1_MAX * 1.5, pre / windup)) if pre > 0 else 1.0
    post = ticks(durations, hit, hi + 1) * DURATION_UNIT
    rec = max(0.05, (cycle - windup) * 0.9)
    s2 = max(1.0, 0.7 * s1, post / rec)
    return start, s1, min(S2_MAX, s2)


def default_hit(durations, hit_frame: int) -> int:
    """Fotogramma del colpo: quello del file o, se manca, ~45% della durata."""
    n = len(durations)
    if n == 0:
        return 0
    if 0 <= hit_frame < n:
        return hit_frame
    tot = ticks(durations, 0, n)
    acc = 0
    for i, d in enumerate(durations):
        acc += max(1, d)
        if acc >= tot * 0.45:
            return i
    return n // 2
