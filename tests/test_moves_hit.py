"""Ogni mossa di DANNO di ogni linea va a segno su un bersaglio fermo davanti.

Per tutto il roster, al livello 3 (mosse base) e al 15 con la prima e la
seconda scelta di ogni potenziamento: si lancia la mossa verso un bersaglio a 2
tile e si controlla che, entro 5 s, perda vita. Gli attacchi base sono spenti,
così il danno viene solo dalla mossa. Copre anche le linee senza test dedicati
(Charmander, Gastly, Rowlet, Snivy, Totodile, Nincada, Poliwag, Roggenrola,
Eevee, Spiritomb).
"""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
DEFS = [load_pokemon_def(os.path.join(ROOT, rel)) for rel in config.ROSTER]
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))
BUILDS = ((3, 0), (15, 0), (15, 1))   # (livello, scelta dei potenziamenti)
# Mosse che fanno danno solo in condizioni particolari, provate nei test
# dedicati della linea: id -> perché qui non si provano.
CONDITIONAL = {
    "florges_mistyterrain": "Campo Nebbioso: area di supporto, niente danno diretto",
    "florges_solarbeam": "Solarraggio parte dai fiori piantati (test_florges)",
    "incineroar_ropes": "Corsa alle Corde: il danno è lo schianto contro un muro (test_incineroar)",
    "incineroar_doublebounce": "come sopra",
    "incineroar_momentum": "come sopra",
    "magnetbomb": "Bombagnete muove solo i nemici CARICHI (test_magnezone)",
    "sleevedance": "Danza delle Maniche: il colpo arriva dopo tre mosse (test_mienshao)",
    "nightfall": "Notte Fonda: il danno è l'attacco base dall'ombra (test_sneasel)",
}


def _spawn(world, d, pos, team):
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=False, types=d.types,
                            base_stats=d.base_stats, growth=d.growth, moves=d.moves,
                            evolutions=d.evolutions, role=d.role, passive=d.passive,
                            attack_range=d.attack_range, attack_cooldown=d.attack_cooldown,
                            attack_fx=d.attack_fx)
    p.radius = d.radius
    p.spawn_pos = Vec2(pos.x, pos.y)
    p.order = "idle"
    return p


def _build(match, p, level, variant):
    match._gain_xp(p, CUMULATIVE_XP[level] - p.xp + 1.0)
    match._update_evolution(0)
    for _ in range(3):
        for slot in list(p.pending_choices):
            evolution.apply_choice(p, slot, variant)
        for _ in range(20):
            for s in ("R", "Q", "W", "E"):
                if skills.can_rank_up(p, s):
                    skills.rank_up(p, s)


def cast_and_watch(d, level, variant, slot, far=False):
    """-> (mossa, esito): esito None = niente da provare, True = colpito.
    far=True: bersaglio alla gittata della mossa (balzi a distanza fissa)."""
    random.seed(3)
    m = load_map(os.path.join(ROOT, config.DEFAULT_MAP))
    for y in range(30, 60):                 # radura senza muri
        for x in range(10, 60):
            m.grid.tiles[y][x] = 0
    world = World(m.grid)
    match = Match(world, m)
    match._wave_timer = 1e9
    match.time = 100.0
    match._update_regen = lambda dt: None
    match._update_combat = lambda dt: None   # niente attacchi base: conta solo la mossa
    me = _spawn(world, d, Vec2(30.5, 45.5), 0)
    foe = _spawn(world, FOE, Vec2(32.5, 45.5), 1)
    foe.max_hp = foe.hp = 1e6
    _build(match, me, level, variant)
    ms = me.moveset.get(slot)
    if ms is None or ms.chosen is None or ms.rank <= 0:
        return None, None
    mv = ms.chosen
    if mv.power_at(ms.rank) <= 0 or mv.id in CONDITIONAL:
        return mv, None
    here = Vec2(30.5 + (max(2.0, mv.range) if far else 2.0), 45.5)
    foe.pos = Vec2(here.x, here.y)
    if mv.effects.get("requires_sleep"):      # Mangiasogni: solo su chi dorme
        match._apply_sleep(foe, 5.0)
    ms.cooldown_remaining = 0.0
    match._combat_hash.rebuild(world.combatants())
    match.vision.update(world, 0)            # Comete cerca un nemico VISIBILE
    match._cast(me, slot, foe.pos.x, foe.pos.y)
    for i in range(int(5.0 / DT)):
        match.update(DT, i)
        foe.pos = Vec2(here.x, here.y)       # bersaglio inchiodato (spinte, lanci...)
        foe.stop()
        if foe.hp < foe.max_hp:
            return mv, True
    return mv, False


class TestMovesHit(unittest.TestCase):
    pass


def _make_test(d):
    def test(self):
        tried = 0
        for level, variant in BUILDS:
            for slot in ("Q", "W", "E", "R"):
                mv, ok = cast_and_watch(d, level, variant, slot)
                if ok is None:
                    continue
                if not ok:
                    mv, ok = cast_and_watch(d, level, variant, slot, far=True)
                tried += 1
                with self.subTest(level=level, variant=variant, slot=slot, move=mv.id):
                    self.assertTrue(ok, f"{d.name}: {mv.id} ({mv.shape}) non fa danno")
        self.assertGreater(tried, 0, f"{d.name}: nessuna mossa di danno provata")
    return test


for _d in DEFS:
    setattr(TestMovesHit, f"test_{_d.name.lower().replace('é', 'e')}", _make_test(_d))


if __name__ == "__main__":
    unittest.main()
