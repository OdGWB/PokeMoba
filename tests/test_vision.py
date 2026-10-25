import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.grid import Grid, TILE_BUSH
from engine.vec import Vec2
from engine.vision import VisionSystem
from engine.world import World

STATS = {"hp": 500, "attack": 40, "defense": 30, "sp_attack": 40, "sp_defense": 30, "speed": 50}


def make_poke(world, pos, team):
    return world.spawn_pokemon(pos=pos, team=team, dex=1, name="T", color=(0, 0, 0),
                               speed=3.5, base_stats=STATS)


class TestVision(unittest.TestCase):
    def setUp(self):
        self.grid = Grid.empty(20, 20)
        self.grid.tiles[5][8] = TILE_BUSH  # tiles[y][x] -> (x=8, y=5) cespuglio
        self.world = World(self.grid)
        self.vis = VisionSystem(self.grid)

    def test_tiles_visible_and_explored(self):
        make_poke(self.world, Vec2(5.5, 5.5), 0)  # vision 9
        self.assertTrue(self.vis.update(self.world, 0))
        self.assertTrue(self.vis.is_tile_visible(0, 5, 5))
        self.assertFalse(self.vis.is_tile_visible(0, 19, 19))
        self.assertTrue(self.vis.is_tile_explored(0, 5, 5))

    def test_enemy_in_range_visible(self):
        make_poke(self.world, Vec2(5.5, 5.5), 0)
        enemy = make_poke(self.world, Vec2(10.5, 5.5), 1)  # floor, entro 9
        self.vis.update(self.world, 0)
        self.assertTrue(self.vis.is_enemy_visible(0, enemy.id))

    def test_enemy_far_hidden(self):
        make_poke(self.world, Vec2(5.5, 5.5), 0)
        enemy = make_poke(self.world, Vec2(18.5, 18.5), 1)
        self.vis.update(self.world, 0)
        self.assertFalse(self.vis.is_enemy_visible(0, enemy.id))

    def test_bush_hides_until_close(self):
        ally = make_poke(self.world, Vec2(5.5, 5.5), 0)
        enemy = make_poke(self.world, Vec2(8.5, 5.5), 1)  # dentro il cespuglio, dist 3 > 2.6
        self.vis.update(self.world, 0)
        self.assertFalse(self.vis.is_enemy_visible(0, enemy.id))
        # Avvicino l'alleato: ora lo sbircia.
        ally.pos = Vec2(7.5, 5.5)
        self.vis.update(self.world, 0)
        self.assertTrue(self.vis.is_enemy_visible(0, enemy.id))

    def test_recompute_only_on_change(self):
        make_poke(self.world, Vec2(5.5, 5.5), 0)
        self.assertTrue(self.vis.update(self.world, 0))
        self.assertFalse(self.vis.update(self.world, 0))  # nessun cambiamento -> no ricalcolo


if __name__ == "__main__":
    unittest.main()
