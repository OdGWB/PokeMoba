"""Taratura dei parametri dei bot con CMA-ES su partite INTERE (5v5, headless).

Ogni candidato e' un insieme di BotParams per GRUPPO (jungler, support, e per gli
altri il ruolo base: tiratore, mago, combattente, assassino, tank). Il candidato
gioca contro un avversario fisso (i parametri di base, o il migliore trovato finora
con --opp best) e la bonta' e' la media su piu' partite:

  - stessi semi per tutti i candidati di una generazione (numeri casuali comuni:
    le differenze vengono dai parametri, non dalle squadre pescate);
  - ogni seme si gioca DUE volte, col candidato una volta nella squadra 0 e una
    nella 1 (stesse squadre: si annulla il vantaggio del lato);
  - punteggio continuo, non solo vittoria: 0.5*vittoria(+-1) + 0.25*tanh(patrimonio/5000)
    + 0.25*(torri vive di differenza)/9 (patrimonio = oro + prezzo degli oggetti).

Per le prime generazioni (--fast): stop anticipato delle partite gia' decise
(tier_sim.EARLY_STOP) e modalita' allenamento (visione e IA dei minion ogni 2-3 tick,
approssimate). Il lato si alterna comunque: ogni seme pesca due rose diverse, giocarlo
due volte a lati scambiati annulla la fortuna delle rose, non un vantaggio della mappa.

CMA-ES lavora in [0,1]^d (ogni parametro normalizzato tra i suoi limiti); con molte
dimensioni si usa la variante diagonale (sep-CMA). Lo stato si salva a ogni
generazione e si riprende con --resume.

Uso:
  python tools/cma_tune.py --run prova --gens 30 --seeds 4 --minutes 14
  python tools/cma_tune.py --run prova --resume
  python tools/cma_tune.py --run prova --gens 10 --fast      # prime generazioni veloci...
  python tools/cma_tune.py --run prova --resume --gens 30    # ...poi esatte (i flag di
                                     # allenamento non si ereditano: decide la riga di comando)
  python tools/cma_tune.py --run smoke --popsize 4 --seeds 1 --minutes 2 --gens 1

Uscita in tools/cma_out/<run>/: state.pkl, log.jsonl (una riga per generazione),
best.json ({gruppo: {campo: valore}}, pronto per OPTS["params"] / Match).
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from engine.bot_params import BotParams  # noqa: E402

GROUPS = ["jungler", "support", "tiratore", "mago", "combattente", "assassino", "tank"]

# Campo -> (minimo, massimo). Pesi del punteggio e qualche soglia di centro rampa.
SPACE = {
    "aggro":          (4.0, 9.0),
    "retreat_hp":     (0.10, 0.50),
    "recall_gold":    (500.0, 1600.0),
    "u_stick":        (0.0, 0.40),
    "u_w_retreat":    (0.5, 3.0),
    "u_ret_danger":   (0.0, 2.0),
    "u_w_fight":      (0.3, 2.0),
    "u_fight_k":      (1.0, 10.0),
    "u_fight_adv":    (0.0, 2.5),
    "u_fight_hp":     (0.0, 2.5),
    "u_fight_bias":   (-0.5, 1.0),
    "u_fight_tower":  (0.0, 1.5),
    "u_w_shop":       (0.3, 2.0),
    "u_w_heal":       (0.0, 1.5),
    "u_w_core":       (0.3, 2.5),
    "u_w_siege":      (0.2, 2.0),
    "u_siege_bias":   (-1.0, 1.0),
    "u_w_lane":       (0.1, 1.0),
}
# Campi che contano solo per un gruppo (altrove sarebbero dimensioni piatte).
EXTRA = {
    "jungler": {"gank_hp": (0.4, 1.0), "gank_cooldown": (20.0, 120.0),
                "gank_min_time": (90.0, 300.0)},
    "support": {"u_w_roam": (0.0, 1.5), "u_roam_bias": (0.0, 6.0)},
}
INTS = {f.name for f in BotParams.__dataclass_fields__.values() if f.type in ("int", int)}

# Base comune: IA a punteggio + gli allargamenti del gank che tier_sim mette con --plan.
BASELINE = BotParams().copy(utility=True, gank_hp=0.9, gank_cooldown=40.0, gank_min_time=210.0)


def layout(groups):
    """[(gruppo, campo, lo, hi)] nell'ordine del vettore."""
    out = []
    for g in groups:
        sp = dict(SPACE)
        sp.update(EXTRA.get(g, {}))
        out += [(g, k, lo, hi) for k, (lo, hi) in sp.items()]
    return out


def x0_of(lay, start=None):
    """Punto di partenza normalizzato (dai parametri di base o da un best.json)."""
    xs = []
    for g, k, lo, hi in lay:
        v = (start or {}).get(g, {}).get(k, getattr(BASELINE, k))
        xs.append(min(1.0, max(0.0, (v - lo) / (hi - lo))))
    return xs


def decode(lay, x):
    """Vettore in [0,1]^d -> {gruppo: {campo: valore}} (piu' utility=True per tutti)."""
    out = {"*": {"utility": True}}
    for (g, k, lo, hi), xi in zip(lay, x):
        v = lo + min(1.0, max(0.0, float(xi))) * (hi - lo)
        out.setdefault(g, {})[k] = int(round(v)) if k in INTS else round(v, 4)
    return out


BASE_PARAMS = {"*": {"utility": True}}      # avversario di default (= BASELINE)


# --- processi --------------------------------------------------------------------
def _init(max_time, early_stop=None, vision_stride=1, minion_stride=1):
    import tier_sim
    tier_sim._init_worker(False, max_time, True, None, early_stop, vision_stride, minion_stride)


def _eval(task):
    """Una partita. task = (job, lato del candidato, params candidato, params avversario)."""
    import tier_sim
    job, side, cand, opp = task
    tier_sim.OPTS["params"] = {side: cand, 1 - side: opp}
    r = tier_sim.play(job)
    gold = r["networth"]
    towers = [sum(r["end"]["towers"][t].values()) for t in (0, 1)]
    kills = [sum(u["kills"] for u in r["units"] if u["team"] == t) for t in (0, 1)]
    o = 1 - side
    win = 1.0 if r["winner"] == side else -1.0
    score = (0.5 * win + 0.25 * math.tanh((gold[side] - gold[o]) / 5000.0)
             + 0.25 * (towers[side] - towers[o]) / 9.0)
    return {"seed": job[0], "side": side, "score": score, "win": r["winner"] == side,
            "timeout": r["timeout"], "time": r["time"], "gold": gold[side] - gold[o],
            "towers": towers[side] - towers[o], "kills": kills[side] - kills[o],
            "early": r["early_stop"] is not None}


# --- ciclo principale ------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="nome della cartella in tools/cma_out")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--gens", type=int, default=30)
    ap.add_argument("--popsize", type=int, default=0, help="0 = default di CMA (4+3 ln d)")
    ap.add_argument("--seeds", type=int, default=4, help="semi per generazione (x2 lati)")
    ap.add_argument("--minutes", type=float, default=14.0, help="durata massima di gioco")
    ap.add_argument("--sigma", type=float, default=0.2)
    ap.add_argument("--groups", default=",".join(GROUPS))
    ap.add_argument("--opp", choices=["base", "best"], default="base")
    ap.add_argument("--opp-every", type=int, default=5, help="con --opp best: ogni N generazioni")
    ap.add_argument("--start", default=None, help="best.json da cui partire")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--seed-base", type=int, default=900)
    ap.add_argument("--early-stop", type=float, default=0.0, metavar="SOGLIA",
                    help="stop anticipato con questa soglia di vantaggio (0 = spento; 2 = tipico)")
    ap.add_argument("--vision-stride", type=int, default=1)
    ap.add_argument("--minion-stride", type=int, default=1)
    ap.add_argument("--fast", action="store_true",
                    help="allenamento veloce: --early-stop 2 --vision-stride 3 --minion-stride 2")
    a = ap.parse_args()
    if a.fast:
        a.early_stop = a.early_stop or 2.0
        a.vision_stride = max(a.vision_stride, 3)
        a.minion_stride = max(a.minion_stride, 2)

    import cma

    out = ROOT / "tools" / "cma_out" / a.run
    out.mkdir(parents=True, exist_ok=True)
    state_f, log_f, best_f = out / "state.pkl", out / "log.jsonl", out / "best.json"

    if a.resume and state_f.exists():
        st = pickle.loads(state_f.read_bytes())
        es, lay, gen, opp, best = st["es"], st["lay"], st["gen"], st["opp"], st["best"]
        a.minutes, a.seeds, a.seed_base = st["minutes"], st["seeds"], st["seed_base"]
        print(f"ripresa da generazione {gen}")
    else:
        groups = [g for g in a.groups.split(",") if g]
        lay = layout(groups)
        start = json.loads(Path(a.start).read_text()) if a.start else None
        d = len(lay)
        opts = {"bounds": [0, 1], "seed": a.seed_base, "verbose": -9}
        if a.popsize:
            opts["popsize"] = a.popsize
        if d > 40:
            opts["CMA_diagonal"] = True
        es = cma.CMAEvolutionStrategy(x0_of(lay, start), a.sigma, opts)
        gen, opp, best = 0, BASE_PARAMS, {"f": None, "params": None, "gen": None}
        print(f"d={d} popsize={es.popsize} diagonale={d > 40}")

    os.environ.setdefault("PYTHONHASHSEED", "0")
    from tier_sim import make_jobs

    with mp.get_context("spawn").Pool(a.workers, initializer=_init,
                                      initargs=(a.minutes * 60.0,
                                                {"threshold": a.early_stop} if a.early_stop else None,
                                                a.vision_stride, a.minion_stride)) as pool:
        while gen < a.gens and not es.stop():
            t0 = time.time()
            xs = es.ask()
            cands = [decode(lay, x) for x in xs]
            jobs = make_jobs(a.seeds, a.seed_base + gen)       # stessi semi per tutti
            tasks, owner = [], []
            for ci, c in enumerate(cands):
                for job in jobs:
                    for side in (0, 1):
                        tasks.append((job, side, c, opp))
                        owner.append(ci)
            res = pool.map(_eval, tasks, chunksize=1)
            per = [[] for _ in cands]
            for ci, r in zip(owner, res):
                per[ci].append(r)
            fit = [-sum(r["score"] for r in rs) / len(rs) for rs in per]   # CMA minimizza
            es.tell(xs, fit)
            gen += 1
            bi = min(range(len(fit)), key=fit.__getitem__)
            if best["f"] is None or fit[bi] < best["f"]:
                best = {"f": fit[bi], "params": cands[bi], "gen": gen}
                best_f.write_text(json.dumps(best["params"], indent=1))
            mean_p = decode(lay, es.mean)
            (out / "mean.json").write_text(json.dumps(mean_p, indent=1))
            rec = {"gen": gen, "wall": round(time.time() - t0, 1), "sigma": round(es.sigma, 4),
                   "fit_best": round(fit[bi], 4), "fit_med": round(sorted(fit)[len(fit) // 2], 4),
                   "win_best": sum(r["win"] for r in per[bi]) / len(per[bi]),
                   "win_all": round(sum(r["win"] for rs in per for r in rs) / len(res), 3),
                   "timeouts": sum(r["timeout"] for r in res), "matches": len(res),
                   "early": sum(r["early"] for r in res),
                   "train": [a.early_stop, a.vision_stride, a.minion_stride],
                   "game_min": round(sum(r["time"] for r in res) / len(res) / 60, 1),
                   "best_ever": round(best["f"], 4), "opp": "base" if opp == BASE_PARAMS else "best"}
            with log_f.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            print(json.dumps(rec), flush=True)
            if a.opp == "best" and gen % a.opp_every == 0:
                opp = mean_p            # la media della distribuzione: piu' stabile del migliore singolo
            state_f.write_bytes(pickle.dumps({"es": es, "lay": lay, "gen": gen, "opp": opp,
                                              "best": best, "minutes": a.minutes,
                                              "seeds": a.seeds, "seed_base": a.seed_base,
                                              "train": [a.early_stop, a.vision_stride,
                                                        a.minion_stride]}))


if __name__ == "__main__":
    main()
