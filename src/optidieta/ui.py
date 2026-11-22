import hashlib

EDITOR_KEYS = ("portions", "objetivos", "catalogo")


def editor_key(base: str, ids) -> str:
    """Clave de widget que cambia cuando cambian las filas: el navegador no reaplica ediciones viejas."""
    return base + "_" + hashlib.sha1("|".join(map(str, ids)).encode()).hexdigest()[:10]


def reset_editors(session_state) -> None:
    """Olvida las ediciones pendientes de las tablas para que no se reapliquen sobre datos nuevos."""
    for k in list(session_state.keys()):
        if any(k == b or k.startswith(b + "_") for b in EDITOR_KEYS):
            del session_state[k]
