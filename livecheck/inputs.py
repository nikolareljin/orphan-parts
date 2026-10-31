"""The demo set's own inputs: a label photo, a voice note and a listing text from demo/.

A file named in demo/set.yaml that is not in the tree (the photos and notes are the owner's,
written by ``./dev demo-scrub``) is stood in for by one drawn or synthesized here, so the check
runs on any clone. Nothing here is personal data: the label values are the
ones the recorded extract stub already answers with."""

import math
import struct
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

# the demo folder: beside this package in a clone, /demo in the backend container
DEMO_DIRS = [Path(__file__).resolve().parents[1] / "demo", Path("/demo")]
LABEL_LINES = [
    "ORBITAL POWER",
    "AC ADAPTER  MODEL OP-65N",
    "INPUT: 100-240V ~ 1.5A 50-60Hz",
    "OUTPUT: 19.5V  3.33A  65W",
]
LISTING_TEXT = (
    "DEMO DATA, a written example. Laptop power adapter, 65 W, 19.5 V 3.33 A, barrel plug,"
    " cable intact, tested on a laptop. Pick up any evening."
)


@dataclass
class DemoItem:
    """The item the check is run on: the set's adapter when the set names one, else a stand-in."""

    key: str
    name: str
    item_type: str
    profile: str
    condition: str
    tests_done: str
    fields: dict[str, str]
    photos: list[str]
    voice_note: str


def demo_dir() -> Path | None:
    for candidate in DEMO_DIRS:
        if (candidate / "set.yaml").is_file():
            return candidate
    return None


def _items(base: Path | None) -> list[dict[str, object]]:
    if base is None:
        return []
    try:
        data = yaml.safe_load((base / "set.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def currency_country(base: Path | None) -> tuple[str, str]:
    """The set's currency and country for the price call; the defaults when it names none."""
    currency, country = "USD", "US"
    if base is None:
        return currency, country
    try:
        data = yaml.safe_load((base / "set.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return currency, country
    if isinstance(data, dict):
        currency = str(data.get("currency") or currency)
        country = str(data.get("country") or country)
    return currency, country


def demo_item(base: Path | None, key: str = "adapter") -> DemoItem:
    """The set's item by key, else its first item with a photo, else the stand-in adapter."""
    items = _items(base)
    chosen = next((i for i in items if i.get("key") == key), None)
    if chosen is None:
        chosen = next((i for i in items if i.get("photos")), None)
    if chosen is None:
        return DemoItem(
            key="adapter",
            name="Laptop power adapter",
            item_type="power adapter",
            profile="power_adapter",
            condition="works",
            tests_done="",
            fields={},
            photos=[],
            voice_note="",
        )
    raw_fields = chosen.get("fields") or {}
    fields = {str(k): str(v) for k, v in raw_fields.items()} if isinstance(raw_fields, dict) else {}
    photos = chosen.get("photos") or []
    return DemoItem(
        key=str(chosen.get("key") or key),
        name=str(chosen.get("name") or ""),
        item_type=str(chosen.get("item_type") or ""),
        profile=str(chosen.get("profile") or ""),
        condition=str(chosen.get("condition") or ""),
        tests_done=str(chosen.get("tests_done") or ""),
        fields=fields,
        photos=[str(p) for p in photos] if isinstance(photos, list) else [],
        voice_note=str(chosen.get("voice_note") or ""),
    )


def label_photo(base: Path | None, item: DemoItem) -> tuple[bytes, str]:
    """The item's first photo that is in the tree, else a label drawn here."""
    for name in item.photos:
        if base is not None and (base / name).is_file():
            return (base / name).read_bytes(), f"demo/{name}"
    return drawn_label(), "a label drawn here (no photo under demo/photos)"


def drawn_label() -> bytes:
    """A plain label: dark print on a light plate, the values the extract stub answers with."""
    image = Image.new("RGB", (960, 600), (236, 234, 228))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 920, 560), outline=(60, 60, 60), width=4)
    try:
        font = ImageFont.load_default(size=44)
    except TypeError:  # an older Pillow without sized default fonts
        font = ImageFont.load_default()
    y = 110
    for line in LABEL_LINES:
        draw.text((90, y), line, fill=(30, 30, 30), font=font)
        y += 100
    out = BytesIO()
    image.save(out, "JPEG", quality=90)
    return out.getvalue()


def voice_note(base: Path | None, item: DemoItem) -> tuple[bytes, str]:
    """The item's note when it is in the tree, else the first WAV under demo/notes, else a
    one-second tone made here (the call is the proof; a tone transcribes to nothing)."""
    if base is not None:
        if item.voice_note and (base / item.voice_note).is_file():
            return (base / item.voice_note).read_bytes(), f"demo/{item.voice_note}"
        notes = sorted((base / "notes").glob("*.wav")) if (base / "notes").is_dir() else []
        if notes:
            return notes[0].read_bytes(), f"demo/notes/{notes[0].name}"
    return tone_wav(), "a one-second tone made here (no WAV under demo/notes)"


def tone_wav(seconds: float = 1.0, rate: int = 16000, hz: float = 440.0) -> bytes:
    frames = int(seconds * rate)
    samples = bytearray()
    for n in range(frames):
        samples += struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * n / rate)))
    out = BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(samples))
    return out.getvalue()


def wav_seconds(data: bytes) -> float:
    try:
        with wave.open(BytesIO(data)) as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
    except (wave.Error, EOFError):
        return 0.0
    return float(frames) / float(rate) if rate > 0 else 0.0


def listing_text(base: Path | None) -> tuple[str, str]:
    """The first written listing under demo/listings, else the line kept here."""
    if base is not None and (base / "listings").is_dir():
        files = sorted((base / "listings").glob("*.txt"))
        if files:
            try:
                text = files[0].read_text(encoding="utf-8").strip()
                return text, f"demo/listings/{files[0].name}"
            except (OSError, UnicodeDecodeError):
                pass
    return LISTING_TEXT, "a listing line kept here (no text under demo/listings)"
