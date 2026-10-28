import base64
from pathlib import Path

from app.model_api.fixtures import FixtureStore, request_key


def body_with_image(payload: bytes, prompt: str = "read the label") -> dict[str, object]:
    data = base64.b64encode(payload).decode("ascii")
    return {
        "model": "muse-spark-1.3",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{data}"},
                ],
            }
        ],
    }


def test_key_ignores_field_order_but_not_content() -> None:
    a = request_key("/responses", {"model": "m", "input": "x", "store": False})
    b = request_key("/responses", {"store": False, "input": "x", "model": "m"})
    c = request_key("/responses", {"model": "m", "input": "y", "store": False})
    assert a == b
    assert a != c
    assert request_key("/other", {"model": "m", "input": "x", "store": False}) != a


def test_same_image_bytes_give_the_same_key() -> None:
    assert request_key("/responses", body_with_image(b"abc")) == request_key(
        "/responses", body_with_image(b"abc")
    )
    assert request_key("/responses", body_with_image(b"abc")) != request_key(
        "/responses", body_with_image(b"abd")
    )


def test_save_then_find_by_exact_key(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path)
    body = body_with_image(b"jpegbytes")
    path = store.save("/responses", body, "extract", {"id": "resp_1", "output": []})
    assert path.parent == tmp_path / "responses"

    found = store.find("/responses", body, "extract")
    assert found is not None
    assert found.response["id"] == "resp_1"
    assert found.op == "extract"
    assert found.model == "muse-spark-1.3"


def test_saved_fixture_holds_a_digest_instead_of_the_image(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path)
    body = body_with_image(b"jpegbytes" * 100)
    path = store.save("/responses", body, "extract", {"output": []})
    text = path.read_text()
    assert base64.b64encode(b"jpegbytes" * 100).decode("ascii") not in text
    assert "data:image/jpeg;sha256," in text


def test_find_falls_back_to_the_operation_fixture(tmp_path: Path) -> None:
    store = FixtureStore(tmp_path)
    shared = store.path_for("/responses", "extract")
    shared.parent.mkdir(parents=True)
    shared.write_text(
        '{"endpoint": "/responses", "op": "extract", "key": "shared", "response": {"id": "s"}}'
    )
    found = store.find("/responses", {"model": "m", "input": "anything"}, "extract")
    assert found is not None
    assert found.response["id"] == "s"
    assert store.find("/responses", {"model": "m", "input": "anything"}, "other") is None


def test_paths_are_filesystem_safe() -> None:
    store = FixtureStore(Path("/x"))
    assert store.path_for("/images/edits", "My Op!") == Path("/x/images-edits/my-op.json")
