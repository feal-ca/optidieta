"""Une Mercadona (precio), BEDCA (nutrientes) y Open Food Facts (etiqueta) en el catálogo del optimizador."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import pandas as pd

from optidieta.diet import diet_flags
from optidieta.nutrients import NUTRIENTS, col, known_col
from optidieta.pricing import price_per_100g
from optidieta.sources.mercadona import MercaProduct
from optidieta.sources.off import label_is_plausible


@dataclass
class BuildReport:
    incluidos: int = 0
    sin_revisar: int = 0
    desaparecidos: list[str] = field(default_factory=list)
    sin_precio: list[str] = field(default_factory=list)
    con_etiqueta: int = 0
    etiqueta_descartada: list[str] = field(default_factory=list)
    sin_bedca: list[str] = field(default_factory=list)
    duplicados: list[str] = field(default_factory=list)

    def texto(self) -> str:
        return (f"Incluidos: {self.incluidos}\nSin revisar (fuera): {self.sin_revisar}\n"
                f"Con etiqueta Open Food Facts: {self.con_etiqueta}\n"
                f"Etiqueta descartada (kcal incoherentes): {len(self.etiqueta_descartada)} {self.etiqueta_descartada[:20]}\n"
                f"Desaparecidos de Mercadona: {len(self.desaparecidos)} {self.desaparecidos[:20]}\n"
                f"Sin precio calculable: {len(self.sin_precio)} {self.sin_precio[:20]}\n"
                f"Sin alimento BEDCA válido: {len(self.sin_bedca)} {self.sin_bedca[:20]}\n"
                f"Filas duplicadas en mapping.csv (se usa la primera): {self.duplicados}")


def _flag(v, default: bool) -> bool:
    s = str(v).strip().lower() if v is not None and not pd.isna(v) else ""
    if s in ("sí", "si", "true", "1"):
        return True
    if s in ("no", "false", "0"):
        return False
    return default


def build_catalog(products: list[MercaProduct], bedca: pd.DataFrame, mapping: pd.DataFrame,
                  labels: Mapping[str, dict[str, float]]) -> tuple[pd.DataFrame, BuildReport]:
    rep = BuildReport()
    by_id = {str(p.id): p for p in products}
    bedca_by_id = bedca.set_index("bedca_id")
    rows = []
    seen: set[str] = set()
    for _, m in mapping.iterrows():
        mid = str(m["mercadona_id"])
        if mid in seen:
            rep.duplicados.append(mid)
            continue
        seen.add(mid)
        if str(m.get("excluir", "")).strip().lower() in ("sí", "si"):
            continue
        if str(m.get("revisado", "")).strip().lower() not in ("sí", "si"):
            rep.sin_revisar += 1
            continue
        p = by_id.get(mid)
        if p is None:
            rep.desaparecidos.append(mid)
            continue
        bid = m.get("bedca_id")
        if pd.isna(bid) or int(bid) not in bedca_by_id.index:
            rep.sin_bedca.append(mid)
            continue
        b = bedca_by_id.loc[int(bid)]
        g = m.get("g_por_unidad")
        precio = price_per_100g(p, m.get("porcion_comestible"), None if pd.isna(g) else float(g), None)
        if precio is None:
            rep.sin_precio.append(mid)
            continue
        veg, vegan = diet_flags(p)
        row = {
            "id": mid, "nombre": p.nombre, "categoria": p.categoria, "subcategoria": p.subcategoria, "url": p.url,
            "precio_100g": precio, "vegetariano": _flag(m.get("vegetariano"), veg),
            "vegano": _flag(m.get("vegano"), vegan), "bedca_nombre": b["bedca_nombre"], "fuente_etiqueta": "bedca",
        }
        for n in NUTRIENTS:
            row[col(n.key)] = float(b[col(n.key)])
            row[known_col(n.key)] = bool(b[known_col(n.key)])
        lab = labels.get(mid) or {}
        if lab:
            if label_is_plausible(lab):
                for k, v in lab.items():
                    row[col(k)] = float(v)
                    row[known_col(k)] = True
                row["fuente_etiqueta"] = "off"
                rep.con_etiqueta += 1
            else:
                rep.etiqueta_descartada.append(mid)
        rows.append(row)
    rep.incluidos = len(rows)
    cols = ["id", "nombre", "categoria", "subcategoria", "url", "precio_100g", "vegetariano", "vegano",
            "bedca_nombre", "fuente_etiqueta"] + [c for n in NUTRIENTS for c in (col(n.key), known_col(n.key))]
    return pd.DataFrame(rows, columns=cols), rep


def load_catalog(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)
