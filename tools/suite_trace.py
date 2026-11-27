"""Traccia COMPLETA per la suite di analisi: candidato (json) contro BASE, partite esatte,
entrambi i lati. Superset di jungle_trace.py (stesso formato: pos/camps/all/kills/ganks) piu':
  log["st"][id]   (t, hp%, livello, networth) ogni 5 s
  log["dmg"]      (t, att_id, vittima_id, perso, tipo_att)  solo vittime Pokemon (P/T/M/W/C)
  log["heal"]     (t, curatore_id, bersaglio_id, hp_guadagnati)
  log["shield"]   (t, lanciatore_id, bersaglio_id, quantita)
  log["farm"]     (t, tipo, killer_id, x, y)  tipo: cs / camp / legend / tower
  log["meta"]     nuclei, dimensione mappa
    python tools/suite_trace.py tools/cma_out/gen5_mean_g25.json --seeds 36 --out tools/cma_out/st_g25_mean.json
"""
import argparse, json, os, sys
from multiprocessing import get_context
from pathlib import Path
os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT)]
import cma_tune  # noqa: E402
import config  # noqa: E402

ASSIST = config.ASSIST_WINDOW
KIND = {"Pokemon": "P", "Structure": "T", "Minion": "M", "Wild": "W", "Core": "C"}


def run(task):
    import tier_sim
    from engine import match as M
    job, side, cand, opp = task
    tier_sim.OPTS["params"] = {side: cand, 1 - side: opp}
    log = {"pos": {0: [], 1: []}, "camps": [], "all": {}, "kills": [], "ganks": [],
           "st": {}, "dmg": [], "heal": [], "shield": [], "farm": [], "meta": {}}
    o_upd, o_kill, o_dmg, o_heal, o_shield, o_death = (M.Match.update, M.Match._award_kill, M.Match._deal_damage,
                                                       M.Match._give_heal, M.Match._give_shield, M.Match._on_death)
    gcur = {}
    nm = lambda e: type(e).__name__

    def kill(self, victim, killer):
        try:
            asst = [aid for aid, t0 in getattr(victim, "_damagers", {}).items()
                    if self.time - t0 <= ASSIST and aid != getattr(killer, "id", None)]
            log["kills"].append((round(self.time, 1), round(victim.pos.x, 1), round(victim.pos.y, 1), victim.id,
                                 victim.team, getattr(killer, "id", None), getattr(killer, "team", None),
                                 nm(killer), asst))
        except Exception:
            pass
        return o_kill(self, victim, killer)

    def dmg(self, attacker, target, amount, *a, **kw):
        if nm(target) == "Pokemon" and amount > 0:
            hp0 = target.hp
            r = o_dmg(self, attacker, target, amount, *a, **kw)
            lost = hp0 - target.hp
            if lost > 0:
                log["dmg"].append((round(self.time, 1), getattr(attacker, "id", None), target.id,
                                   round(lost, 1), KIND.get(nm(attacker), "?")))
            return r
        return o_dmg(self, attacker, target, amount, *a, **kw)

    def heal(self, caster, target, amount):
        hp0 = target.hp
        r = o_heal(self, caster, target, amount)
        g = target.hp - hp0
        if g > 0.5 and nm(target) == "Pokemon":
            log["heal"].append((round(self.time, 1), getattr(caster, "id", None), target.id, round(g, 1)))
        return r

    def shield(self, caster, target, amt, dur):
        if amt > 0 and nm(target) == "Pokemon":
            log["shield"].append((round(self.time, 1), getattr(caster, "id", None), target.id, round(amt, 1)))
        return o_shield(self, caster, target, amt, dur)

    def death(self, victim, killer):
        if nm(killer) == "Pokemon":
            v = nm(victim)
            k = None
            if v == "Minion": k = "cs"
            elif v == "Wild": k = "camp" if victim.kind == "camp" else "legend"
            elif v == "Structure" and getattr(victim, "kind", "") == "tower": k = "tower"
            if k:
                log["farm"].append((round(self.time, 1), k, killer.id, round(victim.pos.x), round(victim.pos.y)))
        return o_death(self, victim, killer)

    state = {"n1": 0.0, "n5": 0.0, "alive": {}}

    def worth(self, p):
        cat = self.item_catalog.items
        return float(p.gold) + sum(cat[i].price for i in p.items if i in cat)

    def upd(self, dt, tick):
        r = o_upd(self, dt, tick)
        t = self.time
        if not log["meta"]:
            log["meta"] = {"cores": {c.team: (round(c.pos.x, 1), round(c.pos.y, 1)) for c in self.world.cores()}}
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
        if t >= state["n5"]:
            state["n5"] = t + 5.0
            ss = {0: [0, 0.0, 0.0], 1: [0, 0.0, 0.0]}        # torri vive, hp torri (frazione somma), hp nucleo (frazione)
            for s_ in self.world.structures():
                if getattr(s_, "kind", "") == "tower" and s_.alive:
                    ss[s_.team][0] += 1; ss[s_.team][1] += s_.hp / max(1.0, s_.max_hp)
            for c_ in self.world.cores():
                ss[c_.team][2] = round(c_.hp / max(1.0, c_.max_hp), 3)
            log.setdefault("str", []).append((round(t), ss[0][0], round(ss[0][1], 2), ss[0][2],
                                              ss[1][0], round(ss[1][1], 2), ss[1][2]))
            for p in self.world.pokemons():
                log["st"].setdefault(p.id, []).append(
                    (round(t), round(100 * p.hp / max(1.0, p.max_hp)), p.level, round(worth(self, p))))
        if t >= state["n1"]:
            state["n1"] = t + 1.0
            jg = {p.team: p for p in self.world.pokemons() if getattr(p, "is_jungler", False)}
            for tm, p in jg.items():
                log["pos"][tm].append((round(t, 1), round(p.pos.x, 1), round(p.pos.y, 1), p.alive, p.level))
            for p in self.world.pokemons():
                log["all"].setdefault(p.id, {"team": p.team, "name": p.name, "p": []})["p"].append(
                    (round(t, 1), round(p.pos.x, 1), round(p.pos.y, 1), p.alive))
            cur = {w.id: w for w in self.world.wilds()}
            for wid, w in list(state["alive"].items()):
                if (wid not in cur or not cur[wid].alive) and w is not None:
                    ds = {tm: round(p.pos.dist(w.pos), 1) for tm, p in jg.items()}
                    log["camps"].append((round(t, 1), w.kind, round(w.pos.x), round(w.pos.y), ds))
                    state["alive"][wid] = None
            for wid, w in cur.items():
                if w.alive and state["alive"].get(wid) is None:
                    state["alive"][wid] = w
        return r

    M.Match.update, M.Match._award_kill, M.Match._deal_damage = upd, kill, dmg
    M.Match._give_heal, M.Match._give_shield, M.Match._on_death = heal, shield, death
    try:
        r = tier_sim.play(job)
    finally:
        (M.Match.update, M.Match._award_kill, M.Match._deal_damage,
         M.Match._give_heal, M.Match._give_shield, M.Match._on_death) = (o_upd, o_kill, o_dmg, o_heal, o_shield, o_death)
    keys = ("team", "name", "camps", "dmg_wild", "smites", "kills", "deaths", "assists", "level", "gold", "u_time",
            "u_switches", "dmg", "taken", "cs", "id", "role", "cc", "support", "selfheal", "towers", "sdmg",
            "dmg_minion", "maxhit", "fb", "tower_deaths", "best_streak", "lane", "jungle", "is_support", "final_name")
    return {"seed": job[0], "side": side, "winner": r["winner"], "time": r["time"], "log": log,
            "jungler": r["jungler"], "networth": r["networth"], "end": r["end"], "early": r["early_stop"],
            "all": [{k: u.get(k) for k in keys} for u in r["units"]]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("params")
    ap.add_argument("--seeds", type=int, default=36)
    ap.add_argument("--seed-base", type=int, default=5000)
    ap.add_argument("--minutes", type=float, default=14.0)
    ap.add_argument("--opp", default=None, help="params.json dell'avversario (default: BASE)")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", default="tools/cma_out/suite_trace.json")
    a = ap.parse_args()
    import tier_sim
    cand = json.loads(Path(a.params).read_text())
    jobs = tier_sim.make_jobs(a.seeds, a.seed_base)
    opp = json.loads(Path(a.opp).read_text()) if a.opp else cma_tune.BASE_PARAMS
    tasks = [(j, s, cand, opp) for j in jobs for s in (0, 1)]
    with get_context("spawn").Pool(a.workers, initializer=cma_tune._init, initargs=(a.minutes * 60.0,)) as pool:
        res = []
        for i, r in enumerate(pool.imap(run, tasks)):
            res.append(r); print(i + 1, len(tasks), r["seed"], r["side"], flush=True)
    Path(a.out).write_text(json.dumps(res))


if __name__ == "__main__":
    main()
