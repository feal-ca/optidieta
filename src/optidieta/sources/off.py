"""Open Food Facts: tabla nutricional de la etiqueta, buscada por EAN, con caché."""

import json
import math
import time
from pathlib import Path

import requests

from optidieta.fsutil import write_atomic
from optidieta.nutrients import NUTRIENTS

URL = "https://world.openfoodfacts.org/api/v2/product/{}.json"
HEADERS = {"User-Agent": "optidieta/0.1"}
FIELDS = "product_name,nutriments"


def fetch_label(ean: str, cache_dir: Path, session=None, delay: float = 1.0, retries: int = 6) -> dict | None:
    if not ean:
        return None
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{ean}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    s = session or requests
    for attempt in range(retries + 1):
        wait = min(60.0, 2 * delay * 2 ** attempt)
        try:
            r = s.get(URL.format(ean), params={"fields": FIELDS}, headers=HEADERS, timeout=30)
        except (requests.Timeout, requests.ConnectionError):
            if attempt == retries:
                raise
            time.sleep(wait)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == retries:
                r.raise_for_status()
            time.sleep(wait)
            continue
        break
    if r.status_code not in (200, 404):
        r.raise_for_status()
    try:
        data = r.json()
    except ValueError:
        data = {"status": 0}
    write_atomic(f, json.dumps(data, ensure_ascii=False))
    if delay:
        time.sleep(delay)
    return data


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x >= 0 else None


def parse_label(resp: dict | None) -> dict[str, float]:
    if not resp or resp.get("status") != 1:
        return {}
    nut = (resp.get("product") or {}).get("nutriments") or {}
    out: dict[str, float] = {}
    for n in NUTRIENTS:
        if not n.off_field:
            continue
        v = _num(nut.get(n.off_field))
        if v is not None:
            out[n.key] = v * n.off_factor
    if "sodio_mg" not in out:
        salt = _num(nut.get("salt_100g"))
        if salt is not None:
            out["sodio_mg"] = salt * 400
    return out


def label_is_plausible(vals: dict[str, float]) -> bool:
    need = ("energia_kcal", "proteina_g", "hidratos_g", "grasa_g")
    if any(k not in vals for k in need):
        return True
    est = 4 * vals["proteina_g"] + 4 * vals["hidratos_g"] + 9 * vals["grasa_g"] + 2 * vals.get("fibra_g", 0.0)
    return abs(vals["energia_kcal"] - est) <= 0.20 * max(vals["energia_kcal"], 1)
