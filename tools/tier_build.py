"""Dalle partite di tools/tier_sim.py ricava la tier list Developer.

Scrive data/tier_developer.json: per ogni Pokemon posizione (1 = il piu' forte),
tier, statistiche, scontri diretti e le ragioni in italiano. La schermata
Developer (game/scenes/tier_scene.py) legge solo questo file.

    python tools/tier_build.py [tools/tier_matches.jsonl]
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from engine.content import load_pokemon_def  # noqa: E402

# Quanti Pokemon in ogni tier, dal piu' forte (S) al piu' scarso (D): 17 in tutto.
TIER_SIZES = [("S", 3), ("A", 4), ("B", 4), ("C", 3), ("D", 3)]
MIN_DUEL = 6        # partite minime contro un avversario per citarlo


def zscores(vals: dict) -> dict:
    xs = list(vals.values())
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs)) or 1.0
    return {k: (v - m) / sd for k, v in vals.items()}


def rank_of(vals: dict, key, higher_better=True) -> int:
    order = sorted(vals, key=lambda k: vals[k], reverse=higher_better)
    return order.index(key) + 1


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "tier_matches.jsonl"
    matches = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    defs = {}
    for rel in config.ROSTER:
        d = load_pokemon_def(str(ROOT / rel))
        defs[d.name] = d
    names = list(defs)

    g = defaultdict(lambda: defaultdict(float))
    duel = defaultdict(lambda: defaultdict(lambda: [0, 0]))     # a -> b -> [vittorie, partite]
    for m in matches:
        for u in m["units"]:
            s = g[u["name"]]
            s["games"] += 1
            s["wins"] += 1 if u["team"] == m["winner"] else 0
            for k in ("kills", "deaths", "dmg", "taken", "level"):
                s[k] += u[k]
            s["early_win"] += 1 if (u["team"] == m["winner"] and not m["timeout"]) else 0
        for a in m["units"]:
            for b in m["units"]:
                if a["team"] != b["team"]:
                    rec = duel[a["name"]][b["name"]]
                    rec[1] += 1
                    rec[0] += 1 if a["team"] == m["winner"] else 0

    per = {}
    for n in names:
        s = g[n]
        gm = max(1.0, s["games"])
        per[n] = {
            "games": int(s["games"]),
            "winrate": s["wins"] / gm,
            "kills": s["kills"] / gm, "deaths": s["deaths"] / gm,
            "kda": s["kills"] / max(1.0, s["deaths"]),
            "dmg": s["dmg"] / gm, "taken": s["taken"] / gm,
            "level": s["level"] / gm,
        }

    # Punteggio: la vittoria di squadra conta di piu', ma e' rumorosa (dipende dai
    # compagni), quindi si somma quanto il Pokemon pesa davvero nello scontro.
    wr = {n: per[n]["winrate"] for n in names}
    kda = {n: per[n]["kda"] for n in names}
    dmg = {n: per[n]["dmg"] for n in names}
    lvl = {n: per[n]["level"] for n in names}
    zw, zk, zd, zl = zscores(wr), zscores(kda), zscores(dmg), zscores(lvl)
    score = {n: 0.50 * zw[n] + 0.25 * zk[n] + 0.15 * zd[n] + 0.10 * zl[n] for n in names}
    order = sorted(names, key=lambda n: score[n], reverse=True)

    tiers, i = {}, 0
    for t, size in TIER_SIZES:
        for n in order[i:i + size]:
            tiers[n] = t
        i += size

    out = []
    avg_wr = sum(wr.values()) / len(wr)
    avg = {k: sum(per[n][k] for n in names) / len(names)
           for k in ("kills", "deaths", "dmg", "taken", "level", "kda")}
    for pos, n in enumerate(order, 1):
        p = per[n]
        d = defs[n]
        rk = {"winrate": rank_of(wr, n), "kda": rank_of(kda, n), "dmg": rank_of(dmg, n),
              "taken": rank_of({k: per[k]["taken"] for k in names}, n),
              "deaths": rank_of({k: per[k]["deaths"] for k in names}, n, False),
              "level": rank_of(lvl, n)}
        pros, cons = [], []
        if rk["winrate"] <= 5:
            pros.append(f"vince molto: {p['winrate'] * 100:.0f}% delle partite ({rk['winrate']}º su 17)")
        if rk["winrate"] >= 13:
            cons.append(f"vince poco: solo {p['winrate'] * 100:.0f}% delle partite ({rk['winrate']}º su 17)")
        if rk["kda"] <= 5:
            pros.append(f"fa molte più uccisioni che morti (K/D {p['kda']:.2f}, media {avg['kda']:.2f})")
        if rk["kda"] >= 13:
            cons.append(f"muore più di quanto uccida (K/D {p['kda']:.2f}, media {avg['kda']:.2f})")
        if rk["dmg"] <= 4:
            pros.append(f"infligge tanto danno: {p['dmg']:.0f} a partita (media {avg['dmg']:.0f})")
        if rk["dmg"] >= 14:
            cons.append(f"infligge poco danno: {p['dmg']:.0f} a partita (media {avg['dmg']:.0f})")
        if rk["deaths"] <= 4:
            pros.append(f"muore raramente: {p['deaths']:.1f} morti a partita (media {avg['deaths']:.1f})")
        if rk["deaths"] >= 14:
            cons.append(f"muore spesso: {p['deaths']:.1f} morti a partita (media {avg['deaths']:.1f})")
        if rk["level"] <= 4:
            pros.append(f"sale di livello in fretta (liv. medio {p['level']:.1f})")
        if rk["level"] >= 14:
            cons.append(f"sale di livello piano (liv. medio {p['level']:.1f})")
        if rk["taken"] <= 4:
            pros.append("regge i colpi: assorbe molto danno senza crollare")
        if not pros:
            pros.append("nessun punto di forza netto: nella media del gruppo")
        if not cons:
            cons.append("nessun punto debole netto")

        beats, loses = [], []
        for o, (w, tot) in duel[n].items():
            if tot >= MIN_DUEL:
                (beats if w / tot >= 0.5 else loses).append((w / tot, o, tot))
        beats.sort(reverse=True)
        loses.sort()
        best = [{"name": o, "winrate": r, "games": t} for r, o, t in beats[:3]]
        worst = [{"name": o, "winrate": r, "games": t} for r, o, t in loses[:3]]

        tier = tiers[n]
        head = {"S": "È tra i più forti del roster", "A": "È sopra la media",
                "B": "È nella fascia di mezzo", "C": "È sotto la media",
                "D": "È tra i più deboli del roster"}[tier]
        out.append({
            "name": n, "pos": pos, "tier": tier, "score": round(score[n], 3),
            "role": d.role, "types": list(d.types), "passive": d.passive,
            "games": p["games"], "winrate": round(p["winrate"], 4),
            "kills": round(p["kills"], 2), "deaths": round(p["deaths"], 2),
            "kda": round(p["kda"], 2), "dmg": round(p["dmg"]), "taken": round(p["taken"]),
            "level": round(p["level"], 2),
            "ranks": rk, "summary": f"{head} (posizione {pos} su 17, tier {tier}).",
            "pros": pros, "cons": cons, "best": best, "worst": worst,
        })

    dst = ROOT / "data" / "tier_developer.json"
    dst.write_text(json.dumps({
        "matches": len(matches), "avg_winrate": round(avg_wr, 4),
        "averages": {k: round(v, 2) for k, v in avg.items()},
        "timeouts": sum(1 for m in matches if m["timeout"]),
        "list": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(matches)} partite -> {dst}")
    for e in out:
        print(f"{e['pos']:>2} {e['tier']} {e['name']:<11} wr {e['winrate'] * 100:4.0f}%  "
              f"kda {e['kda']:.2f}  dmg {e['dmg']}  lv {e['level']}")


if __name__ == "__main__":
    main()
