"""Private details kept out of everything shared: the rules over text, the checks on photos,
the shared copies, and the routes that hand photos and text to someone other than the owner."""

import io
import zipfile
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr

from app.config import Settings
from app.inventory.schema import Assertion
from app.main import create_app
from app.model_api import CostLedger, ModelApiClient
from app.ops.door import live_request
from app.ops.gate import demo_allowed, expensive
from app.privacy import (
    NotCheckedError,
    Privacy,
    SensitiveReading,
    find,
    kinds_in,
    luhn,
    mask_text,
    mask_value,
    note_for,
    place,
)
from app.privacy.render import gridded, pixel_box, redacted
from app.privacy.schema import Area, FoundArea, PhotoCheck
from app.privacy.text import private_field
from tests.conftest import RECORDED_FIXTURES, make_photo
from tests.test_gate import CODE, gated_settings

# a made-up label: every value on it is fake (tests/fixtures/fake-sticker.png), and the one
# live recording of the photo check is of this file
STICKER = Path(__file__).parent / "fixtures" / "fake-sticker.png"
# written in parts: a whole one reads as a credential to the secret scanners
FAKE_KEY = "-".join(("ABCDE", "12345", "FGHIJ", "67890", "KLMNO"))
# the IMEI example of the standard, written in parts: whole, it passes for a card number to the
# scanners (it passes the same Luhn check)
IMEI = "49015420" + "3237518"
NOT_IMEI = IMEI[:-1] + "7"
FAKE_MAC = "00:11:22:33:44:55"

# --- the rules over text -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (f"Product Key: {FAKE_KEY}", "product_key"),
        ("key abcde-12345-fghij-67890-klmno on the sticker", "product_key"),
        (f"MAC {FAKE_MAC}", "mac_address"),
        ("00-11-22-33-44-55", "mac_address"),
        ("0011.2233.4455", "mac_address"),
        ("Lan MAC Address: 00 16 D3 2F 74 AE", "mac_address"),
        ("MAC: 001122334455", "mac_address"),
        (f"IMEI {IMEI}", "imei"),
        (f"{IMEI[:2]} {IMEI[2:8]} {IMEI[8:14]} {IMEI[14]}", "imei"),
        ("S/N: FAKE0000TEST1", "serial_number"),
        ("Serial No.: AB12345", "serial_number"),
        ("SN: 13BD18A00682", "serial_number"),
        ("SVC Tag 2ZZZZZ2", "serial_number"),
        ("Password: hunter2", "password"),
        ("PIN: 4821", "password"),
        ("WPA key=correcthorse", "password"),
        ("Wi-Fi password: battery-staple", "password"),
        ("Network key: 8T2Q-PP91", "password"),
    ],
)
def test_each_kind_of_private_value_is_found(text: str, kind: str) -> None:
    assert kinds_in(text) == [kind]


@pytest.mark.parametrize(
    "text",
    [
        "Model: R-100 Input: 12V 1A",
        "ABCDE-ABCDE-ABCDE-ABCDE-ABCDE",  # no digit: a word pattern, not a key
        "ABCDE-12345-FGHIJ-67890",  # four groups
        "00:11:22-33:44:55",  # separators mixed
        NOT_IMEI,  # fails the Luhn check
        "Serial port: COM",  # no digit after the label
        "Memtest pass: 4 passes",
        "PWR: 12V",
        "Part number 41W4721",
        # a listing's own words after a label: a port, a pin count, a rating, a feature
        "Interfaces: USB 3.0, Serial: RS-232, HDMI",
        "PIN: 24-pin ATX connector",
        "Pin: 40 GPIO header",
        "PW: 65W",
        "WPA2: supported",
        "Dell U2415, 1920x1080, made 2019-03-14, $80, part 990010200, 19.5V 3.34A",
    ],
)
def test_ordinary_label_text_is_left_alone(text: str) -> None:
    assert find(text) == []
    assert mask_text(text) == text


def test_luhn() -> None:
    assert luhn(IMEI) and luhn("7992739871" + "3")
    assert not luhn(NOT_IMEI) and not luhn(IMEI.replace("5", "x", 1))


def test_masking_keeps_the_last_four_of_an_identifier_and_nothing_of_a_password() -> None:
    assert mask_value(FAKE_KEY, "product_key") == "•••• LMNO"
    assert mask_value("hunter2", "password") == "••••"
    assert mask_value("correcthorsebattery", "password") == "••••"
    assert mask_value("AB12") == "••••"
    assert mask_value("") == ""
    masked = mask_text(f"Key {FAKE_KEY}, MAC {FAKE_MAC}, Password: hunter2. Model R-100")
    assert masked == "Key •••• LMNO, MAC •••• 4:55, Password: ••••. Model R-100"
    assert FAKE_KEY not in masked and "hunter2" not in masked


def test_field_names_kept_private() -> None:
    assert private_field("serial_number") and private_field("product_key")
    assert private_field("mac") and private_field("wifi_password")
    assert not private_field("machine_type") and not private_field("model_number")


# --- placing the model's boxes -----------------------------------------------------------


def reading(*boxes: tuple[int, int, int, int], kind: str = "serial_number") -> SensitiveReading:
    return SensitiveReading(
        areas=[
            FoundArea(kind=kind, what="w", x_min=a, y_min=b, x_max=c, y_max=d)  # type: ignore[arg-type]
            for a, b, c, d in boxes
        ]
    )


def test_boxes_are_padded_inside_the_photo_and_swapped_corners_put_right() -> None:
    areas, problem = place(reading((500, 400, 100, 300)), 1000, 500)
    assert problem == ""
    (area,) = areas
    assert area.x < 0.1 and area.y < 0.3 and area.x + area.w > 0.5 and area.y + area.h > 0.4
    edge, _ = place(reading((0, 0, 1000, 1000)), 800, 600)
    assert (edge[0].x, edge[0].y, edge[0].w, edge[0].h) == (0, 0, 1, 1)


@pytest.mark.parametrize(
    ("found", "why"),
    [
        (reading((10, 10, 1200, 50)), "off the photo"),
        (reading((-5, 10, 50, 50)), "off the photo"),
        (reading((10, 10, 11, 50)), "no size"),
        (reading(*[(10, 10, 50, 50)] * 25), "more than 24"),
    ],
)
def test_a_box_that_cannot_be_placed_fails_the_whole_check(
    found: SensitiveReading, why: str
) -> None:
    areas, problem = place(found, 640, 480)
    assert areas == [] and why in problem


def test_a_value_the_model_copied_into_its_words_is_masked() -> None:
    found = SensitiveReading(
        areas=[
            FoundArea(
                kind="product_key", what=f"key {FAKE_KEY}", x_min=1, y_min=1, x_max=99, y_max=99
            )
        ]
    )
    areas, _ = place(found, 100, 100)
    assert FAKE_KEY not in areas[0].what and areas[0].label == "product key"


# --- the shared copy -----------------------------------------------------------------------


def exif_jpeg() -> bytes:
    img = Image.new("RGB", (200, 100), (240, 240, 240))
    exif = Image.Exif()
    exif[0x0110] = "SampleCam"
    out = BytesIO()
    img.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_a_hidden_area_is_solid_black_and_the_rest_and_shown_areas_untouched() -> None:
    hidden = Area(id=1, kind="password", label="password or PIN", x=0.1, y=0.2, w=0.3, h=0.4)
    shown = Area(id=2, kind="barcode", label="barcode", x=0.6, y=0.2, w=0.2, h=0.4, hidden=False)
    data = redacted(exif_jpeg(), [hidden, shown])
    assert b"Exif" not in data and b"SampleCam" not in data
    img = Image.open(BytesIO(data)).convert("L")
    left, top, right, bottom = pixel_box(hidden, 200, 100)
    assert max(img.crop((left + 2, top + 2, right - 2, bottom - 2)).getdata()) < 20
    assert min(img.crop((125, 25, 155, 55)).getdata()) > 200  # the area the owner shows
    assert min(img.crop((180, 80, 198, 98)).getdata()) > 200


def test_the_copy_the_model_reads_carries_a_grid_and_the_photo_is_unchanged() -> None:
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    sent = Image.open(BytesIO(gridded(img))).convert("RGB")
    assert sent.size == (400, 300)
    r, g, b = sent.getpixel((40, 150))  # on the first vertical line
    assert r > 150 and b > 150 and g < 200
    assert img.getpixel((40, 150)) == (255, 255, 255)


def test_notes() -> None:
    assert "Not checked" in note_for(None)
    failed = PhotoCheck(digest="d", status="failed", reason="no answer")
    assert "did not finish (no answer)" in note_for(failed)
    assert note_for(PhotoCheck(digest="d", status="clear")) == "Checked: nothing private found."
    areas = [
        Area(id=1, kind="product_key", label="product key", x=0, y=0, w=0.1, h=0.1),
        Area(id=2, kind="mac_address", label="MAC address", x=0, y=0, w=0.1, h=0.1),
        Area(id=3, kind="barcode", label="barcode", x=0, y=0, w=0.1, h=0.1, hidden=False),
    ]
    assert (
        note_for(PhotoCheck(digest="d", status="found", areas=areas))
        == "2 areas hidden: product key, MAC address; 1 shown by the owner: barcode."
    )


# --- the check, recorded and failing -----------------------------------------------------


def sticker_stored(settings: Settings) -> bytes:
    from app.extract.imaging import prepare

    return prepare(STICKER.read_bytes(), max_px=settings.image_max_px, max_bytes=12 << 20)


@pytest.mark.anyio
async def test_the_recorded_check_of_the_fake_sticker_finds_every_kind(
    recorded_settings: Settings,
) -> None:
    client = ModelApiClient(recorded_settings, CostLedger(1.0))
    privacy = Privacy(recorded_settings, client)
    try:
        check = await privacy.check(sticker_stored(recorded_settings))
    finally:
        await client.aclose()
    assert check.status == "found" and check.from_fixture
    assert [a.kind for a in check.areas] == [
        "product_key",
        "mac_address",
        "password",
        "serial_number",
        "barcode",
        "qr_code",
    ]
    assert client.fixture_fallbacks == 0


@pytest.mark.anyio
async def test_a_shared_copy_is_drawn_once_until_its_areas_change(
    recorded_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.privacy import service as service_module

    client = ModelApiClient(recorded_settings, CostLedger(1.0))
    privacy = Privacy(recorded_settings, client)
    photo = sticker_stored(recorded_settings)
    try:
        check = await privacy.check(photo)
    finally:
        await client.aclose()
    drawn: list[int] = []

    def counted(data: bytes, areas: list[Area]) -> bytes:
        drawn.append(len(areas))
        return redacted(data, areas)

    monkeypatch.setattr(service_module, "redacted", counted)
    first = privacy.shared_copy(photo)
    assert privacy.shared_copy(photo) is first and len(drawn) == 1
    privacy.choose(photo, check.areas[0].id, hidden=False)
    assert privacy.shared_copy(photo) != first and len(drawn) == 2


@pytest.mark.anyio
async def test_a_failed_check_is_kept_and_the_photo_is_not_shared(settings: Settings) -> None:
    client = ModelApiClient(settings, CostLedger(1.0))
    privacy = Privacy(settings, client)
    photo = make_photo()
    try:
        check = await privacy.check(photo)
    finally:
        await client.aclose()
    assert check.status == "failed" and "no recorded answer" in check.reason
    with pytest.raises(NotCheckedError):
        privacy.shared_copy(photo)
    assert privacy.shared_or_none(photo) is None
    # the owner may still choose to share it as it is: re-encoded, nothing more
    assert Image.open(BytesIO(privacy.shared_copy(photo, unchecked=True))).size == (640, 480)


def test_the_request_carries_the_grid_copy_and_the_schema(settings: Settings) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        seen.update(body)
        answer = {"areas": []}
        return httpx.Response(
            200,
            json={
                "id": "r",
                "model": body["model"],
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(answer)}],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 10},
            },
        )

    live = settings.model_copy(update={"fake_api": False, "model_api_key": SecretStr("k" * 20)})
    client = ModelApiClient(live, CostLedger(1.0), transport=httpx.MockTransport(handler))
    privacy = Privacy(live, client)

    async def run() -> PhotoCheck:
        try:
            return await privacy.check(make_photo())
        finally:
            await client.aclose()

    import anyio

    check = anyio.run(run)
    assert check.status == "clear" and check.cost_usd > 0
    assert seen["text"]["format"]["name"] == "SensitiveReading"  # type: ignore[index]
    assert "magenta grid" in str(seen["instructions"])
    parts = seen["input"][0]["content"]  # type: ignore[index]
    assert [p["type"] for p in parts] == ["input_text", "input_image"]
    # kept: asked again, nothing is sent
    seen.clear()
    assert privacy.kept(make_photo()) is not None


# --- the routes --------------------------------------------------------------------------


def sticker_upload() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("uploads", ("sticker.png", STICKER.read_bytes(), "image/png"))]


def is_black(jpeg: bytes, area: dict[str, float]) -> bool:
    img = Image.open(BytesIO(jpeg)).convert("L")
    w, h = img.size
    cx, cy = (area["x"] + area["w"] / 2) * w, (area["y"] + area["h"] / 2) * h
    return max(img.crop((int(cx) - 3, int(cy) - 3, int(cx) + 3, int(cy) + 3)).getdata()) < 25


def test_an_uploaded_photo_is_checked_and_its_shared_copy_blacked_out(
    recorded_client: TestClient,
) -> None:
    c = recorded_client
    item = c.post("/api/items", json={"item_type": "router", "name": "Router"}).json()["id"]
    res = c.post(f"/api/items/{item}/photos", files=sticker_upload())
    assert res.status_code == 201, res.text
    (photo,) = res.json()["photos"]
    assert photo["status"] == "found" and photo["shared"] is True
    assert photo["note"] == (
        "6 areas hidden: product key, MAC address, password or PIN, serial number, barcode,"
        " QR code."
    )
    key = photo["areas"][0]
    first = c.get(f"/api/items/{item}/photos/1")
    original = first.content
    assert first.headers["cache-control"] == "no-store"  # the owner's original is never kept
    served = c.get(f"/api/items/{item}/photos/1", params={"copy": "shared"})
    shared = served.content
    assert not is_black(original, key) and is_black(shared, key)
    assert served.headers["cache-control"] == "no-store"  # the owner's view is never kept
    # shown by the owner: that area is no longer black on the shared copy
    chosen = c.patch(f"/api/items/{item}/photos/1/areas/{key['id']}", json={"hidden": False})
    assert (
        chosen.status_code == 200 and "1 shown by the owner: product key" in chosen.json()["note"]
    )
    assert not is_black(
        c.get(f"/api/items/{item}/photos/1", params={"copy": "shared"}).content, key
    )
    # hidden again: black again (the copy drawn before is the right one again)
    assert (
        c.patch(f"/api/items/{item}/photos/1/areas/{key['id']}", json={"hidden": True}).status_code
        == 200
    )
    assert is_black(c.get(f"/api/items/{item}/photos/1", params={"copy": "shared"}).content, key)
    assert c.patch(f"/api/items/{item}/photos/1/areas/99", json={"hidden": True}).status_code == 404
    # the zip carries the shared copy
    draft = c.post(f"/api/items/{item}/drafts", json={"mode": "sell"})
    assert draft.status_code == 201, draft.text
    zipped = c.get(f"/api/drafts/{draft.json()['id']}/photos.zip")
    assert zipped.status_code == 200
    (name,) = zipfile.ZipFile(io.BytesIO(zipped.content)).namelist()
    entry = zipfile.ZipFile(io.BytesIO(zipped.content)).read(name)
    assert entry != original and is_black(entry, photo["areas"][1])


def test_a_photo_without_a_check_is_kept_but_not_shared(recorded_client: TestClient) -> None:
    c = recorded_client
    item = c.post("/api/items", json={"item_type": "router"}).json()["id"]
    sent = [("uploads", ("a.jpg", make_photo(), "image/jpeg"))]
    (photo,) = c.post(f"/api/items/{item}/photos", files=sent).json()["photos"]
    assert photo["status"] == "failed" and photo["shared"] is False
    assert "kept out of anything shared" in photo["note"]
    assert c.get(f"/api/items/{item}/photos/1").status_code == 200
    refused = c.get(f"/api/items/{item}/photos/1", params={"copy": "shared"})
    assert refused.status_code == 409
    # checking again asks once more, and still has no recording to answer with
    again = c.post(f"/api/items/{item}/photos/check")
    assert again.status_code == 200 and again.json()["photos"][0]["status"] == "failed"
    draft = c.post(f"/api/items/{item}/drafts", json={"mode": "sell"}).json()
    assert c.get(f"/api/drafts/{draft['id']}/photos.zip").status_code == 409


def test_the_visitor_gets_shared_copies_masked_values_and_no_unchecked_photo(
    tmp_path: Path,
) -> None:
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES)
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        item = c.post("/api/items", json={"item_type": "router", "name": "Router"}).json()["id"]
        (photo,) = c.post(f"/api/items/{item}/photos", files=sticker_upload()).json()["photos"]
        sent = [("uploads", ("a.jpg", make_photo(), "image/jpeg"))]
        assert c.post(f"/api/items/{item}/photos", files=sent).status_code == 201
        for field, value in (("serial_number", "FAKE0000TEST1"), ("notes_label", FAKE_KEY)):
            assert c.post(
                f"/api/items/{item}/fields", json={"field": field, "value": value}
            ).status_code in (200, 201)
        version = c.get(f"/api/items/{item}").json()["version"]
        patched = c.patch(
            f"/api/items/{item}", json={"faults": "Password: hunter2", "version": version}
        )
        assert patched.status_code == 200, patched.text
        owner = c.get(f"/api/items/{item}").json()
        assert owner["fields"]["serial_number"]["value"] == "FAKE0000TEST1"
        original = c.get(f"/api/items/{item}/photos/1").content
        c.post(f"/api/items/{item}/public", json={"public": True})
        c.cookies.clear()

        seen = c.get(f"/api/items/{item}")
        assert seen.status_code == 200
        body = seen.text
        assert "FAKE0000TEST1" not in body and FAKE_KEY not in body and "hunter2" not in body
        assert seen.json()["fields"]["serial_number"]["value"] == "•••• EST1"
        listed = c.get(f"/api/items/{item}/photos").json()
        assert [p["shared"] for p in listed["photos"]] == [True, False]
        # whatever is asked for, the visitor gets the shared copy, and none of the unchecked
        for params in ({}, {"copy": "original"}):
            got = c.get(f"/api/items/{item}/photos/1", params=params)
            assert got.status_code == 200 and got.content != original
            assert is_black(got.content, photo["areas"][0])
        assert c.get(f"/api/items/{item}/photos/2").status_code == 404
        # the visitor's browser keeps the shared copy and asks again: unchanged, a 304
        first = c.get(f"/api/items/{item}/photos/1")
        tag = first.headers["etag"]
        assert first.headers["cache-control"] == "private, no-cache"
        again = c.get(f"/api/items/{item}/photos/1", headers={"If-None-Match": tag})
        assert again.status_code == 304 and again.content == b""
        # the live calls and the owner's choices are refused
        assert c.post(f"/api/items/{item}/photos/check").status_code == 403
        assert (
            c.patch(f"/api/items/{item}/photos/1/areas/1", json={"hidden": False}).status_code
            == 403
        )
        # made private again: the tag the visitor kept opens nothing
        c.post("/api/access", json={"code": CODE})
        c.post(f"/api/items/{item}/public", json={"public": False})
        c.cookies.clear()
        gone = c.get(f"/api/items/{item}/photos/1", headers={"If-None-Match": tag})
        assert gone.status_code == 404


def test_the_routes_that_check_spend_and_the_visitor_has_neither() -> None:
    assert expensive("POST", "/api/items/1/photos/check")
    # keeping photos is free; the checks it makes are counted in the route (spend_now)
    assert not expensive("POST", "/api/items/1/photos")
    for path in ("/api/items/1/photos", "/api/items/1/photos/check"):
        assert not demo_allowed("POST", path)
    assert not demo_allowed("PATCH", "/api/items/1/photos/1/areas/1")
    assert demo_allowed("GET", "/api/items/1/photos/1")


def test_a_visitor_reading_has_its_label_text_masked() -> None:
    from app.extract.schema import Evidence, Extraction

    reading = Extraction(
        item_type="router",
        label_text=f"Model R-100\nMAC {FAKE_MAC}",
        fields={
            "part_number": Evidence(value=FAKE_KEY, confidence=0.9, source="photo", raw=FAKE_KEY)
        },
        warnings=[],
        photos=1,
        model="m",
        from_fixture=True,
        cost_usd=0,
    )
    assert FAKE_MAC in reading.model_dump_json()
    token = live_request.set(False)
    try:
        shown = reading.model_dump_json()
    finally:
        live_request.reset(token)
    assert FAKE_MAC not in shown and FAKE_KEY not in shown and "Model R-100" in shown


def test_the_owner_assertion_is_untouched_and_a_text_value_masked_for_the_visitor() -> None:
    from app.inventory.schema import shown_assertion

    a = Assertion(
        id=1,
        field="wifi_note",
        value=f"WPA key=hunter22 on the {FAKE_MAC} box",
        provenance="owner_reported",
        confidence=1,
        source="user_edit",
        review="accepted",
        at="2026-11-03",
    )
    shown = shown_assertion(a)
    assert "hunter22" not in shown.value and FAKE_MAC not in shown.value
    assert a.value.startswith("WPA key=hunter22")


def test_the_pack_and_share_text_mask_what_the_owner_typed() -> None:
    from app.projects.pack import mask_text as pack_mask

    assert pack_mask(f"Configuration: login Password: hunter2 on {FAKE_MAC}") == (
        "Configuration: login Password: •••• on •••• 4:55"
    )


@pytest.mark.anyio
async def test_a_check_run_again_that_fails_leaves_the_finished_one(
    recorded_settings: Settings, settings: Settings
) -> None:
    photo = sticker_stored(recorded_settings)
    client = ModelApiClient(recorded_settings, CostLedger(1.0))
    try:
        found = await Privacy(recorded_settings, client).check(photo)
    finally:
        await client.aclose()
    # the same store, and no recording to answer the second time
    again = settings.model_copy(update={"data_dir": recorded_settings.data_dir})
    client = ModelApiClient(again, CostLedger(1.0))
    privacy = Privacy(again, client)
    try:
        assert (await privacy.check(photo, again=True)).status == "found"
    finally:
        await client.aclose()
    assert privacy.kept(photo) == found


@pytest.mark.anyio
async def test_an_operations_stub_never_answers_a_photo_check(
    recorded_settings: Settings, settings: Settings
) -> None:
    # a stub named after the operation that says "nothing private": it must not clear a photo
    # nobody checked
    clear = RECORDED_FIXTURES / "responses" / "061eab9774f08aa576ee39ad.json"
    stubs = settings.fixtures_dir / "responses"
    stubs.mkdir(parents=True)
    (stubs / "find-sensitive.json").write_bytes(clear.read_bytes())
    client = ModelApiClient(settings, CostLedger(1.0))
    privacy = Privacy(settings, client)
    photo = make_photo()
    try:
        check = await privacy.check(photo)
    finally:
        await client.aclose()
    assert check.status == "failed" and "no recorded answer" in check.reason
    assert privacy.shared_or_none(photo) is None


def test_the_same_photo_twice_is_one_check(recorded_client: TestClient) -> None:
    c = recorded_client
    item = c.post("/api/items", json={"item_type": "router"}).json()["id"]
    twice = sticker_upload() + sticker_upload()
    res = c.post(f"/api/items/{item}/photos", files=twice)
    assert res.status_code == 201, res.text
    assert [p["status"] for p in res.json()["photos"]] == ["found", "found"]


def test_photos_are_kept_while_paused_and_not_shared_until_checked(tmp_path: Path) -> None:
    settings = gated_settings(tmp_path, fixtures_dir=RECORDED_FIXTURES, demo_paused=True)
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        item = c.post("/api/items", json={"item_type": "router"}).json()["id"]
        res = c.post(f"/api/items/{item}/photos", files=sticker_upload())
        assert res.status_code == 201, res.text
        (photo,) = res.json()["photos"]
        assert photo["status"] == "failed" and photo["shared"] is False
        assert "paused by the operator" in photo["note"]
        assert c.get(f"/api/items/{item}/photos/1").status_code == 200  # the owner's original
        assert c.get(f"/api/items/{item}/photos/1", params={"copy": "shared"}).status_code == 409
        assert c.post(f"/api/items/{item}/photos/check").status_code == 503
        assert c.get("/readyz").json()["demo"]["daily_used"] == 0


def test_each_photo_checked_is_counted(tmp_path: Path) -> None:
    settings = gated_settings(
        tmp_path, fixtures_dir=RECORDED_FIXTURES, demo_visitor_calls_per_hour=3
    )
    with TestClient(create_app(settings)) as c:
        c.post("/api/access", json={"code": CODE})
        item = c.post("/api/items", json={"item_type": "router"}).json()["id"]
        two = [("uploads", (f"{n}.jpg", make_photo(320 + n, 240), "image/jpeg")) for n in (1, 2)]
        assert c.post(f"/api/items/{item}/photos", files=two).status_code == 201
        assert c.get("/readyz").json()["demo"]["daily_used"] == 2
        # two more calls asked, one left in the hour: refused before any call, photos kept
        refused = c.post(f"/api/items/{item}/photos/check")
        assert refused.status_code == 429 and "hourly allowance" in refused.json()["detail"]
        assert c.get("/readyz").json()["demo"]["daily_used"] == 2
        one = [("uploads", ("3.jpg", make_photo(400, 300), "image/jpeg"))]
        kept = c.post(f"/api/items/{item}/photos", files=one)
        assert kept.status_code == 201 and kept.json()["count"] == 3
        assert c.get("/readyz").json()["demo"]["daily_used"] == 3
        # the hour is used: the next photo is kept, its check refused and said
        four = [("uploads", ("4.jpg", make_photo(420, 300), "image/jpeg"))]
        last = c.post(f"/api/items/{item}/photos", files=four)
        assert last.status_code == 201
        assert "hourly allowance" in last.json()["photos"][3]["note"]
