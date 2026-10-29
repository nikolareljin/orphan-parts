"""A spoken note about an item: transcribed with Muse Voice Transcribe, kept as the owner's
words with the source ``voice_note``. The owner said it, so it is accepted as stated."""

import logging
import wave
from io import BytesIO

from pydantic import BaseModel

from app.config import Settings
from app.inventory import Inventory
from app.inventory.schema import FieldCreate, Item
from app.model_api import ModelApiClient

log = logging.getLogger("app.voice")

FIELD = "condition_notes"


class BadAudioError(ValueError):
    pass


class VoiceNote(BaseModel):
    transcript: str
    seconds: float
    field: str
    model: str
    from_fixture: bool
    cost_usd: float
    item: Item


def wav_seconds(data: bytes) -> float:
    """The clip's length, from the WAV header. Anything that is not a WAV file is refused."""
    try:
        with wave.open(BytesIO(data)) as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
    except (wave.Error, EOFError) as exc:
        raise BadAudioError("the recording is not a WAV file") from exc
    if rate <= 0 or frames <= 0:
        raise BadAudioError("the recording is empty")
    return float(frames) / float(rate)


class VoiceNotes:
    def __init__(self, settings: Settings, client: ModelApiClient, inventory: Inventory) -> None:
        self.settings = settings
        self.client = client
        self.inventory = inventory

    async def note(self, item_id: int, audio: bytes) -> VoiceNote:
        self.inventory.get(item_id)
        seconds = wav_seconds(audio)
        if seconds > self.settings.voice_max_seconds:
            raise BadAudioError(
                f"the recording is {seconds:.0f} s; at most {self.settings.voice_max_seconds} s"
            )
        transcript = await self.client.transcribe(audio)
        if not transcript.text:
            raise BadAudioError("nothing was heard in the recording")
        item = self.inventory.add_field(
            item_id,
            FieldCreate(field=FIELD, value=transcript.text, raw=transcript.text),
            source="voice_note",
        )
        log.info(
            "voice note",
            extra={"item_id": item_id, "seconds": seconds, "usd": transcript.cost_usd},
        )
        return VoiceNote(
            transcript=transcript.text,
            seconds=round(seconds, 2),
            field=FIELD,
            model=transcript.model,
            from_fixture=transcript.from_fixture,
            cost_usd=transcript.cost_usd,
            item=item,
        )
