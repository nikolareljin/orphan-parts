from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.deps import SamplesDep, SegmenterDep
from app.api.model_errors import as_http
from app.api.samples import sample_photos, visitor_files
from app.model_api import exact_replay
from app.segment import Segmentation

router = APIRouter(prefix="/api", tags=["segment"])


@router.post("/segment", response_model=Segmentation)
async def segment(
    segmenter: SegmenterDep,
    samples: SamplesDep,
    photo: Annotated[
        UploadFile | None, File(description="One photo; the demo visitor sends sample_id")
    ] = None,
    sample_id: Annotated[
        str | None, Form(description="A sample photo id from GET /api/samples, in place of photo")
    ] = None,
    concepts: Annotated[
        list[str] | None,
        Form(description="What to find; default item, label and connector"),
    ] = None,
) -> Segmentation:
    """Find the item, its label and its connector: one region per match, with a crop, plus the
    photo with the masks drawn over it."""
    visitor_files(photo is not None)
    if (photo is None) == (sample_id is None):
        raise HTTPException(status_code=422, detail="send photo or sample_id, one of the two")
    max_mb = segmenter.settings.max_upload_mb
    if photo is not None and photo.size is not None and photo.size > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"the photo is larger than {max_mb} MB")
    if sample_id is not None:
        data = sample_photos(samples, [sample_id])[0]
    else:
        data = await photo.read() if photo is not None else b""
    token = exact_replay.set(sample_id is not None)
    try:
        return await segmenter.segment(data, concepts)
    except Exception as exc:
        raise as_http(exc) from exc
    finally:
        exact_replay.reset(token)
