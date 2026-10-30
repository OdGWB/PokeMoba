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
CHARC = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "charcadet.json"))
FOE = load_pokemon_def(os.path.join(ROOT, "data", "pokemon", "squirtle.json"))


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


class TestCharcadet(unittest.TestCase):
    def setUp(self):
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        for y in range(30, 60):
            for x in range(10, 60):
                m.grid.tiles[y][x] = 0
        self.world = World(m.grid)
        self.match = Match(self.world, m)
        self.c = spawn(self.world, CHARC, Vec2(26.5, 47.5), 0)
        self.e = spawn(self.world, FOE, Vec2(28.0, 47.5), 1)
        self.e.max_hp = self.e.hp = 50000.0
        self.match._update_regen = lambda dt: None   # la rigenerazione (% HP max) coprirebbe i colpi

    def level(self, lv):
        self.match._gain_xp(self.c, CUMULATIVE_XP[lv] - self.c.xp + 1.0)
        self.match._update_evolution(0)

    def choose(self, slot, idx):
        if slot not in self.c.pending_choices:
            self.c.pending_choices.append(slot)
        evolution.apply_choice(self.c, slot, idx)
        self.rank_all()

    def rank_all(self):
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

    def test_armature_bars_count_only_pokemon(self):
        self.match._deal_damage(self.e, self.c, 30.0)
        self.match._deal_damage(self.c, self.e, 12.0)
        minion = self.world.spawn_minion(Vec2(27.0, 46.0), 1, "mid", [Vec2(27.0, 46.0)],
                                         (200, 60, 60))
        self.match._deal_damage(self.c, minion, 99.0)
        self.assertEqual(self.c.fausta, 30.0)
        self.assertEqual(self.c.infausta, 12.0)

    def test_evolves_armarouge_when_fausta_leads(self):
        self.c.fausta, self.c.infausta = 100.0, 40.0
        self.level(8)
        self.assertEqual(self.c.name, "Armarouge")
        self.assertEqual(self.c.types, ["Fire", "Psychic"])
        self.assertEqual(self.c.passive_id, "guardia")
        self.assertEqual(self.c.moveset["Q"].chosen.id, "armorcannon")
        self.assertEqual([u.id for u in self.c.moveset["R"].upgrades], ["floatarmor", "psychic"])

    def test_tie_goes_to_ceruledge_and_q_rank_kept(self):
        self.level(7)
        self.rank_all()
        rq = self.c.moveset["Q"].rank
        self.assertEqual(self.c.moveset["Q"].chosen.id, "incinerateplus")   # liv.5, senza scelta
        self.level(8)
        self.assertEqual(self.c.name, "Ceruledge")
        self.assertEqual(self.c.moveset["Q"].chosen.id, "bitterblade")
        self.assertEqual(self.c.moveset["Q"].rank, rq)

    def test_incinerate_breaks_shield(self):
        self.level(1)
        self.rank_all()
        self.match._apply_shield(self.e, 200.0, 5.0)
        self.cast("Q", self.e.pos.x, self.e.pos.y)
        self.assertLess(self.e.shield, 200.0 * 0.8 + 1e-6)

    def test_night_shade_true_damage(self):
        self.level(6)
        self.choose("W", 0)
        self.e.pos = Vec2(31.0, 47.5)
        hp0 = self.e.hp
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.assertTrue(self.match.shades)
        self.step(1.0)
        rank = self.c.moveset["W"].rank
        mv = self.c.moveset["W"].chosen
        expect = mv.power_at(rank) + mv.effects["per_level"][rank - 1] * self.c.level
        self.assertAlmostEqual(hp0 - self.e.hp, expect, delta=1.0)

    def test_clear_smog_purges_buffs(self):
        self.level(6)
        self.choose("W", 1)
        self.match._apply_atk(self.e, 1.3, 6.0)
        self.match._apply_speed(self.e, 1.3, 6.0)
        self.cast("W", self.e.pos.x, self.e.pos.y)
        self.step(0.1)
        self.assertEqual(self.e.atk_mult, 1.0)
        self.assertEqual(self.e.speed_mult, 1.0)

    def test_armor_cannon_charge_and_self_debuff(self):
        self.c.fausta = 10.0
        self.level(8)
        self.rank_all()
        d0 = self.c.eff_defense()
        self.e.pos = Vec2(32.0, 47.5)
        hp0 = self.e.hp
        self.cast("Q", self.e.pos.x, self.e.pos.y)
        self.assertTrue(self.match.cannon_charges)
        self.assertEqual(self.e.hp, hp0)
        self.step(1.2)
        self.assertLess(self.e.hp, hp0)
        self.assertAlmostEqual(self.c.eff_defense(), d0 * 0.8, delta=0.5)

    def test_float_armor_blocks_projectiles(self):
        self.c.fausta = 10.0
        self.level(8)
        self.choose("R", 0)
        self.cast("R", self.c.pos.x, self.c.pos.y)
        for k in range(4):
            self.match.projectiles.append({
                "pos": Vec2(self.c.pos.x + 1.2, self.c.pos.y), "dir": Vec2(-1, 0), "speed": 0.1,
                "left": 5.0, "radius": 0.3, "team": 1, "caster_id": self.e.id,
                "mv": self.e.moveset["Q"].chosen, "rank": 1, "mtype": "Water"})
            self.step(0.1)
        self.assertEqual(self.c.armor_blocks, 0)
        self.assertEqual(len(self.match.projectiles), 1)

    def test_guard_shields_low_ally(self):
        self.c.fausta = 10.0
        self.level(8)
        ally = spawn(self.world, FOE, Vec2(29.0, 49.0), 0)
        ally.hp = ally.max_hp * 0.2
        self.step(0.1)
        self.assertGreater(ally.shield, 0.0)
        self.assertGreater(self.c.guard_ready_at, self.match.time + 25.0)

    def test_double_blade_second_hit(self):
        self.level(8)
        self.e.pos = Vec2(27.8, 47.5)
        self.c.target_id = self.e.id
        hp0 = self.e.hp
        self.step(1.0)
        self.assertLess(self.e.hp, hp0)
        hits = [ev for ev in self.match.fx_events if ev.get("fx") == "ghostslash"]
        self.assertTrue(hits)

    def test_grudge_blade_untargetable_and_heals(self):
        self.level(8)
        self.choose("R", 0)
        self.e.pos = Vec2(31.0, 47.5)
        self.c.hp = self.c.max_hp * 0.5
        hp_c, hp_e = self.c.hp, self.e.hp
        self.cast("R", self.e.pos.x, self.e.pos.y)
        self.assertLess(self.c.pos.dist(self.e.pos), 1.5)
        self.step(0.5)
        self.assertGreater(self.c.untargetable_until, self.match.time)
        self.step(1.2)
        self.assertLess(self.e.hp, hp_e)
        self.assertGreater(self.c.hp, hp_c)
        self.assertFalse(self.match.flurries)

    def test_shadow_claw_range_and_crit(self):
        self.level(8)
        self.choose("R", 1)
        r0 = self.match._auto_reach(self.c)
        self.cast("R", self.c.pos.x, self.c.pos.y)
        self.assertAlmostEqual(self.match._auto_reach(self.c), r0 * 1.5)
        base = self.match._aa_ghost_damage(self.c, self.e)
        self.assertGreater(base, 0.0)


if __name__ == "__main__":
    unittest.main()
