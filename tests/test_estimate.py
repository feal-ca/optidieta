import math

import pandas as pd
import pytest

from optidieta.estimate import fill_estimates
from optidieta.nutrients import NUTRIENTS, col, known_col


def food(fid, sub, **vals):
    row = {"id": fid, "nombre": fid, "subcategoria": sub}
    for n in NUTRIENTS:
        v = vals.get(n.key)
        row[col(n.key)] = math.nan if v is None else v
        row[known_col(n.key)] = v is not None
    return row


def frame(*rows):
    return fill_estimates(pd.DataFrame(list(rows)))


def get(df, fid, key):
    r = df[df.id == fid].iloc[0]
    return (r[col(key)] if r[known_col(key)] else None), r["estimados"]


def test_sugar_from_subcategory_ratio():
    panes = [food(f"p{i}", "Pan", hidratos_g=50.0, azucares_g=2.5 + i) for i in range(3)]  # ratios .05 .07 .09
    df = frame(*panes, food("x", "Pan", hidratos_g=40.0))
    v, est = get(df, "x", "azucares_g")
    assert v == pytest.approx(40 * 0.07)
    assert est == "azucares_g"
    assert get(df, "p0", "azucares_g") == (2.5, "")


def test_sugar_upper_bound_when_carbs_tiny():
    v, _ = get(frame(food("m", "Carne", hidratos_g=0.5)), "m", "azucares_g")
    assert v == pytest.approx(0.5)


def test_sugar_stays_unknown_without_evidence():
    v, est = get(frame(food("a", "Arroz", hidratos_g=80.0)), "a", "azucares_g")
    assert v is None and est == ""


def test_fat_from_lean_subcategory_only():
    fr = [food(f"f{i}", "Fruta", grasa_g=g) for i, g in enumerate([0.1, 0.2, 0.4])]
    ac = [food(f"o{i}", "Aceite", grasa_g=100.0) for i in range(3)]
    df = frame(*fr, *ac, food("manzana", "Fruta"), food("vinagre", "Aceite"))
    assert get(df, "manzana", "grasa_g")[0] == pytest.approx(0.2)
    assert get(df, "vinagre", "grasa_g")[0] is None


def test_zero_energy_means_no_fat_or_sugar():
    df = frame(food("sal", "Sal", energia_kcal=0.0, sodio_mg=38000.0))
    for k in ("grasa_g", "grasa_sat_g", "azucares_g"):
        assert get(df, "sal", k)[0] == 0.0
    assert get(df, "sal", "azucares_g")[1] == "grasa_g,grasa_sat_g,azucares_g"


def test_sugar_falls_back_to_category():
    rows = [food(f"g{i}", f"Galleta{i}", hidratos_g=60.0, azucares_g=30.0) for i in range(3)]
    for r in rows:
        r["categoria"] = "Panadería"
    x = food("x", "Pan de horno", hidratos_g=50.0)
    x["categoria"] = "Panadería"
    assert get(frame(*rows, x), "x", "azucares_g")[0] == pytest.approx(25.0)


def test_vegan_foods_have_no_epa_dha():
    v = food("lenteja", "Legumbres", epa_dha_mg=70.0)  # BEDCA da valores así a nueces y aceites
    v["vegano"] = True
    a = food("leche", "Leche")
    a["vegano"] = False
    df = frame(v, a)
    assert get(df, "lenteja", "epa_dha_mg") == (0.0, "")
    assert get(df, "leche", "epa_dha_mg")[0] is None
