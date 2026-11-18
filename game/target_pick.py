"""Scelta del bersaglio al CLIC sinistro, sullo SPRITE DISEGNATO.

Prima il clic cercava il nemico coi PIEDI piu' vicini al punto cliccato (raggio
1,4 tile). Ma lo sprite si disegna SOPRA i piedi: cliccando sul corpo di un
minion si finiva vicino ai piedi di quello dietro, e un clic sulla testa di un
Pokemon grosso cadeva fuori dal raggio -> attacco-movimento verso il nemico piu'
vicino a chi clicca, non a quello cliccato.

Ora il Renderer, a ogni frame, registra dove ha disegnato ogni unita'
(record(), chiamato da _draw_entities: superficie, posizione e riquadro del
contenuto, in coordinate MONDO px). pick() sceglie, tra i NEMICI DISEGNATI
(quelli nella nebbia non lo sono), in tre livelli:
  1. PIXEL OPACO dello sprite sotto il mouse; se piu' sprite si sovrappongono
     vince quello DAVANTI (y dei piedi maggiore = disegnato per ultimo);
  2. dentro il RIQUADRO dello sprite (allargato di PAD px e almeno MIN_BOX
     tile: gli sprite piccoli restano facili da cliccare): il centro piu' vicino;
  3. il vecchio raggio attorno ai piedi (PICK_RADIUS), come prima.
Senza dati del frame (test headless, prima del primo draw) resta solo il 3.
Solo cosmetico/input: il motore riceve lo stesso AttackCommand di sempre.
"""
from __future__ import annotations

import config
from engine.entities import Pokemon, Structure, Unit

PICK_RADIUS = 1.4      # tile: raggio di riserva attorno ai piedi
ALPHA_MIN = 40         # pixel "pieno" dello sprite
PAD = 3                # px di tolleranza attorno al riquadro dello sprite
MIN_BOX = 0.9          # tile: lato minimo del riquadro cliccabile

# id -> (profondita', [(surface|None, x, y, rect)]) in px MONDO
_frame: dict = {}


def begin() -> None:
    """Nuovo frame: si dimenticano i disegni del frame precedente."""
    _frame.clear()


def record(eid, depth: float, parts, ox: int, oy: int) -> None:
    """Registra le parti disegnate (coordinate schermo low-res) di un'entita'."""
    if not parts:
        return
    out = [(s, x + ox, y + oy, r.move(ox, oy)) for (s, x, y, r) in parts]
    old = _frame.get(eid)
    if old is not None:
        out = old[1] + out
    _frame[eid] = (depth, out)


def _eligible(e, team, champs_only) -> bool:
    if e is None or e.team == team or not getattr(e, "alive", False):
        return False
    if not isinstance(e, (Unit, Structure)):
        return False
    return not (champs_only and not isinstance(e, Pokemon))


def pick(world, team, wx: float, wy: float, champs_only: bool = False):
    """Nemico sotto il punto (wx, wy) in px MONDO, o None."""
    if world is None:
        return None
    ts = config.TILE_SIZE
    best, best_key = None, None
    drawn = set()
    if _frame:
        mx, my = int(wx), int(wy)
        min_box = MIN_BOX * ts
        for eid, (depth, parts) in _frame.items():
            e = world.get(eid)
            if not _eligible(e, team, champs_only):
                continue
            drawn.add(eid)
            key = None
            for surf, x, y, r in parts:
                if surf is not None and r.collidepoint(mx, my):
                    lx, ly = mx - x, my - y
                    if (0 <= lx < surf.get_width() and 0 <= ly < surf.get_height()
                            and surf.get_at((lx, ly)).a > ALPHA_MIN):
                        key = (0, -depth)
                        break
                w = max(r.w + 2 * PAD, min_box)
                h = max(r.h + 2 * PAD, min_box)
                cx, cy = r.centerx, r.centery
                if abs(mx - cx) <= w / 2 and abs(my - cy) <= h / 2:
                    d = ((mx - cx) / w) ** 2 + ((my - cy) / h) ** 2
                    k = (1, d)
                    if key is None or k < key:
                        key = k
            if key is not None and (best_key is None or key < best_key):
                best, best_key = e, key
        if best is not None:
            return best
    # 3. riserva: piedi entro il raggio (solo tra i disegnati, se ci sono dati)
    tx, ty = wx / ts, wy / ts
    best_d = 1e9
    for e in world.combatants():
        if not _eligible(e, team, champs_only):
            continue
        if _frame and e.id not in drawn:
            continue
        d = ((e.pos.x - tx) ** 2 + (e.pos.y - ty) ** 2) ** 0.5
        if d <= PICK_RADIUS + getattr(e, "radius", 0.0) and d < best_d:
            best, best_d = e, d
    return best
