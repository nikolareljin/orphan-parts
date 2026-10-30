"""Write an SRT file from a narration script.

The script's sections start with `## m:ss to m:ss` and their spoken lines start with `> `.
Each section's narration is split into sentences, long sentences into pieces of at most two
42-character lines, and the section's time is shared among the cues by word count, with a
short gap between cues. Timings are estimates until the narration is recorded: after
recording, shift the section times in the script to where the voice actually starts and run
this again, or retime in the editor.

Usage: python3 captions.py main.md main.srt
"""

import math
import re
import sys
import textwrap

SECTION = re.compile(r"^## (\d+):(\d\d) to (\d+):(\d\d)")
LINE = 42
GAP = 0.12  # seconds between cues


def sections(path):
    out, cur = [], None
    for raw in open(path, encoding="utf-8"):
        m = SECTION.match(raw)
        if m:
            a, b, c, d = map(int, m.groups())
            cur = [a * 60 + b, c * 60 + d, []]
            out.append(cur)
        elif cur is not None and raw.startswith("> "):
            cur[2].append(raw[2:].strip())
    return [(s, e, " ".join(t)) for s, e, t in out if t]


def cues(text):
    # a long sentence is cut into pieces of even length, each at most two lines
    for sentence in re.split(r"(?<=[.?!])\s+", text):
        words = sentence.split()
        pieces = 1
        while True:
            size = math.ceil(len(words) / pieces)
            chunks = [words[i : i + size] for i in range(0, len(words), size)]
            wrapped = [textwrap.wrap(" ".join(c), LINE) for c in chunks]
            if all(len(w) <= 2 for w in wrapped):
                break
            pieces += 1
        for w in wrapped:
            yield "\n".join(w)


def stamp(t):
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main(src, dst):
    n = 0
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        for start, end, text in sections(src):
            parts = list(cues(text))
            words = [len(p.split()) for p in parts]
            span = end - start - GAP * len(parts)
            t = start
            for p, w in zip(parts, words):
                d = span * w / sum(words)
                n += 1
                f.write(f"{n}\n{stamp(t)} --> {stamp(t + d)}\n{p}\n\n")
                t += d + GAP
            rate = sum(words) / (end - start)
            print(f"{start // 60}:{start % 60:02} {sum(words):3} words, {rate:.2f} words/s")


if __name__ == "__main__":
    main(*sys.argv[1:3])
