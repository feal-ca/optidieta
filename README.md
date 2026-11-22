# Optidieta

Calcula la dieta diaria más barata que cumple unos objetivos nutricionales, con productos de Mercadona (tienda de Barcelona) y sus precios. Los nutrientes salen de BEDCA y, cuando hay etiqueta, de Open Food Facts. La idea es la del [Nutrient Optimizer de Right of the Bell](https://www.rightofthebell.com/nutrient), con datos españoles.

## Uso

```
uv run streamlit run app.py
```

En la barra lateral eliges dieta (omnívora, vegetariana o vegana), sexo, edad, peso y el máximo de gramos por alimento. La pestaña Dieta muestra la compra del día, el coste y cómo queda cada nutriente; la casilla "Vetar" quita un producto. En Objetivos puedes cambiar mínimos y máximos o desactivar alguno, y en Catálogo buscar productos, vetarlos o poner tu propio precio. Todo se guarda en `data/estado.json`.

Si la dieta no es posible, la app dice qué nutriente lo impide y deja desactivarlo. La vegana sin productos enriquecidos suele fallar por la B12 y la vitamina D.

## Actualizar precios y productos

```
uv run optidieta fetch --refresh   # vuelve a bajar listados y precios de Mercadona
uv run python scripts/revisar_mapping.py
uv run optidieta build
```

`fetch` guarda todo en `data/raw/` y, si se corta, continúa donde lo dejó. Open Food Facts limita las peticiones; si avisa de ello, vuelve a lanzar `fetch` más tarde para completar las etiquetas.

`scripts/revisar_mapping.py` empareja cada producto con un alimento de BEDCA mediante reglas escritas a mano (patrón de nombre por subcategoría) y excluye los procesados. Si aparece un producto nuevo sin regla, lo lista como "sin regla" y queda fuera del cálculo hasta que añadas una. También puedes corregir filas a mano en `data/mapping.csv` (separado por `;`): las marcadas `revisado = sí` no se tocan al volver a proponer.

Las subcategorías de Mercadona que entran están en `config/subcategorias.toml`, y los objetivos EFSA en `data/targets_efsa.json`.

## Límites conocidos

- Los micronutrientes son los del alimento genérico de BEDCA, no los del producto concreto. La etiqueta solo aporta energía, macros, azúcares, fibra y sodio.
- Si a un alimento le falta un dato en BEDCA, cuenta como 0, y la tabla de nutrientes lo marca con ⚠ y el porcentaje de gramos con dato.
- La solución más barata es extrema por naturaleza (mucho de pocos alimentos). El tope de gramos por alimento y los vetos sirven para hacerla comible.

## Desarrollo

```
uv run pytest
uv run python scripts/probar_dietas.py   # dieta real para las tres opciones
```

El diseño está en `docs/2026-11-22-optidieta-design.md` y el plan en `docs/superpowers/plans/`.
