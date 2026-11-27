"""Suite di analisi completa (md + png) da un json di suite_trace.py.
    python tools/suite_report.py tools/cma_out/st_g25_mean.json reports/suite_g25_mean "Gen 25 mean"
Produce <prefix>.md e: _phases.png, _heal.png, _entry.png, _roles_phase.png, _chars_cand.png, _chars_base.png.
Fasi: early 0-5', mid 5-10', late 10'+. Mappa normalizzata: base propria in basso a sinistra."""
import json, math, os, sys
from collections import defaultdict
os.environ["SDL_VIDEODRIVER"] = "dummy"
import numpy as np, pygame
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]
import config
from engine.content import load_pokemon_def
import tier_sim
pygame.init()

res = json.load(open(sys.argv[1])); pref = sys.argv[2]; title = sys.argv[3] if len(sys.argv) > 3 else "candidato"
os.makedirs(os.path.dirname(pref) or ".", exist_ok=True)
AIS = ("cand", "base"); COL = {"cand": (235, 140, 45), "base": (95, 150, 225)}
PH = [("early 0-5'", 0, 300), ("mid 5-10'", 300, 600), ("late 10'+", 600, 1e9)]
ROLES = ["jungler", "support", "tiratore", "mago", "combattente", "assassino", "tank"]
defs = {d.name: d for d in (load_pokemon_def(os.path.join(ROOT, rel)) for rel in config.ROSTER)}
def grp(name, jg):
    if jg: return "jungler"
    d = defs.get(name)
    if d is None: return "?"
    if d.role == "supporto" or name in tier_sim.SUPPORTS: return "support"
    return "mago" if d.role == "mago mobile" else d.role
phase_of = lambda t: 0 if t < 300 else 1 if t < 600 else 2

# ---------- unita' per partita ----------
for r in res:
    L = r["log"]; cs = {int(k): v for k, v in L["meta"]["cores"].items()}; r["cores"] = cs
    r["W"] = cs[0][0] + cs[1][0]
    jg = {(u["team"], u["name"]) for u in r["all"] if u["smites"] is not None}
    r["U"] = {}
    for k, d in L["all"].items():
        i = int(k)
        r["U"][i] = dict(id=i, team=d["team"], name=d["name"], ai="cand" if d["team"] == r["side"] else "base",
                         grp=grp(d["name"], (d["team"], d["name"]) in jg), p=d["p"], win=(r["winner"] == d["team"]))
    r["dur"] = r["time"]
def mirror(r, u, x, y):
    return (r["W"] - x, r["W"] - y) if u["team"] == 1 else (x, y)
def enemy_half(r, u, x, y):
    oc, ec = r["cores"][u["team"]], r["cores"][1 - u["team"]]
    return math.hypot(x - ec[0], y - ec[1]) < math.hypot(x - oc[0], y - oc[1])
def mins(r, ph):
    a, b = PH[ph][1], PH[ph][2]
    return max(0.0, min(r["dur"], b) - a) / 60.0

# ---------- PNG helpers ----------
F = lambda s: pygame.font.SysFont("consolas", s)
f11, f13, f16, f20 = F(11), F(13), F(16), F(20)
BG = (16, 18, 22); FG = (225, 228, 232); GR = (70, 74, 82)
def txt(s, t, pos, f=f13, c=FG): s.blit(f.render(str(t), True, c), pos)
def bars(s, rect, title_, labels, series, fmt="{:.0f}"):
    """series: {nome: [valori per etichetta]}; barre raggruppate."""
    x0, y0, w, h = rect; txt(s, title_, (x0, y0), f16)
    top = y0 + 26; hh = h - 26 - 34; vmax = max([v for vs in series.values() for v in vs] + [1e-9])
    n = len(labels); gw = w / max(1, n); ns = len(series); bw = max(4, (gw - 10) / ns)
    pygame.draw.line(s, GR, (x0, top + hh), (x0 + w, top + hh))
    for i, lab in enumerate(labels):
        for j, (nm, vs) in enumerate(series.items()):
            v = vs[i]; bh = int(hh * max(0, v) / vmax); bx = x0 + i * gw + 5 + j * bw
            pygame.draw.rect(s, COL.get(nm, (150, 150, 150)), (bx, top + hh - bh, bw - 2, bh))
            txt(s, fmt.format(v), (bx - 2, top + hh - bh - 13), f11)
        txt(s, lab, (x0 + i * gw + 3, top + hh + 4), f11)
    for j, nm in enumerate(series): txt(s, nm, (x0 + w - 70 * (len(series) - j), y0 + 2), f13, COL.get(nm, FG))
def curve(s, rect, title_, xs, series, zero=True):
    x0, y0, w, h = rect; txt(s, title_, (x0, y0), f16)
    top = y0 + 26; hh = h - 26 - 22
    allv = [v for vs in series.values() for v in vs]; lo, hi = min(allv + [0]), max(allv + [0])
    rng = max(1e-9, hi - lo); X = lambda x: x0 + 40 + (w - 50) * (x - xs[0]) / max(1, xs[-1] - xs[0])
    Y = lambda v: top + hh - hh * (v - lo) / rng
    if zero: pygame.draw.line(s, GR, (x0 + 40, Y(0)), (x0 + w, Y(0)))
    for v in (lo, hi): txt(s, f"{v:.0f}", (x0, Y(v) - 6), f11)
    for t in range(0, int(xs[-1]) + 1, 120): txt(s, f"{t // 60}'", (X(t) - 6, top + hh + 4), f11)
    for nm, vs in series.items():
        pts = [(X(x), Y(v)) for x, v in zip(xs, vs)]
        if len(pts) > 1: pygame.draw.lines(s, COL.get(nm, (200, 200, 200)), False, pts, 2)
def heat(v):
    v = np.clip(v, 0, 1); r_ = np.clip(v * 3, 0, 1); g = np.clip(v * 3 - 1, 0, 1); b = np.clip(v * 3 - 2, 0, 1)
    return (np.stack([r_, g, b], -1) * 255).astype(np.uint8)
NB = 75
def heat_tile(H, px):
    k = np.array([1, 2, 1]) / 4.0
    Hb = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 0, H)
    Hb = np.apply_along_axis(lambda m: np.convolve(m, k, "same"), 1, Hb)
    img = heat(np.log1p(Hb) / max(1e-9, np.log1p(Hb.max()) if Hb.max() > 0 else 1))
    sf = pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))
    sf = pygame.transform.scale(sf, (px, px))
    W = px
    for (bx, by, c) in ((0.12, 0.88, (80, 160, 255)), (0.88, 0.12, (255, 90, 90))):
        pygame.draw.circle(sf, c, (int(bx * W), int(by * W)), 5, 2)
    pygame.draw.line(sf, (60, 60, 70), (0, W - 1), (W - 1, 0))
    return sf
def grid_of(units_samples, r_list=None):
    H = np.zeros((NB, NB))
    for r, u, ph in units_samples:
        for t, x, y, alive in u["p"]:
            if not alive or (ph is not None and phase_of(t) != ph): continue
            x, y = mirror(r, u, x, y)
            H[min(NB - 1, max(0, int(y / r["W"] * NB))), min(NB - 1, max(0, int(x / r["W"] * NB)))] += 1
    return H

md = []
P = md.append
nm_ = len(res); wins = sum(r["winner"] == r["side"] for r in res)
P(f"# Suite di analisi: {title}\n")
P(f"{nm_} partite esatte 5v5 (candidato vs BASE, ogni seme su entrambi i lati, tetto 14 min). "
  f"Vittorie candidato **{wins}/{nm_} = {wins / nm_:.0%}**, durata media {np.mean([r['dur'] for r in res]) / 60:.1f} min. "
  "Fasi: early 0-5', mid 5-10', late 10'+ (le grandezze sono per minuto *effettivamente giocato* nella fase).\n")

# ---------- 1. Fasi ----------
agg = {ai: [defaultdict(float) for _ in PH] for ai in AIS}
minutes = {ai: [0.0] * 3 for ai in AIS}
fb = {ai: [] for ai in AIS}; ft = {ai: [] for ai in AIS}
nwc = defaultdict(lambda: {"cand": [], "base": []})
for r in res:
    U = r["U"]; L = r["log"]; ai_of_team = {r["side"]: "cand", 1 - r["side"]: "base"}
    for ph in range(3):
        for ai in AIS: minutes[ai][ph] += mins(r, ph)
    for t, a, v, amt, k in L["dmg"]:
        va = U.get(v)
        if va is None: continue
        ph = phase_of(t); ai = va["ai"]
        agg[ai][ph]["taken"] += amt
        if k == "P" and a in U and U[a]["team"] != va["team"]:
            agg[U[a]["ai"]][ph]["dmg"] += amt
        elif k == "T": agg[U[a]["ai"] if a in U else ai_of_team[1 - va["team"]]][ph]["towerdmg"] += 0
    for t, c, tg, g in L["heal"]:
        if tg not in U: continue
        ai = U[tg]["ai"]; ph = phase_of(t)
        agg[ai][ph]["heal_self" if c == tg else "heal_ally"] += g
    for t, c, tg, amt in L["shield"]:
        if c in U: agg[U[c]["ai"]][phase_of(t)]["shield"] += amt
    for k in L["kills"]:
        t, x, y, vid, vt, kid, kt, ktype, asst = k
        if vt is None or vt not in (0, 1): continue
        ph = phase_of(t)
        agg[ai_of_team[vt]][ph]["deaths"] += 1
        if kt in (0, 1) and kt != vt and ktype == "Pokemon": agg[ai_of_team[kt]][ph]["kills"] += 1
        if ktype != "Pokemon" and kt in (0, 1): pass
    for t, k, kid, x, y in L["farm"]:
        if kid in U: agg[U[kid]["ai"]][phase_of(t)][k] += 1
    # tempi di primo sangue / prima torre
    ks = [k for k in L["kills"] if k[7] == "Pokemon" and k[6] in (0, 1) and k[4] in (0, 1) and k[6] != k[4]]
    if ks: a_ = ai_of_team[min(ks)[6]]; fb[a_].append(min(ks)[0])
    tw = [f for f in L["farm"] if f[1] == "tower" and f[2] in U]
    if tw: f0 = min(tw); ft[U[f0[2]]["ai"]].append(f0[0])
    for ai in AIS:
        tm = r["side"] if ai == "cand" else 1 - r["side"]
        ids = [i for i, u in U.items() if u["team"] == tm]
        series = {}
        for i in ids:
            for t, hp, lv, nw in L["st"].get(str(i), []): series[t] = series.get(t, 0) + nw
        for t, v in series.items(): nwc[t][ai].append(v)
rate = lambda ai, ph, k: agg[ai][ph][k] / max(1e-9, minutes[ai][ph])
P("## 1. Fasi di gioco (per squadra, per minuto)\n")
P("| metrica | ai | early | mid | late |\n|---|---|---|---|---|")
for lab, k, f in (("danno ai campioni", "dmg", "{:.0f}"), ("danno subito (tutte le fonti)", "taken", "{:.0f}"),
                  ("uccisioni", "kills", "{:.2f}"), ("morti", "deaths", "{:.2f}"), ("minion (cs)", "cs", "{:.1f}"),
                  ("campi", "camp", "{:.2f}"), ("torri distrutte", "tower", "{:.3f}"),
                  ("cure su se stessi", "heal_self", "{:.0f}"), ("cure agli alleati", "heal_ally", "{:.0f}"),
                  ("scudi dati", "shield", "{:.0f}")):
    for ai in AIS: P(f"| {lab} | {ai} | " + " | ".join(f.format(rate(ai, ph, k)) for ph in range(3)) + " |")
P(f"\nPrimo sangue: cand mediana {np.median(fb['cand']) / 60 if fb['cand'] else float('nan'):.1f}' ({len(fb['cand'])} volte), "
  f"base {np.median(fb['base']) / 60 if fb['base'] else float('nan'):.1f}' ({len(fb['base'])}). "
  f"Prima torre: cand {np.median(ft['cand']) / 60 if ft['cand'] else float('nan'):.1f}' ({len(ft['cand'])}), "
  f"base {np.median(ft['base']) / 60 if ft['base'] else float('nan'):.1f}' ({len(ft['base'])}).\n")
S = pygame.Surface((1500, 760)); S.fill(BG)
txt(S, f"{title}: fasi di gioco", (12, 8), f20)
xs = sorted(t for t, v in nwc.items() if v["cand"] and v["base"])
curve(S, (12, 40, 740, 330), "networth squadra (medio): cand vs base", xs,
      {ai: [np.mean(nwc[t][ai]) for t in xs] for ai in AIS}, zero=False)
curve(S, (770, 40, 720, 330), "vantaggio networth cand - base (medio)", xs,
      {"cand": [np.mean(nwc[t]["cand"]) - np.mean(nwc[t]["base"]) for t in xs]})
labs = [p[0] for p in PH]
bars(S, (12, 390, 360, 350), "danno ai campioni /min", labs, {ai: [rate(ai, p, "dmg") for p in range(3)] for ai in AIS})
bars(S, (390, 390, 360, 350), "uccisioni /min", labs, {ai: [rate(ai, p, "kills") for p in range(3)] for ai in AIS}, "{:.2f}")
bars(S, (770, 390, 360, 350), "minion+campi /min", labs, {ai: [rate(ai, p, "cs") + rate(ai, p, "camp") for p in range(3)] for ai in AIS}, "{:.1f}")
bars(S, (1150, 390, 340, 350), "morti /min", labs, {ai: [rate(ai, p, "deaths") for p in range(3)] for ai in AIS}, "{:.2f}")
pygame.image.save(S, pref + "_phases.png")

# ---------- 2. Per ruolo e fase ----------
rp = {ai: {g: [defaultdict(float) for _ in PH] for g in ROLES} for ai in AIS}
rminu = {ai: {g: [0.0] * 3 for g in ROLES} for ai in AIS}
for r in res:
    U = r["U"]; L = r["log"]
    for u in U.values():
        for ph in range(3): rminu[u["ai"]][u["grp"]][ph] += mins(r, ph) if u["grp"] in ROLES else 0
    for t, a, v, amt, k in L["dmg"]:
        if v in U and U[v]["grp"] in ROLES:
            rp[U[v]["ai"]][U[v]["grp"]][phase_of(t)]["taken"] += amt
            if k == "P" and a in U and U[a]["team"] != U[v]["team"]:
                rp[U[a]["ai"]][U[a]["grp"]][phase_of(t)]["dmg"] += amt
    for t, c, tg, g in L["heal"]:
        if c in U and U[c]["grp"] in ROLES: rp[U[c]["ai"]][U[c]["grp"]][phase_of(t)]["heal_out" if c != tg else "heal_self"] += g
    for t, c, tg, amt in L["shield"]:
        if c in U and U[c]["grp"] in ROLES: rp[U[c]["ai"]][U[c]["grp"]][phase_of(t)]["shield"] += amt
    for k in L["kills"]:
        t, x, y, vid, vt, kid, kt, kty, asst = k
        if vid in U and U[vid]["grp"] in ROLES: rp[U[vid]["ai"]][U[vid]["grp"]][phase_of(t)]["deaths"] += 1
        if kid in U and kty == "Pokemon" and kt != vt and U[kid]["grp"] in ROLES: rp[U[kid]["ai"]][U[kid]["grp"]][phase_of(t)]["kills"] += 1
        for a in asst:
            if a in U and U[a]["grp"] in ROLES: rp[U[a]["ai"]][U[a]["grp"]][phase_of(t)]["assists"] += 1
    for t, k, kid, x, y in L["farm"]:
        if kid in U and U[kid]["grp"] in ROLES: rp[U[kid]["ai"]][U[kid]["grp"]][phase_of(t)][k] += 1
P("## 2. Per ruolo e fase (per unita', per minuto)\n")
P("Danno ai campioni / danno subito / K-D-A per minuto; farm = minion + campi per minuto.\n")
P("| ruolo | ai | fase | danno/min | subito/min | K/min | D/min | A/min | farm/min | cure+scudi dati/min |\n|---|---|---|---|---|---|---|---|---|---|")
for g in ROLES:
    for ai in AIS:
        for ph in range(3):
            m = max(1e-9, rminu[ai][g][ph]); d = rp[ai][g][ph]
            P(f"| {g} | {ai} | {PH[ph][0]} | {d['dmg'] / m:.0f} | {d['taken'] / m:.0f} | {d['kills'] / m:.2f} | {d['deaths'] / m:.2f} | "
              f"{d['assists'] / m:.2f} | {(d['cs'] + d['camp']) / m:.1f} | {(d['heal_out'] + d['shield']) / m:.0f} |")
P("")
# heatmap ruolo x fase (cand)
for ai in AIS:
    tile = 220
    S = pygame.Surface((len(ROLES) * (tile + 6) + 6, 3 * (tile + 24) + 30)); S.fill(BG)
    txt(S, f"{title}: posizioni per ruolo e fase ({ai}); base propria in basso a sinistra (blu)", (6, 4), f16)
    for pi in range(3):
        for gi, g in enumerate(ROLES):
            smp = [(r, u, pi) for r in res for u in r["U"].values() if u["ai"] == ai and u["grp"] == g]
            H = grid_of(smp)
            x0 = 6 + gi * (tile + 6); y0 = 30 + pi * (tile + 24) + 18
            txt(S, f"{g} {PH[pi][0]}", (x0, y0 - 16), f11)
            S.blit(heat_tile(H, tile), (x0, y0))
    pygame.image.save(S, f"{pref}_roles_phase_{ai}.png")

# ---------- 3. Cure ----------
P("## 3. Cure e scudi\n")
hl = {ai: defaultdict(float) for ai in AIS}
healers = defaultdict(lambda: defaultdict(float))
for r in res:
    U = r["U"]; L = r["log"]
    for t, c, tg, g in L["heal"]:
        if c in U and tg in U:
            ai = U[c]["ai"]; hl[ai]["self" if c == tg else "ally"] += g; healers[(ai, U[c]["name"])]["heal"] += g
            healers[(ai, U[c]["name"])]["n"] += 0
    for t, c, tg, amt in L["shield"]:
        if c in U and tg in U: hl[U[c]["ai"]]["shield"] += amt; healers[(U[c]["ai"], U[c]["name"])]["shield"] += amt
    for u in U.values(): healers[(u["ai"], u["name"])]["games"] += 1
    for t, a, v, amt, k in L["dmg"]:
        if v in U: hl[U[v]["ai"]]["taken"] += amt
P("| ai | cure su se stessi | cure agli alleati | scudi dati | danno subito | (cure+scudi)/danno subito |\n|---|---|---|---|---|---|")
for ai in AIS:
    h = hl[ai]; P(f"| {ai} | {h['self'] / nm_:.0f} | {h['ally'] / nm_:.0f} | {h['shield'] / nm_:.0f} | {h['taken'] / nm_:.0f} | "
                  f"{(h['self'] + h['ally'] + h['shield']) / max(1, h['taken']):.1%} |")
P("\n(valori per partita, squadra intera)\n")
top = sorted(((k, v) for k, v in healers.items() if v["heal"] + v["shield"] > 0 and v["games"] >= 3),
             key=lambda kv: -(kv[1]["heal"] + kv[1]["shield"]) / kv[1]["games"])[:12]
P("Chi cura/scherma di piu' (per partita giocata, min. 3 partite):\n")
P("| Pokemon | ai | partite | cure | scudi |\n|---|---|---|---|---|")
for (ai, nme), v in top: P(f"| {nme} | {ai} | {v['games']:.0f} | {v['heal'] / v['games']:.0f} | {v['shield'] / v['games']:.0f} |")
P("")
# curve cure per fase + bar per ruolo
S = pygame.Surface((1500, 400)); S.fill(BG); txt(S, f"{title}: cure e scudi", (12, 8), f20)
bars(S, (12, 40, 720, 350), "cure+scudi dati per squadra /min, per fase", labs,
     {ai: [(agg[ai][p]["heal_self"] + agg[ai][p]["heal_ally"] + agg[ai][p]["shield"]) / max(1e-9, minutes[ai][p]) for p in range(3)] for ai in AIS})
bars(S, (760, 40, 730, 350), "cure+scudi dati per unita' /min (per ruolo)", ROLES,
     {ai: [sum((rp[ai][g][p]["heal_out"] + rp[ai][g][p]["heal_self"] + rp[ai][g][p]["shield"]) for p in range(3)) /
           max(1e-9, sum(rminu[ai][g])) for g in ROLES] for ai in AIS})
pygame.image.save(S, pref + "_heal.png")

# ---------- 4. Entrate e scontri ----------
P("## 4. Entrate (territorio nemico) e scontri\n")
ent = {ai: {g: dict(n=0, first=[], cross=0, pct=[0, 0, 0], tot=[0, 0, 0], depth=[], deaths_enemy=0, deaths=0) for g in ROLES} for ai in AIS}
for r in res:
    U = r["U"]
    for u in U.values():
        if u["grp"] not in ROLES: continue
        e = ent[u["ai"]][u["grp"]]; e["n"] += 1; inside = False; since = None; first = None
        for t, x, y, alive in u["p"]:
            if not alive: inside = False; since = None; continue
            ph = phase_of(t); h = enemy_half(r, u, x, y); e["tot"][ph] += 1; e["pct"][ph] += h
            ec = r["cores"][1 - u["team"]]; e["depth"].append(math.hypot(x - ec[0], y - ec[1])) if t % 10 < 1 else None
            if h and not inside:
                since = since if since is not None else t
                if t - since >= 5: inside = True; e["cross"] += 1; first = t if first is None else first
            if not h: since = None; inside = False
        if first is not None: e["first"].append(first)
    for k in r["log"]["kills"]:
        t, x, y, vid, vt, kid, kt, kty, asst = k
        if vid in U and U[vid]["grp"] in ROLES:
            e = ent[U[vid]["ai"]][U[vid]["grp"]]; e["deaths"] += 1
            e["deaths_enemy"] += enemy_half(r, U[vid], x, y)
P("Entrata = restare almeno 5 s nella meta' di mappa piu' vicina al nucleo nemico. 'Prof.' = distanza media dal nucleo nemico (tile).\n")
P("| ruolo | ai | entrate/partita | prima entrata (mediana) | % tempo in meta' nemica early/mid/late | morti in meta' nemica | distanza media dal nucleo nemico |\n|---|---|---|---|---|---|---|")
for g in ROLES:
    for ai in AIS:
        e = ent[ai][g]; n = max(1, e["n"])
        fm = f"{np.median(e['first']) / 60:.1f}'" if e["first"] else "-"
        pc = " / ".join(f"{e['pct'][p] / max(1, e['tot'][p]):.0%}" for p in range(3))
        P(f"| {g} | {ai} | {e['cross'] / n:.2f} | {fm} | {pc} | {e['deaths_enemy']}/{e['deaths']} | {np.mean(e['depth']) if e['depth'] else 0:.0f} |")
P("")
# schermaglie
sk_all = []
for r in res:
    U = r["U"]; L = r["log"]
    ev = sorted((t, a, v) for t, a, v, amt, k in L["dmg"] if k == "P" and a in U and v in U and U[a]["team"] != U[v]["team"])
    def pos_at(i, t):
        p = U[i]["p"]; j = min(len(p) - 1, int(t)); return p[j][1], p[j][2]
    cl = []
    for t, a, v in ev:
        vx, vy = pos_at(v, t); put = None
        for c in cl:
            if t - c["end"] <= 6 and math.hypot(vx - c["x"], vy - c["y"]) <= 22: put = c; break
        if put is None:
            put = dict(t0=t, end=t, x=vx, y=vy, init=a, att=set(), vic=set(), n=0); cl.append(put)
        put["end"] = t; put["att"].add(a); put["vic"].add(v); put["n"] += 1
    for c in cl:
        ks = [k for k in L["kills"] if c["t0"] - 1 <= k[0] <= c["end"] + 3 and k[3] in c["vic"] and k[7] == "Pokemon"]
        teams = {0: set(), 1: set()}
        for i in c["att"] | c["vic"]: teams[U[i]["team"]].add(i)
        kt = {0: 0, 1: 0}
        for k in ks: kt[U[k[3]]["team"] ^ 1] += 1
        itm = U[c["init"]]["team"]
        sk_all.append(dict(r=r, t0=c["t0"], dur=c["end"] - c["t0"], x=c["x"], y=c["y"], init=U[c["init"]], itm=itm,
                           sz=(len(teams[itm]), len(teams[1 - itm])), kills_i=kt[itm], kills_o=kt[1 - itm]))
P(f"### Scontri tra campioni ({len(sk_all)} schermaglie, raggruppate per tempo ≤6 s e distanza ≤22 tile)\n")
P("Iniziatore = primo che infligge danno. 'Esito' = uccisioni dell'iniziatore meno quelle subite.\n")
P("| iniziatore | n | % | team medio (suo/avversario) | esito medio | durata media s | early/mid/late |\n|---|---|---|---|---|---|---|")
for ai in AIS:
    s = [x for x in sk_all if x["init"]["ai"] == ai]
    if s:
        P(f"| {ai} | {len(s)} | {len(s) / len(sk_all):.0%} | {np.mean([x['sz'][0] for x in s]):.1f} / {np.mean([x['sz'][1] for x in s]):.1f} | "
          f"{np.mean([x['kills_i'] - x['kills_o'] for x in s]):+.2f} | {np.mean([x['dur'] for x in s]):.0f} | "
          + " / ".join(str(sum(phase_of(x['t0']) == p for x in s)) for p in range(3)) + " |")
P("\nIniziatori per ruolo (quanto spesso apre lo scontro):\n")
P("| ruolo | cand: aperture | cand: esito medio | base: aperture | base: esito medio |\n|---|---|---|---|---|")
for g in ROLES:
    row = [g]
    for ai in AIS:
        s = [x for x in sk_all if x["init"]["ai"] == ai and x["init"]["grp"] == g]
        row += [str(len(s)), f"{np.mean([x['kills_i'] - x['kills_o'] for x in s]):+.2f}" if s else "-"]
    P("| " + " | ".join(row) + " |")
P("\nDimensione delle schermaglie (membri coinvolti per lato):\n")
szs = defaultdict(int)
for x in sk_all: szs[(min(5, x["sz"][0]), min(5, x["sz"][1]))] += 1
P(", ".join(f"{a}v{b}: {n}" for (a, b), n in sorted(szs.items(), key=lambda kv: -kv[1])[:10]) + "\n")
# PNG entrate
S = pygame.Surface((1500, 760)); S.fill(BG); txt(S, f"{title}: entrate e scontri", (12, 8), f20)
bars(S, (12, 40, 740, 350), "% tempo in meta' nemica (tutto il match)", ROLES,
     {ai: [100 * sum(ent[ai][g]["pct"]) / max(1, sum(ent[ai][g]["tot"])) for g in ROLES] for ai in AIS})
bars(S, (770, 40, 720, 350), "entrate in territorio nemico /partita", ROLES,
     {ai: [ent[ai][g]["cross"] / max(1, ent[ai][g]["n"]) for g in ROLES] for ai in AIS}, "{:.1f}")
bars(S, (12, 400, 740, 350), "scontri aperti per ruolo", ROLES,
     {ai: [sum(1 for x in sk_all if x["init"]["ai"] == ai and x["init"]["grp"] == g) for g in ROLES] for ai in AIS})
bars(S, (770, 400, 720, 350), "esito medio dello scontro per ruolo che lo apre (K-D)", ROLES,
     {ai: [(np.mean([x["kills_i"] - x["kills_o"] for x in sk_all if x["init"]["ai"] == ai and x["init"]["grp"] == g] or [0])) for g in ROLES] for ai in AIS},
     "{:.2f}")
pygame.image.save(S, pref + "_entry.png")
# mappa degli scontri
tile = 380; S = pygame.Surface((2 * tile + 18, tile + 40)); S.fill(BG)
for ci, ai in enumerate(AIS):
    H = np.zeros((NB, NB))
    for x in sk_all:
        if x["init"]["ai"] != ai: continue
        px, py = mirror(x["r"], x["init"], x["x"], x["y"])
        H[min(NB - 1, max(0, int(py / x["r"]["W"] * NB))), min(NB - 1, max(0, int(px / x["r"]["W"] * NB)))] += 1
    txt(S, f"dove {ai} apre gli scontri (n={int(H.sum())})", (6 + ci * (tile + 6), 6), f13)
    S.blit(heat_tile(H, tile), (6 + ci * (tile + 6), 28))
pygame.image.save(S, pref + "_fights.png")

# ---------- 5. Per personaggio ----------
chars = defaultdict(lambda: {ai: defaultdict(float) for ai in AIS})
for r in res:
    U = r["U"]; L = r["log"]
    for u in U.values():
        c = chars[u["name"]][u["ai"]]; c["games"] += 1; c["win"] += u["win"]; c["grp_" + u["grp"]] += 1
        for t, x, y, alive in u["p"]:
            if alive: c["al"] += 1; c["enemy"] += enemy_half(r, u, x, y)
    for t, a, v, amt, k in L["dmg"]:
        if v in U:
            chars[U[v]["name"]][U[v]["ai"]]["taken"] += amt
            if k == "P" and a in U and U[a]["team"] != U[v]["team"]: chars[U[a]["name"]][U[a]["ai"]]["dmg"] += amt
    for t, c_, tg, g in L["heal"]:
        if c_ in U and tg in U: chars[U[c_]["name"]][U[c_]["ai"]]["heal"] += g
    for t, c_, tg, amt in L["shield"]:
        if c_ in U: chars[U[c_]["name"]][U[c_]["ai"]]["shield"] += amt
    for k in L["kills"]:
        t, x, y, vid, vt, kid, kt, kty, asst = k
        if vid in U: chars[U[vid]["name"]][U[vid]["ai"]]["deaths"] += 1
        if kid in U and kty == "Pokemon" and kt != vt: chars[U[kid]["name"]][U[kid]["ai"]]["kills"] += 1
        for a in asst:
            if a in U: chars[U[a]["name"]][U[a]["ai"]]["assists"] += 1
    for t, k, kid, x, y in L["farm"]:
        if kid in U: chars[U[kid]["name"]][U[kid]["ai"]][k] += 1
P("## 5. Per personaggio\n")
P("Valori per partita giocata (il Pokemon al livello 1, nome iniziale). Il ruolo prevalente puo' essere jungler o lane: leggere con cautela se n e' piccolo.\n")
for ai in AIS:
    P(f"### {ai}\n")
    P("| Pokemon | ruolo | n | win% | K | D | A | danno | subito | cure+scudi | farm | % in meta' nemica |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    rows = sorted(chars.items(), key=lambda kv: -kv[1][ai]["games"])
    for nme, d in rows:
        c = d[ai]; n = c["games"]
        if n == 0: continue
        gr = max((k for k in c if k.startswith("grp_")), key=lambda k: c[k])[4:]
        P(f"| {nme} | {gr} | {n:.0f} | {c['win'] / n:.0%} | {c['kills'] / n:.1f} | {c['deaths'] / n:.1f} | {c['assists'] / n:.1f} | "
          f"{c['dmg'] / n:.0f} | {c['taken'] / n:.0f} | {(c['heal'] + c['shield']) / n:.0f} | {(c['cs'] + c['camp']) / n:.0f} | "
          f"{c['enemy'] / max(1, c['al']):.0%} |")
    P("")
names = sorted(chars, key=lambda n: -(chars[n]["cand"]["games"] + chars[n]["base"]["games"]))
tile = 190; cols = 6; rows_n = math.ceil(len(names) / cols)
for ai in AIS:
    S = pygame.Surface((cols * (tile + 6) + 6, rows_n * (tile + 22) + 30)); S.fill(BG)
    txt(S, f"{title}: posizioni per personaggio ({ai}); base propria in basso a sinistra (blu), nemica in alto a destra (rosso)", (6, 6), f13)
    for i, nme in enumerate(names):
        smp = [(r, u, None) for r in res for u in r["U"].values() if u["ai"] == ai and u["name"] == nme]
        x0 = 6 + (i % cols) * (tile + 6); y0 = 30 + (i // cols) * (tile + 22) + 16
        txt(S, f"{nme} n={len(smp)}", (x0, y0 - 15), f11)
        S.blit(heat_tile(grid_of(smp), tile), (x0, y0))
    pygame.image.save(S, f"{pref}_chars_{ai}.png")

P("## Immagini\n")
for s in ("phases", "heal", "entry", "fights", "roles_phase_cand", "roles_phase_base", "chars_cand", "chars_base"):
    P(f"- `{os.path.basename(pref)}_{s}.png`")
open(pref + ".md", "w", encoding="utf-8").write("\n".join(md))
print("ok", pref)
