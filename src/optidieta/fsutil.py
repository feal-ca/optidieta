"""Escritura atómica: un corte a mitad no deja en la caché un archivo truncado que luego se lea como bueno."""

from pathlib import Path


def write_atomic(path: Path, data: str | bytes) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")  # por nombre completo: 1.json y 1.jpg no comparten temporal
    if isinstance(data, bytes):
        tmp.write_bytes(data)
    else:
        tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)
