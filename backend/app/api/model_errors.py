"""One mapping from service errors to HTTP answers, shared by every feature route."""

from fastapi import HTTPException

from app.extract.imaging import BadImageError
from app.model_api import (
    FixtureMissingError,
    IncompleteResponseError,
    ModelApiError,
    SpendCapError,
)
from app.ops.door import live_request


def as_http(exc: Exception) -> HTTPException:
    """``detail`` is written to be shown to the user; status says whose fault it was."""
    if isinstance(exc, BadImageError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, SpendCapError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, FixtureMissingError):
        if not live_request.get():
            return HTTPException(
                status_code=503,
                detail=(
                    "the public demo answers its sample photos only; the code opens the live"
                    " models for a photo of your own"
                ),
            )
        return HTTPException(
            status_code=503, detail="no recorded answer for this request in fixture mode"
        )
    if isinstance(exc, IncompleteResponseError | ModelApiError):
        return HTTPException(status_code=502, detail=str(exc))
    raise exc
