"""Motore obbligatorio nell'exe pubblicato (engine/backend.py, run_client.py)."""
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import run_client   # noqa: E402
from engine import backend, grid   # noqa: E402


class TestNativeProblem(unittest.TestCase):
    def test_missing_module(self):
        with mock.patch.object(grid, "_native", None):
            self.assertIn("non e' caricato", backend.native_problem())

    def test_old_build_is_not_enough(self):
        old = types.SimpleNamespace(**{n: object() for n in backend.REQUIRED if "." not in n})
        with mock.patch.object(grid, "_native", old):
            self.assertIn("step_collide_units", backend.native_problem())

    @unittest.skipIf(grid._native is None, "senza motore Rust")
    def test_current_build_is_complete(self):
        self.assertIsNone(backend.native_problem())


class TestCheckEngine(unittest.TestCase):
    def run_check(self, argv, problem, frozen=False):
        with mock.patch.object(sys, "argv", ["run_client.py", *argv]), \
                mock.patch.object(sys, "frozen", frozen, create=True), \
                mock.patch.object(sys, "stdout", None), \
                mock.patch.object(backend, "native_problem", lambda: problem):
            run_client.check_engine()

    def test_flag_exit_code(self):
        for problem, code in ((None, 0), ("rotto", 1)):
            with self.assertRaises(SystemExit) as e:
                self.run_check(["--check-engine"], problem)
            self.assertEqual(e.exception.code, code)

    def test_source_run_allows_pure_python(self):
        self.run_check([], "rotto")                    # nessuna uscita

    def test_exe_with_engine_starts(self):
        self.run_check([], None, frozen=True)          # nessuna uscita

    def test_exe_without_engine_stops_with_message(self):
        import ctypes
        windll = types.SimpleNamespace(user32=types.SimpleNamespace(MessageBoxW=mock.Mock()))
        with mock.patch.object(ctypes, "windll", windll, create=True):
            with self.assertRaises(SystemExit) as e:
                self.run_check([], "rotto", frozen=True)
        self.assertEqual(e.exception.code, 1)
        self.assertIn("rotto", windll.user32.MessageBoxW.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
