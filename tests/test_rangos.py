import pytest

from optidieta.optimizer import NutrientTotal, Solution
from optidieta.rangos import diet_value, drag_edit, nutrient_rows, reference
from optidieta.state import apply_edits
from optidieta.targets import Constraint, Profile, default_constraints

PROT = Constraint("proteina_g", "Proteína", "g", 58.0, None)
SODIO = Constraint("sodio_mg", "Sodio", "mg", None, 2000.0)
GRASA = Constraint("grasa_g", "Grasa total", "% E", 0.20, 0.35, kind="pct_energia", kcal_por_g=9)
AZUC = Constraint("azucares_g", "Azúcares", "% E", None, 0.10, active=False, kind="pct_energia", kcal_por_g=4)
KCAL = Constraint("energia_kcal", "Energía", "kcal", 2400.0, 2600.0)


def sol(**vals):
    return Solution(True, 3.0, totals={k: NutrientTotal(v, 1.0) for k, v in vals.items()})


def test_reference_is_min_else_max():
    assert reference(PROT) == 58.0
    assert reference(SODIO) == 2000.0
    assert reference(GRASA) == pytest.approx(20.0)


def test_pct_energy_value():
    # 80 g de grasa · 9 kcal / 2400 kcal = 30 % E
    assert diet_value(GRASA, sol(grasa_g=80.0, energia_kcal=2400.0)) == pytest.approx(30.0)


def test_rows_band_value_status():
    base = [KCAL, PROT, SODIO, GRASA]
    rows = {r["key"]: r for r in nutrient_rows(base, base, sol(energia_kcal=2400.0, proteina_g=29.0,
                                                               sodio_mg=3000.0, grasa_g=80.0))}
    assert rows["proteina_g"]["value"] == pytest.approx(50.0)
    assert rows["proteina_g"]["status"] == "bajo"
    assert rows["proteina_g"]["band_hi"] is None
    assert rows["sodio_mg"]["band_lo"] == 0.0 and rows["sodio_mg"]["band_hi"] == pytest.approx(100.0)
    assert rows["sodio_mg"]["status"] == "alto"
    assert rows["grasa_g"]["band_hi"] == pytest.approx(175.0)
    assert rows["grasa_g"]["status"] == "ok"
    assert not rows["grasa_g"]["edited"]


def test_rows_without_solution_have_no_dot():
    rows = nutrient_rows([PROT], [PROT], Solution(False, 0.0, blocking=["proteina_g"]))
    assert rows[0]["value"] is None and rows[0]["status"] is None


def test_drag_up_sets_min():
    assert drag_edit(PROT, 120.0, 150.0) == {"min": pytest.approx(87.0)}


def test_drag_down_sets_max_and_keeps_efsa_min():
    assert drag_edit(GRASA, 150.0, 125.0) == {"max": pytest.approx(0.25)}


def test_drag_below_efsa_min_pins_both():
    e = drag_edit(GRASA, 150.0, 50.0)
    assert e == {"min": pytest.approx(0.10), "max": pytest.approx(0.10)}


def test_drag_replaces_previous_edit():
    # tras un mínimo forzado, bajar el punto deja el mínimo EFSA y fija un máximo
    assert drag_edit(PROT, 150.0, 130.0) == {"max": pytest.approx(75.4)}


def test_drag_activates_inactive_constraint():
    e = drag_edit(AZUC, 80.0, 50.0)
    assert e == {"max": pytest.approx(0.05), "active": True}


def test_rows_show_edited_target():
    base = default_constraints(Profile("h", 30, 70.0))
    b = next(c for c in base if c.key == "proteina_g")
    edits = {"proteina_g": drag_edit(b, 100.0, 200.0)}
    rows = {r["key"]: r for r in nutrient_rows(base, apply_edits(base, edits), sol(proteina_g=116.2))}
    assert rows["proteina_g"]["edited"]
    assert rows["proteina_g"]["target_lo"] == pytest.approx(200.0)
    assert rows["proteina_g"]["target_txt"].startswith("≥ 116")


def test_food_contrib_abs_pct_energy_and_unknown():
    import math
    from optidieta.nutrients import col
    from optidieta.rangos import food_contrib
    food = {col("proteina_g"): 24.0, col("grasa_g"): 2.0, col("sodio_mg"): math.nan}
    s = sol(energia_kcal=2400.0, proteina_g=100.0, grasa_g=80.0, sodio_mg=1000.0)
    c = food_contrib(food, 200.0, [PROT, GRASA, SODIO], s)
    assert c["proteina_g"] == pytest.approx(48.0)
    assert c["grasa_g"] == pytest.approx(4 * 9 / 2400 * 100)  # % de la energía de la dieta
    assert c["sodio_mg"] is None


def test_rows_with_contrib():
    s = sol(proteina_g=116.0)
    rows = nutrient_rows([PROT], [PROT], s, contrib={"proteina_g": 29.0})
    assert rows[0]["contrib"] == pytest.approx(50.0)
    assert rows[0]["contrib_share"] == pytest.approx(0.25)


def test_margin_is_not_a_user_edit_but_shows_target():
    from optidieta.targets import apply_margin
    base = [PROT]
    defaults = apply_margin(base, 0.1)
    r = nutrient_rows(base, defaults, sol(proteina_g=63.8), defaults=defaults)[0]
    assert not r["edited"] and r["target_shown"]
    assert r["target_lo"] == pytest.approx(110.0) and r["band_lo"] == pytest.approx(100.0)
    # el arrastre se mide en la escala EFSA y el otro límite vuelve al valor con margen
    assert drag_edit(defaults[0], 110.0, 150.0, ref=58.0) == {"min": pytest.approx(87.0)}


def test_estimated_flag():
    r = nutrient_rows([AZUC], [AZUC], sol(azucares_g=10.0, energia_kcal=2000.0), estimated={"azucares_g"})[0]
    assert r["estimated"]


def test_combine_contrib():
    from optidieta.rangos import combine_contrib
    total, partial = combine_contrib([{"a": 1.0, "b": None, "c": None}, {"a": 2.0, "b": 3.0, "c": None}])
    assert total == {"a": 3.0, "b": 3.0, "c": None}
    assert partial == {"b"}
    r = nutrient_rows([PROT], [PROT], sol(proteina_g=100.0), contrib={"proteina_g": 30.0},
                      contrib_partial={"proteina_g"})[0]
    assert r["contrib_txt"] == "≥ 30,0 g"
