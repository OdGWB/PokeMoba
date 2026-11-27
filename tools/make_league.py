"""Scrive tools/cma_out/league.json: gli avversari della lega per la CMA (--league).
  base   = IA a punteggio di partenza
  g10    = media della run wide1 a gen 10 (congelata)
  split  = split-pusher fatto a mano: ignora il numero di alleati/nemici, assedia presto la torre vicina,
           non va a difendere, guinzaglio di lane largo -> punisce chi si ammassa a mid
  difesa = difensore fatto a mano: va a difendere da lontano, assedia/core tardi -> punisce chi spinge sparso
    python tools/make_league.py"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; CO = ROOT / "tools" / "cma_out"
GROUPS = ["jungler", "support", "tiratore", "mago", "combattente", "assassino", "tank"]
BASE = {"*": {"utility": True}}
SPLIT = dict(tower_w_ally=0.0, tower_w_dist=0.15, tower_w_minion=6.0, siege_from=180.0, siege_my_hp=0.4, core_from=240.0,
             u_siege_k=0.3, u_w_siege=1.4, u_siege_bias=0.3, defend_max_dist=8.0, defend_enemy_r=3.0,
             lane_leash=24.0, lane_leash_early=10.0, early_time=90.0)
DIFE = dict(tower_w_ally=6.0, defend_max_dist=40.0, defend_enemy_r=10.0, siege_from=420.0, core_from=400.0,
            u_w_siege=0.4, u_siege_k=0.1, lane_leash=10.0, lane_leash_early=6.0)
def team(extra):
    d = {"*": {"utility": True}}
    for g in GROUPS:
        d[g] = dict(extra)
        if g == "jungler":
            for k in ("lane_leash", "lane_leash_early", "early_time"): d[g].pop(k, None)
    return d
L = {"base": BASE, "g10": json.loads((CO / "w1_g10_mean.json").read_text()), "split": team(SPLIT), "difesa": team(DIFE)}
(CO / "league.json").write_text(json.dumps(L, indent=1)); print("ok", list(L))
