"""Command line: python -m app.segment photo.jpg [--concepts item,label] [--out DIR]

Prints the regions as JSON (without the image payloads). With --out, writes overlay.jpg and
one crop per region into DIR. Honours the same settings as the service, so OPL_FAKE_API=1
answers from the recorded fixtures.
"""

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

from app.config import get_settings
from app.extract.imaging import BadImageError
from app.model_api import CostLedger, ModelApiClient, ModelApiError
from app.segment.schema import Segmentation
from app.segment.service import Segmenter


async def _run(photo: Path, concepts: list[str] | None) -> Segmentation:
    settings = get_settings()
    ledger = CostLedger(settings.spend_cap_usd, settings.spend_ledger_path)
    client = ModelApiClient(settings, ledger)
    try:
        return await Segmenter(settings, client).segment(photo.read_bytes(), concepts)
    finally:
        await client.aclose()


def _write(result: Segmentation, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "overlay.jpg").write_bytes(base64.b64decode(result.overlay.split(",", 1)[1]))
    counts: dict[str, int] = {}
    for region in result.regions:
        counts[region.concept] = counts.get(region.concept, 0) + 1
        name = f"{region.concept}-{counts[region.concept]}.jpg"
        (out / name).write_bytes(base64.b64decode(region.crop.split(",", 1)[1]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.segment")
    parser.add_argument("photo", type=Path)
    parser.add_argument("--concepts", help="comma separated, default item,label,connector")
    parser.add_argument("--out", type=Path, help="directory for overlay.jpg and the crops")
    args = parser.parse_args(argv)
    if not args.photo.is_file():
        print(f"segment: not a file: {args.photo}", file=sys.stderr)
        return 2
    concepts = [c for c in (args.concepts or "").split(",") if c.strip()] or None
    try:
        result = asyncio.run(_run(args.photo, concepts))
    except (BadImageError, ModelApiError) as exc:
        print(f"segment: {exc}", file=sys.stderr)
        return 1
    if args.out:
        _write(result, args.out)
    summary = result.model_dump(exclude={"overlay": True, "regions": {"__all__": {"crop"}}})
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
