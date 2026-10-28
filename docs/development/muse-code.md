# Working with Muse Code

Muse Code is the coding agent used on this repository.

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

Configuration and models: https://dev.meta.ai/docs/muse-code/
