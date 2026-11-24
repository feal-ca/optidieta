"""Une Mercadona (precio), BEDCA (nutrientes) y Open Food Facts (etiqueta) en el catálogo del optimizador."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from optidieta.diet import diet_flags
from optidieta.estimate import fill_estimates
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
    con_etiqueta_mercadona: int = 0
    etiqueta_descartada: list[str] = field(default_factory=list)
    sin_bedca: list[str] = field(default_factory=list)
    revisar_emparejamiento: list[str] = field(default_factory=list)
    duplicados: list[str] = field(default_factory=list)

    def texto(self) -> str:
        return (f"Incluidos: {self.incluidos}\nSin revisar (fuera): {self.sin_revisar}\n"
                f"Con etiqueta de la foto de Mercadona: {self.con_etiqueta_mercadona}\n"
                f"Con etiqueta Open Food Facts: {self.con_etiqueta}\n"
                f"Etiqueta descartada (kcal incoherentes): {len(self.etiqueta_descartada)} "
                f"{self.etiqueta_descartada[:20]}\n"
                f"Desaparecidos de Mercadona: {len(self.desaparecidos)} {self.desaparecidos[:20]}\n"
                f"Sin precio calculable: {len(self.sin_precio)} {self.sin_precio[:20]}\n"
                f"Sin alimento BEDCA válido: {len(self.sin_bedca)} {self.sin_bedca[:20]}\n"
                f"Filas duplicadas en mapping.csv (se usa la primera): {self.duplicados}\n"
                f"Etiqueta de Mercadona muy lejos de BEDCA (revisar emparejamiento): "
                f"{len(self.revisar_emparejamiento)} {self.revisar_emparejamiento[:20]}")


def _flag(v, default: bool) -> bool:
    s = str(v).strip().lower() if v is not None and not pd.isna(v) else ""
    if s in ("sí", "si", "true", "1"):
        return True
    if s in ("no", "false", "0"):
        return False
    return default


def build_catalog(products: list[MercaProduct], bedca: pd.DataFrame, mapping: pd.DataFrame,
                  labels: Mapping[str, dict[str, float]],
                  merca_labels: Mapping[str, dict[str, float]] | None = None) -> tuple[pd.DataFrame, BuildReport]:
    """`merca_labels` (foto de la etiqueta de Mercadona) tiene prioridad sobre `labels` (Open Food Facts)."""
    rep = BuildReport()
    by_id = {str(p.id): p for p in products}
    bedca_by_id = bedca.set_index("bedca_id")
    # BEDCA repite alimentos con varios ids; si al elegido le falta un nutriente, se toma la mediana de los
    # demás ids con el mismo nombre (es el mismo alimento, no una estimación)
    same_name = {n.key: bedca[bedca[known_col(n.key)]].groupby("bedca_nombre")[col(n.key)].median()
                 for n in NUTRIENTS}
    # Conservas sin EPA+DHA en BEDCA cuyo valor coincide con el del pescado crudo (comprobado con USDA: sardina en
    # aceite escurrida ~980 mg/100 g, BEDCA cruda 930). El atún en lata NO: el claro tiene ~130 frente a 749 del
    # "Atún, crudo" (rojo), y copiarlo haría del atún en lata una fuente de omega-3 que no es.
    epa_equiv = {"Sardina, enlatada, en aceite, escurrida": "Sardina",
                 "Caballa, enlatada en aceite, escurrida": "Caballa, cruda"}
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
            "estimados": "",
        }
        for n in NUTRIENTS:
            row[col(n.key)] = float(b[col(n.key)])
            row[known_col(n.key)] = bool(b[known_col(n.key)])
            if not row[known_col(n.key)] and b["bedca_nombre"] in same_name[n.key].index:
                row[col(n.key)] = float(same_name[n.key][b["bedca_nombre"]])
                row[known_col(n.key)] = True
        eq = epa_equiv.get(b["bedca_nombre"])
        if not row[known_col("epa_dha_mg")] and eq in same_name["epa_dha_mg"].index:
            row[col("epa_dha_mg")] = float(same_name["epa_dha_mg"][eq])
            row[known_col("epa_dha_mg")] = True
            row["estimados"] = "epa_dha_mg"
        descartada = False
        for fuente, lab in (("mercadona", (merca_labels or {}).get(mid) or {}), ("off", labels.get(mid) or {})):
            if not lab:
                continue
            e_lab, e_bed = lab.get("energia_kcal"), row[col("energia_kcal")]
            lejos = (e_lab is not None and e_bed == e_bed and e_bed > 0
                     and not (e_bed / 3 <= e_lab <= e_bed * 3))  # etiqueta de otro producto
            if not label_is_plausible(lab) or (lejos and fuente == "off"):
                descartada = True
                continue
            if lejos:  # la foto es de este producto: si no cuadra con BEDCA, lo sospechoso es el emparejamiento
                rep.revisar_emparejamiento.append(mid)
            for k, v in lab.items():  # la de Mercadona trae también vitaminas y minerales de los enriquecidos
                row[col(k)] = float(v)
                row[known_col(k)] = True
            row["fuente_etiqueta"] = fuente
            if fuente == "mercadona":
                rep.con_etiqueta_mercadona += 1
            else:
                rep.con_etiqueta += 1
            descartada = False
            break
        if descartada:
            rep.etiqueta_descartada.append(mid)
        rows.append(row)
    rep.incluidos = len(rows)
    cols = ["id", "nombre", "categoria", "subcategoria", "url", "precio_100g", "vegetariano", "vegano",
            "bedca_nombre", "fuente_etiqueta", "estimados",
            *[c for n in NUTRIENTS for c in (col(n.key), known_col(n.key))]]
    return fill_estimates(pd.DataFrame(rows, columns=cols)), rep


def load_catalog(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if "estimados" not in df:  # catálogo construido antes de las estimaciones
        df["estimados"] = ""
    return df
