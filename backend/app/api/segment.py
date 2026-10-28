from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.deps import SegmenterDep
from app.api.model_errors import as_http
from app.segment import Segmentation

router = APIRouter(prefix="/api", tags=["segment"])


@router.post("/segment", response_model=Segmentation)
async def segment(
    photo: Annotated[UploadFile, File(description="One photo")],
    segmenter: SegmenterDep,
    concepts: Annotated[
        list[str] | None,
        Form(description="What to find; default item, label and connector"),
    ] = None,
) -> Segmentation:
    """Find the item, its label and its connector: one region per match, with a crop, plus the
    photo with the masks drawn over it."""
    max_mb = segmenter.settings.max_upload_mb
    if photo.size is not None and photo.size > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"the photo is larger than {max_mb} MB")
    data = await photo.read()
    try:
        return await segmenter.segment(data, concepts)
    except Exception as exc:
        raise as_http(exc) from exc
