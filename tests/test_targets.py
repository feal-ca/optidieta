import json

import pytest

from optidieta.nutrients import BY_KEY
from optidieta.targets import DEFAULT_PATH, Profile, default_constraints, energy_kcal


def by_key(cs):
    return {c.key: c for c in cs}


def test_energy_henry():
    assert energy_kcal(Profile("h", 25, 70)) == pytest.approx((0.0669 * 70 + 2.28) * 1.6 * 239.006)
    assert energy_kcal(Profile("m", 65, 60)) == pytest.approx((0.0424 * 60 + 2.38) * 1.6 * 239.006)


def test_energy_band():
    p = Profile("h", 25, 70)
    e = by_key(default_constraints(p))["energia_kcal"]
    assert e.min == pytest.approx(0.95 * energy_kcal(p))
    assert e.max == pytest.approx(1.05 * energy_kcal(p))


def test_iron_by_sex_and_age():
    assert by_key(default_constraints(Profile("m", 30)))["hierro_mg"].min == 16
    assert by_key(default_constraints(Profile("m", 55)))["hierro_mg"].min == 11
    h = by_key(default_constraints(Profile("h", 30)))["hierro_mg"]
    assert h.min == 11 and h.max == 40


def test_calcium_by_age():
    assert by_key(default_constraints(Profile("h", 20)))["calcio_mg"].min == 1000
    assert by_key(default_constraints(Profile("h", 30)))["calcio_mg"].min == 950


def test_protein_scales_with_weight():
    assert by_key(default_constraints(Profile("h", 30, 80)))["proteina_g"].min == pytest.approx(66.4)


def test_pct_constraints():
    g = by_key(default_constraints(Profile("h", 30)))["grasa_g"]
    assert g.kind == "pct_energia" and g.min == 0.20 and g.max == 0.35 and g.kcal_por_g == 9


def test_every_key_known():
    data = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    assert all(k in BY_KEY for k in data["nutrientes"])


def test_sugar_inactive_by_default():
    s = by_key(default_constraints(Profile("h", 30)))["azucares_g"]
    assert s.active is False and s.max == 0.10 and s.kind == "pct_energia"


def test_every_constraint_has_source():
    assert all(c.fuente for c in default_constraints(Profile("m", 40)))


def test_for_diet_turns_off_fish_only_targets():
    from optidieta.targets import Profile, default_constraints, for_diet
    cs = default_constraints(Profile("h", 30, 70.0))
    on = {c.key: c.active for c in for_diet(cs, "omnivora")}
    veg = {c.key: c.active for c in for_diet(cs, "vegetariana")}
    assert on["epa_dha_mg"] and not veg["epa_dha_mg"]
    assert veg["proteina_g"]
