import json

import pytest

from optidieta.sources.etiqueta import SCHEMA, claude_cmd, parse_label, photo_url, read_label

DETAIL = {"photos": [
    {"regular": "https://img/a.jpg?fit=crop&h=600&w=600", "perspective": 2},
    {"regular": "https://img/b.jpg?fit=crop&h=600&w=600", "perspective": 9},
]}
SOJA = {"hay_tabla": True, "base": "100 ml", "energia_kcal": 36, "grasa_g": 1.9, "grasa_sat_g": 0.3, "hidratos_g": 1.2,
        "azucares_g": 0.6, "fibra_g": 0.5, "proteina_g": 3.4, "sal_g": 0.18,
        "otros": [{"clave": "vit_b12_ug", "valor": 0.38, "unidad": "µg"},
                  {"clave": "calcio_mg", "valor": 120, "unidad": "mg"},
                  {"clave": "vit_d_ug", "valor": 0.00075, "unidad": "mg"}]}


def test_photo_url_back_label_bigger():
    assert photo_url(DETAIL) == "https://img/b.jpg?fit=crop&h=1600&w=1600"
    assert photo_url({"photos": [DETAIL["photos"][0]]}) is None


def test_parse_label_units_and_salt():
    v = parse_label(SOJA)
    assert v["proteina_g"] == 3.4 and v["vit_b12_ug"] == 0.38 and v["calcio_mg"] == 120
    assert v["sodio_mg"] == pytest.approx(72.0)
    assert v["vit_d_ug"] == pytest.approx(0.75)


def test_parse_label_without_table():
    assert parse_label({"hay_tabla": False, "otros": []}) == {}
    assert parse_label(None) == {}


def test_cmd_is_minimal_and_schema_lists_keys():
    cmd = claude_cmd(__import__("pathlib").Path("/tmp/x.jpg"))
    for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence", "--json-schema"):
        assert flag in cmd
    assert "vit_b12_ug" in SCHEMA["properties"]["otros"]["items"]["properties"]["clave"]["enum"]
    assert "proteina_g" not in SCHEMA["properties"]["otros"]["items"]["properties"]["clave"]["enum"]


class FakeSession:
    def __init__(self):
        self.calls = 0

    def get(self, url, timeout):
        self.calls += 1
        return type("R", (), {"content": b"jpg", "raise_for_status": lambda self: None})()


def test_read_label_caches(tmp_path):
    calls = []

    def run(cmd):
        calls.append(cmd)
        return {"is_error": False, "total_cost_usd": 0.001, "structured_output": SOJA}

    s = FakeSession()
    d = read_label("14706", DETAIL, tmp_path, run=run, session=s)
    assert d["proteina_g"] == 3.4 and d["producto"] == "14706"
    assert read_label("14706", DETAIL, tmp_path, run=run, session=s) == d
    assert len(calls) == 1 and s.calls == 1
    assert json.loads((tmp_path / "14706.json").read_text())["energia_kcal"] == 36


def test_read_label_no_photo(tmp_path):
    assert read_label("1", {"photos": []}, tmp_path, run=lambda c: pytest.fail("no debe llamar")) is None
