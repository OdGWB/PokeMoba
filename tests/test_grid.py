import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.grid import Grid, TILE_FLOOR, TILE_WALL


class TestGrid(unittest.TestCase):
    def setUp(self):
        # 5x3, muro centrale in (2,1)
        self.grid = Grid.from_rows([
            [0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0],
        ])

    def test_dimensions(self):
        self.assertEqual(self.grid.width, 5)
        self.assertEqual(self.grid.height, 3)

    def test_walkable(self):
        self.assertTrue(self.grid.is_walkable(0, 0))
        self.assertFalse(self.grid.is_walkable(2, 1))
        # Fuori dai bordi = non calpestabile.
        self.assertFalse(self.grid.is_walkable(-1, 0))
        self.assertFalse(self.grid.is_walkable(5, 0))

    def test_out_of_bounds_is_wall(self):
        self.assertEqual(self.grid.tile_at(99, 99), TILE_WALL)

    def test_line_of_sight(self):
        # Linea orizzontale libera sulla riga 0.
        self.assertTrue(self.grid.line_of_sight(0.5, 0.5, 4.5, 0.5))
        # Linea che passa dal muro (2,1).
        self.assertFalse(self.grid.line_of_sight(0.5, 1.5, 4.5, 1.5))

    def test_unequal_rows_raise(self):
        with self.assertRaises(ValueError):
            Grid.from_rows([[0, 0], [0]])


if __name__ == "__main__":
    unittest.main()
