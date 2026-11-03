"""A rough narration from a local text-to-speech, for timing only: each section of a script
(scripts/main.md) spoken from its start time. The owner's own voice replaces it.

Usage: python3 video/tts.py <espeak-ng|espeak|pico2wave> <script.md> <out.wav>
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

SECTION = re.compile(r"^## (\d+):(\d\d) to (\d+):(\d\d)")


def sections(path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, list[str]]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = SECTION.match(raw)
        if m:
            out.append((int(m.group(1)) * 60 + int(m.group(2)), []))
        elif out and raw.startswith("> "):
            out[-1][1].append(raw[2:].strip())
    return [(start, " ".join(lines)) for start, lines in out if lines]


def speak(engine: str, text: str, wav: Path) -> None:
    if engine == "pico2wave":
        cmd = ["pico2wave", "-l", "en-US", "-w", str(wav), text]
    else:
        cmd = [engine, "-v", "en-us", "-s", "150", "-w", str(wav), text]
    subprocess.run(cmd, check=True, capture_output=True)


def main(engine: str, script: str, out: str) -> None:
    parts = sections(Path(script))
    with tempfile.TemporaryDirectory() as tmp:
        inputs: list[str] = []
        mix: list[str] = []
        for i, (start, text) in enumerate(parts):
            wav = Path(tmp) / f"{i}.wav"
            speak(engine, text, wav)
            inputs += ["-i", str(wav)]
            mix.append(f"[{i}:a]aresample=48000,adelay={start * 1000}|{start * 1000}[a{i}]")
        graph = ";".join(mix) + ";" + "".join(f"[a{i}]" for i in range(len(parts))) + f"amix=inputs={len(parts)}:normalize=0[a]"
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[a]", "-ac", "2", out], check=True)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
