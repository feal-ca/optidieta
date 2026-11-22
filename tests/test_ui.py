from optidieta.ui import EDITOR_KEYS, reset_editors


def test_reset_editors_clears_widget_state():
    ss = {"portions": {"edited_rows": {2: {"Vetar": True}}}, "objetivos": {}, "catalogo": {}, "state": "keep"}
    reset_editors(ss)
    assert not any(k in ss for k in EDITOR_KEYS)
    assert ss["state"] == "keep"


def test_reset_editors_clears_dynamic_keys():
    from optidieta.ui import editor_key
    k = editor_key("portions", ["1", "2"])
    assert k != editor_key("portions", ["1", "3"])
    ss = {k: {}, "otra": 1}
    reset_editors(ss)
    assert k not in ss and "otra" in ss
