import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.types import TypeChart


class TestTypeChart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chart = TypeChart.load(os.path.join(ROOT, "data", "types.json"))

    def test_super_effective(self):
        self.assertEqual(self.chart.multiplier("Fire", ["Grass"]), 2.0)
        self.assertEqual(self.chart.multiplier("Water", ["Fire"]), 2.0)

    def test_not_very_effective(self):
        self.assertEqual(self.chart.multiplier("Fire", ["Water"]), 0.5)

    def test_no_immunities(self):
        # In questo gioco non ci sono immunita': gli 0x diventano 0.25x.
        self.assertEqual(self.chart.multiplier("Normal", ["Ghost"]), 0.25)
        self.assertEqual(self.chart.multiplier("Electric", ["Ground"]), 0.25)

    def test_dual_type_stacks(self):
        # Fuoco vs Erba/Veleno: 2 (Erba) * 1 (Veleno) = 2.
        self.assertEqual(self.chart.multiplier("Fire", ["Grass", "Poison"]), 2.0)
        # Fuoco vs Erba/Acciaio: 2 * 2 = 4.
        self.assertEqual(self.chart.multiplier("Fire", ["Grass", "Steel"]), 4.0)

    def test_neutral(self):
        self.assertEqual(self.chart.multiplier("Fire", ["Normal"]), 1.0)
        self.assertEqual(self.chart.multiplier(None, ["Water"]), 1.0)


if __name__ == "__main__":
    unittest.main()
