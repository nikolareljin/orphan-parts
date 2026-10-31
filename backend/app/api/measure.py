from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import ValidationError

from app.api.deps import InventoryDep, MeasurerDep, SamplesDep
from app.api.model_errors import as_http
from app.api.samples import sample_photos, visitor_files
from app.measure import MeasureRequest, MeasureResult
from app.measure.schema import Measurement
from app.profiles import UnknownProfileError

router = APIRouter(prefix="/api", tags=["measure"])

PhotoPart = Annotated[UploadFile, File(description="The photo the points were marked on")]
RequestPart = Annotated[
    str, Form(description="The marks, the reference and the feature, as JSON (MeasureRequest)")
]


async def _read(
    photo: UploadFile | None, request: str, measurer: MeasurerDep, sample: bytes | None = None
) -> tuple[bytes, MeasureRequest]:
    max_mb = measurer.settings.max_upload_mb
    if photo is not None and photo.size is not None and photo.size > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"the photo is larger than {max_mb} MB")
    try:
        spec = MeasureRequest.model_validate_json(request)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"loc": ["body", "request", *e["loc"]], "msg": e["msg"]} for e in exc.errors()],
        ) from exc
    if spec.profile:
        try:
            measurer.profiles.get(spec.profile)
        except UnknownProfileError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
    if sample is not None:
        return sample, spec
    return (await photo.read() if photo is not None else b""), spec


@router.post("/measure", response_model=MeasureResult)
async def measure(
    request: RequestPart,
    measurer: MeasurerDep,
    samples: SamplesDep,
    photo: Annotated[
        UploadFile | None,
        File(description="The photo the points were marked on; the demo visitor sends sample_id"),
    ] = None,
    sample_id: Annotated[
        str | None,
        Form(description="A sample photo id from GET /api/samples, in place of photo"),
    ] = None,
) -> MeasureResult:
    """A dimension from marked points and a scale reference, or the reasons the capture was
    refused. Nothing is stored."""
    visitor_files(photo is not None)
    if (photo is None) == (sample_id is None):
        raise HTTPException(status_code=422, detail="send photo or sample_id, one of the two")
    sample = sample_photos(samples, [sample_id])[0] if sample_id is not None else None
    data, spec = await _read(photo, request, measurer, sample)
    try:
        result, _ = await measurer.measure(data, spec)
    except Exception as exc:
        raise as_http(exc) from exc
    return result


@router.post(
    "/items/{item_id}/measurements",
    response_model=Measurement,
    status_code=status.HTTP_201_CREATED,
)
async def measure_item(
    item_id: int,
    photo: PhotoPart,
    request: RequestPart,
    measurer: MeasurerDep,
    inventory: InventoryDep,
) -> Measurement:
    """The same, stored on the item: an accepted capture proposes an observed value to confirm."""
    inventory.get(item_id)  # a missing item is a 404 before any image work
    data, spec = await _read(photo, request, measurer)
    try:
        result, prepared = await measurer.measure(data, spec)
    except Exception as exc:
        raise as_http(exc) from exc
    return inventory.add_measurement(item_id, result, prepared)


@router.get("/items/{item_id}/measurements", response_model=list[Measurement])
def item_measurements(item_id: int, inventory: InventoryDep) -> list[Measurement]:
    return inventory.measurements(item_id)


@router.get("/items/{item_id}/measurements/{measurement_id}/photo")
def measurement_photo(item_id: int, measurement_id: int, inventory: InventoryDep) -> Response:
    """The prepared photo the measurement's coordinates refer to."""
    return Response(inventory.measurement_photo(item_id, measurement_id), media_type="image/jpeg")
