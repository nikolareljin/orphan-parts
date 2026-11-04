---
name: picture-review
description: Review the drawings of Orphan Parts Lens (project pictures and their views, reuse-card pictures, item pictures) against the facts each must show, with ./dev picture-review; show the owner the report, ask which to redraw, redraw only the approved ones with the corrected brief, review them again, and open a pull request with the set and the new recordings. Use when the owner asks to check, review, fix or redraw the drawings or pictures, or invokes /picture-review.
---

# Picture review

The drawings are made by Muse Image from a prompt the app writes. Some do not match the build:
the hall smart mirror built from an 18 inch monitor came out as a 50 inch television. This
skill runs the repository's own review tool and walks the owner through the fix. The guide is
`docs/guides/picture-review.md`.

## Rules

- Run everything from the repository root with `./dev`; never call the Model API another way.
- The key is `MODEL_API_KEY` in the owner's shell or `.env`. Never print it, echo it, write it
  to a file or put it in a command line.
- Every paid step has a cap: pass `--max-usd`. Say the cap before running and the spend after.
- Redraw only what the owner approved, by id. Never edit `backend/tests/fixtures` by hand.
- Never merge a pull request. Stop at "PR open, checks green".

## Steps

1. **Dry run** (nothing spent): `./dev picture-review --dry-run`. Say how many drawings there
   are, by kind. Ask before going on if the owner named only some (`--only project:2,card:...`).
2. **Review** with a cap (about 0.01 USD a drawing): `./dev picture-review --max-usd 1`
   (add `--decide` to also check the Decide cards and the projects' allocations; report only).
3. **Read** `picture-review/report.md`. Show the owner a short table: id, title, verdict, the
   first issue. Then, for each `wrong` and each `partly` with a scale or wrong-device issue,
   show the facts, the issues and the proposed brief. Open the thumbnail
   (`picture-review/pictures/<id>.jpg`) when the owner asks to see it.
4. **Propose** corrections: keep the tool's brief when it is concrete (real size, proportions,
   setting, "not a TV"); otherwise rewrite it from the facts in the report. Each brief at most
   350 characters, parts named by kind, never by brand.
5. **Ask the owner to approve**: list the ids and the brief for each; wait for a yes per id or
   an edited brief. Write approved briefs that differ from the report's into
   `picture-review/briefs.yaml` as `"<id>": "<brief>"`.
6. **Redraw** the approved ones (one drawing 0.01 USD, one review about 0.01 USD):
   `./dev picture-review --redraw <id,id,...> --max-usd 1` (add `--briefs picture-review/briefs.yaml`
   when step 5 wrote it). The tool writes each brief into `demo/set.yaml`, records only the new
   drawings, replays the set and reviews each new drawing.
7. **Report** from `picture-review/redraw.md`: before and after verdict per id; show
   `picture-review/before.jpg` and `picture-review/after.jpg`. A drawing still `wrong` gets one
   more brief from the owner, or is left as it is.
8. **Check** that nothing else moved: `git status` shows `demo/set.yaml` and new files under
   `backend/tests/fixtures/api/images-generations/` only;
   `git diff --diff-filter=MD -- backend/tests/fixtures` is empty (a drawing redrawn twice
   leaves the first new recording unused: delete that uncommitted pair, the `.json` and its
   `-1.jpg`); `./dev demo` reports
   0 not recorded and 0 stand-in answers; `./dev test` passes.
9. **Pull request**, when the owner says so: a branch `fix/drawings-<date>`, one commit
   `fix(demo): redraw <what> with corrected briefs`, push, `gh pr create` with the before and
   after verdicts in the body. Stop there; the owner merges.
