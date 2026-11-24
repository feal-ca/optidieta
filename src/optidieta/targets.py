"""Objetivos nutricionales por perfil (EFSA), leídos de data/targets_efsa.json."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from optidieta.nutrients import BY_KEY

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "targets_efsa.json"
KCAL_POR_MJ = 239.006


@dataclass
class Profile:
    sexo: Literal["h", "m"]
    edad: int
    peso_kg: float = 70.0


@dataclass
class Constraint:
    key: str
    label: str
    unit: str
    min: float | None
    max: float | None
    active: bool = True
    kind: Literal["abs", "pct_energia"] = "abs"
    kcal_por_g: float | None = None
    fuente: str = ""


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _resolve(spec, p: Profile) -> float | None:
    if spec is None or isinstance(spec, (int, float)):
        return spec
    if "por_kg" in spec:
        return spec["por_kg"] * p.peso_kg
    if "edad_lt" in spec:
        return _resolve(spec["si"] if p.edad < spec["edad_lt"] else spec["no"], p)
    if p.sexo in spec:
        return _resolve(spec[p.sexo], p)
    raise ValueError(f"especificación no reconocida: {spec}")


def energy_kcal(p: Profile, path: Path = DEFAULT_PATH) -> float:
    e = _load(path)["energia"]
    for hasta, a, b in e["henry_mj"][p.sexo]:
        if p.edad < hasta:
            return (a * p.peso_kg + b) * e["pal"] * KCAL_POR_MJ
    raise ValueError(p)


def default_constraints(p: Profile, path: Path = DEFAULT_PATH) -> list[Constraint]:
    data = _load(path)
    e = energy_kcal(p, path)
    band = data["energia"]["banda"]
    en = BY_KEY["energia_kcal"]
    out = [Constraint("energia_kcal", en.label, en.unit, (1 - band) * e, (1 + band) * e,
                      fuente=data["energia"]["fuente"])]
    for key, s in data["nutrientes"].items():
        n = BY_KEY[key]
        kind = s.get("kind", "abs")
        out.append(Constraint(
            key=key, label=n.label, unit="% E" if kind == "pct_energia" else n.unit,
            min=_resolve(s.get("min"), p), max=_resolve(s.get("max"), p), active=s.get("active", True),
            kind=kind, kcal_por_g=s.get("kcal_por_g"), fuente=s.get("fuente", ""),
        ))
    return out


def apply_margin(cs: list[Constraint], margin: float) -> list[Constraint]:
    """Sube los mínimos y baja los máximos un `margin` (0,1 = 10 %), salvo la energía, que ya es una banda.

    Si el margen cruzara mínimo y máximo, el objetivo se deja como está.
    """
    from dataclasses import replace
    if margin <= 0:
        return list(cs)
    out = []
    for c in cs:
        mn = c.min * (1 + margin) if c.min is not None else None
        mx = c.max * (1 - margin) if c.max is not None else None
        if c.key == "energia_kcal" or (mn is not None and mx is not None and mn > mx):
            out.append(c)
        else:
            out.append(replace(c, min=mn, max=mx))
    return out


SIN_PESCADO = {"epa_dha_mg"}  # objetivos que solo se pueden cumplir con pescado (o suplemento)


def for_diet(cs: list[Constraint], diet: str) -> list[Constraint]:
    """En vegetariana y vegana, los objetivos que exigen pescado vienen desactivados (se pueden activar a mano)."""
    from dataclasses import replace
    if diet == "omnivora":
        return list(cs)
    return [replace(c, active=False) if c.key in SIN_PESCADO else c for c in cs]
