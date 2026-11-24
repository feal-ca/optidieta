# Handoff: Optidieta

Estado a 2026-11-24. Repo en `~/optidieta`, rama `main`, con remoto privado en GitHub (`feal-ca/optidieta`). 132 tests en verde (`uv run pytest`); ruff y mypy limpios.

El trabajo del 2026-11-23 está en commits separados por tema. El 2026-11-24 se hizo una auditoría: escritura atómica en las cachés (`fsutil.write_atomic`), `load_state` acota los valores a los rangos de los widgets, la tabla del catálogo cambia de clave al filtrar, y ruff y mypy en el grupo dev.

## Qué es

Herramienta local en Python que calcula la dieta diaria más barata que cumple unos objetivos nutricionales con productos de Mercadona (tienda `bcn1`, Barcelona). Replica la idea del Nutrient Optimizer de Right of the Bell (rightofthebell.com/nutrient), cuyo código no es público.

El usuario la quiere para planificar comida barata, con filtros vegetariano y vegano. Más adelante quiere sacar menús o recetas semanales del resultado, y quizá añadir Lidl o Carrefour. `data/estado.json` guarda su perfil; ese archivo es suyo y no se toca en las pruebas (hacer copia y comparar).

Arranque: `uv run streamlit run app.py` (http://localhost:8501). Streamlit no recarga los módulos `optidieta.*`: tras cambiar código hay que reiniciar el servidor.

## Cómo funciona

```
optidieta fetch     → data/raw/             Mercadona (precios), BEDCA (nutrientes), Open Food Facts, con caché
scripts/revisar_mapping.py → data/mapping.csv   producto Mercadona ↔ alimento BEDCA, por reglas
optidieta etiquetas → data/raw/etiquetas/   foto trasera de Mercadona leída con `claude -p` (suscripción, Haiku)
optidieta build     → data/catalog.parquet  une todo: €/100 g comestibles, nutrientes, flags de dieta, estimaciones
app.py              → Streamlit, una página: barra lateral (dieta, perfil, requisitos extra) y resultados
```

| Módulo | Qué hace |
|---|---|
| `nutrients.py` | Registro de 32 nutrientes: clave, unidad, `c_id` de BEDCA (con factor y suma opcionales) y campo de OFF |
| `sources/bedca.py` | API XML de BEDCA y limpieza |
| `sources/mercadona.py` | API no oficial `tienda.mercadona.es/api` con caché y reintentos |
| `sources/off.py` | Etiqueta por EAN en Open Food Facts |
| `sources/etiqueta.py` | Foto trasera (perspectiva 9) → `claude -p` con `--json-schema`; caché por producto |
| `pricing.py`, `diet.py` | €/100 g comestibles y flags vegetariano/vegano |
| `mapping.py` | Propuesta difusa y fusión de `mapping.csv` (las filas `revisado=sí` no se pisan) |
| `catalog.py` | Une las fuentes. Prioridad: etiqueta de Mercadona > OFF > BEDCA. Completa huecos con otros ids BEDCA del mismo nombre |
| `estimate.py` | Rellena grasa, saturada y azúcares por mediana de subcategoría o categoría; EPA+DHA = 0 en veganos; columna `estimados` |
| `targets.py` + `data/targets_efsa.json` | Objetivos EFSA por sexo, edad y peso; `apply_margin` (margen de seguridad) y `for_diet` (apaga lo que exige pescado) |
| `optimizer.py` | LP con `scipy.linprog` (HiGHS). Si no es factible, un LP elástico dice qué lo bloquea. Productos del mismo alimento BEDCA (o mismo nombre) cuentan como uno: se queda el formato más barato |
| `rangos.py`, `web/rangos.{js,css}` | Gráfico de nutrientes: datos puros (filas, aporte de alimentos, arrastre → objetivo) y componente `st.components.v2` |
| `state.py`, `ui.py`, `app.py` | Estado del usuario en `data/estado.json` e interfaz |

Diseño original: `docs/2026-11-22-optidieta-design.md`. Plan ejecutado: `docs/superpowers/plans/2026-11-22-optidieta.md`.

## La app

Todo está en una página, como pidió el usuario.

- Barra lateral: dieta; perfil; requisitos extra (máximo por alimento, margen de seguridad 0–30 %, interruptores para los objetivos apagados por defecto como azúcares u omega-3, y "Productos que no quiero").
- Arriba: coste, lista de alimentos (selección múltiple; botón para quitar los elegidos) y gráfico de barras. El desplegable "Barras" alterna entre gramos y "Quién aporta: X".
- Gráfico de nutrientes: cada uno en % de su referencia EFSA, banda verde con el rango sano, punto con el valor de la dieta. Arrastrar fija un mínimo (derecha) o un máximo (izquierda); doble clic en el nombre vuelve a EFSA; clic en el nombre cambia las barras a qué alimentos lo aportan. Con alimentos seleccionados, una barra azul muestra lo que aportan entre todos. ⚠ = falta el dato en algún alimento elegido; ≈ = hay estimación.
- Plegadas al final: tabla de nutrientes, editor de objetivos, catálogo con vetos y precios propios.
- En vegetariana y vegana, bajo el coste se avisa de que el precio no incluye el omega-3 y de cuánto costaría la omnívora con los mismos objetivos. El usuario vio la vegetariana más barata que la omnívora y lo señaló como un sinsentido; el aviso lo explica.

## Datos actuales

- 1.276 productos de 35 subcategorías. Entran 791 en el catálogo; 452 quedan fuera como procesados.
- Etiquetas: 610 productos usan la de la foto de Mercadona y 2 la de OFF; el resto, BEDCA. Se leyeron 727 fotos (64 productos no tienen foto trasera, casi todo fruta y verdura a granel). Coste equivalente de la suscripción: unos 0,83 $.
- OFF quedó a medias (485 de 1.239) por límites y un corte de red. Con las fotos ya casi no hace falta.
- `data/raw/` no está en git. Sí lo están `data/mapping.csv` y `data/targets_efsa.json`.
- Referencia (perfil por defecto de `probar_dietas.py`, 500 g por alimento, `uv run python scripts/probar_dietas.py`): omnívora 1,84 €/día (el omega-3 lo cubren 18 g de mejillón); vegetariana 1,83 €/día sin el objetivo de omega-3 (la omnívora en esas condiciones: 1,73); vegana no factible por B12 y vitamina D, factible con 1.000 g por alimento a 5,33 €/día. Antes de las etiquetas eran 3,13 y 6,03: la vitamina D de leches enriquecidas y margarinas no estaba en BEDCA.

## Decisiones tomadas

- La etiqueta de Mercadona manda en lo que declara, también en vitaminas y minerales de los enriquecidos. Lo que no declara sale de BEDCA. De OFF solo se usan macros.
- Una etiqueta se descarta si sus kcal no cuadran con sus macros (±20 %). La de OFF también si está fuera de ×3 respecto a BEDCA. La de Mercadona no: si no cuadra con BEDCA, lo sospechoso es el emparejamiento y `build` lo lista.
- Las etiquetas se leen con `claude -p` usando la suscripción del usuario, como pidió (nada de clave de API). La llamada va sin MCP, skills ni ajustes (`--strict-mcp-config --disable-slash-commands --setting-sources ""` y un `--system-prompt` corto); con el contexto normal costaba unas 90 veces más. No se usa `--bare` porque se salta el llavero y podría romper el login.
- Tesseract y OpenCV se descartaron: Tesseract lee "1,9 g" como "199" y pierde las filas blanco sobre negro, incluso con preprocesado.
- Un nutriente desconocido cuenta como 0 en el LP. Las estimaciones (≈) cuentan como dato.
- Huecos de BEDCA: primero, mediana de otros ids con el mismo nombre (mismo alimento, no estimación). Sardina y caballa en lata toman el EPA+DHA del crudo (`epa_equiv` en `catalog.py`, comprobado con USDA); el atún en lata no, porque el claro tiene unas 5 veces menos que el "Atún, crudo" de BEDCA.
- Omega-3 EPA+DHA (EFSA AI 250 mg/día) es un nutriente (`epa_dha_mg`, `c_id` 231 + 260, g → mg). Activo por defecto solo en omnívora. Se prefirió a "raciones de pescado" porque el modelo trabaja con nutrientes y la evidencia de pescado y de fruta y verdura es observacional (Aune 2017; ensayos de aceite de pescado como VITAL o STRENGTH sin beneficio en población general). El usuario eligió solo esta opción; el mínimo de fruta y verdura por grupo (OMS 400 g, AESAN ~700 g) quedó descartado.
- El margen de seguridad sube mínimos y baja máximos, salvo la energía y lo que el usuario haya movido. La banda verde sigue siendo EFSA; la raya negra es el objetivo real.
- En un LP de coste mínimo los nutrientes que cuestan dinero quedan justo en su límite. Para separarlos del borde está el margen de seguridad.
- El límite de azúcares (OMS, 10 % E) existe pero viene apagado.

## Peculiaridades de las fuentes

- **BEDCA:**
  - Repite alimentos con varios ids; no todos traen los mismos nutrientes (los ácidos grasos faltan a menudo).
  - "Judías blancas, cocidas" (id 2006) tiene valores de judía seca. Las alubias cocidas van a "Alubia blanca, en conserva".
  - Da EPA+DHA a nueces, cacahuete y aceite de girasol (seguramente ALA mal clasificado). En veganos se fuerza 0.
  - Muchos alimentos no traen energía (se calcula con 4/4/9/2), otros la dan en kJ, y algunos ids devuelven `<food/>` vacío. El cobre viene como µg con valores que son mg.
- **Mercadona:**
  - El precio de referencia puede ser por kg, L, "100 g", `dz` o `dc`. Un producto puede aparecer en dos subcategorías y en varios formatos con el mismo nombre.
  - La foto con `perspective` 9 es la etiqueta trasera (1.237 de 1.239 productos). Es el diseño impreso y se lee muy bien.
- **OFF:** limita pronto. Tiene errores claros (aceite de oliva con 6 g de hidratos, un queso con los valores de un aceite).
- **Streamlit:**
  - El gráfico es un `st.components.v2.component` con JS y CSS en línea (sin iframe ni npm). Eventos con `setTriggerValue`: `move`, `reset`, `pick`.
  - Un widget con `key` no se puede cambiar después de crearlo en la misma pasada: el clic en un nutriente se guarda en `_pick` y se aplica al selectbox en la siguiente.
  - Las tablas editables conservan ediciones entre reruns: se usan `editor_key()` y `reset_editors()`.
- **Entorno:** `pkill -f "streamlit run app.py"` dentro de un comando que contenga ese texto se mata a sí mismo (sale con código 144); lánzalo en un comando aparte. `optidieta fetch` aparece como proceso `optidieta`, no `python`.

## Pendiente

- `build` lista 6 emparejamientos a revisar (alcachofas, dos bebidas de almendra, queso fresco 0 %, 26775, 61288) y descarta 10 etiquetas cuyas kcal no cuadran.
- Las bebidas de almendra, avena y arroz usan los minerales de la bebida de soja de BEDCA.
- Atún en lata, gamba y bacalao sin dato de EPA+DHA (cuentan como 0). Huevos tampoco.
- Menores: un nutriente puede quedar justo bajo el mínimo al quitar porciones de menos de 1 g; un precio 0 tecleado se ignora sin avisar; la comparación con la solución anterior desaparece en la siguiente interacción.

Siguientes pasos probables:
1. Menú o recetas semanales a partir de `solve()` (función pura; ver `scripts/probar_dietas.py`).
2. "Alimentos que quiero": el contrario de los vetos, con gramos mínimos. Se propuso y el usuario no lo ha pedido aún.
3. Variedad: mínimo de alimentos o máximo por grupo.
4. Otros supermercados: una fuente que produzca `MercaProduct` (o un tipo común) y reglas propias.

## Verificación

```
uv run pytest                              # 132 passed
uv run ruff check . && uv run mypy         # sin errores
uv run python scripts/probar_dietas.py     # omnívora 1,84 · vegetariana 1,83 · vegana no factible
uv run python scripts/revisar_mapping.py   # "sin regla: 0"
uv run optidieta etiquetas                 # solo lee las que falten
uv run optidieta build                     # informe de incluidos, etiquetas, descartes y emparejamientos a revisar
```

Para la interfaz, arrancar en otro puerto (`--server.port 8599`), copiar antes `data/estado.json` y comprobar después que no ha cambiado.
