"""optidieta fetch | propose | build | census"""

import argparse
import collections
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import requests

from optidieta.catalog import build_catalog
from optidieta.mapping import merge, propose, read_mapping, write_mapping
from optidieta.sources import bedca, mercadona, off

ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return Path(os.environ.get("OPTIDIETA_DATA", ROOT / "data"))


def paths() -> dict[str, Path]:
    d = data_dir()
    return {
        "data": d, "raw": d / "raw", "merca": d / "raw" / "mercadona", "bedca": d / "raw" / "bedca",
        "off": d / "raw" / "off", "products": d / "raw" / "products.json", "bedca_frame": d / "raw" / "bedca.parquet",
        "mapping": d / "mapping.csv", "catalog": d / "catalog.parquet",
        "subcats": ROOT / "config" / "subcategorias.toml",
    }


def load_products(p) -> list[mercadona.MercaProduct]:
    return [mercadona.MercaProduct(**d) for d in json.loads(p["products"].read_text(encoding="utf-8"))]


def _progress(label):
    n = [0]

    def f(*_):
        n[0] += 1
        if n[0] % 50 == 0:
            print(f"  {label}: {n[0]}", flush=True)
    return f


def cmd_fetch(args) -> None:
    p = paths()
    s = requests.Session()
    if args.refresh:
        mercadona.clear_listings(p["merca"])
    print("Mercadona…", flush=True)
    prods = mercadona.fetch_all(p["merca"], mercadona.load_included(p["subcats"]), session=s, delay=args.delay,
                                progress=_progress("productos"))
    p["products"].parent.mkdir(parents=True, exist_ok=True)
    p["products"].write_text(json.dumps([asdict(x) for x in prods], ensure_ascii=False), encoding="utf-8")
    print(f"  {len(prods)} productos")

    print("BEDCA…", flush=True)
    lst = bedca.fetch_food_list(p["bedca"], session=s)
    foods, tick = [], _progress("alimentos BEDCA")
    for fid, _ in lst:
        f = bedca.parse_food(bedca.fetch_food(fid, p["bedca"], session=s, delay=args.delay / 3))
        if f is not None:
            foods.append(f)
        tick()
    bedca.foods_frame(foods).to_parquet(p["bedca_frame"])
    print(f"  {len(foods)} alimentos")

    print("Open Food Facts…", flush=True)
    tick = _progress("etiquetas")
    for x in prods:
        off.fetch_label(x.ean, p["off"], session=s, delay=args.delay * 1.5)
        tick()
    print("Hecho.")


def cmd_propose(args) -> None:
    p = paths()
    prods = load_products(p)
    proposed = propose(prods, pd.read_parquet(p["bedca_frame"]))
    out = merge(read_mapping(p["mapping"]), proposed)
    write_mapping(out, p["mapping"])
    print(f"{p['mapping']}: {len(out)} filas, {(out.revisado == 'sí').sum()} revisadas")


def labels_for(prods, off_dir: Path) -> dict[str, dict[str, float]]:
    out = {}
    for x in prods:
        f = off_dir / f"{x.ean}.json"
        if x.ean and f.exists():
            out[str(x.id)] = off.parse_label(json.loads(f.read_text(encoding="utf-8")))
    return out


def cmd_build(args) -> None:
    p = paths()
    prods = load_products(p)
    cat, rep = build_catalog(prods, pd.read_parquet(p["bedca_frame"]), read_mapping(p["mapping"]),
                             labels_for(prods, p["off"]))
    cat.to_parquet(p["catalog"])
    print(rep.texto())
    print(f"→ {p['catalog']}")


def cmd_census(args) -> None:
    p = paths()
    c = collections.Counter()
    for f in p["bedca"].glob("f_*.xml"):
        food = bedca.parse_food(f.read_text(encoding="utf-8"))
        if food is not None:
            c.update(food.sin_mapear)
    for name, n in c.most_common():
        print(f"{n:5d}  {name}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="optidieta")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="descarga Mercadona, BEDCA y Open Food Facts (con caché)")
    f.add_argument("--refresh", action="store_true", help="vuelve a bajar listados y precios de Mercadona")
    f.add_argument("--delay", type=float, default=1.0)
    f.set_defaults(fn=cmd_fetch)
    sub.add_parser("propose", help="propone emparejamientos en data/mapping.csv").set_defaults(fn=cmd_propose)
    sub.add_parser("build", help="construye data/catalog.parquet").set_defaults(fn=cmd_build)
    sub.add_parser("census", help="componentes BEDCA sin mapear").set_defaults(fn=cmd_census)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
