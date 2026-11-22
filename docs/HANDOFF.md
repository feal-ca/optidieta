# Handoff: Optidieta

Estado a 2026-11-22. Repo git local en `~/optidieta`, rama `main`, sin remoto. 89 tests en verde (`uv run pytest`).

## Qué es

Herramienta local en Python que calcula la dieta diaria más barata que cumple unos objetivos nutricionales con productos de Mercadona (tienda `bcn1`, Barcelona). Replica la idea del Nutrient Optimizer de Right of the Bell (rightofthebell.com/nutrient), cuyo código no es público: su web llama a un backend privado y sus precios son estimaciones británicas hechas a mano.

El usuario quiere usarla para planificar comida barata, con filtros vegetariano y vegano. Más adelante quiere usar el resultado para diseñar menús o recetas semanales, y quizá añadir Lidl o Carrefour.

Arranque: `uv run streamlit run app.py` (abre en http://localhost:8501).

## Cómo funciona

```
optidieta fetch   → data/raw/            Mercadona (precios), BEDCA (nutrientes), Open Food Facts (etiquetas), con caché
scripts/revisar_mapping.py → data/mapping.csv   producto Mercadona ↔ alimento BEDCA, por reglas
optidieta build   → data/catalog.parquet  une todo: €/100 g comestibles + nutrientes + flags de dieta
app.py            → Streamlit: perfil, dieta, vetos, precios propios, objetivos editables
```

| Módulo | Qué hace |
|---|---|
| `src/optidieta/nutrients.py` | Registro de 31 nutrientes: clave, unidad, `c_id` de BEDCA y campo de OFF |
| `sources/bedca.py` | API XML de BEDCA (`POST bedca.net/bdpub/procquery.php`) y limpieza |
| `sources/mercadona.py` | API no oficial `tienda.mercadona.es/api` con caché y reintentos |
| `sources/off.py` | Etiqueta por EAN en Open Food Facts |
| `pricing.py`, `diet.py` | €/100 g comestibles y flags vegetariano/vegano |
| `mapping.py` | Propuesta difusa y fusión de `mapping.csv` (las filas `revisado=sí` no se pisan) |
| `catalog.py` | Une las fuentes; la etiqueta OFF sustituye a BEDCA en macros si es plausible |
| `targets.py` + `data/targets_efsa.json` | Objetivos EFSA por sexo, edad y peso (energía Henry × PAL 1,6) |
| `optimizer.py` | LP con `scipy.linprog` (HiGHS); si no es factible, un LP elástico dice qué restricción bloquea |
| `state.py`, `ui.py`, `app.py` | Estado del usuario en `data/estado.json` e interfaz |

Diseño completo: `docs/2026-11-22-optidieta-design.md`. Plan ejecutado: `docs/superpowers/plans/2026-11-22-optidieta.md`.

## Datos actuales

- 1.276 productos de 35 subcategorías (`config/subcategorias.toml`). Entran 791 en el catálogo y 452 quedan excluidos como procesados.
- Etiquetas OFF: solo 73 productos las usan. OFF bloqueó la IP con 429/503 a mitad de descarga. `uv run optidieta fetch` reanuda y `build` las incorpora.
- `data/raw/` (36 MB) no está en git. Sí lo están `data/mapping.csv` y `data/targets_efsa.json`.
- Resultado de referencia (perfil por defecto de `probar_dietas.py`, `uv run python scripts/probar_dietas.py`): omnívora 3,12 €/día, vegetariana 4,95 €/día, vegana no factible por B12 y vitamina D.

## Decisiones tomadas

- Los micronutrientes son los del alimento genérico de BEDCA. La etiqueta OFF solo aporta energía, macros, azúcares, fibra y sodio.
- Un nutriente desconocido cuenta como 0 en el LP. La app lo marca con ⚠ y "Con dato" (% de gramos con valor conocido).
- Se descarta la etiqueta OFF si sus kcal no cuadran con sus macros (±20 %) o si están fuera de ×3 respecto a BEDCA. Había fichas de otro producto, como una castaña con 612 kcal.
- El emparejamiento se hace por reglas en `scripts/revisar_mapping.py`, no fila a fila. Los productos nuevos sin regla quedan fuera y el script los lista.
- Los cereales de desayuno solo se emparejan con la entrada enriquecida de BEDCA si los ingredientes de Mercadona mencionan vitaminas. Si no, se usa "Avena, cruda".
- El límite de azúcares (OMS, 10 % E) existe pero viene desactivado. El tope por alimento es 500 g/día.

## Peculiaridades de las fuentes

- **BEDCA:**
  - Repite alimentos con varios ids, uno por fuente. El script de revisión elige el que tiene más nutrientes conocidos.
  - Muchos alimentos no traen energía (se calcula con 4/4/9/2), otros la dan en kJ, y algunos ids devuelven `<food/>` vacío.
  - El cobre viene etiquetado como µg con valores que son mg.
  - Los azúcares están en `c_id` 446, solo en unos 450 alimentos.
- **Mercadona:**
  - El precio de referencia puede ser por kg, L, "100 g", `dz` (docena de huevos) o `dc` (decena).
  - Un producto puede aparecer en dos subcategorías.
  - Los alérgenos incluyen frases tipo "Libre de pescado…", que no deben contar como ingrediente.
- **OFF:** limita pronto la descarga por producto. La API de búsqueda por marca (`/api/v2/search?brands_tags=hacendado`, hasta 1.000 por página) sería más eficiente, pero devolvía 503 y no está implementada.
- **Streamlit:**
  - No recarga módulos importados (`optidieta.*`) al editarlos: hay que reiniciar el servidor.
  - Los `data_editor` conservan ediciones entre reruns. Por eso la tabla de porciones usa `editor_key()` y `save_and_rerun()` llama a `reset_editors()`.
- **Entorno:** `pkill -f "streamlit run app.py"` dentro de un comando que contenga ese texto se mata a sí mismo. Lánzalo en un comando aparte.

## Pendiente

Menores conocidos, sin tocar:
- Al quitar las porciones de menos de 1 g, un nutriente puede quedar justo bajo el mínimo y salir con ✗.
- Si el LP falla numéricamente, el mensaje sale vacío ("Lo impiden: .").
- `estado.json` editado a mano admite precios ≤ 0, y un 0 tecleado en la app se ignora sin avisar.
- La comparación con la solución anterior desaparece en la siguiente interacción.

Siguientes pasos probables:
1. Completar las etiquetas OFF (`fetch` + `build`), o implementar la búsqueda por marca.
2. Menú o recetas semanales a partir de `solve()`. Es una función pura y se puede llamar sin Streamlit; ver `scripts/probar_dietas.py`.
3. Variedad: una restricción de mínimo de alimentos o de máximo por grupo, para que la dieta sea comible.
4. Otros supermercados: una fuente nueva que produzca `MercaProduct` (o un tipo común) y reglas propias.

## Verificación

```
uv run pytest                              # 89 passed
uv run python scripts/probar_dietas.py     # tres dietas con datos reales
uv run python scripts/revisar_mapping.py   # "sin regla: 0"
uv run optidieta build                     # informe de incluidos, etiquetas y descartes
```
