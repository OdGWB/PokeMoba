"""Token di identita' dei Pokémon (engine/poke_tokens.py): stabilita' degli indici,
unicita', separazione dei vettori, copertura di roster e forme, uso dal giocatore."""
import itertools
import json
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from engine import poke_tokens as T
from engine.content import load_map, load_pokemon_def
from engine.vec import Vec2
from engine.world import World

# Fotografia degli indici: se questo test fallisce hai cambiato un indice gia'
# assegnato (vietato: i modelli addestrati lo leggerebbero come un altro Pokémon).
# Un Pokémon NUOVO si aggiunge qui in coda, con l'indice che ha in poke_tokens.
LINE_SNAPSHOT = {
    "Charmander": 1, "Gastly": 2, "Totodile": 3, "Rowlet": 4, "Snivy": 5, "Nincada": 6,
    "Poliwag": 7, "Roggenrola": 8, "Spiritomb": 9, "Eevee": 10, "Rookidee": 11,
    "Charcadet": 12, "Noibat": 13, "Teddiursa": 14, "Sneasel": 15, "Mienfoo": 16,
    "Duraludon": 17, "Hatenna": 18, "Magnemite": 19, "Swinub": 20, "Venonat": 21,
    "Remoraid": 22, "Flabébé": 23, "Scyther": 24, "Litten": 25, "Delibird": 26,
}
FORM_SNAPSHOT = [
    "Charmander", "Charmeleon", "Charizard", "Gastly", "Haunter", "Gengar", "Totodile",
    "Croconaw", "Feraligatr", "Rowlet", "Dartrix", "Decidueye", "Snivy", "Servine",
    "Serperior", "Nincada", "Ninjask", "Shedinja", "Poliwag", "Poliwhirl", "Poliwrath",
    "Politoad", "Roggenrola", "Boldore", "Gigalith", "Spiritomb", "Eevee", "Jolteon",
    "Flareon", "Espeon", "Glaceon", "Leafeon", "Umbreon", "Sylveon", "Vaporeon",
    "Rookidee", "Corvisquire", "Corviknight", "Charcadet", "Armarouge", "Ceruledge",
    "Noibat", "Noivern", "Teddiursa", "Ursaring", "Ursaluna", "Sneasel", "Weavile",
    "Sneasler", "Mienfoo", "Mienshao", "Duraludon", "Archaludon", "Hatenna", "Hattrem",
    "Hatterene", "Magnemite", "Magneton", "Magnezone", "Swinub", "Piloswine",
    "Mamoswine", "Venonat", "Venomoth", "Remoraid", "Octillery", "Flabébé", "Floette",
    "Florges", "Scyther", "Scizor", "Kleavor", "Litten", "Torracat", "Incineroar",
    "Delibird", "Ferrosacco",
]   # indice = posizione + 1


def _roster():
    for path in config.ROSTER:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            yield path, json.load(f)


def _forms(data):
    """(dex, nome) di tutte le forme giocabili di una linea: evolutions + temporanee."""
    out = [(int(st["dex"]), st["name"]) for st in data["evolutions"]]
    if "ferro" in data:
        out.append((int(data["ferro"].get("dex", 991)), data["ferro"].get("name", "Ferrosacco")))
    if data["name"] == "Nincada":
        out.append((T.SHEDINJA_DEX, "Shedinja"))
    return out


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class TestStability(unittest.TestCase):
    def test_line_snapshot(self):
        got = {n: i for i, n in T.LINES.values()}
        for name, idx in LINE_SNAPSHOT.items():
            self.assertEqual(got.get(name), idx, f"indice della linea {name} cambiato")

    def test_form_snapshot(self):
        for i, name in enumerate(FORM_SNAPSHOT, start=1):
            self.assertEqual(T.form_id(name), i, f"indice della forma {name} cambiato")

    def test_vectors_depend_only_on_index(self):
        # Valori attesi scritti a mano: la costruzione non deve cambiare.
        s = 1 / 8
        self.assertEqual(T.line_vec(0), (s,) * 64)
        self.assertEqual(T.line_vec(1)[:4], (s, -s, s, -s))
        self.assertEqual(T.line_vec(3)[:4], (s, -s, -s, s))
        self.assertEqual(T.line_vec(T.line_id("Eevee")), T.line_vec(10))

    def test_roster_order_irrelevant(self):
        ids = {d["name"]: T.line_id(d["dex"]) for _, d in _roster()}
        rev = {d["name"]: T.line_id(d["dex"]) for _, d in reversed(list(_roster()))}
        self.assertEqual(ids, rev)


class TestUniqueness(unittest.TestCase):
    def test_line_ids_unique_and_in_range(self):
        ids = [i for i, _ in T.LINES.values()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(0 < i < T.LINE_VOCAB for i in ids))
        self.assertEqual(len(set(n for _, n in T.LINES.values())), len(ids))

    def test_form_ids_unique_and_in_range(self):
        ids = [i for i, _, _ in T.FORMS.values()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(0 < i < T.FORM_VOCAB for i in ids))
        self.assertEqual(len(set(n for _, n, _ in T.FORMS.values())), len(ids))

    def test_forms_point_to_registered_lines(self):
        for d, (_, name, line) in T.FORMS.items():
            self.assertIn(line, T.LINES, name)
        for d in T.LINES:
            self.assertEqual(T.FORMS[d][2], d, "la forma base appartiene alla sua linea")

    def test_room_for_new_pokemon(self):
        self.assertGreaterEqual(T.LINE_VOCAB - 1 - len(T.LINES), 30)
        self.assertGreaterEqual(T.FORM_VOCAB - 1 - len(T.FORMS), 40)


class TestSeparation(unittest.TestCase):
    """Dimensione e separazione documentate: vettori unitari, coseno |.|<=1e-9
    tra ogni coppia (ortogonali), distanza sqrt(2) tra ogni coppia."""

    def _check(self, vecs, dim):
        for v in vecs:
            self.assertEqual(len(v), dim)
            self.assertAlmostEqual(_dot(v, v), 1.0, places=12)
            self.assertTrue(all(-1.0 <= x <= 1.0 for x in v))
        worst_cos, min_dist = 0.0, math.inf
        for a, b in itertools.combinations(vecs, 2):
            worst_cos = max(worst_cos, abs(_dot(a, b)))
            min_dist = min(min_dist, math.dist(a, b))
        self.assertLess(worst_cos, 1e-9)
        self.assertAlmostEqual(min_dist, math.sqrt(2), places=9)

    def test_lines_all_slots(self):
        self._check([T.line_vec(i) for i in range(T.LINE_DIM)], T.LINE_DIM)

    def test_forms_all_slots(self):
        self._check([T.form_vec(i) for i in range(T.FORM_DIM)], T.FORM_DIM)

    def test_out_of_range_is_unknown(self):
        self.assertEqual(T.line_vec(999), T.line_vec(T.UNKNOWN))
        self.assertEqual(T.form_vec(-3), T.form_vec(T.UNKNOWN))


class TestCoverage(unittest.TestCase):
    def test_every_roster_line_registered(self):
        for path, d in _roster():
            self.assertIn(d["dex"], T.LINES, f"{path}: linea senza token")
            self.assertEqual(T.LINES[d["dex"]][1], d["name"], path)

    def test_every_form_registered(self):
        for path, d in _roster():
            line = T.line_id(d["dex"])
            for dex, name in _forms(d):
                self.assertIn(dex, T.FORMS, f"{path}: forma {name} ({dex}) senza token")
                self.assertEqual(T.FORMS[dex][1], name, path)
                self.assertEqual(T.line_id(dex), line, f"{name} sulla linea sbagliata")

    def test_lanes_and_categories_cover_roster(self):
        lanes = T.lanes_table()
        for _, d in _roster():
            self.assertTrue(lanes.get(d["name"]), f"{d['name']} senza corsie")
            self.assertTrue(set(lanes[d["name"]]) <= set(T.LANE_NAMES))
            roles = [d["role"]] + [st["role"] for st in d["evolutions"] if "role" in st]
            for r in roles:
                f = T.descriptive_features(r)
                self.assertEqual(sum(f[:len(T.CATEGORIES)]), 1.0, f"categoria {r}?")
            for st in d["evolutions"]:
                for t in st.get("types") or d["types"]:
                    self.assertIn(t, T.TYPE_NAMES)


class TestFromPlayer(unittest.TestCase):
    def setUp(self):
        self.world = World(load_map(os.path.join(ROOT, "data", "maps", "map_3v3.json")).grid)

    def _spawn(self, path):
        d = load_pokemon_def(os.path.join(ROOT, path))
        return self.world.spawn_pokemon(pos=Vec2(5, 5), team=0, dex=d.dex, name=d.name,
                                        color=d.color, speed=d.base_speed, types=d.types,
                                        base_stats=d.base_stats, moves=d.moves,
                                        evolutions=d.evolutions, role=d.role,
                                        passive=d.passive)

    def test_player_tokens_follow_form_keep_line(self):
        for path, data in _roster():
            p = self._spawn(path)
            line = T.line_id(data["dex"])
            self.assertEqual(T.line_id_of(p), line)
            self.assertEqual(T.form_id_of(p), T.form_id(data["dex"]))
            for dex, name in _forms(data):
                if name == "Shedinja":
                    p.form = "shedinja"
                else:
                    p.form, p.dex, p.name = "", dex, name
                self.assertEqual(T.line_id_of(p), line, name)
                self.assertEqual(T.form_id_of(p), T.form_id(dex), name)
            p.form = ""

    def test_observation_shape_and_range(self):
        p = self._spawn("data/pokemon/eevee.json")
        obs = T.observation(p)
        self.assertEqual(len(obs), T.OBS_DIM)
        self.assertTrue(all(-1.0 <= x <= 1.0 for x in obs))
        feat = obs[T.LINE_DIM + T.FORM_DIM:]
        self.assertEqual(sum(feat[len(T.CATEGORIES):len(T.CATEGORIES) + 5]), 3.0)  # mid/bot/sup
        empty = T.observation(None)
        self.assertEqual(len(empty), T.OBS_DIM)
        self.assertEqual(empty[:T.LINE_DIM], T.line_vec(T.UNKNOWN))
        self.assertTrue(all(x == 0.0 for x in empty[T.LINE_DIM + T.FORM_DIM:]))


if __name__ == "__main__":
    unittest.main()
