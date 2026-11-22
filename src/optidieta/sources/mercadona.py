"""Mercadona: catálogo y precios de la tienda online (API no oficial), con caché en disco."""

import json
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

from optidieta.textutil import strip_html

BASE = "https://tienda.mercadona.es/api"
PARAMS = {"lang": "es", "wh": "bcn1"}
HEADERS = {"User-Agent": "optidieta/0.1"}


@dataclass
class MercaProduct:
    id: str
    ean: str | None
    nombre: str
    categoria: str
    subcategoria: str
    subcategoria_id: int
    precio_envase: float
    precio_ref: float | None
    formato_ref: str | None
    peso_variable: bool
    ingredientes: str
    alergenos: str
    url: str
    marca: str = ""


def load_included(path: Path) -> set[int]:
    with open(path, "rb") as f:
        return {int(i) for i in tomllib.load(f).get("include", [])}


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_product(listing: dict, detail: dict, categoria: str, subcategoria: str, subcategoria_id: int) -> MercaProduct:
    pi = detail.get("price_instructions") or listing.get("price_instructions") or {}
    ni = detail.get("nutrition_information") or {}
    pid = str(detail.get("id") or listing["id"])
    return MercaProduct(
        id=pid,
        ean=detail.get("ean") or None,
        nombre=detail.get("display_name") or listing.get("display_name", ""),
        categoria=categoria,
        subcategoria=subcategoria,
        subcategoria_id=int(subcategoria_id),
        precio_envase=_f(pi.get("unit_price")) or 0.0,
        precio_ref=_f(pi.get("reference_price")),
        formato_ref=pi.get("reference_format"),
        peso_variable=bool(detail.get("is_variable_weight")),
        ingredientes=strip_html(ni.get("ingredients") or ""),
        alergenos=strip_html(ni.get("allergens") or ""),
        url=detail.get("share_url") or listing.get("share_url") or f"https://tienda.mercadona.es/product/{pid}",
        marca=detail.get("brand") or "",
    )


def _get_cached(session, cache: Path, name: str, path: str, delay: float) -> dict:
    f = cache / f"{name}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    r = session.get(f"{BASE}/{path}/", params=PARAMS, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)
    if delay:
        time.sleep(delay)
    return data


def clear_listings(cache_dir: Path) -> None:
    """Borra categorías y listados (precios) pero conserva los detalles de producto."""
    for f in Path(cache_dir).glob("cat*.json"):
        f.unlink()


def fetch_all(cache_dir: Path, include: set[int], session=None, delay: float = 1.0, progress=None) -> list[MercaProduct]:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()
    if not (cache / "categories.json").exists():
        (cache / "fetched_at.txt").write_text(datetime.now().isoformat(timespec="minutes"), encoding="utf-8")
    cats = _get_cached(session, cache, "categories", "categories", delay)
    out: list[MercaProduct] = []
    for top in cats.get("results", []):
        for sub in top.get("categories", []):
            if int(sub["id"]) not in include:
                continue
            data = _get_cached(session, cache, f"cat_{sub['id']}", f"categories/{sub['id']}", delay)
            for leaf in data.get("categories", []):
                for listing in leaf.get("products", []):
                    detail = _get_cached(session, cache, f"product_{listing['id']}", f"products/{listing['id']}", delay)
                    p = parse_product(listing, detail, top["name"], sub["name"], sub["id"])
                    # el precio vigente es el del listado (se refresca); el detalle puede ser antiguo
                    lp = listing.get("price_instructions") or {}
                    p.precio_envase = _f(lp.get("unit_price")) or p.precio_envase
                    p.precio_ref = _f(lp.get("reference_price")) or p.precio_ref
                    p.formato_ref = lp.get("reference_format") or p.formato_ref
                    out.append(p)
                    if progress:
                        progress(p)
    return out
