from optidieta.state import UserState, apply_edits, load_state, save_state
from optidieta.targets import Profile, default_constraints


def test_state_roundtrip(tmp_path):
    s = UserState(Profile("m", 41, 62.5), "vegana", {"1", "2"}, {"3": 0.25}, {"hierro_mg": {"min": 14.0}}, 400.0)
    f = tmp_path / "e.json"
    save_state(s, f)
    assert load_state(f) == s


def test_state_missing_returns_default(tmp_path):
    s = load_state(tmp_path / "no.json")
    assert s.profile == Profile("h", 30, 70.0) and s.diet == "omnivora" and s.excluded == set()


def test_state_corrupt_returns_default(tmp_path):
    f = tmp_path / "e.json"
    f.write_text("{no es json", encoding="utf-8")
    assert load_state(f) == UserState.default()


def test_apply_edits():
    base = default_constraints(Profile("h", 30))
    out = {c.key: c for c in apply_edits(base, {"vit_b12_ug": {"active": False}, "hierro_mg": {"min": 14}})}
    assert out["vit_b12_ug"].active is False
    assert out["hierro_mg"].min == 14
    assert {c.key: c for c in base}["hierro_mg"].min == 11  # no muta la base
