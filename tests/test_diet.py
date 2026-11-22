from helpers import product

from optidieta.diet import diet_flags


def test_lentils_vegan():
    assert diet_flags(product(nombre="Lentejas pardinas", ingredientes="Lentejas pardinas.")) == (True, True)


def test_yogurt_vegetarian():
    p = product(nombre="Yogur natural", categoria="Postres y yogures", ingredientes="Leche, fermentos lácticos.",
                alergenos="Contiene leche y sus derivados (incluida la lactosa).")
    assert diet_flags(p) == (True, False)


def test_tuna_not_vegetarian():
    p = product(nombre="Atún claro en aceite de oliva", categoria="Conservas, caldos y cremas",
                ingredientes="Atún claro, aceite de oliva, sal.", alergenos="Contiene pescado.")
    assert diet_flags(p) == (False, False)


def test_meat_category():
    assert diet_flags(product(nombre="Contramuslo deshuesado", categoria="Carne")) == (False, False)


def test_soy_drink_vegan():
    p = product(nombre="Bebida de soja Hacendado", categoria="Huevos, leche y mantequilla",
                ingredientes="Agua, haba de soja (8%).")
    assert diet_flags(p) == (True, True)


def test_traces_do_not_count():
    p = product(nombre="Fideo cabello de ángel", ingredientes="Sémola de trigo duro (gluten). Puede contener trazas de huevos, soja y mostaza.",
                alergenos="Contiene trigo. Puede contener trazas de huevo y leche.")
    assert diet_flags(p) == (True, True)


def test_egg_pasta_not_vegan():
    p = product(nombre="Macarrón al huevo", ingredientes="Sémola de trigo duro, huevo (20%).")
    assert diet_flags(p) == (True, False)


def test_free_from_statements_do_not_count():
    p = product(nombre="Arroz Nomen", ingredientes="Arroz semilargo",
                alergenos="Libre de moluscos y productos a base de moluscos. Libre de huevos y productos a base de huevo. "
                          "Libre de pescado y productos a base de pescado. Libre de leche y sus derivados (incluida la lactosa).")
    assert diet_flags(p) == (True, True)
