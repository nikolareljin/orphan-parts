"""The narrator: a synthetic voice reading the captions, offline, with Piper.

One clip per caption of an SRT file (scripts/main.srt, scripts/short.srt), each started at its
caption's time and fitted to its window: a clip that runs over is spoken faster through Piper's
length_scale, never more than 1.15x; a line that still does not fit is an error, and its
wording is what changes (scripts/*.md, then captions.py), never the pace. The clips are laid on
one track, normalized to -16 LUFS integrated with the peaks under -1.5 dBTP, no room tone.

Usage: python3 video/tts.py <captions.srt> <out.wav> [--voice NAME|FILE.onnx] [--check]

Piper is found as $PIPER (the executable), else `piper` on PATH (pip install piper-tts, in a
virtual environment of its own); without it the script says so and exits 3. A voice is a name
from VOICES, looked up in $PIPER_VOICES (default ~/.cache/piper-voices) and downloaded there
once, its checksum verified, or the path of a .onnx model with its .onnx.json beside it. The
models are never kept in the repository. --check reports each line's fit without writing.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

# voices whose model card allows use in a public video: the name, its folder on
# huggingface.co/rhasspy/piper-voices, the MD5 of the model and of its config, the license
VOICES = {
    "en_US-ljspeech-high": (
        "en/en_US/ljspeech/high",
        "dad093b5d2cff6a5fda99883ceda09d1",
        "de98fc398ddead60fb82d93bfafb3ad1",
        "public domain (LJ Speech dataset)",
    ),
    "en_US-norman-medium": (
        "en/en_US/norman/medium",
        "829cea515dc724d694b83b71e8083f9f",
        "975830d6f230f6eccf657d265de99eba",
        "public domain (LibriVox recordings)",
    ),
}
DEFAULT_VOICE = "en_US-ljspeech-high"
HUB = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

MAX_SPEEDUP = 1.15  # at most this much faster than the voice's natural pace
BREATH = 0.08  # seconds kept free before the next caption
TARGET_LUFS = -16.0
PEAK_DBTP = -1.5
RATE = 48000

CUE = re.compile(r"(\d+):(\d\d):(\d\d),(\d{3}) --> (\d+):(\d\d):(\d\d),(\d{3})")
# how a few words are said, where the voice reads them wrong; the captions keep the spelling
SAY = {"SAM 3.1": "Sam three point one"}


def seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def cues(path: Path) -> list[tuple[float, float, str]]:
    """(start, end, text) per caption, the lines of a caption joined."""
    out: list[tuple[float, float, str]] = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = block.splitlines()
        for i, line in enumerate(lines):
            m = CUE.match(line.strip())
            if m:
                g = m.groups()
                text = " ".join(t.strip() for t in lines[i + 1 :] if t.strip())
                out.append((seconds(*g[:4]), seconds(*g[4:]), text))
                break
    return out


def piper() -> str:
    exe = os.environ.get("PIPER") or shutil.which("piper") or ""
    if not exe or not Path(exe).is_file():
        print("tts: Piper is not installed (set PIPER to its executable or put piper on PATH)", file=sys.stderr)
        sys.exit(3)
    return exe


def md5(path: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - the checksum the voice index publishes, not a secret
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def voice_model(voice: str) -> Path:
    """The .onnx of a voice: a path as given, or a known name, downloaded once."""
    if voice.endswith(".onnx"):
        model = Path(voice).expanduser()
        if not model.is_file() or not Path(f"{model}.json").is_file():
            sys.exit(f"tts: {model} and {model}.json are needed")
        return model
    if voice not in VOICES:
        sys.exit(f"tts: unknown voice {voice}; one of {', '.join(VOICES)}, or a path to a .onnx")
    folder, model_md5, config_md5, _ = VOICES[voice]
    cache = Path(os.environ.get("PIPER_VOICES") or Path.home() / ".cache" / "piper-voices")
    cache.mkdir(parents=True, exist_ok=True)
    for suffix, digest in ((".onnx", model_md5), (".onnx.json", config_md5)):
        target = cache / f"{voice}{suffix}"
        if target.is_file() and md5(target) == digest:
            continue
        print(f"tts: downloading {voice}{suffix} into {cache}", file=sys.stderr)
        part = target.with_suffix(target.suffix + ".part")
        urllib.request.urlretrieve(f"{HUB}/{folder}/{voice}{suffix}", part)  # noqa: S310 - a fixed https URL
        if md5(part) != digest:
            part.unlink()
            sys.exit(f"tts: {voice}{suffix} does not match its published checksum")
        part.replace(target)
    return cache / f"{voice}.onnx"


def ffmpeg(*args: str) -> str:
    done = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-y", *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        sys.exit(f"tts: ffmpeg failed: {done.stderr.strip()[-400:]}")
    return done.stderr


def duration(wav: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip() or 0)


TRIM = "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse"


def say(text: str) -> str:
    for words, said in SAY.items():
        text = text.replace(words, said)
    return " ".join(text.split())


def speak(exe: str, model: Path, texts: list[str], scale: float, tmp: Path, tag: str) -> list[Path]:
    """Lines at one length_scale, one Piper run (the model loads once), each clip's leading and
    trailing silence trimmed."""
    work = tmp / tag
    work.mkdir()
    (work / "in.txt").write_text("".join(say(t) + "\n" for t in texts), encoding="utf-8")
    subprocess.run(
        [exe, "-m", str(model), "-i", str(work / "in.txt"), "-d", str(work / "raw"), "--length-scale", f"{scale:.4f}", "--sentence-silence", "0"],
        capture_output=True,
        check=True,
    )
    # one WAV per line, named by a monotonic clock: in the order of the lines
    raw = sorted((work / "raw").glob("*.wav"), key=lambda p: int(p.stem))
    if len(raw) != len(texts):
        sys.exit(f"tts: Piper wrote {len(raw)} clips for {len(texts)} lines")
    out = []
    for i, wav in enumerate(raw):
        clip = work / f"line-{i}.wav"
        ffmpeg("-i", str(wav), "-af", f"{TRIM},aresample={RATE}", "-ac", "1", str(clip))
        out.append(clip)
    return out


def fit(exe: str, model: Path, texts: list[str], windows: list[float], tmp: Path) -> list[tuple[Path, float, float, float]]:
    """Per line: the clip, its length, its natural length and the speed-up used (1.0 = the
    natural pace, 0.0 = it does not fit at MAX_SPEEDUP)."""
    natural = speak(exe, model, texts, 1.0, tmp, "natural")
    out = []
    for i, (clip, window) in enumerate(zip(natural, windows)):
        length = duration(clip)
        result = (clip, length, length, 1.0)
        scale = window / length
        tries = 0
        while length > window and scale >= 1 / MAX_SPEEDUP - 1e-9 and tries < 4:
            faster = speak(exe, model, [texts[i]], scale, tmp, f"line-{i}-{tries}")[0]
            got = duration(faster)
            if got <= window:
                result = (faster, got, length, 1 / scale)
                break
            scale *= window / got * 0.99
            tries += 1
        else:
            if length > window:
                result = (clip, length, length, 0.0)
        out.append(result)
    return out


def loudness(wav: Path) -> tuple[float, float]:
    """Integrated loudness (LUFS) and true peak (dBTP), by ffmpeg's EBU R128 meter."""
    log = ffmpeg("-i", str(wav), "-af", "ebur128=peak=true", "-f", "null", "-")
    summary = log[log.rfind("Summary:") :]
    lufs = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    return (float(lufs.group(1)) if lufs else float("-inf"), float(peak.group(1)) if peak else float("-inf"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("srt", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--voice", default=os.environ.get("VIDEO_VOICE") or DEFAULT_VOICE)
    parser.add_argument("--check", action="store_true", help="report each line's fit, write nothing")
    args = parser.parse_args()
    exe = piper()
    model = voice_model(args.voice)
    lines = cues(args.srt)
    if not lines:
        sys.exit(f"tts: no captions in {args.srt}")
    placed: list[tuple[float, Path]] = []
    tight: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        windows = []
        for n, (start, end, _) in enumerate(lines):
            nxt = lines[n + 1][0] if n + 1 < len(lines) else end
            windows.append(max(end, nxt - BREATH) - start)
        fitted = fit(exe, model, [text for _, _, text in lines], windows, tmp)
        for n, ((start, _, text), window, (clip, got, natural, speed)) in enumerate(zip(lines, windows, fitted)):
            state = "natural" if speed == 1.0 else (f"{speed:.2f}x" if speed else "DOES NOT FIT")
            print(f"  {n + 1:>2} {start:7.2f}s window {window:5.2f}s spoken {got:5.2f}s (natural {natural:5.2f}s) {state}  {text[:48]}")
            if not speed:
                tight.append(f"caption {n + 1} at {start:.2f}s needs {natural / MAX_SPEEDUP:.2f}s of {window:.2f}s: {text}")
            placed.append((start, clip))
        if tight:
            sys.exit("tts: tighten these lines in the script, then run captions.py again:\n  " + "\n  ".join(tight))
        if args.check:
            return
        inputs: list[str] = []
        chain: list[str] = []
        for i, (start, clip) in enumerate(placed):
            inputs += ["-i", str(clip)]
            ms = round(start * 1000)
            chain.append(f"[{i}:a]adelay={ms}:all=1[a{i}]")
        mix = tmp / "mix.wav"
        graph = ";".join(chain) + ";" + "".join(f"[a{i}]" for i in range(len(placed))) + f"amix=inputs={len(placed)}:normalize=0:dropout_transition=0[m]"
        ffmpeg(*inputs, "-filter_complex", graph, "-map", "[m]", "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s24le", str(mix))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        # a gain to the target and a limiter for the odd peak, mono to both sides; measured
        # again on the result and corrected once, since the limiter takes a little off
        limit = 10 ** (PEAK_DBTP / 20)
        lufs, _ = loudness(mix)
        gain = TARGET_LUFS - lufs
        for _ in range(3):
            ffmpeg("-i", str(mix), "-af", f"volume={gain:.2f}dB,alimiter=limit={limit:.4f}:level=disabled:attack=1:release=50,aresample={RATE}", "-ac", "2", "-c:a", "pcm_s16le", str(args.out))
            lufs, _ = loudness(args.out)
            if abs(TARGET_LUFS - lufs) <= 0.2:
                break
            gain += TARGET_LUFS - lufs
    lufs, peak = loudness(args.out)
    print(f"tts: {args.out} {duration(args.out):.2f}s, {lufs:.1f} LUFS, peak {peak:.1f} dBFS, voice {model.stem}")


if __name__ == "__main__":
    main()
