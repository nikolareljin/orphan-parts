"""The demo samples: the catalog, its files, and a reading of the samples a visitor picks.
Every route here is the demo visitor's too; a reading through the code's door is live when
the server has a key, so it is counted as a call that spends."""

from fastapi import APIRouter, HTTPException, Path, Request, Response

from app.api.deps import GateDep, SampleReaderDep, SamplesDep
from app.api.model_errors import as_http
from app.ops.door import for_visitor, live_request
from app.ops.gate import charge_more
from app.samples import (
    VISITOR_UPLOAD_LINE,
    SampleCatalog,
    SampleRead,
    SampleReadRequest,
    Samples,
    UnknownSampleError,
)

router = APIRouter(prefix="/api", tags=["samples"])

SampleId = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$", description="an id from GET /api/samples")
CACHE = {"Cache-Control": "public, max-age=3600"}
MEDIA = {"photo": "image/jpeg", "listing": "text/plain; charset=utf-8", "note": "audio/wav"}


@router.get("/samples", response_model=SampleCatalog)
def samples(catalog: SamplesDep) -> SampleCatalog:
    """The demo set's photos grouped by item, its listing texts and voice notes: what the demo
    visitor reads instead of a file of their own. Empty where the set is not shipped."""
    return catalog.catalog()


@router.get("/samples/{sample_id}/file")
def sample_file(catalog: SamplesDep, sample_id: str = SampleId) -> Response:
    """A sample as it is stored: the photo, the listing text or the voice note."""
    try:
        kind = catalog.kind(sample_id)
        data = catalog.file(sample_id)
    except UnknownSampleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(data, media_type=MEDIA[kind], headers=CACHE)


@router.get("/samples/{sample_id}/thumb")
def sample_thumb(catalog: SamplesDep, sample_id: str = SampleId) -> Response:
    """A sample photo, small (at most 320 px on its long side), for the gallery."""
    try:
        data = catalog.thumb(sample_id)
    except UnknownSampleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(data, media_type="image/jpeg", headers=CACHE)


@router.post("/samples/read", response_model=SampleRead)
async def read_samples(
    request: SampleReadRequest, reader: SampleReaderDep, gate: GateDep, http: Request
) -> SampleRead:
    """The picked sample photos read: an item whose every photo is picked is one reading of
    them all, any other photo is read alone, one result each. For the demo visitor every
    answer is the recording of that exact photo; a selection with none says so plainly
    (``missing``) rather than answering with a stub. Unknown ids are 404."""
    try:
        units = reader.units(request.sample_ids)
    except UnknownSampleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not live_request.get() and gate.enabled and len(units) > 1:
        # the demo visitor: the gate took one try for the request; each further reading is
        # one more, so a large selection is paid for in tries as the readings it makes
        address = gate.client_ip(http)
        ok, retry = gate.tries.take(address, count=len(units) - 1)
        if not ok:
            # refused before any reading: the try the gate took for the request is given back
            gate.tries.give_back(address, 1)
            raise HTTPException(
                status_code=429,
                detail=f"this address's hourly allowance of tries has fewer than {len(units)}"
                f" left; wait {retry} s or pick fewer photos",
                headers={"Retry-After": str(retry)},
            )
    if live_request.get() and len(units) > 1:
        # the gate counted one call for the request; through the code's door each further
        # reading is one more
        refused = charge_more(gate, len(units) - 1)
        if refused is not None:
            detail, retry = refused
            headers = {"Retry-After": str(retry)} if retry else None
            raise HTTPException(status_code=429, detail=detail, headers=headers)
    try:
        return await reader.read(request.sample_ids, request.find_label)
    except Exception as exc:
        raise as_http(exc) from exc


# --- sample references on the reading routes ------------------------------------------


def visitor_files(uploaded: bool) -> None:
    """The demo visitor reads the samples, never a file of their own: one sent is a 403."""
    if uploaded and for_visitor():
        raise HTTPException(status_code=403, detail=VISITOR_UPLOAD_LINE)


def sample_photos(catalog: Samples, sample_ids: list[str]) -> list[bytes]:
    """The stored bytes of these sample photos, in order; an unknown id is a 404."""
    try:
        return [catalog.photo(sid) for sid in sample_ids]
    except UnknownSampleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
