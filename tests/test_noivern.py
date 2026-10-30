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
NOI = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "noibat.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "squirtle.json"))


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


class TestNoivern(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.grid = m.grid
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.n = spawn(self.world, NOI, Vec2(26.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(30.0, 47.5), 1)
        self.e.max_hp = self.e.hp = 50000.0
        self.match._update_regen = lambda dt: None   # la rigenerazione (% HP max) coprirebbe i colpi

    def level(self, lv):
        self.match._gain_xp(self.n, CUMULATIVE_XP[lv] - self.n.xp + 1.0)
        self.match._update_evolution(0)

    def choose(self, slot, idx):
        if slot not in self.n.pending_choices:
            self.n.pending_choices.append(slot)
        evolution.apply_choice(self.n, slot, idx)
        self.rank_all()

    def rank_all(self):
        for _ in range(20):
            for s in ("R", "Q", "W", "E"):
                if skills.can_rank_up(self.n, s):
                    skills.rank_up(self.n, s)

    def cast(self, slot, x, y):
        self.n.moveset[slot].cooldown_remaining = 0.0
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.n, slot, x, y)

    def step(self, sec):
        for i in range(int(round(sec / DT))):
            self.match.update(DT, i)

    def aa(self, n=1):
        """`n` attacchi base completi sul nemico."""
        for _ in range(n):
            self.n.attack_timer = 0.0
            self.n.target_id = self.e.id
            self.match._combat_hash.rebuild(self.world.combatants())
            self.match._pokemon_auto_attack(self.n)
            self.match.time = self.n.aa_until + 0.01
            self.match._pokemon_auto_attack(self.n)

    def test_evolves_into_noivern_at_8(self):
        self.level(7)
        self.assertEqual(self.n.name, "Noibat")
        self.level(8)
        self.assertEqual(self.n.name, "Noivern")
        self.assertEqual(self.n.types, ["Flying", "Dragon"])
        self.assertEqual(self.n.passive_id, "ecolocalizzazione")

    def test_basic_attack_is_special(self):
        self.e.stats.sp_defense = 0.0
        hp0 = self.e.hp
        self.aa()
        low_spdef = hp0 - self.e.hp
        self.e.stats.sp_defense = 300.0
        hp1 = self.e.hp
        self.aa()
        self.assertGreater(low_spdef, (hp1 - self.e.hp) * 1.5)   # mitigato dalla Dif. Sp.

    def test_item_attack_becomes_sp_attack(self):
        self.match._item_bonus_for = lambda p: {"attack": 40.0, "attack_speed": 0.2}
        self.match._recompute_stats(self.n)
        self.assertNotIn("attack", self.n.item_bonus)
        self.assertEqual(self.n.item_bonus["sp_attack"], 40.0)
        self.assertEqual(self.n.item_bonus["attack_speed"], 0.2)   # gli altri bonus restano
        self.assertAlmostEqual(self.n.ap, 40.0)

    def test_third_attack_pings_and_reveals_bush(self):
        self.e.pos = Vec2(30.5, 47.5)
        hidden = spawn(self.world, FOE, Vec2(33.5, 47.5), 1)
        self.grid.tiles[47][33] = TILE_BUSH
        self.n.vision = 3.0   # il nemico in cespuglio e' anche fuori portata visiva
        self.match.update(DT, 0)
        self.assertFalse(self.match.vision.is_enemy_visible(0, hidden.id))
        self.aa(2)
        self.assertEqual(self.n.echo_count, 2)
        self.assertFalse(self.match.sonar_pings)
        self.aa()
        self.assertEqual(self.n.echo_count, 0)
        self.assertEqual(len(self.match.sonar_pings), 1)
        self.step(0.1)
        self.assertTrue(self.match.vision.is_enemy_visible(0, hidden.id))
        self.step(2.1)
        self.assertFalse(self.match.vision.is_enemy_visible(0, hidden.id))

    def test_supersonic_confuses(self):
        self.level(1)
        self.rank_all()
        self.cast("Q", self.e.pos.x, self.e.pos.y)
        self.assertGreater(self.e.confuse_until, self.match.time + 1.0)

    def test_dragon_pulse_hits_all_in_line(self):
        self.level(5)
        self.choose("Q", 0)
        e2 = spawn(self.world, FOE, Vec2(34.0, 47.5), 1)
        e2.max_hp = e2.hp = 50000.0
        hp1, hp2 = self.e.hp, e2.hp
        self.cast("Q", 40.0, 47.5)
        self.assertLess(self.e.hp, hp1)
        self.assertLess(e2.hp, hp2)

    def test_screech_lowers_both_defenses(self):
        self.level(3)
        self.rank_all()
        self.assertGreater(self.n.moveset["W"].rank, 0)
        self.e.pos = Vec2(28.5, 47.5)
        d0, s0 = self.e.eff_defense(), self.e.eff_sp_defense()
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.match.update(DT, 0)
        self.assertAlmostEqual(self.e.eff_defense(), d0 * 0.9, delta=0.5)
        self.assertAlmostEqual(self.e.eff_sp_defense(), s0 * 0.9, delta=0.5)

    def test_whirlwind_pushes_4_tiles(self):
        self.level(6)
        self.choose("W", 1)
        self.e.pos = Vec2(28.0, 47.5)
        self.cast("W", self.n.pos.x, self.n.pos.y)
        self.assertAlmostEqual(self.e.pos.x, 32.0, delta=0.05)

    def test_acrobatics_plus_two_charges(self):
        self.level(7)
        self.choose("E", 0)
        ms = self.n.moveset["E"]
        self.match._cast(self.n, "E", 40.0, 47.5)
        ms.cooldown_remaining = 0.0
        self.assertTrue(ms.ready)
        self.match._cast(self.n, "E", 20.0, 47.5)
        ms.cooldown_remaining = 0.0
        self.assertFalse(ms.ready)

    def test_hurricane_drags_and_confuses_on_release(self):
        self.level(8)
        self.choose("R", 0)
        self.e.pos = Vec2(28.0, 47.5)
        self.cast("R", 40.0, 47.5)
        self.step(1.0)
        self.assertIn(self.e.id, self.match.hurricanes[0]["caught"])
        self.assertGreater(self.e.pos.x, 28.5)          # trascinato in avanti
        self.assertGreater(self.e.stun_until, self.match.time)
        hp_mid = self.e.hp
        self.step(3.2)
        self.assertFalse(self.match.hurricanes)
        self.assertLess(self.e.hp, hp_mid)
        self.assertGreater(self.e.confuse_until, self.match.time)
        self.assertLessEqual(self.e.stun_until, self.match.time)

    def test_hurricane_bigger_in_rain(self):
        self.level(8)
        self.choose("R", 0)
        self.match.jungle.weather = "rain"
        self.cast("R", 40.0, 47.5)
        self.assertAlmostEqual(self.match.hurricanes[0]["radius"], 1.5 * 1.5)

    def test_draco_meteor_delay_and_spa_drop(self):
        self.level(8)
        self.choose("R", 1)
        self.e.pos = Vec2(36.5, 47.5)   # fuori dalla portata degli attacchi base
        hp0 = self.e.hp
        self.cast("R", self.e.pos.x, self.e.pos.y)
        self.step(0.8)
        self.assertEqual(self.e.hp, hp0)
        self.step(0.4)
        self.assertLess(self.e.hp, hp0)
        self.assertAlmostEqual(self.match._spa_down_mult(self.n), 0.6)
        self.step(6.2)
        self.assertEqual(self.match._spa_down_mult(self.n), 1.0)


if __name__ == "__main__":
    unittest.main()
