"""Dalle partite di tools/tier_sim.py ricava la tier list Developer.

Scrive data/tier_developer.json: per ogni Pokemon posizione (1 = il piu' forte),
tier, statistiche, classifica delle forme, tipi, scontri diretti e le ragioni in
italiano. La schermata Developer (game/scenes/tier_scene.py) legge solo questo file.

Il punteggio dipende dal RUOLO: un tank non si giudica dal danno ma da quanto ne
assorbe e dai controlli; un supporto da assist, controlli e cure/scudi; gli altri
da danno e K/D. La vittoria di squadra pesa sempre il 40%.

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
MIN_FORM = 3        # partite minime per classificare una forma
TYPE_WEIGHT = 0.08  # correzione per la "fortuna di tipo" degli avversari affrontati

_BASE = {"winrate": 0.40, "level": 0.05}
ROLE_WEIGHTS = {
    "tank": {**_BASE, "taken": 0.20, "cc": 0.10, "assists": 0.10, "deaths_inv": 0.10, "dmg": 0.05},
    "supporto": {**_BASE, "assists": 0.20, "cc": 0.15, "support": 0.10, "deaths_inv": 0.10},
    "mago": {**_BASE, "dmg": 0.25, "kda": 0.20, "assists": 0.10},
    "tiratore": {**_BASE, "dmg": 0.25, "kda": 0.20, "assists": 0.10},
    "assassino": {**_BASE, "kda": 0.25, "dmg": 0.20, "assists": 0.10},
    "combattente": {**_BASE, "dmg": 0.20, "kda": 0.15, "taken": 0.10, "assists": 0.10},
}
METRIC_NAME = {"winrate": "Vittorie", "level": "Livello", "taken": "Danno assorbito",
               "cc": "Controllo (CC)", "assists": "Assist", "deaths_inv": "Poche morti",
               "dmg": "Danno inflitto", "support": "Cure/scudi", "kda": "K/D (con assist)"}
# Statistiche mostrate nella scheda, per ruolo (oltre a Vittorie e Livello).
ROLE_STATS = {
    "tank": ["taken", "cc", "assists", "deaths"],
    "supporto": ["assists", "cc", "support", "deaths"],
    "mago": ["kda", "dmg", "kills", "deaths"],
    "tiratore": ["kda", "dmg", "kills", "deaths"],
    "assassino": ["kda", "dmg", "kills", "deaths"],
    "combattente": ["kda", "dmg", "taken", "deaths"],
}


def fmt_time(sec: float) -> str:
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def zscores(vals: dict) -> dict:
    xs = list(vals.values())
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
    if sd < 1e-9:
        return {k: 0.0 for k in vals}
    return {k: max(-2.5, min(2.5, (v - m) / sd)) for k, v in vals.items()}


def rank_of(vals: dict, key, higher_better=True) -> int:
    order = sorted(vals, key=lambda k: vals[k], reverse=higher_better)
    return order.index(key) + 1


def type_mult(chart: dict, att: list, dfn: list) -> float:
    """Moltiplicatore migliore tra i tipi dell'attaccante contro i tipi del difensore."""
    best = 0.0
    for a in att:
        m = 1.0
        for d in dfn:
            m *= chart.get(a, {}).get(d, 1.0)
        best = max(best, m)
    return best or 1.0


def aggregate(units: list) -> dict:
    """Medie per partita di un insieme di righe-unita'."""
    n = max(1, len(units))
    s = lambda k: sum(u.get(k, 0) or 0 for u in units)   # noqa: E731
    t8 = [u["t8"] for u in units if u.get("t8") is not None]
    return {
        "games": len(units),
        "kills": s("kills") / n, "deaths": s("deaths") / n, "assists": s("assists") / n,
        "dmg": s("dmg") / n, "taken": s("taken") / n, "level": s("level") / n,
        "cc": s("cc") / n, "support": s("support") / n,
        "kda": (s("kills") + s("assists")) / max(1.0, s("deaths")),
        "reach8": len(t8) / n, "t8": (sum(t8) / len(t8)) if t8 else None,
    }


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "tier_matches.jsonl"
    matches = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    chart = json.loads((ROOT / "data" / "types.json").read_text(encoding="utf-8"))
    chart = {k: v for k, v in chart.items() if not k.startswith("_")}
    defs = {}
    for rel in config.ROSTER:
        d = load_pokemon_def(str(ROOT / rel))
        defs[d.name] = d
    names = list(defs)

    rows = defaultdict(list)                                    # nome -> righe-unita'
    duel = defaultdict(lambda: defaultdict(lambda: [0, 0]))     # a -> b -> [vittorie, partite]
    for m in matches:
        for u in m["units"]:
            u = dict(u, won=(u["team"] == m["winner"]))
            rows[u["name"]].append(u)
        for a in m["units"]:
            for b in m["units"]:
                if a["team"] != b["team"]:
                    rec = duel[a["name"]][b["name"]]
                    rec[1] += 1
                    rec[0] += 1 if a["team"] == m["winner"] else 0

    per = {}
    for n in names:
        a = aggregate(rows[n])
        a["winrate"] = sum(1 for u in rows[n] if u["won"]) / max(1, len(rows[n]))
        a["deaths_inv"] = -a["deaths"]
        per[n] = a

    # Vantaggio di tipo: intrinseco (contro tutto il roster) e "fortuna" nel campione.
    adv = {}
    for n in names:
        for o in names:
            if o != n:
                off = type_mult(chart, defs[n].types, defs[o].types)
                dfn = type_mult(chart, defs[o].types, defs[n].types)
                adv[n, o] = math.log2(off) - math.log2(dfn)
    luck = {}
    for n in names:
        faced = duel[n]
        tot = sum(t for _, t in faced.values())
        got = sum(adv[n, o] * t for o, (_, t) in faced.items()) / max(1, tot)
        intr = sum(adv[n, o] for o in names if o != n) / (len(names) - 1)
        luck[n] = got - intr
    zl = zscores(luck)

    z = {k: zscores({n: per[n][k] for n in names}) for k in METRIC_NAME}
    mean_sd = {}
    for k in METRIC_NAME:
        xs = [per[n][k] for n in names]
        mu = sum(xs) / len(xs)
        mean_sd[k] = (mu, math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs)) or 1.0)

    def score_of(role, vals, luck_z=0.0):
        w = ROLE_WEIGHTS.get(role, ROLE_WEIGHTS["combattente"])
        tot = 0.0
        for k, wt in w.items():
            mu, sd = mean_sd[k]
            tot += wt * max(-2.5, min(2.5, (vals[k] - mu) / sd))
        return tot - TYPE_WEIGHT * luck_z

    def role_key(n):
        r = defs[n].role.split()[0] if defs[n].role else ""
        return r if r in ROLE_WEIGHTS else "combattente"

    score = {n: score_of(role_key(n), per[n], zl[n]) for n in names}
    order = sorted(names, key=lambda n: score[n], reverse=True)
    tiers, i = {}, 0
    for t, size in TIER_SIZES:
        for n in order[i:i + size]:
            tiers[n] = t
        i += size

    avg = {k: sum(per[n][k] for n in names) / len(names)
           for k in ("kills", "deaths", "dmg", "taken", "level", "kda", "assists", "cc",
                     "support", "winrate", "reach8")}
    t8s = [per[n]["t8"] for n in names if per[n]["t8"]]
    avg["t8"] = sum(t8s) / len(t8s) if t8s else None

    def stat_box(key, p):
        a = avg
        return {
            "winrate": ("Vittorie", f"{p['winrate'] * 100:.0f}%", f"{a['winrate'] * 100:.0f}%"),
            "kda": ("K/D+assist", f"{p['kda']:.2f}", f"{a['kda']:.2f}"),
            "dmg": ("Danno", f"{p['dmg']:.0f}", f"{a['dmg']:.0f}"),
            "taken": ("Danno subito", f"{p['taken']:.0f}", f"{a['taken']:.0f}"),
            "kills": ("Uccisioni", f"{p['kills']:.1f}", f"{a['kills']:.1f}"),
            "deaths": ("Morti", f"{p['deaths']:.1f}", f"{a['deaths']:.1f}"),
            "assists": ("Assist", f"{p['assists']:.1f}", f"{a['assists']:.1f}"),
            "cc": ("CC (s)", f"{p['cc']:.0f}", f"{a['cc']:.0f}"),
            "support": ("Cure/scudi", f"{p['support']:.0f}", f"{a['support']:.0f}"),
            "level": ("Livello", f"{p['level']:.1f}", f"{a['level']:.1f}"),
        }[key]

    out = []
    for pos, n in enumerate(order, 1):
        p, d = per[n], defs[n]
        role = role_key(n)
        weights = ROLE_WEIGHTS[role]
        rk = {k: rank_of({m: per[m][k] for m in names}, n) for k in METRIC_NAME}

        phrase = {
            "winrate": (f"vince molto: {p['winrate'] * 100:.0f}% delle partite",
                        f"vince poco: solo {p['winrate'] * 100:.0f}% delle partite"),
            "level": (f"sale di livello in fretta (liv. medio {p['level']:.1f})",
                      f"sale di livello piano (liv. medio {p['level']:.1f})"),
            "taken": (f"assorbe tantissimo danno: {p['taken']:.0f} a partita (media {avg['taken']:.0f})",
                      f"assorbe poco danno: {p['taken']:.0f} a partita (media {avg['taken']:.0f})"),
            "cc": (f"controlla molto i nemici: {p['cc']:.0f} s di CC a partita (media {avg['cc']:.0f})",
                   f"controlla poco i nemici: {p['cc']:.0f} s di CC a partita (media {avg['cc']:.0f})"),
            "assists": (f"fa tanti assist: {p['assists']:.1f} a partita (media {avg['assists']:.1f})",
                        f"pochi assist: {p['assists']:.1f} a partita (media {avg['assists']:.1f})"),
            "deaths_inv": (f"muore raramente: {p['deaths']:.1f} morti a partita (media {avg['deaths']:.1f})",
                           f"muore spesso: {p['deaths']:.1f} morti a partita (media {avg['deaths']:.1f})"),
            "dmg": (f"infligge tanto danno: {p['dmg']:.0f} a partita (media {avg['dmg']:.0f})",
                    f"infligge poco danno: {p['dmg']:.0f} a partita (media {avg['dmg']:.0f})"),
            "support": (f"cura/protegge molto gli alleati: {p['support']:.0f} a partita",
                        f"cura/protegge poco gli alleati: {p['support']:.0f} a partita"),
            "kda": (f"uccide e assiste molto più di quanto muoia (K/D+assist {p['kda']:.2f}, media {avg['kda']:.2f})",
                    f"muore più di quanto uccida o assista (K/D+assist {p['kda']:.2f}, media {avg['kda']:.2f})"),
        }
        pros, cons = [], []
        for k in weights:
            r = rk[k]
            if k == "support" and avg["support"] < 1:
                continue
            tag = f" ({r}º su 17)"
            if r <= 5:
                pros.append(phrase[k][0] + tag)
            elif r >= 13:
                cons.append(phrase[k][1] + tag)
        if p["t8"] is not None:
            msg = (f"arriva al liv. 8 nel {p['reach8'] * 100:.0f}% delle partite "
                   f"(in media dopo {fmt_time(p['t8'])}; media roster {avg['reach8'] * 100:.0f}%)")
            (pros if p["reach8"] >= avg["reach8"] * 1.1 else cons if p["reach8"] <= avg["reach8"] * 0.8
             else []).append(msg)
        if role == "tank" and rk["dmg"] >= 10:
            pros.append("ha poco danno, ma è normale per un tank: qui conta quanto assorbe e controlla")
        if not pros:
            pros.append("nessun punto di forza netto: nella media del gruppo")
        if not cons:
            cons.append("nessun punto debole netto")

        # Scontri diretti, con l'effetto dei tipi accanto.
        beats, loses = [], []
        for o, (w, tot) in duel[n].items():
            if tot >= MIN_DUEL:
                (beats if w / tot >= 0.5 else loses).append((w / tot, o, tot))
        beats.sort(reverse=True)
        loses.sort()

        def duel_row(r, o, t):
            off = type_mult(chart, d.types, defs[o].types)
            dfn = type_mult(chart, defs[o].types, d.types)
            return {"name": o, "winrate": r, "games": t, "off": off, "dfn": dfn}
        best = [duel_row(r, o, t) for r, o, t in beats[:3]]
        worst = [duel_row(r, o, t) for r, o, t in loses[:3]]

        strong = [o for o in names if o != n and type_mult(chart, d.types, defs[o].types) >= 2]
        weak = [o for o in names if o != n and type_mult(chart, defs[o].types, d.types) >= 2]
        resist = [o for o in names if o != n and type_mult(chart, defs[o].types, d.types) <= 0.5]
        types_info = {"types": list(d.types), "strong_vs": strong, "weak_to": weak,
                      "resists": resist,
                      "net": round(sum(adv[n, o] for o in names if o != n) / (len(names) - 1), 2),
                      "luck": round(luck[n], 2)}
        net = types_info["net"]
        if net >= 0.25:
            pros.append(f"i suoi tipi lo favoriscono contro il roster (vantaggio {net:+.2f})")
        elif net <= -0.25:
            cons.append(f"i suoi tipi lo svantaggiano contro il roster (vantaggio {net:+.2f})")

        # Classifica interna delle forme (solo per le linee con rami).
        forms = []
        evo = d.evolutions
        last_stage = max((e.get("stage", 0) for e in evo), default=0)
        finals = [e["name"] for e in evo if e.get("stage", 0) == last_stage]
        if len(finals) >= 2:
            by = defaultdict(list)
            for u in rows[n]:
                by[u["final_name"]].append(u)
            evolved = sum(len(by[f]) for f in finals)
            for f in finals:
                us = by.get(f, [])
                if len(us) < MIN_FORM:
                    forms.append({"name": f, "games": len(us), "score": None})
                    continue
                a = aggregate(us)
                a["winrate"] = sum(1 for u in us if u["won"]) / len(us)
                a["deaths_inv"] = -a["deaths"]
                ftypes = us[0].get("types") or list(d.types)
                forms.append({"name": f, "games": len(us), "score": round(score_of(role, a), 3),
                              "winrate": round(a["winrate"], 3), "kda": round(a["kda"], 2),
                              "dmg": round(a["dmg"]), "assists": round(a["assists"], 1),
                              "cc": round(a["cc"]), "types": ftypes,
                              "share": round(len(us) / max(1, evolved), 3)})
            forms.sort(key=lambda f: (f["score"] is None, -(f["score"] or 0)))
            for k, f in enumerate(forms, 1):
                f["rank"] = k

        head = {"S": "È tra i più forti del roster", "A": "È sopra la media",
                "B": "È nella fascia di mezzo", "C": "È sotto la media",
                "D": "È tra i più deboli del roster"}[tiers[n]]
        stats = [stat_box(k, p) for k in ["winrate"] + ROLE_STATS[role] + ["level"]]
        out.append({
            "name": n, "pos": pos, "tier": tiers[n], "score": round(score[n], 3),
            "role": d.role, "types": list(d.types), "passive": d.passive,
            "games": p["games"], "winrate": round(p["winrate"], 4),
            "stats": [{"label": a, "value": b, "avg": c} for a, b, c in stats],
            "ranks": rk, "summary": f"{head} (posizione {pos} su 17, tier {tiers[n]}).",
            "weights": {METRIC_NAME[k]: v for k, v in weights.items()},
            "pros": pros, "cons": cons, "best": best, "worst": worst,
            "types_info": types_info, "forms": forms,
        })

    dst = ROOT / "data" / "tier_developer.json"
    dst.write_text(json.dumps({
        "matches": len(matches), "minutes": round(sum(m["time"] for m in matches) / len(matches) / 60, 1),
        "avg_winrate": round(avg["winrate"], 4), "reach8": round(avg["reach8"], 3),
        "list": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(matches)} partite -> {dst}")
    for e in out:
        print(f"{e['pos']:>2} {e['tier']} {e['name']:<11} {e['role']:<11} wr {e['winrate'] * 100:3.0f}%  "
              + "  ".join(f"{s['label']} {s['value']}" for s in e["stats"][1:-1]))


if __name__ == "__main__":
    main()
