import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import evolution, skills
from engine.content import load_map, load_pokemon_def
from engine.match import Match
from engine.stats import CUMULATIVE_XP
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
CORVI = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "rookidee.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "charmander.json"))


def spawn(world, d, pos, team):
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=False, types=d.types,
                            base_stats=d.base_stats, moves=d.moves, evolutions=d.evolutions,
                            role=d.role, passive=d.passive, attack_range=d.attack_range,
                            attack_cooldown=d.attack_cooldown)
    p.radius = d.radius
    p.spawn_pos = Vec2(2.0, 98.0)   # lontano dalla fontana: niente rigenerazione
    p.order = "idle"
    return p


class TestCorviknight(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.c = spawn(self.world, CORVI, Vec2(26.5, 47.5), 0)

    def level(self, lv):
        self.match._gain_xp(self.c, CUMULATIVE_XP[lv] + 1.0)
        self.match._update_evolution(0)

    def choose(self, slot, idx):
        if slot not in self.c.pending_choices:
            self.c.pending_choices.append(slot)
        evolution.apply_choice(self.c, slot, idx)
        for _ in range(20):
            for s in ("R", "Q", "W", "E"):
                if skills.can_rank_up(self.c, s):
                    skills.rank_up(self.c, s)

    def cast(self, slot, x, y):
        self.c.moveset[slot].cooldown_remaining = 0.0
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._cast(self.c, slot, x, y)

    def step(self, sec):
        for i in range(int(round(sec / DT))):
            self.match.update(DT, i)

    def test_evolution_types_and_vision(self):
        self.step(0.1)
        self.assertEqual(self.c.vision, 12.0)          # Sguardofermo: 9 +30%
        self.level(4)
        self.assertEqual(self.c.name, "Corvisquire")
        self.level(8)
        self.assertEqual(self.c.name, "Corviknight")
        self.assertEqual(self.c.types, ["Flying", "Steel"])
        self.assertEqual(self.c.passive_id, "specchiarmatura")

    def test_mirror_armor(self):
        self.level(8)
        e = spawn(self.world, FOE, Vec2(28.0, 47.5), 1)
        self.match._apply_hit_effects(e, self.c, {"slow": {"mult": 0.5, "duration": 2.0}})
        self.assertLess(self.c.slow_until, self.match.time)
        self.assertGreater(e.slow_until, self.match.time)
        # Stesso nemico entro 12 s: la riduzione la subisce.
        self.match._apply_hit_effects(e, self.c, {"def_debuff": {"amount": 10, "duration": 2.0}})
        self.assertGreater(self.c.def_debuff_until, self.match.time)

    def test_taunt(self):
        self.level(6)
        self.choose("W", 0)
        e = spawn(self.world, FOE, Vec2(29.5, 47.5), 1)
        self.cast("W", e.pos.x, e.pos.y)
        self.assertEqual(e.taunt_src, self.c.id)
        e.pending_cast = ("Q", 40.0, 47.5)
        self.step(0.5)
        self.assertEqual(e.target_id, self.c.id)
        self.assertIsNone(e.pending_cast)
        self.step(1.5)
        self.assertLess(e.taunt_until, self.match.time)

    def test_flying_taxi(self):
        self.level(8)
        self.choose("R", 0)
        ally = spawn(self.world, FOE, Vec2(28.0, 47.5), 0)
        self.cast("R", 45.0, 47.5)
        self.step(1.7)
        self.assertGreater(ally.untargetable_until, self.match.time)
        self.step(1.5)
        self.assertFalse(self.match.taxi_flights)
        self.assertLess(self.c.pos.dist(Vec2(45.0, 47.5)), 0.8)
        self.assertLess(ally.pos.dist(self.c.pos), 2.2)

    def test_roost_drops_flying(self):
        self.level(8)
        self.choose("E", 0)
        self.c.hp = self.c.max_hp * 0.5
        self.cast("E", self.c.pos.x, self.c.pos.y)
        self.assertEqual(self.c.types, ["Steel"])
        self.step(3.2)
        self.assertEqual(self.c.types, ["Flying", "Steel"])


if __name__ == "__main__":
    unittest.main()
