from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import ExtractorDep
from app.api.model_errors import as_http
from app.extract import Extraction

router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract", response_model=Extraction)
async def extract(
    photos: Annotated[list[UploadFile], File(description="One to four photos of the label")],
    extractor: ExtractorDep,
    crops: Annotated[
        list[UploadFile] | None,
        File(description="Label crops from /api/segment; evidence is then sourced label_crop"),
    ] = None,
) -> Extraction:
    """Read the label on an item into typed fields, each with a confidence and its source."""
    max_mb = extractor.settings.max_upload_mb
    uploads = [*photos, *(crops or [])]
    if any(u.size is not None and u.size > max_mb * 1024 * 1024 for u in uploads):
        # refuse by the declared size before pulling the body into memory
        raise HTTPException(status_code=400, detail=f"the photo is larger than {max_mb} MB")
    data = [await photo.read() for photo in photos]
    crop_data = [await c.read() for c in crops or []]
    try:
        return await extractor.extract(data, crop_data)
    except Exception as exc:
        raise as_http(exc) from exc
