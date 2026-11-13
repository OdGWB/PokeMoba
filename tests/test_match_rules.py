"""Regole GENERALI della partita (engine/match.py), indipendenti dai Pokémon:
ondate, crescita dei minion, torri, nucleo, oro, esperienza, respawn, vittoria."""
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from engine.content import load_map, load_pokemon_def
from engine.match import XP_RADIUS, Match
from engine.stats import respawn_time
from engine.vec import Vec2
from engine.world import World

DT = 1 / 30
FOE = load_pokemon_def(os.path.join(ROOT, "tests", "fixtures", "dummy_foe.json"))


def spawn(world, pos, team):
    d = FOE
    p = world.spawn_pokemon(pos=pos, team=team, dex=d.dex, name=d.name, color=d.color,
                            speed=d.base_speed, is_bot=False, types=d.types,
                            base_stats=d.base_stats, moves=d.moves, evolutions=d.evolutions,
                            role=d.role, passive=d.passive, attack_range=d.attack_range,
                            attack_cooldown=d.attack_cooldown, attack_fx=d.attack_fx)
    p.radius = d.radius
    p.spawn_pos = Vec2(pos.x, pos.y)
    p.order = "idle"
    return p


class Base(unittest.TestCase):
    def setUp(self):
        random.seed(1)
        self.map = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        self.world = World(self.map.grid)
        self.match = Match(self.world, self.map)

    def run_for(self, sec):
        for i in range(int(round(sec / DT))):
            self.match.update(DT, i)

    def towers(self, team, lane=None):
        return [s for s in self.world.structures() if s.kind == "tower" and s.team == team
                and (lane is None or s.lane == lane)]

    def core(self, team):
        return next(c for c in self.world.cores() if c.team == team)

    def minion(self, team, mtype="melee"):
        self.match._spawn_minion(team, "mid", mtype)
        return max(self.world.minions(), key=lambda m: m.id)


class TestWaves(Base):
    def test_first_wave_composition(self):
        self.run_for(config.FIRST_WAVE_TIME + 6 * config.MINION_SPAWN_GAP + 0.2)
        n_lanes = len(self.map.lanes)
        for team in (0, 1):
            ms = [m for m in self.world.minions() if m.team == team]
            self.assertEqual(len(ms), n_lanes * (config.MELEE_PER_WAVE + config.CASTER_PER_WAVE))
            kinds = sorted(m.minion_type for m in ms if m.lane == "mid")
            self.assertEqual(kinds, ["caster"] * config.CASTER_PER_WAVE
                             + ["melee"] * config.MELEE_PER_WAVE)

    def test_cannon_every_n_waves(self):
        self.match._wave_number = config.CANNON_EVERY - 1
        self.match._wave_timer = 0.0
        self.match._update_waves(0.0)
        queued = [q[3] for q in self.match._spawn_queue if q[1] == 0 and q[2] == "mid"]
        self.assertIn("cannon", queued)
        self.match._spawn_queue.clear()
        self.match._wave_timer = 0.0
        self.match._update_waves(0.0)   # ondata successiva: niente cannone
        queued = [q[3] for q in self.match._spawn_queue if q[1] == 0 and q[2] == "mid"]
        self.assertNotIn("cannon", queued)

    def test_minions_grow_with_time(self):
        early = self.minion(0)
        self.match.time = 600.0
        late = self.minion(0)
        k = 1.0 + config.MINION_SCALE_PER_MIN * 10.0
        self.assertAlmostEqual(late.max_hp, early.max_hp * k, places=3)


class TestTowersAndCore(Base):
    def test_core_invulnerable_while_towers_stand(self):
        core = self.core(1)
        hp = core.hp
        hero = spawn(self.world, Vec2(core.pos.x + 2, core.pos.y), 0)
        self.match._deal_damage(hero, core, 500.0)
        self.assertEqual(core.hp, hp)

    def test_core_exposed_when_a_lane_is_empty(self):
        core = self.core(1)
        hero = spawn(self.world, Vec2(core.pos.x + 2, core.pos.y), 0)
        for t in self.towers(1, "top"):
            self.match._deal_damage(hero, t, 1e9)
        self.assertTrue(all(not t.alive for t in self.towers(1, "top")))
        self.assertTrue(any(t.alive for t in self.towers(1, "mid")))
        self.assertEqual(self.match._alive_towers(1), 0)
        hp = core.hp
        self.match._deal_damage(hero, core, 500.0)
        self.assertLess(core.hp, hp)

    def test_core_destroyed_ends_match(self):
        core = self.core(1)
        hero = spawn(self.world, Vec2(core.pos.x + 2, core.pos.y), 0)
        for t in self.towers(1, "mid"):
            self.match._deal_damage(hero, t, 1e9)
        self.match._deal_damage(hero, core, 1e9)
        self.assertFalse(core.alive)
        self.assertEqual(self.match.winner, 0)
        t = self.match.time
        self.match.update(DT, 0)
        self.assertEqual(self.match.time, t)   # partita finita: il tempo si ferma

    def test_tower_prefers_minions_and_ignores_passive_heroes(self):
        tower = self.towers(1, "mid")[0]
        d = (tower.pos - Vec2(self.map.grid.width / 2, self.map.grid.height / 2)).normalized()
        spot = tower.pos - d * 3.0
        hero = spawn(self.world, spot, 0)
        self.match._combat_hash.rebuild(self.world.combatants())
        self.match._tower_fire(tower)
        self.assertIsNone(tower.target_id)   # un Pokémon che non ha fatto nulla: ignorato
        m = self.minion(0)
        m.pos = Vec2(spot.x + 0.5, spot.y)
        self.match._combat_hash.rebuild(self.world.combatants())
        tower.attack_timer = 0.0
        self.match._tower_fire(tower)
        self.assertEqual(tower.target_id, m.id)
        # Il Pokémon colpisce un nemico: la torre passa a lui finché il minion muore.
        hero._tower_aggro_at = self.match.time
        m.alive = False
        self.match._combat_hash.rebuild(self.world.combatants())
        tower.attack_timer = 0.0
        self.match._tower_fire(tower)
        self.assertEqual(tower.target_id, hero.id)


class TestRewards(Base):
    def test_last_hit_gold_only_to_pokemon(self):
        hero = spawn(self.world, Vec2(50, 50), 0)
        m = self.minion(1)
        m.pos = Vec2(51, 50)
        g0 = hero.gold
        self.match._deal_damage(hero, m, 1e9)
        self.assertEqual(hero.gold - g0, self.match._minion_gold(m))
        m2 = self.minion(1)
        m2.pos = Vec2(51, 50)
        tower = self.towers(0)[0]
        g1 = hero.gold
        self.match._deal_damage(tower, m2, 1e9)   # ucciso dalla torre: niente oro
        self.assertEqual(hero.gold, g1)

    def test_minion_xp_shared_in_radius(self):
        a = spawn(self.world, Vec2(50, 50), 0)
        b = spawn(self.world, Vec2(52, 50), 0)
        far = spawn(self.world, Vec2(50 + XP_RADIUS + 3, 50), 0)
        m = self.minion(1)
        m.pos = Vec2(51, 50)
        xa, xb, xf = a.xp, b.xp, far.xp
        self.match._award_xp(m, a)
        share = Match._XP_SHARE[2]
        self.assertAlmostEqual(a.xp - xa, m.xp * share, places=4)
        self.assertAlmostEqual(b.xp - xb, m.xp * share, places=4)
        self.assertEqual(far.xp, xf)

    def test_kill_xp_and_respawn(self):
        killer = spawn(self.world, Vec2(50, 50), 0)
        victim = spawn(self.world, Vec2(51, 50), 1)
        victim.level = 5
        x0 = killer.xp
        self.match._award_xp(victim, killer)
        self.assertAlmostEqual(killer.xp - x0, (140 + 40 * 5) * 1.2, places=4)  # vittima più alta
        victim.pos = Vec2(60, 60)
        self.match._deal_damage(killer, victim, 1e9)
        self.assertFalse(victim.alive)
        self.assertAlmostEqual(victim.respawn_timer, respawn_time(victim.level))
        self.match._update_respawns(victim.respawn_timer + 0.01)
        self.assertTrue(victim.alive)
        self.assertEqual(victim.hp, victim.max_hp)
        self.assertEqual((victim.pos.x, victim.pos.y), (victim.spawn_pos.x, victim.spawn_pos.y))


if __name__ == "__main__":
    unittest.main()
