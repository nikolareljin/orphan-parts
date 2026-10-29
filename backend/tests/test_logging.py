import json
import logging
import re

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


def test_access_log_path_is_printable_and_bounded(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    # a line break or an escape sequence in the path cannot forge a log line
    with caplog.at_level(logging.INFO, logger="app.http"):
        client.get("/healthz%0Aforged%1b[31m" + "x" * 600)
    record = next(r for r in caplog.records if r.name == "app.http")
    assert record.path.startswith("/healthz")
    assert "\n" not in record.path and "\x1b" not in record.path
    assert len(record.path) <= 512
    assert record.method == "GET"


def test_an_unsafe_client_request_id_is_replaced(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.http"):
        res = client.get("/healthz", headers={"X-Request-ID": "bad id\r\nX-Forged: 1"})
    record = next(r for r in caplog.records if r.name == "app.http")
    assert re.fullmatch(r"[0-9a-f]{16}", record.request_id)
    assert res.headers["X-Request-ID"] == record.request_id
