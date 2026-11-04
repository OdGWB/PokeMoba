"""Regolazioni VISIVE delle animazioni dei Pokémon (scritte dall'editor delle
animazioni, game/scenes/anim_editor_scene.py).

Nessuna logica di gioco: velocità di movimento, cicli d'attacco e tempi delle
mosse restano quelli del motore. Qui si cambia solo COME si vede lo sprite:
quale animazione usare, quanto in fretta scorre, quali fotogrammi tagliare, in
che fotogramma e da che punto dello sprite parte il proiettile visivo.

File: data/anim_overrides.json
    { "<cartella sprite>": { "<azione>": { ... }, ... }, ... }
cartella = nome della cartella sotto assets/ (es. "0856", "0_melee").
azione   = "idle" (fermo), "walk" (camminata), "aa" (attacco base) oppure
           "move:<id mossa>" (es. "move:confusion").
voce     = anim    nome dell'animazione PMD (es. "Shoot"); assente = quella di default
           speed   moltiplicatore della velocità dell'animazione (1 = normale)
           start   primo fotogramma tenuto (taglio iniziale, default 0)
           end     ultimo fotogramma tenuto, compreso (taglio finale, default l'ultimo)
           release fotogramma in cui parte il proiettile (solo "aa" e mosse)
           origin  [avanti, su] in pixel dello sprite: punto da cui parte il
                   proiettile, misurato con lo sprite rivolto a DESTRA dal punto
                   a terra; ruota con la direzione in cui guarda il Pokémon.

Effetti in gioco del fotogramma del proiettile:
  - attacco base: quando il motore rilascia il colpo, l'animazione salta al
    fotogramma del proiettile se non c'è ancora arrivata (sempre sincronizzati);
  - mosse: il proiettile/effetto VISIVO aspetta che l'animazione arrivi a quel
    fotogramma (al massimo MAX_DELAY s). Il danno resta quello del motore.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from engine.vec import DIR_VECTORS

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "anim_overrides.json"

# Un'unità di durata PMD vale 1/30 di secondo (come in sprites/animator.py).
DURATION_UNIT = 1.0 / 30.0
# Ritardo visivo massimo del proiettile di una mossa (il colpo nel motore e' gia'
# avvenuto: oltre si vedrebbe troppo staccato dal danno).
MAX_DELAY = 0.6
SPEED_MIN, SPEED_MAX = 0.1, 5.0

_data: dict | None = None
version = 0   # cresce a ogni modifica: gli animatori rileggono la loro tabella


def data() -> dict:
    """Tutte le regolazioni ({cartella: {azione: voce}}), lette una volta."""
    global _data
    if _data is None:
        try:
            with open(PATH, encoding="utf-8") as f:
                raw = json.load(f)
            _data = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            _data = {}
    return _data


def table(key) -> dict:
    """Regolazioni di una cartella sprite ({azione: voce}), vuote se nessuna."""
    if not key:
        return {}
    return data().get(key, {})


def get(key, action):
    if not key or not action:
        return None
    return data().get(key, {}).get(action)


def save(new_data: dict) -> None:
    """Scrive il file (solo le voci non vuote) e avvisa gli animatori."""
    global _data, version
    clean = {}
    for key in sorted(new_data):
        acts = {a: v for a, v in sorted(new_data[key].items()) if v}
        if acts:
            clean[key] = acts
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=1)
        f.write("\n")
    _data = clean
    version += 1


def frame_range(entry, n: int) -> tuple[int, int]:
    """Fotogrammi tenuti (primo, ultimo compreso) dopo il taglio."""
    if n <= 0:
        return 0, 0
    if not entry:
        return 0, n - 1
    lo = max(0, min(n - 1, int(entry.get("start") or 0)))
    end = entry.get("end")
    hi = n - 1 if end is None else max(lo, min(n - 1, int(end)))
    return lo, hi


def speed_of(entry) -> float:
    if not entry:
        return 1.0
    return max(SPEED_MIN, min(SPEED_MAX, float(entry.get("speed", 1.0) or 1.0)))


def release_frame(entry, n: int):
    """Fotogramma del proiettile dentro il taglio, o None."""
    if not entry or entry.get("release") is None or n <= 0:
        return None
    lo, hi = frame_range(entry, n)
    return max(lo, min(hi, int(entry["release"])))


def release_delay(durations, entry, speed: float = 1.0) -> float:
    """Secondi dall'inizio (taglio compreso) al fotogramma del proiettile."""
    r = release_frame(entry, len(durations))
    if r is None:
        return 0.0
    lo, _ = frame_range(entry, len(durations))
    ticks = sum(max(1, d) for d in durations[lo:r])
    return ticks * DURATION_UNIT / max(0.05, speed * speed_of(entry))


def origin_offset(entry, facing: int, scale: float = 1.0, tile: int = 32):
    """Spostamento in tile del punto di partenza del proiettile, ruotato con la
    direzione in cui guarda il Pokémon (l'editor lo misura rivolto a destra)."""
    if not entry or not entry.get("origin"):
        return 0.0, 0.0
    fwd, up = entry["origin"]
    dv = DIR_VECTORS[facing % 8]
    ln = math.hypot(dv.x, dv.y) or 1.0
    k = scale / tile
    return dv.x / ln * fwd * k, dv.y / ln * fwd * k - up * k


def action_of(e) -> str | None:
    """Azione che ha generato un evento FX (attacco base o mossa), se nota."""
    if e.get("aa") or e.get("kind") == "attack":
        return "aa"
    mv = e.get("move")
    return f"move:{mv}" if mv else None


def trigger_anim(animator, e) -> None:
    """Avvia l'animazione una-tantum di un evento {"eid", "anim", ...},
    passando l'azione (attacco base / mossa) per le regolazioni dell'editor."""
    play = getattr(animator, "play_once", None)
    if play is None or not hasattr(animator, "anim_set"):
        return
    animator.play_once(e.get("anim") or "", float(e.get("anim_speed", 1.0)),
                       action=action_of(e) if (e.get("aa") or e.get("move")) else None)


class FxTuner:
    """Applica le regolazioni agli eventi FX dei proiettili prima di disegnarli:
    punto di partenza sullo sprite e attesa del fotogramma del proiettile."""

    def __init__(self, tile: int = 32):
        self.tile = tile
        self.pending: list[list] = []   # [secondi rimasti, evento]

    def process(self, events, animators, pos_of) -> list:
        """Eventi da disegnare SUBITO; quelli da ritardare restano in coda.
        `pos_of(id)` -> (x, y) dell'unità o None."""
        out = []
        for e in events:
            src = e.get("src")
            an = animators.get(src) if src is not None else None
            aset = getattr(an, "anim_set", None)
            action = action_of(e) if aset is not None else None
            entry = get(aset.key, action) if action else None
            if not entry:
                out.append(e)
                continue
            if action == "aa":
                an.snap_release()   # il colpo parte: l'animazione e' al fotogramma giusto
            e = dict(e)
            a, p = e.get("a"), pos_of(src)
            if a is not None and p is not None and entry.get("origin"):
                if (a[0] - p[0]) ** 2 + (a[1] - p[1]) ** 2 < 0.36:
                    dx, dy = origin_offset(entry, an.facing, getattr(an, "scale", 1.0),
                                           self.tile)
                    e["a"] = (a[0] + dx, a[1] + dy)
            delay = 0.0
            if action != "aa":
                anim = aset.get(entry.get("anim") or "") or aset.get(an.state)
                if anim is not None:
                    delay = min(MAX_DELAY, release_delay(anim.durations, entry))
            if delay > 0.01:
                self.pending.append([delay, e])
            else:
                out.append(e)
        return out

    def due(self, dt: float) -> list:
        """Eventi ritardati arrivati al loro fotogramma."""
        if not self.pending:
            return []
        ready, keep = [], []
        for item in self.pending:
            item[0] -= dt
            (ready if item[0] <= 0 else keep).append(item)
        self.pending = keep
        return [e for _, e in ready]
