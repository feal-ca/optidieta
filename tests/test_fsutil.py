from optidieta.fsutil import write_atomic


def test_write_atomic_text_and_bytes(tmp_path):
    write_atomic(tmp_path / "1.json", "{}")
    write_atomic(tmp_path / "1.jpg", b"\xff\xd8")
    assert (tmp_path / "1.json").read_text(encoding="utf-8") == "{}"
    assert (tmp_path / "1.jpg").read_bytes() == b"\xff\xd8"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["1.jpg", "1.json"]  # sin temporales
