# Optidieta

Calcula la dieta diaria más barata que cumple unos objetivos nutricionales, con productos de Mercadona (tienda de Barcelona) y sus precios. Los nutrientes salen de la etiqueta del producto (leída de la foto de Mercadona) y de BEDCA. La idea es la del [Nutrient Optimizer de Right of the Bell](https://www.rightofthebell.com/nutrient), con datos españoles.

## Uso

```
uv run streamlit run app.py
```

Todo está en una página. En la barra lateral eliges la dieta (omnívora, vegetariana o vegana), tu perfil (sexo, edad, peso) y los requisitos extra: máximo de gramos por alimento, margen de seguridad, límites opcionales como el de azúcares y los productos que no quieres. Se guarda en `data/estado.json`.

Arriba salen el coste, la lista de alimentos y un gráfico de barras con los gramos de cada uno. Si marcas uno o varios alimentos en la lista, el gráfico de nutrientes pinta en azul lo que aportan entre todos y aparece un botón para quitarlos de la dieta.

El gráfico de nutrientes pone cada uno en % de su referencia EFSA. La banda verde es el rango sano para tu perfil y el punto, dónde te deja la dieta. Arrastrar el punto a la derecha fija un mínimo y a la izquierda un máximo, y la dieta se recalcula. Un doble clic en el nombre lo devuelve a EFSA; un clic cambia el gráfico de barras para mostrar qué alimentos aportan ese nutriente. ⚠ marca los nutrientes en los que a algún alimento elegido le falta el dato (cuenta como 0) y ≈ los que llevan una estimación.

Debajo, plegadas, están la tabla de nutrientes, el editor de objetivos y el catálogo, donde puedes vetar productos o poner tu propio precio.

Si la dieta no es posible, la app dice qué nutriente lo impide y deja desactivarlo o devolverlo a EFSA. La vegana no sale con 500 g por alimento porque falta B12 y vitamina D; con 1.000 g sí, casi toda a base de bebida de soja enriquecida.

## Actualizar precios y productos

```
uv run optidieta fetch --refresh   # listados y precios de Mercadona, BEDCA y Open Food Facts
uv run python scripts/revisar_mapping.py
uv run optidieta etiquetas         # lee con Claude la foto de la etiqueta de los productos nuevos
uv run optidieta build
```

`fetch` guarda todo en `data/raw/` y, si se corta, sigue donde lo dejó. Open Food Facts limita las peticiones; si avisa, vuelve a lanzarlo más tarde.

`etiquetas` descarga la foto trasera de cada producto del catálogo y pide a Claude Code (`claude -p`, con Haiku) la tabla nutricional en JSON. Usa la suscripción con la que esté identificado `claude` en la máquina, sin clave de API. La llamada va sin MCP, skills ni ajustes del usuario, que multiplican por unas 90 el contexto. Leer las etiquetas de los 791 productos costó el equivalente a unos 0,83 $, con 4 llamadas en paralelo. Cada resultado queda en `data/raw/etiquetas/` y no se vuelve a pedir, así que si algo falla basta con relanzar el comando.

`scripts/revisar_mapping.py` empareja cada producto con un alimento de BEDCA mediante reglas escritas a mano (patrón de nombre por subcategoría) y excluye los procesados. Un producto nuevo sin regla sale listado como "sin regla" y queda fuera hasta que añadas una. También puedes corregir filas a mano en `data/mapping.csv` (separado por `;`): las marcadas `revisado = sí` no se tocan al volver a proponer.

`build` avisa de las etiquetas de Mercadona que quedan muy lejos de su alimento BEDCA. Casi siempre hay que revisar ese emparejamiento.

Las subcategorías de Mercadona que entran están en `config/subcategorias.toml`, y los objetivos EFSA en `data/targets_efsa.json`.

## De dónde sale cada dato

Por orden de prioridad: la etiqueta de la foto de Mercadona (610 productos), Open Food Facts (2) y BEDCA (el resto). La etiqueta da energía, macros, azúcares, fibra y sal, y en los productos enriquecidos también las vitaminas y minerales que declare. Lo que no dice sale del alimento genérico de BEDCA. Una etiqueta se descarta si sus kcal no cuadran con sus macros (±20 %).

Los huecos de grasa, grasa saturada y azúcares se rellenan con la mediana de la proporción en su subcategoría (o, si hay pocos ejemplos, en su categoría) y quedan apuntados en la columna `estimados`.

El omega-3 de pescado (EPA+DHA, mínimo EFSA de 250 mg/día) sale de BEDCA. Si la ficha elegida no lo trae, se toma de otra ficha con el mismo nombre. Las sardinas y la caballa en lata usan el valor del pescado crudo, que coincide con el de USDA para la conserva; el atún en lata no, porque el claro tiene unas 5 veces menos que el atún crudo de BEDCA. Los productos veganos cuentan con 0 aunque BEDCA diga otra cosa (da EPA+DHA a nueces y aceites, seguramente ALA mal clasificado). En vegetariana y vegana el objetivo viene apagado: sin pescado solo se cumple con un suplemento.

## Límites conocidos

- Las bebidas de almendra, avena y arroz se emparejan con "Bebida de soja", porque BEDCA no tiene otras. Macros y vitaminas añadidas vienen de la etiqueta; el resto de minerales es de la soja.
- El atún en lata, la gamba y el bacalao no tienen dato de EPA+DHA y cuentan como 0 (⚠).
- La solución más barata es extrema por naturaleza (mucho de pocos alimentos). El tope de gramos por alimento, el margen y los vetos sirven para hacerla comible.

## Desarrollo

```
uv run pytest
uv run python scripts/probar_dietas.py   # dieta real para las tres opciones
```

El diseño está en `docs/2026-11-22-optidieta-design.md` y el plan en `docs/superpowers/plans/`.
