---
name: decide-tune
description: Evaluate and improve the text parameters of Orphan Parts Lens (backend/app/textparams/params.yaml, what the Decide cards, the ideas and the proposals are told beyond their fixed instructions) so the recommendations stop claiming what the items' facts deny; check every recommendation of the demo set against the facts, score the current version, propose edits from the flags (compatibility facts first, constraints, corrections, banned phrases), ask the owner, apply them, record the demo set again for the text that changed, check again, compare the versions and open a pull request. Use when the owner asks to tune, improve or evaluate the Decide cards, the ideas or the proposals, asks why a card recommends a part that does not fit, or invokes /decide-tune.
---

# Tune the text parameters

The Decide cards, the ideas and the proposals are written by Muse Spark from a brief the app
builds and fixed instructions. What can be changed without touching code is
`backend/app/textparams/params.yaml`: per section (`scenarios` for the Decide cards, `uses` for
the ideas, `propose` for the proposals) whether the brief opens with the item's compatibility
facts, and the constraints, corrections and banned phrases said after the instructions, with a
`version`. An empty section adds nothing, so its requests stay word for word what they were.
This skill measures a version on the demo set, changes it from what the checks flag, and
measures the next one. Every step is a `./dev decide-review` command; the guide is
`docs/guides/picture-review.md#tuning-the-text-parameters`.

## How to run

1. Install once from the repository root: `mkdir -p .agents/skills && ln -s ../../tools/muse/decide-tune .agents/skills/decide-tune`;
   `muse skills validate tools/muse/decide-tune`; `muse skills list --source project`.
2. Start `muse` in the repository root, trust the workspace, then `/decide-tune`.
3. Free first: `./dev decide-review --dry-run` (no key). A full check is about 0.50 USD (about
   60 text calls); a proposal 0.01; a re-record about 0.60 for the Decide cards (45 cards, the
   5 reuse-card drawings made from them) plus the check after it. The key (`MODEL_API_KEY`,
   shell or `.env`) bills the Model API account.
4. Outputs: `picture-review/decide/report.md`, `report.json`, `tune.md`, `tune.json`;
   `backend/app/textparams/params.yaml`, `eval/decide/text-v<N>.json`, the table between the
   `text-history` markers in `docs/project/picture-review-results.md`, recordings under
   `backend/tests/fixtures/api/`.
5. Undo before a commit: `git checkout -- backend/app/textparams/params.yaml eval/decide docs/project/picture-review-results.md backend/tests/fixtures`
   and `git clean -f backend/tests/fixtures/api eval/decide`.

## Inputs

- The demo set, `demo/set.yaml`, and its recordings under `backend/tests/fixtures/api`.
- The parameters, `backend/app/textparams/params.yaml` (its `version` is N).
- The earlier scores, `eval/decide/text-v*.json`.
- Optional from the owner: a spending cap for the whole run (default 3 USD), sections to leave
  alone (the proposals' section changes every project and its drawings), edits to the proposal.

## Outputs

- `picture-review/decide/report.md`: every flagged recommendation with the claim and the fact
  that contradicts it.
- `picture-review/decide/tune.md` and `tune.json`: the proposed edits and why.
- `backend/app/textparams/params.yaml` at version N+1, once the owner approves.
- New recordings for the requests that changed; the ones version N used and N+1 does not,
  removed (`--evaluate --prune`).
- `eval/decide/text-v<N+1>.json` and the history table on the results page.
- A pull request. Never a merge.

## Rules

- Run everything from the repository root with `./dev`; never call the Model API another way.
- The key is `MODEL_API_KEY` in the owner's shell or `.env`. Never print it, echo it, write it
  to a file or put it in a command line.
- Every paid step takes `--max-usd`. Say the cap before running and the spend after; keep a
  running total and stop before it would pass the owner's cap.
- Never edit `params.yaml` or anything under `backend/tests/fixtures` by hand; the commands
  write them. A request the parameters do not change must replay its recording: the re-record
  buys only the Decide cards, the ideas, the proposals and the drawings made from them, and
  refuses anything else.
- A banned phrase must be false wherever it is used ("with the processor you own" when none
  fits); drop one that can be true ("works as it is" for an item with nothing wrong).
- Approval points (wait for the owner each time): before the first paid step, before
  `--apply`, before `--rerecord`, before the pull request.

## Steps

1. **Check the state** (nothing spent). `git status` is clean; `./dev decide-review --dry-run`
   loads the set and lists the recordings it replays. Read `version` in
   `backend/app/textparams/params.yaml` (N) and list `eval/decide/`. Tell the owner N and the
   cost ahead.
2. **Evaluate version N.** If `eval/decide/text-vN.json` is missing, or the owner wants a fresh
   score: `./dev decide-review --max-usd 1`, then `./dev decide-review --evaluate`. Show the
   counts (checked, with flags, flags, major) by section and the flagged ids from
   `picture-review/decide/report.md`.
3. **Propose.** `./dev decide-review --tune --max-usd 0.1` (one Muse Spark call phrases the
   corrections and the banned phrases; `--dry-run` proposes the rule edits alone, free). Show
   the owner the table from `picture-review/decide/tune.md`. Point out a banned phrase that can
   be true, a correction that names one item, and any edit to `propose` (it records every
   project and its drawings again).
4. **Ask the owner.** To drop or change an edit, edit its entry in the `edits` list of
   `picture-review/decide/tune.json`; never edit `params.yaml` itself.
5. **Apply.** `./dev decide-review --tune --apply`: the file is written at version N+1 (it
   refuses a proposal made for another version). Show `git diff backend/app/textparams/params.yaml`.
6. **Re-record** (ask first; say the cap): `./dev decide-review --rerecord --max-usd 2.5`. The
   requests the new version changes are bought and recorded, every other answer replays, then
   every recommendation is checked again. The replay line must say 0 not recorded and 0
   stand-in answers.
7. **Compare.** `./dev decide-review --evaluate --prune`: the score is kept in
   `eval/decide/text-v<N+1>.json`, the history table is written into the results page, and the
   recordings version N used and N+1 does not are removed. A changed Decide card changes its
   reuse-card drawing: review the drawings after (`/picture-review`), and score them with
   `./dev picture-review --evaluate --stage <word>`.
8. **One more round, only if asked**, from step 3. Keep the best version: if a round flags more
   than the one before, revert the file to the better version
   (`git checkout -- backend/app/textparams/params.yaml backend/tests/fixtures eval/decide`) and
   stop. Never more than three rounds in one session without the owner raising the cap.
9. **Check** that nothing else moved: `git status` shows `params.yaml`, `eval/decide/`, the
   results page and recordings added or deleted under `backend/tests/fixtures/api/`;
   `git diff --diff-filter=M -- backend/tests/fixtures` is empty; `./dev picture-review --dry-run`
   prints a set load with 0 not recorded and 0 stand-in answers; `./dev test` passes.
10. **Pull request**, when the owner says so: a branch `feat/text-params-v<N+1>`, one commit
    `feat(decide): text parameters v<N+1> from the check of <date>`, push, `gh pr create` with
    the version table and the spend in the body. Stop there; the owner merges.

## Install

Muse Code reads project skills from `.agents/skills/<id>/SKILL.md`; `.agents/` stays out of
git, so link this folder in once from the repository root:

```bash
mkdir -p .agents/skills && ln -s ../../tools/muse/decide-tune .agents/skills/decide-tune
muse skills validate tools/muse/decide-tune
```

Then `/decide-tune` starts it. `/picture-tune` is the same loop for the drawing parameters.
