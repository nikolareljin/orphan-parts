from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import ExtractorDep
from app.extract import BadImageError, Extraction
from app.model_api import (
    FixtureMissingError,
    IncompleteResponseError,
    ModelApiError,
    SpendCapError,
)

router = APIRouter(prefix="/api", tags=["extract"])


@router.post("/extract", response_model=Extraction)
async def extract(
    photos: Annotated[list[UploadFile], File(description="One to four photos of the label")],
    extractor: ExtractorDep,
) -> Extraction:
    """Read the label on an item into typed fields, each with a confidence and its source."""
    data = [await photo.read() for photo in photos]
    try:
        return await extractor.extract(data)
    except BadImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SpendCapError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FixtureMissingError as exc:
        raise HTTPException(
            status_code=503, detail="no recorded answer for this request in fixture mode"
        ) from exc
    except IncompleteResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ModelApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
