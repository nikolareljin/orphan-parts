"""Cut the draft videos from the takes, the owner's photos, the cards and the titles.

The shot lists below follow storyboard/main.md and storyboard/short.md: change both together.
Each shot becomes a 1920x1080, 30 fps segment; the segments are joined, the captions from
scripts/*.srt burned in, and the sound is silence or a narration track (never retimed): the
owner's recording, or the synthetic narrator tts.py writes from the captions.

- take:   a web take from video/scenes (out/work/takes/<shot>.webm and .json), cut from the
          moment the scene called ready() (or a named mark), sped up evenly when it runs
          longer than the shot (at most 2x), held on its last frame when shorter
- phone:  a phone take (out/work/takes/<shot>.mp4) or, without one, the app's screenshots
- photo:  the owner's photos side by side on a blurred fill, with a slow push in
- still:  a picture under video/ with a slow push in
- card:   a card under video/brand, held, faded in and out

A take whose model answer came from an operation's stub rather than a recording of that very
request (listed by generate.sh in out/work/standins.txt) carries a red DRAFT line naming the
operation, so a stand-in is never mistaken for the real answer.

Usage: python3 video/assemble.py [--narration FILE] [--narration-short FILE] [--only main|short]
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "out"
WORK = OUT / "work"
TAKES = WORK / "takes"
SEG = WORK / "segments"
PHOTOS = ROOT / "demo" / "photos"
PHONE_STILLS = ROOT / "docs" / "assets" / "pairing"
W, H, FPS = 1920, 1080, 30
FONT = "Noto Sans"

# (shot, seconds, kind, source, titles as [(title, second it comes in)])
MAIN = [
    ("S01", 6, "photo", ["hamilton-729-mixer.jpg"], []),
    ("S02", 6, "photo", ["evga-9800gt-front.jpg", "intel-slot-cpu.jpg", "tplink-pa2010.jpg"], []),
    ("S03", 5, "card", "card-open.png", []),
    ("S04", 7, "photo", ["hamilton-729-side.jpg", "agitator-head.jpg", "agitator-coupling.jpg"], [("t01-story-a", 0)]),
    ("S05", 8, "take", "S05", [("t21-which-device", 0)]),
    ("S06", 5, "photo", ["hamilton-729-label.jpg"], [("t22-label", 0)]),
    ("S07", 7, "take", "S07", [("t23-device-read", 0)]),
    ("S08", 16, "take", "S08", [("t24-search-web", 0), ("t29-fit", 9)]),
    ("S09", 8, "take", "S09", [("t25-decide", 0)]),
    ("S10", 6, "take", "S10", [("t08-story-b", 0)]),
    ("S11", 9, "take", "S11", [("t09-preferences", 0)]),
    ("S12", 9, "take", "S12", [("t10-propose", 0)]),
    ("S13", 8, "take", "S13", [("t11-select", 0)]),
    ("S14", 7, "take", "S14", [("t26-draw", 0)]),
    ("S15", 8, "take", "S15", [("t12-marketplace", 0)]),
    ("S16", 6, "take", "S16", [("t13-pack", 0)]),
    ("S17", 6, "take", "S17", [("t30-value", 0)]),
    ("S18", 11, "take", "S18", [("t31-sell", 0)]),
    ("S19", 6, "phone", "S19", [("t27-phone", 0)]),
    ("S20", 6, "card", "card-models.png", []),
    ("S21", 13, "take", "S21", [("t28-gallery", 0)]),
    ("S22", 9, "card", "card-close.png", []),
]

# the short: the same takes, shorter cuts; "S08@found" starts at that take's mark
SHORT = [
    ("K1", 5, "card", "card-open.png", []),
    ("K2", 6, "photo", ["agitator-head.jpg", "hamilton-729-label.jpg"], [("t01-story-a", 0)]),
    ("K3", 6, "take", "S07", [("t21-which-device", 0)]),
    ("K4", 9, "take", "S08", [("t24-search-web", 0)]),
    ("K5", 6, "take", "S12@proposed", [("t10-propose", 0)]),
    ("K6", 6, "take", "S14", [("t26-draw", 0)]),
    ("K7", 5, "take", "S15", [("t12-marketplace", 0)]),
    ("K8", 5, "take", "S18@drafted", [("t31-sell", 0)]),
    ("K9", 7, "card", "card-close.png", []),
]


def run(args: list[str]) -> None:
    done = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *args], check=False)
    if done.returncode != 0:
        sys.exit(f"assemble: ffmpeg failed: {' '.join(args[-1:])}")


def probe(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip() or 0)


ENCODE = ["-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-an"]


def standins() -> dict[str, list[str]]:
    """shot -> the operations answered by a stub in its take (from generate.sh)."""
    found: dict[str, list[str]] = {}
    path = WORK / "standins.txt"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            shot, _, ops = line.partition(" ")
            if ops.strip():
                found[shot] = ops.split()
    return found


def overlays(chain: str, label: str, titles: list[tuple[str, float]], secs: float, corner: bool, draft: list[str]) -> tuple[list[str], str]:
    """Inputs and filter for the corner logo, the titles (4 s each) and the DRAFT line."""
    inputs: list[str] = []
    n = 1
    last = label
    if corner:
        inputs += ["-loop", "1", "-t", f"{secs}", "-i", str(HERE / "brand" / "corner-overlay.png")]
        chain += f";[{last}][{n}:v]overlay=0:0[c{n}]"
        last = f"c{n}"
        n += 1
    for title, at in titles:
        inputs += ["-loop", "1", "-t", f"{secs}", "-i", str(HERE / "titles" / f"{title}.png")]
        chain += f";[{last}][{n}:v]overlay=0:0:enable='between(t,{at},{at + 4})'[c{n}]"
        last = f"c{n}"
        n += 1
    if draft:
        # a text file, so the colon and the parentheses need no escaping in the filter
        note = SEG / f"draft-{label}-{abs(hash(tuple(draft))) % 10**8}.txt"
        note.write_text("DRAFT: stand-in answer, not recorded yet (" + ", ".join(draft) + ")", encoding="utf-8")
        chain += (
            f";[{last}]drawbox=x={W - 760}:y=196:w=736:h=52:color=0xb91c1c@0.92:t=fill,"
            f"drawtext=font='{FONT}':textfile='{note}':fontsize=22:fontcolor=white:x={W - 744}:y=210[d]"
        )
        last = "d"
    return inputs, chain + f";[{last}]format=yuv420p[v]"


def take(shot: str, src: str, secs: float, titles, draft, out: Path) -> bool:
    name, _, mark = src.partition("@")
    video = TAKES / f"{name}.webm"
    meta = TAKES / f"{name}.json"
    if not video.is_file() or not meta.is_file():
        return False
    info = json.loads(meta.read_text(encoding="utf-8"))
    start = float(info.get("start", 0))
    if mark:
        start = max(start, float(info.get("marks", {}).get(mark, start)) - 0.8)
    end = min(float(info.get("end", 0)) or probe(video), probe(video))
    avail = max(0.1, end - start)
    if avail > secs * 2:
        # more than twice the shot: the last part, where the answer is, at double speed
        start = end - secs * 2
        avail = secs * 2
    speed = max(1.0, avail / secs)
    chain = f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=(PTS-STARTPTS)/{speed:.4f},fps={FPS},scale={W}:{H}:flags=lanczos,tpad=stop_mode=clone:stop_duration={secs},trim=duration={secs}[base]"
    inputs, chain = overlays(chain, "base", titles, secs, True, draft)
    run(["-i", str(video), *inputs, "-filter_complex", chain, "-map", "[v]", "-t", f"{secs}", *ENCODE, str(out)])
    return True


def compose_photos(files: list[str], out: Path) -> None:
    """The photos side by side, fitted to 960 px high, on a blurred and darkened fill."""
    paths = [PHOTOS / f for f in files]
    args: list[str] = []
    for p in paths:
        args += ["-i", str(p)]
    n = len(paths)
    fill = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:3,eq=brightness=-0.25[bg]"
    parts = [fill]
    for i in range(n):
        parts.append(f"[{i}:v]scale=-2:{960 if n == 1 else 900},pad=iw+40:ih:20:0:color=0x0e131d@0[p{i}]")
    if n > 1:
        parts.append("".join(f"[p{i}]" for i in range(n)) + f"hstack=inputs={n}[row]")
    else:
        parts.append("[p0]null[row]")
    parts.append(f"[row]scale='min({W - 80},iw)':-2[fit];[bg][fit]overlay=(W-w)/2:(H-h)/2")
    run([*args, "-filter_complex", ";".join(parts), "-frames:v", "1", str(out)])


def push(image: Path, secs: float, out: Path, zoom: float, titles, fade: bool = False) -> None:
    """A slow push in on a still (a Ken Burns move), rendered at twice the size to keep it smooth."""
    frames = int(secs * FPS)
    move = (
        f"[0:v]scale={W * 2}:{H * 2}:force_original_aspect_ratio=decrease,pad={W * 2}:{H * 2}:(ow-iw)/2:(oh-ih)/2:color=0x0e131d,"
        f"zoompan=z='1+{zoom - 1}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}"
    )
    if fade:
        move += f",fade=t=in:st=0:d=0.6,fade=t=out:st={secs - 0.8}:d=0.8"
    chain = move + "[base]"
    inputs, chain = overlays(chain, "base", titles, secs, False, [])
    run(["-loop", "1", "-framerate", str(FPS), "-t", f"{secs}", "-i", str(image), *inputs, "-filter_complex", chain, "-map", "[v]", "-frames:v", str(frames), *ENCODE, str(out)])


def card(image: Path, secs: float, out: Path, first: bool, last: bool) -> None:
    fades = []
    if not first:
        fades.append("fade=t=in:st=0:d=0.5")
    if last:
        fades.append(f"fade=t=out:st={secs - 1}:d=1")
    chain = f"[0:v]scale={W}:{H},fps={FPS}" + ("," + ",".join(fades) if fades else "") + ",format=yuv420p[v]"
    run(["-loop", "1", "-framerate", str(FPS), "-t", f"{secs}", "-i", str(image), "-filter_complex", chain, "-map", "[v]", "-t", f"{secs}", *ENCODE, str(out)])


def phone(shot: str, secs: float, titles, out: Path) -> str:
    """The emulator's take when generate.sh recorded one, else the app's screenshots."""
    video = TAKES / f"{shot}.mp4"
    if video.is_file():
        length = probe(video)
        speed = max(1.0, length / secs)
        chain = (
            f"[0:v]setpts=PTS/{speed:.4f},fps={FPS},scale=-2:{H - 80},pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0e131d,"
            f"tpad=stop_mode=clone:stop_duration={secs},trim=duration={secs}[base]"
        )
        inputs, chain = overlays(chain, "base", titles, secs, True, [])
        run(["-i", str(video), *inputs, "-filter_complex", chain, "-map", "[v]", "-t", f"{secs}", *ENCODE, str(out)])
        return "recorded"
    stills = [PHONE_STILLS / "android-capture.png", PHONE_STILLS / "android-sent.png"]
    composite = SEG / f"{shot}-phone.png"
    args: list[str] = []
    for p in stills:
        args += ["-i", str(p)]
    parts = [f"[{i}:v]scale=-2:{H - 120},pad=iw+80:ih:40:0:color=0x0e131d[p{i}]" for i in range(len(stills))]
    parts.append("".join(f"[p{i}]" for i in range(len(stills))) + f"hstack=inputs={len(stills)},pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0e131d")
    run([*args, "-filter_complex", ";".join(parts), "-frames:v", "1", str(composite)])
    push(composite, secs, out, 1.04, titles)
    return "stills"


def build(name: str, shots, srt: Path, narration: Path | None) -> dict:
    SEG.mkdir(parents=True, exist_ok=True)
    drafts = standins()
    report: dict = {"shots": [], "missing": []}
    parts: list[Path] = []
    for i, (shot, secs, kind, src, titles) in enumerate(shots):
        out = SEG / f"{name}-{i:02d}-{shot}.mp4"
        how = kind
        if kind == "take":
            draft = drafts.get(src.partition("@")[0], [])
            if not take(shot, src, secs, titles, draft, out):
                report["missing"].append(shot)
                frame = SEG / f"{shot}-missing.png"
                run(["-f", "lavfi", "-i", f"color=c=0x0e131d:s={W}x{H}", "-vf", f"drawtext=font='{FONT}':text='{shot} take missing':fontsize=48:fontcolor=0x94a3b8:x=(w-tw)/2:y=(h-th)/2", "-frames:v", "1", str(frame)])
                push(frame, secs, out, 1.0, titles)
                how = "missing"
            elif draft:
                how = "take, stand-in: " + ",".join(draft)
        elif kind == "photo":
            composite = SEG / f"{name}-{shot}-photos.png"
            compose_photos(src, composite)
            push(composite, secs, out, 1.06, titles)
        elif kind == "still":
            push(HERE / src, secs, out, 1.05, titles)
        elif kind == "card":
            card(HERE / "brand" / src, secs, out, i == 0, i == len(shots) - 1)
        elif kind == "phone":
            how = "phone " + phone(src, secs, titles, out)
        parts.append(out)
        report["shots"].append((shot, secs, how))
    joined = SEG / f"{name}-joined.mp4"
    listing = SEG / f"{name}-list.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(joined)])
    total = sum(s[1] for s in shots)
    style = f"FontName={FONT},FontSize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=3,Outline=1,Shadow=0,MarginV=36"
    srt_path = str(srt).replace(":", r"\:")
    audio = ["-f", "lavfi", "-t", f"{total}", "-i", "anullsrc=r=48000:cl=stereo"]
    amap = "1:a"
    if narration is not None:
        audio = ["-i", str(narration)]
        amap = "1:a"
    final = OUT / f"{name}-draft.mp4"
    run([
        "-i", str(joined), *audio,
        "-filter_complex", f"[0:v]subtitles='{srt_path}':force_style='{style}'[v];[{amap}]aresample=48000,apad,atrim=0:{total}[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{total}",
        "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final),
    ])
    report["file"] = str(final)
    report["duration"] = probe(final)
    report["parts"] = [str(p) for p in parts]
    return report


def contact_sheet(report: dict, out: Path) -> None:
    """One frame from the middle of every shot, labeled, six to a row."""
    frames = []
    for i, (part, (shot, secs, _)) in enumerate(zip(report["parts"], report["shots"])):
        frame = SEG / f"sheet-{i:02d}.png"
        run(["-ss", f"{secs * 0.6:.2f}", "-i", part, "-frames:v", "1", "-vf", f"scale=480:270,drawbox=x=0:y=0:w=72:h=34:color=black@0.7:t=fill,drawtext=font='{FONT}':text='{shot}':fontsize=22:fontcolor=white:x=8:y=6", str(frame)])
        frames.append(frame)
    cols = 6
    rows = (len(frames) + cols - 1) // cols
    run(["-framerate", "1", "-i", str(SEG / "sheet-%02d.png"), "-vf", f"tile={cols}x{rows}:padding=6:margin=6:color=0x0e131d", "-frames:v", "1", "-q:v", "3", str(out)])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--narration", type=Path, help="the main video's narration (WAV), mixed in as is")
    parser.add_argument("--narration-short", type=Path, help="the short video's narration (WAV), mixed in as is")
    parser.add_argument("--only", choices=["main", "short"])
    args = parser.parse_args()
    if shutil.which("ffmpeg") is None:
        sys.exit("assemble: ffmpeg is not installed")
    OUT.mkdir(parents=True, exist_ok=True)
    for f in SEG.glob("sheet-*.png") if SEG.is_dir() else []:
        f.unlink()
    lines = []
    if args.only in (None, "main"):
        report = build("main", MAIN, HERE / "scripts" / "main.srt", args.narration)
        contact_sheet(report, OUT / "main-shots.jpg")
        lines.append(f"main  {report['file']}  {report['duration']:.2f} s")
        lines += [f"  {s} {d:>3}s {how}" for s, d, how in report["shots"]]
        if report["duration"] >= 180:
            sys.exit(f"assemble: the main video is {report['duration']:.1f} s, the limit is under 3:00")
    if args.only in (None, "short"):
        report = build("short", SHORT, HERE / "scripts" / "short.srt", args.narration_short)
        lines.append(f"short {report['file']}  {report['duration']:.2f} s")
        lines += [f"  {s} {d:>3}s {how}" for s, d, how in report["shots"]]
        if report["duration"] > 60:
            sys.exit(f"assemble: the short video is {report['duration']:.1f} s, over 60")
    (OUT / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
