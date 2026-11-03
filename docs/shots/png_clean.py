"""The docs' screenshots, published with their pixels alone (docs/shots/generate.sh).

Usage: python3 -I png_clean.py SRC DEST [--force]
       python3 -I png_clean.py --check DIR

Every SRC/<guide>/<name>.png is written to DEST/<guide>/<name>.png with only the chunks that
carry the picture (IHDR, PLTE, tRNS, IDAT, IEND): no text, time, color profile or EXIF. A shot
with the same pixels as the one already in DEST is left as it was (the file untouched), unless
--force. --check DIR fails when any PNG under DIR carries another
chunk. Standard library only.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

SIGNATURE = b"\x89PNG\r\n\x1a\n"
KEEP = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}


def chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(SIGNATURE):
        raise ValueError("not a PNG")
    out, at = [], len(SIGNATURE)
    while at < len(data):
        (length,) = struct.unpack(">I", data[at : at + 4])
        kind = data[at + 4 : at + 8]
        out.append((kind, data[at + 8 : at + 8 + length]))
        at += 12 + length
        if kind == b"IEND":
            break
    return out


def clean(data: bytes) -> bytes:
    parts = [SIGNATURE]
    for kind, body in chunks(data):
        if kind in KEEP:
            crc = zlib.crc32(kind + body) & 0xFFFFFFFF
            parts.append(struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc))
    return b"".join(parts)


def same_pixels(new: bytes, old: bytes) -> bool:
    """Whether two PNGs hold the same picture: the same header and the same decompressed data."""
    if new == old:
        return True
    try:
        a, b = chunks(new), chunks(old)
        head_a = next(body for kind, body in a if kind == b"IHDR")
        head_b = next(body for kind, body in b if kind == b"IHDR")
        data_a = zlib.decompress(b"".join(body for kind, body in a if kind == b"IDAT"))
        data_b = zlib.decompress(b"".join(body for kind, body in b if kind == b"IDAT"))
    except (ValueError, StopIteration, zlib.error, struct.error):
        return False
    return head_a == head_b and data_a == data_b


def publish(src: Path, dest: Path, force: bool) -> int:
    written = kept = 0
    for png in sorted(src.rglob("*.png")):
        target = dest / png.relative_to(src)
        data = clean(png.read_bytes())
        if not force and target.exists() and same_pixels(data, target.read_bytes()):
            kept += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written += 1
    print(f"shots: {written} written, {kept} unchanged")
    return 0


def check(root: Path) -> int:
    bad = []
    for png in sorted(root.rglob("*.png")):
        extra = sorted({kind.decode("latin-1") for kind, _ in chunks(png.read_bytes())} - {k.decode() for k in KEEP})
        if extra:
            bad.append(f"{png}: {', '.join(extra)}")
    for line in bad:
        print(f"metadata in a docs shot: {line}", file=sys.stderr)
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--check":
        return check(Path(argv[1]))
    args = [a for a in argv if a != "--force"]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    return publish(Path(args[0]), Path(args[1]), "--force" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
