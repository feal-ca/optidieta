import math
from pathlib import Path

import pytest

from optidieta.sources.bedca import fetch_food, fetch_food_list, foods_frame, parse_food

FIX = Path(__file__).parent / "fixtures"


class FakeResp:
    def __init__(self, text):
        self.content = text.encode("utf-8")
        self.text = text

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def post(self, *a, **k):
        self.calls += 1
        return FakeResp(self.text)


class Boom:
    def post(self, *a, **k):
        raise AssertionError("no debería pedir a la red")


def test_parse_garbanzo():
    f = parse_food((FIX / "bedca_food_160.xml").read_text(encoding="utf-8"))
    assert f.f_id == 160
    assert f.nombre == "Garbanzo, seco, crudo"
    assert f.valores["proteina_g"] == 20.4
    assert f.valores["cobre_mg"] == 0.85
    assert f.valores["energia_kcal"] == pytest.approx(4 * 20.4 + 4 * 55.8 + 9 * 5.5 + 2 * 13.6)
    assert f.porcion_comestible == 1.0


def test_gap_is_unknown_not_zero():
    f = parse_food((FIX / "bedca_food_gaps.xml").read_text(encoding="utf-8"))
    df = foods_frame([f])
    assert math.isnan(df.n_hierro_mg[0])
    assert not df.k_hierro_mg[0]
    assert df.n_energia_kcal[0] == pytest.approx(1500 / 4.184)
    assert df.n_proteina_g[0] == 3.5
    assert df.porcion_comestible[0] == 0.73
    assert "componente raro" in f.sin_mapear


def test_list_dedup(tmp_path):
    s = FakeSession((FIX / "bedca_list.xml").read_text(encoding="utf-8"))
    lst = fetch_food_list(tmp_path, session=s)
    assert lst == [(160, "Garbanzo, seco, crudo"), (189, "Lenteja, seca, cruda")]


def test_fetch_uses_cache(tmp_path):
    (tmp_path / "f_160.xml").write_text("<x/>", encoding="utf-8")
    assert fetch_food(160, tmp_path, session=Boom()) == "<x/>"


def test_fetch_writes_cache(tmp_path):
    s = FakeSession("<y/>")
    fetch_food(5, tmp_path, session=s)
    fetch_food(5, tmp_path, session=s)
    assert s.calls == 1
