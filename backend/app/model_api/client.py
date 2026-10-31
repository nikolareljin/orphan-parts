"""The one place that talks to the Model API.

Responsibilities: bearer auth from settings, timeouts, retries with backoff for 429/500/503
(honouring Retry-After), the spend cap, the cost ledger, structured output, and fixture mode
for tests and the offline demo.
"""

import asyncio
import base64
import hashlib
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

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
from app.ops.door import live_request
from app.ops.logging import request_id_var

log = logging.getLogger("app.model_api")

RESPONSES = "/responses"
MODELS = "/models"
TRANSCRIBE = "/asr/transcribe"
IMAGES = "/images/generations"
JPEG_MAGIC = b"\xff\xd8\xff"

IMAGE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp", "image/x-icon"}
)
REASONING_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})
# Reasoning tokens count against max_output_tokens on this API: a label read at effort low
# spent 798 of its 800 on reasoning and stopped before the answer. A caller's max_output_tokens
# is the budget for the answer alone; the request adds this much room for reasoning, by effort.
# Billing is per token used, so the larger cap costs nothing unless the model uses it.
REASONING_HEADROOM: dict[str, int] = {
    "minimal": 1024,
    "low": 4096,
    "medium": 8192,
    "high": 16384,
    "xhigh": 32768,
}
# with no effort given the model may still reason, so the room is the same as for low
DEFAULT_REASONING_HEADROOM = REASONING_HEADROOM["low"]
# how much of the text a validation error quotes; pydantic cuts about this much itself
PREVIEW_CHARS = 120

SleepFn = Callable[[float], Awaitable[None]]


def output_cap(answer_tokens: int, effort: str | None, ceiling: int = 0) -> int:
    """The max_output_tokens sent: the answer budget plus the reasoning headroom for the
    effort, held under the ceiling when one is set (0 = none)."""
    headroom = REASONING_HEADROOM.get(effort or "", DEFAULT_REASONING_HEADROOM)
    total = answer_tokens + headroom
    return min(total, ceiling) if ceiling > 0 else total


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
    # the last message alone: with a search or tool in play the model may write a line or two
    # before the calls, and the answer is the message after them
    final_text: str = ""
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


class PictureResult(BaseModel):
    """One generated image, decoded; priced per image, the tokens kept for the record."""

    data: bytes
    model: str
    revised_prompt: str
    usage: Usage
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


def final_text(output: list[dict[str, Any]]) -> str:
    """The output_text of the last message item: the answer, once any tool calls are done."""
    for item in reversed(output):
        if item.get("type") != "message":
            continue
        parts = item.get("content") or []
        return "".join(str(p.get("text", "")) for p in parts if p.get("type") == "output_text")
    return ""


def last_json_object(text: str) -> str | None:
    """The last JSON object in the text that runs to its end, or None: tried from the last
    opening brace backwards, each candidate decoded (so braces inside strings do not count)."""
    body = text.rstrip()
    if not body.endswith("}"):
        return None
    decoder = json.JSONDecoder()
    start = body.rfind("{")
    while start >= 0:
        try:
            value, end = decoder.raw_decode(body, start)
        except ValueError:
            value, end = None, -1
        if isinstance(value, dict) and end == len(body):
            return body[start:]
        start = body.rfind("{", 0, start)
    return None


def searches(output: list[dict[str, Any]]) -> int:
    """How many web searches the response made: one per web_search_call item."""
    return sum(1 for item in output if item.get("type") == "web_search_call")


def search_results(output: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The pages the searches returned (with ``include: web_search_call.results``)."""
    found: list[dict[str, str]] = []
    for item in output:
        if item.get("type") != "web_search_call":
            continue
        results = item.get("results") or (item.get("action") or {}).get("sources") or []
        for r in results:
            if isinstance(r, dict) and r.get("url"):
                found.append(
                    {
                        "url": str(r["url"]),
                        "title": str(r.get("title") or ""),
                        "snippet": str(r.get("snippet") or ""),
                    }
                )
    return found


def citations(output: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The url_citation annotations on the text, in order."""
    found: list[dict[str, str]] = []
    for item in output:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            for a in part.get("annotations") or []:
                if isinstance(a, dict) and a.get("type") == "url_citation" and a.get("url"):
                    found.append({"url": str(a["url"]), "title": str(a.get("title") or "")})
    return found


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
        # how many fixture answers came from an operation's stub rather than a recording of
        # the exact request: a demo set loaded on stubs is not the demo set
        self.fixture_fallbacks = 0
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
        # the fixture twin answers the demo visitor: same fixtures, its own ledger, nothing
        # spent; set by the app when the demo gate is on, None on a machine of your own
        self.twin: ModelApiClient | None = None

    def _for_request(self) -> "ModelApiClient | None":
        """The twin when this request came through the demo door, else None (answer here)."""
        if self.twin is not None and not live_request.get():
            return self.twin
        return None

    async def aclose(self) -> None:
        await self._http.aclose()
        if self.twin is not None:
            await self.twin.aclose()

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
        include: list[str] | None = None,
        metadata: dict[str, str] | None = None,
        op: str = "respond",
        search_queries: int = 0,
        audio_seconds: float = 0.0,
    ) -> ModelResponse:
        if (twin := self._for_request()) is not None:
            return await twin.respond(
                model=model,
                input=input,
                instructions=instructions,
                schema=schema,
                schema_name=schema_name,
                effort=effort,
                max_output_tokens=max_output_tokens,
                tools=tools,
                include=include,
                metadata=metadata,
                op=op,
                search_queries=search_queries,
                audio_seconds=audio_seconds,
            )
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
        if tools:
            body["tools"] = tools
        if include:
            body["include"] = include
        if metadata:
            body["metadata"] = metadata
        if self.settings.prompt_cache_name:
            body["prompt_cache_key"] = self.settings.prompt_cache_name
        # the fixture is keyed on the answer budget, not on the cap sent, so a recording outlives
        # a change of headroom or ceiling; the wire carries the sum
        key: dict[str, Any] | None = None
        cap = 0
        if max_output_tokens:
            key = {**body, "max_output_tokens": max_output_tokens}
            cap = output_cap(max_output_tokens, effort, self.settings.model_max_output_tokens)
            body["max_output_tokens"] = cap

        data, from_fixture, attempts, ms = await self._post(RESPONSES, body, op, key=key)
        output = data.get("output") or []
        text, refusal = output_text(output)
        answer = final_text(output)
        # The API reports no search count in usage; every web_search_call item is one query,
        # so the bill is read off the output unless the caller already knows the count.
        usage = Usage.from_response(
            data.get("usage"),
            search_queries=search_queries or searches(output),
            audio_seconds=audio_seconds,
        )
        usd = 0.0 if from_fixture else cost_usd(model, usage)
        self._record(op, model, RESPONSES, usage, usd, from_fixture, attempts, ms)
        status = str(data.get("status", "completed"))
        if status != "completed":
            detail = data.get("incomplete_details") or data.get("error") or {}
            reason = detail.get("reason") if isinstance(detail, dict) else None
            if reason == "max_output_tokens":
                # the numbers say what to raise next: the answer budget, or the headroom
                sent = f" ({cap})" if cap else ""
                raise IncompleteResponseError(
                    f"response incomplete: {op} reached max_output_tokens{sent} with "
                    f"{usage.output_tokens} output tokens used, {usage.reasoning_tokens} of them "
                    "reasoning",
                    attempts=attempts,
                )
            raise IncompleteResponseError(f"response {status}: {detail}", attempts=attempts)
        if refusal is not None:
            raise IncompleteResponseError(f"model refused: {refusal}", attempts=attempts)
        return ModelResponse(
            id=str(data.get("id", "")),
            model=str(data.get("model", model)),
            status=status,
            text=text,
            final_text=answer,
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
        parsed = parse_structured(model_cls, response, str(kwargs.get("op") or "respond"))
        return StructuredResponse[T](parsed=parsed, response=response)

    async def respond_with_tools[T: BaseModel](
        self,
        model_cls: type[T],
        *,
        model: str,
        input: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        handle: Callable[[str, dict[str, Any]], str | Awaitable[str]],
        max_steps: int = 4,
        op: str = "agent",
        schema_name: str | None = None,
        **kwargs: Any,
    ) -> StructuredResponse[T]:
        """The tool loop, stateless: every step resends the input, the previous output items and
        the tool results, since nothing is stored on the server. Ends with the strict answer."""
        items = list(input)
        last: ModelResponse | None = None
        spent = 0.0
        for step in range(1, max_steps + 1):
            response = await self.respond(
                model=model,
                input=items,
                tools=tools,
                schema=strict_schema(model_cls),
                schema_name=schema_name or model_cls.__name__,
                op=f"{op}-{step}",
                **kwargs,
            )
            last = response
            spent += response.cost_usd
            calls = response.tool_calls
            if not calls:
                parsed = parse_structured(model_cls, response, f"{op}-{step}")
                # the answer carries what the whole loop cost, every step counted once
                return StructuredResponse[T](
                    parsed=parsed, response=response.model_copy(update={"cost_usd": spent})
                )
            items = items + list(response.output)
            for call in calls:
                try:
                    args = json.loads(call.get("arguments") or "{}")
                except ValueError:
                    args = {}
                result = handle(str(call.get("name", "")), args if isinstance(args, dict) else {})
                output = await result if isinstance(result, Awaitable) else result
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call.get("call_id", "")),
                        "output": output,
                    }
                )
        raise IncompleteResponseError(
            f"the tool loop did not finish in {max_steps} steps",
            attempts=last.attempts if last else 0,
        )

    async def transcribe(
        self,
        audio_wav: bytes,
        *,
        keywords: list[str] | None = None,
        op: str = "transcribe",
    ) -> Transcript:
        """One recording to text with Muse Voice Transcribe: multipart, WAV only, one turn."""
        if (twin := self._for_request()) is not None:
            return await twin.transcribe(audio_wav, keywords=keywords, op=op)
        model = self.settings.model_voice
        body: dict[str, Any] = {"model": model, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
        if keywords:
            body["keywords"] = keywords
        files = {
            "request": (None, json.dumps(body).encode("utf-8"), "application/json"),
            "audio": ("note.wav", audio_wav, "audio/wav"),
        }
        # the recording is what distinguishes one transcription from another: its digest joins
        # the fixture key (the request itself carries the bytes, not the digest)
        key = {**body, "audio_sha256": hashlib.sha256(audio_wav).hexdigest()[:16]}
        data, from_fixture, attempts, ms = await self._post(
            TRANSCRIBE, body, op, files=files, key=key
        )
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

    async def picture(self, prompt: str, *, op: str = "picture") -> PictureResult:
        """One image with Muse Image: a JPEG, square, drawn without the model's own refinement
        pass (``reasoning_strength`` low), handed back decoded. Called on a click, never by
        itself."""
        if (twin := self._for_request()) is not None:
            return await twin.picture(prompt, op=op)
        model = self.settings.model_image
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
            "output_format": "jpeg",
            "reasoning_strength": "low",
        }
        data, from_fixture, attempts, ms = await self._post(IMAGES, body, op)
        images = [item for item in data.get("data") or [] if isinstance(item, dict)]
        first = images[0] if images else {}
        encoded = first.get("b64_json")
        try:
            image = base64.b64decode(encoded, validate=True) if isinstance(encoded, str) else b""
        except ValueError:
            image = b""
        # one image asked for, one billed, whatever the answer held
        usage = Usage.from_response(data.get("usage")).model_copy(update={"images": 1})
        usd = 0.0 if from_fixture else cost_usd(model, usage)
        self._record(op, model, IMAGES, usage, usd, from_fixture, attempts, ms)
        # a JPEG was asked for: anything else is kept nowhere, though the call is charged
        if not image.startswith(JPEG_MAGIC):
            raise IncompleteResponseError("the answer carried no image", attempts=attempts)
        return PictureResult(
            data=image,
            model=model,
            revised_prompt=str(first.get("revised_prompt") or ""),
            usage=usage,
            cost_usd=usd,
            from_fixture=from_fixture,
            attempts=attempts,
        )

    async def list_models(self) -> list[str]:
        if (twin := self._for_request()) is not None:
            return await twin.list_models()
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
            result["status"] = exc.status
            result["error"] = str(exc)
        return result

    # -- transport ------------------------------------------------------------

    async def _post(
        self,
        endpoint: str,
        body: dict[str, Any],
        op: str,
        files: dict[str, Any] | None = None,
        key: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool, int, float]:
        """body goes on the wire; key, when given, is what names the fixture instead."""
        keyed = body if key is None else key
        if self.mode == "record":
            # a recording already on disk for this exact request is replayed, not bought
            # again: a run that stopped half-way is resumed at no cost for what it has
            kept = self.fixtures.find(endpoint, keyed, op)
            if kept is not None and kept.key == request_key(endpoint, keyed) and kept.status < 400:
                return kept.response, True, 1, 0.0
        if self.mode == "fixture":
            fixture = self.fixtures.find(endpoint, keyed, op)
            if fixture is None:
                raise FixtureMissingError(endpoint, request_key(endpoint, keyed), op)
            if fixture.key != request_key(endpoint, keyed):
                self.fixture_fallbacks += 1
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
            self.fixtures.save(endpoint, keyed, op, data)
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


def parse_structured[T: BaseModel](model_cls: type[T], response: ModelResponse, op: str) -> T:
    """The typed answer out of a response. The schema binds the final message; a message the
    model wrote before a search or a tool call is prose and is not read. When the final message
    is not the schema alone, the last JSON object the whole text ends with is tried once."""
    try:
        return model_cls.model_validate_json(response.final_text)
    except ValueError as exc:
        reason = _validation_summary(exc)
    tail = last_json_object(response.text)
    if tail is not None and tail != response.final_text:
        try:
            return model_cls.model_validate_json(tail)
        except ValueError:
            pass
    raise IncompleteResponseError(
        f"{op}: the final message did not match {model_cls.__name__}: {reason}",
        attempts=response.attempts,
    )


def _validation_summary(exc: ValueError) -> str:
    """One line per failed check, the text they ran on cut short: enough to say what came back,
    never the whole answer."""
    if not isinstance(exc, ValidationError):
        return str(exc)[:PREVIEW_CHARS]
    lines: list[str] = []
    for err in exc.errors(include_url=False)[:3]:
        where = ".".join(str(part) for part in err.get("loc") or ()) or "text"
        value = err.get("input")
        shown = value if isinstance(value, str) else json.dumps(value, default=str)
        if len(shown) > PREVIEW_CHARS:
            shown = shown[: PREVIEW_CHARS // 2] + "..." + shown[-(PREVIEW_CHARS // 2) :]
        lines.append(f"{where}: {err.get('msg')} (input {shown!r})")
    return "; ".join(lines)


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
