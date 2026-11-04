import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.grid import TILE_BUSH
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
TED = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "teddiursa.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))
BIRD = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "noibat.json"))


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


class TestUrsaring(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.grid = m.grid
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.match._wave_timer = 1e9
        self.u = spawn(self.world, TED, Vec2(26.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(30.0, 47.5), 1)
        self.e.max_hp = self.e.hp = 50000.0
        self.match._update_regen = lambda dt: None

    def level(self, lv):
        self.match._gain_xp(self.u, CUMULATIVE_XP[lv] - self.u.xp + 1.0)
        self.match._update_evolution(0)

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

    def cast(self, slot, x, y):
        self.u.moveset[slot].cooldown_remaining = 0.0
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.u, slot, x, y)

    def step(self, sec):
        for i in range(int(round(sec / DT))):
            self.match.update(DT, i)

    def wild(self, pos, kind="camp"):
        w = self.world.spawn_wild(pos, kind, 3000.0, 10.0, 1.6, 1.2, 50.0, 30)
        return w

    def test_evolutions_and_types(self):
        self.level(3)
        self.assertEqual(self.u.name, "Teddiursa")
        self.level(4)
        self.assertEqual(self.u.name, "Ursaring")
        self.assertEqual(self.u.passive_id, "dentistretti")
        self.level(8)
        self.assertEqual(self.u.name, "Ursaluna")
        self.assertEqual(self.u.types, ["Ground", "Normal"])

    def test_honey_from_camp_and_heal(self):
        # Fermi sul posto: col raggio d'acquisizione i due si attaccherebbero da soli.
        self.u.order = self.e.order = "stop"
        for i in range(4):
            w = self.wild(Vec2(28.0, 45.0 + i))
            self.match._deal_damage(self.u, w, w.hp + 1.0)
        self.assertEqual(self.u.honey, 3)              # massimo 3 vasetti
        self.u.hp = self.u.max_hp * 0.3
        hp0 = self.u.hp
        self.match.update(DT, 0)
        self.assertEqual(self.u.honey, 2)
        self.assertAlmostEqual(self.u.hp - hp0, self.u.max_hp * 0.15, delta=1.0)
        self.u.hp = self.u.max_hp * 0.3
        self.step(1.0)
        self.assertEqual(self.u.honey, 2)              # una volta ogni 10 s
        self.step(9.2)
        self.assertEqual(self.u.honey, 1)

    def test_honey_bonus_vs_wild(self):
        w = self.wild(Vec2(28.0, 45.0))
        hp0 = w.hp
        self.match._deal_damage(self.u, w, 100.0)
        self.assertAlmostEqual(hp0 - w.hp, 130.0)
        hp1 = self.e.hp
        self.match._deal_damage(self.u, self.e, 100.0)
        self.assertAlmostEqual(hp1 - self.e.hp, 100.0)   # niente bonus sui Pokémon

    def test_guts_with_status_and_burn(self):
        self.level(4)
        self.match.update(DT, 0)
        atk = self.u.eff_attack()
        self.u.burn_until = self.match.time + 3.0
        self.match.update(DT, 1)
        self.assertAlmostEqual(self.u.eff_attack(), atk * 1.5, delta=0.5)   # niente -25%
        self.u.burn_until = -1.0
        self.u.root_until = self.match.time + 2.0   # paralisi
        self.match.update(DT, 2)
        self.assertTrue(self.u.guts_active)

    def test_slash_crit_bonus_and_hammer_arm(self):
        self.level(5)
        self.choose("Q", 1)
        self.e.pos = Vec2(28.0, 47.5)
        self.cast("Q", self.e.pos.x, self.e.pos.y)
        self.assertGreater(self.e.stun_until, self.match.time + 0.5)
        self.assertLess(self.u.slow_mult, 1.0)
        self.assertGreater(self.u.slow_until, self.match.time + 2.5)

    def test_sweet_scent_slows_and_reveals_in_bush(self):
        self.level(3)
        self.rank_all()
        self.assertGreater(self.u.moveset["W"].rank, 0)
        self.e.pos = Vec2(31.5, 47.5)
        self.grid.tiles[47][31] = TILE_BUSH
        self.u.vision = 2.0
        self.match.update(DT, 0)
        self.assertFalse(self.match.vision.is_enemy_visible(0, self.e.id))
        self.cast("W", 31.5, 47.5)
        self.step(0.2)
        self.assertLess(self.e.slow_mult, 1.0)
        self.assertTrue(self.match.vision.is_enemy_visible(0, self.e.id))
        self.step(4.2)
        self.assertFalse(self.match.honey_zones)
        self.assertFalse(self.match.vision.is_enemy_visible(0, self.e.id))

    def test_rest_heals_cleanses_and_guts_after(self):
        self.level(6)
        self.choose("W", 0)
        self.u.hp = self.u.max_hp * 0.2
        self.u.poison_until = self.match.time + 5.0
        self.u.poison_dps = 1.0
        missing = self.u.max_hp - self.u.hp
        hp0 = self.u.hp
        self.cast("W", self.u.pos.x, self.u.pos.y)
        self.assertAlmostEqual(self.u.hp - hp0, missing * 0.5, delta=1.0)
        self.assertLessEqual(self.u.poison_until, self.match.time)
        self.match._deal_damage(self.e, self.u, 10.0)
        self.assertGreater(self.u.sleep_until, self.match.time)   # il danno non sveglia
        self.step(2.2)
        self.assertLessEqual(self.u.sleep_until, self.match.time)
        self.assertTrue(self.u.guts_active)          # bonus per 4 s dopo il risveglio
        self.step(4.2)
        self.assertFalse(self.u.guts_active)

    def test_roar_fears(self):
        self.level(6)
        self.choose("W", 1)
        self.e.pos = Vec2(29.0, 47.5)
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.assertGreater(self.e.fear_until, self.match.time + 0.5)

    def test_body_slam_stops_on_first_enemy_and_paralyzes(self):
        self.level(3)
        self.rank_all()
        self.e.pos = Vec2(29.0, 47.5)
        hp0 = self.e.hp
        self.cast("E", 31.0, 47.5)
        self.step(0.4)
        self.assertLess(self.u.pos.x, self.e.pos.x)    # si ferma davanti al nemico
        self.assertLess(self.e.hp, hp0)
        self.assertGreater(self.e.root_until, self.match.time)

    def test_bulldoze_slows_but_not_flying(self):
        self.level(7)
        self.choose("E", 0)
        bird = spawn(self.world, BIRD, Vec2(30.5, 48.3), 1)
        bird.max_hp = bird.hp = 50000.0
        self.e.pos = Vec2(30.5, 46.8)
        hp_b = bird.hp
        self.cast("E", 30.5, 47.5)
        self.step(0.4)
        self.assertLess(self.e.slow_mult, 1.0)
        self.assertEqual(bird.hp, hp_b)

    def test_full_moon_leap_stun_and_growth(self):
        self.level(8)
        self.choose("R", 0)
        self.e.pos = Vec2(33.0, 47.5)
        hp_max = self.u.max_hp
        self.u.hp = hp_max * 0.5
        self.cast("R", 33.0, 47.5)
        self.step(0.7)
        self.assertAlmostEqual(self.u.pos.x, 33.0, delta=1.2)
        self.assertGreater(self.e.stun_until, self.match.time)
        self.assertAlmostEqual(self.u.max_hp, hp_max * 1.25, delta=1.0)
        self.assertAlmostEqual(self.u.hp, hp_max * 0.75, delta=hp_max * 0.05)
        self.match._apply_slow(self.u, 0.5, 2.0)
        self.assertEqual(self.u.slow_mult, 1.0)       # immune ai rallentamenti
        self.step(6.2)
        self.assertAlmostEqual(self.u.max_hp, hp_max, delta=1.0)

    def test_full_moon_cleave(self):
        self.level(8)
        self.choose("R", 0)
        self.u.moon_until = self.match.time + 5.0
        self.u.moon_cleave = 1.3
        e2 = spawn(self.world, FOE, Vec2(28.8, 48.0), 1)
        e2.max_hp = e2.hp = 50000.0
        self.e.pos = Vec2(28.0, 47.5)
        hp2 = e2.hp
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._ursa_after_aa(self.u, self.e)
        self.assertLess(e2.hp, hp2)

    def test_earthquake_pulses_skip_flying(self):
        self.level(8)
        self.choose("R", 1)
        bird = spawn(self.world, BIRD, Vec2(28.5, 48.0), 1)
        bird.max_hp = bird.hp = 50000.0
        self.e.pos = Vec2(28.5, 47.0)
        hp_e, hp_b = self.e.hp, bird.hp
        self.cast("R", self.u.pos.x, self.u.pos.y)
        self.step(1.1)
        self.assertLess(self.e.hp, hp_e)
        self.assertLess(self.e.slow_mult, 1.0)
        self.assertEqual(bird.hp, hp_b)
        self.step(2.5)
        self.assertFalse(self.match.quakes)


if __name__ == "__main__":
    unittest.main()
