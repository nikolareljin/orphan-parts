# Working with Muse Code

Muse Code was used in the development of this repository.

## Install and sign in

```bash
curl -fsSL https://dev.meta.ai/install.sh -o muse-install.sh   # read it before running it
sh muse-install.sh
muse --version
```

On Linux the sandbox uses bubblewrap; if `muse` cannot start it, install the distribution's
`bubblewrap` package. Then, from the repository root:

```bash
muse
```

Choose *Sign in with your browser*, or paste a Model API key (a separate key from the one in
`.env` keeps the two revocable on their own). Trust the workspace when asked. Muse reads the
instructions file at the repository root and nothing above it.

Pay-as-you-go sessions bill per token to the Model API account. Keep the model on the standard
IDs and check Billing after the first session.

## Working on this repository

- Run it from the repository root so it sees the whole project.
- `./dev test` is the acceptance check for any change; it runs in Docker, so approve the
  `docker compose` command once in the sandbox prompt.
- Tests run in fixture mode and never spend credits. Ask for a real call only through
  `./dev check-api` once that command exists.
- `.env` holds the API key. Keep it out of prompts and out of the files Muse reads.
- Useful commands: `/plan` before a larger change, `/grilling` to pressure-test a design,
  `/taste` for a UI polish pass, `/goal` to pin acceptance checks across turns.

## Skills in this repository

Muse Code reads project skills from `.agents/skills/<id>/SKILL.md` once the workspace is
trusted; `muse skills list` shows them under `project`, and a slash command starts one.
`.agents/` stays out of git, so the skills' sources are under `tools/muse/`, each linked in
once:

```bash
mkdir -p .agents/skills
ln -s ../../tools/muse/picture-review .agents/skills/picture-review
ln -s ../../tools/muse/picture-tune .agents/skills/picture-tune
```

- `/picture-review`: check the drawings against their facts, show the report, redraw the ones
  the owner approves with a corrected brief, review them again and open a pull request
  ([Review and redraw the drawings](../guides/picture-review.md)).
- `/picture-tune`: the Muse Code skill that evaluates and improves the drawing parameters:
  score the demo set's drawings for the current version of `backend/app/picture/params.yaml`,
  propose edits from the issues that recur, ask the owner, apply them, redraw and review the
  whole set within a cap, compare the versions and open a pull request
  ([Tuning the drawing parameters](../guides/picture-review.md#tuning-the-drawing-parameters)).

`muse skills validate tools/muse/<id>` checks a skill file. To run both step by step, with a zero-cost path, a
first live run on one drawing, the costs and how to undo, see
[Try the skills yourself](../guides/picture-review.md#try-the-skills-yourself).

Configuration and models: https://dev.meta.ai/docs/muse-code/
