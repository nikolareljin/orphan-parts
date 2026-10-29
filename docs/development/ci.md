# CI and releases

The workflows in `.github/workflows/`, kept as small as they can be. No personal tokens anywhere.

## Branch and pull request flow

One piece of functionality per branch:

1. `git switch -c feat/<topic> main`
2. Build it with its tests. `./dev test` must pass locally.
3. Open a pull request against `main`. The PR template asks for what, why and tests.
4. CI runs the same checks. Merge when green (squash, keeping the title as the commit subject).

Conventional Commits for subjects and PR titles: `feat(extract): read part labels with Muse Spark`.

## `ci.yml`

Runs on every pull request and on pushes to `main`. Four jobs, in parallel:

| Job | Steps |
|---|---|
| backend | ruff, mypy, pytest in fixture mode |
| frontend | eslint, tsc, vitest, production build |
| scripts | bash helper tests |
| e2e | `./dev e2e`: the dev stack in fixture mode plus Playwright in its image; results uploaded on failure |

Concurrent runs on the same ref cancel each other.

The `docs` job builds the site with `--strict` on every pull request, the same steps as the
Pages workflow without the deploy, so a page that no longer builds is caught before `main`.

## `tag-release.yml` and `release.yml`

Versions follow SemVer and live in `backend/pyproject.toml`, `backend/app/__init__.py` and
`frontend/package.json`. Tags are bare versions, no `v` prefix.

```bash
./dev version 0.2.0      # bumps every manifest and opens a changelog section
# move the Unreleased notes under the new heading, open the pull request from release/0.2.0,
# merge it: the merge commit is tagged 0.2.0 and the release is published
```

`tag-release.yml` runs when a pull request from a `release/x.y.z` branch is merged into `main`.
`scripts/release-tag.sh` reads the version off the branch name and refuses anything that is
not `x.y.z`, a version that differs from any manifest, a changelog without its section, and a
version that is tagged already: an existing tag is never moved or deleted. Then the merge commit
gets the tag and the publish job calls `release.yml`. A pull request closed without a merge, or
from any other branch, does nothing. The tag is pushed with the job token, which on its own
does not start tag-triggered workflows; that is why `release.yml` is called rather than waited
for. The ruleset that limits tag creation has to list GitHub Actions as a bypass actor, or the
push is refused and the tag is pushed by hand (`git tag 0.2.0 && git push origin 0.2.0`),
which still triggers `release.yml`.

`release.yml`, called with the tag or triggered by a tag push:

1. checks that the tag equals the version in all three manifests and that `CHANGELOG.md` has a
   section for it,
2. builds the production images and boots the backend one with `/readyz` reporting `ok`,
3. pushes them to GHCR as `ghcr.io/<owner>/orphan-parts/backend:0.2.0` and
   `.../frontend:0.2.0` (plus `latest`), nothing is pushed if the smoke test fails,
4. creates a GitHub release whose notes are that changelog section.

The jobs use only `actions/checkout`, the job token, Docker and `gh`; no other actions and no
stored secrets. A repository ruleset lets only the repository admin and the tag workflow create
tags, and nobody move or delete them; the workflow tags only what the admin merged, so nobody
else can trigger a release.

Only a tag, or the tag workflow, triggers it; no image is built or pushed for pull requests or
other merges. The images are
the release artifact: the demo host pulls them, and a tagged version can be run anywhere without
a build. See [Deployment](../operations/deployment.md).

## `docs.yml`

Runs when `docs/`, `mkdocs.yml`, the docs image, the backend app or the changelog change on `main`.
Exports the OpenAPI document, builds the site with `--strict`, uploads it and deploys to GitHub
Pages through OIDC (`pages: write`, `id-token: write`).
