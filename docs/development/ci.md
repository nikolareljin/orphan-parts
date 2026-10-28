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

1. checks that the tag equals the version in the manifests,
2. builds the production images and pushes them to GHCR as
   `ghcr.io/<owner>/orphan-parts/backend:0.2.0` and `.../frontend:0.2.0` (plus `latest`),
3. boots the published backend image and checks `/readyz`,
4. creates a GitHub release whose notes are the matching changelog section.

Deployments pull those images; see [Deployment](../operations/deployment.md).

## `docs.yml`

Runs when `docs/`, `mkdocs.yml`, the docs image, the backend app or the changelog change on `main`.
Exports the OpenAPI document, builds the site with `--strict`, uploads it and deploys to GitHub
Pages through OIDC (`pages: write`, `id-token: write`).
