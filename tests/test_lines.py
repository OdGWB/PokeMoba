"""Registro delle linee (engine/lines.py): agganci validi, niente conflitti di nomi,
dichiarazioni di rete (LINE["net"]) che puntano a campi veri."""
import ast
import dataclasses
import glob
import os
import sys
import unittest
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.content import load_map
from engine.entities import Pokemon
from engine.lines import HOOK_KINDS, LINE_MIXINS, NET_KINDS
from engine.match import Match
from engine.world import World


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
                self.assertIn(k, ("passives", "net") + HOOK_KINDS, f"{m.__name__}: aggancio {k}?")
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

    def test_net_declarations(self):
        """Ogni lista di rete esiste sul Match dopo l'init della linea, ogni campo
        su Pokemon; nessun nome dichiarato da due linee."""
        m = load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json"))
        match = Match(World(m.grid), m)
        fields = {f.name: f for f in dataclasses.fields(Pokemon)}
        owner = {}
        for mx in LINE_MIXINS:
            net = mx.LINE.get("net", {})
            for k in net:
                self.assertIn(k, NET_KINDS, f"{mx.__name__}: net.{k}?")
            lists = list(net.get("lists", {})) + list(net.get("shared", ()))
            for name in lists:
                self.assertIsInstance(getattr(match, name, None), list,
                                      f"{mx.__name__}: Match.{name} non è una lista")
                self.assertNotIn(name, owner, f"{name} in {mx.__name__} e {owner.get(name)}")
                owner[name] = mx.__name__
            for name in net.get("moving", ()):
                self.assertIn(name, lists, f"{mx.__name__}: {name} in moving ma non spedita")
            for name, off in net.get("unit_flags", {}).items():
                self.assertIn(name, fields, f"{mx.__name__}: Pokemon.{name} non esiste")
                self.assertEqual(fields[name].default, off,
                                 f"{mx.__name__}: {name} spento = {off}, default diverso")
            for name in net.get("me", ()):
                self.assertIn(name, fields, f"{mx.__name__}: Pokemon.{name} non esiste")

    def test_passives_do_not_overlap(self):
        seen = {}
        for m in LINE_MIXINS:
            for pid in m.LINE["passives"]:
                self.assertNotIn(pid, seen, f"passiva {pid} in {m.__name__} e {seen.get(pid)}")
                seen[pid] = m.__name__


if __name__ == "__main__":
    unittest.main()
