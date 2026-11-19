"""Novità e patch notes (game/news.py): massimo 10 voci, la più recente in cima."""
import json

from game import news as N


def test_add_entry_tiene_le_ultime_10(tmp_path):
    f = tmp_path / "news.json"
    for i in range(1, 14):
        N.add_entry(f"3.0.{i}", f"t{i}", [f"n{i}"], date="2026-11-19", path=f)
    out = N.load(f)
    assert len(out) == N.MAX_ENTRIES == 10
    assert out[0]["version"] == "3.0.13"
    assert out[-1]["version"] == "3.0.4"     # le 3 più vecchie sono sparite


def test_add_entry_sostituisce_la_stessa_versione(tmp_path):
    f = tmp_path / "news.json"
    N.add_entry("3.0.1", "a", ["x"], path=f)
    N.add_entry("3.0.2", "b", ["y"], path=f)
    N.add_entry("3.0.1", "c", ["z"], path=f)
    out = N.load(f)
    assert [e["version"] for e in out] == ["3.0.1", "3.0.2"]
    assert out[0]["title"] == "c"


def test_load_file_rotto_o_troppo_lungo(tmp_path):
    f = tmp_path / "news.json"
    f.write_text("{non json", encoding="utf-8")
    assert N.load(f) == []
    assert N.load(tmp_path / "manca.json") == []
    f.write_text(json.dumps([{"version": str(i)} for i in range(15)] + [{"x": 1}]),
                 encoding="utf-8")
    assert len(N.load(f)) == 10


def test_lette(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    news = [{"version": "3.0.1", "date": "", "title": "", "items": []}]
    assert N.is_unread(news)
    N.mark_read(news)
    assert not N.is_unread(news)
    assert N.is_unread([{"version": "3.0.2", "date": "", "title": "", "items": []}] + news)
    assert not N.is_unread([])


def test_file_del_gioco_valido():
    out = N.load()
    assert out and out[0]["version"] == "3.0.1" and len(out) <= 10
