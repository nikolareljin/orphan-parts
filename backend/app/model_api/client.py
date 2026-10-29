"""The one place that talks to the Model API.

Responsibilities: bearer auth from settings, timeouts, retries with backoff for 429/500/503
(honouring Retry-After), the spend cap, the cost ledger, structured output, and fixture mode
for tests and the offline demo.
"""

import asyncio
import base64
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.model_api.errors import (
    RETRYABLE_STATUSES,
    FixtureMissingError,
    IncompleteResponseError,
    ModelApiError,
)
from app.model_api.fixtures import FixtureStore, request_key
from app.model_api.ledger import CostLedger, LedgerEntry
from app.model_api.pricing import Usage, cost_usd
from app.ops.logging import request_id_var

log = logging.getLogger("app.model_api")

RESPONSES = "/responses"
MODELS = "/models"
TRANSCRIBE = "/asr/transcribe"

IMAGE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp", "image/x-icon"}
)
REASONING_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})

SleepFn = Callable[[float], Awaitable[None]]


# --- input helpers -----------------------------------------------------------


def text_part(text: str) -> dict[str, Any]:
    return {"type": "input_text", "text": text}


def image_part(data: bytes, mime: str = "image/jpeg") -> dict[str, Any]:
    if mime not in IMAGE_MIME_TYPES:
        raise ValueError(f"unsupported image type: {mime}")
    encoded = base64.b64encode(data).decode("ascii")
    return {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"}


def user_message(*parts: dict[str, Any]) -> dict[str, Any]:
    return {"type": "message", "role": "user", "content": list(parts)}


# --- results -----------------------------------------------------------------


class ModelResponse(BaseModel):
    id: str
    model: str
    status: str
    text: str
    output: list[dict[str, Any]]
    usage: Usage
    cost_usd: float
    from_fixture: bool
    attempts: int

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return [item for item in self.output if item.get("type") == "function_call"]


class StructuredResponse[T: BaseModel](BaseModel):
    parsed: T
    response: ModelResponse


class Transcript(BaseModel):
    text: str
    seconds: float
    model: str
    cost_usd: float
    from_fixture: bool
    attempts: int


def output_text(output: list[dict[str, Any]]) -> tuple[str, str | None]:
    """Concatenate output_text parts; return the first refusal, if any."""
    chunks: list[str] = []
    refusal: str | None = None
    for item in output:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            kind = part.get("type")
            if kind == "output_text":
                chunks.append(str(part.get("text", "")))
            elif kind == "refusal" and refusal is None:
                refusal = str(part.get("refusal") or part.get("text") or "refused")
    return "".join(chunks), refusal


# --- client ------------------------------------------------------------------


class ModelApiClient:
    def __init__(
        self,
        settings: Settings,
        ledger: CostLedger,
        fixtures: FixtureStore | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: SleepFn = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings
        self.ledger = ledger
        self.fixtures = fixtures or FixtureStore(settings.fixtures_dir)
        self.mode = settings.model_api_mode
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._key = settings.model_api_key.get_secret_value() if settings.model_api_key else ""
        headers = {"Accept": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        self._http = httpx.AsyncClient(
            base_url=settings.model_api_base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(settings.model_api_timeout_s, connect=10.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- public calls ---------------------------------------------------------

    async def respond(
        self,
        *,
        model: str,
        input: str | list[dict[str, Any]],
        instructions: str | None = None,
        schema: dict[str, Any] | None = None,
        schema_name: str = "result",
        effort: str | None = None,
        max_output_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, str] | None = None,
        op: str = "respond",
        search_queries: int = 0,
        audio_seconds: float = 0.0,
    ) -> ModelResponse:
        body: dict[str, Any] = {"model": model, "input": input, "store": False}
        if instructions:
            body["instructions"] = instructions
        if effort:
            if effort not in REASONING_EFFORTS:
                raise ValueError(f"unknown reasoning effort: {effort}")
            body["reasoning"] = {"effort": effort}
        if schema is not None:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            }
        if max_output_tokens:
            body["max_output_tokens"] = max_output_tokens
        if tools:
            body["tools"] = tools
        if metadata:
            body["metadata"] = metadata
        if self.settings.prompt_cache_name:
            body["prompt_cache_key"] = self.settings.prompt_cache_name

        data, from_fixture, attempts, ms = await self._post(RESPONSES, body, op)
        output = data.get("output") or []
        text, refusal = output_text(output)
        usage = Usage.from_response(
            data.get("usage"), search_queries=search_queries, audio_seconds=audio_seconds
        )
        usd = 0.0 if from_fixture else cost_usd(model, usage)
        self._record(op, model, RESPONSES, usage, usd, from_fixture, attempts, ms)
        status = str(data.get("status", "completed"))
        if status != "completed":
            detail = data.get("incomplete_details") or data.get("error") or {}
            raise IncompleteResponseError(f"response {status}: {detail}", attempts=attempts)
        if refusal is not None:
            raise IncompleteResponseError(f"model refused: {refusal}", attempts=attempts)
        return ModelResponse(
            id=str(data.get("id", "")),
            model=str(data.get("model", model)),
            status=status,
            text=text,
            output=output,
            usage=usage,
            cost_usd=usd,
            from_fixture=from_fixture,
            attempts=attempts,
        )

    async def respond_structured[T: BaseModel](
        self, model_cls: type[T], *, schema_name: str | None = None, **kwargs: Any
    ) -> StructuredResponse[T]:
        schema = strict_schema(model_cls)
        response = await self.respond(
            schema=schema, schema_name=schema_name or model_cls.__name__, **kwargs
        )
        try:
            parsed = model_cls.model_validate_json(response.text)
        except ValueError as exc:
            raise IncompleteResponseError(
                f"output did not match {model_cls.__name__}: {exc}", attempts=response.attempts
            ) from exc
        return StructuredResponse[T](parsed=parsed, response=response)

    async def transcribe(
        self,
        audio_wav: bytes,
        *,
        keywords: list[str] | None = None,
        op: str = "transcribe",
    ) -> Transcript:
        """One recording to text with Muse Voice Transcribe: multipart, WAV only, one turn."""
        model = self.settings.model_voice
        body: dict[str, Any] = {"model": model, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
        if keywords:
            body["keywords"] = keywords
        files = {
            "request": (None, json.dumps(body).encode("utf-8"), "application/json"),
            "audio": ("note.wav", audio_wav, "audio/wav"),
        }
        data, from_fixture, attempts, ms = await self._post(TRANSCRIBE, body, op, files=files)
        seconds = float(data.get("audioDurationMs") or 0) / 1000.0
        usage = Usage.from_response(None, audio_seconds=seconds)
        usd = 0.0 if from_fixture else cost_usd(model, usage)
        self._record(op, model, TRANSCRIBE, usage, usd, from_fixture, attempts, ms)
        return Transcript(
            text=str(data.get("transcript") or "").strip(),
            seconds=seconds,
            model=model,
            cost_usd=usd,
            from_fixture=from_fixture,
            attempts=attempts,
        )

    async def list_models(self) -> list[str]:
        if self.mode == "fixture":
            s = self.settings
            return [s.model_spark, s.model_wonder, s.model_image, s.model_voice, s.model_sam]
        data, _, _ = await self._request("GET", MODELS, None, "list_models")
        items = data.get("data") or []
        return [str(item["id"]) for item in items if isinstance(item, dict) and "id" in item]

    async def check(self) -> dict[str, Any]:
        """Readiness probe: what mode is active and whether the API answers."""
        result: dict[str, Any] = {"mode": self.mode, "reachable": None, "models": []}
        if self.mode == "fixture":
            result["models"] = await self.list_models()
            return result
        try:
            result["models"] = await self.list_models()
            result["reachable"] = True
        except ModelApiError as exc:
            result["reachable"] = False
            result["error"] = str(exc)
        return result

    # -- transport ------------------------------------------------------------

    async def _post(
        self,
        endpoint: str,
        body: dict[str, Any],
        op: str,
        files: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool, int, float]:
        if self.mode == "fixture":
            fixture = self.fixtures.find(endpoint, body, op)
            if fixture is None:
                raise FixtureMissingError(endpoint, request_key(endpoint, body), op)
            if fixture.status >= 400:
                err = fixture.response.get("error") or {}
                raise ModelApiError(
                    str(err.get("message", "recorded failure")),
                    status=fixture.status,
                    error_type=_opt_str(err.get("type")),
                    code=_opt_str(err.get("code")),
                )
            return fixture.response, True, 1, 0.0
        self.ledger.require_budget()
        data, attempts, ms = await self._request("POST", endpoint, body, op, files=files)
        if self.mode == "record":
            self.fixtures.save(endpoint, body, op, data)
        return data, False, attempts, ms

    async def _request(
        self,
        method: str,
        endpoint: str,
        body: dict[str, Any] | None,
        op: str,
        files: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], int, float]:
        started = time.perf_counter()
        max_attempts = self.settings.model_api_max_attempts
        last: ModelApiError | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                if files is None:
                    response = await self._http.request(method, endpoint, json=body)
                else:
                    # multipart: the JSON settings as one part, the media as another
                    response = await self._http.request(method, endpoint, files=files)
            except httpx.TimeoutException as exc:
                last = ModelApiError(f"timeout on {op}: {exc}", status=503, attempts=attempt)
            except httpx.HTTPError as exc:
                detail = self._redact(str(exc))
                last = ModelApiError(
                    f"network error on {op}: {detail}", status=503, attempts=attempt
                )
            else:
                if response.status_code < 400:
                    ms = round((time.perf_counter() - started) * 1000, 1)
                    return _json_body(response), attempt, ms
                last = self._error_from(response, attempt)
                if not last.retryable:
                    raise last
            if attempt < max_attempts:
                delay = self._delay(attempt, last)
                log.warning(
                    "model api retry",
                    extra={"op": op, "attempt": attempt, "delay_s": delay, "error": str(last)},
                )
                await self._sleep(delay)
        assert last is not None
        last.attempts = max_attempts
        raise last

    def _delay(self, attempt: int, error: ModelApiError) -> float:
        cap = self.settings.model_api_retry_after_max_s
        if error.retry_after is not None:
            return float(min(error.retry_after, cap))
        base: float = 0.5 * (2 ** (attempt - 1))
        return float(min(base + self._rng.random(), cap))

    def _error_from(self, response: httpx.Response, attempt: int) -> ModelApiError:
        payload = _json_body(response)
        raw = payload.get("error")
        err: dict[str, Any] = raw if isinstance(raw, dict) else {}
        message = str(err.get("message") or response.text[:200] or "request failed")
        retry_after: float | None = None
        header = response.headers.get("retry-after")
        if header and response.status_code in RETRYABLE_STATUSES:
            try:
                retry_after = float(header)
            except ValueError:
                retry_after = None
        return ModelApiError(
            self._redact(message),
            status=response.status_code,
            error_type=_opt_str(err.get("type")),
            code=_opt_str(err.get("code")),
            attempts=attempt,
            retry_after=retry_after,
        )

    def _redact(self, text: str) -> str:
        return text.replace(self._key, "***") if self._key else text

    def _record(
        self,
        op: str,
        model: str,
        endpoint: str,
        usage: Usage,
        usd: float,
        fixture: bool,
        attempts: int,
        ms: float,
    ) -> None:
        self.ledger.record(
            LedgerEntry(
                request_id=request_id_var.get(),
                op=op,
                model=model,
                endpoint=endpoint,
                usage=usage,
                usd=usd,
                fixture=fixture,
                attempts=attempts,
                ms=ms,
            )
        )
        log.info(
            "model api %s %s",
            op,
            model,
            extra={
                "op": op,
                "model": model,
                "fixture": fixture,
                "attempts": attempts,
                "ms": ms,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "usd": usd,
                "total_usd": self.ledger.total_usd,
            },
        )


# --- helpers -----------------------------------------------------------------


def strict_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema in the strict subset: every object closed, every property required."""
    schema = model_cls.model_json_schema()
    _close(schema)
    for definition in (schema.get("$defs") or {}).values():
        _close(definition)
    return schema


def _close(node: dict[str, Any]) -> None:
    if node.get("type") == "object" or "properties" in node:
        props = node.get("properties") or {}
        node["additionalProperties"] = False
        node["required"] = list(props.keys())
        for prop in props.values():
            if isinstance(prop, dict):
                _close(prop)
    if isinstance(node.get("items"), dict):
        _close(node["items"])
    for alt in node.get("anyOf") or []:
        if isinstance(alt, dict):
            _close(alt)


def _json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {"data": data}


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
