import json
from pathlib import Path

import pytest
import requests

from optidieta.sources.mercadona import fetch_all, load_included, parse_product

FIX = Path(__file__).parent / "fixtures"
CATS = json.loads((FIX / "merca_categories.json").read_text(encoding="utf-8"))
CAT120 = json.loads((FIX / "merca_cat_120.json").read_text(encoding="utf-8"))
PROD = json.loads((FIX / "merca_product_13577.json").read_text(encoding="utf-8"))
N_PRODUCTS = sum(len(s["products"]) for s in CAT120["categories"])


class FakeResp:
    def __init__(self, data):
        self.data = data
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    """Devuelve las fixtures según la URL. `fail_on` = nº de llamada de detalle que falla."""

    def __init__(self, fail_on=None):
        self.urls = []
        self.detail_calls = 0
        self.fail_on = fail_on

    def get(self, url, **k):
        self.urls.append(url)
        path = url.split("/api/")[1].split("?")[0].strip("/")
        if path == "categories":
            return FakeResp(CATS)
        if path.startswith("categories/"):
            cid = int(path.split("/")[1])
            if cid == 120:
                return FakeResp(CAT120)
            return FakeResp({"id": cid, "name": "otra", "categories": []})
        if path.startswith("products/"):
            self.detail_calls += 1
            if self.fail_on and self.detail_calls >= self.fail_on:  # red caída a partir de aquí
                raise requests.ConnectionError("red caída")
            pid = path.split("/")[1]
            return FakeResp(dict(PROD, id=pid))
        raise AssertionError(url)


def _listing():
    return CAT120["categories"][0]["products"][0]


def test_parse_product():
    p = parse_product(_listing(), PROD, "Arroz, legumbres y pasta", "Pasta y fideos", 120)
    assert p.id == "13577"
    assert p.ean == PROD["ean"]
    assert p.precio_ref == 1.7
    assert p.precio_envase == 0.85
    assert p.formato_ref == "kg"
    assert "Sémola de trigo" in p.ingredientes
    assert "<strong>" not in p.ingredientes and "<strong>" not in p.alergenos
    assert p.url.startswith("https://tienda.mercadona.es/product/13577")
    assert p.peso_variable is False


def test_only_included_subcategories(tmp_path):
    s = FakeSession()
    prods = fetch_all(tmp_path, include={120}, session=s, delay=0)
    assert len(prods) == N_PRODUCTS
    assert all(p.subcategoria_id == 120 for p in prods)
    assert all(p.categoria == "Arroz, legumbres y pasta" for p in prods)
    assert not any("categories/118" in u for u in s.urls)


def test_fetch_resumes_from_cache(tmp_path):
    bad = FakeSession(fail_on=2)
    with pytest.raises(requests.ConnectionError):
        fetch_all(tmp_path, include={120}, session=bad, delay=0)
    good = FakeSession()
    prods = fetch_all(tmp_path, include={120}, session=good, delay=0)
    assert len(prods) == N_PRODUCTS
    assert good.detail_calls == N_PRODUCTS - 1  # el primero ya estaba en caché
    again = FakeSession()
    fetch_all(tmp_path, include={120}, session=again, delay=0)
    assert again.urls == []


def test_load_included(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text("include = [120, 121] # pasta, legumbres\n", encoding="utf-8")
    assert load_included(f) == {120, 121}


class StatusSession(FakeSession):
    """El detalle del producto `bad` responde con los códigos de `codes` (y luego 200)."""

    def __init__(self, bad, codes):
        super().__init__()
        self.bad, self.codes = bad, list(codes)

    def get(self, url, **k):
        if f"products/{self.bad}/" in url and self.codes:
            self.urls.append(url)
            code = self.codes.pop(0)
            r = FakeResp({"detail": "x"})
            r.status_code = code

            def rfs():
                raise requests.HTTPError(str(code), response=r)
            r.raise_for_status = rfs
            return r
        r = super().get(url, **k)
        r.status_code = 200
        return r


def test_delisted_product_skipped_and_remembered(tmp_path):
    first = CAT120["categories"][0]["products"][1]["id"]
    s = StatusSession(first, [404])
    prods = fetch_all(tmp_path, include={120}, session=s, delay=0)
    assert len(prods) == N_PRODUCTS - 1
    again = FakeSession()
    fetch_all(tmp_path, include={120}, session=again, delay=0)
    assert again.urls == []


def test_transient_errors_retried(tmp_path):
    first = CAT120["categories"][0]["products"][1]["id"]
    s = StatusSession(first, [503, 429])
    prods = fetch_all(tmp_path, include={120}, session=s, delay=0)
    assert len(prods) == N_PRODUCTS


class TimeoutOnce(FakeSession):
    def __init__(self):
        super().__init__()
        self.raised = False

    def get(self, url, **k):
        if "products/" in url and not self.raised:
            self.raised = True
            raise requests.ReadTimeout("lento")
        r = super().get(url, **k)
        r.status_code = 200
        return r


def test_timeouts_retried(tmp_path):
    prods = fetch_all(tmp_path, include={120}, session=TimeoutOnce(), delay=0)
    assert len(prods) == N_PRODUCTS
