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

# Quanti Pokemon in ogni tier, dal piu' forte (S) al piu' scarso (D): 
TIER_SIZES = [("S", 3), ("A", 5), ("B", 7), ("C", 6), ("D", 4)]   # 25 in tutto
MIN_DUEL = 6        # partite minime contro un avversario per citarlo
MIN_FORM = 3        # partite minime per classificare una forma
TYPE_WEIGHT = 0.08  # correzione per la "fortuna di tipo" degli avversari affrontati

# Tutti i ruoli contano anche CC, danno assorbito e assist (un combattente con tanti CC
# sale, un tank col danno inflitto basso non scende): cambia solo quanto pesano.
ROLE_WEIGHTS = {
    "tank": {"winrate": .30, "kp": .10, "taken": .16, "cc": .14, "assists": .05, "deaths_inv": .08,
             "dmg": .05, "level": .04, "sdmg": .04, "cs": .04},
    "supporto": {"winrate": .30, "kp": .14, "assists": .14, "cc": .12, "support": .10,
                 "deaths_inv": .08, "taken": .04, "level": .04, "dmg": .04},
    "mago": {"winrate": .30, "kp": .12, "dmg": .20, "kda": .10, "cc": .08, "assists": .04,
             "taken": .03, "deaths_inv": .05, "level": .04, "sdmg": .02, "cs": .02},
    "tiratore": {"winrate": .30, "kp": .12, "dmg": .20, "kda": .10, "cc": .08, "assists": .04,
                 "taken": .03, "deaths_inv": .05, "level": .04, "sdmg": .02, "cs": .02},
    "assassino": {"winrate": .30, "kp": .16, "kda": .14, "dmg": .14, "cc": .08, "assists": .05,
                  "deaths_inv": .04, "taken": .02, "level": .04, "sdmg": .02, "cs": .01},
    "combattente": {"winrate": .30, "kp": .14, "dmg": .12, "kda": .10, "cc": .12, "taken": .08,
                    "assists": .05, "deaths_inv": .03, "level": .04, "sdmg": .02},
}
METRIC_NAME = {"winrate": "Vittorie (corrette)", "level": "Livello", "taken": "Danno assorbito",
               "cc": "Controllo (CC)", "assists": "Assist", "deaths_inv": "Poche morti",
               "dmg": "Danno inflitto", "support": "Cure/scudi", "kda": "K/D (con assist)",
               "kp": "Partecipazione alle uccisioni", "sdmg": "Danno alle torri", "cs": "Minion"}
# Statistiche mostrate nella scheda, per ruolo (oltre a Vittorie e Livello).
ROLE_STATS = {
    "tank": ["taken", "cc", "kp", "deaths"],
    "supporto": ["assists", "cc", "support", "kp"],
    "mago": ["kda", "dmg", "cc", "kp"],
    "tiratore": ["kda", "dmg", "cc", "kp"],
    "assassino": ["kda", "dmg", "cc", "kp"],
    "combattente": ["kda", "dmg", "cc", "kp"],
}
JUNGLERS = ["Nincada", "Sneasel", "Teddiursa", "Swinub", "Totodile"]
SUPPORT_NAMES = {"Spiritomb", "Duraludon", "Rookidee", "Flabébé"}
SHORT_GAME = 15 * 60.0   # secondi: sotto = partita "breve" (decisa presto), sopra = "lunga"
MIN_SPLIT = 8            # partite minime per mostrare le vittorie brevi/lunghe
# Informazioni EXTRA (non entrano nel punteggio): (chiave, etichetta, formato, piu' alto = meglio).
EXTRA_GROUPS = [
    ("Primi 10 minuti", [
        ("gold10", "Oro a 10'", "{:.0f}", True), ("cs10", "Farm a 10'", "{:.0f}", True),
        ("kda10", "K/D+A a 10'", "{:.2f}", True), ("dmg10", "Danno a 10'", "{:.0f}", True),
        ("fb", "Primo sangue", "{:.0%}", True)]),
    ("Combattimento", [
        ("dpm", "Danno al minuto", "{:.0f}", True), ("dmg_share", "% danno squadra", "{:.0%}", True),
        ("taken_share", "% danno subito", "{:.0%}", True), ("maxhit", "Colpo più forte", "{:.0f}", True),
        ("best_streak", "Serie uccisioni", "{:.1f}", True), ("selfheal", "Auto-cura", "{:.0f}", True)]),
    ("Danno per bersaglio", [
        ("dmg", "Danno ai nemici", "{:.0f}", True), ("dmg_minion", "Danno ai minion", "{:.0f}", True),
        ("dmg_wild", "Danno ai neutrali", "{:.0f}", True), ("sdmg", "Danno alle torri", "{:.0f}", True),
        ("enemy_pct", "% danno ai nemici", "{:.0%}", True)]),
    ("Rischio e tempi", [
        ("dead_pct", "Tempo da KO", "{:.0%}", False), ("tower_deaths", "Morti da torre", "{:.2f}", False),
        ("wr_short", "Vittorie < 15'", "{:.0%}", True), ("wr_long", "Vittorie ≥ 15'", "{:.0%}", True)]),
]
FORM_RULE = {"Sneasler": "se è il jungler della squadra", "Weavile": "se gioca in lane",
             "Poliwrath": "se in squadra c'è già un supporto",
             "Politoad": "se è lui il supporto della squadra",
             "Sylveon": "se è lui il supporto della squadra"}
FORM_RULE_DEFAULT = {"Eevee": "se in squadra c'è già un supporto"}


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
        "camps": s("camps") / n, "kills": s("kills") / n, "deaths": s("deaths") / n,
        "assists": s("assists") / n, "dmg": s("dmg") / n, "taken": s("taken") / n,
        "level": s("level") / n, "cc": s("cc") / n, "support": s("support") / n,
        "kp": s("kp") / n, "sdmg": s("sdmg") / n, "cs": s("cs") / n, "towers": s("towers") / n,
        "dmg_minion": s("dmg_minion") / n, "dmg_wild": s("dmg_wild") / n,
        "legend": s("legend") / n, "smites": s("smites") / n,
        "kda": (s("kills") + s("assists")) / max(1.0, s("deaths")),
        "reach8": len(t8) / n, "t8": (sum(t8) / len(t8)) if t8 else None,
    }


def winrate_of(units: list) -> float:
    return sum(1 for u in units if u["won"]) / max(1, len(units))


def main():
    newest = ROOT / "tools" / "tier_matches_5v5_b.jsonl"
    srcs = ([Path(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else
            [newest if newest.exists() else ROOT / "tools" / "tier_matches_5v5.jsonl"])
    matches = [json.loads(l) for src in srcs for l in src.read_text(encoding="utf-8").splitlines()
               if l.strip()]
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
        tk = {t: max(1, sum(u["kills"] for u in m["units"] if u["team"] == t)) for t in (0, 1)}
        td = {t: max(1.0, sum(u["dmg"] for u in m["units"] if u["team"] == t)) for t in (0, 1)}
        tt = {t: max(1.0, sum(u["taken"] for u in m["units"] if u["team"] == t)) for t in (0, 1)}
        mins = max(1.0, m["time"] / 60.0)
        for u in m["units"]:
            tot_d = u["dmg"] + u.get("dmg_minion", 0) + u.get("dmg_wild", 0) + u.get("sdmg", 0)
            u = dict(u, won=(u["team"] == m["winner"]),
                     my_sup=bool(m["support"][u["team"]]), opp_sup=bool(m["support"][1 - u["team"]]),
                     enemy_pct=(u["dmg"] / tot_d if "dmg_minion" in u and tot_d > 0 else None),
                     kp=(u["kills"] + u["assists"]) / tk[u["team"]],
                     dmg_share=u["dmg"] / td[u["team"]], taken_share=u["taken"] / tt[u["team"]],
                     dpm=u["dmg"] / mins, dead_pct=min(1.0, u.get("dead_time", 0.0) / max(1.0, m["time"])),
                     short=m["time"] < SHORT_GAME)
            if "gold10" in u:
                u["kda10"] = (u["kills10"] + u["assists10"]) / max(1.0, u["deaths10"])
            rows[u["name"]].append(u)
        for a in m["units"]:
            for b in m["units"]:
                if a["team"] != b["team"]:
                    rec = duel[a["name"]][b["name"]]
                    rec[1] += 1
                    rec[0] += 1 if a["team"] == m["winner"] else 0

    # Vittorie CORRETTE sul contesto: chi gioca senza support vince di piu perche lo spareggio
    # a tempo premia il danno, quindi ogni partita si confronta con la quota di vittorie
    # attesa per (squadra con/senza support, avversario con/senza support).
    allu = [u for n_ in names for u in rows[n_]]
    ctx_n, ctx_w, own_n, own_w = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    for u in allu:
        ctx_n[u["my_sup"], u["opp_sup"]] += 1
        ctx_w[u["my_sup"], u["opp_sup"]] += u["won"]
        own_n[u["my_sup"]] += 1
        own_w[u["my_sup"]] += u["won"]

    def expected_wr(u):
        k = (u["my_sup"], u["opp_sup"])
        if ctx_n[k] >= 40:
            return ctx_w[k] / ctx_n[k]
        return own_w[u["my_sup"]] / max(1, own_n[u["my_sup"]])

    def winrate_adj(units):
        """0,5 + (vittorie - vittorie attese per il contesto), in media sulle partite."""
        if not units:
            return 0.5
        return 0.5 + sum(u["won"] - expected_wr(u) for u in units) / len(units)

    per = {}
    for n in names:
        a = aggregate(rows[n])
        a["winrate_raw"] = winrate_of(rows[n])
        a["winrate"] = winrate_adj(rows[n])
        a["deaths_inv"] = -a["deaths"]
        per[n] = a

    def extra_of(units):
        """Medie delle informazioni extra su un insieme di righe (None se non ci sono dati)."""
        res = {}
        for k in ("gold10", "cs10", "kda10", "dmg10", "fb", "dpm", "dmg_share", "taken_share",
                  "maxhit", "best_streak", "selfheal", "dead_pct", "tower_deaths",
                  "dmg", "dmg_minion", "dmg_wild", "sdmg", "enemy_pct"):
            v = [u[k] for u in units if u.get(k) is not None]
            res[k] = sum(v) / len(v) if len(v) >= max(3, len(units) // 2) else None
        for k, grp in (("wr_short", [u for u in units if u["short"]]),
                       ("wr_long", [u for u in units if not u["short"]])):
            res[k] = winrate_of(grp) if len(grp) >= MIN_SPLIT else None
        return res
    extra = {n: extra_of(rows[n]) for n in names}

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
                     "support", "winrate", "reach8", "kp", "sdmg", "cs")}
    t8s = [per[n]["t8"] for n in names if per[n]["t8"]]
    avg["t8"] = sum(t8s) / len(t8s) if t8s else None

    def stat_box(key, p):
        a = avg
        return {
            "winrate": ("Vittorie (corr.)", f"{p['winrate'] * 100:.0f}%", f"{a['winrate'] * 100:.0f}%"),
            "kda": ("K/D+assist", f"{p['kda']:.2f}", f"{a['kda']:.2f}"),
            "dmg": ("Danno", f"{p['dmg']:.0f}", f"{a['dmg']:.0f}"),
            "taken": ("Danno subito", f"{p['taken']:.0f}", f"{a['taken']:.0f}"),
            "kills": ("Uccisioni", f"{p['kills']:.1f}", f"{a['kills']:.1f}"),
            "deaths": ("Morti", f"{p['deaths']:.1f}", f"{a['deaths']:.1f}"),
            "assists": ("Assist", f"{p['assists']:.1f}", f"{a['assists']:.1f}"),
            "cc": ("CC (s)", f"{p['cc']:.0f}", f"{a['cc']:.0f}"),
            "support": ("Cure/scudi", f"{p['support']:.0f}", f"{a['support']:.0f}"),
            "level": ("Livello", f"{p['level']:.1f}", f"{a['level']:.1f}"),
            "kp": ("Partec. kill", f"{p['kp'] * 100:.0f}%", f"{a['kp'] * 100:.0f}%"),
        }[key]

    out = []
    for pos, n in enumerate(order, 1):
        p, d = per[n], defs[n]
        role = role_key(n)
        weights = ROLE_WEIGHTS[role]
        rk = {k: rank_of({m: per[m][k] for m in names}, n) for k in METRIC_NAME}

        phrase = {
            "winrate": (f"vince più del previsto: {p['winrate'] * 100:.0f}% corretto sul contesto "
                        f"(grezzo {p['winrate_raw'] * 100:.0f}%)",
                        f"vince meno del previsto: {p['winrate'] * 100:.0f}% corretto sul contesto "
                        f"(grezzo {p['winrate_raw'] * 100:.0f}%)"),
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
            "kp": (f"è dentro a molte uccisioni della squadra: {p['kp'] * 100:.0f}% (media {avg['kp'] * 100:.0f}%)",
                   f"partecipa a poche uccisioni della squadra: {p['kp'] * 100:.0f}% (media {avg['kp'] * 100:.0f}%)"),
            "sdmg": (f"butta giù le torri: {p['sdmg']:.0f} danno a partita (media {avg['sdmg']:.0f})",
                     f"fa poco danno alle torri: {p['sdmg']:.0f} a partita (media {avg['sdmg']:.0f})"),
            "cs": (f"fa molti minion: {p['cs']:.0f} a partita (media {avg['cs']:.0f})",
                   f"fa pochi minion: {p['cs']:.0f} a partita (media {avg['cs']:.0f})"),
            "kda": (f"uccide e assiste molto più di quanto muoia (K/D+assist {p['kda']:.2f}, media {avg['kda']:.2f})",
                    f"muore più di quanto uccida o assista (K/D+assist {p['kda']:.2f}, media {avg['kda']:.2f})"),
        }
        pros, cons = [], []
        for k in weights:
            r = rk[k]
            if k == "support" and avg["support"] < 1:
                continue
            tag = f" ({r}º su {len(names)})"
            if r <= round(len(names) * 0.25):
                pros.append(phrase[k][0] + tag)
            elif r > len(names) - round(len(names) * 0.25):
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
                a["winrate"] = winrate_adj(us)
                a["deaths_inv"] = -a["deaths"]
                ftypes = us[0].get("types") or list(d.types)
                forms.append({"name": f, "games": len(us), "score": round(score_of(role, a), 3),
                              "winrate": round(winrate_of(us), 3), "kda": round(a["kda"], 2),
                              "dmg": round(a["dmg"]), "assists": round(a["assists"], 1),
                              "cc": round(a["cc"]), "types": ftypes,
                              "rule": FORM_RULE.get(f, FORM_RULE_DEFAULT.get(d.name, "")),
                              "share": round(len(us) / max(1, evolved), 3)})
            forms.sort(key=lambda f: (f["score"] is None, -(f["score"] or 0)))
            for k, f in enumerate(forms, 1):
                f["rank"] = k

        def ctx(units):
            a = aggregate(units)
            return {"games": len(units), "winrate": round(winrate_of(units), 3),
                    "kda": round(a["kda"], 2), "camps": round(a["camps"], 1),
                    "smites": round(a["smites"], 1), "legend": round(a["legend"], 2)}
        rs = rows[n]
        context = {}
        jg = [u for u in rs if u["jungle"]]
        ln = [u for u in rs if not u["jungle"]]
        if jg:
            context["jungler"] = ctx(jg)
        if ln:
            context["laner"] = ctx(ln)
        if n not in SUPPORT_NAMES:
            ws = [u for u in rs if u["with_support"]]
            ns = [u for u in rs if not u["with_support"]]
            if ws:
                context["with_support"] = ctx(ws)
            if ns:
                context["no_support"] = ctx(ns)
        sp = [u for u in rs if u.get("is_support")]
        if sp:
            context["as_support"] = ctx(sp)
        lanes = {}
        for u in rs:
            lanes.setdefault(u["lane"], []).append(u)
        context["lanes"] = {k: {"games": len(v), "winrate": round(winrate_of(v), 3)}
                            for k, v in sorted(lanes.items())}

        head = {"S": "È tra i più forti del roster", "A": "È sopra la media",
                "B": "È nella fascia di mezzo", "C": "È sotto la media",
                "D": "È tra i più deboli del roster"}[tiers[n]]
        stats = [stat_box(k, p) for k in ["winrate"] + ROLE_STATS[role] + ["level"]]
        extra_out = []
        for gname, items in EXTRA_GROUPS:
            cells = []
            for k, label, fmt, hi in items:
                vals = {m: extra[m][k] for m in names if extra[m][k] is not None}
                v = extra[n][k]
                if v is None or len(vals) < 4:
                    continue
                rank_ = rank_of(vals, n, hi)
                avg_ = sum(vals.values()) / len(vals)
                q = max(1, round(len(vals) * 0.25))
                cells.append({"label": label, "value": fmt.format(v), "avg": fmt.format(avg_),
                              "rank": rank_, "of": len(vals),
                              "good": 1 if rank_ <= q else -1 if rank_ > len(vals) - q else 0})
            if cells:
                extra_out.append({"group": gname, "cells": cells})
        out.append({
            "name": n, "pos": pos, "tier": tiers[n], "score": round(score[n], 3),
            "role": d.role, "types": list(d.types), "passive": d.passive,
            "games": p["games"], "winrate": round(p["winrate_raw"], 4),
            "winrate_adj": round(p["winrate"], 4),
            "stats": [{"label": a, "value": b, "avg": c} for a, b, c in stats],
            "ranks": rk, "summary": f"{head} (posizione {pos} su {len(names)}, tier {tiers[n]}).",
            "weights": {METRIC_NAME[k]: v for k, v in weights.items()},
            "pros": pros, "cons": cons, "best": best, "worst": worst,
            "types_info": types_info, "forms": forms, "context": context,
            "extra": extra_out,
        })

    # Dati sull'insieme delle partite (pagina "Dati partite").
    def team_rows(flag):
        out_, tot_, win_ = 0, 0, 0
        for m in matches:
            for t in (0, 1):
                if m["support"][t] == flag:
                    tot_ += 1
                    win_ += 1 if m["winner"] == t else 0
        return {"games": tot_, "winrate": round(win_ / max(1, tot_), 3)}
    jung = {}
    for n in JUNGLERS:
        js = [u for u in rows[n] if u["jungle"]]
        if js:
            a = aggregate(js)
            jung[n] = {"games": len(js), "winrate": round(winrate_of(js), 3),
                       "camps": round(a["camps"], 1), "legend": round(a["legend"], 2),
                       "smites": round(a["smites"], 1), "kills": round(a["kills"], 1),
                       "assists": round(a["assists"], 1), "level": round(a["level"], 1),
                       "t5": round(sum(u["t5"] for u in js if u.get("t5")) /
                                   max(1, sum(1 for u in js if u.get("t5"))), 0)}
    forms_all = {}
    finals_all = set()
    for d_ in defs.values():
        top = max((e.get("stage", 0) for e in d_.evolutions), default=0)
        finals_all |= {e["name"] for e in d_.evolutions if e.get("stage", 0) == top}
    for n in names:
        for u in rows[n]:
            if u.get("plan") and u["final_name"] in finals_all:
                rec = forms_all.setdefault(u["final_name"], [0, 0])
                rec[0] += 1 if u["won"] else 0
                rec[1] += 1
    match_data = {
        "matches": len(matches),
        "minutes": round(sum(m["time"] for m in matches) / len(matches) / 60, 1),
        "decided_by_core": sum(1 for m in matches if not m["timeout"]),
        "open_nexus": sum(1 for m in matches if m.get("open_nexus")),
        "blue_wins": round(sum(1 for m in matches if m["winner"] == 0) / len(matches), 3),
        "teams_with_support": team_rows(True), "teams_without_support": team_rows(False),
        "junglers": jung,
        "forced_forms": {k: {"games": v[1], "winrate": round(v[0] / max(1, v[1]), 3)}
                         for k, v in sorted(forms_all.items())},
        "smites": round(sum(u.get("smites", 0) for m in matches for u in m["units"]) / len(matches), 1),
    }
    # Dati extra sull'insieme: primo sangue, durata, uccisioni e torri per partita.
    fbm = [(next((u["team"] for u in m["units"] if u.get("fb")), None), m["winner"]) for m in matches]
    fbm = [(a, b) for a, b in fbm if a is not None]
    short = [m for m in matches if m["time"] < SHORT_GAME]
    match_data["first_blood_wins"] = {"games": len(fbm), "winrate": round(
        sum(1 for a, b in fbm if a == b) / max(1, len(fbm)), 3)}
    match_data["short_games"] = {"games": len(short), "minutes": round(
        sum(m["time"] for m in short) / max(1, len(short)) / 60, 1)}
    match_data["kills_per_match"] = round(sum(u["kills"] for m in matches for u in m["units"])
                                          / len(matches), 1)
    match_data["towers_per_match"] = round(sum(u.get("towers", 0) for m in matches
                                               for u in m["units"]) / len(matches), 1)
    match_data["new_fields"] = sum(1 for m in matches if "gold10" in m["units"][0])

    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "tier_developer.json"
    dst.write_text(json.dumps({
        "matches": len(matches), "minutes": round(sum(m["time"] for m in matches) / len(matches) / 60, 1),
        "match_data": match_data, "map": "5v5", "avg_winrate": round(avg["winrate"], 4), "reach8": round(avg["reach8"], 3),
        "list": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(matches)} partite -> {dst}")
    for e in out:
        print(f"{e['pos']:>2} {e['tier']} {e['name']:<11} {e['role']:<11} wr {e['winrate'] * 100:3.0f}% (corr {e['winrate_adj'] * 100:3.0f}%)  "
              + "  ".join(f"{s['label']} {s['value']}" for s in e["stats"][1:-1]))


if __name__ == "__main__":
    main()
