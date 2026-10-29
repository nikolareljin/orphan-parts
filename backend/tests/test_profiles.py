from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.profiles import Profiles, UnknownProfileError


def test_the_shipped_profiles_load_with_their_features() -> None:
    profiles = Profiles()
    assert profiles.ids() == ["generic_item", "power_adapter", "vacuum_attachment"]
    vacuum = profiles.get("vacuum_attachment")
    assert [f.key for f in vacuum.features] == [
        "opening_inner_diameter",
        "opening_outer_diameter",
        "insertion_depth",
        "outer_diameter_at_depth",
        "latch_position",
    ]
    assert vacuum.features[0].tolerance_mm == 0.5
    assert vacuum.features[0].unit == "mm"
    assert "ruler" in vacuum.features[0].how
    assert profiles.feature("vacuum_attachment", "insertion_depth") is not None
    assert profiles.feature("vacuum_attachment", "colour") is None
    assert profiles.feature(None, "width") is None
    with pytest.raises(UnknownProfileError):
        profiles.get("toaster")


def test_rules_load_and_take_the_feature_tolerance_when_they_name_none() -> None:
    profiles = Profiles()
    adapter = profiles.get("power_adapter")
    by_key = {r.key: r for r in adapter.rules}
    assert by_key["part_number"].identity and not by_key["part_number"].hard
    assert by_key["output_voltage"].tolerance_pct == 5 and by_key["output_voltage"].hard
    assert by_key["plug_outer_diameter"].tolerance == 0.1  # from the feature
    assert by_key["plug_outer_diameter"].unit == "mm"
    assert by_key["plug_length"].hard is False
    vacuum = profiles.get("vacuum_attachment")
    assert [r.key for r in vacuum.rules if r.hard] == ["opening_inner_diameter"]
    assert all(not r.hard for r in profiles.get("generic_item").rules)


def test_rule_files_are_checked(tmp_path: Path) -> None:
    def write(rules: str) -> None:
        (tmp_path / "kettle.yaml").write_text(
            "id: kettle\nlabel: Kettle\nfeatures:\n"
            "  - {key: spout, label: Spout, tolerance_mm: 1, how: mark it}\nrules:\n" + rules
        )

    write(
        "  - {key: spout, label: Spout, kind: within}\n"
        "  - {key: spout, label: Again, kind: equal}\n"
    )
    with pytest.raises(ValueError, match="repeats rule 'spout'"):
        Profiles(tmp_path)
    write("  - {key: lid, label: Lid, kind: within}\n")
    with pytest.raises(ValueError, match="within needs a tolerance"):
        Profiles(tmp_path)
    write("  - {key: lid, label: Lid, kind: equal, tolerance: 1}\n")
    with pytest.raises(ValueError, match="equal takes no tolerance"):
        Profiles(tmp_path)
    write("  - {key: lid, label: Lid, kind: equal, tolerance_pct: 0}\n")
    with pytest.raises(ValueError, match="equal takes no tolerance"):
        Profiles(tmp_path)
    write("  - {key: lid, label: Lid, kind: bigger}\n")
    with pytest.raises(ValueError):
        Profiles(tmp_path)
    write("  - {key: spout, label: Spout, kind: within}\n")
    assert Profiles(tmp_path).get("kettle").rules[0].tolerance == 1


def test_a_file_whose_id_does_not_match_its_name_is_refused(tmp_path: Path) -> None:
    (tmp_path / "kettle.yaml").write_text("id: toaster\nlabel: Toaster\nfeatures: []\n")
    with pytest.raises(ValueError, match="file name must match"):
        Profiles(tmp_path)


def test_a_feature_is_measured_in_millimetres(tmp_path: Path) -> None:
    (tmp_path / "kettle.yaml").write_text(
        "id: kettle\nlabel: Kettle\nfeatures:\n"
        "  - {key: spout, label: Spout, unit: cm, tolerance_mm: 1, how: mark it}\n"
    )
    with pytest.raises(ValueError, match="unit"):
        Profiles(tmp_path)


def test_a_feature_needs_a_positive_tolerance(tmp_path: Path) -> None:
    (tmp_path / "kettle.yaml").write_text(
        "id: kettle\nlabel: Kettle\nfeatures:\n"
        "  - {key: spout, label: Spout, tolerance_mm: 0, how: mark it}\n"
    )
    with pytest.raises(ValueError):
        Profiles(tmp_path)


def test_profiles_are_served(client: TestClient) -> None:
    listed = client.get("/api/profiles").json()
    assert [p["id"] for p in listed] == ["generic_item", "power_adapter", "vacuum_attachment"]
    assert listed[2] == {
        "id": "vacuum_attachment",
        "label": "Vacuum attachment",
        "feature_count": 5,
        "rule_count": 6,
    }
    features = client.get("/api/profiles/vacuum_attachment/features").json()
    assert features[0]["key"] == "opening_inner_diameter"
    assert client.get("/api/profiles/vacuum_attachment").json()["label"] == "Vacuum attachment"
    assert client.get("/api/profiles/toaster").status_code == 404
    assert client.get("/api/profiles/toaster/features").status_code == 404
