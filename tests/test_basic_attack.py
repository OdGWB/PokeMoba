"""Attacco base a tre fasi (engine/basic_attack.py): caricamento, rilascio,
recupero; proiettili a ricerca; scelta del bersaglio; richiesta d'aiuto."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import basic_attack as BA
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
TED = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "teddiursa.json"))
OWL = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "rowlet.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))


def spawn(world, match, d, pos, team, order="idle"):
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=False, types=d.types,
                            base_stats=d.base_stats, moves=d.moves, evolutions=d.evolutions,
                            role=d.role, passive=d.passive, attack_range=d.attack_range,
                            attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)
    p.radius = d.radius
    p.spawn_pos = Vec2(2.0, 98.0)   # lontano dalla fontana
    match._recompute_stats(p)
    p.hp = p.max_hp
    p.order = order
    return p


class TestBasicAttack(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.match._update_regen = lambda dt: None

    def foe(self, pos, order="stop"):
        e = spawn(self.world, self.match, FOE, pos, 1, order)
        e.max_hp = e.hp = 50000.0
        e.attack_range = 0.0   # bersaglio inerte
        return e

    def step(self, sec, watch=None):
        """Avanza; se `watch` è dato ritorna gli istanti in cui ha perso HP."""
        hits, last = [], watch.hp if watch else 0.0
        for i in range(int(round(sec / DT))):
            self.match.update(DT, i)
            if watch is not None:
                if watch.hp < last - 1e-6:
                    hits.append(self.match.time)
                last = watch.hp
        return hits

    def vis(self):
        self.match.vision.update(self.world, 0)
        self.match.vision.update(self.world, 1)

    # --- ciclo -------------------------------------------------------------------
    def test_melee_hits_at_end_of_windup(self):
        u = spawn(self.world, self.match, TED, Vec2(26.5, 47.5), 0)
        e = self.foe(Vec2(28.5, 47.5))
        self.vis()
        u.order, u.order_target_id = "attack", e.id
        t0 = self.match.time
        hits = self.step(2.5, watch=e)
        cycle, windup = self.match._aa_timing(u)
        self.assertGreaterEqual(len(hits), 2)
        self.assertAlmostEqual(hits[0] - t0, windup, delta=2.5 * DT)
        self.assertAlmostEqual(hits[1] - hits[0], cycle, delta=1.5 * DT)

    def test_move_order_cancels_windup_without_cost(self):
        u = spawn(self.world, self.match, TED, Vec2(26.5, 47.5), 0)
        e = self.foe(Vec2(28.5, 47.5))
        self.vis()
        u.order, u.order_target_id = "attack", e.id
        self.step(2 * DT)
        self.assertTrue(u.aa_active)
        u.order = "move"
        u.set_path([Vec2(20.5, 47.5)])
        self.assertEqual(self.step(0.6, watch=e), [])
        self.assertFalse(u.aa_active)
        self.assertEqual(u.attack_timer, 0.0)   # il ciclo non si è consumato

    def test_ranged_fires_homing_projectile(self):
        u = spawn(self.world, self.match, OWL, Vec2(20.5, 47.5), 0)
        e = self.foe(Vec2(26.0, 47.5))
        self.vis()
        u.order, u.order_target_id = "attack", e.id
        t0 = self.match.time
        _, windup = self.match._aa_timing(u)
        self.step(windup + 2 * DT)
        self.assertEqual(len(self.match.aa_projectiles), 1)
        self.assertEqual(e.hp, e.max_hp)        # ancora in volo
        e.pos = Vec2(26.0, 49.0)                # si sposta: il proiettile lo segue
        hits = self.step(0.6, watch=e)
        self.assertEqual(len(hits), 1)
        self.assertGreater(hits[0] - t0, windup + 0.15)

    def test_projectile_vanishes_if_target_untargetable(self):
        u = spawn(self.world, self.match, OWL, Vec2(20.5, 47.5), 0)
        e = self.foe(Vec2(26.0, 47.5))
        self.vis()
        u.order, u.order_target_id = "attack", e.id
        _, windup = self.match._aa_timing(u)
        self.step(windup + 2 * DT)
        e.untargetable_until = self.match.time + 5.0
        self.step(0.5)
        self.assertEqual(self.match.aa_projectiles, [])
        self.assertEqual(e.hp, e.max_hp)

    def test_attack_speed_bonuses_add_and_cap(self):
        u = spawn(self.world, self.match, TED, Vec2(26.5, 47.5), 0)
        base = u.as_base
        u.as_bonus = 0.2 + 0.3
        self.assertAlmostEqual(self.match._eff_attack_speed(u), base * 1.5)
        u.as_bonus = 10.0
        self.assertAlmostEqual(self.match._eff_attack_speed(u), BA.AS_CAP)
        # il caricamento si accorcia con la velocità, ma un po' meno del ciclo
        u.as_bonus = 0.0
        c0, w0 = self.match._aa_timing(u)
        u.as_bonus = 1.0
        c1, w1 = self.match._aa_timing(u)
        self.assertLess(w1, w0)
        self.assertGreater(w1 / c1, w0 / c0)

    # --- bersaglio ---------------------------------------------------------------
    def test_reach_is_edge_to_edge(self):
        u = spawn(self.world, self.match, TED, Vec2(26.5, 47.5), 0)
        e = self.foe(Vec2(26.5 + u.attack_range + u.radius + 0.1, 47.5))
        self.assertTrue(self.match._within_attack(u, e))

    def test_idle_acquires_and_stops_chasing(self):
        u = spawn(self.world, self.match, TED, Vec2(26.5, 47.5), 0)
        reach = self.match._aa_reach(u, u)
        e = self.foe(Vec2(26.5 + reach + 0.6, 47.5))
        self.vis()
        self.step(0.3)
        self.assertEqual(u.target_id, e.id)      # nel raggio d'acquisizione: lo prende
        e.pos = Vec2(40.5, 47.5)                 # scappa lontano
        self.step(3.0)
        self.assertIsNone(u.target_id)
        self.assertLessEqual(u.pos.dist(Vec2(26.5, 47.5)), BA.IDLE_CHASE_LEASH + 0.2)

    def test_attack_move_champions_only(self):
        u = spawn(self.world, self.match, OWL, Vec2(20.5, 47.5), 0)
        e = self.foe(Vec2(24.0, 47.5))
        mn = self.world.spawn_minion(Vec2(22.0, 48.5), 1, "mid", [Vec2(22.0, 48.5)],
                                     (255, 0, 0), hp=5000.0)
        self.vis()
        u.order, u.order_point = "attackmove", Vec2(22.0, 48.6)
        self.step(DT)
        self.assertEqual(u.target_id, mn.id)     # il più vicino al cursore
        u.target_id, u.champs_only = None, True
        self.step(DT)
        self.assertEqual(u.target_id, e.id)      # "solo Pokémon"

    def test_tower_switches_to_champion_attacker(self):
        tower = next(s for s in self.world.structures() if s.kind == "tower" and s.team == 1)
        tower.pos = Vec2(40.5, 40.5)   # dentro la zona libera del test
        tp = tower.pos
        victim = self.foe(Vec2(tp.x + 1.5, tp.y))
        u = spawn(self.world, self.match, OWL, Vec2(tp.x + 4.5, tp.y), 0, order="stop")
        u.max_hp = u.hp = 50000.0
        mn = self.world.spawn_minion(Vec2(tp.x, tp.y + 1.5), 0, "mid", [tp], (0, 0, 255),
                                     hp=50000.0)
        self.match._ai[mn.id] = {}
        self.vis()
        self.step(0.5)
        self.assertEqual(tower.target_id, mn.id)
        u.order, u.order_target_id = "attack", victim.id
        self.step(1.5)
        self.assertEqual(tower.target_id, u.id)


if __name__ == "__main__":
    unittest.main()
