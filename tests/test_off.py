import json
from pathlib import Path

import pytest

from optidieta.sources.off import fetch_label, label_is_plausible, parse_label

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FakeResp:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, data, status=200):
        self.data, self.status, self.calls = data, status, 0

    def get(self, *a, **k):
        self.calls += 1
        return FakeResp(self.data, self.status)


def test_parse_label():
    v = parse_label(load("off_found.json"))
    assert v["azucares_g"] == 3.5
    assert v["sodio_mg"] == pytest.approx(8.0)
    assert v["energia_kcal"] == 359
    assert "hierro_mg" not in v


def test_parse_empty():
    assert parse_label(load("off_empty.json")) == {}
    assert parse_label(None) == {}
    assert parse_label({"status": 0}) == {}


def test_plausibility():
    assert label_is_plausible(parse_label(load("off_found.json")))
    assert not label_is_plausible(parse_label(load("off_bad_kcal.json")))
    assert label_is_plausible({"azucares_g": 1.0})


def test_not_found_is_cached(tmp_path):
    s = FakeSession({"status": 0, "status_verbose": "product not found"}, status=404)
    assert fetch_label("123", tmp_path, session=s, delay=0) == {"status": 0, "status_verbose": "product not found"}
    fetch_label("123", tmp_path, session=s, delay=0)
    assert s.calls == 1
