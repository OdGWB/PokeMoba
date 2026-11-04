import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.grid import TILE_JUNGLE_WALL, TILE_PILLAR
from engine.magnezone import CHARGE_DUR, CHARGE_DUR_STEEL, PUSH_DIST
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
MAG = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "magnemite.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))
STEEL = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "duraludon.json"))


def spawn(world, d, pos, team):
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=False, types=d.types,
                            base_stats=d.base_stats, moves=d.moves, evolutions=d.evolutions,
                            role=d.role, passive=d.passive, attack_range=d.attack_range,
                            attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)
    p.radius = d.radius
    p.spawn_pos = Vec2(2.0, 98.0)   # lontano dalla fontana: niente rigenerazione
    p.order = "idle"
    return p


class TestMagnezone(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.grid = m.grid
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.match.time = 100.0
        self.u = spawn(self.world, MAG, Vec2(20.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(26.5, 47.5), 1)
        self.f = spawn(self.world, FOE, Vec2(26.5, 51.5), 1)
        self.a = spawn(self.world, FOE, Vec2(20.5, 40.5), 0)   # alleato
        for x in (self.e, self.f, self.a):
            x.max_hp = x.hp = 50000.0
        for x in (self.u, self.e, self.f, self.a):
            x.crit = 0.0
        self.match._update_regen = lambda dt: None

    def level(self, lv):
        self.match._gain_xp(self.u, CUMULATIVE_XP[lv] - self.u.xp + 1.0)
        self.match._update_evolution(0)
        self.rank_all()

    def choose(self, slot, idx):
        if slot not in self.u.pending_choices:
            self.u.pending_choices.append(slot)
        evolution.apply_choice(self.u, slot, idx)
        self.rank_all()

    def rank_all(self):
        for _ in range(20):
            for s in ("R", "Q", "W", "E"):
                if skills.can_rank_up(self.u, s):
                    skills.rank_up(self.u, s)

    def cast(self, slot, x, y, hold=0.0):
        ms = self.u.moveset[slot]
        ms.cooldown_remaining = 0.0
        ms.rank = max(1, ms.rank)
        self.u.cast_hold = hold
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.u, slot, x, y)

    def tick(self, sec):
        for _ in range(int(round(sec / DT))):
            self.match.time += DT
            self.match._combat_hash.rebuild(self.world.combatants())
            self.match._update_mag(DT)
            self.match._update_mag_drags(DT)
            self.match._update_status(DT)

    def charge(self, unit, sign):
        self.match._mag_charge(unit, sign, self.u)

    # --- dati ---------------------------------------------------------------------
    def test_evolutions_and_types(self):
        self.assertEqual(self.u.types, ["Electric", "Steel"])
        self.level(4)
        self.assertEqual(self.u.name, "Magneton")
        self.level(8)
        self.assertEqual(self.u.name, "Magnezone")
        self.assertEqual(self.u.types, ["Electric", "Steel"])
        self.assertEqual(self.u.base_stats.sp_attack, 130)
        self.assertEqual(self.u.base_stats.defense, 115)

    # --- Q -------------------------------------------------------------------------
    def test_thundershock_charges_first_enemy(self):
        self.cast("Q", 30.5, 47.5)
        self.tick(0.5)
        self.assertGreater(self.e.max_hp - self.e.hp, 0)
        self.assertEqual(self.e.mag_sign, 1)
        left = self.e.mag_until - self.match.time
        self.assertTrue(CHARGE_DUR - 0.5 < left < CHARGE_DUR - 0.1, left)
        self.tick(CHARGE_DUR)
        self.assertEqual(self.e.mag_sign, 0)

    def test_steel_enemy_charge_lasts_longer(self):
        s = spawn(self.world, STEEL, Vec2(30.5, 44.5), 1)
        self.charge(s, 1)
        self.assertAlmostEqual(s.mag_until - self.match.time, CHARGE_DUR_STEEL)

    def test_thundershock_charges_wall(self):
        self.e.pos = Vec2(26.5, 55.5)
        self.f.pos = Vec2(26.5, 57.5)
        self.grid.tiles[47][24] = TILE_JUNGLE_WALL
        self.cast("Q", 30.5, 47.5)
        self.tick(0.4)
        self.assertEqual(len(self.match.mag_walls), 1)
        w = self.match.mag_walls[0]
        self.assertEqual((w["tx"], w["ty"], w["sign"]), (24, 47, 1))

    def test_electroweb_pierces_and_slows(self):
        self.level(8)
        self.choose("Q", 0)
        self.f.pos = Vec2(29.5, 47.5)
        self.cast("Q", 32.5, 47.5)
        self.tick(0.45)
        self.assertGreater(self.e.max_hp - self.e.hp, 0)
        self.assertLess(self.e.slow_mult, 1.0)
        self.tick(0.2)
        self.assertGreater(self.f.max_hp - self.f.hp, 0)

    def test_steelcannon_paralyzes(self):
        self.level(8)
        self.choose("Q", 1)
        self.cast("Q", 30.5, 47.5)
        self.tick(0.8)
        self.assertGreater(self.e.root_until, self.match.time)
        self.assertEqual(self.e.mag_sign, 1)

    # --- interazioni -------------------------------------------------------------------
    def test_opposite_enemies_clash(self):
        self.f.pos = Vec2(26.5, 51.0)
        self.charge(self.e, 1)
        self.charge(self.f, -1)
        self.tick(0.6)
        gap = self.e.pos.dist(self.f.pos)
        self.assertLess(gap, self.e.radius + self.f.radius + 0.2)
        self.assertGreater(self.e.max_hp - self.e.hp, 0)
        self.assertGreater(self.f.max_hp - self.f.hp, 0)
        self.assertGreater(self.e.stun_until, self.match.time)
        self.assertEqual((self.e.mag_sign, self.f.mag_sign), (0, 0))

    def test_same_enemies_repel(self):
        self.f.pos = Vec2(26.5, 50.0)
        d0 = self.e.pos.dist(self.f.pos)
        self.charge(self.e, 1)
        self.charge(self.f, 1)
        self.tick(0.1)
        self.assertLess(self.e.slow_mult, 1.0)
        self.tick(0.5)
        self.assertAlmostEqual(self.e.pos.dist(self.f.pos), d0 + 2 * PUSH_DIST, delta=0.2)
        self.assertEqual(self.e.max_hp, self.e.hp)

    def test_far_charges_do_not_interact(self):
        self.f.pos = Vec2(26.5, 54.0)   # 6,5 tile
        self.charge(self.e, 1)
        self.charge(self.f, -1)
        self.tick(0.3)
        self.assertEqual((self.e.mag_sign, self.f.mag_sign), (1, -1))

    def test_ally_anchor_pulls_enemy(self):
        self.a.pos = Vec2(26.5, 43.0)
        self.f.pos = Vec2(40.5, 55.5)
        a0 = Vec2(self.a.pos.x, self.a.pos.y)
        self.charge(self.a, -1)
        self.charge(self.e, 1)
        self.tick(0.6)
        self.assertEqual(self.a.pos.dist(a0), 0.0)
        self.assertLess(self.e.pos.dist(self.a.pos), self.e.radius + self.a.radius + 0.2)
        self.assertEqual(self.e.max_hp, self.e.hp)   # niente urto contro un alleato

    def test_wall_anchor_pull_hits_and_stuns(self):
        self.f.pos = Vec2(40.5, 55.5)
        self.grid.tiles[47][29] = TILE_JUNGLE_WALL
        self.match._mag_charge_wall(Vec2(28.95, 47.5), (29, 47), -1, self.u)
        self.charge(self.e, 1)
        self.tick(0.6)
        self.assertGreater(self.e.pos.x, 28.0)
        self.assertGreater(self.e.max_hp - self.e.hp, 0)
        self.assertGreater(self.e.stun_until, self.match.time)
        self.assertEqual(self.match.mag_walls, [])

    def test_wall_anchor_same_repels(self):
        self.f.pos = Vec2(40.5, 55.5)
        self.grid.tiles[47][29] = TILE_JUNGLE_WALL
        self.match._mag_charge_wall(Vec2(28.95, 47.5), (29, 47), 1, self.u)
        self.charge(self.e, 1)
        self.tick(0.6)
        self.assertAlmostEqual(self.e.pos.x, 26.5 - PUSH_DIST, delta=0.2)

    def test_each_unit_pairs_once_with_nearest(self):
        g = spawn(self.world, FOE, Vec2(26.5, 44.0), 1)   # 3,5 tile da e
        g.max_hp = g.hp = 50000.0
        self.f.pos = Vec2(26.5, 49.5)                    # 2 tile da e (il più vicino)
        self.charge(g, -1)
        self.charge(self.e, 1)
        self.charge(self.f, -1)
        self.tick(DT)
        self.assertEqual(g.mag_sign, -1)                 # resta: e era già occupato
        self.assertEqual(len(self.match.mag_links), 1)

    # --- W -----------------------------------------------------------------------------
    def test_magnet_field_enemy_and_ally(self):
        self.f.pos = Vec2(40.5, 55.5)
        self.cast("W", 26.5, 47.5)
        self.assertGreater(self.e.max_hp - self.e.hp, 0)
        self.assertEqual(self.e.mag_sign, -1)
        self.cast("W", 20.5, 40.5)
        self.assertGreater(self.a.shield, 0)
        self.assertEqual(self.a.mag_sign, -1)

    def test_magnet_field_needs_target(self):
        self.cast("W", 30.5, 40.5)
        self.assertEqual(self.u.moveset["W"].cooldown_remaining, 0.0)

    def test_double_polarity_stronger_shield(self):
        self.level(8)
        self.cast("W", 20.5, 40.5)
        base = self.a.shield
        self.a.shield = 0.0
        self.a.shield_until = -1.0
        self.choose("W", 0)
        self.cast("W", 20.5, 40.5)
        self.assertAlmostEqual(self.a.shield / base, 1.5, places=2)
        self.assertAlmostEqual(self.a.shield_until - self.match.time, 5.0)

    def test_chain_spreads_negative(self):
        self.level(8)
        self.choose("W", 1)
        self.f.pos = Vec2(26.5, 50.5)
        self.cast("W", 26.5, 47.5)
        self.assertEqual(self.e.mag_sign, -1)
        self.assertEqual(self.f.mag_sign, -1)
        self.assertAlmostEqual((self.f.max_hp - self.f.hp) / (self.e.max_hp - self.e.hp), 0.5,
                               places=2)

    # --- E -----------------------------------------------------------------------------
    def test_voltswitch_inverts_crossed_charges(self):
        self.f.pos = Vec2(40.5, 55.5)
        self.e.pos = Vec2(22.5, 47.5)
        self.e.mag_sign, self.e.mag_until, self.e.mag_team = 1, self.match.time + 4, 0
        self.cast("E", 24.0, 47.5)
        self.assertEqual(self.e.mag_sign, -1)
        self.assertGreater(self.u.pos.x, 23.0)

    def test_double_dash_has_two_charges(self):
        self.level(8)
        self.choose("E", 0)
        self.cast("E", 23.5, 47.5)
        self.u.moveset["E"].cooldown_remaining = 0.0   # solo il mini-ritardo tra le cariche
        self.match._cast(self.u, "E", 26.5, 47.5)
        self.assertFalse(self.u.moveset["E"].ready)
        self.assertGreater(self.u.pos.x, 25.0)

    def test_ion_trail_charges_positive(self):
        self.level(8)
        self.choose("E", 1)
        self.f.pos = Vec2(40.5, 55.5)
        self.e.pos = Vec2(22.5, 49.0)
        self.cast("E", 24.0, 47.5)
        self.e.pos = Vec2(22.5, 47.6)
        self.tick(DT)
        self.assertEqual(self.e.mag_sign, 1)

    # --- R -----------------------------------------------------------------------------
    def test_magnet_bomb_pillar_pulls_opposite(self):
        self.level(8)
        self.choose("R", 0)
        self.f.pos = Vec2(40.5, 55.5)
        self.charge(self.e, 1)
        self.e.mag_sign = 1
        self.cast("R", 23.5, 47.5, hold=1.0)   # polarità "-"
        pl = self.match.mag_pillars[0]
        self.assertEqual(pl["sign"], -1)
        self.tick(0.5)
        self.assertEqual(self.grid.tiles[47][23], TILE_PILLAR)
        self.tick(0.4)
        self.assertLess(self.e.pos.dist(Vec2(23.5, 47.5)), 1.2)
        self.assertGreater(self.e.max_hp - self.e.hp, 0)
        self.tick(4.0)
        self.assertNotEqual(self.grid.tiles[47][23], TILE_PILLAR)

    def test_magnet_bomb_same_pushes_to_edge(self):
        self.level(8)
        self.choose("R", 0)
        self.f.pos = Vec2(40.5, 55.5)
        self.charge(self.e, 1)
        self.cast("R", 23.5, 47.5, hold=0.0)
        self.tick(0.9)
        self.assertGreater(self.e.pos.dist(Vec2(23.5, 47.5)), 5.5)

    def test_electric_terrain_charges_and_extends_range(self):
        self.level(8)
        self.choose("R", 1)
        self.cast("R", 24.5, 49.5, hold=1.0)
        self.tick(DT)
        # i due nemici ricevono "-" e si respingono subito
        self.assertTrue(any(ln["kind"] == "push" for ln in self.match.mag_links))
        mv = self.match._mag_on_cast(self.u, self.u.moveset["Q"].chosen)
        self.assertAlmostEqual(mv.range, 9.0 * 1.5)


if __name__ == "__main__":
    unittest.main()
