from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError

from app.api.deps import CapturesDep
from app.api.model_errors import as_http
from app.captures import Capture, CaptureCreate, CaptureError, CaptureList
from app.listing import BadAudioError

router = APIRouter(prefix="/api", tags=["captures"])

PhotosPart = Annotated[list[UploadFile] | None, File(description="Photos, one to MAX_PHOTOS")]
ClipPart = Annotated[UploadFile | None, File(description="A short MP4 clip from the phone")]
AudioPart = Annotated[UploadFile | None, File(description="A WAV note, hold to talk")]
RequestPart = Annotated[str | None, Form(description="The text part, as JSON (CaptureCreate)")]


def _refused(exc: CaptureError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.post("/captures", response_model=Capture, status_code=status.HTTP_201_CREATED)
async def create_capture(
    captures: CapturesDep,
    photos: PhotosPart = None,
    clip: ClipPart = None,
    audio: AudioPart = None,
    request: RequestPart = None,
) -> Capture:
    """What the phone captured in one go: photos (re-encoded on arrival, pixels only), a clip,
    a spoken note and a line of text. Kept privately until processed, and after, until deleted."""
    try:
        spec = CaptureCreate.model_validate_json(request) if request else CaptureCreate()
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"loc": ["body", "request", *e["loc"]], "msg": e["msg"]} for e in exc.errors()],
        ) from exc
    s = captures.settings
    photo_cap, clip_cap = s.max_upload_mb * 1024 * 1024, s.max_clip_mb * 1024 * 1024
    for upload in photos or []:
        if upload.size is not None and upload.size > photo_cap:
            raise HTTPException(
                status_code=400, detail=f"a photo is larger than {s.max_upload_mb} MB"
            )
    if clip is not None and clip.size is not None and clip.size > clip_cap:
        raise HTTPException(status_code=400, detail=f"the clip is larger than {s.max_clip_mb} MB")
    if audio is not None and audio.size is not None and audio.size > photo_cap:
        raise HTTPException(status_code=400, detail=f"the note is larger than {s.max_upload_mb} MB")
    photo_data = [await p.read() for p in photos or []]
    clip_data = await clip.read() if clip is not None else None
    audio_data = await audio.read() if audio is not None else None
    try:
        return captures.create(spec, photo_data, clip_data, audio_data)
    except CaptureError as exc:
        raise _refused(exc) from exc


@router.get("/captures", response_model=CaptureList)
def list_captures(captures: CapturesDep) -> CaptureList:
    """Every capture not deleted, newest first."""
    return CaptureList(captures=captures.captures())


@router.get("/captures/{capture_id}", response_model=Capture)
def get_capture(capture_id: int, captures: CapturesDep) -> Capture:
    return captures.capture(capture_id)


@router.get("/captures/{capture_id}/photos/{n}", response_class=Response)
def capture_photo(capture_id: int, n: int, captures: CapturesDep) -> Response:
    return Response(captures.photo(capture_id, n), media_type="image/jpeg")


@router.get("/captures/{capture_id}/clip", response_class=Response)
def capture_clip(capture_id: int, captures: CapturesDep) -> Response:
    return Response(captures.media(capture_id, "clip.mp4"), media_type="video/mp4")


@router.get("/captures/{capture_id}/note", response_class=Response)
def capture_note(capture_id: int, captures: CapturesDep) -> Response:
    return Response(captures.media(capture_id, "note.wav"), media_type="audio/wav")


@router.post("/captures/{capture_id}/process", response_model=Capture)
async def process_capture(capture_id: int, captures: CapturesDep) -> Capture:
    """The photos read into an item (the label found first when asked), the note transcribed
    onto it as the owner's words, the line kept as its notes. A failure is recorded on the
    capture and the media stays for another try."""
    try:
        return await captures.process(capture_id)
    except CaptureError as exc:
        raise _refused(exc) from exc
    except BadAudioError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise as_http(exc) from exc


@router.delete("/captures/{capture_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_capture(capture_id: int, captures: CapturesDep) -> None:
    """The files go and the capture is hidden; an item made from it stays."""
    captures.delete(capture_id)
