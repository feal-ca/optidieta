"""Datos del gráfico de rangos: cada nutriente en % de su referencia EFSA, y cómo un arrastre cambia el objetivo."""

import math
from collections.abc import Mapping, Set

from optidieta.nutrients import col
from optidieta.optimizer import Solution
from optidieta.targets import Constraint

AXIS_MAX = 300.0  # % de la referencia; lo que pase de aquí se dibuja en el borde

GRUPOS = {
    "Energía y macronutrientes": ["energia_kcal", "proteina_g", "hidratos_g", "azucares_g", "fibra_g", "grasa_g",
                                  "grasa_sat_g", "epa_dha_mg", "colesterol_mg"],
    "Minerales": ["sodio_mg", "cloruro_mg", "potasio_mg", "calcio_mg", "magnesio_mg", "fosforo_mg", "hierro_mg",
                  "zinc_mg", "cobre_mg", "manganeso_mg", "selenio_ug", "yodo_ug"],
    "Vitaminas": ["vit_a_ug", "vit_d_ug", "vit_e_mg", "tiamina_mg", "riboflavina_mg", "niacina_mg", "vit_b5_mg",
                  "vit_b6_mg", "vit_b12_ug", "vit_c_mg", "folato_ug"],
}
_GRUPO = {k: g for g, ks in GRUPOS.items() for k in ks}


def to_display(c: Constraint, v: float | None) -> float | None:
    """Valor en las unidades que ve el usuario (% E para los de porcentaje de energía)."""
    return None if v is None else (v * 100 if c.kind == "pct_energia" else v)


def from_display(c: Constraint, v: float | None) -> float | None:
    """Inverso de `to_display`."""
    if v is None:
        return None
    return v / 100 if c.kind == "pct_energia" else float(v)


def reference(base: Constraint) -> float | None:
    """El 100 % del eje: el mínimo EFSA, o el máximo si no hay mínimo."""
    r = to_display(base, base.min if base.min is not None else base.max)
    return r if r else None


def diet_value(c: Constraint, sol: Solution) -> float | None:
    """Total del nutriente en la dieta, en unidades de pantalla; None si no hay dieta."""
    if not sol.feasible or c.key not in sol.totals:
        return None
    v = sol.totals[c.key].value
    if c.kind == "pct_energia":
        kcal = sol.totals["energia_kcal"].value if "energia_kcal" in sol.totals else 0
        return (c.kcal_por_g or 0) * v / kcal * 100 if kcal else 0.0
    return v


def _num(x: float) -> str:
    d = 0 if abs(x) >= 100 else 1 if abs(x) >= 1 else 2
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def _pct(v: float | None, ref: float) -> float | None:
    return None if v is None else v / ref * 100


def range_text(c: Constraint) -> str:
    lo, hi = to_display(c, c.min), to_display(c, c.max)
    if lo is not None and hi is not None:
        return f"{_num(lo)}–{_num(hi)}"
    if lo is not None:
        return f"≥ {_num(lo)}"
    return f"≤ {_num(hi)}" if hi is not None else "—"


def _edited(c: Constraint, b: Constraint) -> bool:
    return (c.min, c.max, c.active) != (b.min, b.max, b.active)


def food_contrib(food: Mapping, grams: float, constraints: list[Constraint], sol: Solution) -> dict[str, float | None]:
    """Lo que aporta un alimento (grams g) a cada nutriente, en unidades de pantalla; None si no hay dato."""
    kcal = sol.totals["energia_kcal"].value if "energia_kcal" in sol.totals else 0
    out: dict[str, float | None] = {}
    for c in constraints:
        v = food.get(col(c.key))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out[c.key] = None
            continue
        g = float(v) * grams / 100
        out[c.key] = ((c.kcal_por_g or 0) * g / kcal * 100 if kcal else 0.0) if c.kind == "pct_energia" else g
    return out


def combine_contrib(parts: list[Mapping[str, float | None]]) -> tuple[dict[str, float | None], set[str]]:
    """Suma los aportes de varios alimentos. Devuelve el total (None si ninguno tiene dato) y los nutrientes en
    los que falta el dato de alguno (el total es entonces un mínimo)."""
    total: dict[str, float | None] = {}
    partial: set[str] = set()
    for k in set().union(*parts) if parts else set():
        vals = [p.get(k) for p in parts]
        known = [v for v in vals if v is not None]
        total[k] = sum(known) if known else None
        if known and len(known) < len(vals):
            partial.add(k)
    return total, partial


def nutrient_rows(base: list[Constraint], constraints: list[Constraint], sol: Solution,
                  contrib: Mapping[str, float | None] | None = None, defaults: list[Constraint] | None = None,
                  estimated: Set[str] = frozenset(), contrib_partial: Set[str] = frozenset()) -> list[dict]:
    """Filas del gráfico. `base` (EFSA) da la banda y la escala; `defaults` (EFSA con margen) dice qué objetivos
    ha cambiado el usuario; `estimated` son los nutrientes en los que algún alimento elegido lleva un valor estimado.
    """
    base_by = {b.key: b for b in base}
    def_by = {d.key: d for d in (defaults or base)}
    rows = []
    for c in constraints:
        b, d = base_by[c.key], def_by[c.key]
        ref = reference(b)
        if ref is None:
            continue
        val = diet_value(c, sol)
        lo, hi = _pct(to_display(b, b.min), ref), _pct(to_display(b, b.max), ref)
        p = _pct(val, ref)
        status = None
        if p is not None:
            status = "bajo" if lo is not None and p < lo - 0.5 else "alto" if hi is not None and p > hi + 0.5 else "ok"
        t = sol.totals.get(c.key)
        cv = contrib.get(c.key) if contrib else None
        rows.append({
            "key": c.key, "label": c.label, "unit": c.unit, "group": _GRUPO.get(c.key, "Otros"), "ref": ref,
            "band_lo": lo or 0.0, "band_hi": hi, "value": p,
            "value_txt": None if val is None else f"{_num(val)} {c.unit}",
            "range_txt": range_text(b), "active": c.active, "status": status,
            "edited": _edited(c, d), "target_shown": _edited(c, b),
            "target_lo": _pct(to_display(c, c.min), ref), "target_hi": _pct(to_display(c, c.max), ref),
            "target_txt": range_text(c) if _edited(c, b) else None, "estimated": c.key in estimated,
            "contrib": _pct(cv, ref),
            "contrib_txt": _contrib_txt(cv, c, contrib_partial) if contrib else None,
            "contrib_share": cv / val if cv is not None and val else None,
            "warn": bool(t is not None and (t.known_fraction < 0.999 or c.key in sol.unverified_max)),
        })
    return rows


def _contrib_txt(v: float | None, c: Constraint, partial: Set[str]) -> str:
    if v is None:
        return "sin dato"
    return ("≥ " if c.key in partial else "") + f"{_num(v)} {c.unit}"


def drag_edit(base: Constraint, current_pct: float | None, new_pct: float, ref: float | None = None) -> dict:
    """Edición del objetivo tras soltar el punto en new_pct (% de la referencia).

    Hacia arriba fija un mínimo y hacia abajo un máximo; el otro límite vuelve al de EFSA, salvo que choque,
    en cuyo caso se iguala al nuevo valor. Cada arrastre sustituye al anterior. `base` es el objetivo por defecto
    (EFSA con margen) y `ref` el 100 % del eje (por defecto, el de `base`).
    """
    ref = ref if ref is not None else reference(base)
    if ref is None:
        raise ValueError(f"{base.key} no tiene referencia")
    v = new_pct / 100 * ref
    if base.kind == "pct_energia":
        v /= 100
    mn, mx = base.min, base.max
    if current_pct is None or new_pct >= current_pct:
        mn = v
        if mx is not None and mx < v:
            mx = v
    else:
        mx = v
        if mn is not None and mn > v:
            mn = v
    e = {}
    if mn != base.min:
        e["min"] = mn
    if mx != base.max:
        e["max"] = mx
    if not base.active:
        e["active"] = True
    return e
