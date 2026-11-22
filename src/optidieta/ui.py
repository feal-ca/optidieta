EDITOR_KEYS = ("portions", "objetivos", "catalogo")


def reset_editors(session_state) -> None:
    """Olvida las ediciones pendientes de las tablas para que no se reapliquen sobre datos nuevos."""
    for k in EDITOR_KEYS:
        if k in session_state:
            del session_state[k]
