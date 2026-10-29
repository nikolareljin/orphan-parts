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


def test_a_file_whose_id_does_not_match_its_name_is_refused(tmp_path: Path) -> None:
    (tmp_path / "kettle.yaml").write_text("id: toaster\nlabel: Toaster\nfeatures: []\n")
    with pytest.raises(ValueError, match="file name must match"):
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
    }
    features = client.get("/api/profiles/vacuum_attachment/features").json()
    assert features[0]["key"] == "opening_inner_diameter"
    assert client.get("/api/profiles/vacuum_attachment").json()["label"] == "Vacuum attachment"
    assert client.get("/api/profiles/toaster").status_code == 404
    assert client.get("/api/profiles/toaster/features").status_code == 404
