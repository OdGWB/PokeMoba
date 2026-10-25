import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.grid import Grid
from engine.pathfinding import find_path, smooth_path


class TestPathfinding(unittest.TestCase):
    def test_straight_path(self):
        grid = Grid.empty(10, 1)
        path = find_path(grid, (0, 0), (9, 0))
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (9, 0))

    def test_no_path_when_blocked(self):
        # Colonna di muri che divide la mappa in due.
        rows = [[0, 1, 0] for _ in range(3)]
        grid = Grid.from_rows(rows)
        self.assertEqual(find_path(grid, (0, 0), (2, 0)), [])

    def test_path_around_wall(self):
        # Muro verticale con un varco in basso.
        rows = [
            [0, 1, 0],
            [0, 1, 0],
            [0, 0, 0],
        ]
        grid = Grid.from_rows(rows)
        path = find_path(grid, (0, 0), (2, 0))
        self.assertTrue(path)
        self.assertEqual(path[0], (0, 0))
        self.assertEqual(path[-1], (2, 0))
        # Non deve attraversare i tile muro.
        for (x, y) in path:
            self.assertTrue(grid.is_walkable(x, y))

    def test_no_corner_cutting(self):
        # Diagonale che toccherebbe l'angolo di un muro: deve aggirarlo.
        rows = [
            [0, 1],
            [0, 0],
        ]
        grid = Grid.from_rows(rows)
        path = find_path(grid, (0, 0), (1, 1))
        # Il passo (0,0)->(1,1) taglierebbe l'angolo del muro (1,0): vietato.
        self.assertNotIn((1, 0), path)
        self.assertEqual(path[-1], (1, 1))
        # Deve passare per (0,1).
        self.assertIn((0, 1), path)

    def test_goal_equals_start(self):
        grid = Grid.empty(5, 5)
        self.assertEqual(find_path(grid, (2, 2), (2, 2)), [(2, 2)])

    def test_smoothing_reduces_waypoints(self):
        grid = Grid.empty(10, 1)
        path = find_path(grid, (0, 0), (9, 0))
        smoothed = smooth_path(grid, path)
        # Una linea retta libera si riduce a start + goal.
        self.assertEqual(len(smoothed), 2)
        self.assertAlmostEqual(smoothed[0][0], 0.5)
        self.assertAlmostEqual(smoothed[-1][0], 9.5)


if __name__ == "__main__":
    unittest.main()
