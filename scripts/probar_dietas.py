"""Prueba real: dieta más barata para un perfil en las tres dietas. Uso: uv run python scripts/probar_dietas.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from optidieta.catalog import load_catalog
from optidieta.cli import paths
from optidieta.nutrients import BY_KEY
from optidieta.optimizer import solve
from optidieta.targets import Profile, default_constraints, for_diet

cat = load_catalog(paths()["catalog"])
cs = default_constraints(Profile("h", 30, 70))
for diet in ("omnivora", "vegetariana", "vegana"):
    s = solve(cat, for_diet(cs, diet), diet=diet)
    print(f"\n== {diet}: {'factible' if s.feasible else 'NO factible'}"
          + (f", {s.cost_day:.2f} €/día, {s.cost_day * 7:.2f} €/semana" if s.feasible else
             f" — lo impiden: {', '.join(BY_KEY[k].label for k in s.blocking)}"))
    for p in s.portions:
        print(f"   {p.grams:6.0f} g  {p.cost:5.2f} €  {p.nombre}")
