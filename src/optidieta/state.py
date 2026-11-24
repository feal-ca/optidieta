"""Preferencias del usuario (vetos, precios, objetivos editados) guardadas en un JSON local."""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from optidieta.fsutil import write_atomic
from optidieta.targets import Constraint, Profile


@dataclass
class UserState:
    profile: Profile
    diet: str = "omnivora"
    excluded: set[str] = field(default_factory=set)
    price_overrides: dict[str, float] = field(default_factory=dict)
    constraint_edits: dict[str, dict] = field(default_factory=dict)
    max_g: float = 500.0
    margen: float = 0.0

    @staticmethod
    def default() -> "UserState":
        return UserState(Profile("h", 30, 70.0))


def load_state(path: Path) -> UserState:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return UserState(
            profile=Profile(d["profile"]["sexo"], int(d["profile"]["edad"]), float(d["profile"]["peso_kg"])),
            diet=d.get("diet", "omnivora"),
            excluded=set(map(str, d.get("excluded", []))),
            price_overrides={str(k): float(v) for k, v in d.get("price_overrides", {}).items()},
            constraint_edits=dict(d.get("constraint_edits", {})),
            max_g=float(d.get("max_g", 500.0)),
            margen=min(max(float(d.get("margen", 0.0)), 0.0), 0.5),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return UserState.default()


def save_state(s: UserState, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    d = {
        "profile": {"sexo": s.profile.sexo, "edad": s.profile.edad, "peso_kg": s.profile.peso_kg},
        "diet": s.diet, "excluded": sorted(s.excluded), "price_overrides": s.price_overrides,
        "constraint_edits": s.constraint_edits, "max_g": s.max_g, "margen": s.margen,
    }
    write_atomic(path, json.dumps(d, ensure_ascii=False, indent=1))


def apply_edits(base: list[Constraint], edits: dict[str, dict]) -> list[Constraint]:
    out = []
    for c in base:
        e = edits.get(c.key) or {}
        out.append(replace(c, **{k: v for k, v in e.items() if k in ("min", "max", "active")}))
    return out
