"""Emparejamiento producto Mercadona ↔ alimento BEDCA, guardado en un CSV revisable a mano."""

import re
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from optidieta.sources.mercadona import MercaProduct
from optidieta.textutil import norm

COLUMNS = ["mercadona_id", "nombre", "bedca_id", "bedca_nombre", "confianza", "revisado", "excluir",
           "porcion_comestible", "g_por_unidad", "vegetariano", "vegano"]
MARCAS = ["hacendado", "deliplus", "bosque verde", "compy", "mercadona"]
COCINADO = ("hervid", "cocid", "frit", "asad", "guisad", "en conserva", "en almibar")
CRUDO = ("crud", "sec", "fresc")

HUEVO_G = 60


def default_unit_grams(p: MercaProduct) -> float | None:
    """Peso por unidad de venta para productos por unidades conocidos (huevos: 60 g/huevo)."""
    if (p.formato_ref or "").lower() in ("kg", "l", "100 g", "100 ml"):
        return None
    name = norm(p.nombre)
    if "huevo" not in name:
        return None
    m = re.search(r"\b(\d+)\s*(ud|uds|unidades|huevos)\b", name)
    n = int(m.group(1)) if m else (12 if "docena" in name or (p.formato_ref or "").lower() == "docena" else None)
    if n is None and "media docena" in name:
        n = 6
    return n * HUEVO_G if n else None


_PESO = re.compile(r"\b\d+([.,]\d+)?\s*(kg|g|gr|l|ml|cl|ud|uds|unidades)\b|\bpack\s*\d+\b|\b\d+\s*x\s*\d+\b")


def _clean(s: str, marca: str = "") -> str:
    s = norm(s)
    for m in MARCAS + ([norm(marca)] if marca else []):
        s = s.replace(m, " ")
    s = _PESO.sub(" ", s)
    s = re.sub(r"[^a-zñ ]", " ", s)
    toks = []
    for t in s.split():
        if len(t) > 4 and t.endswith("es") and not t.endswith("ses"):
            t = t[:-2] if t[-3] in "rlnd" else t[:-1]
        elif len(t) > 3 and t.endswith("s"):
            t = t[:-1]
        toks.append(t)
    return " ".join(toks)


def propose(products: list[MercaProduct], bedca: pd.DataFrame) -> pd.DataFrame:
    names = [_clean(n) for n in bedca["bedca_nombre"]]
    heads = [_clean(str(n).split(",")[0]) for n in bedca["bedca_nombre"]]
    raw_bias = np.array([1 if any(w in n for w in CRUDO) else (-1 if any(w in n for w in COCINADO) else 0)
                         for n in names], dtype=float)
    queries = [_clean(p.nombre, p.marca) for p in products]
    rows = []
    if not queries or not names:
        return pd.DataFrame(columns=COLUMNS)
    # el nombre BEDCA es "Alimento, descriptor, descriptor": pesa más el alimento que los descriptores
    scores = (0.7 * process.cdist(queries, heads, scorer=fuzz.token_set_ratio, workers=-1)
              + 0.3 * process.cdist(queries, names, scorer=fuzz.token_set_ratio, workers=-1))
    for p, q, sc in zip(products, queries, scores):
        cooked = any(w in q for w in COCINADO)
        adj = sc + 8 * (-raw_bias if cooked else raw_bias)
        j = int(np.argmax(adj))
        b = bedca.iloc[j]
        pc = b.get("porcion_comestible")
        rows.append({
            "mercadona_id": str(p.id), "nombre": p.nombre, "bedca_id": int(b["bedca_id"]),
            "bedca_nombre": b["bedca_nombre"], "confianza": int(round(float(sc[j]))), "revisado": "no",
            "excluir": "no", "porcion_comestible": float(pc) if pd.notna(pc) and pc else 1.0,
            "g_por_unidad": default_unit_grams(p), "vegetariano": "", "vegano": "",
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def merge(existing: pd.DataFrame, proposed: pd.DataFrame) -> pd.DataFrame:
    if existing is None or existing.empty:
        out = proposed.copy()
    else:
        reviewed = existing[existing["revisado"] == "sí"]
        keep = set(reviewed["mercadona_id"])
        out = pd.concat([reviewed, proposed[~proposed["mercadona_id"].isin(keep)]], ignore_index=True)
    out = out[COLUMNS].drop_duplicates("mercadona_id", keep="first")
    key = pd.to_numeric(out["mercadona_id"], errors="coerce")
    return out.assign(_k=key).sort_values(["_k", "mercadona_id"], kind="stable").drop(columns="_k").reset_index(drop=True)


def read_mapping(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, encoding="utf-8")
    for c in COLUMNS:
        if c not in df:
            df[c] = ""
    df = df[COLUMNS]
    df["bedca_id"] = pd.to_numeric(df["bedca_id"], errors="coerce").astype("Int64")
    for c in ("confianza", "porcion_comestible", "g_por_unidad"):
        df[c] = pd.to_numeric(df[c].str.replace(",", "."), errors="coerce")
    for c in ("revisado", "excluir"):
        df[c] = df[c].str.strip().str.lower().replace({"si": "sí"})
    return df


def write_mapping(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df[COLUMNS].copy()
    out["bedca_id"] = out["bedca_id"].astype("Int64")
    tmp = path.with_suffix(".tmp")
    out.to_csv(tmp, sep=";", index=False, encoding="utf-8")
    tmp.replace(path)
