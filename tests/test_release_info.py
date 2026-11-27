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


def test_serie_32_parte_da_zero():
    # 3.2.0 = build 10: piu' alta dell'ultima della serie 3.1 (3.1.0 ricostruita = 9),
    # cosi' gli exe installati la vedono come aggiornamento.
    assert version.SERIES == "3.2"
    assert version.name_of(10) == "3.2.0"
    assert R.build_of("3.2.0") == 10 and R.build_of("3.2.1") == 11


def test_ricostruzione_tiene_il_nome(monkeypatch):
    # Una build ricostruita (es. 11 = 3.2.0 ricostruita): l'updater la vede
    # (11 > 10) ma il nome non cambia, e la patch dopo slitta di uno.
    monkeypatch.setattr(version, "REBUILDS", (11,))
    assert version.name_of(10) == version.name_of(11) == "3.2.0"
    assert R.build_of("3.2.0") == 11
    assert R.build_of("3.2.1") == 12 and version.name_of(12) == "3.2.1"


def test_nome_release_delle_ricostruzioni(monkeypatch):
    # Su GitHub le ricostruzioni dicono la build; la Release originale e le patch no.
    monkeypatch.setattr(version, "REBUILDS", (11,))
    assert version.release_name_of(10) == "3.2.0"
    assert version.release_name_of(11) == "3.2.0 (build 11)"
    assert version.release_name_of(12) == "3.2.1"


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
