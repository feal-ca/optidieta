"""BEDCA: descarga (con caché), parseo y limpieza de la composición de alimentos."""

import math
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import requests

from optidieta.fsutil import write_atomic
from optidieta.nutrients import NUTRIENTS, col, known_col
from optidieta.textutil import norm

URL = "https://www.bedca.net/bdpub/procquery.php"
HEADERS = {"Content-Type": "text/xml", "User-Agent": "optidieta/0.1"}

_LIST_Q = (
    '<?xml version="1.0" encoding="utf-8"?><foodquery><type level="1"/><selection>'
    '<atribute name="f_id"/><atribute name="f_ori_name"/></selection>'
    '<order ordtype="ASC"><atribute3 name="f_id"/></order></foodquery>'
)
_FOOD_Q = (
    '<?xml version="1.0" encoding="utf-8"?><foodquery><type level="2"/><selection>'
    '<atribute name="f_id"/><atribute name="f_ori_name"/><atribute name="edible_portion"/>'
    '<atribute name="c_id"/><atribute name="c_ori_name"/><atribute name="best_location"/>'
    '<atribute name="v_unit"/></selection><condition><cond1><atribute1 name="f_id"/></cond1>'
    '<relation type="EQUAL"/><cond3>{}</cond3></condition></foodquery>'
)

_BY_ID = {i: n for n in NUTRIENTS for i in n.bedca_ids}
_BY_NAME = {name: n for n in NUTRIENTS for name in n.bedca_names}


@dataclass
class BedcaFood:
    f_id: int
    nombre: str
    porcion_comestible: float | None
    valores: dict[str, float | None]
    sin_mapear: list[str] = field(default_factory=list)


def _post(session, body: str, timeout: float = 60) -> str:
    r = (session or requests).post(URL, data=body.encode("utf-8"), headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.content.decode("utf-8")


def fetch_food_list(cache_dir: Path, session=None) -> list[tuple[int, str]]:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "list.xml"
    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = _post(session, _LIST_Q)
        write_atomic(path, text)
    seen: dict[int, str] = {}
    for food in ET.fromstring(text).iter("food"):
        fid = int(food.findtext("f_id"))
        seen.setdefault(fid, (food.findtext("f_ori_name") or "").strip())
    return list(seen.items())


def fetch_food(f_id: int, cache_dir: Path, session=None, delay: float = 0.0) -> str:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"f_{f_id}.xml"
    if path.exists():
        return path.read_text(encoding="utf-8")
    text = _post(session, _FOOD_Q.format(int(f_id)))
    write_atomic(path, text)
    if delay:
        time.sleep(delay)
    return text


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip().replace(",", ".")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def parse_food(xml: str) -> BedcaFood | None:
    """None si BEDCA devuelve el alimento vacío (pasa con algunos ids de la lista)."""
    root = ET.fromstring(xml)
    food = root.find("food")
    if food is None or not (food.findtext("f_id") or "").strip():
        return None
    valores: dict[str, float | None] = {n.key: None for n in NUTRIENTS}
    sin_mapear: list[str] = []
    for fv in food.iter("foodvalue"):
        name = (fv.findtext("c_ori_name") or "").strip()
        cid = fv.findtext("c_id")
        nut = _BY_ID.get(int(cid)) if cid and cid.strip().isdigit() else None
        nut = nut or _BY_NAME.get(norm(name))
        if nut is None:
            sin_mapear.append(name)
            continue
        v = _num(fv.findtext("best_location"))
        unit = (fv.findtext("v_unit") or "").strip()
        # cobre llega como "ug" con valores que son mg (error conocido de BEDCA): se toma tal cual en mg
        if v is not None:
            if nut.key == "energia_kcal" and unit.lower() == "kj":
                v = v / 4.184
            v *= nut.bedca_factor
        if nut.bedca_sum and v is not None and valores.get(nut.key) is not None:
            valores[nut.key] += v
        elif valores.get(nut.key) is None:
            valores[nut.key] = v

    if valores["energia_kcal"] is None:
        p, c, g = valores["proteina_g"], valores["hidratos_g"], valores["grasa_g"]
        if None not in (p, c, g):
            valores["energia_kcal"] = 4 * p + 4 * c + 9 * g + 2 * (valores["fibra_g"] or 0.0)

    return BedcaFood(
        f_id=int(food.findtext("f_id")),
        nombre=(food.findtext("f_ori_name") or "").strip(),
        porcion_comestible=_num(food.findtext("edible_portion")),
        valores=valores,
        sin_mapear=sin_mapear,
    )


def foods_frame(foods: list[BedcaFood]) -> pd.DataFrame:
    rows = []
    for f in foods:
        row = {"bedca_id": f.f_id, "bedca_nombre": f.nombre, "porcion_comestible": f.porcion_comestible}
        for n in NUTRIENTS:
            v = f.valores.get(n.key)
            row[col(n.key)] = float("nan") if v is None else float(v)
            row[known_col(n.key)] = v is not None
        rows.append(row)
    return pd.DataFrame(rows)
