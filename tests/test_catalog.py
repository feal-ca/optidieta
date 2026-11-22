import math

import pandas as pd
from helpers import product

from optidieta.catalog import build_catalog
from optidieta.nutrients import NUTRIENTS, col, known_col


def bedca_row(bid, **vals):
    row = {"bedca_id": bid, "bedca_nombre": f"B{bid}", "porcion_comestible": 1.0}
    for n in NUTRIENTS:
        v = vals.get(n.key)
        row[col(n.key)] = float("nan") if v is None else v
        row[known_col(n.key)] = v is not None
    return row


BEDCA = pd.DataFrame([bedca_row(1, proteina_g=12.0, hierro_mg=3.0, energia_kcal=300.0, hidratos_g=50.0, grasa_g=2.0)])


def mrow(mid, rev="sí", excl="no", g=None, veg="", vegan=""):
    return {"mercadona_id": mid, "nombre": "x", "bedca_id": 1, "bedca_nombre": "B1", "confianza": 90,
            "revisado": rev, "excluir": excl, "porcion_comestible": 1.0, "g_por_unidad": g,
            "vegetariano": veg, "vegano": vegan}


def build(products, rows, labels=None):
    return build_catalog(products, BEDCA, pd.DataFrame(rows), labels or {})


def test_build_skips_unreviewed_and_excluded():
    ps = [product(id="1"), product(id="2"), product(id="3")]
    cat, rep = build(ps, [mrow("1"), mrow("2", rev="no"), mrow("3", excl="sí")])
    assert list(cat.id) == ["1"]
    assert rep.incluidos == 1
    assert rep.sin_revisar == 1
    assert cat.precio_100g[0] == 0.1


def test_build_reports_vanished_product():
    cat, rep = build([product(id="1")], [mrow("1"), mrow("9")])
    assert rep.desaparecidos == ["9"]
    assert "9" not in set(cat.id)


def test_build_reports_no_price():
    cat, rep = build([product(id="1", formato_ref="ud")], [mrow("1")])
    assert rep.sin_precio == ["1"]
    assert cat.empty


def test_mapping_overrides_diet_flags():
    ps = [product(id="1", nombre="Lentejas")]
    cat, _ = build(ps, [mrow("1", veg="no", vegan="no")])
    assert not cat.vegetariano[0] and not cat.vegano[0]
    cat, _ = build(ps, [mrow("1")])
    assert cat.vegetariano[0] and cat.vegano[0]


def test_label_overrides_bedca_macros():
    labels = {"1": {"proteina_g": 13.0, "energia_kcal": 300.0, "hidratos_g": 55.0, "grasa_g": 2.0, "azucares_g": 1.0}}
    cat, rep = build([product(id="1")], [mrow("1")], labels)
    assert cat.n_proteina_g[0] == 13.0
    assert cat.fuente_etiqueta[0] == "off"
    assert cat.n_hierro_mg[0] == 3.0
    assert cat.k_azucares_g[0]
    assert rep.con_etiqueta == 1


def test_implausible_label_ignored():
    labels = {"1": {"proteina_g": 13.0, "energia_kcal": 50.0, "hidratos_g": 55.0, "grasa_g": 2.0}}
    cat, rep = build([product(id="1")], [mrow("1")], labels)
    assert cat.n_proteina_g[0] == 12.0
    assert cat.fuente_etiqueta[0] == "bedca"
    assert rep.etiqueta_descartada == ["1"]


def test_sugar_unknown_without_label():
    cat, _ = build([product(id="1")], [mrow("1")])
    assert not cat.k_azucares_g[0]
    assert math.isnan(cat.n_azucares_g[0])


def test_duplicate_mapping_rows_deduped():
    cat, rep = build([product(id="1")], [mrow("1"), mrow("1")])
    assert list(cat.id) == ["1"]
    assert rep.duplicados == ["1"]


def test_label_far_from_bedca_ignored():
    # etiqueta coherente consigo misma pero de otro producto (612 kcal frente a 300 → no; 1000 frente a 300 → sí)
    labels = {"1": {"energia_kcal": 1000.0, "proteina_g": 20.0, "hidratos_g": 14.0, "grasa_g": 100.0}}
    cat, rep = build([product(id="1")], [mrow("1")], labels)
    assert cat.fuente_etiqueta[0] == "bedca"
    assert rep.etiqueta_descartada == ["1"]


def test_light_label_kept():
    labels = {"1": {"energia_kcal": 110.0, "proteina_g": 12.0, "hidratos_g": 14.0, "grasa_g": 0.5}}
    cat, _ = build([product(id="1")], [mrow("1")], labels)
    assert cat.fuente_etiqueta[0] == "off"
