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

Versions follow SemVer. `VERSION` is the one place the version is read from by hand, and
`backend/pyproject.toml`, `backend/app/__init__.py` and `frontend/package.json` carry the same
value; every check compares all four. Tags are bare versions, no `v` prefix.

```bash
./dev version 0.2.0      # writes VERSION and every manifest, opens a changelog section
# move the Unreleased notes under the new heading, open the pull request from release/0.2.0,
# merge it: the merge commit is tagged 0.2.0 and the release is published
./dev release            # or tag it yourself on main, after the merge: the admin's command
./dev deploy             # when the release is up: the host pulls it (and the APK is built)
```

`./dev release` refuses unless the checkout is `main`, clean and level with `origin/main`,
`VERSION` matches every manifest and the changelog has the section, and no such tag exists here
or on origin; then it tags `HEAD` and pushes the tag, which the ruleset lets only the admin do.
`--dry-run` runs the checks and stops. The same checks guard the merge workflow below.

`tag-release.yml` runs when a pull request from a `release/x.y.z` branch is merged into `main`.
`scripts/release-tag.sh` reads the version off the branch name and refuses anything that is
not `x.y.z`, a version that differs from any manifest, a changelog without its section, and a
version that is tagged already: an existing tag is never moved or deleted. Then the merge commit
gets the tag and the publish job calls `release.yml`. A pull request closed without a merge, or
from any other branch, does nothing. The tag is pushed with the job token, which on its own
does not start tag-triggered workflows; that is why `release.yml` is called rather than waited
for. The ruleset that limits tag creation lists only the admin role as a bypass actor, so the
job token's push is refused (`GH013 ... creations being restricted`); the job then fails with
the exact command in its run summary, and an admin pushes the tag on the merge commit
(`git tag 0.2.0 <merge commit> && git push origin 0.2.0`), which triggers `release.yml` by
itself. To let the workflow tag on its own, give tag creation a ruleset of its own with GitHub
Actions as a bypass actor and keep updates and deletions admin-only, so a tag is still never
moved.

`release.yml`, called with the tag or triggered by a tag push:

1. checks that the tag equals `VERSION` and the version in all three manifests,
2. assembles the release notes with `scripts/release-notes.sh`: the changelog section for the
   version, the pull requests merged since the previous release (from the merge commits), the
   compare link between the two releases, and the images the release publishes,
3. builds the production images and boots the backend one with `/readyz` reporting `ok`,
4. pushes them to GHCR as `ghcr.io/<owner>/orphan-parts/backend:0.2.0` and
   `.../frontend:0.2.0` (plus `latest`), nothing is pushed if the smoke test fails,
5. creates a GitHub release with those notes,
6. then `android` builds the release APK with `scripts/deploy.sh android` and attaches it to
   the release as `orphan-parts-<version>.apk`, and `deploy`, inert until there is a host, runs `scripts/deploy.sh web` against the host when the repository variable
   `DEPLOY_ENABLED` is `true` and the secrets `DEPLOY_HOST` (`user@host`), `DEPLOY_PATH` and
   `DEPLOY_SSH_KEY` are set. See [Deployment](../operations/deployment.md).

The jobs use only `actions/checkout`, the job token, Docker, `gh` and `ssh`; no other actions,
and no stored secrets beyond the deploy host's, which exist only when a host does. A repository ruleset limits tag creation to the repository admin, plus the tag
workflow once GitHub Actions is on its bypass list, and lets nobody move or delete a tag; the
workflow tags only what the admin merged, so nobody else can trigger a release.

Only a tag, or the tag workflow, triggers it; no image is built or pushed for other pull
requests or merges. The images are the release artifact: the demo host pulls them, and a
tagged version can be run anywhere without a build. See
[Deployment](../operations/deployment.md).

## `deploy.yml`

The hosted demo: the backend to Modal and the web app to Cloudflare Pages, from the
repository's secrets and variables. Inert until the variable `HOSTED_DEPLOY` is `true`; then
it runs from **Run workflow** (both, backend or web) and after every release tag, one run at a
time. Its jobs call `scripts/deploy-hosted.sh`, the same script `./dev deploy hosted` runs,
and use only `actions/checkout`, `actions/setup-python` and `actions/setup-node`. Which
secret and variable is which is on the [Deployment](../operations/deployment.md) page.

## `android.yml`

The app's checks, only when `android/`, `scripts/android.sh` or `VERSION` changed: the unit
tests on the JVM and the debug APK, on the runner's JDK 17 and the SDK it already has. The
smoke run on a device is a local step (`./dev android smoke`), not a CI one.

## `docs.yml`

Runs when `docs/`, `mkdocs.yml`, the docs image, the backend app or the changelog change on `main`.
Exports the OpenAPI document, builds the site with `--strict`, uploads it and deploys to GitHub
Pages through OIDC (`pages: write`, `id-token: write`).
