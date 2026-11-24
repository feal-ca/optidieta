"""Tabla nutricional leída de la foto trasera de Mercadona con Claude Code en modo headless (`claude -p`).

Usa la suscripción con la que esté identificado `claude` en esta máquina, no una clave de API. Cada producto se
lee una vez: la imagen y el resultado quedan en caché en data/raw/etiquetas/.
"""

import json
import subprocess
from pathlib import Path

import requests

from optidieta.fsutil import write_atomic
from optidieta.nutrients import BY_KEY, NUTRIENTS

PERSPECTIVA_TRASERA = 9
MACROS = ["energia_kcal", "grasa_g", "grasa_sat_g", "hidratos_g", "azucares_g", "fibra_g", "proteina_g"]
# Sin EPA+DHA: las etiquetas suelen dar "omega-3" total (incluye ALA vegetal), que no es lo mismo.
MICROS = [n.key for n in NUTRIENTS if n.key not in MACROS and n.key not in ("sodio_mg", "cloruro_mg", "epa_dha_mg")]
_UNIT_FACTOR = {("g", "mg"): 1000, ("g", "µg"): 1e6, ("mg", "µg"): 1000, ("mg", "g"): 1e-3, ("µg", "g"): 1e-6,
                ("µg", "mg"): 1e-3}

SCHEMA = {
    "type": "object",
    "properties": {
        "hay_tabla": {"type": "boolean", "description": "true si la imagen muestra una tabla nutricional legible"},
        "base": {"type": "string", "description": "cantidad de la primera columna: '100 g' o '100 ml'"},
        **{k: {"type": ["number", "null"]} for k in MACROS},
        "sal_g": {"type": ["number", "null"]},
        "otros": {
            "type": "array",
            "description": "vitaminas y minerales que aparezcan en la tabla",
            "items": {"type": "object", "properties": {
                "clave": {"type": "string", "enum": MICROS,
                          "description": "; ".join(f"{k} = {BY_KEY[k].label}" for k in MICROS)},
                "valor": {"type": "number"},
                "unidad": {"type": "string", "enum": ["g", "mg", "µg"]}},
                "required": ["clave", "valor", "unidad"]},
        },
    },
    "required": ["hay_tabla", "base", *MACROS, "sal_g", "otros"],
}

PROMPT = ("Lee la imagen {img}: es la etiqueta trasera de un producto de supermercado. Extrae la tabla de "
          "información nutricional, solo la columna por 100 g o 100 ml (no la de por ración). Usa punto decimal. "
          "Un valor '<0,5 g' cuéntalo como 0,5. Si un dato no aparece, null. Si no hay tabla, hay_tabla=false. "
          "No inventes valores.")
SYSTEM = "Extraes tablas nutricionales de fotos de etiquetas. Usa la herramienta Read para ver la imagen."


def photo_url(detail: dict, size: int = 1600) -> str | None:
    for p in detail.get("photos") or []:
        if p.get("perspective") == PERSPECTIVA_TRASERA and p.get("regular"):
            return p["regular"].replace("h=600&w=600", f"h={size}&w={size}")
    return None


def claude_cmd(image: Path, model: str = "haiku") -> list[str]:
    """Llamada mínima: sin MCP, sin skills ni ajustes del usuario (si no, el contexto cuesta ~90 veces más)."""
    return ["claude", "-p", PROMPT.format(img=image), "--model", model, "--tools", "Read", "--allowedTools", "Read",
            "--add-dir", str(image.parent), "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
            "--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands", "--setting-sources", "",
            "--system-prompt", SYSTEM]


def _run_claude(cmd: list[str]) -> dict:
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180,
                       check=False)
    if r.returncode != 0:
        raise RuntimeError(f"claude salió con {r.returncode}: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


def read_label(pid: str, detail: dict, cache_dir: Path, run=_run_claude, session=None,
               model: str = "haiku") -> dict | None:
    """Devuelve la salida estructurada de la etiqueta (o None si el producto no tiene foto trasera)."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{pid}.json"
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    url = photo_url(detail)
    if url is None:
        return None
    img = cache / f"{pid}.jpg"
    if not img.exists():
        r = (session or requests).get(url, timeout=60)
        r.raise_for_status()
        write_atomic(img, r.content)
    res = run(claude_cmd(img.resolve(), model))
    if res.get("is_error") or "structured_output" not in res:
        raise RuntimeError(f"respuesta sin datos para {pid}: {str(res.get('result'))[:200]}")
    data = {"producto": pid, "modelo": model, "coste_usd": res.get("total_cost_usd"), **res["structured_output"]}
    write_atomic(out, json.dumps(data, ensure_ascii=False))
    return data


def parse_label(d: dict | None) -> dict[str, float]:
    """Valores por 100 g (100 ml se toma como 100 g, igual que con Open Food Facts) en las unidades internas."""
    if not d or not d.get("hay_tabla"):
        return {}
    out: dict[str, float] = {}
    for k in MACROS:
        v = d.get(k)
        if isinstance(v, (int, float)) and v >= 0:
            out[k] = float(v)
    sal = d.get("sal_g")
    if isinstance(sal, (int, float)) and sal >= 0:
        out["sodio_mg"] = float(sal) * 400
    for o in d.get("otros") or []:
        k, v, u = o.get("clave"), o.get("valor"), o.get("unidad")
        if k not in BY_KEY or not isinstance(v, (int, float)) or v < 0:
            continue
        target = BY_KEY[k].unit
        f = 1.0 if u == target else _UNIT_FACTOR.get((u, target))
        if f is not None:
            out[k] = float(v) * f
    return out
