"""Registro delle linee (engine/lines.py): agganci validi e niente conflitti di nomi."""
import ast
import glob
import os
import sys
import unittest
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.lines import HOOK_KINDS, LINE_MIXINS
from engine.match import Match


def _own_methods(cls):
    return {n for n, v in vars(cls).items() if callable(v) or isinstance(v, (staticmethod,
                                                                              classmethod))}


class TestLines(unittest.TestCase):
    def test_declared_hooks_exist(self):
        for m in LINE_MIXINS:
            line = getattr(m, "LINE", None)
            self.assertIsInstance(line, dict, f"{m.__name__}: manca LINE")
            self.assertTrue(line.get("passives"), f"{m.__name__}: LINE senza passives")
            for k in line:
                self.assertIn(k, ("passives",) + HOOK_KINDS, f"{m.__name__}: aggancio {k}?")
            for k in HOOK_KINDS:
                name = line.get(k)
                if name:
                    self.assertIn(name, vars(m), f"{m.__name__}.{name} ({k}) non esiste")

    def test_no_method_name_clash(self):
        """Due mixin (o un mixin e Match) con lo stesso metodo: uno coprirebbe
        l'altro in silenzio, secondo l'ordine delle basi."""
        owners = defaultdict(list)
        for cls in Match.__mro__:
            if cls is object:
                continue
            for n in _own_methods(cls):
                if not (n.startswith("__") and n.endswith("__")):
                    owners[n].append(cls.__name__)
        clashes = {n: o for n, o in owners.items() if len(o) > 1}
        self.assertEqual(clashes, {})

    def test_every_line_module_is_registered(self):
        """Ogni mixin con un attributo LINE in engine/ deve stare nel registro."""
        registered = {m.__name__ for m in LINE_MIXINS}
        for f in glob.glob(os.path.join(ROOT, "engine", "*.py")):
            with open(f, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and any(
                        isinstance(b, ast.Assign) and any(
                            getattr(t, "id", None) == "LINE" for t in b.targets)
                        for b in node.body):
                    self.assertIn(node.name, registered, f"{node.name} non è in LINE_MIXINS")

    def test_passives_do_not_overlap(self):
        seen = {}
        for m in LINE_MIXINS:
            for pid in m.LINE["passives"]:
                self.assertNotIn(pid, seen, f"passiva {pid} in {m.__name__} e {seen.get(pid)}")
                seen[pid] = m.__name__


if __name__ == "__main__":
    unittest.main()
