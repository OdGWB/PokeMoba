"""Rapporto breve sull'IA: candidato contro base da tools/jungle_trace.py (json delle partite).

    python tools/ai_report.py tools/cma_out/jt_g25.json reports/ai_g25 [--label gen25]
Scrive <out>.md e <out>.png (heatmap jungler + campi + curva)."""
import json, sys, os, math, collections, subprocess
res = json.load(open(sys.argv[1])); out = sys.argv[2]
label = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else "cand"
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
n = len(res)

def side_units(r, role):
    tm = r["side"] if role == "cand" else 1 - r["side"]
    return tm, [u for u in r["all"] if u["team"] == tm]
mean = lambda xs: sum(xs) / max(1, len(xs))
L = []
# ---- risultato complessivo
wins = sum(r["winner"] == r["side"] for r in res)
p = wins / n; se = math.sqrt(p * (1 - p) / n)
gold = [r["networth"][r["side"]] - r["networth"][1 - r["side"]] for r in res]
tw = [sum(r["end"]["towers"][r["side"]].values()) - sum(r["end"]["towers"][1 - r["side"]].values()) for r in res]
kd = {}
for role in ("cand", "base"):
    k = d = a = 0
    for r in res:
        _, us = side_units(r, role)
        k += sum(u["kills"] for u in us); d += sum(u["deaths"] for u in us); a += sum(u["assists"] for u in us)
    kd[role] = (k / n, d / n, a / n)
L += [f"# Rapporto IA: {label} contro base", "",
      f"{n} partite esatte ({n//2} semi, entrambi i lati).", "",
      "## Risultato", "",
      f"- Vittorie: **{wins}/{n} = {p:.0%}** (+-{se:.0%})",
      f"- Oro netto medio: {mean(gold):+.0f} · torri: {mean(tw):+.2f} · durata media: {mean([r['time'] for r in res])/60:.1f} min",
      f"- Uccisioni/morti/assist per partita: candidato {kd['cand'][0]:.1f}/{kd['cand'][1]:.1f}/{kd['cand'][2]:.1f}, "
      f"base {kd['base'][0]:.1f}/{kd['base'][1]:.1f}/{kd['base'][2]:.1f}", ""]

# ---- ruoli: farm, combattimento
L += ["## Per ruolo (media per partita)", "", "| ruolo | | K | D | A | danno | oro finale | liv |", "|---|---|---|---|---|---|---|---|"]
def rolekey(u): return "jungler" if u["smites"] is not None else "lane"
for rk in ("jungler", "lane"):
    for role in ("cand", "base"):
        rows = []
        for r in res:
            _, us = side_units(r, role)
            rows += [u for u in us if rolekey(u) == rk]
        L.append(f"| {rk} | {role} | {mean([u['kills'] for u in rows]):.1f} | {mean([u['deaths'] for u in rows]):.1f} | "
                 f"{mean([u['assists'] for u in rows]):.1f} | {mean([u['dmg'] or 0 for u in rows]):.0f} | "
                 f"{mean([u['gold'] for u in rows]):.0f} | {mean([u['level'] for u in rows]):.1f} |")
L.append("")

# ---- jungling
L += ["## Jungling", ""]
J = {}
for role in ("cand", "base"):
    rows = []
    for r in res:
        tm, us = side_units(r, role)
        ju = [u for u in us if u["smites"] is not None][0]
        camps = [c for c in r["log"]["camps"] if c[4].get(str(tm), 999) < 8]
        rows.append((ju, camps, tm, r))
    J[role] = rows
L += ["| | campi | danno neutrali | smite | primo campo | morto (s) | `lane` | `fight` | `core` | `home` |", "|---|---|---|---|---|---|---|---|---|---|"]
for role, rows in J.items():
    ut = collections.Counter()
    for ju, *_ in rows:
        for k, v in (ju.get("u_time") or {}).items(): ut[k] += v
    tot = sum(ut.values()) or 1
    first = [c[0][0] for _, c, *_ in rows if c]
    dead = mean([sum(1 for q in r["log"]["pos"][str(tm)] if not q[3]) for _, _, tm, r in rows])
    L.append(f"| {role} | {mean([j['camps'] for j,*_ in rows]):.1f} | {mean([j['dmg_wild'] for j,*_ in rows]):.0f} | "
             f"{mean([j['smites'] for j,*_ in rows]):.1f} | {mean(first):.0f}s | {dead:.0f} | "
             + " | ".join(f"{ut[k]/tot:.0%}" for k in ("lane", "fight", "core", "home")) + " |")
L.append("")

# ---- pathfinding: bloccaggi e tragitto, per tutti i campioni
L += ["## Pathfinding / movimento", "",
      "Campionamento a 1 s su tutti i campioni vivi. *Fermo* = spostamento < 1,5 tile in 5 s mentre vivo e lontano dalla base (possibile incastro o attesa); "
      "*velocita'* = tile/s medi da vivo.", "", "| squadra | fermo (% tempo) | velocita' | tile/partita | max fermo di fila (s) |", "|---|---|---|---|---|"]
for role in ("cand", "base"):
    fermi = []; vel = []; dist = []; mx = []
    for r in res:
        tm = r["side"] if role == "cand" else 1 - r["side"]
        for pid, d in r["log"]["all"].items():
            if d["team"] != tm: continue
            ps = d["p"]
            home = ps[0][1:3]
            tot = still = run = best = 0; dd = 0.0
            for i in range(5, len(ps)):
                a, b = ps[i - 5], ps[i]
                if not (a[3] and b[3]): run = 0; continue
                step = math.dist(a[1:3], b[1:3]); dd += math.dist(ps[i - 1][1:3], b[1:3]) if ps[i - 1][3] else 0
                if math.dist(b[1:3], home) < 8: run = 0; continue
                tot += 1
                if step < 1.5:  # coordinate in tile? soglia scalata sotto
                    still += 1; run += 1; best = max(best, run)
                else: run = 0
            if tot:
                fermi.append(still / tot); mx.append(best)
            alive = sum(1 for q in ps if q[3])
            vel.append(dd / max(1, alive)); dist.append(dd)
    L.append(f"| {role} | {mean(fermi):.1%} | {mean(vel):.2f} | {mean(dist):.0f} | {max(mx)} |")
L.append("")
open(out + ".md", "w", encoding="utf8").write("\n".join(L))

# ---- immagine
subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "jungle_plot.py"), sys.argv[1], out + ".png"], check=True)
print("\n".join(L))
