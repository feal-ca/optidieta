from optidieta.nutrients import BY_KEY, NUTRIENTS, col, known_col


def test_registry_unique_and_columns():
    keys = [n.key for n in NUTRIENTS]
    assert len(keys) == len(set(keys))
    assert col("hierro_mg") == "n_hierro_mg"
    assert known_col("hierro_mg") == "k_hierro_mg"
    assert BY_KEY["cobre_mg"].unit == "mg"
    ids = [i for n in NUTRIENTS for i in n.bedca_ids]
    assert len(ids) == len(set(ids))


def test_off_fields():
    assert BY_KEY["azucares_g"].off_field == "sugars_100g"
    assert BY_KEY["azucares_g"].bedca_ids == (446,)
    assert BY_KEY["sodio_mg"].off_factor == 1000
    assert BY_KEY["hierro_mg"].off_field is None
