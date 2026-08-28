# Contributing to Flagward

Thanks for taking the time to contribute. This document explains how to get a
working environment, the quality bar a change has to clear, and how to get your
pull request merged.

By participating in this project you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

---

## Table of contents

- [Ways to contribute](#ways-to-contribute)
- [Development setup](#development-setup)
- [Project layout](#project-layout)
- [Test validation](#test-validation)
- [Linting and formatting](#linting-and-formatting)
- [Commit conventions](#commit-conventions)
- [Pull request process](#pull-request-process)
- [Reporting security issues](#reporting-security-issues)

---

## Ways to contribute

- **Report a bug** — open an issue with reproduction steps, expected vs. actual
  behaviour, and your environment.
- **Propose a feature** — open an issue describing the problem first. Agreement
  on the problem makes the solution review much shorter.
- **Improve documentation** — corrections and clarifications are welcome and
  are reviewed the same way as code.
- **Submit code** — please open or comment on an issue before starting
  significant work, so effort is not duplicated.

Good first issues are labelled [`good first issue`][gfi].

[gfi]: https://github.com/basb7/flagward/labels/good%20first%20issue

---

## Development setup

Flagward is a Django REST backend plus a Next.js dashboard. You can run either
stack in Docker or locally.

### Option 1 — Docker (recommended)

```bash
git clone https://github.com/basb7/flagward.git
cd flagward

docker compose -f compose.dev.yml up -d --build
docker compose -f compose.dev.yml exec backend python manage.py migrate
docker compose -f compose.dev.yml exec backend python manage.py create_super_user
```

The backend is served on `http://localhost:8000`, the dashboard on
`http://localhost:3000`.

### Option 2 — Local

**Backend** (Python 3.14, Django 6.1):

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements/dev.txt

python manage.py migrate           # SQLite by default
python manage.py createsuperuser
python manage.py runserver
```

Postgres is used automatically when `DB_NAME` or `USE_POSTGRES` is set;
otherwise the project falls back to SQLite, which is enough for the test suite.

**Frontend**:

```bash
cd frontend
npm install
npm run dev
```

### Configuration

Copy `.env.example` to `.env` and adjust as needed. Every value in
`.env.example` is a development placeholder — **never reuse them in a
deployment**. In particular, `SECRET_KEY` must be set to a unique random value
and `DEBUG` must be `False` outside of local development.

---

## Project layout

| Path | Purpose |
|------|---------|
| `config/` | Django project settings, URLs, ASGI/WSGI entrypoints |
| `core/` | Shared utilities and management commands |
| `core_flags/` | Feature flag domain: models, evaluation, overrides |
| `sdk_api/` | Public SDK endpoints, authentication, SSE streaming |
| `analytics/` | Evaluation metrics and reporting |
| `authentication/` | JWT cookie authentication |
| `frontend/` | Next.js dashboard |
| `tests/unit/` | Fast tests with no I/O |
| `tests/integration/` | API-level tests through the Django test client |
| `openspec/` | Specification and design artifacts |

---

## Test validation

**Every pull request must keep the full suite green.** The CI workflow runs the
same commands documented here, so a change that passes locally passes in CI.

### Running the backend suite

```bash
source .venv/bin/activate
pytest                      # full suite
pytest -q                   # quiet output
pytest tests/unit           # unit tests only
pytest tests/integration    # integration tests only
pytest tests/unit/test_evaluation.py::TestBooleanFlag    # a single test
```

Pytest is configured in `pyproject.toml`; no extra flags are required.

In Docker:

```bash
docker compose -f compose.dev.yml exec backend pytest
```

### Coverage

```bash
coverage run -m pytest
coverage report -m
coverage html               # writes htmlcov/index.html
```

Coverage is not gated at a fixed percentage, but a pull request should not
reduce it. New behaviour needs new tests.

### What we expect from tests

- **Test behaviour, not implementation.** Assert on the response or the
  returned value, not on how it was produced.
- **Put the test in the right tier.** No network or database in `tests/unit/`;
  use `tests/integration/` for anything that goes through the API.
- **A bug fix starts with a failing test.** Add the test that reproduces the
  bug, watch it fail, then fix it. That test is the proof the bug is gone and
  the guard against it coming back.
- **Name tests after the scenario**, e.g.
  `test_override_takes_precedence_over_rules`, not `test_override_2`.
- **Keep them deterministic.** No reliance on wall-clock time, ordering of
  unordered collections, or network access.

### Frontend checks

```bash
cd frontend
npm run lint        # biome check .
npm run build       # production build must succeed
```

---

## Linting and formatting

Backend uses [Ruff](https://docs.astral.sh/ruff/), frontend uses
[Biome](https://biomejs.dev/). Both are enforced in CI.

```bash
# Backend
ruff check .
ruff check --fix .

# Frontend
cd frontend
npm run lint
npm run lint:fix
npm run format
```

Style notes:

- Line length is 120 characters.
- Follow existing Django conventions; type hints are encouraged.
- Do not reformat unrelated code in a pull request — it hides the real diff.

---

## Commit conventions

This project uses [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(<optional scope>): <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`,
`chore`, `revert`.

Examples:

```
feat(flags): add percentage rollout strategy
fix(sdk): return 401 instead of 500 on an unknown api key
docs: document override precedence
test(evaluation): cover multivariate fallback
```

Write the description in the imperative mood ("add", not "added"), keep the
subject under 72 characters, and explain *why* in the body when the reason is
not obvious from the diff.

Branch names follow the same shape: `feat/percentage-rollout`,
`fix/sdk-unknown-key`.

---

## Pull request process

1. Fork the repository and create a branch from `main`.
2. Make your change, with tests.
3. Run the full local check before pushing:

   ```bash
   ruff check . && pytest
   cd frontend && npm run lint && npm run build
   ```

4. Push and open a pull request against `main`.
5. Fill in the pull request template. Describe the problem, the approach, and
   how you verified it.
6. Keep the pull request focused. A reviewer can hold roughly 400 lines of diff
   in their head at once; beyond that, split the work into a chain of smaller
   pull requests.
7. Address review comments with additional commits — avoid force-pushing during
   review so reviewers can see what changed.

### Checklist

- [ ] Tests added or updated for the change
- [ ] `pytest` passes locally
- [ ] `ruff check .` passes
- [ ] `npm run lint` and `npm run build` pass, if the frontend changed
- [ ] Documentation updated, if behaviour changed
- [ ] Commits follow Conventional Commits

---

## Reporting security issues

Please do **not** open a public issue for a security vulnerability. Follow the
process in [SECURITY.md](SECURITY.md) instead.
