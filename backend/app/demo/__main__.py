"""Command line: python -m app.demo <load|record|samples|scrub> [options]

  load    [--set demo/set.yaml] [--reset]  load the set through the services, in whatever mode
                                           the settings say (fixture mode replays, no key needed)
  record  [--set demo/set.yaml] [--reset]  the same run with OPL_RECORD_FIXTURES=1 forced, so
                                           every model answer is written as a fixture, then every
                                           reading a sample click can ask for; needs a key
  samples [--set demo/set.yaml]            only the sample readings: recorded in record mode,
                                           checked in fixture mode (each one without a recording
                                           is named, and the exit status is 1)
  scrub  <raw dir> [--out demo/photos] [--notes demo/notes]
                                           raw photos re-encoded without metadata, WAV notes copied

--reset removes the inventory file first, so the set is the whole inventory.
"""

import asyncio
import os
import sys
from pathlib import Path

import yaml

from app.config import Settings, get_settings
from app.demo.schema import DemoSet, Outcome
from app.demo.service import Loader, load_set, reset, scrub
from app.extract import Extractor
from app.find import Finder
from app.inventory import Inventory
from app.listing import Lister, VoiceNotes
from app.match import Assessor
from app.model_api import CostLedger, ModelApiClient
from app.picture import Pictures
from app.profiles import Profiles
from app.projects import Planner, Templates
from app.samples import SampleReader, Samples, SamplesOutcome, record_samples
from app.segment import Segmenter
from app.value import Valuer

DEFAULT_SET = Path("demo/set.yaml")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "demo" / "set.yaml").is_file() or (parent / ".git").exists():
            return parent
    return Path.cwd()


def _set_path(given: str | None) -> Path:
    if given:
        return Path(given)
    for root in (Path.cwd(), _repo_root(), Path("/")):
        candidate = root / DEFAULT_SET
        if candidate.is_file():
            return candidate
    return DEFAULT_SET


def build_loader(settings: Settings) -> tuple[Loader, ModelApiClient]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    ledger = CostLedger(settings.spend_cap_usd, settings.spend_ledger_path)
    client = ModelApiClient(settings, ledger)
    inventory = Inventory(settings)
    extractor = Extractor(settings, client)
    profiles = Profiles()
    assessor = Assessor(profiles, inventory)
    finder = Finder(settings, client, inventory, profiles, extractor, assessor)
    templates = Templates()
    # an item of the set that names a picture asks for it whatever PICTURE_ENABLED says: the
    # set is the owner's own run, and fixture mode replays the drawing or skips it
    pictures = Pictures(
        settings.model_copy(update={"picture_enabled": True}), client, inventory, templates
    )
    loader = Loader(
        settings,
        client,
        inventory,
        extractor,
        Lister(settings, client, inventory),
        VoiceNotes(settings, client, inventory),
        Valuer(settings, client, inventory),
        finder,
        Planner(settings, client, inventory, templates, finder),
        pictures,
    )
    return loader, client


def build_sample_reader(settings: Settings, client: ModelApiClient, set_file: Path) -> SampleReader:
    return SampleReader(
        settings,
        Samples(settings, set_file),
        Extractor(settings, client),
        Segmenter(settings, client),
    )


async def _run(settings: Settings, demo: DemoSet, base: Path) -> Outcome:
    loader, client = build_loader(settings)
    try:
        return await loader.run(demo, base)
    finally:
        await client.aclose()


async def _samples(settings: Settings, set_file: Path) -> SamplesOutcome:
    ledger = CostLedger(settings.spend_cap_usd, settings.spend_ledger_path)
    client = ModelApiClient(settings, ledger)
    try:
        return await record_samples(build_sample_reader(settings, client, set_file))
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("load", "record", "samples", "scrub"):
        print(__doc__, file=sys.stderr)
        return 2
    what = args.pop(0)
    if what == "scrub":
        if not args or args[0].startswith("--"):
            print(
                "usage: python -m app.demo scrub <raw dir> [--out DIR] [--notes DIR]",
                file=sys.stderr,
            )
            return 2
        raw = Path(args.pop(0))
        out = Path("demo/photos")
        notes: Path | None = None
        while len(args) >= 2 and args[0] in ("--out", "--notes"):
            if args[0] == "--out":
                out = Path(args[1])
            else:
                notes = Path(args[1])
            args = args[2:]
        if not raw.is_dir():
            print(f"demo: {raw} is not a directory", file=sys.stderr)
            return 1
        for line in scrub(raw, out, notes):
            print(line)
        return 0
    set_file: str | None = None
    do_reset = False
    while args:
        arg = args.pop(0)
        if arg == "--set" and args:
            set_file = args.pop(0)
        elif arg == "--reset":
            do_reset = True
        else:
            print(f"demo: unknown argument {arg}", file=sys.stderr)
            return 2
    path = _set_path(set_file)
    if not path.is_file():
        print(f"demo: no set at {path}", file=sys.stderr)
        return 1
    if what == "record":
        os.environ["OPL_RECORD_FIXTURES"] = "1"
        os.environ.pop("OPL_FAKE_API", None)
        clear = getattr(get_settings, "cache_clear", None)
        if clear is not None:
            clear()
    try:
        settings = get_settings()
    except ValueError as exc:
        print(f"demo: the settings are refused: {exc}", file=sys.stderr)
        return 1
    if what == "record" and settings.model_api_mode != "record":
        print("demo: record needs a key in the environment and fixture mode off", file=sys.stderr)
        return 1
    try:
        demo = load_set(path)
    except (ValueError, yaml.YAMLError) as exc:
        print(f"demo: {path}: {exc}", file=sys.stderr)
        return 1
    if what == "samples":
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        found = asyncio.run(_samples(settings, path))
        for line in found.lines():
            print(line)
        return 1 if found.missing or found.failed else 0
    if do_reset:
        for name in reset(settings):
            print(f"removed {name}")
    outcome = asyncio.run(_run(settings, demo, path.parent))
    for line in outcome.lines():
        print(line)
    failed = bool(outcome.skipped)
    if what == "record":
        # the readings a sample click asks for, kept beside the set's own
        found = asyncio.run(_samples(settings, path))
        for line in found.lines():
            print(line)
        failed = failed or bool(found.missing or found.failed)
    if what == "record" and failed:
        # the paid run: what it skipped has no recording, so the run is not done
        print("demo: part of the set or its samples was skipped; see above", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
