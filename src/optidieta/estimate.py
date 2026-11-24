"""Rellena huecos de grasa, grasa saturada y azúcares con estimaciones por subcategoría.

Un hueco cuenta como 0 en el LP, lo que subestima los máximos (azúcares, saturada). Las estimaciones se apuntan en
la columna `estimados` para poder mostrarlas como tales.
"""

import pandas as pd

from optidieta.nutrients import col, known_col

MIN_EJEMPLOS = 3  # productos con dato en la subcategoría para fiarse de su mediana
MAX_GRASA_MEDIANA = 3.0  # g/100 g: solo se copia la grasa de subcategorías magras (fruta, verdura)
KCAL_CASI_CERO = 5.0
# (nutriente, padre, tope del padre por debajo del cual se usa el padre como cota superior)
RATIOS = [("grasa_sat_g", "grasa_g", 1.0), ("azucares_g", "hidratos_g", 2.0)]


def _set(df: pd.DataFrame, mask: pd.Series, key: str, values, est: dict[int, list[str]]) -> None:
    mask = mask & ~df[known_col(key)]
    if not mask.any():
        return
    df.loc[mask, col(key)] = values if not isinstance(values, pd.Series) else values[mask]
    df.loc[mask, known_col(key)] = True
    for i in df.index[mask]:
        est.setdefault(i, []).append(key)


def fill_estimates(cat: pd.DataFrame) -> pd.DataFrame:
    df = cat.copy()
    if df.empty:
        df["estimados"] = pd.Series(dtype=str)
        return df
    est: dict[int, list[str]] = {}
    if "estimados" in df:  # estimaciones que ya traiga (p. ej. EPA+DHA de conservas en el catálogo)
        for i, v in df["estimados"].fillna("").items():
            if v:
                est[i] = v.split(",")
    sub = df["subcategoria"]

    kcal_known = df[known_col("energia_kcal")] & (df[col("energia_kcal")] <= KCAL_CASI_CERO)
    for k in ("grasa_g", "grasa_sat_g", "azucares_g"):
        _set(df, kcal_known, k, 0.0, est)

    # EPA y DHA solo vienen de animales (o aceite de algas, que no hay en el catálogo): en un vegano es 0. Se fuerza
    # aunque BEDCA dé un valor, porque da EPA+DHA a nueces, cacahuete y aceite de girasol (probablemente ALA mal
    # clasificado).
    if "vegano" in df and col("epa_dha_mg") in df:
        vegan = df["vegano"].astype(bool)
        df.loc[vegan, col("epa_dha_mg")] = 0.0
        df.loc[vegan, known_col("epa_dha_mg")] = True

    known_fat = df[known_col("grasa_g")]
    med = df[known_fat].groupby("subcategoria")[col("grasa_g")].agg(["median", "size"])
    ok = med[(med["size"] >= MIN_EJEMPLOS) & (med["median"] <= MAX_GRASA_MEDIANA)]["median"]
    _set(df, sub.isin(ok.index), "grasa_g", sub.map(ok), est)

    for key, parent, tope in RATIOS:
        both = df[known_col(key)] & df[known_col(parent)] & (df[col(parent)] > 0)
        r = (df.loc[both, col(key)] / df.loc[both, col(parent)]).clip(upper=1.0)
        pk = df[known_col(parent)]
        # primero la mediana de la subcategoría; si no hay ejemplos, la de la categoría (si existe la columna)
        for grupo in [sub] + ([df["categoria"]] if "categoria" in df else []):
            g = r.groupby(grupo[both]).agg(["median", "size"])
            ratio = g[g["size"] >= MIN_EJEMPLOS]["median"]
            _set(df, pk & grupo.isin(ratio.index), key, df[col(parent)] * grupo.map(ratio), est)
        _set(df, pk & (df[col(parent)] <= tope), key, df[col(parent)], est)

    df["estimados"] = [",".join(est.get(i, [])) for i in df.index]
    return df
