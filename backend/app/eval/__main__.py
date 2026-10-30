"""Command line: python -m app.eval <run|export|diff> [options]

run    [--set demo/set.yaml] [--out eval/] [--keep]
                      load the set as `python -m app.demo load` does, in whatever mode the
                      settings say (fixture mode replays, no key needed), score it by the
                      rules and write report.json, report.md and charts/ under --out;
                      the inventory is reset first unless --keep
export [--out eval/]  write train.jsonl: one chat-format line per item with accepted
                      observed values, from the inventory as it stands
diff   a.json b.json  two reports side by side
"""

import asyncio
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.demo.__main__ import _set_path, build_loader
from app.demo.service import load_set, reset
from app.eval.service import Report, diff, score, training_lines, write_report
from app.inventory import Inventory
from app.match import Assessor
from app.profiles import Profiles

DEFAULT_OUT = Path("eval")


def _out_path(given: str | None) -> Path:
    if given:
        return Path(given)
    root = _set_path(None).resolve().parent.parent
    return root / DEFAULT_OUT if (root / "demo").is_dir() else DEFAULT_OUT


async def run(settings: Settings, set_file: Path, out: Path, *, keep: bool) -> int:
    try:
        demo = load_set(set_file)
    except (ValueError, yaml.YAMLError) as exc:
        print(f"eval: {set_file}: {exc}", file=sys.stderr)
        return 1
    if not keep:
        for name in reset(settings):
            print(f"removed {name}")
    loader, client = build_loader(settings)
    try:
        outcome = await loader.run(demo, set_file.parent)
    finally:
        await client.aclose()
    assessor = Assessor(Profiles(), loader.inventory)
    report = score(
        demo, outcome, loader.inventory, assessor, loader.planner, loader.ids, str(set_file)
    )
    for path in write_report(report, out):
        print(f"wrote {path}")
    s = report.summary
    print(
        f"mode {s.mode}: {s.items_loaded}/{s.items} item(s), {s.fields_read} field(s) read,"
        f" {s.matches}/{s.expected} expected value(s) matched, {s.fits_right}/{s.fits_total}"
        f" fit verdict(s) right, proposals {s.proposals_kept} kept of {s.proposals_proposed},"
        f" {s.stub_answers} stub answer(s), {s.cost_usd:.4f} USD"
    )
    return 0


def export(settings: Settings, out: Path) -> int:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    lines = training_lines(Inventory(settings))
    out.mkdir(parents=True, exist_ok=True)
    path = out / "train.jsonl"
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    print(f"wrote {path}: {len(lines)} line(s)")
    return 0


def _report(path: Path) -> Report | None:
    try:
        return Report.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as exc:
        print(f"eval: {path}: {exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("run", "export", "diff"):
        print(__doc__, file=sys.stderr)
        return 2
    what = args.pop(0)
    if what == "diff":
        if len(args) != 2:
            print("usage: python -m app.eval diff a.json b.json", file=sys.stderr)
            return 2
        a, b = _report(Path(args[0])), _report(Path(args[1]))
        if a is None or b is None:
            return 1
        for line in diff(a, b):
            print(line)
        return 0
    set_file: str | None = None
    out: str | None = None
    keep = False
    while args:
        arg = args.pop(0)
        if arg == "--set" and args:
            set_file = args.pop(0)
        elif arg == "--out" and args:
            out = args.pop(0)
        elif arg == "--keep":
            keep = True
        else:
            print(f"eval: unknown argument {arg}", file=sys.stderr)
            return 2
    try:
        settings = get_settings()
    except ValueError as exc:
        print(f"eval: the settings are refused: {exc}", file=sys.stderr)
        return 1
    out_dir = _out_path(out)
    if what == "export":
        return export(settings, out_dir)
    path = _set_path(set_file)
    if not path.is_file():
        print(f"eval: no set at {path}", file=sys.stderr)
        return 1
    return asyncio.run(run(settings, path, out_dir, keep=keep))


if __name__ == "__main__":
    sys.exit(main())
