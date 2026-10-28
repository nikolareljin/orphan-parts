"""Command line: python -m app.extract photo.jpg [more photos]

Prints the extraction as JSON. Honours the same settings as the service, so
OPL_FAKE_API=1 answers from the recorded fixtures and a key in .env calls Muse Spark.
"""

import asyncio
import sys
from pathlib import Path

from app.config import get_settings
from app.extract.imaging import BadImageError
from app.extract.service import Extractor
from app.model_api import CostLedger, ModelApiClient, ModelApiError


async def _run(paths: list[Path]) -> str:
    settings = get_settings()
    ledger = CostLedger(settings.spend_cap_usd, settings.spend_ledger_path)
    client = ModelApiClient(settings, ledger)
    try:
        result = await Extractor(settings, client).extract([p.read_bytes() for p in paths])
    finally:
        await client.aclose()
    return result.model_dump_json(indent=2)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    paths = [Path(a) for a in args]
    if not paths or any(not p.is_file() for p in paths):
        print("usage: python -m app.extract <photo> [<photo> ...]", file=sys.stderr)
        return 2
    try:
        print(asyncio.run(_run(paths)))
    except (BadImageError, ModelApiError) as exc:
        print(f"extract: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
