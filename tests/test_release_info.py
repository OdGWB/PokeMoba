"""Versione e tag della Release ricavati da data/news.json (tools/release_info.py)."""
import json

import pytest

from game import version
from tools import release_info as R


def test_build_dalla_versione():
    n = 7
    ver = f"{version.SERIES}.{n}"
    assert R.build_of(ver) == version.SERIES_BASE + n + len(version.REBUILDS)
    assert version.name_of(R.build_of(ver)) == ver


@pytest.mark.parametrize("bad", ["9.9.1", f"{version.SERIES}.x", f"{version.SERIES}.-1", "3"])
def test_versione_fuori_serie(bad):
    with pytest.raises(ValueError):
        R.build_of(bad)


def test_serie_31_parte_da_zero():
    # 3.1.0 = build 7: piu' alta dell'ultima della serie 3.0 (3.0.2 = build 6).
    assert version.SERIES == "3.1"
    assert version.name_of(7) == "3.1.0"


def test_ricostruzione_tiene_il_nome():
    # build 8 e 9 = 3.1.0 ricostruita: l'updater le vede (9 > 8 > 7) ma il nome non
    # cambia, e la patch dopo diventa la build 10.
    assert version.REBUILDS == (8, 9)
    assert version.name_of(8) == version.name_of(9) == "3.1.0"
    assert R.build_of("3.1.0") == 9
    assert R.build_of("3.1.1") == 10 and version.name_of(10) == "3.1.1"


def test_nome_release_delle_ricostruzioni():
    # Su GitHub le ricostruzioni dicono la build; la Release originale e le patch no.
    assert version.release_name_of(7) == "3.1.0"
    assert version.release_name_of(9) == "3.1.0 (build 9)"
    assert version.release_name_of(10) == "3.1.1"


def test_info_dalla_voce_in_cima(tmp_path):
    f = tmp_path / "news.json"
    f.write_text(json.dumps([
        {"version": f"{version.SERIES}.5", "title": "Nuovo", "items": ["a", "b"]},
        {"version": f"{version.SERIES}.4", "title": "Vecchio", "items": []}]),
        encoding="utf-8")
    d = R.info(f)
    assert d["tag"] == f"v{version.SERIES_BASE + 5 + len(version.REBUILDS)}"
    assert "**Nuovo**" in d["notes"] and "- a\n- b" in d["notes"]
    assert "PokeMoba-Setup.exe" in d["notes"]


def test_news_vera_ha_una_versione_valida():
    R.info()
