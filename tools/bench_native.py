"""Confronto Python puro vs estensione Rust (pokemoba_native) su partite 5v5 headless.

Ogni misura gira in un PROCESSO NUOVO (RAM e import puliti). Il figlio stampa una
riga JSON: tempo reale, CPU (user+kernel), picco RAM (working set), esito, hash.

    python tools/bench_native.py single --seeds 3 [--fast] [--minutes 14]
    python tools/bench_native.py scale  --workers 1,4,8,16 --seeds 16 [--fast]

  single: stesse partite in Python e in Rust, una alla volta (+ verifica stesso esito)
  scale : throughput con N processi in parallelo (partite/ora), solo Rust (o --py)
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _peak_ram_mb():
    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    pmc = PMC()
    pmc.cb = ctypes.sizeof(pmc)
    k32, ps = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    ps.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    ps.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return pmc.PeakWorkingSetSize / 2**20, pmc.PeakPagefileUsage / 2**20


def child(seed_index, minutes, fast):
    os.environ.setdefault("PYTHONHASHSEED", "0")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
    t_imp = time.perf_counter()
    import tier_sim
    from engine.grid import _native
    t_imp = time.perf_counter() - t_imp
    if fast:
        tier_sim._init_worker(False, minutes * 60.0, True, None, {"threshold": 2.0}, 3, 2)
    else:
        tier_sim._init_worker(False, minutes * 60.0, True, None, None, 1, 1)
    tier_sim.OPTS["params"] = {0: {"*": {"utility": True}}, 1: {"*": {"utility": True}}}
    job = tier_sim.make_jobs(seed_index + 1, 900)[seed_index]
    c0, w0 = time.process_time(), time.perf_counter()
    r = tier_sim.play(job)
    wall, cpu = time.perf_counter() - w0, time.process_time() - c0
    ws, pf = _peak_ram_mb()
    print("RESULT " + json.dumps({
        "native": _native is not None, "seed": job[0], "wall": wall, "cpu": cpu, "import": t_imp,
        "peak_ws_mb": ws, "peak_commit_mb": pf, "sim_time": r["time"], "winner": r["winner"],
        "timeout": r["timeout"], "early": r["early_stop"], "networth": r["networth"],
        "kills": [sum(u["kills"] for u in r["units"] if u["team"] == t) for t in (0, 1)],
        "core_hp": r["end"]["core_hp"]}), flush=True)


def spawn(seed_index, minutes, fast, native):
    env = dict(os.environ, PYTHONHASHSEED="0")
    if not native:
        env["POKEMOBA_NO_NATIVE"] = "1"
    else:
        env.pop("POKEMOBA_NO_NATIVE", None)
    args = [PY, __file__, "child", str(seed_index), str(minutes)] + (["--fast"] if fast else [])
    return subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def collect(p):
    out, err = p.communicate()
    for line in out.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    raise RuntimeError(err[-2000:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["single", "scale", "child"])
    ap.add_argument("idx", nargs="?", type=int)
    ap.add_argument("min", nargs="?", type=float)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--minutes", type=float, default=14.0)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--workers", default="1,4,8,16")
    ap.add_argument("--py", action="store_true", help="scale: usa Python puro")
    a = ap.parse_args()
    if a.mode == "child":
        return child(a.idx, a.min, a.fast)
    if a.mode == "single":
        rows = []
        for i in range(a.seeds):
            for nat in (True, False):
                r = collect(spawn(i, a.minutes, a.fast, nat))
                rows.append(r)
                print(f"seed {i} {'RUST  ' if nat else 'PYTHON'} wall {r['wall']:.1f}s cpu {r['cpu']:.1f}s "
                      f"ram {r['peak_ws_mb']:.0f}MB sim {r['sim_time']:.0f}s win {r['winner']} "
                      f"early {r['early']} nw {r['networth']} kills {r['kills']}", flush=True)
        Path(ROOT / "tools" / "bench_native_single.json").write_text(json.dumps(rows, indent=1))
    else:
        for n in [int(x) for x in a.workers.split(",")]:
            t0 = time.perf_counter()
            res, running, nxt = [], [], 0
            total = max(a.seeds, n)
            while nxt < total or running:
                while nxt < total and len(running) < n:
                    running.append(spawn(nxt, a.minutes, a.fast, not a.py))
                    nxt += 1
                p = running.pop(0)
                res.append(collect(p))
            wall = time.perf_counter() - t0
            print(f"workers {n:2d}: {total} partite in {wall:.0f}s -> {total / wall * 3600:.0f} partite/ora; "
                  f"CPU medio/partita {sum(r['cpu'] for r in res) / total:.1f}s, "
                  f"wall medio {sum(r['wall'] for r in res) / total:.1f}s, "
                  f"RAM media {sum(r['peak_ws_mb'] for r in res) / total:.0f}MB", flush=True)


if __name__ == "__main__":
    main()
