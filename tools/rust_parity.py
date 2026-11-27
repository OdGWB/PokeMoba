"""Parita' tick per tick fra due motori sulla stessa partita di tier_sim.

Motori:  py      Python puro (POKEMOBA_NO_NATIVE=1): il RIFERIMENTO
         native  Python + estensione Rust attuale (pokemoba_native)
         rust    motore di allenamento in Rust (pokemoba_native.run_match)

Ogni motore gioca il job in un processo a parte e scrive, per ogni tick, le
impronte dello stato canonico (tools/sim_spec.snapshot): tempo, RNG, Match,
entita'. Alla prima differenza le due partite si rigiocano fino a quel tick e si
stampano i campi diversi (entita', campo, valore di A e di B).

    python tools/rust_parity.py                       # py vs native, 3 job x 60 s
    python tools/rust_parity.py --b rust --jobs 5 --secs 240
Esce con 0 se tutto coincide, 1 se c'e' una differenza, 3 se un motore non c'e'.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINES = ("py", "native", "rust")
NOT_AVAILABLE = 3


def _md5(x) -> str:
    return hashlib.md5(repr(x).encode()).hexdigest()


# --- processo figlio -------------------------------------------------------------

def _worker(engine, job_i, secs, out, full_at, start_seed):
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    os.chdir(ROOT)
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import tier_sim
    import sim_spec
    tier_sim._init_worker(False, secs, True)
    job = tier_sim.make_jobs(job_i + 1, start_seed)[job_i]
    if engine == "rust":
        try:
            import pokemoba_native as nat
        except ImportError:
            nat = None
        if nat is None or not hasattr(nat, "run_match"):
            print("rust: pokemoba_native senza run_match", file=sys.stderr)
            sys.exit(NOT_AVAILABLE)
        spec = sim_spec.build_spec(job)
        spec["trace"] = {"full_at": full_at}
        res = nat.run_match(spec)
        if res.get("stub"):
            print("rust: run_match in questa build e' ancora uno stub (fase 0): "
                  "spec letta, %d tick previsti, RNG passato (%r)" % (res["ticks"], res["rng_next"]),
                  file=sys.stderr)
            sys.exit(NOT_AVAILABLE)
        with open(out, "w") as f:      # fase 1+: il Rust restituisce le stesse impronte
            json.dump({"ticks": res["trace"], "full": res.get("full")}, f)
        return
    import engine.match as em
    orig = em.Match.update
    ticks, full = [], {}
    n = [0]

    class _Done(Exception):
        pass

    def update(self, dt, tick):
        r = orig(self, dt, tick)
        n[0] += 1
        s = sim_spec.snapshot(self)
        if full_at is not None:
            if n[0] == full_at:
                full["snap"] = s
                raise _Done
            return r
        ticks.append([n[0], s["time"], s["rng"], _md5(s["match"]), _md5(s["entities"])])
        return r

    em.Match.update = update
    try:
        tier_sim.play(job)
    except _Done:
        pass
    with open(out, "w") as f:
        json.dump({"ticks": ticks, "full": full.get("snap")}, f)


# --- confronto ---------------------------------------------------------------

def _run(engine, job_i, secs, start_seed, full_at=None):
    fd, out = tempfile.mkstemp(suffix=".json", prefix="parity_%s_" % engine)
    os.close(fd)
    env = dict(os.environ, PYTHONHASHSEED="0", SDL_VIDEODRIVER="dummy")
    env.pop("POKEMOBA_NO_NATIVE", None)
    if engine == "py":
        env["POKEMOBA_NO_NATIVE"] = "1"
    cmd = [sys.executable, os.path.abspath(__file__), "--worker", engine, "--job", str(job_i),
           "--secs", str(secs), "--out", out, "--seed", str(start_seed)]
    if full_at is not None:
        cmd += ["--full-at", str(full_at)]
    return subprocess.Popen(cmd, env=env, stderr=subprocess.PIPE, text=True), out


def _collect(proc_out):
    proc, out = proc_out
    _, err = proc.communicate()
    try:
        if proc.returncode != 0:
            return proc.returncode, err.strip(), None
        with open(out) as f:
            return 0, err.strip(), json.load(f)
    finally:
        os.remove(out)


def _field_diff(a, b, limit):
    """Campi diversi fra due snapshot completi: [(dove, campo, A, B)]."""
    diffs = []
    if a["rng"] != b["rng"]:
        diffs.append(("rng", "state", a["rng"], b["rng"]))
    for k in sorted(set(a["match"]) | set(b["match"])):
        va, vb = a["match"].get(k, "<assente>"), b["match"].get(k, "<assente>")
        if va != vb:
            diffs.append(("match", k, va, vb))
    ea, eb = dict((i, r) for i, r in a["entities"]), dict((i, r) for i, r in b["entities"])
    if [i for i, _ in a["entities"]] != [i for i, _ in b["entities"]]:
        diffs.append(("world", "entity ids", [i for i, _ in a["entities"]], [i for i, _ in b["entities"]]))
    for i in ea:
        if i not in eb:
            continue
        ra, rb = ea[i], eb[i]
        for k in ra:
            if k in rb and ra[k] != rb[k]:
                diffs.append(("%s %s" % (ra["_type"], i), k, ra[k], rb[k]))
    return diffs[:limit]


def _short(v, n=110):
    s = repr(v)
    return s if len(s) <= n else s[:n] + "..."


def compare(a, b, jobs, secs, start_seed, limit=20) -> int:
    runs = [(j, _run(a, j, secs, start_seed), _run(b, j, secs, start_seed)) for j in range(jobs)]
    status = 0
    for j, pa, pb in runs:
        ca, ea, ra = _collect(pa)
        cb, eb, rb = _collect(pb)
        for eng, code, err in ((a, ca, ea), (b, cb, eb)):
            if code:
                print("job %d: motore %s non disponibile/errore (%d)\n  %s" % (j, eng, code, err[-600:]))
                status = max(status, NOT_AVAILABLE if code == NOT_AVAILABLE else 1)
        if ca or cb:
            continue
        ta, tb = ra["ticks"], rb["ticks"]
        first = next((x for x, y in zip(ta, tb) if x != y), None)
        if first is None and len(ta) == len(tb):
            print("job %d: %s == %s per %d tick" % (j, a, b, len(ta)))
            continue
        status = 1
        if first is None:
            print("job %d: stessi tick ma durata diversa (%d vs %d)" % (j, len(ta), len(tb)))
            continue
        t = first[0]
        y = tb[ta.index(first)]
        parts = [n for n, u, v in zip(("time", "rng", "match", "entities"), first[1:], y[1:]) if u != v]
        print("job %d: prima differenza al tick %d (%s)" % (j, t, ", ".join(parts)))
        fa, fb = _run(a, j, secs, start_seed, t), _run(b, j, secs, start_seed, t)
        (_, _, sa), (_, _, sb) = _collect(fa), _collect(fb)
        if sa and sb and sa["full"] and sb["full"]:
            for where, k, va, vb in _field_diff(sa["full"], sb["full"], limit):
                print("  %-18s %-22s %s: %s\n  %-18s %-22s %s: %s" % (where, k, a, _short(va), "", "", b, _short(vb)))
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", default="py", choices=ENGINES)
    ap.add_argument("--b", default="native", choices=ENGINES)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--secs", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=7, help="seme iniziale di tier_sim.make_jobs")
    ap.add_argument("--limit", type=int, default=20, help="campi diversi da stampare")
    ap.add_argument("--worker", choices=ENGINES, help=argparse.SUPPRESS)
    ap.add_argument("--job", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    ap.add_argument("--full-at", type=int, help=argparse.SUPPRESS)
    o = ap.parse_args()
    if o.worker:
        _worker(o.worker, o.job, o.secs, o.out, o.full_at, o.seed)
        return
    sys.exit(compare(o.a, o.b, o.jobs, o.secs, o.seed, o.limit))


if __name__ == "__main__":
    main()
