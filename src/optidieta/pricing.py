from optidieta.sources.mercadona import MercaProduct
from optidieta.textutil import norm

HUEVO_G = 60  # gramos por huevo


def price_per_100g(p: MercaProduct, porcion_comestible: float | None, g_por_unidad: float | None,
                   densidad: float | None) -> float | None:
    """€ por 100 g de porción comestible, o None si no se puede calcular."""
    fmt = (p.formato_ref or "").strip().lower()
    if fmt == "kg" and p.precio_ref:
        bruto = p.precio_ref / 10
    elif fmt in ("100 g", "100g", "100 ml", "100ml") and p.precio_ref:
        bruto = p.precio_ref
    elif fmt in ("dz", "dc") and p.precio_ref:  # huevos: precio por docena / decena, 60 g por huevo
        bruto = p.precio_ref / ((12 if fmt == "dz" else 10) * HUEVO_G / 100)
    elif fmt == "l" and p.precio_ref:
        d = densidad or (0.92 if "aceite" in norm(p.nombre) else 1.0)
        bruto = p.precio_ref / 10 / d
    elif g_por_unidad and g_por_unidad > 0 and p.precio_envase:
        bruto = p.precio_envase / (g_por_unidad / 100)
    else:
        return None
    pc = porcion_comestible if porcion_comestible and porcion_comestible > 0 else 1.0
    return bruto / pc
