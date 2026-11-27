"""Parita' di UN sistema del motore Rust, passo per passo, su partite vere.

Si gioca un job di tier_sim nel motore Python (con l'estensione, identico al
Python puro: tools/rust_parity.py). A ogni tick, attorno al sistema scelto:
  1. stato prima (righe canoniche delle entita', solo i campi che il Rust legge)
  2. il sistema in Python (quello vero della partita)
  3. lo stesso sistema in Rust sullo stato del punto 1
  4. confronto dei campi che il sistema scrive, e tempi dei due
Cosi' ogni sistema portato si verifica da solo, sugli stati veri, senza dover
spegnere il resto del motore.

    python tools/sim_step_parity.py --system world_tick --jobs 3 --secs 240
Esce con 0 se tutto coincide, 1 alla prima differenza (stampata).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.chdir(ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pokemoba_native as nat  # noqa: E402
import tier_sim  # noqa: E402
from sim_spec import canon  # noqa: E402

SYSTEMS = ("world_tick",)


def rows(world, fields):
    out = []
    for eid, e in world.entities.items():
        r = {"_type": type(e).__name__}
        for f in fields:
            if f != "_type" and hasattr(e, f):
                r[f] = canon(getattr(e, f), 1)
        out.append([eid, r])
    return out


def unit_rows(world, fields):
    from engine.entities import Unit
    return [(e.id, {f: canon(getattr(e, f), 1) for f in fields})
            for e in world.entities.values() if isinstance(e, Unit)]


def _put_in_wall(world, k):
    """Mette un'unita' a terra col centro dentro il muro piu' vicino (per provare
    l'anti-incastro di advance_unit, che nelle partite capita di rado)."""
    movers = [u for u in world.alive_units() if getattr(u, "air_z", 0.0) <= 0.0]
    if not movers:
        return
    from engine.vec import Vec2
    u = movers[k % len(movers)]
    g = world.grid
    cx, cy = int(u.pos.x), int(u.pos.y)
    for r in range(1, 8):
        for ty in range(cy - r, cy + r + 1):
            for tx in range(cx - r, cx + r + 1):
                if g.in_bounds(tx, ty) and not g.is_walkable_point(tx + 0.5, ty + 0.5, u.bush_blocks):
                    u.pos = Vec2(tx + 0.5, ty + 0.5)
                    return


def run(system, jobs, secs, seed, reps, limit, inject=0, parts=0):
    import engine.world as ew
    fields = nat.sim_fields()
    f_in, f_out = fields["in"], fields[system]
    st = {"ticks": 0, "bad": 0, "py_s": 0.0, "rs_ns": 0.0, "units": 0, "stuck": 0, "tower": 0,
          "parts": [0.0, 0.0, 0.0]}
    shown = [0]
    orig = ew.World.tick

    def tick(self, dt):
        grid = self.grid
        nv = grid.native_view()
        if inject and st["ticks"] % inject == 0:
            _put_in_wall(self, st["ticks"])
        before = rows(self, f_in)
        # Copertura dei rami rari: unita' a terra col centro in un muro (anti-incastro)
        # e unita' a contatto con una torre (spinta fuori).
        movers = self.alive_units()
        st["stuck"] += sum(1 for u in movers if getattr(u, "air_z", 0.0) <= 0.0
                           and not grid.is_walkable_point(u.pos.x, u.pos.y, u.bush_blocks))
        towers = [s for s in self.structures() if s.kind == "tower" and s.alive]
        t = time.perf_counter()
        orig(self, dt)
        st["py_s"] += time.perf_counter() - t
        want = unit_rows(self, f_out)
        st["tower"] += sum(1 for u in movers for s in towers
                           if (u.pos - s.pos).length() < 0.85 + u.radius + 0.02)
        got, ns = nat.sim_world_tick(nv, bytes(grid._shape_cen_b), before, dt, reps)
        st["rs_ns"] += ns
        if parts:
            for k, v in enumerate(nat.sim_world_tick_parts(nv, bytes(grid._shape_cen_b), before, dt, parts)):
                st["parts"][k] += v
        st["ticks"] += 1
        st["units"] += len(want)
        got = [(i, dict(r)) for i, r in got]
        if got != want:
            st["bad"] += 1
            if shown[0] < limit:
                shown[0] += 1
                gd = dict(got)
                for i, w in want:
                    g = gd.get(i)
                    if g != w:
                        for k in f_out:
                            if g is None or g.get(k) != w.get(k):
                                print("  tick %d unit %d %s\n    py:   %r\n    rust: %r"
                                      % (st["ticks"], i, k, w.get(k), None if g is None else g.get(k)))
                        break

    ew.World.tick = tick
    try:
        tier_sim._init_worker(False, secs, True)
        for j, job in enumerate(tier_sim.make_jobs(jobs, seed)):
            t0, b0 = st["ticks"], st["bad"]
            tier_sim.play(job)
            print("job %d: %d tick, %d diversi" % (j, st["ticks"] - t0, st["bad"] - b0), flush=True)
    finally:
        ew.World.tick = orig
    n = max(1, st["ticks"])
    print("%s: %d tick, %d diversi | Python (estensione attuale) %.1f us/tick, "
          "Rust su stato proprio %.2f us/tick (%.0fx), %.1f unita'/tick"
          % (system, st["ticks"], st["bad"], st["py_s"] / n * 1e6, st["rs_ns"] / n / 1e3,
             (st["py_s"] / n * 1e9) / max(1.0, st["rs_ns"] / n) if reps else 0.0, st["units"] / n))
    print("copertura: %d unita' col centro in un muro, %d contatti con una torre" % (st["stuck"], st["tower"]))
    if parts:
        print("Rust per fase (us/tick): passo %.2f, collisioni %.2f, torri %.2f"
              % tuple(v / n / 1e3 for v in st["parts"]))
    return 1 if st["bad"] else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", default="world_tick", choices=SYSTEMS)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--secs", type=float, default=120.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--reps", type=int, default=5, help="ripetizioni cronometrate del passo Rust (0 = niente tempi)")
    ap.add_argument("--limit", type=int, default=5, help="differenze da stampare")
    ap.add_argument("--inject-stuck", type=int, default=0, metavar="N",
                    help="ogni N tick mette un'unita' dentro un muro (prova l'anti-incastro)")
    ap.add_argument("--parts", type=int, default=0, metavar="R", help="tempi del Rust per fase (R ripetizioni)")
    o = ap.parse_args()
    sys.exit(run(o.system, o.jobs, o.secs, o.seed, o.reps, o.limit, o.inject_stuck, o.parts))


if __name__ == "__main__":
    main()
