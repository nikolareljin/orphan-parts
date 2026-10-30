"""The photos kept beside an item: from the web form after a save, from a capture when it is
read; served one by one; gone with the item."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.inventory import Inventory
from app.photos import ItemPhotos, PhotoError
from tests.conftest import make_photo


def create(client: TestClient, **spec: Any) -> int:
    res = client.post("/api/items", json=spec)
    assert res.status_code == 201, res.text
    return int(res.json()["id"])


def test_photos_are_kept_after_a_save_and_served_one_by_one(client: TestClient) -> None:
    item_id = create(client, item_type="USB webcam")
    assert client.get(f"/api/items/{item_id}/photos").json() == {"count": 0}
    res = client.post(
        f"/api/items/{item_id}/photos",
        files=[
            ("uploads", ("a.png", make_photo(fmt="PNG"), "image/png")),
            ("uploads", ("b.jpg", make_photo(800, 600), "image/jpeg")),
        ],
    )
    assert res.status_code == 201, res.text
    assert res.json() == {"count": 2}
    assert client.get(f"/api/items/{item_id}/photos").json() == {"count": 2}
    one = client.get(f"/api/items/{item_id}/photos/1")
    assert one.status_code == 200
    assert one.headers["content-type"] == "image/jpeg"
    assert one.content[:2] == b"\xff\xd8", "re-encoded as JPEG, whatever came in"
    assert client.get(f"/api/items/{item_id}/photos/3").status_code == 404
    assert client.get(f"/api/items/{item_id}/photos/0").status_code == 404


def test_the_limit_the_empty_send_and_the_file_that_is_not_an_image(
    client: TestClient, settings: Settings
) -> None:
    item_id = create(client, item_type="USB webcam")
    too_many = [("uploads", (f"{n}.jpg", make_photo(), "image/jpeg")) for n in range(5)]
    res = client.post(f"/api/items/{item_id}/photos", files=too_many)
    assert res.status_code == 422
    assert "at most 4 photos" in res.json()["detail"]
    assert client.get(f"/api/items/{item_id}/photos").json() == {"count": 0}
    res = client.post(
        f"/api/items/{item_id}/photos",
        files=[("uploads", ("x.jpg", b"not an image", "image/jpeg"))],
    )
    assert res.status_code == 400
    assert "not an image" in res.json()["detail"]
    photos = ItemPhotos(settings, Inventory(settings))
    with pytest.raises(PhotoError, match="no photo"):
        photos.add(item_id, [])


def test_an_unknown_item_has_no_photos(client: TestClient) -> None:
    assert client.get("/api/items/999/photos").status_code == 404
    assert client.get("/api/items/999/photos/1").status_code == 404
    res = client.post(
        "/api/items/999/photos", files=[("uploads", ("a.jpg", make_photo(), "image/jpeg"))]
    )
    assert res.status_code == 404


def test_the_photos_go_with_the_item(client: TestClient, settings: Settings) -> None:
    item_id = create(client, item_type="USB webcam")
    client.post(
        f"/api/items/{item_id}/photos", files=[("uploads", ("a.jpg", make_photo(), "image/jpeg"))]
    )
    folder = settings.data_dir / "items" / str(item_id)
    assert (folder / "photo-1.jpg").is_file()
    assert client.delete(f"/api/items/{item_id}").status_code == 204
    assert not folder.exists()
    assert client.get(f"/api/items/{item_id}/photos").status_code == 404
    assert client.get(f"/api/items/{item_id}/photos/1").status_code == 404


def test_the_count_keeps_going_across_sends(settings: Settings) -> None:
    inventory = Inventory(settings)
    from app.inventory import ItemCreate

    item = inventory.create(ItemCreate(item_type="charger"))
    photos = ItemPhotos(settings, inventory)
    assert photos.add(item.id, [make_photo()]) == 1
    assert photos.add(item.id, [make_photo(), make_photo()]) == 3
    with pytest.raises(PhotoError, match="has 3"):
        photos.add(item.id, [make_photo(), make_photo()])
    assert photos.count(item.id) == 3
    assert [p.name for p in sorted((settings.data_dir / "items" / str(item.id)).iterdir())] == [
        "photo-1.jpg",
        "photo-2.jpg",
        "photo-3.jpg",
    ]
