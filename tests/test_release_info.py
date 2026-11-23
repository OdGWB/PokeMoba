"""Versione e tag della Release ricavati da data/news.json (tools/release_info.py)."""
import json

import pytest

from game import version
from tools import release_info as R


def test_build_dalla_versione():
    n = 7
    ver = f"{version.SERIES}.{n}"
    assert R.build_of(ver) == version.SERIES_BASE + n
    assert version.name_of(R.build_of(ver)) == ver


@pytest.mark.parametrize("bad", ["9.9.1", f"{version.SERIES}.0", f"{version.SERIES}.x", "3"])
def test_versione_fuori_serie(bad):
    with pytest.raises(ValueError):
        R.build_of(bad)


def test_info_dalla_voce_in_cima(tmp_path):
    f = tmp_path / "news.json"
    f.write_text(json.dumps([
        {"version": f"{version.SERIES}.5", "title": "Nuovo", "items": ["a", "b"]},
        {"version": f"{version.SERIES}.4", "title": "Vecchio", "items": []}]),
        encoding="utf-8")
    d = R.info(f)
    assert d["tag"] == f"v{version.SERIES_BASE + 5}"
    assert "**Nuovo**" in d["notes"] and "- a\n- b" in d["notes"]
    assert "PokeMoba-Setup.exe" in d["notes"]


def test_news_vera_ha_una_versione_valida():
    R.info()
