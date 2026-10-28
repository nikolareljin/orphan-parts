# Code style

## Python

- ruff for linting and formatting, line length 100, rule sets `E F I B UP N W SIM RUF`.
- mypy strict with the pydantic plugin. `mypy app` must be clean.
- Type hints everywhere; `snake_case` functions, `PascalCase` classes.
- Comments explain why, not what. No docstring on every function.
- Settings come from `app.config.Settings`; model IDs are never literals.

## TypeScript

- strict compiler options, eslint with the typescript-eslint and react-hooks rules.
- 2-space indent, `PascalCase` components, `camelCase` everything else.
- All backend calls go through `src/lib/api.ts`.

## Bash

- `#!/usr/bin/env bash`, `set -euo pipefail`, 2-space indent, `snake_case` functions.
- bash 3.2-safe: no `mapfile`, no associative arrays, no GNU-only flags (`sed -i`, `readlink -f`).
- Optional tools are guarded with `has_cmd`.

## Commits

Conventional Commits, one line, imperative: `feat(match): treat 19.5V and 19.50V as equal`.
