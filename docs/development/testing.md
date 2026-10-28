# Testing

```bash
./dev test              # everything
./dev test backend      # ruff, mypy, pytest with coverage
./dev test frontend     # eslint, tsc, vitest, production build
./dev test scripts      # bash helper tests
```

## Backend

pytest with coverage, threshold 80 percent. `tests/conftest.py` builds the app with a temporary
data directory and fixture mode on, so no test ever reaches the Model API. Tests are named after
the behaviour they pin down (`test_missing_key_fails_fast_in_live_mode`).

## Frontend

vitest for pure modules under `src/lib/`. Component tests come with the first real pages.

## Scripts

`scripts/tests/run.sh` loads every `test_*.sh`, runs each `test_*` function and counts
`assert_eq`, `assert_true` and `assert_false`. CI runs it on Linux and macOS.

## Fixture mode and recorded fixtures

`OPL_FAKE_API=1` makes the Model API client serve recorded responses. Recording real responses
once (`./dev record-fixtures`) and the evaluation set over the demo photos arrive with the client.
