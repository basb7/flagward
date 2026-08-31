# Flagward

[![CI](https://github.com/basb7/flagward/actions/workflows/ci.yml/badge.svg)](https://github.com/basb7/flagward/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-informational.svg)](LICENSE)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/)
[![Django 6.1](https://img.shields.io/badge/django-6.1-092E20.svg)](https://www.djangoproject.com/)

**Open-source feature flags with local SDK evaluation and real-time updates.**

Flagward is a modular feature flag system built with Django and Redis. SDKs
download the flag rules once and evaluate them locally in under a millisecond,
so a flag check never blocks on a network call — and changes still reach every
client in real time over SSE.

- **Local evaluation** — rules are evaluated in your process, not over HTTP
- **Real-time propagation** — flag changes stream to connected SDKs via SSE
- **Kill switch overrides** — force a flag on or off during an incident, with an
  audit trail
- **Targeting rules** — boolean and multivariate flags with percentage rollouts
- **Self-hostable** — one `docker compose up` away

> [!IMPORTANT]
> Flagward ships with development defaults so it runs out of the box. They are
> **not** safe for a deployment. Read [SECURITY.md](SECURITY.md#deployment-hardening)
> before exposing an instance.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Backend (Django)                                           │
│  ├── core_flags/    # Flag models + evaluation engine       │
│  ├── sdk_api/       # SDK surface + monitoring read API     │
│  ├── analytics/     # Aggregation endpoints (no models)     │
│  ├── core/          # Shared API mixins, management cmds    │
│  └── config/        # Settings, ASGI, URLs                  │
├─────────────────────────────────────────────────────────────┤
│  Dashboard (Next.js)                                        │
│  ├── Overview       # Live counters + evaluation volume     │
│  ├── Flags          # Toggle, target, override              │
│  ├── Environments   # API keys                              │
│  └── Monitoring     # SDKs, evaluation log, override trail   │
├─────────────────────────────────────────────────────────────┤
│  SDK (Client Libraries)                                     │
│  ├── Download flag rules once                               │
│  ├── Evaluate locally (< 1ms)                               │
│  └── Receive real-time updates via SSE                      │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Option 1: Docker (Recommended)

The fastest way to get started:

```bash
# Clone the repository
git clone https://github.com/basb7/flagward.git
cd flagward

# Start all services (development mode with hot-reload)
docker compose -f compose.dev.yml up

# Or start in production mode
docker compose up
```

**Development mode** (`compose.dev.yml`):
- Hot-reload enabled
- Debug mode on
- Runserver (auto-restart on code changes)

**Production mode** (`compose.yml`):
- Gunicorn with 4 workers
- Debug mode off
- Optimized for performance

**Services:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Django Admin: http://localhost:8000/admin/
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### Option 2: Local Development

#### Prerequisites

- Python 3.14+
- Node.js 20+

#### Backend Setup

```bash
# Clone the repository
git clone https://github.com/basb7/flagward.git
cd flagward

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements/base.txt
pip install -r requirements/dev.txt

# Setup database (SQLite by default)
python manage.py migrate

# Create admin user
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

#### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run with verbose output
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/unit/test_models.py
```

## Docker Compose

### Files

| File | Mode | Description |
|------|------|-------------|
| `compose.dev.yml` | Development | Hot-reload, debug, runserver |
| `compose.yml` | Production | Gunicorn, optimized, secure |

### Commands

```bash
# Development (with hot-reload)
docker compose -f compose.dev.yml up

# Development (detached)
docker compose -f compose.dev.yml up -d

# Production
docker compose up

# Production (detached)
docker compose up -d

# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v

# View logs
docker compose logs -f backend

# Rebuild images
docker compose build --no-cache
```

### Environment Variables

For production, copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | `django-insecure-dev-key-change-in-production` |
| `DEBUG` | Debug mode | `True` |
| `DJANGO_SUPERUSER_USERNAME` | Admin username | `admin` |
| `DJANGO_SUPERUSER_EMAIL` | Admin email | `admin@example.com` |
| `DJANGO_SUPERUSER_PASSWORD` | Admin password | `admin` |
| `ALLOWED_HOSTS` | Allowed domains | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | CORS origins | `http://localhost:3000` |
| `CSRF_TRUSTED_ORIGINS` | CSRF origins | `http://localhost:3000` |
| `FRONTEND_BASE_URL` | Where the frontend lives; used to build the clickable links in the password-reset email and the invitation-create response (a trailing slash is stripped, so it never doubles up) | `http://localhost:3000` |
| `EMAIL_HOST` | SMTP server host (optional -- see below) | unset |
| `EMAIL_PORT` | SMTP server port | `587` |
| `EMAIL_HOST_USER` | SMTP username | empty |
| `EMAIL_HOST_PASSWORD` | SMTP password | empty |
| `EMAIL_USE_TLS` | Use TLS for SMTP | `True` |
| `DEFAULT_FROM_EMAIL` | "From" address for outgoing mail | `webmaster@localhost` |

Email is entirely optional; a self-hosted instance keeps working with none of
this set. It backs the password-reset flow (`POST
/api/v1/auth/password-reset/request/` and `/confirm/`):

* With `EMAIL_HOST` unset and `DEBUG=True`, outgoing messages print to the
  terminal (Django's console email backend) instead of being sent, so the
  whole flow is testable without a mail server.
* With `EMAIL_HOST` unset and `DEBUG=False`, messages are silently discarded
  instead -- printing a password-reset token to production stdout, which is
  routinely shipped to log aggregators, is worse than not sending it.
* `GET /api/v1/auth/config/` reports `password_reset_enabled` so the frontend
  knows whether to offer a "forgot password" link at all -- it is `true`
  whenever `EMAIL_HOST` is set, or whenever `DEBUG=True` (console backend).

### Production Deployment

1. **Set up your server** (AWS, GCP, DigitalOcean, etc.)

2. **Clone the repository**
   ```bash
   git clone https://github.com/basb7/flagward.git
   cd flagward
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your production values
   ```

4. **Start services**
   ```bash
   docker compose up -d
   ```

5. **Verify**
   ```bash
   docker compose ps
   docker compose logs backend
   ```

6. **Set up SSL** (recommended)
   - Use Nginx or Traefik as reverse proxy
   - Configure SSL certificates (Let's Encrypt)

### Development Workflow

```bash
# Start development environment
docker compose -f compose.dev.yml up

# Make code changes (auto-reload)

# Run tests
docker compose -f compose.dev.yml exec backend python -m pytest tests/

# Access Django shell
docker compose -f compose.dev.yml exec backend python manage.py shell

# Create migrations
docker compose -f compose.dev.yml exec backend python manage.py makemigrations

# Apply migrations
docker compose -f compose.dev.yml exec backend python manage.py migrate
```

## Creating Your First Flag

### Using the Frontend (Recommended)

In production, use the web dashboard at http://localhost:3000:

1. **Login** with your superuser credentials
2. **Create Environment**: Go to Environments → New Environment
   - Name: Production
   - Key: prod
   - Save → API key is auto-generated
3. **Create Feature Flag**: Go to Flags → New Flag
   - Select environment: Production
   - Key: new-dashboard
   - Name: New Dashboard
   - Type: BOOLEAN
4. **Turn it on**: flip the switch in the Status column
5. **Add Rules** (optional): row menu → Rules → New Rule
   - Priority: 1
   - Operator Logic: AND
6. **Add Conditions** (optional): Click on the rule → Condition
   - Attribute: country
   - Operator: Equals
   - Value: US
7. **Watch it work**: Monitoring shows which SDKs are connected and every
   evaluation they logged

### Killing a flag during an incident

Do **not** reach for the switch — that edits the flag's design and loses the
state it was in. Instead:

1. Go to **Monitoring → Overrides → New override**
2. Pick the flag, choose `Disabled (kill switch)`, write the reason
3. The flag is forced off immediately, for everyone, ignoring its targeting rules

Its switch on the Flags page now shows `Overridden` and is locked. When the
incident is over, hit **Lift** (Monitoring, or the flag's row menu) and the flag
returns to exactly the configuration it had. The override stays in the trail with
its reason and timestamps.

### Using Django Admin (Development Only)

For development and debugging, you can also use the Django admin at http://localhost:8000/admin/:

1. Go to http://localhost:8000/admin/
2. Login with your superuser
3. Navigate to the model you want to edit
4. Create/edit entries directly

> **Note**: The Django admin is useful for development and debugging, but the frontend dashboard is the primary interface for managing feature flags in production.

### Creation Order

```
1. ENVIRONMENT (first)          # carries the API key SDKs authenticate with
   └── 2. FEATURE FLAG          # is_enabled = the configured state
         └── 3. STRATEGY RULES (optional)   # who gets it
               └── 4. CONDITIONS (optional) # attribute + operator + value

   FLAG OVERRIDE                # not part of setup: an incident tool.
                                # Forces the value, bypasses 3 and 4,
                                # and is lifted when the incident ends.
```

## Project Structure

```
flagward/
├── config/              # Django settings, ASGI, URLs
├── core/                # Shared building blocks
│   ├── api/mixins.py    # QueryParamFilterMixin (query-param filtering)
│   └── management/commands/create_super_user.py
├── core_flags/          # Core flag models and evaluation engine
│   ├── models.py        # Environment, FeatureFlag, StrategyRule, Condition, FlagOverride
│   ├── services.py      # FlagEvaluationService (override → is_enabled → rules)
│   ├── admin.py         # Django admin configuration
│   └── api/             # Flag management + override endpoints
├── sdk_api/             # SDK surface and monitoring
│   ├── models.py        # SDKRegistration, EvaluationLog
│   ├── views.py         # /sdk/flags/, /sdk/evaluate/, /sdk/register/, /sdk/stream/
│   ├── payloads.py      # THE SDK wire format (shared by /flags/ and /stream/)
│   ├── authentication.py # SDK authentication via API key
│   └── api/             # Read-only monitoring endpoints for the dashboard
├── analytics/           # Aggregation endpoints (no models)
│   ├── services.py      # All aggregation lives here, testable without HTTP
│   └── api/             # Thin views over those services
├── tests/               # Test suite
│   ├── unit/            # Models, evaluation service, override precedence
│   └── integration/     # API endpoints, analytics, SDK payload
├── frontend/            # Next.js dashboard
│   ├── src/app/dashboard/  # Overview, flags, environments, monitoring
│   ├── src/components/ui/  # Design-token primitives (Badge, Switch, StatCard…)
│   ├── src/components/charts/ # Evaluation volume chart
│   ├── src/lib/api.ts   # Typed API client
│   ├── Dockerfile       # Frontend Docker image
│   └── package.json     # Dependencies
├── compose.dev.yml      # Docker Compose for development
├── compose.yml          # Docker Compose for production
├── Dockerfile           # Backend Docker image
├── .env.example         # Environment variables template
└── openspec/            # SDD artifacts (proposal, specs, design, tasks)
```

## API Endpoints

All dashboard endpoints require an authenticated session or JWT cookie.
Every list endpoint is paginated (`PAGE_SIZE = 20`).

### Auth

Tokens travel in httpOnly cookies, so the browser never handles them directly.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/register/` | Create a user |
| `POST` | `/api/v1/auth/login/` | Sets the auth cookies |
| `POST` | `/api/v1/auth/logout/` | Clears them |
| `POST` | `/api/v1/auth/refresh/` | Rotates the access token |
| `GET` | `/api/v1/auth/me/` | Current user |
| `GET` | `/api/v1/health/` | Liveness probe, no auth required |

### Flag management (core_flags)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` `POST` | `/api/v1/environments/` | Environments (API key is auto-generated) |
| `GET` `PATCH` `DELETE` | `/api/v1/environments/{id}/` | One environment |
| `GET` `POST` | `/api/v1/flags/` | Feature flags |
| `GET` `PATCH` `DELETE` | `/api/v1/flags/{id}/` | One flag |
| `GET` `POST` | `/api/v1/rules/` | Strategy rules |
| `GET` `PATCH` `DELETE` | `/api/v1/rules/{id}/` | One rule |
| `GET` `POST` | `/api/v1/conditions/` | Conditions |
| `GET` `PATCH` `DELETE` | `/api/v1/conditions/{id}/` | One condition |

Filters: `/flags/?environment=&is_enabled=&flag_type=`, `/rules/?flag=`,
`/conditions/?rule=`. A malformed filter value returns `400`, never an empty page.

The flag payload distinguishes configuration from what is actually served:

```jsonc
{
  "key": "checkout",
  "is_enabled": true,            // configured state
  "effective_is_enabled": false, // what SDKs serve, after overrides
  "active_override": {           // null when nothing is forcing the flag
    "id": "...",
    "is_enabled": false,
    "reason": "Payment provider outage",
    "created_at": "..."
  }
}
```

### Overrides (kill switch)

An active override forces a flag's value and **bypasses its targeting rules**.
It never rewrites `is_enabled`, so lifting it restores the configured state.
One active override per flag: recording a new one lifts the previous.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` `POST` | `/api/v1/overrides/` | Trail of overrides, newest first |
| `GET` | `/api/v1/overrides/{id}/` | One override |
| `POST` | `/api/v1/overrides/{id}/lift/` | Stop forcing the flag; the row stays |

Rows are never edited or deleted (`PUT`/`PATCH`/`DELETE` return `405`) — that is
what preserves the record of who forced what and why. Filters:
`?flag=`, `?environment=`, `?is_enabled=`, `?active=true|false`.

```bash
# Kill a flag, with a reason
curl -X POST -b cookies.txt -H "Content-Type: application/json" \
  -d '{"flag": "<flag_id>", "is_enabled": false, "reason": "Payment provider outage"}' \
  http://localhost:8000/api/v1/overrides/

# Put it back the way it was configured
curl -X POST -b cookies.txt http://localhost:8000/api/v1/overrides/<id>/lift/
```

### Monitoring (read-only)

Written by the SDK surface, never edited by hand.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/sdk-registrations/` | Connected SDKs: type, version, last seen |
| `GET` | `/api/v1/evaluations/` | Evaluation log |

Filters: `/sdk-registrations/?environment=&sdk_type=&version=`,
`/evaluations/?flag=&environment=&result=true|false`.

### Analytics

Aggregates for the dashboard. All four accept `?environment=<uuid>` to scope.

| Endpoint | Returns |
|---|---|
| `GET /api/v1/analytics/overview/` | Flag / SDK / evaluation / override counters |
| `GET /api/v1/analytics/evaluations/timeseries/?hours=24` | Hourly buckets (1-168h), empty hours included |
| `GET /api/v1/analytics/flags/top/?hours=24&limit=5` | Most evaluated flags with their true rate |
| `GET /api/v1/analytics/sdks/health/` | Fleet health by SDK type and version |

`overview` reports both the configured and the effective picture:

```jsonc
{
  "flags": {
    "total": 12, "enabled": 5, "disabled": 7,
    "effective_enabled": 4,  // after overrides
    "overridden": 2          // flags currently being forced
  },
  "sdks": { "total": 4, "active": 2, "stale": 2, "active_window_minutes": 5 },
  "evaluations": { "total": 1500, "last_24h": 320, "true_rate": 0.6691 },
  "overrides": { "total": 7, "active": 2, "last_24h": 1 }
}
```

> An SDK counts as **active** when it polled within the last 5 minutes
> (`analytics.services.SDK_ACTIVE_WINDOW`); past that it is **stale**.

### SDK API

```bash
# Get API key from admin (Environment → api_key)

# Get all flags for local evaluation
curl -H "X-API-Key: <api_key>" http://localhost:8000/api/v1/sdk/flags/

# Evaluate flags with context (server-side)
curl -X POST -H "X-API-Key: <api_key>" -H "Content-Type: application/json" \
  -d '{"context": {"country": "US", "plan": "premium"}}' \
  http://localhost:8000/api/v1/sdk/evaluate/

# Register SDK instance
curl -X POST -H "X-API-Key: <api_key>" -H "Content-Type: application/json" \
  -d '{"sdk_type": "PYTHON", "version": "1.0.0"}' \
  http://localhost:8000/api/v1/sdk/register/

# SSE streaming for real-time updates
curl -N -H "X-API-Key: <api_key>" http://localhost:8000/api/v1/sdk/stream/
```

#### The flag payload an SDK evaluates locally

```jsonc
{
  "flags": [
    {
      "key": "checkout",
      "name": "Checkout",
      "is_enabled": false,   // already effective: override applied if any
      "flag_type": "BOOLEAN",
      "rules": [],           // stripped to [] while an override is active
      "overridden": true     // informational: this value is being forced
    }
  ]
}
```

`is_enabled` is the **effective** value, so a client never needs to know about
overrides to be correct. When one is active the rules are stripped, which makes
local evaluation reproduce the server engine exactly: no rules left, so the flag
value *is* the answer.

Local evaluation an SDK must implement:

```
if not is_enabled:        -> false
if rules is empty:        -> true
otherwise:                -> true if any rule matches the context
```

`/sdk/flags/` and `/sdk/stream/` share one projection (`sdk_api/payloads.py`), so
the stream cannot drift from the polling endpoint. Lifting an override is a flag
change like any other and is pushed over SSE.

## Flag Evaluation

### Boolean Flags

```python
from core_flags.services import FlagEvaluationService

service = FlagEvaluationService()
result = service.evaluate_flag(flag, {"country": "US", "plan": "premium"})
# Returns: True or False
```

### Multivariate Flags

```python
# Returns variant name (e.g., "control", "variant_a", "variant_b")
result = service.evaluate_flag(multivariate_flag, context)
```

### Evaluation Logic

Order of precedence in `FlagEvaluationService.evaluate_flag`:

1. **Active override** — wins over everything and bypasses the rules. A forced
   value has nothing left to evaluate.
2. **`is_enabled`** — a disabled flag is `false`, whatever its rules say.
3. **Rules** — no rules means `true`; otherwise any matching rule wins.

- **AND logic**: All conditions must match
- **OR logic**: Any condition can match
- **Priority ordering**: Rules evaluated by priority (lower = higher priority)
- **Operators**: EQUALS, NOT_EQUALS, GREATER_THAN, LESS_THAN, IN_LIST, CONTAINS

### Configuration vs. intervention

The switch and the override answer different questions, which is why they are
separate:

| | Switch (`is_enabled`) | Override |
|---|---|---|
| What it is | a decision | an incident |
| Means | "this is how the feature should behave" | "right now, ignore the design" |
| Lifetime | permanent | temporary, until lifted |
| Respects targeting | yes | no, bypasses it |
| Carries a reason | no | yes, required |
| Undone by | changing the design again | `lift/`, which restores the design |

Toggling the switch to handle an incident loses the information about how the
flag *was* configured. An override leaves the configuration untouched, so
lifting it puts the flag back without anyone having to remember.

While an override is active the dashboard **locks** that flag's switch and
labels it `Overridden` — two sources of truth would let the UI lie about what
the SDKs are serving.

## Known Limitations

- **`EvaluationLog` grows without bound.** `/sdk/evaluate/` writes one row per
  flag per call, so a call covering 20 flags writes 20 rows. There is no
  retention policy and `timestamp` has no index, so the analytics queries
  (`timestamp__gte`) table-scan. Add an index and a purge/retention strategy
  before running this under real traffic.
- **Multivariate flags are not implemented.** `FlagType.MULTIVARIATE` exists on
  the model, but `FlagEvaluationService` only ever returns a boolean.
- **No settings page.** SDK/API keys are read from the Environments page.
- **`test_admin_api.py` is a stub.** Its 25 tests are `pass` bodies with
  `# TODO: Implement admin authentication`, so the environment/flag/rule/condition
  CRUD has no automated coverage yet.

## Models

| Model | Purpose |
|-------|---------|
| **Environment** | Deployment target (production, staging, dev) |
| **FeatureFlag** | Toggle for a feature (enabled/disabled) |
| **StrategyRule** | Group of conditions for a flag |
| **Condition** | Single rule (attribute + operator + value) |
| **FlagOverride** | Kill switch. Forces a flag's value while active; `lift()` stamps `cleared_at` and restores the configured state. Never deleted. |
| **SDKRegistration** | Tracks connected SDK instances (type, version, `last_seen_at`) |
| **EvaluationLog** | One row per flag per evaluation call, for analytics |

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | `django-insecure-dev-key-change-in-production` |
| `DEBUG` | Enable debug mode | `True` |
| `POSTGRES_DB` | Database name | `flagward` |
| `POSTGRES_USER` | Database user | `postgres` |
| `POSTGRES_PASSWORD` | Database password | `postgres` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `NEXT_PUBLIC_API_URL` | Frontend API URL | `http://localhost:8000` |
| `DJANGO_SUPERUSER_USERNAME` | Admin username | `admin` |
| `DJANGO_SUPERUSER_EMAIL` | Admin email | `admin@example.com` |
| `DJANGO_SUPERUSER_PASSWORD` | Admin password | `admin` |
| `ALLOWED_HOSTS` | Allowed domains | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | CORS origins | `http://localhost:3000` |
| `CSRF_TRUSTED_ORIGINS` | CSRF origins | `http://localhost:3000` |
| `FRONTEND_BASE_URL` | Where the frontend lives; used to build the clickable links in the password-reset email and the invitation-create response | `http://localhost:3000` |
| `EMAIL_HOST` | SMTP server host (optional, powers password reset) | unset |
| `EMAIL_PORT` | SMTP server port | `587` |
| `EMAIL_HOST_USER` | SMTP username | empty |
| `EMAIL_HOST_PASSWORD` | SMTP password | empty |
| `EMAIL_USE_TLS` | Use TLS for SMTP | `True` |
| `DEFAULT_FROM_EMAIL` | "From" address for outgoing mail | `webmaster@localhost` |

See the "Environment Variables" section above for what happens with no
`EMAIL_HOST` set, in both `DEBUG=True` and `DEBUG=False`.

## Development

### Docker Commands

```bash
# Start development environment
docker compose -f compose.dev.yml up

# Start in background
docker compose -f compose.dev.yml up -d

# View logs
docker compose -f compose.dev.yml logs -f backend

# Stop services
docker compose -f compose.dev.yml down

# Access backend container
docker compose -f compose.dev.yml exec backend bash

# Run management commands
docker compose -f compose.dev.yml exec backend python manage.py createsuperuser
docker compose -f compose.dev.yml exec backend python manage.py shell

# Run tests
docker compose -f compose.dev.yml exec backend python -m pytest tests/
```

### Linting

```bash
# Run linter
ruff check .

# Auto-fix issues
ruff check . --fix
```

### Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run with verbose output
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/unit/test_models.py

# Run tests in Docker
docker compose -f compose.dev.yml exec backend python -m pytest tests/
```

### Code Style

- Line length: 120 characters
- Django conventions
- Type hints encouraged

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) — it
covers the development setup, the test and lint commands CI runs, the commit
convention, and the pull request process.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

Quick check before opening a pull request:

```bash
ruff check . && pytest
cd frontend && npm run lint && npm run build
```

## Security

Found a vulnerability? **Do not open a public issue.** Report it privately
through [GitHub Security Advisories](https://github.com/basb7/flagward/security/advisories/new).

Before deploying, read the [deployment hardening](SECURITY.md#deployment-hardening)
table — the shipped defaults are for local development only.

## License

[MIT](LICENSE) © Brian Suárez
