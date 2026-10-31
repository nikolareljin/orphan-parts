"""The HTTP mode: the proof end to end against a running backend, as a browser or the phone
would make it. Behind a gate: the demo visitor's extract is answered from the recordings and a
write is refused, then a session with the code reads the live models, and ends. Without a
gate every caller is the owner, so only the live reading is checked.

The code reaches this module as a value already read from the environment; it goes into one
request body and nowhere else. Nothing printed is a request, a token or a body: statuses, the
fields the answers carry, and the server's own one-line ``detail`` on a refusal."""

import time
from collections.abc import Callable
from typing import Any, TextIO

import httpx

from app.extract.service import MAX_OUTPUT_TOKENS as EXTRACT_OUT
from livecheck.ceilings import tokens
from livecheck.report import FAIL, HEADER, PASS, SKIP, RefusedError, Result, Run, one_line, said

WRITE_PROBE = {"item_type": "live check probe"}


def _detail(response: httpx.Response) -> str:
    """The server's own line for a refusal, when it sent one; else the status alone."""
    try:
        body = response.json()
    except ValueError:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    text = f"HTTP {response.status_code}"
    if isinstance(detail, str) and detail:
        text += f": {detail[:120]}"
    return text


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _timed(op: str, fn: Callable[[], Result]) -> Result:
    started = time.perf_counter()
    try:
        result = fn()
    except httpx.HTTPError as exc:
        result = Result(op=op, status=FAIL, note=one_line(exc))
    result.ms = round((time.perf_counter() - started) * 1000, 1)
    return result


def _extract(http: httpx.Client, photo: bytes, headers: dict[str, str], op: str) -> Result:
    response = http.post(
        "/api/extract",
        files=[("photos", ("label.jpg", photo, "image/jpeg"))],
        headers=headers,
    )
    if response.status_code != 200:
        return Result(op=op, status=FAIL, note=_detail(response))
    reading = _json(response)
    fields = reading.get("fields")
    return Result(
        op=op,
        model=str(reading.get("model") or "-"),
        status=PASS,
        usd=float(reading.get("cost_usd") or 0.0),
        note=(
            f"fields={len(fields) if isinstance(fields, dict) else 0}"
            f" from_fixture={reading.get('from_fixture')}"
        ),
    )


def _expect_recorded(result: Result) -> Result:
    if result.status == PASS and "from_fixture=True" not in result.note:
        result.status = FAIL
        result.note = "a caller without the code reached the live models; " + result.note
    return result


def _expect_live(result: Result, host_live: bool) -> Result:
    if result.status == PASS and "from_fixture=False" not in result.note:
        result.status = FAIL
        why = (
            "the host answers from recordings (no working key behind the door)"
            if not host_live
            else "answered from recordings although the host says it is live"
        )
        result.note = f"{why}; {result.note}"
    return result


def run_remote(http: httpx.Client, *, code: str, max_usd: float, photo: bytes, out: TextIO) -> Run:
    """The steps against ``http``'s base URL, each printed as it ends."""
    print(said("LIVECHECK_ACCESS_CODE", code), file=out)
    ready = _json(http.get("/readyz"))
    raw_demo = ready.get("demo")
    demo: dict[str, Any] = raw_demo if isinstance(raw_demo, dict) else {}
    gated = bool(demo.get("gated"))
    host_live = bool(demo.get("live_models"))
    spent = float(ready.get("spend_usd") or 0.0)
    cap = float(ready.get("spend_cap_usd") or 0.0)
    headroom = max(cap - spent, 0.0)
    print(
        f"host: {http.base_url}; model_api: {ready.get('model_api', '?')}; gated={gated};"
        f" ledger: spent ${spent:.4f} of ${cap:.2f} (headroom ${headroom:.4f});"
        f" this run at most ${max_usd:.2f}",
        file=out,
    )
    # the host's own output cap is not known from here: the ceiling is without one
    most = tokens("muse-spark", EXTRACT_OUT, 0, images=1)
    if host_live and headroom < max_usd:
        raise RefusedError(
            f"the host's spend cap leaves ${headroom:.4f}, below --max-usd {max_usd:.2f}"
        )
    if host_live and most > max_usd:
        raise RefusedError(f"one extract may cost ${most:.4f}, above --max-usd {max_usd:.2f}")
    run = Run()
    print(file=out)
    print(HEADER, file=out)

    def add(result: Result) -> Result:
        run.results.append(result)
        print(result.line(), file=out)
        return result

    def access(op: str, headers: dict[str, str]) -> Result:
        response = http.get("/api/access", headers=headers)
        if response.status_code != 200:
            return Result(op=op, status=FAIL, note=_detail(response))
        body = _json(response)
        return Result(
            op=op,
            status=PASS,
            note=f"gated={body.get('gated')} granted={body.get('granted')} live={body.get('live')}",
        )

    add(_timed("access", lambda: access("access", {})))

    if not gated:
        print(
            "no gate on this host: every caller is the owner, the no-code proof does not apply",
            file=out,
        )
        add(
            _timed("extract", lambda: _expect_live(_extract(http, photo, {}, "extract"), host_live))
        )
        print(file=out)
        print(run.total(), file=out)
        return run

    # the demo visitor: recordings only, and no write
    add(
        _timed(
            "extract (no code)",
            lambda: _expect_recorded(_extract(http, photo, {}, "extract (no code)")),
        )
    )

    def write_probe() -> Result:
        response = http.post("/api/items", json=WRITE_PROBE)
        if response.status_code == 403:
            return Result(op="write (no code)", status=PASS, note=_detail(response))
        if response.status_code < 400:
            return Result(
                op="write (no code)",
                status=FAIL,
                note=f"a write without the code was accepted (HTTP {response.status_code})",
            )
        return Result(op="write (no code)", status=FAIL, note=_detail(response))

    add(_timed("write (no code)", write_probe))

    if not code:
        add(Result(op="sign-in", status=SKIP, note="LIVECHECK_ACCESS_CODE is not set"))
        for op in ("extract", "access (signed in)", "sign-out"):
            add(Result(op=op, note="not run"))
        print(file=out)
        print(run.total(), file=out)
        return run

    token = ""

    def sign_in() -> Result:
        nonlocal token
        response = http.post("/api/access", json={"code": code})
        if response.status_code != 200:
            return Result(op="sign-in", status=FAIL, note=_detail(response))
        body = _json(response)
        token = str(body.get("token") or "")
        if not body.get("granted") or not token:
            return Result(op="sign-in", status=FAIL, note="no session granted")
        return Result(op="sign-in", status=PASS, note=f"session granted, live={body.get('live')}")

    if add(_timed("sign-in", sign_in)).status != PASS:
        for op in ("extract", "access (signed in)", "sign-out"):
            add(Result(op=op, note="not run"))
        print(file=out)
        print(run.total(), file=out)
        return run

    bearer = {"Authorization": f"Bearer {token}"}
    add(
        _timed("extract", lambda: _expect_live(_extract(http, photo, bearer, "extract"), host_live))
    )

    def signed_in() -> Result:
        result = access("access (signed in)", bearer)
        if result.status == PASS and "live=True" not in result.note:
            result.status = FAIL
            result.note = "the session does not reach the live models; " + result.note
        return result

    add(_timed("access (signed in)", signed_in))

    def sign_out() -> Result:
        response = http.delete("/api/access", headers=bearer)
        if response.status_code != 200:
            return Result(op="sign-out", status=FAIL, note=_detail(response))
        # the cookie is gone; a caller without the token is the demo visitor again
        http.cookies.clear()
        after = _json(http.get("/api/access"))
        if after.get("granted"):
            return Result(op="sign-out", status=FAIL, note="still granted without the token")
        return Result(op="sign-out", status=PASS, note="signed out; the visitor again")

    add(_timed("sign-out", sign_out))
    print(file=out)
    print(run.total(), file=out)
    return run
