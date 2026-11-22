from optidieta.sources.mercadona import MercaProduct


def product(**kw) -> MercaProduct:
    base = dict(
        id="1", ean=None, nombre="Producto", categoria="Arroz, legumbres y pasta", subcategoria="Legumbres",
        subcategoria_id=121, precio_envase=1.0, precio_ref=1.0, formato_ref="kg", peso_variable=False,
        ingredientes="", alergenos="", url="https://tienda.mercadona.es/product/1",
    )
    base.update(kw)
    return MercaProduct(**base)
