from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.deps import ExtractorDep, SamplesDep
from app.api.model_errors import as_http
from app.api.samples import sample_photos, visitor_files
from app.extract import Extraction
from app.model_api import exact_replay

router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract", response_model=Extraction)
async def extract(
    extractor: ExtractorDep,
    samples: SamplesDep,
    photos: Annotated[
        list[UploadFile] | None,
        File(description="One to four photos of the label; the demo visitor sends sample_ids"),
    ] = None,
    crops: Annotated[
        list[UploadFile] | None,
        File(description="Label crops from /api/segment; evidence is then sourced label_crop"),
    ] = None,
    sample_ids: Annotated[
        list[str] | None,
        Form(description="Sample photo ids from GET /api/samples, read in place of photos"),
    ] = None,
) -> Extraction:
    """Read the label on an item into typed fields, each with a confidence and its source."""
    visitor_files(bool(photos or crops))
    if bool(photos) == bool(sample_ids):
        raise HTTPException(status_code=422, detail="send photos or sample_ids, one of the two")
    max_mb = extractor.settings.max_upload_mb
    uploads = [*(photos or []), *(crops or [])]
    if any(u.size is not None and u.size > max_mb * 1024 * 1024 for u in uploads):
        # refuse by the declared size before pulling the body into memory
        raise HTTPException(status_code=400, detail=f"the photo is larger than {max_mb} MB")
    if sample_ids:
        if len(sample_ids) > extractor.settings.max_photos:
            raise HTTPException(
                status_code=400,
                detail=f"at most {extractor.settings.max_photos} photos per request",
            )
        data = sample_photos(samples, sample_ids)
    else:
        data = [await photo.read() for photo in photos or []]
    crop_data = [await c.read() for c in crops or []]
    # a sample is answered by its own recording or not at all, never by a stub
    token = exact_replay.set(bool(sample_ids))
    try:
        return await extractor.extract(data, crop_data)
    except Exception as exc:
        raise as_http(exc) from exc
    finally:
        exact_replay.reset(token)
