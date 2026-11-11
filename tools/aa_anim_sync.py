"""Sincronizza l'animazione dell'ATTACCO BASE di ogni forma del roster col motore.

Per ogni forma (data/pokemon/*.json, tutte le evoluzioni):
  1. sceglie l'animazione PMD: corpo a corpo -> Attack (poi Strike/Swing),
     a distanza -> Shoot (poi Attack/Charge);
  2. sceglie il FOTOGRAMMA DEL COLPO: <HitFrame> di AnimData.xml; se manca, il
     fotogramma in cui lo sprite (rivolto a destra) si spinge piu' in AVANTI
     (l'affondo / il colpo che parte);
  3. calcola con i tempi del motore (engine/basic_attack.py: caricamento e ciclo)
     la velocita' dell'animazione a vel. d'attacco base e al tetto, e quanti
     fotogrammi di preparazione si tagliano (game/aa_sync.plan).

Scrive data/aa_anims.json (letto da game/aa_sync.py) e una tavola di controllo
screenshots/aa_sync_sheet.png: una riga per forma, fotogrammi rivolti a destra,
colpo in oro, fotogrammi tagliati al tetto della vel. d'attacco scuriti.

Uso:  python tools/aa_anim_sync.py            (tabella + json + tavola)
      python tools/aa_anim_sync.py --no-sheet
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from engine import basic_attack as BA  # noqa: E402
from game import aa_sync  # noqa: E402
from game.sprites.spritesheet import load_pokemon_animations  # noqa: E402

RIGHT = 2   # direzione PMD "destra"


def roster_forms():
    seen = {}
    for f in sorted((ROOT / "data" / "pokemon").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for ev in d.get("evolutions") or [d]:
            sd = ev.get("sprite_dir") or d.get("sprite_dir")
            rng = ev.get("attack_range", d.get("attack_range"))
            if not sd or rng is None:
                continue
            bs = ev.get("base_stats") or d.get("base_stats") or {}
            seen[Path(sd).name] = {
                "name": ev.get("name") or d.get("name"), "dir": sd,
                "dex": ev.get("dex", d.get("dex", 0)),
                "role": ev.get("role", d.get("role", "")), "range": float(rng),
                "speed": float(bs.get("speed", 50)),
            }
    return seen


def forward_hit(anim) -> int:
    """Fotogramma con lo sprite piu' spinto in avanti (rivolto a destra)."""
    frames = anim.frames[RIGHT % len(anim.frames)]
    best, bx = 0, -1
    for i, fr in enumerate(frames):
        r = fr.get_bounding_rect()
        if r.width and r.right > bx:
            best, bx = i, r.right
    return best


def pick(aset, melee):
    for name in (aa_sync.MELEE_ANIMS if melee else aa_sync.RANGED_ANIMS):
        a = aset.get(name)
        if a is not None and a.frame_count >= 2:
            return name, a
    return None, None


def timing(form, aps):
    u = type("U", (), {})()
    u.dex, u.role, u.attack_range = form["dex"], form["role"], form["range"]
    base_cycle = 1.0 / form["as1"]
    cycle = 1.0 / aps
    scale = 1.0 + BA.WINDUP_AS_SCALE * (cycle / base_cycle - 1.0)
    windup = max(BA.WINDUP_MIN, BA.windup_frac(u) * base_cycle * scale)
    return cycle, min(windup, cycle * 0.6)


def main():
    pygame.init()
    pygame.display.set_mode((8, 8))
    forms = roster_forms()
    out, rows = {}, []
    print(f"{'forma':12} {'cart':5} {'anim':7} {'colpo':>5} {'fot':>3} "
          f"{'pre':>5} {'post':>5} | {'s1 base':>7} {'s2':>4} | {'s1 cap':>6} {'taglio':>6}")
    for key, fm in sorted(forms.items(), key=lambda kv: kv[1]["dex"]):
        aset = load_pokemon_animations(ROOT / fm["dir"])
        if aset is None:
            print(f"{fm['name']:12} {key:5} (sprite mancanti)")
            continue
        melee = BA.is_melee(type("U", (), {"attack_range": fm["range"]})())
        name, anim = pick(aset, melee)
        if anim is None:
            continue
        src = "file"
        hit = anim.hit_frame
        if not (0 < hit < anim.frame_count):   # assente o 0 (niente preparazione): stima
            hit, src = forward_hit(anim), "avanti"
        fm["as1"] = 0.55 + 0.0015 * fm["speed"]
        d = anim.durations
        pre = aa_sync.ticks(d, 0, hit) * aa_sync.DURATION_UNIT
        post = aa_sync.ticks(d, hit, len(d)) * aa_sync.DURATION_UNIT
        cyc, wu = timing(fm, fm["as1"])
        _, s1, s2 = aa_sync.plan(d, hit, wu, cyc)
        cyc2, wu2 = timing(fm, BA.AS_CAP)
        cut, s1c, _ = aa_sync.plan(d, hit, wu2, cyc2)
        print(f"{fm['name'][:12]:12} {key:5} {name:7} {hit:>3}{'*' if src != 'file' else ' '} "
              f"{len(d):>3} {pre:5.2f} {post:5.2f} | {s1:7.2f} {s2:4.1f} | {s1c:6.2f} {cut:>6}")
        out[key] = {"anim": name, "hit": hit, "melee": melee}
        rows.append((fm, key, anim, hit, cut))
    with open(aa_sync.PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"\n{len(out)} forme -> {aa_sync.PATH.relative_to(ROOT)}  (* = colpo stimato: "
          "fotogramma piu' in avanti)")
    if "--no-sheet" not in sys.argv:
        sheet(rows)


def sheet(rows):
    cell, lab = 44, 96
    ncol = max(r[2].frame_count for r in rows)
    W, H = lab + ncol * cell + 8, len(rows) * cell + 8
    img = pygame.Surface((W, H))
    img.fill((24, 26, 30))
    font = pygame.font.SysFont("consolas", 12)
    for i, (fm, key, anim, hit, cut) in enumerate(rows):
        y = 4 + i * cell
        img.blit(font.render(f"{fm['name'][:11]}", True, (220, 220, 220)), (4, y + 6))
        img.blit(font.render(f"{key} {'M' if fm['range'] <= BA.MELEE_REACH else 'D'}",
                             True, (140, 150, 160)), (4, y + 22))
        frames = anim.frames[RIGHT % len(anim.frames)]
        for j, fr in enumerate(frames):
            x = lab + j * cell
            bb = fr.get_bounding_rect()
            k = min(1.0, (cell - 4) / max(1, bb.width, bb.height))
            sub = fr.subsurface(bb) if bb.width else fr
            sub = pygame.transform.scale(sub, (max(1, int(bb.width * k)), max(1, int(bb.height * k))))
            img.blit(sub, (x + (cell - sub.get_width()) // 2, y + cell - 2 - sub.get_height()))
            if j < cut:
                veil = pygame.Surface((cell, cell), pygame.SRCALPHA)
                veil.fill((0, 0, 0, 150))
                img.blit(veil, (x, y))
            if j == hit:
                pygame.draw.rect(img, (236, 190, 70), (x, y, cell, cell), 2)
            img.blit(font.render(str(anim.durations[j]), True, (110, 120, 130)), (x + 2, y + 1))
    out = ROOT / "screenshots" / "aa_sync_sheet.png"
    pygame.image.save(img, str(out))
    print(f"tavola -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
