"""Registro de nutrientes: claves internas, unidades y cómo leerlos de BEDCA y Open Food Facts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Nutrient:
    key: str
    label: str
    unit: str
    bedca_ids: tuple[int, ...] = ()
    bedca_names: tuple[str, ...] = ()
    off_field: str | None = None
    off_factor: float = 1.0


N = Nutrient
NUTRIENTS: list[Nutrient] = [
    N("energia_kcal", "Energía", "kcal", (), ("energia, total",), "energy-kcal_100g"),
    N("proteina_g", "Proteína", "g", (416,), (), "proteins_100g"),
    N("grasa_g", "Grasa total", "g", (410,), (), "fat_100g"),
    N("grasa_sat_g", "Grasa saturada", "g", (299,), (), "saturated-fat_100g"),
    N("hidratos_g", "Hidratos de carbono", "g", (53,), (), "carbohydrates_100g"),
    N("azucares_g", "Azúcares", "g", (446,), ("azucares, totales",), "sugars_100g"),
    N("fibra_g", "Fibra", "g", (307,), (), "fiber_100g"),
    N("sodio_mg", "Sodio", "mg", (323,), (), "sodium_100g", 1000),
    N("potasio_mg", "Potasio", "mg", (321,)),
    N("cloruro_mg", "Cloruro", "mg", (318,)),
    N("calcio_mg", "Calcio", "mg", (317,)),
    N("magnesio_mg", "Magnesio", "mg", (322,)),
    N("fosforo_mg", "Fósforo", "mg", (326,)),
    N("hierro_mg", "Hierro", "mg", (319,)),
    N("zinc_mg", "Zinc", "mg", (464,)),
    N("cobre_mg", "Cobre", "mg", (453,)),
    N("manganeso_mg", "Manganeso", "mg", (457,)),
    N("selenio_ug", "Selenio", "µg", (462,)),
    N("yodo_ug", "Yodo", "µg", (456,)),
    N("vit_a_ug", "Vitamina A (ER)", "µg", (100,)),
    N("vit_d_ug", "Vitamina D", "µg", (102,)),
    N("vit_e_mg", "Vitamina E", "mg", (103,)),
    N("tiamina_mg", "Vitamina B1", "mg", (483,)),
    N("riboflavina_mg", "Vitamina B2", "mg", (482,)),
    N("niacina_mg", "Niacina (EN)", "mg", (475,)),
    N("vit_b5_mg", "Vitamina B5", "mg", (478,)),
    N("vit_b6_mg", "Vitamina B6", "mg", (481,), ("vitamina b-6, total",)),
    N("vit_b12_ug", "Vitamina B12", "µg", (484,)),
    N("vit_c_mg", "Vitamina C", "mg", (486,)),
    N("folato_ug", "Folato", "µg", (487,), ("folato, total",)),
    N("colesterol_mg", "Colesterol", "mg", (433,)),
]
del N

BY_KEY: dict[str, Nutrient] = {n.key: n for n in NUTRIENTS}


def col(key: str) -> str:
    return f"n_{key}"


def known_col(key: str) -> str:
    return f"k_{key}"
