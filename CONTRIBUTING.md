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
- [Tenancy invariants](#tenancy-invariants)
- [Test validation](#test-validation)
- [Linting and formatting](#linting-and-formatting)
- [Commit conventions](#commit-conventions)
- [Pull request process](#pull-request-process)
- [Signing the CLA](#signing-the-cla)
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
| `tenancy/` | Tenancy and permissions: organizations, projects, memberships, roles, capabilities, queryset scoping |
| `sdk_api/` | Public SDK endpoints, authentication, SSE streaming |
| `analytics/` | Evaluation metrics and reporting |
| `authentication/` | JWT cookie authentication |
| `frontend/` | Next.js dashboard |
| `tests/unit/` | Fast tests with no I/O |
| `tests/integration/` | API-level tests through the Django test client |
| `openspec/` | Specification and design artifacts |

---

## Tenancy invariants

Flagward is multi-tenant. Everything a dashboard request can reach hangs off
one chain:

```
Organization → Project → Environment → FeatureFlag → StrategyRule → Condition
```

The four rules below hold that chain together. They are the ones a change
breaks without meaning to, so each is written with its reason — a rule without
its reason gets tidied away by the next person. Read them before you touch
`tenancy/`, a viewset, or a serializer.

- **No `is_superuser` bypass in the permission layer.** Nothing in
  `tenancy/permissions.py` — or anywhere else on the DRF path — may consult
  `is_superuser` or `is_staff`. The superadmin operates through `/admin/`; a
  bypass in the API would make the tenant boundary conditional on a flag on a
  user row. The guarantee rests on the *absence* of a line, which no reviewer
  can be relied on to keep noticing, so
  `tests/integration/test_tenant_scoping.py::TestNoSuperuserBypass` fails the
  moment one comes back.
- **A resource in another tenant is a 404, never a 403.** Scoping happens in
  `get_queryset()` — `TenantScopedViewSetMixin` for everything at or below
  `Environment`, `orgs_with`/`projects_with` for the two viewsets above it — so
  an invisible object is simply not there. A 403 would confirm the UUID exists.
  403 is reserved for visible-but-unprivileged, and 400 for a write aimed at a
  parent object in another tenant; do not collapse the three.
- **The capability catalogue lives in code, not in a table.**
  `tenancy/capabilities.py` holds every capability string and every
  role → capability grant as frozen module constants, and `resolve_capabilities`
  is a pure function over them — no database, no request, no user object. There
  is nothing to migrate, so permissions version with the code and cannot drift
  between environments. Adding or changing a capability is a code change plus a
  test, never a data fix.
- **Scoping queries stay join-free.** Every branch in `tenancy/scoping.py` is a
  scalar `IN` subquery over the model's own column; no membership table is ever
  traversed as a join in the outer query. Nothing fans out, which is why
  `.distinct()` is needed nowhere. The invariant is asserted structurally by the
  `assert_membership_never_joined` fixture in `tests/conftest.py`, not by
  grepping for `.distinct(` — a new scoping branch has to pass it.

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
npm test            # node --test 'src/**/*.test.ts'
npm run build       # production build must succeed
```

CI runs all three, in that order. `npm test` is Node's built-in `node:test`
runner over the TypeScript sources directly — Node strips the types, so there
is no transpiler step and no test dependency in `package.json`. Put a test
beside the module it covers, named `<module>.test.ts`.

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
   cd frontend && npm run lint && npm test && npm run build
   ```

4. Push and open a pull request against `main`.
5. Fill in the pull request template. Describe the problem, the approach, and
   how you verified it.
6. Keep the pull request focused. A reviewer can hold roughly 400 lines of diff
   in their head at once; beyond that, split the work into a chain of smaller
   pull requests.
7. Address review comments with additional commits — avoid force-pushing during
   review so reviewers can see what changed.
8. Sign the CLA on your first pull request. See below.

---

## Signing the CLA

Your first pull request needs one comment on it:

```
I have read the CLA document and I hereby sign the CLA
```

That is the whole process. You sign **once** — it covers every contribution
you make to this project afterwards.

### What you are agreeing to, in plain terms

You keep the copyright in everything you write. You are granting a licence
broad enough that Flagward can be relicensed later if it has to be — to a
copyleft licence, or to offer a commercial licence alongside the open one.

**Why ask at all, when the project is MIT and means to stay open?** Because
the option has to be kept open now or not at all. Every contributor owns the
copyright in their own contribution, so relicensing needs all of them to
agree. At three contributors that is an afternoon of email. At fifty, spread
over years, with old addresses and changed jobs, it is a permanent no.

Asking today costs you one comment. Not asking closes a door that cannot be
reopened.

It is **not** a transfer of ownership, not exclusive, and has no claim on
anything you write outside this project. Use your own contribution wherever
else you like.

The full text is in [CLA.md](CLA.md), adapted from the Apache Software
Foundation's ICLA v2.0 — deliberately not novel, so you can recognise what
you are signing.

If your employer owns the intellectual property you create, check that you
are allowed to contribute before signing (clause 4). If your organisation
would rather cover several people under one corporate agreement, open an
issue and we will arrange it.

### Checklist

- [ ] Tests added or updated for the change
- [ ] `pytest` passes locally
- [ ] `ruff check .` passes
- [ ] `npm run lint`, `npm test` and `npm run build` pass, if the frontend changed
- [ ] Documentation updated, if behaviour changed
- [ ] Commits follow Conventional Commits

---

## Reporting security issues

Please do **not** open a public issue for a security vulnerability. Follow the
process in [SECURITY.md](SECURITY.md) instead.
