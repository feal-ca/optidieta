import pytest

from helpers import product
from optidieta.pricing import price_per_100g


def test_price_kg():
    assert price_per_100g(product(precio_ref=1.7, formato_ref="kg"), 1.0, None, None) == pytest.approx(0.17)


def test_price_edible_portion():
    assert price_per_100g(product(precio_ref=2.0, formato_ref="kg"), 0.8, None, None) == pytest.approx(0.25)


def test_price_oil_litre():
    p = product(nombre="Aceite de oliva virgen extra Hacendado", precio_ref=9.2, formato_ref="L")
    assert price_per_100g(p, 1.0, None, None) == pytest.approx(1.0)


def test_price_milk_litre():
    p = product(nombre="Leche entera Hacendado", precio_ref=0.95, formato_ref="L")
    assert price_per_100g(p, 1.0, None, None) == pytest.approx(0.095)


def test_price_unit_without_weight_is_none():
    assert price_per_100g(product(formato_ref="ud", precio_envase=2.4), 1.0, None, None) is None


def test_price_unit_with_weight():
    p = product(nombre="Huevos frescos L", formato_ref="ud", precio_envase=2.4)
    assert price_per_100g(p, 1.0, 720, None) == pytest.approx(0.3333, abs=1e-3)


def test_zero_edible_portion_treated_as_one():
    assert price_per_100g(product(precio_ref=1.0), 0, None, None) == pytest.approx(0.1)


def test_price_per_100g_format():
    assert price_per_100g(product(precio_ref=0.45, formato_ref="100 g"), 1.0, None, None) == pytest.approx(0.45)


def test_price_eggs_dozen_and_ten():
    dz = product(nombre="Huevos", precio_ref=2.625, formato_ref="dz", precio_envase=5.25)
    dc = product(nombre="Huevos grandes L", precio_ref=3.05, formato_ref="dc", precio_envase=3.05)
    assert price_per_100g(dz, 1.0, None, None) == pytest.approx(2.625 / (12 * 0.6))
    assert price_per_100g(dc, 1.0, None, None) == pytest.approx(3.05 / (10 * 0.6))
