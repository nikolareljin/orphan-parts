# Recording on Ubuntu with OBS Studio

## Once

```bash
sudo apt install obs-studio scrcpy ffmpeg
```

OBS, **Settings**:

- **Video**: base and output resolution 1920x1080, 30 fps.
- **Output**, mode *Simple*: recording quality *High Quality, Medium File Size*, format
  *Matroska Video (.mkv)* (a crash does not lose the take), encoder *x264* or the hardware
  encoder when listed. After a session, **File, Remux Recordings** turns the MKV files into
  MP4 for the editor.
- **Audio**: 48 kHz. The desktop audio off; the microphone only for narration takes.
- Sources, one scene each:
  - *Browser*: **Window Capture (Xcomposite)** on X11, or **Screen Capture (PipeWire)** on
    Wayland (pick the window when asked).
  - *Phone*: the scrcpy window, the same way.
  - *Terminal*: the terminal window, 18 pt font, dark theme.

Before every session: Do Not Disturb on (GNOME: the notification panel), a browser profile
with no bookmarks bar and no extensions, the window sized so its page area is 1920x1080
(full screen with F11 is simplest), zoom 110 percent.

## The stack

From a clone of the repository, `main` checked out:

```bash
cp .env.example .env          # once
./dev up
./dev demo                    # before every take: the inventory reset, the demo set loaded
```

- **Fixture scenes** (status *now* in `readiness.md`): `.env` with `OPL_FAKE_API=1`. Nothing
  is spent; every model answer is the recorded one.
- **Live scenes** (status *key*, and S06): `.env` with `MODEL_API_KEY` set and
  `OPL_FAKE_API=0`, then `./dev down && ./dev up`, `./dev demo`, and `./dev check-api`, which
  says the mode is live. Each **Propose** and **Read it** spends credits; rehearse in fixture
  mode, then record each live take once or twice.

Record the fixture scenes first, then the live ones, so a reset between takes never costs a
run.

## The phone

```bash
scrcpy --max-size 1080 --stay-awake --turn-screen-off=false
```

Or, without a window: `adb shell screenrecord /sdcard/take.mp4` (three minutes at most), then
`adb pull /sdcard/take.mp4`. Pair the app with the web app opened at the computer's network
address, not `localhost` (JUDGES.md, step 5). For the phone's own camera footage, turn off
the camera's *high efficiency* video setting so clips are H.264.

## Narration

Record it after the picture is cut, in a quiet room, one section at a time from
`scripts/main.md`, in OBS with only the microphone, or any recorder at 48 kHz. Leave a second
of silence at each end. Then shift the section times in `scripts/main.md` to where each
section starts in the edit and run `python3 scripts/captions.py scripts/main.md
scripts/main.srt` again.

## Names for the takes

`S05-take2.mkv`, `S11-take1.mkv`: the shot number first, so the editor's media bin sorts
them in story order. Takes stay under `video/out/` or outside the repository; `video/out/` is
ignored by git.
