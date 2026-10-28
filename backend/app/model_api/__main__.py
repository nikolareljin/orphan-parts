"""`python -m app.model_api check`: confirm the key, the mode and the ledger state."""

import asyncio
import json
import sys

from app.config import get_settings
from app.model_api.client import ModelApiClient
from app.model_api.ledger import CostLedger


async def _check() -> int:
    settings = get_settings()
    ledger = CostLedger(settings.spend_cap_usd, settings.spend_ledger_path)
    client = ModelApiClient(settings, ledger)
    try:
        result = await client.check()
    finally:
        await client.aclose()
    result["spend"] = ledger.summary().model_dump()
    print(json.dumps(result, indent=2))
    return 0 if result["reachable"] in (True, None) else 1


def main(argv: list[str]) -> int:
    if argv[:1] != ["check"]:
        print("usage: python -m app.model_api check", file=sys.stderr)
        return 2
    return asyncio.run(_check())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
