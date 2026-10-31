"""Errors raised by the Model API client."""

RETRYABLE_STATUSES = frozenset({429, 500, 503})


class ModelApiError(Exception):
    """A request to the Model API failed and will not be retried further."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        error_type: str | None = None,
        code: str | None = None,
        attempts: int = 1,
        retry_after: float | None = None,
    ) -> None:
        self.status = status
        self.error_type = error_type
        self.code = code
        self.attempts = attempts
        self.retry_after = retry_after
        super().__init__(message)

    @property
    def retryable(self) -> bool:
        return self.status in RETRYABLE_STATUSES

    def __str__(self) -> str:
        parts = []
        if self.status is not None:
            parts.append(f"HTTP {self.status}")
        if self.error_type:
            parts.append(self.error_type)
        if self.code:
            parts.append(self.code)
        head = " ".join(parts)
        body = super().__str__()
        return f"{head}: {body}" if head else body


class IncompleteResponseError(ModelApiError):
    """The response came back with a status other than completed, or with a refusal."""


class SpendCapError(ModelApiError):
    """The spend ledger reached the configured cap; live calls are paused."""

    def __init__(self, spent_usd: float, cap_usd: float) -> None:
        self.spent_usd = spent_usd
        self.cap_usd = cap_usd
        super().__init__(f"spend cap reached: {spent_usd:.4f} of {cap_usd:.2f} USD")


class FixtureMissingError(ModelApiError):
    """Fixture mode is on and no recorded response matches the request."""

    def __init__(self, endpoint: str, key: str, op: str) -> None:
        self.endpoint = endpoint
        self.key = key
        self.op = op
        super().__init__(
            f"no fixture for {endpoint} op={op} key={key}; "
            "record one with OPL_RECORD_FIXTURES=1 or add <fixtures_dir>/"
            f"{endpoint.strip('/')}/{op}.json"
        )


class NoRecordingError(FixtureMissingError):
    """Only an exact recording may answer (a sample photo's read) and this request has none:
    the operation's stub is never handed back in its place."""

    def __init__(self, endpoint: str, key: str, op: str) -> None:
        super().__init__(endpoint, key, op)
        self.args = (f"no recording of {op} for this request",)
