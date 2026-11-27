"""Analisi del jungle pathing: candidato (json) contro BASE, partite esatte, entrambi i lati.

    python tools/jungle_trace.py tools/cma_out/gen5/mean.json --seeds 8
Campiona ogni jungler a 1 s: posizione, intenzione, e registra morte dei campi (chi era vicino).
"""
import argparse, json, os, sys, math
from multiprocessing import get_context
from pathlib import Path
os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
import cma_tune  # noqa: E402

import config
config_assist = config.ASSIST_WINDOW

def run(task):
    import tier_sim
    from engine import match as M
    job, side, cand, opp = task
    tier_sim.OPTS["params"] = {side: cand, 1 - side: opp}
    log = {"pos": {0: [], 1: []}, "camps": [], "int": {0: [], 1: []}, "all": {}, "kills": [], "ganks": []}
    orig = M.Match.update
    orig_kill = M.Match._award_kill
    gcur = {}   # jungler id -> gank in corso

    def kill(self, victim, killer):
        try:
            asst = [aid for aid, t0 in getattr(victim, "_damagers", {}).items()
                    if self.time - t0 <= config_assist and aid != getattr(killer, "id", None)]
            log["kills"].append((round(self.time, 1), round(victim.pos.x, 1), round(victim.pos.y, 1), victim.id,
                                 victim.team, getattr(killer, "id", None), getattr(killer, "team", None),
                                 type(killer).__name__, asst))
        except Exception:
            pass
        return orig_kill(self, victim, killer)
    state = {"next": 0.0, "alive": {}}
    def upd(self, dt, tick):
        r = orig(self, dt, tick)
        t = self.time
        for p in self.world.pokemons():
            if not getattr(p, "is_jungler", False):
                continue
            gid = self._ai.get(p.id, {}).get("gank_id")
            g = gcur.get(p.id)
            if gid is not None and (g is None or g["tid"] != gid):
                if g is not None:
                    g["end"] = round(t, 1); g["why"] = "retarget"
                e = self.world.get(gid)
                if e is not None:
                    g = {"t": round(t, 1), "jid": p.id, "team": p.team, "tid": gid, "tname": e.name,
                         "tpos": (round(e.pos.x, 1), round(e.pos.y, 1)), "jpos": (round(p.pos.x, 1), round(p.pos.y, 1)),
                         "hp": round(e.hp / max(1.0, e.max_hp), 2), "end": None, "why": None}
                    log["ganks"].append(g); gcur[p.id] = g
            elif gid is None and g is not None:
                tgt = self.world.get(g["tid"])
                g["end"] = round(t, 1)
                g["why"] = "dead" if (tgt is None or not tgt.alive) else ("jungler_dead" if not p.alive else "gave_up")
                gcur[p.id] = None
        if t >= state["next"]:
            state["next"] = t + 1.0
            jg = {p.team: p for p in self.world.pokemons() if getattr(p, "is_jungler", False)}
            for tm, p in jg.items():
                tr = getattr(self, "bot_trace", {}).get(p.id, {})
                last = (tr.get("last") or [None])[-1] if tr.get("last") else None
                log["pos"][tm].append((round(t, 1), round(p.pos.x, 1), round(p.pos.y, 1), p.alive, p.level))
            for p in self.world.pokemons():
                log["all"].setdefault(p.id, {"team": p.team, "name": p.name, "p": []})["p"].append(
                    (round(t, 1), round(p.pos.x, 1), round(p.pos.y, 1), p.alive))
            cur = {}
            for w in self.world.wilds():
                cur[w.id] = w
            for wid, w in list(state["alive"].items()):
                if (wid not in cur or not cur[wid].alive) and w is not None:
                    ds = {tm: round(p.pos.dist(w.pos), 1) for tm, p in jg.items()}
                    log["camps"].append((round(t, 1), w.kind, round(w.pos.x), round(w.pos.y), ds))
                    state["alive"][wid] = None
            for wid, w in cur.items():
                if w.alive and state["alive"].get(wid) is None:
                    state["alive"][wid] = w
        return r
    M.Match.update = upd
    M.Match._award_kill = kill
    try:
        r = tier_sim.play(job)
    finally:
        M.Match.update = orig
        M.Match._award_kill = orig_kill
    out = {"seed": job[0], "side": side, "winner": r["winner"], "time": r["time"], "log": log, "units": {}}
    for u in r["units"]:
        if u["team"] in (0, 1) and u.get("name") and u["name"] in [r["jungler"][0], r["jungler"][1]] or u.get("is_jungler"):
            out["units"].setdefault(u["team"], u)
    out["jungler"] = r["jungler"]
    out["networth"] = r["networth"]; out["end"] = r["end"]; out["early"] = r["early_stop"]
    out["all"] = [{k: u.get(k) for k in ("team", "name", "camps", "dmg_wild", "smites", "kills", "deaths", "assists",
                  "level", "gold", "u_time", "u_switches", "dmg", "cs", "id", "role")} for u in r["units"]]
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("params")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--seed-base", type=int, default=5000)
    ap.add_argument("--minutes", type=float, default=14.0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", default="tools/cma_out/jungle_trace.json")
    a = ap.parse_args()
    import tier_sim
    cand = json.loads(Path(a.params).read_text())
    jobs = tier_sim.make_jobs(a.seeds, a.seed_base)
    tasks = [(j, s, cand, cma_tune.BASE_PARAMS) for j in jobs for s in (0, 1)]
    with get_context("spawn").Pool(a.workers, initializer=cma_tune._init, initargs=(a.minutes * 60.0,)) as pool:
        res = []
        for i, r in enumerate(pool.imap(run, tasks)):
            res.append(r); print(i + 1, len(tasks), r["seed"], r["side"], flush=True)
    Path(a.out).write_text(json.dumps(res))

if __name__ == "__main__":
    main()
