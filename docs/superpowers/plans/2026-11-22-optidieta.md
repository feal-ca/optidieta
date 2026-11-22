# Optidieta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Herramienta local en Python que calcula la dieta diaria más barata con productos básicos de Mercadona (tienda `bcn1`), nutrientes de BEDCA, objetivos EFSA y filtros vegetariano/vegano, con interfaz Streamlit.

**Architecture:** Un paquete `optidieta` con módulos pequeños: fuentes (Mercadona, BEDCA y Open Food Facts, con caché), emparejamiento producto↔BEDCA en un CSV revisable, construcción del catálogo (Parquet), objetivos, optimizador LP puro y estado de usuario. `app.py` (Streamlit) solo orquesta. Un CLI (`optidieta fetch|build|propose`) regenera datos.

**Tech Stack:** Python ≥3.12, uv, numpy, pandas, pyarrow, scipy (`linprog`, método `highs`), requests, rapidfuzz, streamlit, pytest.

**Spec:** `docs/2026-11-22-optidieta-design.md`

## Global Constraints

- Todo local; la app no hace peticiones de red. Solo `optidieta fetch` las hace.
- Mercadona: `https://tienda.mercadona.es/api/...` con `?lang=es&wh=bcn1`; pausa ≥1 s entre peticiones; caché en `data/raw/mercadona/`.
- BEDCA: `POST https://www.bedca.net/bdpub/procquery.php`, `Content-Type: text/xml`; caché en `data/raw/bedca/`.
- Open Food Facts: `User-Agent: optidieta/0.1`, sin datos personales; pausa ≥1 s; caché en `data/raw/off/`.
- Un nutriente desconocido nunca se guarda como 0: valor `NaN` + indicador `k_<clave>=False`. Solo el optimizador lo trata como 0.
- Solo entran al catálogo filas de `mapping.csv` con `revisado == "sí"` y `excluir != "sí"`; la propuesta automática nunca pisa filas revisadas.
- Tope por defecto 500 g/día por producto.
- Valores de objetivos y su fuente viven en `data/targets_efsa.json`, no en el código.
- `optimizer.py` no importa Streamlit.
- Gitignore: `data/raw/`, `data/catalog.parquet`, `data/estado.json`. Se versionan `data/mapping.csv`, `data/targets_efsa.json`, `config/`.

## Review Focus

1. Dieta vegana con B12 y vitamina D activas: casi seguro no factible sin enriquecidos. La app debe decir "no factible por: Vitamina B12…" y permitir desactivarla, no fallar ni mostrar vacío. (Test en Task 8.)
2. Producto revisado en `mapping.csv` que ya no aparece en la última descarga de Mercadona: se omite del catálogo y `build` informa cuántos; no rompe. (Test en Task 6.)
3. Producto vendido por unidad sin `g_por_unidad`: excluido y listado, nunca precio infinito o cero. (Test en Task 4.)
4. Descarga interrumpida (timeout o red caída a mitad): relanzar `fetch` reanuda desde la caché sin repetir lo ya bajado. (Test en Task 3.)
5. Precio local editado a 0 o vetar todos los alimentos de la solución: precio 0 se rechaza en la UI (mínimo 0,01 €/100 g); vetar todo lleva a "no factible" explicado. (Tests en Tasks 8 y 9.)

---

### Task 1: Esqueleto del proyecto y registro de nutrientes

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `optidieta/__init__.py`, `optidieta/nutrients.py`
- Test: `tests/test_nutrients.py`

**Interfaces:**
- Produces: `NUTRIENTS: list[Nutrient]`, `Nutrient(key: str, label: str, unit: str, bedca_ids: tuple[int, ...], bedca_names: tuple[str, ...], off_field: str | None = None, off_factor: float = 1.0)` (dataclass frozen); `BY_KEY: dict[str, Nutrient]`; `col(key) -> "n_<key>"`, `known_col(key) -> "k_<key>"`.

`off_field` / `off_factor` (Open Food Facts, valor × factor = unidad del registro): energia_kcal `energy-kcal_100g` ×1; proteina_g `proteins_100g`; grasa_g `fat_100g`; grasa_sat_g `saturated-fat_100g`; hidratos_g `carbohydrates_100g`; fibra_g `fiber_100g`; sodio_mg `sodium_100g` ×1000 (si falta, `salt_100g` ×400); azucares_g `sugars_100g`. Resto `None`.

Claves y `bedca_ids` (comprobados en BEDCA el 2026-11-22; `bedca_names` es el respaldo por nombre en minúsculas sin acentos):

| key | label | unit | bedca_ids | bedca_names |
|---|---|---|---|---|
| energia_kcal | Energía | kcal | () | ("energia, total",) |
| proteina_g | Proteína | g | (416,) | |
| grasa_g | Grasa total | g | (410,) | |
| grasa_sat_g | Grasa saturada | g | (299,) | |
| hidratos_g | Hidratos de carbono | g | (53,) | |
| fibra_g | Fibra | g | (307,) | |
| azucares_g | Azúcares | g | () | () (solo Open Food Facts) |
| sodio_mg | Sodio | mg | (323,) | |
| potasio_mg | Potasio | mg | (321,) | |
| cloruro_mg | Cloruro | mg | (318,) | |
| calcio_mg | Calcio | mg | (317,) | |
| magnesio_mg | Magnesio | mg | (322,) | |
| fosforo_mg | Fósforo | mg | (326,) | |
| hierro_mg | Hierro | mg | (319,) | |
| zinc_mg | Zinc | mg | (464,) | |
| cobre_mg | Cobre | mg | (453,) | |
| manganeso_mg | Manganeso | mg | (457,) | |
| selenio_ug | Selenio | µg | (462,) | |
| yodo_ug | Yodo | µg | (456,) | |
| vit_a_ug | Vitamina A (ER) | µg | (100,) | |
| vit_d_ug | Vitamina D | µg | (102,) | |
| vit_e_mg | Vitamina E | mg | (103,) | |
| tiamina_mg | Vitamina B1 | mg | (483,) | |
| riboflavina_mg | Vitamina B2 | mg | (482,) | |
| niacina_mg | Niacina (EN) | mg | (475,) | |
| vit_b5_mg | Vitamina B5 | mg | (478,) | |
| vit_b6_mg | Vitamina B6 | mg | (481,) | ("vitamina b-6, total",) |
| vit_b12_ug | Vitamina B12 | µg | (484,) | |
| vit_c_mg | Vitamina C | mg | (486,) | |
| folato_ug | Folato | µg | (487,) | ("folato, total",) |
| colesterol_mg | Colesterol | mg | (433,) | |

- [ ] **Step 1:** `git init` en `~/optidieta`; `uv init --package --name optidieta`; añadir dependencias del Tech Stack (`uv add ...`, `uv add --dev pytest`); entrada de script `optidieta = "optidieta.cli:main"`; `.gitignore` según Global Constraints.
- [ ] **Step 2: Test** `test_registry_unique_and_columns`: claves únicas; `col("hierro_mg") == "n_hierro_mg"`; `known_col("hierro_mg") == "k_hierro_mg"`; `BY_KEY["cobre_mg"].unit == "mg"`; ningún `bedca_id` repetido entre nutrientes.
- [ ] **Step 3:** Ejecutar `uv run pytest tests/test_nutrients.py -v` → FAIL (módulo no existe).
- [ ] **Step 4:** Implementar `optidieta/nutrients.py` con la tabla.
- [ ] **Step 5:** `uv run pytest -v` → PASS.
- [ ] **Step 6:** Commit `feat: esqueleto y registro de nutrientes` (incluye `docs/`).

### Task 2: Fuente BEDCA (descarga, parseo, limpieza)

**Files:**
- Create: `optidieta/sources/__init__.py`, `optidieta/sources/bedca.py`
- Test: `tests/test_bedca.py`, `tests/fixtures/bedca_list.xml`, `tests/fixtures/bedca_food_160.xml`, `tests/fixtures/bedca_food_gaps.xml`

**Interfaces:**
- Consumes: `NUTRIENTS`, `col`, `known_col` (Task 1).
- Produces:
  - `fetch_food_list(cache_dir: Path, session=None) -> list[tuple[int, str]]` (deduplicado por `f_id`; la lista real trae repetidos).
  - `fetch_food(f_id: int, cache_dir: Path, session=None) -> str` (XML; lee de `cache_dir/f_<id>.xml` si existe).
  - `parse_food(xml: str) -> BedcaFood`, `BedcaFood(f_id: int, nombre: str, porcion_comestible: float | None, valores: dict[str, float | None], sin_mapear: list[str])`.
  - `foods_frame(foods: list[BedcaFood]) -> pd.DataFrame` con columnas `bedca_id, bedca_nombre, porcion_comestible`, y por nutriente `n_<key>` (float, NaN si desconocido) y `k_<key>` (bool).

Consultas XML: nivel 1 selecciona `f_id, f_ori_name`; nivel 2 con condición `f_id EQUAL <id>` selecciona `f_id, f_ori_name, edible_portion, c_id, c_ori_name, best_location, v_unit`. Cada componente llega en `<foodvalue>`.

Reglas de limpieza:
- `best_location` vacío, ausente o no numérico → desconocido. Acepta coma decimal.
- Cobre con `v_unit == "ug"` se interpreta como mg (error conocido de BEDCA: garbanzo 0,85 "ug").
- Energía en kJ → kcal dividiendo por 4,184.
- Si falta energía pero proteína, hidratos y grasa son conocidos: `4·P + 4·HC + 9·G + 2·fibra` (fibra desconocida cuenta 0) y se marca conocida.
- Componentes no reconocidos van a `sin_mapear` (para el censo).

- [ ] **Step 1:** Crear fixtures: `bedca_food_160.xml` copia literal de una respuesta real de garbanzo (ver spec: 32 componentes, cobre `0.85 ug`, sin energía); `bedca_food_gaps.xml` con `best_location` vacío para hierro y energía `1500` en `kJ`; `bedca_list.xml` con 3 alimentos, uno duplicado.
- [ ] **Step 2: Tests:**
  - `test_parse_garbanzo`: `valores["proteina_g"] == 20.4`, `valores["cobre_mg"] == 0.85`, `valores["energia_kcal"] == pytest.approx(4*20.4 + 4*55.8 + 9*5.5 + 2*13.6)`, `porcion_comestible == 1.0`.
  - `test_gap_is_unknown_not_zero`: en `foods_frame`, `math.isnan(df.n_hierro_mg[0])` y `df.k_hierro_mg[0] is False`; `df.n_energia_kcal[0] == pytest.approx(1500/4.184)`.
  - `test_list_dedup`: `fetch_food_list` con sesión falsa que devuelve el fixture → 2 elementos.
  - `test_fetch_uses_cache`: con `f_160.xml` en `tmp_path`, `fetch_food(160, tmp_path, session=Boom())` no llama a la sesión.
- [ ] **Step 3:** `uv run pytest tests/test_bedca.py -v` → FAIL.
- [ ] **Step 4:** Implementar con `xml.etree.ElementTree`; nombres de componente normalizados (minúsculas, sin acentos) para el respaldo `bedca_names`.
- [ ] **Step 5:** `uv run pytest -v` → PASS.
- [ ] **Step 6:** Commit `feat: fuente BEDCA con limpieza`.

### Task 3: Fuente Mercadona (descarga con caché y reanudación)

**Files:**
- Create: `optidieta/sources/mercadona.py`, `config/subcategorias.toml`
- Test: `tests/test_mercadona.py`, `tests/fixtures/merca_categories.json`, `tests/fixtures/merca_cat_120.json`, `tests/fixtures/merca_product_13577.json`

**Interfaces:**
- Produces:
  - `MercaProduct(id: str, ean: str | None, nombre: str, categoria: str, subcategoria: str, subcategoria_id: int, precio_envase: float, precio_ref: float | None, formato_ref: str | None, peso_variable: bool, ingredientes: str, alergenos: str, url: str)` (dataclass).
  - `load_included(path: Path) -> set[int]` (lee `include = [ids]` del TOML).
  - `fetch_all(cache_dir: Path, include: set[int], session=None, delay: float = 1.0) -> list[MercaProduct]`: categorías → subcategorías incluidas → detalle de cada producto; cada respuesta se guarda como `cache_dir/<tipo>_<id>.json` y se reutiliza si existe. Cachea también el listado de categorías con la fecha en `cache_dir/fetched_at.txt`; `fetch --refresh` borra la caché de categorías y listados (no de detalles).
  - `parse_product(listing: dict, detail: dict, categoria: str, subcategoria: str, subcategoria_id: int) -> MercaProduct` (HTML quitado de ingredientes y alérgenos).

`config/subcategorias.toml`: el builder rellena `include` con los ids de subcategorías de alimentos básicos según la lista de la spec, comprobándolos contra la API real; comentario con el nombre junto a cada id.

- [ ] **Step 1:** Fixtures recortadas de respuestas reales (spec: producto 13577 "Fideo cabello de ángel Hacendado", `unit_price` 0.85, `reference_price` 1.700, `reference_format` "kg").
- [ ] **Step 2: Tests:**
  - `test_parse_product`: `precio_ref == 1.7`, `formato_ref == "kg"`, `"Sémola de trigo" in ingredientes`, sin `<strong>`.
  - `test_fetch_resumes_from_cache`: sesión falsa que lanza `requests.ConnectionError` en la 2.ª llamada de detalle; primera `fetch_all` falla; segunda con sesión buena hace exactamente las peticiones que faltan (contarlas).
  - `test_only_included_subcategories`: solo se piden detalles de productos en subcategorías de `include`.
- [ ] **Step 3:** `uv run pytest tests/test_mercadona.py -v` → FAIL.
- [ ] **Step 4:** Implementar; `delay=0` en tests.
- [ ] **Step 5:** `uv run pytest -v` → PASS.
- [ ] **Step 6:** Commit `feat: fuente Mercadona con caché`.

### Task 3b: Fuente Open Food Facts (etiqueta por EAN)

**Files:**
- Create: `optidieta/sources/off.py`
- Test: `tests/test_off.py`, `tests/fixtures/off_found.json`, `tests/fixtures/off_empty.json`, `tests/fixtures/off_bad_kcal.json`

**Interfaces:**
- Consumes: `NUTRIENTS` (`off_field`, `off_factor`), `MercaProduct.ean`.
- Produces:
  - `fetch_label(ean: str, cache_dir: Path, session=None, delay: float = 1.0) -> dict | None`: `GET https://world.openfoodfacts.org/api/v2/product/{ean}.json?fields=product_name,nutriments`, cabecera `User-Agent: optidieta/0.1` (sin datos personales); caché `cache_dir/<ean>.json`, también para respuestas `status == 0` (no repetir búsquedas fallidas).
  - `parse_label(resp: dict | None) -> dict[str, float]` → solo claves de nutrientes con valor numérico, convertidas a la unidad del registro. Vacío si no hay producto o `nutriments` está vacío.
  - `label_is_plausible(vals: dict[str, float]) -> bool`: si hay energía, proteína, hidratos y grasa, `|kcal − (4P + 4HC + 9G + 2·fibra)| ≤ 0.20 · max(kcal, 1)`; si falta alguno de esos cuatro, `True`.

- [ ] **Step 1: Fixtures:** `off_found.json` con `energy-kcal_100g 359, proteins_100g 13, carbohydrates_100g 70, fat_100g 2.5, fiber_100g 3, sugars_100g 3.5, salt_100g 0.02` (sin `sodium_100g`); `off_empty.json` con `status 1` y `nutriments {}`; `off_bad_kcal.json` con kcal 100 y los mismos macros.
- [ ] **Step 2: Tests:**
  - `test_parse_label`: `azucares_g == 3.5`, `sodio_mg == pytest.approx(8.0)`, `energia_kcal == 359`.
  - `test_parse_empty`: `{}`.
  - `test_plausibility`: `off_found` → `True`; `off_bad_kcal` → `False`.
  - `test_not_found_is_cached`: respuesta `status 0` se guarda y la segunda llamada no usa la sesión.
- [ ] **Step 3:** `uv run pytest tests/test_off.py -v` → FAIL.
- [ ] **Step 4:** Implementar.
- [ ] **Step 5:** `uv run pytest -v` → PASS.
- [ ] **Step 6:** Commit `feat: fuente Open Food Facts`.

### Task 4: Precio por 100 g y etiquetas de dieta

**Files:**
- Create: `optidieta/pricing.py`, `optidieta/diet.py`
- Test: `tests/test_pricing.py`, `tests/test_diet.py`

**Interfaces:**
- Consumes: `MercaProduct` (Task 3).
- Produces:
  - `price_per_100g(p: MercaProduct, porcion_comestible: float, g_por_unidad: float | None, densidad: float | None) -> float | None` en € por 100 g comestibles; `None` si no se puede calcular.
  - `diet_flags(p: MercaProduct) -> tuple[bool, bool]` → `(vegetariano, vegano)`.

Reglas de precio: `formato_ref == "kg"` → `precio_ref/10`; `"L"` (sin distinguir mayúsculas) → `precio_ref/10/densidad`, densidad por defecto 1,0 y 0,92 si el nombre contiene "aceite"; otro formato → `precio_envase / (g_por_unidad/100)` si hay `g_por_unidad`, si no `None`. Después dividir por `porcion_comestible` (si es 0 o None, usar 1,0).

Reglas de dieta (sobre texto en minúsculas sin acentos de nombre + ingredientes + alérgenos): no vegetariano si `categoria` es "Carne" o "Marisco y pescado", o el texto contiene alguna de `carne, cerdo, pollo, pavo, ternera, vacuno, cordero, jamon, pescado, atun, salmon, bacalao, sardina, anchoa, marisco, gamba, mejillon, calamar, pulpo, gelatina, cuajo animal`. No vegano además si contiene `leche, lacteo, nata, mantequilla, queso, yogur, huevo, miel, suero, caseina, lactosa` o la categoría es "Huevos, leche y mantequilla" (salvo bebidas vegetales: nombre contiene "bebida de" o "vegetal").

- [ ] **Step 1: Tests:**
  - `test_price_kg`: `precio_ref=1.7, formato_ref="kg", porcion=1.0` → `0.17`.
  - `test_price_edible_portion`: `precio_ref=2.0, "kg", porcion=0.8` → `0.25`.
  - `test_price_oil_litre`: nombre "Aceite de oliva", `precio_ref=9.2, "L"` → `pytest.approx(1.0)`.
  - `test_price_unit_without_weight_is_none`: `formato_ref="ud"`, `g_por_unidad=None` → `None`.
  - `test_price_unit_with_weight`: docena de huevos `precio_envase=2.4`, `g_por_unidad=720` → `pytest.approx(0.3333, abs=1e-3)`.
  - `test_diet_flags`: lentejas → `(True, True)`; yogur natural → `(True, False)`; atún en conserva → `(False, False)`; "Bebida de soja" en categoría "Huevos, leche y mantequilla" → `(True, True)`; pasta con "Puede contener trazas de huevo" → `(True, True)` (las trazas no cuentan: quitar la frase "puede contener trazas de ..." antes de buscar).
- [ ] **Step 2:** `uv run pytest tests/test_pricing.py tests/test_diet.py -v` → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** `uv run pytest -v` → PASS.
- [ ] **Step 5:** Commit `feat: precio por 100 g y etiquetas de dieta`.

### Task 5: Emparejamiento producto ↔ BEDCA (`mapping.csv`)

**Files:**
- Create: `optidieta/mapping.py`
- Test: `tests/test_mapping.py`

**Interfaces:**
- Consumes: `MercaProduct`, `foods_frame` (Tasks 2, 3).
- Produces:
  - `COLUMNS = ["mercadona_id", "nombre", "bedca_id", "bedca_nombre", "confianza", "revisado", "excluir", "porcion_comestible", "g_por_unidad", "vegetariano", "vegano"]`.
  - `propose(products: list[MercaProduct], bedca: pd.DataFrame) -> pd.DataFrame` (columnas `COLUMNS`; `revisado="no"`, `excluir="no"`, `porcion_comestible` = la de BEDCA o 1,0, `vegetariano`/`vegano` vacíos = usar `diet_flags`).
  - `merge(existing: pd.DataFrame, proposed: pd.DataFrame) -> pd.DataFrame`: filas con `revisado=="sí"` intactas; filas no revisadas se reemplazan por la propuesta; filas nuevas se añaden; orden estable por `mercadona_id`.
  - `read_mapping(path) -> pd.DataFrame`, `write_mapping(df, path)` (UTF-8, `;` como separador para Excel en español).

Similitud: `rapidfuzz.process.extractOne` con `fuzz.token_set_ratio` sobre nombres normalizados (minúsculas, sin acentos, sin marca `Hacendado|Deliplus|...` presente en `MercaProduct`, sin pesos tipo `500 g`, `1 kg`, `pack 6`); a igualdad, preferir entradas BEDCA con "crud" o "sec" en el nombre. `confianza` = puntuación 0–100.

- [ ] **Step 1: Tests:**
  - `test_propose_prefers_raw`: producto "Lentejas pardinas Hacendado 1 kg" con candidatos "Lenteja, seca, cruda" y "Lenteja, hervida" → `bedca_nombre == "Lenteja, seca, cruda"`.
  - `test_merge_keeps_reviewed`: fila existente revisada con `bedca_id=999` y propuesta con `bedca_id=189` → sigue 999.
  - `test_merge_replaces_unreviewed_and_adds_new`.
  - `test_roundtrip_csv`: `write_mapping` → `read_mapping` preserva tipos y acentos.
- [ ] **Step 2:** `uv run pytest tests/test_mapping.py -v` → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** `uv run pytest -v` → PASS.
- [ ] **Step 5:** Commit `feat: propuesta y fusión del emparejamiento`.

### Task 6: Catálogo y CLI

**Files:**
- Create: `optidieta/catalog.py`, `optidieta/cli.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces:
  - `build_catalog(products: list[MercaProduct], bedca: pd.DataFrame, mapping: pd.DataFrame, labels: Mapping[str, dict[str, float]]) -> tuple[pd.DataFrame, BuildReport]`. `labels` va de `mercadona_id` a la salida de `parse_label`. Catálogo con `id, nombre, categoria, url, precio_100g, vegetariano, vegano, fuente_etiqueta` + `n_<key>`/`k_<key>`. Precedencia: si la etiqueta existe y `label_is_plausible`, sus valores sustituyen a los de BEDCA en esas claves (`fuente_etiqueta = "off"`); si no, todo BEDCA (`"bedca"`). `BuildReport(incluidos: int, sin_revisar: int, desaparecidos: list[str], sin_precio: list[str], con_etiqueta: int, etiqueta_descartada: list[str])`.
  - `load_catalog(path: Path) -> pd.DataFrame` (Parquet).
  - CLI `optidieta fetch [--refresh]` (Mercadona; BEDCA lista completa + detalle de todos, cacheado; Open Food Facts por EAN de cada producto incluido), `optidieta propose` (escribe/fusiona `data/mapping.csv`), `optidieta build` (escribe `data/catalog.parquet` e imprime el `BuildReport`), `optidieta census` (imprime componentes BEDCA `sin_mapear` agregados con su recuento).
- Flags de dieta: valor de `mapping.csv` si no está vacío; si no, `diet_flags`.

- [ ] **Step 1: Tests:**
  - `test_build_skips_unreviewed_and_excluded`.
  - `test_build_reports_vanished_product`: fila revisada cuyo `mercadona_id` no está en `products` → en `desaparecidos`, no en el catálogo.
  - `test_build_reports_no_price`: producto por unidad sin `g_por_unidad` → en `sin_precio`.
  - `test_mapping_overrides_diet_flags`.
  - `test_label_overrides_bedca_macros`: BEDCA proteína 12, etiqueta 13 → `n_proteina_g == 13`, `fuente_etiqueta == "off"`, hierro sigue de BEDCA.
  - `test_implausible_label_ignored`: etiqueta con kcal incoherentes → valores BEDCA, producto en `etiqueta_descartada`.
  - `test_sugar_unknown_without_label`: sin etiqueta → `k_azucares_g` falso.
- [ ] **Step 2:** `uv run pytest tests/test_catalog.py -v` → FAIL.
- [ ] **Step 3:** Implementar (`argparse`).
- [ ] **Step 4:** `uv run pytest -v` → PASS.
- [ ] **Step 5:** Commit `feat: catálogo y CLI`.

### Task 7: Objetivos nutricionales EFSA

**Files:**
- Create: `optidieta/targets.py`, `data/targets_efsa.json`
- Test: `tests/test_targets.py`

**Interfaces:**
- Consumes: `BY_KEY` (Task 1).
- Produces:
  - `Profile(sexo: Literal["h", "m"], edad: int, peso_kg: float = 70.0)`.
  - `Constraint(key: str, label: str, unit: str, min: float | None, max: float | None, active: bool = True, kind: Literal["abs", "pct_energia"] = "abs", kcal_por_g: float | None = None, fuente: str = "")`. Para `pct_energia`, `min`/`max` son fracciones (0,20) y la fila LP es `kcal_por_g·x_nutriente − frac·x_energia`.
  - `energy_kcal(p: Profile) -> float`: TMB de Henry (MJ/día) × 1,6 × 239,006.
  - `default_constraints(p: Profile, path: Path = DEFAULT_PATH) -> list[Constraint]`.

TMB Henry (W = peso en kg, resultado en MJ/día): hombre 18–29 `0.0669W + 2.28`, 30–59 `0.0592W + 2.48`, ≥60 `0.0563W + 2.15`; mujer 18–29 `0.0546W + 2.33`, 30–59 `0.0407W + 2.90`, ≥60 `0.0424W + 2.38`. Energía: banda `[0.95·E, 1.05·E]`.

`data/targets_efsa.json` (valores por adulto; `h`/`m` cuando difieren; `fuente` en cada entrada):

| key | mínimo | máximo |
|---|---|---|
| proteina_g | 0,83 g/kg × peso (PRI) | — |
| grasa_g | 20 % E (pct, 9 kcal/g) | 35 % E |
| hidratos_g | 45 % E (pct, 4 kcal/g) | 60 % E |
| grasa_sat_g | — | 10 % E (pct, 9 kcal/g; fuente OMS) |
| fibra_g | 25 (AI) | — |
| azucares_g | — | 10 % E (pct, 4 kcal/g; OMS), `active: false` por defecto |
| sodio_mg | — | 2000 |
| cloruro_mg | — | 3100 |
| potasio_mg | 3500 (AI) | — |
| calcio_mg | 1000 si edad < 25, si no 950 (PRI) | 2500 (UL) |
| magnesio_mg | h 350 / m 300 (AI) | — |
| fosforo_mg | 550 (AI) | — |
| hierro_mg | h 11 / m 16 si edad < 50, 11 si ≥ 50 (PRI) | 40 |
| zinc_mg | h 11,7 / m 9,3 (PRI, fitato 600 mg) | 25 (UL) |
| cobre_mg | h 1,6 / m 1,3 (AI) | 5 (UL) |
| manganeso_mg | 3 (AI) | — |
| selenio_ug | 70 (AI) | 255 (UL) |
| yodo_ug | 150 (AI) | 600 (UL) |
| vit_a_ug | h 750 / m 650 (PRI) | — (la UL es solo para retinol; BEDCA da ER con carotenoides) |
| vit_d_ug | 15 (AI) | 100 (UL) |
| vit_e_mg | h 13 / m 11 (AI) | 300 (UL) |
| tiamina_mg | h 1,1 / m 0,9 | — |
| riboflavina_mg | 1,6 (PRI) | — |
| niacina_mg | h 17 / m 14 | — |
| vit_b5_mg | 5 (AI) | — |
| vit_b6_mg | h 1,7 / m 1,6 (PRI) | — |
| vit_b12_ug | 4 (AI) | — |
| vit_c_mg | h 110 / m 95 (PRI) | — |
| folato_ug | 330 (PRI) | — |

Colesterol no lleva restricción (sin valor EFSA), pero se muestra en totales.

- [ ] **Step 1: Tests:**
  - `test_energy_henry`: `Profile("h", 25, 70)` → `pytest.approx((0.0669*70 + 2.28) * 1.6 * 239.006)`.
  - `test_iron_by_sex_and_age`: m 30 → min 16; m 55 → 11; h 30 → 11, max 40.
  - `test_protein_scales_with_weight`: peso 80 → min `pytest.approx(66.4)`.
  - `test_pct_constraints`: grasa `kind=="pct_energia"`, `min==0.20`, `max==0.35`, `kcal_por_g==9`.
  - `test_every_key_known`: toda clave del JSON está en `BY_KEY`.
  - `test_sugar_inactive_by_default`: `azucares_g` existe, `active is False`, `max == 0.10`.
- [ ] **Step 2:** `uv run pytest tests/test_targets.py -v` → FAIL.
- [ ] **Step 3:** Implementar y escribir el JSON con la tabla.
- [ ] **Step 4:** `uv run pytest -v` → PASS.
- [ ] **Step 5:** Commit `feat: objetivos EFSA`.

### Task 8: Optimizador

**Files:**
- Create: `optidieta/optimizer.py`
- Test: `tests/test_optimizer.py`

**Interfaces:**
- Consumes: `Constraint` (Task 7), columnas del catálogo (Task 6).
- Produces:
  - `solve(foods: pd.DataFrame, constraints: list[Constraint], *, excluded: frozenset[str] = frozenset(), price_overrides: Mapping[str, float] = {}, max_g: float = 500.0, diet: Literal["omnivora", "vegetariana", "vegana"] = "omnivora") -> Solution`.
  - `Solution(feasible: bool, cost_day: float, portions: list[Portion], totals: dict[str, NutrientTotal], blocking: list[str], unverified_max: list[str])`.
  - `Portion(id: str, nombre: str, grams: float, cost: float)`; `NutrientTotal(value: float, known_fraction: float)`.
  - `compare(prev: Solution, new: Solution) -> SolutionDiff(cost_delta: float, added: list[str], removed: list[str])`.

Formulación: variables `x_j` = gramos/día (cotas `[0, max_g]`), coste `precio_100g/100`; nutriente por gramo `n_<key>/100` con NaN → 0. Restricciones inactivas o con nutriente ausente del catálogo se ignoran. `pct_energia` según Task 7. Porciones < 1 g se descartan del resultado. `known_fraction` = aporte de alimentos con `k_<key>` verdadero / total (1,0 si total es 0). `unverified_max`: claves con máximo activo donde algún alimento elegido tiene `k_<key>` falso.

Diagnóstico si no es factible: segundo LP elástico con holgura `s_i ≥ 0` por restricción activa, escalada por `max(|límite|, 1)`, coste 1e3 por unidad escalada además del coste real; `blocking` = claves con holgura > 1e-6, ordenadas por holgura descendente.

- [ ] **Step 1: Tests** (catálogos sintéticos de 2–4 alimentos):
  - `test_cheapest_mix`: A (0,10 €/100 g, 10 g prot/100 g) y B (0,50 €, 20 g); mínimo prot 30 → solo A, 300 g, coste 0,30.
  - `test_respects_max_g`: mismo caso con `max_g=200` → A 200 g + B 50 g.
  - `test_exclusion`: excluir A → B 150 g.
  - `test_diet_filter`: `diet="vegana"` ignora filas con `vegano=False`.
  - `test_unknown_counts_zero_and_reports`: alimento con hierro desconocido elegido → `totals["hierro_mg"].known_fraction < 1`.
  - `test_infeasible_names_blocking`: catálogo vegano sin B12 y mínimo B12 4 → `feasible is False`, `blocking[0] == "vit_b12_ug"`.
  - `test_all_excluded_infeasible`: excluir todo → `feasible is False`, sin excepción.
  - `test_pct_energy`: grasa ≥ 20 % E se cumple en la solución (`9·grasa ≥ 0.2·kcal - 1e-6`).
  - `test_compare`: `added`/`removed`/`cost_delta` correctos.
- [ ] **Step 2:** `uv run pytest tests/test_optimizer.py -v` → FAIL.
- [ ] **Step 3:** Implementar con `scipy.optimize.linprog(method="highs")`.
- [ ] **Step 4:** `uv run pytest -v` → PASS.
- [ ] **Step 5:** Commit `feat: optimizador LP con diagnóstico`.

### Task 9: Estado de usuario y app Streamlit

**Files:**
- Create: `optidieta/state.py`, `app.py`
- Test: `tests/test_state.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: Tasks 6–8.
- Produces:
  - `UserState(profile: Profile, diet: str, excluded: set[str], price_overrides: dict[str, float], constraint_edits: dict[str, dict], max_g: float)`; `load_state(path) -> UserState` (por defecto si no existe o está corrupto: `Profile("h", 30, 70)`, omnívora); `save_state(state, path)` (JSON atómico: escribir a `.tmp` y renombrar).
  - `apply_edits(base: list[Constraint], edits: dict[str, dict]) -> list[Constraint]` (edits por clave: `min`, `max`, `active`).

App (`uv run streamlit run app.py`), en español:
- Barra lateral: dieta (omnívora/vegetariana/vegana), sexo, edad (18–99), peso (30–200 kg), tope g/día, botón "Restablecer".
- Pestaña "Dieta": coste/día y coste/semana con delta frente a la solución anterior (`st.metric`), frase de cambios de `compare`; tabla de porciones (nombre con enlace a Mercadona, g/día, €/día) con columna de casilla "Vetar" (`st.data_editor`); tabla de nutrientes total/objetivo/% con aviso ⚠ si `known_fraction < 1` o la clave está en `unverified_max`. Si no es factible: mensaje con las etiquetas de `blocking` y un botón por cada una para desactivarla.
- Pestaña "Objetivos": `st.data_editor` con mínimo, máximo y activo por restricción.
- Pestaña "Catálogo": búsqueda por texto, filtro por categoría, casilla de vetar y precio local editable (mínimo 0,01 €/100 g; borrar el valor vuelve al de Mercadona); aviso con `sin_revisar` y la fecha de `fetched_at.txt`.
- Si `data/catalog.parquet` no existe: mensaje con los comandos `optidieta fetch`, `optidieta propose`, `optidieta build`.
- Cada cambio guarda `data/estado.json`.
- En la tabla de porciones y en el catálogo, columna "Fuente" (`etiqueta` / `BEDCA`).

- [ ] **Step 1: Tests:**
  - `test_state_roundtrip` (sets y floats preservados).
  - `test_state_corrupt_returns_default`.
  - `test_apply_edits`: desactivar `vit_b12_ug` y cambiar `hierro_mg.min` a 14.
  - `test_app_smoke`: `streamlit.testing.v1.AppTest.from_file("app.py")` con catálogo sintético de `tests/fixtures/catalog_small.parquet` (ruta por variable de entorno `OPTIDIETA_DATA`); `at.run()` sin excepciones y existe una `metric` con "€".
  - `test_app_infeasible_shows_blocking`: catálogo sin B12, dieta vegana → texto contiene "Vitamina B12".
- [ ] **Step 2:** `uv run pytest tests/test_state.py tests/test_app.py -v` → FAIL.
- [ ] **Step 3:** Implementar `state.py` y `app.py` (rutas de datos desde `OPTIDIETA_DATA`, por defecto `./data`).
- [ ] **Step 4:** `uv run pytest -v` → PASS.
- [ ] **Step 5:** Commit `feat: app Streamlit y estado persistente`.

### Task 10: Datos reales y emparejamiento revisado

**Files:**
- Modify: `config/subcategorias.toml`, `data/mapping.csv`, `optidieta/nutrients.py` (solo si el censo encuentra ids nuevos)
- Create: `docs/datos.md` (cómo actualizar precios y revisar filas nuevas)

- [ ] **Step 1:** `uv run optidieta fetch` completo. Esperado: termina; relanzarlo no hace peticiones nuevas.
- [ ] **Step 2:** `uv run optidieta census`. Si aparecen componentes que corresponden a un nutriente del registro con otro `c_id`, añadirlo a `bedca_ids` y volver a pasar los tests.
- [ ] **Step 3:** `uv run optidieta propose`; revisar a mano todas las filas: corregir `bedca_id`, `porcion_comestible`, `g_por_unidad`, `excluir` para procesados, y marcar `revisado=sí`.
- [ ] **Step 4:** `uv run optidieta build`. Esperado: `sin_revisar == 0`; `sin_precio` vacío o justificado; informe de `con_etiqueta` y `etiqueta_descartada` (revisar a mano los descartados).
- [ ] **Step 5:** Prueba real: script corto que llama a `solve` para `Profile("h", 30, 70)` en las tres dietas e imprime coste y porciones. Esperado: omnívora y vegetariana factibles con coste entre 1 y 10 €/día; vegana factible o no factible con `blocking` en B12/vitamina D.
- [ ] **Step 6:** `uv run streamlit run app.py` y captura de pantalla de la pestaña Dieta como evidencia.
- [ ] **Step 7:** Escribir `docs/datos.md`; commit `data: emparejamiento revisado y catálogo inicial`.
