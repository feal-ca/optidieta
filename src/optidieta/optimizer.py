"""Dieta de coste mínimo por programación lineal (scipy/HiGHS). Sin dependencias de interfaz."""

from dataclasses import dataclass, field
from typing import Literal, Mapping

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from optidieta.nutrients import NUTRIENTS, col, known_col
from optidieta.targets import Constraint

MIN_GRAMS = 1.0
PENALTY = 1e3


@dataclass
class Portion:
    id: str
    nombre: str
    grams: float
    cost: float


@dataclass
class NutrientTotal:
    value: float
    known_fraction: float


@dataclass
class Solution:
    feasible: bool
    cost_day: float
    portions: list[Portion] = field(default_factory=list)
    totals: dict[str, NutrientTotal] = field(default_factory=dict)
    blocking: list[str] = field(default_factory=list)
    unverified_max: list[str] = field(default_factory=list)


@dataclass
class SolutionDiff:
    cost_delta: float
    added: list[str]
    removed: list[str]


def _filter(foods: pd.DataFrame, excluded, diet: str) -> pd.DataFrame:
    df = foods[~foods["id"].astype(str).isin(set(excluded))]
    if diet == "vegana":
        df = df[df["vegano"].astype(bool)]
    elif diet == "vegetariana":
        df = df[df["vegetariano"].astype(bool)]
    return df.reset_index(drop=True)


def _cheapest_format(df: pd.DataFrame, price: np.ndarray) -> tuple[pd.DataFrame, np.ndarray]:
    """Productos que son el mismo alimento (mismo alimento BEDCA o, sin él, mismo nombre) cuentan como uno solo:
    se queda el más barato. Si no, el LP reparte gramos entre formatos para saltarse el máximo por alimento.
    """
    if df.empty or "nombre" not in df:
        return df, price
    name = df["nombre"].astype(str).str.lower().str.split().str.join(" ")
    if "bedca_nombre" in df:
        b = df["bedca_nombre"]
        name = ("b:" + b.astype(str)).where(b.notna() & (b.astype(str).str.strip() != ""), "n:" + name)
    keep = pd.Series(price, index=df.index).groupby(name).idxmin().sort_values().to_numpy()
    return df.loc[keep].reset_index(drop=True), price[keep]


def _rows(df: pd.DataFrame, constraints: list[Constraint]):
    """Filas A_ub·x ≤ b_ub (x en gramos), con la clave y el límite de cada una."""
    per_g = {n.key: df[col(n.key)].fillna(0).to_numpy(float) / 100 for n in NUTRIENTS if col(n.key) in df}
    A, b, keys, lims = [], [], [], []
    e_target = next((c.min or c.max for c in constraints if c.key == "energia_kcal" and c.active
                     and (c.min or c.max)), 2000.0)
    for c in constraints:
        if not c.active or c.key not in per_g:
            continue
        a = per_g[c.key]
        if c.kind == "pct_energia":
            if "energia_kcal" not in per_g:
                continue
            fac, e = (c.kcal_por_g or 0), per_g["energia_kcal"]
            if c.min is not None:  # fac·n ≥ min·E  →  min·E − fac·n ≤ 0
                A.append(c.min * e - fac * a); b.append(0.0); keys.append(c.key); lims.append(max(c.min * e_target, 1.0))
            if c.max is not None:
                A.append(fac * a - c.max * e); b.append(0.0); keys.append(c.key); lims.append(max(c.max * e_target, 1.0))
        else:
            if c.min is not None:
                A.append(-a); b.append(-c.min); keys.append(c.key); lims.append(max(abs(c.min), 1.0))
            if c.max is not None:
                A.append(a); b.append(c.max); keys.append(c.key); lims.append(max(abs(c.max), 1.0))
    return A, b, keys, lims


def _blocking(cost, A, b, keys, lims, max_g, n) -> list[str]:
    """LP elástico: cada restricción puede violarse pagando una penalización; devuelve las que se violan."""
    m = len(A)
    if m == 0:
        return []
    A_el = np.hstack([np.array(A) if n else np.zeros((m, 0)), -np.diag(lims)])
    c_el = np.concatenate([cost, np.full(m, PENALTY)])
    bounds = [(0, max_g)] * n + [(0, None)] * m
    r = linprog(c_el, A_ub=A_el, b_ub=np.array(b), bounds=bounds, method="highs")
    if r.status != 0:
        return sorted(set(keys))
    slack = r.x[n:]
    worst: dict[str, float] = {}
    for k, s in zip(keys, slack):
        if s > 1e-6:
            worst[k] = max(worst.get(k, 0.0), s)
    return sorted(worst, key=lambda k: -worst[k])


def solve(foods: pd.DataFrame, constraints: list[Constraint], *, excluded: frozenset[str] = frozenset(),
          price_overrides: Mapping[str, float] = {}, max_g: float = 500.0,
          diet: Literal["omnivora", "vegetariana", "vegana"] = "omnivora") -> Solution:
    df = _filter(foods, excluded, diet)
    price = df["precio_100g"].to_numpy(float).copy()
    for i, fid in enumerate(df["id"].astype(str)):
        if fid in price_overrides:
            price[i] = price_overrides[fid]
    df, price = _cheapest_format(df, price)
    n = len(df)
    cost = price / 100
    A, b, keys, lims = _rows(df, constraints)

    if n == 0:
        if not A or all(bi >= 0 for bi in b):
            return Solution(True, 0.0, totals={nu.key: NutrientTotal(0.0, 1.0) for nu in NUTRIENTS})
        return Solution(False, 0.0, blocking=_blocking(cost, A, b, keys, lims, max_g, 0))

    r = linprog(cost, A_ub=np.array(A) if A else None, b_ub=np.array(b) if b else None,
                bounds=[(0, max_g)] * n, method="highs")
    if r.status != 0:
        return Solution(False, 0.0, blocking=_blocking(cost, A, b, keys, lims, max_g, n))

    x = np.where(r.x < MIN_GRAMS, 0.0, r.x)
    portions = [Portion(str(df.id[i]), str(df.nombre[i]), float(x[i]), float(x[i] * cost[i]))
                for i in np.argsort(-x) if x[i] > 0]
    totals = {}
    chosen = x > 0
    gsum = x.sum()
    for nu in NUTRIENTS:
        if col(nu.key) not in df:
            continue
        vals = df[col(nu.key)].fillna(0).to_numpy(float) / 100
        known = df[known_col(nu.key)].to_numpy(bool)
        frac = float(x[known].sum() / gsum) if gsum > 0 else 1.0
        totals[nu.key] = NutrientTotal(float(vals @ x), frac)
    unverified = [c.key for c in constraints
                  if c.active and c.max is not None and c.key in totals
                  and (~df[known_col(c.key)].to_numpy(bool) & chosen).any()]
    return Solution(True, float(cost @ x), portions, totals, [], list(dict.fromkeys(unverified)))


def compare(prev: Solution, new: Solution) -> SolutionDiff:
    a = {p.id for p in prev.portions}
    b = {p.id for p in new.portions}
    order_new = [p.id for p in new.portions]
    order_prev = [p.id for p in prev.portions]
    return SolutionDiff(new.cost_day - prev.cost_day,
                        [i for i in order_new if i not in a], [i for i in order_prev if i not in b])
