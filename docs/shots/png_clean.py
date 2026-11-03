"""The docs' screenshots, published with their pixels alone (docs/shots/generate.sh).

Usage: python3 -I png_clean.py SRC DEST [--force]
       python3 -I png_clean.py --check DIR

Every SRC/<guide>/<name>.png is written to DEST/<guide>/<name>.png with only the chunks that
carry the picture (IHDR, PLTE, tRNS, IDAT, IEND): no text, time, color profile or EXIF. A shot
that is the same picture as the one already in DEST (equal, or a few pixels off by a few levels:
decoding noise) is left as it was, unless --force. --check DIR fails when any PNG under DIR carries another
chunk. Standard library only.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

SIGNATURE = b"\x89PNG\r\n\x1a\n"
KEEP = {b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"}
NOISE_PIXELS = 200
NOISE_DELTA = 12


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


def pixels(data: bytes) -> tuple[bytes, bytes]:
    """The header and the unfiltered scanlines of an 8-bit, non-interlaced PNG."""
    found = chunks(data)
    head = next(body for kind, body in found if kind == b"IHDR")
    width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", head)
    if depth != 8 or interlace:
        raise ValueError("only 8-bit, non-interlaced PNGs are compared")
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    raw = zlib.decompress(b"".join(body for kind, body in found if kind == b"IDAT"))
    stride = width * bpp
    out = bytearray()
    prev = bytes(stride)
    for y in range(height):
        at = y * (stride + 1)
        kind, line = raw[at], bytearray(raw[at + 1 : at + 1 + stride])
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif kind == 2:
            line = bytearray((x + p) & 0xFF for x, p in zip(line, prev))
        elif kind == 3:
            for i in range(stride):
                line[i] = (line[i] + (((line[i - bpp] if i >= bpp else 0) + prev[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                a_ = line[i - bpp] if i >= bpp else 0
                b_ = prev[i]
                c_ = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b_ - c_), abs(a_ - c_), abs(a_ + b_ - 2 * c_)
                line[i] = (line[i] + (a_ if pa <= pb and pa <= pc else b_ if pb <= pc else c_)) & 0xFF
        prev = bytes(line)
        out += prev
    return head, bytes(out)


def same_picture(new: bytes, old: bytes) -> bool:
    """The same picture: equal data, or at most NOISE_PIXELS pixels off by at most NOISE_DELTA
    in a channel (Chromium decodes and scales a photo with a little noise from run to run)."""
    if new == old:
        return True
    try:
        head_a, data_a = pixels(new)
        head_b, data_b = pixels(old)
    except (ValueError, StopIteration, KeyError, zlib.error, struct.error):
        return False
    if head_a != head_b or len(data_a) != len(data_b):
        return False
    if data_a == data_b:
        return True
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[head_a[9]]
    off = 0
    for i in range(0, len(data_a), bpp):
        pa, pb = data_a[i : i + bpp], data_b[i : i + bpp]
        if pa != pb:
            if max(abs(x - y) for x, y in zip(pa, pb)) > NOISE_DELTA:
                return False
            off += 1
            if off > NOISE_PIXELS:
                return False
    return True


def publish(src: Path, dest: Path, force: bool) -> int:
    written = kept = 0
    for png in sorted(src.rglob("*.png")):
        target = dest / png.relative_to(src)
        data = clean(png.read_bytes())
        if not force and target.exists() and same_picture(data, target.read_bytes()):
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
