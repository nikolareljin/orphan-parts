"""Recorded Model API responses.

A fixture is one JSON file: the request (with image payloads replaced by their digest) and
the response body. Files live under ``<fixtures_dir>/<endpoint>/``:

* ``<key>.json``: exact match on the digest of the request body
* ``<op>.json``: fallback shared by every request made for that operation

Tests and the offline demo read them; ``OPL_RECORD_FIXTURES=1`` writes them. A generated
image in a response (``data[n].b64_json``) is kept beside its fixture as ``<key>-<n>.jpg`` (or
``.png``) and the field says ``@<that file>``: the picture stays a picture, and the JSON holds
no long base64 run for a secret scanner to mistake for a token. Inline images still load.
"""

import base64
import binascii
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)

_DATA_URL = re.compile(r"^data:([\w./+-]+);base64,(.*)$", re.DOTALL)
_SAFE = re.compile(r"[^a-z0-9_.-]+")


class Fixture(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    endpoint: str
    op: str
    model: str | None = None
    # written as "digest": a long hex value under "key" reads as a credential to secret
    # scanners; files written before that still say "key"
    key: str = Field(validation_alias=AliasChoices("digest", "key"), serialization_alias="digest")
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    status: int = 200


def _without_reasoning(value: Any) -> Any:
    """The model's encrypted reasoning emptied: opaque, large, never read back from a recording,
    and random enough to pass for a credential. A request that carries an earlier answer's
    reasoning is keyed without it, so a replayed chain still finds its next step."""
    if isinstance(value, dict):
        return {
            k: "" if k == "encrypted_content" and isinstance(v, str) else _without_reasoning(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_without_reasoning(v) for v in value]
    return value


def _summarise(value: Any) -> Any:
    """Replace inline media with a digest so fixtures stay small and keys stay stable."""
    if isinstance(value, dict):
        return {
            k: "" if k == "encrypted_content" and isinstance(v, str) else _summarise(v)
            for k, v in sorted(value.items())
        }
    if isinstance(value, list):
        return [_summarise(v) for v in value]
    if isinstance(value, str) and value.startswith("data:"):
        m = _DATA_URL.match(value)
        if m:
            digest = hashlib.sha256(m.group(2).encode("ascii")).hexdigest()[:16]
            return f"data:{m.group(1)};sha256,{digest}"
    return value


def request_key(endpoint: str, body: dict[str, Any]) -> str:
    canonical = json.dumps({"endpoint": endpoint, "body": _summarise(body)}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _slug(text: str) -> str:
    return _SAFE.sub("-", text.strip("/").lower()).strip("-") or "root"


def _image_suffix(data: bytes) -> str:
    return ".png" if data.startswith(b"\x89PNG") else ".jpg"


def _images_out(response: dict[str, Any], folder: Path, key: str) -> dict[str, Any]:
    """The response with each generated image written beside the fixture, named in its place."""
    items = response.get("data")
    if not isinstance(items, list):
        return response
    out = []
    for n, item in enumerate(items, 1):
        b64 = item.get("b64_json") if isinstance(item, dict) else None
        if isinstance(b64, str) and b64 and not b64.startswith("@"):
            try:
                data = base64.b64decode(b64, validate=True)
            except (binascii.Error, ValueError):
                out.append(item)
                continue
            name = f"{key}-{n}{_image_suffix(data)}"
            (folder / name).write_bytes(data)
            item = {**item, "b64_json": f"@{name}"}
        out.append(item)
    return {**response, "data": out}


def _images_in(fixture: "Fixture", folder: Path) -> "Fixture":
    """The fixture with every ``@file`` image read back as base64, as the API sent it."""
    items = fixture.response.get("data")
    if not isinstance(items, list):
        return fixture
    out = []
    for item in items:
        ref = item.get("b64_json") if isinstance(item, dict) else None
        if isinstance(ref, str) and ref.startswith("@"):
            file = folder / Path(ref[1:]).name
            item = {**item, "b64_json": base64.b64encode(file.read_bytes()).decode("ascii")}
        out.append(item)
    return fixture.model_copy(update={"response": {**fixture.response, "data": out}})


class FixtureStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _dir(self, endpoint: str) -> Path:
        return self.root / _slug(endpoint)

    def path_for(self, endpoint: str, name: str) -> Path:
        return self._dir(endpoint) / f"{_slug(name)}.json"

    def find(self, endpoint: str, body: dict[str, Any], op: str) -> Fixture | None:
        key = request_key(endpoint, body)
        exact = self.path_for(endpoint, key)
        if exact.is_file():
            found = Fixture.model_validate_json(exact.read_text(encoding="utf-8"))
            return _images_in(found, exact.parent)
        fallback = self.path_for(endpoint, op)
        if fallback.is_file():
            # said in the log: a recorded set that stops matching (a photo changed, or what is
            # sent of it, as EXTRACT_ENHANCE does) answers from here without an error
            log.info("fixture by operation", extra={"op": op, "endpoint": endpoint, "key": key})
            found = Fixture.model_validate_json(fallback.read_text(encoding="utf-8"))
            return _images_in(found, fallback.parent)
        return None

    def save(
        self,
        endpoint: str,
        body: dict[str, Any],
        op: str,
        response: dict[str, Any],
        *,
        status: int = 200,
    ) -> Path:
        key = request_key(endpoint, body)
        model = body.get("model")
        path = self.path_for(endpoint, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fixture = Fixture(
            endpoint=endpoint,
            op=op,
            model=model if isinstance(model, str) else None,
            key=key,
            request=_summarise(body),
            response=_images_out(_without_reasoning(response), path.parent, path.stem),
            status=status,
        )
        path.write_text(fixture.model_dump_json(indent=2, by_alias=True) + "\n", encoding="utf-8")
        return path
