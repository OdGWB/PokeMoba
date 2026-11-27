"""MatchSpec per il motore di allenamento in Rust (docs/RUST_ENGINE.md).

Il Python fa TUTTA la preparazione della partita (tier_sim.play fino al primo
tick: squadre, spawn, rami, parametri dei bot) e il Rust riparte da li': la spec
e' la fotografia dello stato appena prima del primo `Match.update`, piu' lo stato
dell'RNG globale in quell'istante. Cosi' il Rust non deve rifare la preparazione.

snapshot(match) e' anche il formato che tools/rust_parity.py confronta tick per
tick: stesso schema per il Python e per il Rust.

    capture(job) -> Captured(match, ctx)   # partita pronta, nessun tick giocato
    build_spec(job) -> dict                # per pokemoba_native.run_match
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
_TOOLS = os.path.join(ROOT, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import config  # noqa: E402

SPEC_VERSION = 1

# Variabili locali di tier_sim.play che servono per il risultato della partita.
_CTX_KEYS = ("seed", "max_time", "stat", "units", "plans", "u_teams", "team_info", "core_ev")


class _Stop(Exception):
    pass


class Captured:
    def __init__(self, match, ctx):
        self.match = match
        self.ctx = ctx


def capture(job) -> Captured:
    """Esegue la preparazione di tier_sim.play(job) e si ferma al primo tick.
    Richiede tier_sim._init_worker gia' chiamato (come per play)."""
    import tier_sim
    import engine.match as em
    orig = em.Match.update
    got = {}

    def update(self, dt, tick):
        f = sys._getframe(1)                 # il frame di tier_sim.play
        got["match"] = self
        got["ctx"] = {k: f.f_locals.get(k) for k in _CTX_KEYS}
        got["rng"] = random.getstate()
        raise _Stop

    em.Match.update = update
    try:
        tier_sim.play(job)
    except _Stop:
        pass
    finally:
        em.Match.update = orig
    if "match" not in got:
        raise RuntimeError("tier_sim.play e' finita senza giocare un tick")
    random.setstate(got["rng"])
    return Captured(got["match"], got["ctx"])


# --- forma canonica dello stato ----------------------------------------------
# float -> hex (esatto), Vec2 -> ("V", x, y), entita' dentro altri campi -> ("E", id)
# (niente cicli), liste/tuple in ordine, dict in ordine di inserimento (conta: il
# Python li scorre cosi'), set ordinati. Oggetti nativi, funzioni e cache grosse
# restano fuori: non sono stato di gioco.

_SKIP_MATCH = {"world", "map", "vision", "_minion_ai", "_combat_hash", "items", "type_chart",
               "_native_bot", "_hooks", "_by_type", "spatial", "grid"}


# Oggetti del motore che altri oggetti tengono come riferimento (es. JungleSystem.m
# e' il Match): non si ricopiano, si segna solo il riferimento.
_REF_TYPES = {"Match", "World", "Grid", "MapData", "VisionSystem", "FastVision", "SpatialHash",
              "ItemCatalog", "TypeChart", "BotParams"}


def _is_cache(k: str) -> bool:
    """Cache e memo (rifatti dal motore, non stato di gioco): diverse fra Python
    puro ed estensione, non vanno confrontate."""
    return "cache" in k.lower() or k.endswith("_c") or k.startswith("_nscan")


def _is_entity(v) -> bool:
    return hasattr(v, "id") and hasattr(v, "pos") and dataclasses.is_dataclass(v)


def canon(v, depth=0):
    t = type(v)
    if t is float:
        return v.hex()
    if v is None or t in (int, bool, str):
        return v
    if t.__name__ == "Vec2":
        return ("V", v.x.hex(), v.y.hex())
    if depth > 6:
        return ("...", t.__name__)
    if t in (list, tuple):
        return [canon(x, depth + 1) for x in v]
    if t is dict:
        return [[canon(k, depth + 1), canon(x, depth + 1)] for k, x in v.items()]
    if t in (set, frozenset):
        return sorted((canon(x, depth + 1) for x in v), key=repr)
    if depth and _is_entity(v):
        return ("E", v.id)
    if depth > 1 and t.__name__ in _REF_TYPES:
        return ("ref", t.__name__)
    if t.__module__.startswith("numpy"):
        b = getattr(v, "tobytes", None)
        return ("np", hashlib.md5(b()).hexdigest() if b else repr(v))
    if callable(v) or t.__module__ in ("builtins", "pokemoba_native"):
        return None
    if dataclasses.is_dataclass(v):
        return [[f.name, canon(getattr(v, f.name), depth + 1)] for f in dataclasses.fields(v)]
    d = getattr(v, "__dict__", None)
    if d is not None:
        return [[k, canon(x, depth + 1)] for k, x in d.items()
                if not k.startswith("__") and not _is_cache(k)]
    return ("?", t.__name__)


def entity_row(e) -> dict:
    row = {"_type": type(e).__name__}
    for f in dataclasses.fields(e):
        row[f.name] = canon(getattr(e, f.name), 1)
    for k, x in e.__dict__.items():            # campi aggiunti a runtime (es. color, lane_idx)
        if k not in row and not k.startswith("__"):
            row[k] = canon(x, 1)
    return row


def match_row(match) -> dict:
    out = {}
    for k, x in match.__dict__.items():
        if k in _SKIP_MATCH or _is_cache(k) or callable(x) and not isinstance(x, (list, dict)):
            continue
        c = canon(x, 1)
        if c is not None:
            out[k] = c
    return out


def rng_digest(state=None) -> str:
    st = state if state is not None else random.getstate()
    return hashlib.md5(repr(st[1]).encode()).hexdigest()


def snapshot(match) -> dict:
    """Stato completo e confrontabile: entita' (ordine del World), Match, RNG."""
    return {"time": match.time.hex(),
            "rng": rng_digest(),
            "match": match_row(match),
            "entities": [[eid, entity_row(e)] for eid, e in match.world.entities.items()]}


# --- spec ----------------------------------------------------------------------

def _data_texts() -> dict:
    out = {}
    for name in ("items.json", "types.json"):
        with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
            out[name] = f.read()
    for rel in config.ROSTER:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            out[rel.replace("\\", "/")] = f.read()
    return out


def _config_values() -> dict:
    out = {}
    for k in dir(config):
        if k.isupper():
            v = getattr(config, k)
            try:
                json.dumps(v)
            except TypeError:
                continue
            out[k] = v
    return out


def build_spec(job, cap: Captured | None = None) -> dict:
    cap = cap or capture(job)
    m, g = cap.match, cap.match.world.grid
    fine = getattr(g, "_shape_np", None)
    if fine is None:
        shape = bytes(g.width * g.height * 64)
    else:
        shape = fine.astype("uint8").tobytes()
    teams = [[], []]
    for p in cap.ctx["units"]:
        teams[p.team].append({"id": p.id, "name": p.name, "dex": p.dex,
                              "lane": cap.ctx["stat"][p.id]["lane"],
                              "plan": cap.ctx["plans"].get(p.id),
                              "is_jungler": bool(getattr(p, "is_jungler", False)),
                              "support": bool(getattr(p, "bot_support", False))})
    import tier_sim
    return {"version": SPEC_VERSION,
            "job": list(job),
            "rng_state": random.getstate(),
            "horizon": float(cap.ctx["max_time"]),
            "dt": float(config.TICK_DT),
            "strides": [m.vision.stride, m.minion_ai_stride],
            "opts": {k: v for k, v in tier_sim.OPTS.items() if k != "params"},
            "map": {"width": g.width, "height": g.height,
                    "tiles": bytes(t for row in g.tiles for t in row), "shape": shape},
            "teams": teams,
            "config": _config_values(),
            "data": _data_texts(),
            "initial": snapshot(m)}
