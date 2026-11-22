import pandas as pd
import pytest

from optidieta.nutrients import NUTRIENTS, col, known_col
from optidieta.optimizer import compare, solve
from optidieta.targets import Constraint


def food(fid, precio, vegano=True, vegetariano=True, **vals):
    row = {"id": fid, "nombre": f"F{fid}", "precio_100g": precio, "vegano": vegano, "vegetariano": vegetariano,
           "url": "", "fuente_etiqueta": "bedca"}
    for n in NUTRIENTS:
        v = vals.get(n.key)
        row[col(n.key)] = float("nan") if v is None else v
        row[known_col(n.key)] = v is not None
    return row


def C(key, mn=None, mx=None, **kw):
    return Constraint(key, key, "", mn, mx, **kw)


AB = pd.DataFrame([food("A", 0.10, proteina_g=10.0), food("B", 0.50, proteina_g=20.0)])


def test_cheapest_mix():
    s = solve(AB, [C("proteina_g", 30)])
    assert s.feasible
    assert [p.id for p in s.portions] == ["A"]
    assert s.portions[0].grams == pytest.approx(300)
    assert s.cost_day == pytest.approx(0.30)
    assert s.totals["proteina_g"].value == pytest.approx(30)


def test_respects_max_g():
    s = solve(AB, [C("proteina_g", 30)], max_g=200)
    g = {p.id: p.grams for p in s.portions}
    assert g["A"] == pytest.approx(200) and g["B"] == pytest.approx(50)


def test_exclusion():
    s = solve(AB, [C("proteina_g", 30)], excluded=frozenset({"A"}))
    assert [(p.id, round(p.grams)) for p in s.portions] == [("B", 150)]


def test_price_override():
    s = solve(AB, [C("proteina_g", 30)], price_overrides={"A": 5.0})
    assert [p.id for p in s.portions] == ["B"]


def test_diet_filter():
    df = pd.DataFrame([food("A", 0.10, vegano=False, proteina_g=10.0), food("B", 0.50, proteina_g=20.0)])
    s = solve(df, [C("proteina_g", 30)], diet="vegana")
    assert [p.id for p in s.portions] == ["B"]


def test_inactive_constraint_ignored():
    s = solve(AB, [C("proteina_g", 30, active=False)])
    assert s.feasible and s.portions == [] and s.cost_day == 0


def test_unknown_counts_zero_and_reports():
    df = pd.DataFrame([food("A", 0.10, proteina_g=10.0), food("B", 0.20, proteina_g=10.0, hierro_mg=5.0)])
    s = solve(df, [C("proteina_g", 30), C("hierro_mg", 1)], max_g=200)
    assert s.feasible
    assert s.totals["hierro_mg"].known_fraction == pytest.approx(100 / 300)
    s2 = solve(df, [C("proteina_g", 30), C("hierro_mg", mx=100)], max_g=200)
    assert "A" in {p.id for p in s2.portions}
    assert "hierro_mg" in s2.unverified_max


def test_known_fraction_partial():
    df = pd.DataFrame([food("A", 0.10, proteina_g=10.0, hierro_mg=1.0), food("B", 0.10, hierro_mg=1.0)])
    df.loc[1, known_col("proteina_g")] = False
    df.loc[1, col("proteina_g")] = float("nan")
    s = solve(df, [C("hierro_mg", 4)], max_g=200)
    assert s.totals["proteina_g"].known_fraction == pytest.approx(0.5)
    assert s.totals["hierro_mg"].known_fraction == pytest.approx(1.0)


def test_infeasible_names_blocking():
    df = pd.DataFrame([food("A", 0.10, proteina_g=10.0, vit_b12_ug=0.0)])
    s = solve(df, [C("proteina_g", 30), C("vit_b12_ug", 4)], diet="vegana")
    assert s.feasible is False
    assert s.blocking[0] == "vit_b12_ug"
    assert "proteina_g" not in s.blocking


def test_all_excluded_infeasible():
    s = solve(AB, [C("proteina_g", 30)], excluded=frozenset({"A", "B"}))
    assert s.feasible is False
    assert s.blocking == ["proteina_g"]


def test_pct_energy():
    df = pd.DataFrame([
        food("Pan", 0.10, energia_kcal=250.0, grasa_g=1.0, hidratos_g=50.0),
        food("Aceite", 0.50, energia_kcal=900.0, grasa_g=100.0, hidratos_g=0.0),
    ])
    s = solve(df, [C("energia_kcal", 2000, 2100), C("grasa_g", 0.20, 0.35, kind="pct_energia", kcal_por_g=9)],
              max_g=2000)
    assert s.feasible
    kcal, grasa = s.totals["energia_kcal"].value, s.totals["grasa_g"].value
    assert 9 * grasa >= 0.20 * kcal - 1e-6
    assert 9 * grasa <= 0.35 * kcal + 1e-6


def test_compare():
    a = solve(AB, [C("proteina_g", 30)])
    b = solve(AB, [C("proteina_g", 30)], excluded=frozenset({"A"}))
    d = compare(a, b)
    assert d.added == ["B"] and d.removed == ["A"]
    assert d.cost_delta == pytest.approx(0.75 - 0.30)


def test_blocking_scales_pct_rows_by_energy():
    # la grasa se queda a un 0,2 % E del mínimo; la B12 falta entera: la B12 es la causa principal
    df = pd.DataFrame([food("A", 0.10, energia_kcal=100.0, grasa_g=2.2, vit_b12_ug=0.0)])
    s = solve(df, [C("energia_kcal", 2000, 2100), C("grasa_g", 0.20, kind="pct_energia", kcal_por_g=9),
                   C("vit_b12_ug", 4)], max_g=3000)
    assert not s.feasible
    assert s.blocking[0] == "vit_b12_ug"
