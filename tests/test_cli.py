import requests

from optidieta import cli


def test_off_stage_stops_gracefully(monkeypatch, capsys):
    calls = []

    def limited(ean, *a, **k):
        calls.append(ean)
        raise requests.HTTPError("429 Too Many Requests")

    monkeypatch.setattr(cli.off, "fetch_label", limited)
    n = cli.fetch_labels([type("P", (), {"ean": e})() for e in ("1", "2", "3")], None, None, 0)
    assert n == 0 and calls == ["1"]
    assert "Open Food Facts" in capsys.readouterr().out
