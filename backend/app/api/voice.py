from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import VoiceDep
from app.api.model_errors import as_http
from app.listing import BadAudioError, VoiceNote

router = APIRouter(prefix="/api", tags=["listing"])


@router.post("/items/{item_id}/voice", response_model=VoiceNote)
async def voice_note(
    item_id: int,
    audio: Annotated[UploadFile, File(description="One WAV recording, at most ten minutes")],
    voice: VoiceDep,
) -> VoiceNote:
    """Say what you know about the item. Muse Voice Transcribe turns the recording into text,
    kept on the item as the owner's own words (field ``condition_notes``, source
    ``voice_note``), accepted as stated; the draft and the listing read it from there."""
    max_mb = voice.settings.max_upload_mb
    if audio.size is not None and audio.size > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"the recording is larger than {max_mb} MB")
    data = await audio.read()
    try:
        return await voice.note(item_id, data)
    except BadAudioError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise as_http(exc) from exc
