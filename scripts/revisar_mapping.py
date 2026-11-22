"""Revisión del emparejamiento Mercadona ↔ BEDCA por reglas escritas a mano.

Cada regla: (subcategorías o None, patrón sobre el nombre normalizado, alimento BEDCA o None para excluir, extras).
Gana la primera que encaja. Las filas sin regla se quedan `revisado=no` (fuera del catálogo) y se listan.
Uso: uv run python scripts/revisar_mapping.py [--check]
"""

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from optidieta.cli import load_products, paths  # noqa: E402
from optidieta.mapping import read_mapping, write_mapping  # noqa: E402
from optidieta.nutrients import NUTRIENTS, known_col  # noqa: E402
from optidieta.textutil import norm  # noqa: E402

X = None  # excluir

# Procesados, platos, dulces, no alimentos básicos: fuera en cualquier subcategoría.
EXCLUIR = (
    r"listo para comer|ensalada (de pasta|de pollo|cesar|california|de la casa|ensatun|queso de cabra)|wraps|"
    r"guacamole|rebozad|empanad|a la romana|tempura|croqueta|buñuelo|bunuelo|fingers|figuritas|torpedos|rabas|"
    r"empanadilla|surimi|delicias del mar|salpicon|elaborado de|preparado de paella|arreglo de marisco|"
    r"adobad|marinad|al vino|provenzal|san jacobo|brocheta|pincho|albondiga|burger|hamburguesa|"
    r"preparado de carne picada|steak tartar|carpaccio|foie|careta|manos de cerdo|fiambre|"
    r"crema de queso|mousse|queso untar|tabla de quesos|rulo con piña|"
    r"girasoles|ravioli|tortellini|medialunas|gnocchi|canelones|lasaña|lasana|fideos orientales|noodles ramen|"
    r"noodles orientales|yakisoba|yatekomo|sabor (pollo|picante|soja)|"
    r"barrita|cereales (cubiertos|rellenos|de arroz inflado|estrellas|avena crunchy|copos de trigo chocodays)|"
    r"chocolate|cacao|crunchy|mini cereales|con miel|special k|corn flakes kellogg|"
    r"azucar glas|sobres|edulcorante|sirope|panela|"
    r"aroma |gelatina|impulsor|levadura|masa (de|fresca|filo|gruesa|para)|preparado en polvo|preparado para reposteria|"
    r"batido|bebida lactea|preparado lacteo|crema de leche para cafe|horchata|leche condensada|leche evaporada|"
    r"preparado de coco|bechamel|"
    r"postre lacteo|kefir|yogur (con frutas|cremoso|sabor|sabores)|postre de soja (con caramelo|sabor)|postre de coco|"
    r"aliño|alino|bebida aromatizada|crema de vinagre|reduccion|preparado para ahumar|sal de ajo|sal de frutas|"
    r"bicarbonato|vinagre|limon exprimido|"
    r"cous cous|arroz cocido|quinoa cocida|"
    r"salsa|en tinta|escabeche|rellenos|al ajillo|con pimientos del piquillo|picantes|"
    r"fritada|tomate frito|para untar|tomate seco|"
    r"bolsita|papilla|cabello de angel hida|caramelizada|chucrut|dulce de membrillo|ensalada china|"
    r"agridulce|almibar|postre de manzana|verduras asadas|macedonia de verduras|"
    r"frito|fritas|frita|tostad[oa]s? con sal|gigante con sal|\bsalad[oa]s?\b|aguasal|girasol barbacoa|sabores a barbacoa|tex-mex|twist|sabor ahumado|rodeo|rumba|combinado|"
    r"cocktail de fruta|palomitas|pan de higo|peladillas|cacahuete en polvo|deshidratad|"
    r"a la crema|ensaladilla|gyozas|relleno fajitas|rollitos|salteado de (gambas|patata|pollo)|prefritas|"
    r"patatas fritas|pisto|menestra|parrillada|wok|mix frutas pink|"
    r"tinta de sepia|huevo hilado|claras de huevo|huevos de codorniz|"
    r"pan (de burger|hot dog|brioche|bagel|de pita|viena|de leche)|piadina|panes de leche|panecillo de queso|"
    r"sin gluten|maxi pan|mini pan|tortillas de (maiz|avena)|"
    r"manteca de cerdo|margarina (flora|tulipan)|crema de soja|\bnata\b"
)

R = [
    # ---- Fruta (27, 145) ----
    ((27, 145), r"aguacate", "Aguacate", {"porcion_comestible": 0.70}),
    ((27, 145), r"arandano", "Arandano", {}),
    ((27,), r"banana|platano", "Plátano", {"porcion_comestible": 0.65}),
    ((27,), r"cereza", "Cereza", {"porcion_comestible": 0.90}),
    ((27, 145), r"frambuesa", "Frambuesa, cruda", {}),
    ((27,), r"granada", "Granada", {"porcion_comestible": 0.55}),
    ((27,), r"kaki", "Caqui", {"porcion_comestible": 0.85}),
    ((27,), r"kiwi", "Kiwi", {"porcion_comestible": 0.85}),
    ((27,), r"^lima$", "Lima, cruda", {"porcion_comestible": 0.70}),
    ((27,), r"limon", "Limón, zumo, fresco", {"porcion_comestible": 0.45}),
    ((27,), r"mandarina", "Mandarina", {"porcion_comestible": 0.75}),
    ((27,), r"mango", "Mango, crudo", {"porcion_comestible": 0.70}),
    ((27,), r"manzana", "Manzana", {"porcion_comestible": 0.90}),
    ((27,), r"melon", "Melón", {"porcion_comestible": 0.60}),
    ((27,), r"naranja", "Naranja", {"porcion_comestible": 0.73}),
    ((27,), r"papaya", "Papaya, cruda", {"porcion_comestible": 0.70}),
    ((27,), r"^peras?\b", "Pera", {"porcion_comestible": 0.85}),
    ((27,), r"piña natural", "Piña", {}),
    ((27,), r"^piña$", "Piña", {"porcion_comestible": 0.55}),
    ((27,), r"pomelo", "Pomelo", {"porcion_comestible": 0.70}),
    ((27,), r"^uva", "Uva blanca", {"porcion_comestible": 0.95}),
    ((27, 145), r"^moras|frutos rojos", "Frambuesa, cruda", {}),
    ((145,), r"fresa", "Fresa", {}),
    ((145,), r"mix frutas tropical", "Mango, crudo", {}),
    # ---- Verdura (28, 29, 145, 127) ----
    ((28,), r"canonigo|ensalada mezcla|rucula|brotes", "Lechuga", {}),
    ((28,), r"cogollos corazon", "Lechuga", {"g_por_unidad": 360}),
    ((28,), r"cogollos", "Lechuga", {"g_por_unidad": 300}),
    ((28,), r"lechuga iceberg$", "Lechuga", {"g_por_unidad": 500, "porcion_comestible": 0.85}),
    ((28,), r"lechugas corazon romana", "Lechuga", {"g_por_unidad": 400}),
    ((28,), r"lechuga corazon romana", "Lechuga", {"g_por_unidad": 450, "porcion_comestible": 0.85}),
    ((28,), r"lechuga hoja roble", "Lechuga", {"g_por_unidad": 300, "porcion_comestible": 0.85}),
    ((28,), r"lechuga", "Lechuga", {}),
    ((28,), r"escarola rizada$", "Escarola", {"g_por_unidad": 500, "porcion_comestible": 0.80}),
    ((28,), r"escarola", "Escarola", {}),
    ((28,), r"endibia", "Endibia", {}),
    ((28, 29, 145), r"espinaca", "Espinaca, congelada, cruda", {}),
    ((29, 127), r"acelga", "Acelga, cruda", {}),
    ((29,), r"^ajo", "Ajo", {"porcion_comestible": 0.90}),
    ((145,), r"ajo", "Ajo", {}),
    ((29, 145, 127), r"alcachofa", "Alcachofa, cruda", {"porcion_comestible": 0.45}),
    ((29,), r"apio", "Apio, crudo", {"porcion_comestible": 0.80}),
    ((29, 145), r"batata", "Batata, cruda", {"porcion_comestible": 0.85}),
    ((29,), r"berenjena", "Berenjena", {"porcion_comestible": 0.90}),
    ((29, 145), r"brocoli", "Brocoli, crudo", {}),
    ((29,), r"calabacin", "Calabacín", {"porcion_comestible": 0.95}),
    ((29,), r"calabaza", "Calabaza, cruda", {"porcion_comestible": 0.80}),
    ((29, 133), r"castaña", "Castaña, cruda", {"porcion_comestible": 0.85}),
    ((29,), r"cebollas tiernas", "Cebolla", {"g_por_unidad": 300, "porcion_comestible": 0.80}),
    ((29, 145), r"cebolla", "Cebolla", {"porcion_comestible": 0.90}),
    ((29,), r"chalota", "Cebolla", {"porcion_comestible": 0.90}),
    ((29, 127), r"champiñon|setas?\b|shiitake", "Champiñón", {}),
    ((29,), r"col lombarda|repollo", "Repollo", {"porcion_comestible": 0.85}),
    ((145,), r"coles de bruselas", "Col de bruselas, congelada", {}),
    ((29, 145), r"coliflor", "Coliflor, congelada, cruda", {}),
    ((29, 145, 127), r"esparrago", "Espárrago, verde", {}),
    ((29, 145, 127), r"judia verde|judias verdes", "Judía verde, cruda", {}),
    ((29,), r"maiz dulce en mazorca cocido", "Maíz en conserva", {"g_por_unidad": 500, "porcion_comestible": 0.50}),
    ((29,), r"maiz dulce en mazorca$", "Maíz, en mazorca, crudo", {"g_por_unidad": 500, "porcion_comestible": 0.50}),
    ((145, 127), r"^maiz dulce", "Maíz en conserva", {}),
    ((29, 127), r"zanahoria", "Zanahoria, cruda", {"porcion_comestible": 0.90}),
    ((29, 145, 127), r"patata", "Patata, cruda", {"porcion_comestible": 0.85}),
    ((29,), r"pepino", "Pepino", {"porcion_comestible": 0.90}),
    ((29, 145, 127), r"pimiento", "Pimiento rojo, crudo", {"porcion_comestible": 0.85}),
    ((29,), r"puerro", "Puerro, crudo y congelado", {"porcion_comestible": 0.70}),
    ((29,), r"rabanito", "Rábano", {}),
    ((29, 127), r"remolacha", "Remolacha, en conserva", {}),
    ((29,), r"^tomate|tomates", "Tomate", {}),
    ((29,), r"yuca", X, {"porcion_comestible": 0.80}),
    ((29,), r"jengibre", "Jengibre", {}),
    ((29,), r"perejil|cilantro|albahaca|hierbabuena|cebollino", "Perejil, fresco", {}),
    ((29,), r"vegetales para microondas|preparado de verdura|salteado de (pimientos|verduras)", "Pimiento rojo, crudo", {}),
    ((145,), r"salteado de verduras|salteado de setas|salteado rustico|coliflor, brocoli", "Brocoli, crudo", {}),
    ((145,), r"edamame", "Soja, fresca", {}),
    ((145,), r"guisante", "Guisante, congelado, crudo", {}),
    ((127,), r"guisantes", "Guisantes en conserva", {}),
    ((145,), r"habas", "Haba, fresca", {}),
    ((145,), r"wakame", X, {}),
    ((127,), r"palmito|yemas de esparrago|esparragos blancos", "Esparragos blancos en conserva", {}),
    ((127,), r"melocoton light|piña en su jugo", "Piña, enlatada en su jugo", {}),
    ((127,), r"carne de ñora", "Pimiento rojo, crudo", {}),
    # ---- Tomate (126) ----
    ((126,), r"tomate (entero|triturado|troceado|tamizado)", "Tomate, maduro, pelado y triturado, enlatado", {}),
    ((126,), r"doble concentrado", X, {}),
    # ---- Legumbres, arroz, pasta, harinas, cereales ----
    ((121,), r"lenteja cocida", "Lenteja, en conserva", {}),
    ((121,), r"lenteja", "Lenteja, seca, cruda", {}),
    ((121,), r"garbanzo cocido", "Garbanzo, en conserva", {}),
    ((121,), r"garbanzo", "Garbanzo, seco, crudo", {}),
    ((121,), r"alubia cocida", "Judías blancas, cocidas", {}),
    ((121,), r"alubia (blanca|granja)", "Judía blanca", {}),
    ((121,), r"alubia", "Judía pinta", {}),
    ((121,), r"soja texturizada", "Soja, seca, cruda", {}),
    ((118,), r"integral", "Arroz integral, crudo", {}),
    ((118,), r"quinoa", "Quinoa, cruda", {}),
    ((118,), r"arroz", "Arroz", {}),
    ((120,), r"integral", "Pasta alimenticia, integral, cruda", {}),
    ((120,), r"al huevo|tagliatelle|nidos", "Pasta alimenticia, con huevo, cruda", {}),
    ((120,), r"vegetal", "Pasta alimenticia, con vegetales, cruda", {}),
    ((120,), r"lentejas rojas", "Lenteja, seca, cruda", {}),
    ((120,), r"noodles de arroz", "Arroz", {}),
    ((120,), r"fideo|fideua|helices|macarron|pappardelle|pasta|spaghetti|tallarines", "Pasta alimenticia, cruda", {}),
    ((69,), r"harina de arroz", "Arroz", {}),
    ((69,), r"integral|espelta", "Harina de trigo, integral", {}),
    ((69,), r"harina de garbanzo", "Garbanzo, seco, crudo", {}),
    ((69,), r"maiz", "Harina de maíz", {}),
    ((69,), r"harina|semola", "Harina de trigo", {}),
    ((78,), r"avena|copos de avena", "Avena, cruda", {}),
    ((78,), r"muesli", "Muesli", {}),
    ((78,), r"salvado", "Salvado de trigo", {}),
    ((78,), r"corn flakes|copos de maiz", "Cereales desayuno base de maíz y trigo", {}),
    ((78,), r"copos de trigo|cereal mix|crujientes", "Muesli", {}),
    # ---- Pan (59, 60) ----
    ((59, 60), r"centeno", "Pan de centeno", {}),
    ((59, 60), r"integral|espelta|avena|semillas|cereales", "Pan integral", {}),
    ((60,), r"tortillas de trigo", "Pan blanco, de barra", {}),
    ((60,), r"molde", "Pan blanco, de barra", {}),
    ((59, 60), r"pan|baguette|barra|bocadillo|hogaza|chapata|panecillo|pulguita", "Pan blanco, de barra", {}),
    # ---- Lácteos y huevos ----
    ((72,), r"bebida de soja", "Bebida de soja", {}),
    ((72,), r"bebida de (almendra|arroz|avena|avellana|coco)", "Bebida de soja", {"vegano": "sí"}),
    ((72,), r"leche en polvo", "Leche de vaca, semidesnatada, en polvo", {}),
    ((72,), r"leche desnatada", "Leche, desnatada, pasteurizada", {}),
    ((72,), r"leche semidesnatada", "Leche, semidesnatada, pasteurizada", {}),
    ((72,), r"leche entera", "Leche de vaca, entera", {}),
    ((75,), r"mantequilla", "Mantequilla salada", {}),
    ((75,), r"margarina", "Margarina de maíz", {}),
    ((77,), r"cocidos", "Huevo de gallina, pasado por agua", {"porcion_comestible": 0.88}),
    ((77,), r"huevos", "Huevo de gallina fresco", {"porcion_comestible": 0.88}),
    ((103, 104), r"yogur natural", "Yogur \"tipo bio\", natural", {}),
    ((106,), r"postre de soja natural", "Yogur de soja", {"vegano": "sí"}),
    ((53,), r"fresco batido|quark", "Queso fresco de burgos", {}),
    ((53,), r"fresco.*(0%|desnatado|light)", "Queso fresco de burgos", {}),
    ((53,), r"fresco|burgos|mato|requeson|ricotta|cottage", "Queso fresco de burgos", {}),
    ((53,), r"mozzarella|burrata", "Queso mozzarella", {}),
    ((53,), r"azul|gorgonzola|roquefort", "Queso roquefort", {}),
    ((53,), r"brie", "Queso brie", {}),
    ((53,), r"feta", "Queso fresco, cabra", {}),
    ((53,), r"mascarpone", "Queso para untar", {}),
    ((53,), r"cabra|provolone", "Queso cabra, curado", {}),
    ((54,), r"emmental", "Queso emmental", {}),
    ((54,), r"grana padano", "Queso parmesano", {}),
    ((54,), r"cheddar", "Queso cheddar", {}),
    ((54,), r"gouda|edam|maasdam", "Queso gouda", {}),
    ((54,), r"tierno|arzua|tronchon", "Queso tierno, genérico", {}),
    ((54,), r"semicurado|mahon", "Queso semicurado, genérico", {}),
    ((54,), r"curado|añejo|viejo|manchego", "Queso curado, genérico", {}),
    # ---- Carne ----
    ((38,), r"higado|corazon|molleja", "Higado de pollo, crudo", {}),
    ((38,), r"pavo", "Pavo, pechuga, con piel, crudo", {}),
    ((38,), r"pato|magret", "Pato, entero, crudo", {}),
    ((38,), r"codorni", X, {"porcion_comestible": 0.65}),
    ((38,), r"pechuga|solomillo|taquitos", "Pollo, pechuga, con piel, crudo", {}),
    ((38,), r"carcasa", "Pollo, entero, con piel, crudo", {"porcion_comestible": 0.35}),
    ((38,), r"alas", "Pollo, ala, con piel, cruda", {"porcion_comestible": 0.60}),
    ((38,), r"contramuslo|muslo|jamoncito|cuartos traseros", "Pollo, muslo, con piel, crudo", {"porcion_comestible": 0.75}),
    ((38,), r"pollo|picanton", "Pollo, entero, con piel, crudo", {"porcion_comestible": 0.70}),
    ((37,), r"higado", "Hígado, de cerdo, crudo", {}),
    ((37,), r"panceta", "Cerdo, panceta, cruda", {}),
    ((37,), r"costilla", "Cerdo, chuleta, crudo", {"porcion_comestible": 0.70}),
    ((37,), r"chuleta", "Cerdo, chuleta, crudo", {"porcion_comestible": 0.80}),
    ((37,), r"lomo|solomillo|cabeza", "Cerdo, lomo, crudo", {}),
    ((37,), r"secreto|presa|pluma|lagarto|carrillada|cerdo a tacos|taquitos", "Cerdo, chuleta, crudo", {}),
    ((40,), r"higado", "Hígado, de vaca/buey, crudo", {}),
    ((40,), r"vacuno|ternera|churrasco", "Ternera, lomo, crudo, con grasa separable", {}),
    ((42,), r"conejo", "Conejo de granja, carne, cruda", {"porcion_comestible": 0.75}),
    ((42,), r"cordero", "Cordero, costilla, crudo", {"porcion_comestible": 0.75}),
    # ---- Pescado y marisco ----
    ((31, 34, 149), r"bacaladilla|merluza|pescadilla", "Merluza fresca", {}),
    ((31, 34, 149), r"bacalao", "Bacalao, crudo", {}),
    ((31, 34, 149), r"salmon", "Salmón", {}),
    ((31, 34, 149), r"atun", "Atún, crudo", {}),
    ((31, 34, 149), r"dorada|lubina|corvina|rodaballo|lenguado|gallineta|rape|panga|emperador|tintorera|fritura",
     "Lubina", {}),
    ((31,), r"trucha", "Trucha", {}),
    ((31, 34, 149), r"dorada|lubina", "Lubina", {"porcion_comestible": 0.60}),
    ((31, 34, 149), r"calamar|pota|poton|chipiron", "Calamar, crudo", {}),
    ((31, 34, 149), r"sepia", "Sepia", {}),
    ((31, 34, 149), r"pulpo", "Pulpo", {}),
    ((32,), r"mejillon", "Mejillón", {"porcion_comestible": 0.35}),
    ((32,), r"almeja|chirla|berberecho|coquina|navaja|ostra|vieira", "Almeja", {"porcion_comestible": 0.30}),
    ((32,), r"gamba|gambon|langostino|camaron|cigala|bogavante|cangrejo|buey", "Gamba roja, cruda", {"porcion_comestible": 0.45}),
    ((123,), r"mejillon", "Mejillón", {}),
    ((123,), r"almeja|almejon|berberecho", "Almeja", {}),
    ((122,), r"atun|bonito|ventresca", "Atún en aceite de oliva isabel", {}),
    ((122,), r"caballa|melva", "Caballa, enlatada en aceite, escurrida", {}),
    ((122,), r"sardin", "Sardina, enlatada, en aceite, escurrida", {}),
    ((122,), r"salmon al natural", "Salmón", {}),
    # ---- Aceite, sal, azúcar ----
    ((112,), r"coco", "Aceite de coco", {}),
    ((112,), r"girasol", "Aceite de girasol", {}),
    ((112,), r"oliva virgen", "Aceite de oliva virgen extra", {}),
    ((112,), r"oliva", "Aceite de oliva", {}),
    ((112,), r"yodada", "Sal yodada", {}),
    ((112,), r"^sal|sal marina", "Sal de mar", {}),
    ((89,), r"moreno", "Azúcar moreno", {}),
    ((89,), r"azucar", "Azúcar blanca", {}),
    # ---- Frutos secos y desecados (133) ----
    ((133,), r"almendra", "Almendra, cruda", {}),
    ((133,), r"anacardo", "Anacardo, crudo", {}),
    ((133,), r"avellana", "Avellana", {}),
    ((133,), r"cacahuete", "Cacahuete, crudo, con cáscara", {}),
    ((133,), r"nuez de brasil", X, {}),
    ((133,), r"macadamia", "Nuez", {}),
    ((133,), r"pecana", "Nuez", {}),
    ((133,), r"nuez", "Nuez", {}),
    ((133,), r"pistacho", "Pistacho", {}),
    ((133,), r"pipas (de )?calabaza", "Pipa de calabaza", {}),
    ((133,), r"pipas", "Pipa de girasol", {}),
    ((133,), r"chia", X, {}),
    ((133,), r"lino", "Semilla de lino", {}),
    ((133,), r"sesamo", "Sesamo, semilla", {}),
    ((133,), r"mezcla semillas", "Pipa de girasol", {}),
    ((133,), r"frutos secos", "Almendra, cruda", {}),
    ((133,), r"ciruela", X, {}),
    ((133,), r"datil", "Dátil", {"porcion_comestible": 0.90}),
    ((133,), r"higo", X, {}),
    ((133,), r"orejon", X, {}),
    ((133,), r"pasas", "Uva pasa", {}),
    ((133,), r"maiz palomitas", "Maíz, crudo", {}),
]


def bedca_index(bedca: pd.DataFrame) -> dict[str, int]:
    """Nombre normalizado → id con más nutrientes conocidos (BEDCA repite alimentos por fuente)."""
    known = bedca[[known_col(n.key) for n in NUTRIENTS]].sum(axis=1)
    best: dict[str, tuple[int, int]] = {}
    for name, bid, k in zip(bedca.bedca_nombre, bedca.bedca_id, known):
        key = norm(name)
        if key not in best or k > best[key][1]:
            best[key] = (int(bid), int(k))
    return {k: v[0] for k, v in best.items()}


def main(check: bool) -> None:
    p = paths()
    prods = {str(x.id): x for x in load_products(p)}
    bedca = pd.read_parquet(p["bedca_frame"])
    idx = bedca_index(bedca)
    names_by_id = dict(zip(bedca.bedca_id.astype(int), bedca.bedca_nombre))
    missing = sorted({b for _, _, b, _ in R if b and norm(b) not in idx})
    if missing:
        import difflib
        for b in missing:
            print(f"NO EXISTE en BEDCA: {b!r} → {difflib.get_close_matches(norm(b), idx, 4, 0.5)}")
        if check:
            return
    m = read_mapping(p["mapping"])
    excl = re.compile(norm(EXCLUIR))  # los nombres se normalizan (ñ→n, sin tildes): los patrones también
    rules = [(set(s) if s else None, re.compile(norm(rx)), b, ex) for s, rx, b, ex in R]
    sin_regla = []
    for i, row in m.iterrows():
        x = prods.get(str(row.mercadona_id))
        if x is None:
            continue
        name = norm(x.nombre)
        upd = {"revisado": "sí", "excluir": "no", "g_por_unidad": row.g_por_unidad}
        if excl.search(name):
            upd["excluir"] = "sí"
        else:
            for subs, rx, b, ex in rules:
                if (subs is None or x.subcategoria_id in subs) and rx.search(name):
                    if b is None or norm(b) not in idx:
                        upd["excluir"] = "sí"
                    else:
                        bid = idx[norm(b)]
                        upd.update(bedca_id=bid, bedca_nombre=names_by_id[bid], confianza=100,
                                   porcion_comestible=ex.get("porcion_comestible", 1.0))
                        for k in ("g_por_unidad", "vegetariano", "vegano"):
                            if k in ex:
                                upd[k] = ex[k]
                    break
            else:
                sin_regla.append(f"{x.subcategoria_id} {x.nombre}")
                upd = {"revisado": "no"}
        for k, v in upd.items():
            m.at[i, k] = v
    if not check:
        write_mapping(m, p["mapping"])
    print(f"filas: {len(m)}, revisadas: {(m.revisado == 'sí').sum()}, excluidas: {(m.excluir == 'sí').sum()}, "
          f"incluidas: {((m.revisado == 'sí') & (m.excluir != 'sí')).sum()}, sin regla: {len(sin_regla)}")
    for s in sin_regla:
        print("  sin regla:", s)


if __name__ == "__main__":
    main("--check" in sys.argv)
