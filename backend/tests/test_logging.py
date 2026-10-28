import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.ops.logging import JsonFormatter, request_id_var


def test_json_lines_carry_request_id_and_extras() -> None:
    token = request_id_var.set("rid-1")
    try:
        record = logging.LogRecord("app.t", logging.INFO, __file__, 1, "hello %s", ("x",), None)
        record.ms = 1.5
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line["msg"] == "hello x"
    assert line["request_id"] == "rid-1"
    assert line["ms"] == 1.5
    assert line["level"] == "INFO"


def test_access_log_line_carries_the_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.http"):
        client.get("/healthz", headers={"X-Request-ID": "trace-me"})
    record = next(r for r in caplog.records if r.name == "app.http")
    assert record.request_id == "trace-me"
