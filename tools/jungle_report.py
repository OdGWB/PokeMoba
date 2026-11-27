import json, sys, math, collections
res = json.load(open(sys.argv[1]))
# candidato = lato 'side' del task; jungler del candidato = team side
def agg(role):
    rows = []
    for r in res:
        tm = r["side"] if role == "cand" else 1 - r["side"]
        ju = [u for u in r["all"] if u["team"] == tm and u["smites"] is not None][0]
        pos = r["log"]["pos"][str(tm)]
        camps = [c for c in r["log"]["camps"] if c[4].get(str(tm), 999) < 8]
        rows.append((r, ju, pos, camps, tm))
    return rows
for role in ("cand", "base"):
    rows = agg(role); n = len(rows)
    print(f"\n=== {role} ({n} partite)")
    m = lambda f: sum(f(x) for x in rows) / n
    print(f" camps {m(lambda x:x[1]['camps']):.1f}  dmg_wild {m(lambda x:x[1]['dmg_wild']):.0f}  smites {m(lambda x:x[1]['smites']):.1f}"
          f"  kills {m(lambda x:x[1]['kills']):.1f} deaths {m(lambda x:x[1]['deaths']):.1f} assists {m(lambda x:x[1]['assists']):.1f}"
          f"  lvl {m(lambda x:x[1]['level']):.1f}")
    ut = collections.Counter()
    for x in rows:
        for k, v in (x[1].get("u_time") or {}).items(): ut[k] += v
    tot = sum(ut.values()) or 1
    print(" intenzioni:", {k: f"{v/tot:.0%}" for k, v in ut.most_common()}, " cambi", f"{m(lambda x:x[1]['u_switches']):.0f}")
    # primo campo, camp per fascia di tempo
    first = [c[0][0] for x in rows for c in [x[3]] if c]
    print(f" primo campo a {sum(first)/max(1,len(first)):.0f}s (n={len(first)})")
    bins = collections.Counter()
    for x in rows:
        for c in x[3]: bins[int(c[0] // 120)] += 1
    print(" campi/2min:", {f"{k*2}-{k*2+2}m": round(v / n, 1) for k, v in sorted(bins.items())})
    # distanza da casa (spawn = prima pos) e quota di tempo vicino a campi / in lane / morto
    dead = sum(sum(1 for p in x[2] if not p[3]) for x in rows) / n
    far = 0; tl = 0
    for x in rows:
        for p in x[2]:
            if p[3]:
                tl += 1
    print(f" secondi morto/partita {dead:.0f}")
    # campi presi per tipo e ordine medio (primi 6)
    seq = collections.Counter()
    for x in rows:
        for i, c in enumerate(x[3][:6]): seq[(i, c[2] // 10 * 10, c[3] // 10 * 10)] += 1
    for i in range(6):
        top = [(k[1:], v) for k, v in seq.most_common() if k[0] == i][:2]
        print(f"  campo #{i+1}: {top}")
    # furto dei campi avversari: campi uccisi con jungler a <8 mentre alla meta' nemica
    # meta' mappa: team0 in alto-sx? usa diagonale x+y<W
    steal = 0
    for x in rows:
        for c in x[3]:
            if (c[2] + c[3] < 200) != (x[4] == 0): steal += 1
    print(f" campi nemici (invasioni) per partita {steal/n:.1f}")
