import re

from optidieta.sources.mercadona import MercaProduct
from optidieta.textutil import norm

NO_VEGETARIANO = ["carne", "cerdo", "pollo", "pavo", "ternera", "vacuno", "cordero", "jamon", "pescado", "atun",
                  "salmon", "bacalao", "sardina", "anchoa", "marisco", "gamba", "mejillon", "calamar", "pulpo",
                  "gelatina", "cuajo animal"]
NO_VEGANO = ["leche", "lacteo", "nata", "mantequilla", "queso", "yogur", "huevo", "miel", "suero", "caseina",
             "lactosa"]
CAT_CARNE_PESCADO = {"carne", "marisco y pescado"}
CAT_LACTEOS = "huevos, leche y mantequilla"

_TRAZAS = re.compile(r"(libre de|sin |puede contener trazas? de|trazas de"
                     r"|elaborado en .*? que (tambien )?(utiliza|elabora|manipula))[^.]*\.?")


def _has(text: str, words: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(w), text) for w in words)


def diet_flags(p: MercaProduct) -> tuple[bool, bool]:
    """(vegetariano, vegano) según categoría, nombre, ingredientes y alérgenos (sin contar trazas)."""
    text = _TRAZAS.sub(" ", norm(f"{p.nombre}. {p.ingredientes}. {p.alergenos}"))
    cat = norm(p.categoria)
    vegetariano = cat not in CAT_CARNE_PESCADO and not _has(text, NO_VEGETARIANO)
    nombre = norm(p.nombre)
    vegetal = any(w in nombre for w in ("bebida", "vegetal", "margarina"))
    vegano = vegetariano and not _has(text, NO_VEGANO) and not (cat == CAT_LACTEOS and not vegetal)
    return vegetariano, vegano
