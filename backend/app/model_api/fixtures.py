"""Recorded Model API responses.

A fixture is one JSON file: the request (with image payloads replaced by their digest) and
the response body. Files live under ``<fixtures_dir>/<endpoint>/``:

* ``<key>.json``: exact match on the digest of the request body
* ``<op>.json``: fallback shared by every request made for that operation

Tests and the offline demo read them; ``OPL_RECORD_FIXTURES=1`` writes them.
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

_DATA_URL = re.compile(r"^data:([\w./+-]+);base64,(.*)$", re.DOTALL)
_SAFE = re.compile(r"[^a-z0-9_.-]+")


class Fixture(BaseModel):
    endpoint: str
    op: str
    model: str | None = None
    key: str
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    status: int = 200


def _summarise(value: Any) -> Any:
    """Replace inline media with a digest so fixtures stay small and keys stay stable."""
    if isinstance(value, dict):
        return {k: _summarise(v) for k, v in sorted(value.items())}
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
            return Fixture.model_validate_json(exact.read_text(encoding="utf-8"))
        fallback = self.path_for(endpoint, op)
        if fallback.is_file():
            # said in the log: a recorded set that stops matching (a photo changed, or what is
            # sent of it, as EXTRACT_ENHANCE does) answers from here without an error
            log.info("fixture by operation", extra={"op": op, "endpoint": endpoint, "key": key})
            return Fixture.model_validate_json(fallback.read_text(encoding="utf-8"))
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
        fixture = Fixture(
            endpoint=endpoint,
            op=op,
            model=model if isinstance(model, str) else None,
            key=key,
            request=_summarise(body),
            response=response,
            status=status,
        )
        path = self.path_for(endpoint, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fixture.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path
