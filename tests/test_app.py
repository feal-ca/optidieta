import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from optidieta.nutrients import NUTRIENTS, col, known_col
from optidieta.targets import Profile, default_constraints

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def food(fid, precio, vegano=True, **vals):
    row = {"id": fid, "nombre": f"Alimento {fid}", "categoria": "Legumbres", "subcategoria": "Legumbres",
           "url": "https://tienda.mercadona.es/product/" + fid, "precio_100g": precio, "vegetariano": True,
           "vegano": vegano, "bedca_nombre": "B", "fuente_etiqueta": "bedca"}
    for n in NUTRIENTS:
        v = vals.get(n.key)
        row[col(n.key)] = float("nan") if v is None else v
        row[known_col(n.key)] = v is not None
    return row


@pytest.fixture
def data(tmp_path, monkeypatch):
    cat = pd.DataFrame([
        food("1", 0.15, energia_kcal=350.0, proteina_g=24.0, vit_b12_ug=0.0),
        food("2", 0.40, vegano=False, energia_kcal=150.0, proteina_g=12.0, vit_b12_ug=1.0),
    ])
    cat.to_parquet(tmp_path / "catalog.parquet")
    monkeypatch.setenv("OPTIDIETA_DATA", str(tmp_path))
    return tmp_path


def write_state(d, diet, keep):
    keys = [c.key for c in default_constraints(Profile("h", 30))]
    edits = {k: {"active": False} for k in keys if k not in keep}
    st = {"profile": {"sexo": "h", "edad": 30, "peso_kg": 70.0}, "diet": diet, "excluded": [],
          "price_overrides": {}, "constraint_edits": edits, "max_g": 1500.0}
    (d / "estado.json").write_text(json.dumps(st), encoding="utf-8")


def all_text(at):
    parts = [m.value for m in at.markdown] + [e.value for e in at.error] + [w.value for w in at.warning]
    parts += [i.value for i in at.info] + [b.label for b in at.button]
    return "\n".join(map(str, parts))


def test_app_smoke(data):
    write_state(data, "omnivora", {"energia_kcal", "proteina_g"})
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("€" in str(m.value) for m in at.metric)


def test_app_infeasible_shows_blocking(data):
    write_state(data, "vegana", {"energia_kcal", "proteina_g", "vit_b12_ug"})
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert "Vitamina B12" in all_text(at)


def test_app_without_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIDIETA_DATA", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert "optidieta fetch" in all_text(at)
