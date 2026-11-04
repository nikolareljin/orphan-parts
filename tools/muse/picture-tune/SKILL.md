---
name: picture-tune
description: Evaluate and improve the drawing parameters of Orphan Parts Lens (backend/app/picture/params.yaml, the data every Muse Image request is built from) so future drawings avoid the issues the reviews keep finding; review the demo set's drawings, score the current version, propose parameter edits from the recurring issues, ask the owner, apply them, redraw and re-review the whole set within a cap, draw several candidates of each drawing that still misses and keep the best, compare the versions and open a pull request with the parameters, the new recordings and the results table. Use when the owner asks to tune, improve or evaluate the drawing parameters or the picture prompts, asks why the drawings keep getting something wrong, or invokes /picture-tune.
---

# Tune the drawing parameters

Muse Image cannot be fine-tuned through the Model API; what can be changed is the request the
app writes. That request is built from `backend/app/picture/params.yaml`: which facts of each
part are said and in what order, how each kind of part looks at its real size, a correction
for each kind of project, view presets, negatives and closing rules, with a `version`. This
skill measures a version on the demo set, changes it from what the reviews found, and measures
the next one. Every step is a `./dev picture-review` command; the guide is
`docs/guides/picture-review.md#tuning-the-drawing-parameters`.

## How to run

1. Install once from the repository root: `mkdir -p .agents/skills && ln -s ../../tools/muse/picture-tune .agents/skills/picture-tune`;
   `muse skills validate tools/muse/picture-tune`; `muse skills list --source project`.
2. Start `muse` in the repository root, trust the workspace, then `/picture-tune`.
3. Free first: `./dev picture-review --dry-run` (no key). Smallest live run: `./dev picture-review --only project:2 --max-usd 0.10`
   then `./dev picture-review --tune --dry-run` (rule edits only, free; never apply a proposal
   made from one drawing). One round is about 0.55 USD: proposal 0.01, the set drawn again
   0.32 and reviewed 0.20; scoring the current version first adds a review, 0.21. The key
   (`MODEL_API_KEY`, shell or `.env`) bills the Model API account.
4. Outputs: `picture-review/report.md`, `tune.md`, `tune.json`, `compare.md`, `sheet-v<N>.jpg`;
   `backend/app/picture/params.yaml`, `eval/pictures/params-v<N>.json`, the table in
   `docs/project/picture-review-results.md`, recordings under
   `backend/tests/fixtures/api/images-generations/`.
5. Undo before a commit: `git checkout -- backend/app/picture/params.yaml eval/pictures docs/project/picture-review-results.md backend/tests/fixtures`
   and `git clean -f backend/tests/fixtures/api/images-generations eval/pictures`.

## Inputs

- The demo set, `demo/set.yaml`, and its recordings under `backend/tests/fixtures/api`.
- The parameters, `backend/app/picture/params.yaml` (its `version` is N).
- The earlier scores, `eval/pictures/params-v*.json`.
- Optional from the owner: a spending cap for the whole run (default 2 USD), subjects or
  drawings to leave out, edits to the proposal.

## Outputs

- `picture-review/report.md`: the review of every drawing (verdict, issues, proposed brief).
- `picture-review/tune.md` and `tune.json`: the proposed edits, why, and the diff.
- `backend/app/picture/params.yaml` at version N+1, once the owner approves.
- New drawing recordings under `backend/tests/fixtures/api/images-generations/`; the ones
  version N used and N+1 does not, removed.
- `eval/pictures/params-v<N+1>.json` (and `params-v<N>-<stage>.json` for a later score of the
  same version: the best of N kept), `picture-review/compare.md`, the history table in
  `docs/project/picture-review-results.md`, contact sheets `picture-review/sheet-v<N>.jpg`.
- A pull request. Never a merge.

## Rules

- Run everything from the repository root with `./dev`; never call the Model API another way.
- The key is `MODEL_API_KEY` in the owner's shell or `.env`. Never print it, echo it, write it
  to a file or put it in a command line.
- Every paid step takes `--max-usd`. Say the cap before running and the spend after; keep a
  running total and stop before it would pass the owner's cap.
- Never edit `params.yaml` or anything under `backend/tests/fixtures` by hand; the commands
  write them. Never change a request other than a drawing's.
- Approval points (wait for the owner each time): before the first paid step, before
  `--apply`, before `--redraw-set`, before `--candidates`, before the pull request.

## Steps

1. **Check the state** (nothing spent). `git status` is clean; `./dev picture-review --dry-run`
   lists the drawings (about 32: items, reuse cards, projects and their views). Read `version`
   in `backend/app/picture/params.yaml` (N) and list `eval/pictures/`. Tell the owner N, the
   number of drawings and the cost ahead: a review is about 0.007 USD a drawing, a drawing
   0.01 USD, so one full round (review, tune, redraw, review) is about 0.75 USD for 32, 0.55
   when version N is already scored; best of three for ten drawings about 0.50 USD.
2. **Evaluate version N.** If `eval/pictures/params-vN.json` is missing, or the owner wants a
   fresh score: `./dev picture-review --max-usd 1`, then `./dev picture-review --evaluate`.
   Show the verdict counts and the issues by category from the output and
   `picture-review/compare.md`.
3. **Propose.** `./dev picture-review --tune --max-usd 0.1` (one Muse Spark call phrases the
   corrections; `--dry-run` proposes the rule edits alone, free). Read `picture-review/tune.md`
   and show the owner a short table: each edit's place in the file, why, the drawings behind
   it. Point out any edit that would hold for one part but not for every part of its kind
   (a kind's looks with a fixed size or aspect ratio, a correction naming one model).
4. **Ask the owner.** Wait for a yes, a no per edit, or a changed text. To drop or change an
   edit, edit its entry in the `edits` list of `picture-review/tune.json` (the diff in
   `tune.md` shows the proposal as made; `--apply` writes the list as it is then); never edit
   `params.yaml` itself.
5. **Apply.** `./dev picture-review --tune --apply`: the file is written at version N+1 (it
   refuses a proposal made for another version). Show the diff: `git diff backend/app/picture/params.yaml`.
6. **Redraw the set** (ask first; say the cap): `./dev picture-review --redraw-set --max-usd 1.5`.
   Every drawing whose request changed is drawn and recorded; every other answer replays; then
   every drawing is reviewed into `picture-review/report.md`. Check the output's load lines:
   the replay must say 0 not recorded and 0 stand-in answers. A drawing skipped for the cap
   stays unrecorded: raise the cap with the owner or stop.
7. **Compare.** `./dev picture-review --evaluate --prune`: the score is kept in
   `eval/pictures/params-v<N+1>.json`, the history table is written into
   `docs/project/picture-review-results.md`, and the recordings version N used and N+1 does
   not are removed. Show the table from `picture-review/compare.md` and the drawings that
   moved; show `picture-review/sheet-vN.jpg` and `sheet-v<N+1>.jpg` when asked.
8. **Best of N, when some drawings still miss** (ask first; say the cap):
   `./dev picture-review --candidates 3 --max-usd 1.5` draws each drawing the last review did
   not find matching three more times, each with its own brief (the review's corrected brief,
   then another framing or a narrower scene), reviews every candidate and keeps the best by
   verdict, confidence and fewer issues; the drawing as it stands keeps its place on a tie.
   Name drawings to try even when they match with `--only project:7,project:8` (the featured
   builds' views). Only the winner's brief goes into `demo/set.yaml` and only its recording is
   kept; every candidate is copied under `picture-review/candidates/` with
   `picture-review/candidates.md` (each candidate's verdict and brief) and
   `best-before.jpg` / `best-after.jpg`. About 0.017 USD a candidate. Then
   `./dev picture-review --evaluate --stage best3 --prune` keeps the score beside the version's
   first one (`eval/pictures/params-v<N>-best3.json`) and removes the recordings replaced.
9. **One more round, only if asked.** If some drawings are still `wrong`, offer one more
   round from step 3 on the new report (it proposes edits for those subjects only, so only
   their drawings are redrawn). Never more than two rounds in one session without the owner
   raising the cap.
10. **Check** that nothing else moved: `git status` shows `params.yaml`, `eval/pictures/`, the
   results page and files added or deleted under
   `backend/tests/fixtures/api/images-generations/`;
   `git diff --diff-filter=M -- backend/tests/fixtures` is empty; `./dev picture-review --dry-run`
   prints a set load with 0 not recorded and 0 stand-in answers (it loads into a folder of
   its own; `./dev demo` would reset the stack's inventory); `./dev test` passes.
11. **Pull request**, when the owner says so: a branch `feat/drawing-params-v<N+1>`, one commit
    `feat(picture): drawing parameters v<N+1> from the review of <date>`, push, `gh pr create`
    with the version table and the spend in the body. Stop there; the owner merges.

## Install

Muse Code reads project skills from `.agents/skills/<id>/SKILL.md`; `.agents/` stays out of
git, so link this folder in once from the repository root:

```bash
mkdir -p .agents/skills && ln -s ../../tools/muse/picture-tune .agents/skills/picture-tune
muse skills validate tools/muse/picture-tune
```

Then `/picture-tune` starts it. `/picture-review` is the skill for fixing single drawings with
a brief; this one changes what every drawing is asked with.
