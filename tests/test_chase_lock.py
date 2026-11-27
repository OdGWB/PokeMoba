"""Aggancio del bersaglio: un ordine di movimento lo molla davvero (da fermo non si
reinsegue), e un bersaglio irraggiungibile non tiene il Pokemon incollato al muro."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_basic_attack import DT, TED, TestBasicAttack, spawn   # noqa: E402
from engine.vec import Vec2   # noqa: E402
from sim.commands import AttackCommand, AttackMoveCommand, MoveCommand   # noqa: E402
from sim.simulation import Simulation   # noqa: E402


class TestChaseLock(unittest.TestCase):
    # stesse impalcature dei test dell'attacco base, senza ereditarne i test
    foe = TestBasicAttack.foe
    vis = TestBasicAttack.vis
    step = TestBasicAttack.step

    def setUp(self):
        TestBasicAttack.setUp(self)
        self.sim = Simulation(self.world, DT, self.match)
        self.p = spawn(self.world, self.match, TED, Vec2(27.5, 47.5), 0)
        self.t = self.foe(Vec2(30.5, 47.5))      # un po' oltre la portata di Teddiursa

    def run_ticks(self, n):
        for _ in range(n):
            self.sim.step()
            self.vis()

    def test_move_order_drops_lock_and_idle_does_not_rechase(self):
        self.sim.queue_command(AttackCommand(seq=1, entity_id=self.p.id, target_id=self.t.id))
        self.run_ticks(10)
        self.assertEqual(self.p.order, "attack")
        self.sim.queue_command(MoveCommand(seq=2, entity_id=self.p.id, x=24.5, y=47.5))
        self.run_ticks(120)
        self.assertEqual(self.p.order, "idle")
        x = self.p.pos.x
        self.run_ticks(60)
        self.assertAlmostEqual(self.p.pos.x, x, places=3)   # fermo: niente re-lock

    def test_unreachable_target_is_given_up(self):
        for y in range(44, 52):
            for x in range(29, 40):
                self.world.grid.tiles[y][x] = 1        # blocco di muro attorno al bersaglio
        self.t.pos = Vec2(34.5, 47.5)
        self.sim.queue_command(AttackCommand(seq=1, entity_id=self.p.id, target_id=self.t.id))
        self.run_ticks(int(4.0 / DT))
        self.assertEqual(self.p.order, "idle")             # ha rinunciato
        x = self.p.pos.x
        self.run_ticks(60)
        self.assertAlmostEqual(self.p.pos.x, x, places=2)  # e non lo reinsegue

    def test_attackmove_away_ignores_enemy_behind(self):
        self.t.pos = Vec2(25.5, 47.5)                      # alle spalle, a portata
        self.sim.queue_command(AttackMoveCommand(seq=1, entity_id=self.p.id, x=45.5, y=47.5))
        x0 = self.p.pos.x
        self.run_ticks(30)
        self.assertGreater(self.p.pos.x, x0 + 2.0)         # se ne va, niente muro invisibile
        self.assertIsNone(self.p.target_id)

    def test_attackmove_chase_has_a_leash(self):
        self.sim.queue_command(AttackMoveCommand(seq=1, entity_id=self.p.id, x=90.5, y=47.5))
        dropped = False
        for _ in range(int(8.0 / DT)):                     # il bersaglio scappa sempre avanti
            self.t.pos = Vec2(self.p.pos.x + 3.0, 47.5)
            self.sim.step()
            self.vis()
            dropped = dropped or self.match._chase_skipped(self.p) == self.t.id
        self.assertTrue(dropped)                           # a guinzaglio finito lo molla


if __name__ == "__main__":
    unittest.main()
