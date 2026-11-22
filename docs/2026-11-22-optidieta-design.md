# Optidieta: diseño

Fecha: 2026-11-22

## Qué es y por qué

Una herramienta local en Python que calcula la dieta diaria más barata que cumple unos objetivos nutricionales, usando productos reales de Mercadona (tienda de Barcelona) con sus precios actuales. Replica la idea del Nutrient Optimizer de Right of the Bell (rightofthebell.com/nutrient), que usa la tabla británica CoFID con precios estimados a mano, pero con datos españoles, mejor interfaz y filtros de dieta.

Es para uso personal. Más adelante el resultado (lista de alimentos y gramos por día) servirá de entrada para diseñar menús o recetas semanales, así que el optimizador tiene que poder usarse desde Python sin la interfaz.

## Objetivos

- Resolver el problema clásico de la dieta de coste mínimo (programación lineal) sobre el catálogo de alimentos básicos de Mercadona.
- Nutrientes por producto estimados desde BEDCA, emparejando cada producto con un alimento BEDCA.
- Filtro omnívoro / vegetariano / vegano.
- Interfaz Streamlit local más cómoda que la original: vetar alimentos, editar precios, ajustar objetivos, ver cómo cambia el coste.
- Optimizador como módulo Python reutilizable.

## No objetivos (por ahora)

- Lidl, Carrefour u otros supermercados. El diseño debe permitir añadir otra fuente de productos después, pero no se implementa.
- Recetas o menús semanales.
- Productos procesados o compuestos (pizzas, platos preparados, salsas, galletas, embutidos con muchos ingredientes). Estimar sus nutrientes por la lista de ingredientes no es fiable.
- Despliegue web, cuentas de usuario, móvil.

## Anti-objetivos

- Que dé una dieta "barata" basada en nutrientes falsos. Si un nutriente falta en BEDCA para un alimento, la app tiene que dejarlo visible, no esconderlo.
- Que dependa de un servidor ajeno en tiempo de uso. Los datos se descargan con un script y se guardan en local; la app funciona sin conexión.

## Fuentes de datos (comprobadas el 2026-11-22)

### Mercadona

API no oficial de la tienda online, sin autenticación:

- `GET https://tienda.mercadona.es/api/categories/?lang=es&wh=bcn1` devuelve 26 categorías de primer nivel, cada una con subcategorías (`id`).
- `GET https://tienda.mercadona.es/api/categories/{id}/?lang=es&wh=bcn1` devuelve los productos de la subcategoría. Cada producto trae `id`, `display_name`, `price_instructions` con `unit_price` (precio del envase), `reference_price` y `reference_format` (precio por kg o L).
- `GET https://tienda.mercadona.es/api/products/{id}/?lang=es&wh=bcn1` devuelve el detalle con `nutrition_information.ingredients` y `nutrition_information.allergens` (HTML), `details`, `is_variable_weight`, `ean`. No trae tabla nutricional.

El scraper debe ir despacio (pausa entre peticiones) y guardar caché en disco para no repetir descargas.

### BEDCA

Interfaz XML pública: `POST https://www.bedca.net/bdpub/procquery.php` con cuerpo `text/xml`.

- La consulta de nivel 1 devuelve la lista de 2.336 alimentos (`f_id`, `f_ori_name`).
- La consulta de nivel 2 con `f_id` devuelve los nutrientes: `c_ori_name`, `best_location` (valor por 100 g de porción comestible), `v_unit`. Ejemplo: "Lenteja, seca, cruda" trae 32 componentes (macros, fibra, ácidos grasos, colesterol, 10 minerales, vitaminas A, D, E, B1, B2, niacina, B5, B6, B12, C, fólico).

Problemas conocidos que la limpieza debe tratar:

- Unidades erróneas puntuales (cobre aparece en µg con valores de mg).
- Valores vacíos o ausentes: se guardan como "desconocido", nunca como 0 en silencio.
- No hay vitamina K, y el yodo es escaso.

Tratamiento de "desconocido" en el optimizador (decisión mía): para las restricciones de mínimo cuenta como 0, que es lo conservador porque nunca da por cubierto algo que no consta. Para las de máximo también cuenta como 0, y la solución marca ese nutriente como "posible exceso no verificable" si algún producto elegido tiene el dato desconocido. El catálogo guarda por celda el valor y un indicador `conocido`. La salida del optimizador devuelve, por nutriente, el total y la fracción aportada por alimentos con dato conocido.

### Open Food Facts (etiqueta del producto)

BEDCA no trae azúcares y a muchos alimentos les falta la energía. Para eso se usa la tabla de la etiqueta del producto concreto, buscada por el EAN que da Mercadona:

- `GET https://world.openfoodfacts.org/api/v2/product/{ean}.json?fields=product_name,nutriments`, con un User-Agent genérico (`optidieta/0.1`), pausa de 1 s y caché en disco.
- Campos por 100 g: `energy-kcal_100g`, `fat_100g`, `saturated-fat_100g`, `carbohydrates_100g`, `sugars_100g`, `fiber_100g`, `proteins_100g`, `sodium_100g` (o `salt_100g` / 2,5).
- En una muestra de 10 productos de pasta de Mercadona, 7 tenían azúcares y kcal.

Precedencia: para los nutrientes de la etiqueta manda Open Food Facts cuando el dato existe; el resto (vitaminas, minerales salvo sodio) sale de BEDCA. Si las kcal de la etiqueta se desvían más de un 20 % de las calculadas con sus macros (4·P + 4·HC + 9·G + 2·fibra), los datos de etiqueta de ese producto se descartan y se usa BEDCA. El catálogo guarda de dónde sale cada producto (`fuente_etiqueta`: `off` o `bedca`). Los datos de Open Food Facts son colaborativos y pueden estar desactualizados; la app muestra la fuente.

## Cómo funciona

```
scripts/fetch_mercadona.py  → data/raw/mercadona/*.json (caché)
scripts/fetch_bedca.py      → data/raw/bedca/*.xml (caché)
(fetch Open Food Facts)     → data/raw/off/*.json (caché, por EAN)
scripts/build_catalog.py    → data/catalog.parquet  (producto, precio €/100 g, nutrientes, flags de dieta)
data/mapping.csv            → emparejamiento producto Mercadona ↔ f_id BEDCA (editable a mano)
optidieta/optimizer.py      → función pura: catálogo + objetivos + vetos → solución
app.py                      → Streamlit
```

### Emparejamiento producto ↔ BEDCA

- Solo se consideran subcategorías de alimentos básicos (fruta y verdura, arroz/legumbres/pasta, huevos/leche/mantequilla, carne, pescado, aceites, frutos secos, conservas simples como legumbre o atún, pan básico, yogur natural, quesos). La lista de subcategorías incluidas vive en un fichero de configuración.
- Propuesta automática por similitud de nombre (normalizando acentos y quitando marca, formato y peso), prefiriendo la entrada BEDCA en crudo/seco, que es como se vende.
- `mapping.csv` con columnas: `mercadona_id`, `nombre`, `bedca_id`, `bedca_nombre`, `confianza`, `revisado` (sí/no), `excluir` (sí/no). La propuesta automática solo rellena filas nuevas; nunca pisa filas revisadas a mano.
- Los productos sin emparejamiento o marcados `excluir` no entran en el catálogo.
- Solo entran en el catálogo las filas con `revisado = sí`. El builder entrega el CSV ya revisado (emparejamiento, porción comestible y peso por unidad) para todos los productos de las subcategorías incluidas, de modo que la app dé dietas sensatas desde el primer día. Al actualizar precios, los productos nuevos quedan sin revisar y la app avisa de cuántos hay.

### Precio

- €/100 g a partir de `reference_price` cuando `reference_format` es kg o L (para L se asume 1 kg/L salvo aceite, que usa densidad 0,92).
- Productos por unidad (por ejemplo huevos por docena, piezas de fruta): se necesita un peso por unidad. Para huevos 60 g/unidad; para el resto, la propuesta del mapping puede incluir una columna `g_por_unidad` editable. Sin peso conocido el producto se excluye.
- Porción comestible: BEDCA da valores por 100 g comestibles; el precio de Mercadona es por peso bruto. Primera versión: columna `porcion_comestible` en `mapping.csv` (por defecto 1,0; el builder pone valores razonables para fruta con piel/hueso, pescado entero, etc.).

### Dieta

Flags por producto, calculados en `build_catalog.py` y sobrescribibles en `mapping.csv`:

- No vegetariano: categorías Carne y Marisco y pescado, o ingredientes con carne, pescado, gelatina, etc.
- No vegano: además, leche, huevo, miel, mantequilla, queso, yogur, o alérgenos "leche" / "huevos".

### Optimizador

Programación lineal con `scipy.optimize.linprog` (método HiGHS):

- Variables: gramos diarios de cada producto, ≥ 0, con un máximo opcional por producto (por defecto 500 g/día) para evitar soluciones absurdas.
- Objetivo: minimizar el coste diario.
- Restricciones: mínimo y máximo por nutriente activo.
- Si no es factible, devolver qué restricciones lo impiden (relajar una a una o usar variables de holgura con coste alto) para que la interfaz lo explique.
- Entrada y salida en estructuras simples (dataclasses o dicts), sin dependencias de Streamlit.

### Objetivos nutricionales

Valores de referencia EFSA (DRV) para adultos, con perfil de sexo, franja de edad y peso (por defecto 70 kg). Los valores concretos y su fuente se guardan en un fichero de datos versionado, no en el código.

- Mínimo: PRI; si no existe, AI.
- Máximo: UL cuando existe; si no, sin máximo.
- Energía: banda de ±5 % alrededor del objetivo, que por defecto sale de la tabla EFSA por sexo y edad con actividad moderada, editable.
- Proteína: 0,83 g/kg de peso como mínimo.
- Grasa e hidratos: rangos EFSA en % de energía (grasa del 20 al 35 %, hidratos del 45 al 60 %), expresados como restricciones lineales sobre energía (por ejemplo 9·grasa ≥ 0,20·kcal). Fibra ≥ 25 g, sodio con máximo. Azúcares (de Open Food Facts) con máximo del 10 % de la energía (OMS), inactivo por defecto: la OMS lo fija para azúcares libres, y en alimentos básicos casi todo el azúcar es el natural de fruta y leche. El usuario puede activarlo.
- Cada restricción tiene mínimo, máximo e interruptor de activo editables.

### Interfaz (Streamlit)

- Barra lateral: tipo de dieta, perfil (sexo, edad, peso).
- Resultado principal: coste diario y semanal, tabla de productos (nombre, gramos/día, coste, enlace a Mercadona) y botón de vetar en cada fila.
- Tabla de nutrientes: cubierto / objetivo, con aviso de los nutrientes que dependen de alimentos con datos incompletos en BEDCA.
- Pestaña de objetivos: editar mínimos y máximos, activar o desactivar cada uno.
- Pestaña de catálogo: buscar productos, vetar, editar precio local (no toca los datos descargados).
- Comparación con la solución anterior: diferencia de coste y qué alimentos entran y salen, como en el original.
- Estado del usuario (vetos, precios editados, objetivos) guardado en un fichero local para que sobreviva al reinicio.

## Enfoques considerados

1. Web en el navegador (React + HiGHS WASM): sin servidor e interfaz más pulida, pero el usuario prefiere todo en Python local.
2. Backend Python + web aparte: imita la arquitectura del original; demasiada infraestructura para uso personal.
3. Python + Streamlit local (elegido): el usuario lo prefiere, da tablas editables y gráficos con poco código, y deja el optimizador reutilizable desde Python.

Para los datos se descartó CoFID con los precios del original (precios británicos estimados por él, no reutilizables en serio) y BEDCA con precios metidos a mano. El usuario propuso Mercadona + BEDCA y se comprobó que ambas APIs dan lo necesario.

## Decisiones del usuario

- Herramienta local, toda en Python, interfaz Streamlit.
- Catálogo: productos de Mercadona; nutrientes estimados con BEDCA.
- Filtros vegetariano y vegano.
- Lo demás (supermercados extra, recetas) queda para después.

## Decisiones mías (corregibles)

- Solo alimentos básicos de un ingrediente; procesados fuera.
- Emparejamiento semiautomático con CSV revisable.
- Objetivos EFSA con selector sexo/edad, en vez de los 3.000 kcal fijos del original.
- Tope por defecto de 500 g/día por producto.
- Dato desconocido = 0 en el optimizador, con aviso visible.
- Mapping entregado ya revisado; las filas sin revisar no entran.
- Objetivos: PRI/AI como mínimo, UL como máximo, energía ±5 %, macros en % de energía, peso en el perfil.
- Sin presupuesto en la interfaz: el objetivo ya es minimizar el coste, así que un tope de presupuesto no cambiaría la solución.
- Nombre y ubicación: `~/optidieta`.

## Lo que queda al builder

- Estructura interna de módulos, formato de caché, nombres.
- Algoritmo concreto de similitud para el emparejamiento.
- Diseño visual de la interfaz dentro de lo descrito.
- Tests: como mínimo el optimizador (casos pequeños con solución conocida, caso no factible) y la limpieza de BEDCA.
