import pandas as pd
from helpers import product

from optidieta.mapping import COLUMNS, merge, propose, read_mapping, write_mapping


def bedca():
    return pd.DataFrame({
        "bedca_id": [189, 190, 160],
        "bedca_nombre": ["Lenteja, hervida", "Lenteja, seca, cruda", "Garbanzo, seco, crudo"],
        "porcion_comestible": [1.0, 1.0, None],
    })


def test_propose_prefers_raw():
    df = propose([product(id="10", nombre="Lentejas pardinas Hacendado 1 kg", marca="Hacendado")], bedca())
    assert list(df.columns) == COLUMNS
    row = df.iloc[0]
    assert row.bedca_nombre == "Lenteja, seca, cruda"
    assert row.bedca_id == 190
    assert row.revisado == "no" and row.excluir == "no"
    assert row.porcion_comestible == 1.0
    assert 0 <= row.confianza <= 100


def test_propose_default_edible_portion():
    df = propose([product(id="11", nombre="Garbanzo cocido")], bedca())
    assert df.iloc[0].porcion_comestible == 1.0


def _row(mid, bid, rev):
    return {"mercadona_id": mid, "nombre": "x", "bedca_id": bid, "bedca_nombre": "y", "confianza": 50,
            "revisado": rev, "excluir": "no", "porcion_comestible": 1.0, "g_por_unidad": None,
            "vegetariano": "", "vegano": ""}


def test_merge_keeps_reviewed():
    old = pd.DataFrame([_row("1", 999, "sí")])
    new = pd.DataFrame([_row("1", 189, "no")])
    assert merge(old, new).iloc[0].bedca_id == 999


def test_merge_replaces_unreviewed_and_adds_new():
    old = pd.DataFrame([_row("1", 999, "no")])
    new = pd.DataFrame([_row("1", 189, "no"), _row("2", 160, "no")])
    out = merge(old, new)
    assert list(out.mercadona_id) == ["1", "2"]
    assert list(out.bedca_id) == [189, 160]


def test_merge_keeps_reviewed_rows_absent_from_proposal():
    old = pd.DataFrame([_row("1", 999, "sí")])
    out = merge(old, pd.DataFrame([_row("2", 160, "no")]))
    assert set(out.mercadona_id) == {"1", "2"}


def test_roundtrip_csv(tmp_path):
    df = pd.DataFrame([_row("1", 189, "sí"), _row("2", None, "no")])
    df.loc[0, "nombre"] = "Plátano de Canarias"
    df.loc[0, "g_por_unidad"] = 720.0
    p = tmp_path / "m.csv"
    write_mapping(df, p)
    back = read_mapping(p)
    assert back.iloc[0].nombre == "Plátano de Canarias"
    assert back.iloc[0].mercadona_id == "1"
    assert back.iloc[0].bedca_id == 189
    assert back.iloc[0].g_por_unidad == 720.0
    assert pd.isna(back.iloc[1].bedca_id)
    assert back.iloc[1].vegano == ""
