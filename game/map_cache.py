"""Cache su disco della mappa pre-renderizzata (MapRenderer).

Costruire i layer della mappa 5v5 richiede ~17-19 s (rumore, silhouette, alberi,
fiume...). Il risultato dipende SOLO da: tile della griglia, campi, dimensione del
tile e codice di disegno (tutta la casualita' del build e' a seme fisso). Quindi
dopo il primo build i layer si salvano in
%APPDATA%/PokeMoba/cache/map_<LxA>_<hash griglia>.bin e alle partite seguenti si
ricaricano in ~1 s.

La CHIAVE contiene anche l'hash dei sorgenti che disegnano la mappa
(map_renderer.py, renderer.py, fx.py, config.py) e le versioni di pygame e numpy:
qualunque modifica alla grafica invalida la cache da sola, senza versioni da
aggiornare a mano. Un file illeggibile, di un'altra chiave o corrotto viene
ignorato (si ricostruisce e lo si riscrive). La scrittura avviene in un thread
(compressione + file temporaneo + os.replace), quindi non allunga il caricamento
e un'uscita a meta' non lascia mai un file rotto. Formato: 4 byte con la
lunghezza dell'intestazione JSON, l'intestazione, poi i blocchi compressi in fila
(niente pickle: leggere il file non esegue codice).

POKEMOBA_NO_MAP_CACHE=1 nell'ambiente disattiva la cache (build sempre da zero).
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import threading
import zlib
from pathlib import Path

import numpy as np
import pygame

import config

FORMAT = 1
KEEP = 4            # file tenuti al massimo (i piu' vecchi si cancellano)
_ROOT = Path(__file__).resolve().parent.parent
_SOURCES = ("game/map_renderer.py", "game/renderer.py", "game/fx.py", "config.py")
_src_hash = None


def enabled() -> bool:
    return not os.environ.get("POKEMOBA_NO_MAP_CACHE")


def cache_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "PokeMoba" / "cache"


def _sources_hash() -> bytes:
    global _src_hash
    if _src_hash is None:
        h = hashlib.sha1()
        for rel in _SOURCES:
            try:
                h.update((_ROOT / rel).read_bytes())
            except OSError:
                h.update(b"?" + rel.encode())
        _src_hash = h.digest()
    return _src_hash


def _grid_hash(grid) -> str:
    arr = np.array(grid.tiles, dtype=np.int16)
    return hashlib.sha1(arr.tobytes()).hexdigest()[:16]


def key_for(mr, grid) -> tuple[Path, str]:
    """(file della cache, chiave completa) per il MapRenderer `mr` e la griglia."""
    gh = _grid_hash(grid)
    h = hashlib.sha1()
    h.update(repr((FORMAT, mr.tile_size, grid.width, grid.height, gh, mr._camps,
                   config.SHOW_GRID_LINES, pygame.version.ver,
                   np.__version__)).encode())
    h.update(_sources_hash())
    path = cache_dir() / f"map_{grid.width}x{grid.height}_{gh}.bin"
    return path, h.hexdigest()


# --- lettura ---------------------------------------------------------------------
def _surf(raw: bytes, size, opaque: bool):
    if opaque:
        return pygame.image.frombytes(raw, size, "RGB").convert()
    return pygame.image.frombytes(raw, size, "RGBA").convert_alpha()


def load(mr, grid, layer_cls) -> bool:
    """Riempie `mr` dalla cache. True se ci e' riuscito, False = da costruire."""
    if not enabled():
        return False
    try:
        path, key = key_for(mr, grid)
        if not path.is_file():
            return False
        buf = memoryview(path.read_bytes())
        (n,) = struct.unpack_from("<I", buf, 0)
        head = json.loads(bytes(buf[4:4 + n]))
        if head.get("key") != key:
            return False
        pos = 4 + n

        def blob(length):
            nonlocal pos
            raw = zlib.decompress(buf[pos:pos + length])
            pos += length
            return raw

        layers = {}
        for L in head["layers"]:
            bg = tuple(L["bg"]) if L["bg"] is not None else None
            lyr = layer_cls(L["map_w"], L["map_h"], opaque=L["opaque"], bg=bg)
            for cx, cy, w, h, length in L["chunks"]:
                lyr.chunks[(cx, cy)] = _surf(blob(length), (w, h), L["opaque"])
            layers[L["name"]] = lyr
        foam = [(ax, ay, [_surf(blob(length), (w, h), False) for w, h, length in frames])
                for ax, ay, frames in head["foam"]]
    except Exception:
        return False
    mr.layers = layers
    mr._foam = foam
    mr._H, mr._top = head["H"], head["top"]
    mr._grid = grid
    return True


# --- scrittura -------------------------------------------------------------------
def save(mr, grid, layer_order) -> None:
    """Salva i layer di `mr`. I pixel si copiano qui (veloce); compressione e
    scrittura del file vanno in un thread."""
    if not enabled():
        return
    try:
        path, key = key_for(mr, grid)
        layers = []
        for name in layer_order:
            lyr = mr.layers[name]
            fmt = "RGB" if lyr.opaque else "RGBA"
            layers.append((name, lyr.map_w, lyr.map_h, lyr.opaque, lyr.bg,
                           [(ck, s.get_size(), pygame.image.tobytes(s, fmt))
                            for ck, s in lyr.chunks.items()]))
        foam = [(ax, ay, [(s.get_size(), pygame.image.tobytes(s, "RGBA")) for s in frames])
                for ax, ay, frames in mr._foam]
    except Exception:
        return
    head = {"key": key, "H": mr._H, "top": mr._top}
    threading.Thread(target=_write, args=(path, head, layers, foam),
                     name="map-cache", daemon=False).start()


def _write(path: Path, head, layers, foam) -> None:
    tmp = None
    try:
        blobs = []

        def z(raw):   # livello 1: veloce, e i layer con alfa sono quasi vuoti
            b = zlib.compress(raw, 1)
            blobs.append(b)
            return len(b)

        head["layers"] = [
            {"name": name, "map_w": mw, "map_h": mh, "opaque": op,
             "bg": list(bg) if bg is not None else None,
             "chunks": [[ck[0], ck[1], size[0], size[1], z(raw)] for ck, size, raw in chunks]}
            for name, mw, mh, op, bg, chunks in layers]
        head["foam"] = [[ax, ay, [[size[0], size[1], z(raw)] for size, raw in frames]]
                        for ax, ay, frames in foam]
        hb = json.dumps(head).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        with open(tmp, "wb") as f:
            f.write(struct.pack("<I", len(hb)))
            f.write(hb)
            for b in blobs:
                f.write(b)
        os.replace(tmp, path)
        _prune(path.parent)
    except Exception:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass


def _prune(folder: Path) -> None:
    """Tiene solo i KEEP file piu' recenti (mappe modificate = file nuovi)."""
    files = sorted(folder.glob("map_*.bin"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[KEEP:]:
        try:
            f.unlink()
        except OSError:
            pass
