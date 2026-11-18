"""Mappa pre-renderizzata che segue il METEO (pozze, cespugli secchi, varchi del
Vento, tana di Arceus aperta).

La mappa e' disegnata una volta in layer (MapRenderer, ~10-20 s di build): rifarla
a ogni cambio di meteo bloccherebbe la partita. Ma il terreno puo' assumere solo
POCHI stati, noti dall'inizio: (tana chiusa | aperta) x (sereno, sole, pioggia,
vento). Quindi:

1. Un PROCESSO a parte (bassa priorita', senza finestra) costruisce ogni variante
   con lo stesso codice di disegno e salva solo i BLOCCHI di 64 px che cambiano
   rispetto alla mappa di base: patch_<chiave>.bin nella cartella della cache
   (pioggia ~0,7k blocchi, sole ~4k: pochi MB). Le patch restano su disco: dalla
   seconda partita sulla stessa mappa sono gia' pronte.
2. In partita MapRenderer controlla solo grid._ver (un confronto a frame); quando
   cambia riconosce la variante, legge la patch in un thread e la applica a pezzi
   (budget di pochi ms per frame): rimette i blocchi originali e copia i nuovi.

Le parti GLOBALI del disegno (sentieri, anello delle lane, etichette dei muri)
si calcolano dalla mappa di base anche nelle varianti (MapRenderer.build ref=),
quindi una variante differisce dalla base solo vicino ai tile cambiati.

Avvio del processo: `python -m game.terrain_variants <job.json>`; nell'exe
(PyInstaller) `PokeMoba.exe --terrain-worker <job.json>` (run_client.main). Il
processo si chiude da solo se il gioco termina (controllo del pid del padre).
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import struct
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

import numpy as np

from engine.grid import TILE_FLOOR, TILE_PILLAR
from engine.jungle import apply_weather

FORMAT = 1
BLOCK = 64            # lato dei blocchi confrontati/salvati (divide CHUNK=1024)
KEEP = 40             # patch tenute al massimo su disco
WEATHERS = ("clear", "sun", "rain", "wind")
_ROOT = Path(__file__).resolve().parent.parent


# --- varianti del terreno ----------------------------------------------------------
class _Scratch:
    """Griglia minima per apply_weather (width/height/tiles/in_bounds)."""

    def __init__(self, w, h):
        self.width, self.height, self.tiles = w, h, []

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height


def variant_list(base, seal, md, weathers=WEATHERS) -> list[tuple[str, list]]:
    """[(nome, tile)] di tutti gli stati raggiungibili, nell'ordine in cui servono
    (prima i meteo a tana chiusa, poi quelli a tana aperta). Il primo e' la base."""
    h, w = len(base), len(base[0])
    opened = [row[:] for row in base]
    for (x, y) in seal or ():
        opened[y][x] = TILE_FLOOR
    out = []
    for is_open, src in ((False, base), (True, opened)):
        if is_open and not seal:
            break
        for wth in weathers:
            g = _Scratch(w, h)
            apply_weather(g, src, wth, puddles=getattr(md, "puddles", None),
                          puddle_spots=getattr(md, "puddle_spots", None),
                          wind_passages=getattr(md, "wind_passages", None))
            out.append((("open_" if is_open else "") + wth, g.tiles))
    return out


def tiles_hash(tiles) -> str:
    return hashlib.sha1(np.asarray(tiles, dtype=np.int16).tobytes()).hexdigest()[:16]


def patch_path(base_key: str, vh: str) -> Path:
    from game import map_cache
    return map_cache.cache_dir() / f"patch_{base_key[:16]}_{vh}.bin"


# --- lettura delle patch (processo di gioco) ----------------------------------------
def read_patch(path: Path, key: str):
    """[(layer, x, y, w, h, bytes)] o None (file mancante, di un'altra chiave o
    rotto). Solo I/O e zlib: si puo' chiamare da un thread."""
    try:
        buf = memoryview(path.read_bytes())
        (n,) = struct.unpack_from("<I", buf, 0)
        head = json.loads(bytes(buf[4:4 + n]))
        if head.get("key") != key or head.get("format") != FORMAT:
            return None
        pos = 4 + n
        out = []
        for li, x, y, w, h, length in head["blocks"]:
            out.append((head["layers"][li], x, y, w, h,
                        zlib.decompress(buf[pos:pos + length])))
            pos += length
        return out
    except Exception:
        return None


# --- applicazione in partita -------------------------------------------------------
_running: dict = {}      # chiave della base -> processo delle patch in corso


class TerrainPatcher:
    """Tiene i layer di MapRenderer allineati al terreno della griglia.

    sync(grid) a ogni frame: se grid._ver non cambia costa un confronto; se cambia
    si riconosce la variante (i PILASTRI, temporanei, valgono come jolly) e si
    porta la mappa li': prima si rimettono i blocchi originali non piu' toccati,
    poi si copiano quelli della patch, al massimo BUDGET_MS per frame. I blocchi
    originali si salvano compressi al primo tocco (pochi MB, niente copie piene)."""

    BUDGET_MS = 3.0

    def __init__(self, mr, base, seal, md):
        self.mr = mr
        self.base = [list(row) for row in base]
        self.W, self.H = len(base[0]), len(base)
        self.base_vh = tiles_hash(self.base)
        self.variants = []                    # [(nome, hash, array int16, tile)]
        seen = {self.base_vh}
        for name, t in variant_list(self.base, seal, md):
            vh = tiles_hash(t)
            if vh not in seen:
                seen.add(vh)
                self.variants.append((name, vh, np.asarray(t, np.int16), t))
        self._base_arr = np.asarray(self.base, np.int16)
        self.base_key = None
        self.ver = None
        self.target = self.applied = self.base_vh
        self.orig: dict = {}                  # (layer, x, y) -> zlib dei pixel di base
        self.cur: set = set()                 # blocchi ora diversi dalla base
        self.ops = None
        self.ops_for = None
        self.loading = None
        self.retry_at = 0.0

    def fits(self, grid) -> bool:
        return grid.width == self.W and grid.height == self.H

    def ref_grid(self):
        from game.map_renderer import _RefGrid
        return _RefGrid(self.W, self.H, self.base)

    def attach(self, src, fresh=True) -> None:
        """fresh: layer appena costruiti/caricati dalla base, si riparte da li'."""
        from game import map_cache
        if fresh or self.base_key is None:
            self.base_key = map_cache.key_for(self.mr, src)[1]
        if fresh:
            self.orig.clear()
            self.cur.clear()
            self.ops = self.loading = None
            self.applied = self.base_vh
        self.ver = None
        self._ensure_worker()

    def adopt(self, old) -> None:
        """Stessa base di un patcher precedente: eredita lo stato dei layer."""
        self.base_key, self.orig, self.cur = old.base_key, old.orig, old.cur
        self.applied = self.target = old.applied
        self.ops = self.loading = None

    def _path(self, vh):
        return patch_path(self.base_key, vh)

    def _ensure_worker(self) -> None:
        if not self.variants or self.base_key is None:
            return
        missing = [v for v in self.variants if not self._path(v[1]).is_file()]
        if not missing:
            return
        p = _running.get(self.base_key)
        if p is not None and p.poll() is None:
            return
        job = {"parent": os.getpid(), "tile_size": self.mr.tile_size,
               "camps": [list(c) for c in self.mr._camps], "base": self.base,
               "variants": [{"path": str(self._path(vh)), "key": self.base_key + vh,
                             "tiles": t} for (_n, vh, _a, t) in missing]}
        _running[self.base_key] = start_worker(job)

    def _match(self, grid):
        try:
            arr = np.asarray(grid.tiles, np.int16)
        except Exception:
            return None
        if arr.shape != self._base_arr.shape:
            return None
        wild = arr == TILE_PILLAR
        cands = [(self.base_vh, self._base_arr)] + [(vh, a) for (_n, vh, a, _t) in self.variants]
        cands.sort(key=lambda c: c[0] != self.target)       # prima quella attuale
        for vh, a in cands:
            if ((arr == a) | wild).all():
                return vh
        return None

    def sync(self, grid) -> None:
        ver = getattr(grid, "_ver", None)
        if ver is not None and ver != self.ver:
            self.ver = ver
            vh = self._match(grid)
            if vh is not None and vh != self.target:
                self.target = vh
                self.ops = self.loading = None
                self.retry_at = 0.0
        if self.target != self.applied or self.ops is not None:
            self._step()

    def _step(self) -> None:
        if self.ops is None:
            if self.target == self.base_vh:
                blocks = []
            else:
                if self.loading is None:
                    if time.perf_counter() < self.retry_at:
                        return
                    holder = {"path": self._path(self.target), "key": self.base_key + self.target}

                    def run(h=holder):
                        h["res"] = read_patch(h["path"], h["key"])
                        h["done"] = True
                    self.loading = holder
                    threading.Thread(target=run, daemon=True).start()
                    return
                if not self.loading.get("done"):
                    return
                blocks = self.loading["res"]
                self.loading = None
                if blocks is None:                # patch non ancora pronta
                    self.retry_at = time.perf_counter() + 1.0
                    self._ensure_worker()
                    return
            keys = {(b[0], b[1], b[2]) for b in blocks}
            ops = [("r", k) for k in self.cur if k not in keys]
            ops += [("p", b) for b in blocks]
            self.ops = ops[::-1]                  # pop() dalla fine
            self.ops_for = self.target
        ops = self.ops
        t_end = time.perf_counter() + self.BUDGET_MS / 1000.0
        while ops and time.perf_counter() < t_end:
            kind, d = ops.pop()
            if kind == "r":
                lay, x, y = d
                L = self.mr.layers[lay]
                w, h = min(BLOCK, L.map_w - x), min(BLOCK, L.map_h - y)
                self._put(lay, x, y, w, h, zlib.decompress(self.orig[d]), save=False)
                self.cur.discard(d)
            else:
                self._put(*d, save=True)
                self.cur.add((d[0], d[1], d[2]))
        if not ops:
            self.ops = None
            self.applied = self.ops_for

    def _put(self, lay, x, y, w, h, raw, save) -> None:
        import pygame
        from game.map_renderer import CHUNK
        L = self.mr.layers[lay]
        cx, cy = x // CHUNK, y // CHUNK
        s = L._chunk_surf(cx, cy)
        if s is None:
            return
        lx, ly = x - cx * CHUNK, y - cy * CHUNK
        fmt = "RGB" if L.opaque else "RGBA"
        k = (lay, x, y)
        if save and k not in self.orig:
            self.orig[k] = zlib.compress(
                pygame.image.tobytes(s.subsurface((lx, ly, w, h)), fmt), 1)
        src = pygame.image.frombytes(raw, (w, h), fmt)
        if L.opaque:
            s.blit(src, (lx, ly))
        else:                                     # copia ESATTA, alfa compresa
            s.fill((0, 0, 0, 0), (lx, ly, w, h))
            s.blit(src, (lx, ly), special_flags=pygame.BLEND_RGBA_ADD)


# --- processo che prepara le patch ------------------------------------------------
_procs: list = []


def _kill_all():
    for p in _procs:
        try:
            if p.poll() is None:
                p.terminate()
        except Exception:
            pass


atexit.register(_kill_all)


def start_worker(job: dict):
    """Lancia il processo delle patch (bassa priorita', senza finestra)."""
    from game import map_cache
    try:
        folder = map_cache.cache_dir()
        folder.mkdir(parents=True, exist_ok=True)
        jf = folder / f"job_{os.getpid()}_{int(time.time() * 1000)}.json"
        jf.write_text(json.dumps(job))
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--terrain-worker", str(jf)]
        else:
            cmd = [sys.executable, "-m", "game.terrain_variants", str(jf)]
        kw = {"env": dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000 | 0x00004000   # NO_WINDOW | BELOW_NORMAL
        p = subprocess.Popen(cmd, cwd=str(_ROOT), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        _procs.append(p)
        return p
    except Exception:
        return None


def stop_worker(p) -> None:
    try:
        if p is not None and p.poll() is None:
            p.terminate()
    except Exception:
        pass


def _parent_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259         # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _layer_arrays(mr):
    """{nome: (array HxWxC, opaco)} dei layer a piena mappa (chunk mancanti = 0)."""
    import pygame
    from game.map_renderer import CHUNK
    out = {}
    for name in mr.LAYER_NAMES:
        L = mr.layers[name]
        c = 3 if L.opaque else 4
        a = np.zeros((L.map_h, L.map_w, c), np.uint8)
        for (cx, cy), s in L.chunks.items():
            w, h = s.get_size()
            raw = pygame.image.tobytes(s, "RGB" if L.opaque else "RGBA")
            a[cy * CHUNK:cy * CHUNK + h, cx * CHUNK:cx * CHUNK + w] = \
                np.frombuffer(raw, np.uint8).reshape(h, w, c)
        out[name] = (a, L.opaque)
    return out


def _diff_blocks(base, var):
    """Blocchi BLOCKxBLOCK diversi: [(layer, x, y, w, h, bytes della variante)]."""
    out = []
    for name, (a, opq) in var.items():
        b = base[name][0]
        H, W = a.shape[:2]
        d = (a != b).any(axis=2)
        nby, nbx = -(-H // BLOCK), -(-W // BLOCK)
        pad = np.zeros((nby * BLOCK, nbx * BLOCK), bool)
        pad[:H, :W] = d
        hit = pad.reshape(nby, BLOCK, nbx, BLOCK).any(axis=(1, 3))
        for by, bx in zip(*np.nonzero(hit)):
            x, y = int(bx) * BLOCK, int(by) * BLOCK
            w, h = min(BLOCK, W - x), min(BLOCK, H - y)
            out.append((name, x, y, w, h, np.ascontiguousarray(a[y:y + h, x:x + w]).tobytes()))
    return out


def _write_patch(path: Path, key: str, layers, blocks) -> None:
    blobs, rows = [], []
    for name, x, y, w, h, raw in blocks:
        z = zlib.compress(raw, 6)
        blobs.append(z)
        rows.append([layers.index(name), x, y, w, h, len(z)])
    hb = json.dumps({"format": FORMAT, "key": key, "layers": list(layers),
                     "blocks": rows}).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    with open(tmp, "wb") as f:
        f.write(struct.pack("<I", len(hb)))
        f.write(hb)
        for z in blobs:
            f.write(z)
    os.replace(tmp, path)


def _prune(folder: Path) -> None:
    files = sorted(folder.glob("patch_*.bin"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[KEEP:]:
        try:
            f.unlink()
        except OSError:
            pass


def worker_main(job_path: str) -> int:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    jp = Path(job_path)
    try:
        job = json.loads(jp.read_text())
    finally:
        try:
            jp.unlink()
        except OSError:
            pass
    import pygame
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    from game import map_cache
    from game.map_renderer import _RefGrid
    from game.renderer import Renderer

    parent = int(job["parent"])
    base = job["base"]
    W, H = len(base[0]), len(base)
    r = Renderer(job["tile_size"])
    mr = r.map
    mr.set_camps(job["camps"])
    bgrid = _RefGrid(W, H, base)
    from game.map_renderer import _Layer
    # La base la scrive gia' il gioco (map_cache, in un thread): si aspetta un
    # attimo che arrivi, altrimenti si costruisce qui.
    for _ in range(40):
        if map_cache.load(mr, bgrid, _Layer):
            break
        if not _parent_alive(parent):
            return 0
        time.sleep(0.5)
    else:
        mr.build(bgrid)
    base_arr = _layer_arrays(mr)
    for v in job["variants"]:
        if not _parent_alive(parent):
            return 0
        path = Path(v["path"])
        if path.is_file():
            continue
        mr.build(_RefGrid(W, H, v["tiles"]), ref=base)
        blocks = _diff_blocks(base_arr, _layer_arrays(mr))
        _write_patch(path, v["key"], mr.LAYER_NAMES, blocks)
    _prune(map_cache.cache_dir())
    return 0


if __name__ == "__main__":
    sys.exit(worker_main(sys.argv[1]))
