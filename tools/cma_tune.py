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
# Posizionamento / macro: dove stare, quando assediare, quanto difendere. Valgono per tutti i gruppi.
SPACE.update({
    "tower_w_ally":   (0.0, 6.0),      # peso di (alleati - nemici) nella scelta della torre (prima fisso a 3)
    "tower_w_dist":   (0.1, 1.5),
    "tower_w_minion": (0.0, 20.0),
    "siege_from":     (120.0, 480.0),
    "siege_my_hp":    (0.3, 0.8),
    "core_from":      (90.0, 420.0),
    "u_siege_k":      (0.05, 0.4),
    "defend_max_dist": (8.0, 40.0),
    "defend_enemy_r": (3.0, 10.0),
})
# Solo ruoli di lane (il jungler non ha un guinzaglio di lane).
LANE_ONLY = {"lane_leash_early": (3.0, 12.0), "lane_leash": (8.0, 24.0), "early_time": (60.0, 300.0)}
# Campi che contano solo per un gruppo (altrove sarebbero dimensioni piatte).
EXTRA = {
    "jungler": {"gank_hp": (0.4, 1.0), "gank_cooldown": (20.0, 120.0),
                "gank_min_time": (90.0, 300.0)},
    "support": {"u_w_roam": (0.0, 1.5), "u_roam_bias": (0.0, 6.0),
                "roam_from": (90.0, 360.0), "roam_time": (10.0, 40.0)},
}
INTS = {f.name for f in BotParams.__dataclass_fields__.values() if f.type in ("int", int)}

# Base comune: IA a punteggio + gli allargamenti del gank che tier_sim mette con --plan.
BASELINE = BotParams().copy(utility=True, gank_hp=0.9, gank_cooldown=40.0, gank_min_time=210.0)


# Solo posizionamento/macro: per gli exploiter (avversari fatti a mano che si ottimizzano senza cambiare stile).
POS_FIELDS = {"tower_w_ally", "tower_w_dist", "tower_w_minion", "siege_from", "siege_my_hp", "core_from", "u_siege_k",
              "u_w_siege", "u_siege_bias", "defend_max_dist", "defend_enemy_r", "lane_leash", "lane_leash_early", "early_time"}
FIELDS = None      # None = tutto lo spazio; altrimenti insieme di campi ammessi (--fields pos)


def layout(groups):
    """[(gruppo, campo, lo, hi)] nell'ordine del vettore."""
    out = []
    for g in groups:
        sp = dict(SPACE)
        if g != "jungler": sp.update(LANE_ONLY)
        sp.update(EXTRA.get(g, {}))
        out += [(g, k, lo, hi) for k, (lo, hi) in sp.items() if FIELDS is None or k in FIELDS]
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
_PHI = None      # (pesi di phi_fit, orizzonte in s) quando la fitness e' troncata: score = 2*Phi - 1


def _init(max_time, early_stop=None, vision_stride=1, minion_stride=1, phi=None):
    global _PHI
    import tier_sim
    _PHI = phi
    tier_sim._init_worker(False, max_time, True, None, early_stop, vision_stride, minion_stride)


def phi_value(feat, side, t, W):
    """Phi(s,t) = P(vittoria della squadra `side`): stesse feature e stessa normalizzazione di tools/phi_fit.py."""
    names, w = W["names"], W["w"]; n = len(names); z = w[-1]
    for i, k in enumerate(names):
        a, b = feat[side][k], feat[1 - side][k]
        x = (a - b) / (a + b + (1000.0 if k == "worth" else 0.5 if k == "core" else 3.0))
        z += w[i] * x + w[n + i] * x * t / W["cap"]
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


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
    if _PHI is not None:       # orizzonte troncato: la fitness e' Phi all'istante di arresto (2*Phi-1 in [-1, 1])
        score = 2.0 * phi_value(r["phi_feat"], side, r["time"], _PHI) - 1.0
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
    ap.add_argument("--seeds", type=int, default=None,
                    help="semi per generazione (x2 lati; default 4; con --resume sostituisce quello salvato)")
    ap.add_argument("--minutes", type=float, default=14.0, help="durata massima di gioco")
    ap.add_argument("--sigma", type=float, default=0.2)
    ap.add_argument("--groups", default=",".join(GROUPS))
    ap.add_argument("--opp", choices=["base", "best"], default="base")
    ap.add_argument("--opp-every", type=int, default=5, help="con --opp best: ogni N generazioni")
    ap.add_argument("--horizon", type=float, default=0.0, help="secondi: gioca solo fino a qui e valuta Phi (richiede --phi)")
    ap.add_argument("--phi", default=None, help="pesi di Phi (phi_fit *_weights.json)")
    ap.add_argument("--opp-file", default=None, help="con --resume: params.json del nuovo avversario (azzera il best)")
    ap.add_argument("--league", default=None,
                    help="json {nome: params}: ogni seme gioca contro un avversario della lega (a rotazione, uguale per tutti i candidati)")
    ap.add_argument("--fields", choices=["all", "pos"], default="all",
                    help="pos = solo posizionamento/macro (exploiter: lo stile non cambia)")
    ap.add_argument("--opp-fixed", default=None, help="params.json dell'avversario fisso (partenza nuova, non solo con --resume)")
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
    global FIELDS
    FIELDS = POS_FIELDS if a.fields == "pos" else None

    out = ROOT / "tools" / "cma_out" / a.run
    out.mkdir(parents=True, exist_ok=True)
    state_f, log_f, best_f = out / "state.pkl", out / "log.jsonl", out / "best.json"

    if a.resume and state_f.exists():
        st = pickle.loads(state_f.read_bytes())
        es, lay, gen, opp, best = st["es"], st["lay"], st["gen"], st["opp"], st["best"]
        a.minutes, a.seed_base = st["minutes"], st["seed_base"]
        a.seeds = a.seeds or st["seeds"]
        if a.opp_file:  # nuovo avversario fisso (es. la gen 30): il best precedente non e' piu' confrontabile
            opp = json.loads(Path(a.opp_file).read_text())
            best = {"f": None, "params": None, "gen": None}
        print(f"ripresa da generazione {gen}")
    else:
        a.seeds = a.seeds or 4
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
        if a.opp_fixed:
            opp = json.loads(Path(a.opp_fixed).read_text())
        print(f"d={d} popsize={es.popsize} diagonale={d > 40}")

    os.environ.setdefault("PYTHONHASHSEED", "0")
    from tier_sim import make_jobs

    league = json.loads(Path(a.league).read_text()) if a.league else None
    lnames = list(league) if league else None
    phi = None
    if a.horizon:                      # fitness troncata: niente stop anticipato, la partita finisce all'orizzonte
        phi = json.loads(Path(a.phi).read_text()); a.early_stop = 0.0; a.minutes = a.horizon / 60.0
    with mp.get_context("spawn").Pool(a.workers, initializer=_init,
                                      initargs=(a.minutes * 60.0,
                                                {"threshold": a.early_stop} if a.early_stop else None,
                                                a.vision_stride, a.minion_stride, phi)) as pool:
        while gen < a.gens and not es.stop():
            t0 = time.time()
            xs = es.ask()
            cands = [decode(lay, x) for x in xs]
            jobs = make_jobs(a.seeds, a.seed_base + gen)       # stessi semi per tutti
            tasks, owner, otag = [], [], []
            for ci, c in enumerate(cands):
                for ji, job in enumerate(jobs):
                    on = lnames[(ji + gen) % len(lnames)] if lnames else None
                    for side in (0, 1):
                        tasks.append((job, side, c, league[on] if lnames else opp))
                        owner.append(ci); otag.append(on)
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
                   "best_ever": round(best["f"], 4), "opp": "lega" if lnames else ("base" if opp == BASE_PARAMS else "best")}
            if lnames:                 # vittorie e punteggio medio di tutta la popolazione per avversario
                rec["by_opp"] = {n: {"win": round(sum(r["win"] for r, o in zip(res, otag) if o == n) / max(1, otag.count(n)), 3),
                                     "score": round(sum(r["score"] for r, o in zip(res, otag) if o == n) / max(1, otag.count(n)), 3)}
                                 for n in lnames}
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
