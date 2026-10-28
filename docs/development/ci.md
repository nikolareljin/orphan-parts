# CI and releases

Two workflows in `.github/workflows/`, kept as small as they can be. No personal tokens anywhere.

## Branch and pull request flow

One piece of functionality per branch:

1. `git switch -c feat/<topic> main`
2. Build it with its tests. `./dev test` must pass locally.
3. Open a pull request against `main`. The PR template asks for what, why and tests.
4. CI runs the same checks. Merge when green (squash, keeping the title as the commit subject).

Conventional Commits for subjects and PR titles: `feat(extract): read part labels with Muse Spark`.

## `ci.yml`

Runs on every pull request and on pushes to `main`. Three jobs, in parallel:

| Job | Steps |
|---|---|
| backend | ruff, mypy, pytest in fixture mode |
| frontend | eslint, tsc, vitest, production build |
| scripts | bash helper tests |

Concurrent runs on the same ref cancel each other.

## `release.yml`

Versions follow SemVer and live in `backend/pyproject.toml`, `backend/app/__init__.py` and
`frontend/package.json`. Tags are bare versions, no `v` prefix.

```bash
./dev version 0.2.0      # bumps every manifest and opens a changelog section
# move the Unreleased notes under the new heading, open the release PR, merge it
git switch main && git pull
git tag 0.2.0 && git push origin 0.2.0
```

The tag push triggers the workflow, which:

1. checks that the tag equals the version in all three manifests and that `CHANGELOG.md` has a
   section for it,
2. builds the production images and boots the backend one with `/readyz` reporting `ok`,
3. pushes them to GHCR as `ghcr.io/<owner>/orphan-parts/backend:0.2.0` and
   `.../frontend:0.2.0` (plus `latest`), nothing is pushed if the smoke test fails,
4. creates a GitHub release whose notes are that changelog section.

The job uses only `actions/checkout`, the job token, Docker and `gh`; no other actions and no
stored secrets.

Only a tag triggers it; no image is built or pushed for pull requests or merges. The images are
the release artifact: the demo host pulls them, and a tagged version can be run anywhere without
a build. See [Deployment](../operations/deployment.md).

## `docs.yml`

Runs when `docs/`, `mkdocs.yml`, the docs image, the backend app or the changelog change on `main`.
Exports the OpenAPI document, builds the site with `--strict`, uploads it and deploys to GitHub
Pages through OIDC (`pages: write`, `id-token: write`).
