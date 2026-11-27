import json, sys, math, collections
sys.path[:0]=['.','tools']
import config
from engine.content import load_pokemon_def
import tier_sim
res = json.load(open(sys.argv[1]))
defs = {}
for rel in config.ROSTER:
    d = load_pokemon_def(rel if __import__('os').path.isabs(rel) else rel); defs[d.name] = d
W = collections.defaultdict(lambda: [0, 0, 0, 0, 0, 0, 0.0, 0.0]) ; side = [0, 0]
for r in res:
    side[r["winner"]] += 1
    for u in r["units"]:
        w = W[u["name"]]; w[0] += r["winner"] == u["team"]; w[1] += 1
        w[2] += u["kills"]; w[3] += u["deaths"]; w[4] += u["assists"]; w[5] += 1; w[6] += u["dmg"] or 0; w[7] += u["gold"] or 0
n = len(res)
print(f"{n} partite, durata media {sum(r['time'] for r in res)/n/60:.1f} min; vittorie blu {side[0]} / rosso {side[1]}")
print(f"{'Pokemon':12} {'ruolo':12} {'n':>4} {'vitt':>6} {'+-':>5}   K    D    A   danno  oro")
rows = []
for k, w in W.items():
    p = w[0] / w[1]; se = 1.96 * math.sqrt(p * (1 - p) / w[1])
    rows.append((p, k, w, se))
for p, k, w, se in sorted(rows, reverse=True):
    role = getattr(defs.get(k), "role", "?")
    print(f"{k:12} {role:12} {w[1]:4d} {p:6.0%} {se:5.0%}  {w[2]/w[1]:4.1f} {w[3]/w[1]:4.1f} {w[4]/w[1]:4.1f} {w[6]/w[1]:6.0f} {w[7]/w[1]:5.0f}")
R = collections.defaultdict(lambda: [0, 0])
for p, k, w, se in rows:
    role = getattr(defs.get(k), "role", "?"); R[role][0] += w[0]; R[role][1] += w[1]
print("\nper ruolo:", {r: f"{a/b:.0%} (n={b})" for r, (a, b) in R.items()})
