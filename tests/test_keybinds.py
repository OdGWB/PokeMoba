"""Tasti personalizzabili e lancio rapido (game/keybinds.py, InputController)."""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame

from game import keybinds
from game.input_controller import InputController
from sim.commands import CastMoveCommand


class _Cam:
    def screen_window_to_world(self, x, y):
        return float(x), float(y)


class _MS:
    def __init__(self, mv):
        self.chosen, self.unlocked, self.rank = mv, True, 1


class _Mv:
    def __init__(self, effects=None):
        self.effects = effects or {}
        self.d = {"id": "x"}


class _Me:
    def __init__(self, effects=None):
        self.moveset = {"Q": _MS(_Mv(effects))}


class _World:
    def __init__(self, me):
        self.me = me

    def get(self, _id):
        return self.me


class KeybindsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()

    def tearDown(self):
        keybinds.load({})

    def test_assign_swaps_and_reserved(self):
        keybinds.load({})
        self.assertEqual(keybinds.slot_for(pygame.K_q), "Q")
        self.assertIsNone(keybinds.assign("Q", pygame.K_w))      # scambio con W
        self.assertEqual(keybinds.slot_for(pygame.K_w), "Q")
        self.assertEqual(keybinds.slot_for(pygame.K_q), "W")
        self.assertIsNotNone(keybinds.assign("R", pygame.K_ESCAPE))
        self.assertEqual(keybinds.key("R"), pygame.K_r)

    def test_load_rejects_duplicates(self):
        keybinds.load({"keys": {"Q": pygame.K_e, "E": pygame.K_e}, "camera_speed": 9})
        vals = list(keybinds.to_options()["keys"].values())
        self.assertEqual(len(vals), len(set(vals)))
        self.assertLessEqual(keybinds.camera_speed, 3.0)

    def _press(self, effects):
        ic = InputController(1)
        world = _World(_Me(effects))
        ev = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q, mod=0)
        return ic, ic.process([ev], _Cam(), world)

    def test_smart_cast(self):
        keybinds.load({"smart_cast": False})
        ic, cmds = self._press(None)
        self.assertEqual(cmds, [])
        self.assertEqual(ic.aiming_slot, "Q")
        keybinds.load({"smart_cast": True})
        ic, cmds = self._press(None)
        self.assertEqual(len(cmds), 1)
        self.assertIsInstance(cmds[0], CastMoveCommand)
        self.assertIsNone(ic.aiming_slot)
        # Tiro Lungo (pressione tenuta): resta a mira anche col lancio rapido
        ic, cmds = self._press({"hold": {"time": 1.0}})
        self.assertEqual(cmds, [])
        self.assertEqual(ic.aiming_slot, "Q")


if __name__ == "__main__":
    unittest.main()
