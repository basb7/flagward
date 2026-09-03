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
│  ├── tenancy/       # Organizations, projects, roles        │
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
│  ├── Monitoring     # SDKs, evaluation log, override trail  │
│  └── Members        # Roles, grants, invitations            │
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

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

The SQLite fallback is why the backend runs with nothing configured, and it is
worth knowing about: it is not what CI or a deployment runs, so a migration or
a query that behaves differently there will not show up locally.

The file is read on startup, in development and in production alike, and is
resolved next to `manage.py` rather than from the working directory — a
management command run from anywhere sees the same settings.

Values already present in the environment win over the file. A container that
sets `DB_HOST` through compose keeps it even if an `.env` reached the image, so
the file is a convenience and never a way to quietly override a deployment.

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | `django-insecure-dev-key-change-in-production` |
| `DEBUG` | Debug mode | `True` |
| `DJANGO_SUPERUSER_USERNAME` | Admin username | `admin` |
| `DJANGO_SUPERUSER_EMAIL` | Admin email | `admin@example.com` |
| `DJANGO_SUPERUSER_PASSWORD` | Admin password | `admin` |
| `DB_NAME` | PostgreSQL database. **Setting this (or `USE_POSTGRES`) is what selects PostgreSQL**; with neither, the app falls back to SQLite at `db.sqlite3` | unset (SQLite) |
| `DB_USER` | PostgreSQL user | `postgres` |
| `DB_PASSWORD` | PostgreSQL password | empty |
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `REDIS_URL` | Cache backend. Unset, Django uses an in-process cache — correct for one development server, wrong for more than one process | unset |
| `REDIS_STREAMS_URL` | Backs the flag-change stream to connected SDKs. Unset, flags still evaluate; what stops is live propagation | unset |
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

1. **Register** at http://localhost:3000/register — username, email, password.

   Not your superuser. The superuser administers the *deployment*, through
   Django admin; it holds no membership anywhere, so the dashboard API shows
   it nothing at all, not even a list of organizations it does not belong to.
   The dashboard is for ordinary accounts, and anyone can register one.
   Whoever registers becomes the `ADMIN` of the organizations they create.
2. **Create your organization**: the dashboard asks for one the moment you
   arrive with none, and the nav keeps a "New organization" button for later
   - Name: Acme
   - Creating it makes you its `ADMIN`, in the same transaction
3. **Create a project**: nav → New project
   - Name: Checkout
   - No key to invent — the server derives `checkout` from the name
   - The nav's organization and project selectors decide which project every
     other screen is showing
4. **Create Environment**: Go to Environments → New Environment
   - Name: Production
   - Save → key derived (`production`), and the API key is auto-generated
     and copyable from the table
5. **Create Feature Flag**: Go to Flags → New Flag
   - Select environment: Production
   - Key: new-dashboard
   - Name: New Dashboard
6. **Turn it on**: flip the switch in the Status column
7. **Add Rules** (optional): row menu → Rules → New Rule
   - Priority: 1
   - Operator Logic: AND
8. **Add Conditions** (optional): Click on the rule → Condition
   - Attribute: country
   - Operator: Equals
   - Value: US
9. **Watch it work**: Monitoring shows which SDKs are connected

   It will not show evaluations from a client evaluating locally, which is
   what the JavaScript SDKs do -- those never reach the server. Only calls to
   `POST /api/v1/sdk/evaluate/` are recorded. See
   [Consuming flags from your app](#consuming-flags-from-your-app).

### Inviting someone into your organization

Go to **Members → Invite by link**, pick the organization role, and you get a
single-use link back exactly once — the server stores only its hash, so a
database dump yields no working invitation. Whoever opens the link joins with
the role baked into it, and the link is spent.

An organization role is deliberately almost nothing. `ADMIN` is the full key to
the account: every capability at every level, including deleting the
organization with every project, environment and flag under it. `USER`, the
only other one, grants exactly `org.view`.

So a plain `USER` with no project or environment grant sees the organization's
name and **nothing else**. Projects, environments and flags all come back
empty, and fetching one by its UUID answers `404`, not `403` — a row you cannot
see must not even confirm that it exists.

Access is widened from there, on **Members → Grant role**: a project role
covers everything in that project, an environment role covers one environment,
and both use the same four names (`ADMIN`, `EDITOR`, `OPERATOR`, `VIEWER`).
Grants only ever add. There is no carve-out — you cannot give someone a whole
project and then take one environment back, and no lower grant narrows a higher
one. Before saving, the dialog previews the exact capabilities the proposed
role would produce, computed by the same function that enforces them, so the
preview cannot drift from the answer.

Removing someone's organization membership also removes every project and
environment grant they held inside it.

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

The superuser's reach ends here. Nothing in the dashboard API consults
`is_superuser`: access comes from memberships only, so a superuser holding none
sees no organization, no project and no flag through `/api/v1/`, and gets the
same `404` on a foreign row as anyone else. To use the dashboard, register an
account like everybody else.

### Creation Order

```
1. ORGANIZATION (first)         # you create it, and become its ADMIN
   └── 2. PROJECT               # key derived from the name
         └── 3. ENVIRONMENT     # key derived too; carries the API key
                                # SDKs authenticate with
               └── 4. FEATURE FLAG          # is_enabled = the configured state
                     └── 5. STRATEGY RULES (optional)   # who gets it
                           └── 6. CONDITIONS (optional) # attribute + operator + value

   FLAG OVERRIDE                # not part of setup: an incident tool.
                                # Forces the value, bypasses 5 and 6,
                                # and is lifted when the incident ends.
```

### Which keys you type, and which are derived

| Key | Who writes it |
|---|---|
| `Project.key` | Derived from the name when the project is created |
| `Environment.key` | Derived from the name when the environment is created |
| `FeatureFlag.key` | You do — it is the string your code passes to `useFlag('...')` |

A derived key is a slug of the name, unique among its siblings: a project key
within its organization, an environment key within its project. A name that
slugifies to nothing becomes `untitled`, and a taken slug gets `-2`, `-3`, and
so on. Nobody is asked to invent these two because nothing resolves them — no
URL, filter or SDK path reads either one, every row is addressed by UUID and
the SDK authenticates with the environment's `api_key`.

A derived key is never re-derived afterwards: rename an environment and its key
stays exactly as first derived. Both remain writable through `PATCH`, but only
a project's is editable from the dashboard (nav → rename, which offers name and
key). An environment can be created and deleted from the dashboard and nothing
else — if you need a different one, delete it and create it again, remembering
that its API key goes with it.

A flag's key is the exception and stays yours: deriving it would rename the
`useFlag('...')` calls in your code. It is fixed once created — the edit dialog
locks it.

## Consuming flags from your app

Install the package for your framework. Every one of them carries the same
evaluator, so a rule resolves identically whichever you use, and an adapter
re-exports the core — you install one package, not two.

| Package | For |
| --- | --- |
| [`@flagward/react`](https://www.npmjs.com/package/@flagward/react) | React 18+ |
| [`@flagward/vue`](https://www.npmjs.com/package/@flagward/vue) | Vue 3.5+ |
| [`@flagward/core`](https://www.npmjs.com/package/@flagward/core) | everything else: a plain script, a server, a framework with no adapter yet |

The API key is the environment's, from the dashboard. A key scopes the SDK to
one environment and nothing else.

### React

```bash
npm install @flagward/react
```

```tsx
import { FlagwardProvider, useFlag } from "@flagward/react";

function App() {
  return (
    <FlagwardProvider apiKey="your-environment-api-key" host="http://localhost:8000">
      <Checkout />
    </FlagwardProvider>
  );
}

function Checkout() {
  const { value, isLoading } = useFlag("new-checkout");

  // `value` is undefined until the first snapshot arrives, and stays
  // undefined for a key this environment does not have -- so decide what
  // an unknown flag means rather than letting undefined decide for you.
  if (isLoading) return <LegacyCheckout />;

  return value ? <NewCheckout /> : <LegacyCheckout />;
}
```

### Vue

```bash
npm install @flagward/vue
```

It installs on the application, so nothing has to be wrapped:

```ts
// main.ts
import { createApp } from "vue";
import { flagward } from "@flagward/vue";

createApp(App)
  .use(flagward({
    apiKey: "your-environment-api-key",
    host: "http://localhost:8000",
  }))
  .mount("#app");
```

```vue
<script setup lang="ts">
import { useFlag } from "@flagward/vue";

// Same caveat as above: undefined while loading, and for a key this
// environment does not have.
const { value, isLoading } = useFlag("new-checkout");
</script>

<template>
  <LegacyCheckout v-if="isLoading" />
  <NewCheckout v-else-if="value" />
  <LegacyCheckout v-else />
</template>
```

The context a rule is evaluated against can be a ref or a getter, at either
level, so the attributes you target on stay current as the user signs in or
changes plan:

```ts
const user = ref({ plan: "free" });

app.use(flagward({ apiKey, context: user }));   // application-wide
useFlag("beta", () => ({ plan: user.value.plan }));  // or for one call
```

### Without a framework

The client, the rule evaluator and the reporting live in `@flagward/core`,
which has no framework dependency. Use it directly in a plain script, on a
server, or in a framework that has no adapter yet:

```bash
npm install @flagward/core
```

```js
import { FlagwardClient } from "@flagward/core";

const client = new FlagwardClient({ apiKey: "your-environment-api-key" });
await client.init();

if (client.getFlag("new-checkout")) {
  // ...
}
```

This works on a server as well as in a browser. Where there is no
`EventSource` — server rendering, plain Node — live updates are reported as off
and the flags already read keep working, rather than the client failing to
start.

Source: [basb7/flagward-sdk-js](https://github.com/basb7/flagward-sdk-js) —
one repository holding the shared core and one thin adapter per framework.

### Two ways to evaluate, and why it matters

**Locally, which is what the JavaScript SDKs do.** They download the flags and
their rules once, evaluate in the process, and an SSE stream keeps the
snapshot fresh. Evaluation costs nothing, works offline, and the user's
context never leaves the client.

In a browser, the trade-off is that **the rules travel to the client**. Anyone
can open devtools and read that you target `plan == "enterprise"`. Do not put
anything secret in a targeting rule.

**Remotely, via `POST /api/v1/sdk/evaluate/`.** You send the context, the
server evaluates and answers. The rules stay on the server, at the cost of a
round trip per evaluation and of sending user context off the client.

This is also the only path that writes to `EvaluationLog`, so the
Monitoring page counts remote evaluations only. A dashboard reading zero does
not mean your flags are unused -- it means your clients are evaluating
locally.

## Project Structure

```
flagward/
├── config/              # Django settings, ASGI, URLs
├── core/                # Shared building blocks
│   ├── api/mixins.py    # QueryParamFilterMixin (query-param filtering)
│   └── management/commands/create_super_user.py
├── tenancy/             # Organizations, projects, roles and access control
│   ├── models.py        # Organization, Project, the three membership tables, Invitation
│   ├── capabilities.py  # The frozen capability catalogue and role → capability grants
│   ├── scoping.py       # Join-free "what can this user see" querysets
│   ├── permissions.py   # DRF permission classes + the tenant-scoped viewset mixin
│   ├── slugs.py         # Deriving Project.key / Environment.key from a name
│   └── api/             # Organization, project, membership and invitation endpoints
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
│   ├── src/app/dashboard/  # Overview, flags, environments, monitoring, members
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

All dashboard endpoints require the JWT cookie — a Django admin session is not
an API credential, and an SDK API key is refused here with a `403`.
Every list endpoint is paginated (`PAGE_SIZE = 20`).

Every read is scoped to what the caller's memberships reach, so a row in
another tenant is `404` rather than `403`: an id you cannot see must not
answer differently from one that does not exist.

### Auth

Tokens travel in httpOnly cookies, so the browser never handles them directly.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/register/` | Create a user |
| `POST` | `/api/v1/auth/login/` | Sets the auth cookies |
| `POST` | `/api/v1/auth/logout/` | Clears them |
| `POST` | `/api/v1/auth/refresh/` | Rotates the access token |
| `GET` | `/api/v1/auth/me/` | Current user, with its capabilities per organization |
| `GET` | `/api/v1/health/` | Liveness probe, no auth required |

Registration creates the user and nothing else — no organization is
provisioned for it (`authentication/views.py`). The first organization is
created explicitly, from the dashboard's empty state.

### Tenancy (organizations, projects, members)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` `POST` | `/api/v1/tenancy/organizations/` | Organizations; creating one makes you its `ADMIN` |
| `GET` `PATCH` `DELETE` | `/api/v1/tenancy/organizations/{id}/` | One organization |
| `GET` | `/api/v1/tenancy/organizations/{id}/deletion_impact/` | What a delete would remove, counted |
| `GET` `POST` | `/api/v1/tenancy/projects/` | Projects (`key` derived from `name`) |
| `GET` `PATCH` `DELETE` | `/api/v1/tenancy/projects/{id}/` | One project |
| `GET` | `/api/v1/tenancy/projects/{id}/deletion_impact/` | Same shape, one level down |
| `GET` | `/api/v1/tenancy/organization-memberships/` | Who else is in the organizations you can see |
| `PATCH` `DELETE` | `/api/v1/tenancy/organization-memberships/{id}/` | Change or revoke an organization role |
| `GET` `POST` | `/api/v1/tenancy/project-memberships/` | Per-project role grants |
| `PATCH` `DELETE` | `/api/v1/tenancy/project-memberships/{id}/` | Change or revoke one |
| `GET` `POST` | `/api/v1/tenancy/environment-memberships/` | Per-environment role grants |
| `PATCH` `DELETE` | `/api/v1/tenancy/environment-memberships/{id}/` | Change or revoke one |
| `GET` `POST` | `/api/v1/tenancy/invitations/` | Single-use invitation links |
| `POST` | `/api/v1/tenancy/invitations/{id}/revoke/` | Revoke one nobody has used |
| `GET` | `/api/v1/tenancy/invitations/{token}/preview/` | What you were invited to; no auth required |
| `POST` | `/api/v1/tenancy/invitations/{token}/accept/` | Join, with the role baked into the link |
| `POST` | `/api/v1/tenancy/effective-capabilities/preview/` | What proposed roles *would* grant; saves nothing |

`DELETE` on an organization or a project asks for `confirm_name`: the object's
exact current name, echoed back. An organization with other members is refused
outright — remove them first.

Organization membership rows are never created directly. An invitation link is
the only way in for anyone but the organization's founding `ADMIN`, and
removing an organization membership also revokes every project and environment
grant that member held inside it.

### Flag management (core_flags)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` `POST` | `/api/v1/environments/` | Environments (`key` derived from `name`, API key auto-generated) |
| `GET` `PATCH` `DELETE` | `/api/v1/environments/{id}/` | One environment |
| `POST` | `/api/v1/environments/{id}/rotate_api_key/` | Issue a fresh API key for it |
| `GET` `POST` | `/api/v1/flags/` | Feature flags |
| `GET` `PATCH` `DELETE` | `/api/v1/flags/{id}/` | One flag |
| `GET` `POST` | `/api/v1/rules/` | Strategy rules |
| `GET` `PATCH` `DELETE` | `/api/v1/rules/{id}/` | One rule |
| `GET` `POST` | `/api/v1/conditions/` | Conditions |
| `GET` `PATCH` `DELETE` | `/api/v1/conditions/{id}/` | One condition |

Filters: `/environments/?project=`, `/flags/?environment=&project=&is_enabled=&flag_type=`,
`/rules/?flag=`, `/conditions/?rule=`. A malformed filter value returns `400`,
never an empty page.

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

Each SDK registers under its own `sdk_type`, so one environment can hold a
`REACT` row and a `VUE` row at once. `SDKType` does not declare those two yet
and Django does not validate choices on save, so they are stored and returned
as sent — filter by the literal value. Declaring them is
[open work](https://github.com/basb7/flagward-sdk-js); nothing needs to change
in an SDK when it lands.

### Analytics

Aggregates for the dashboard. All four accept `?environment=<uuid>` or
`?project=<uuid>` to scope, and all four are bounded to the environments the
caller can read analytics on — an id outside them is a `404`.

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
# Get the API key from the dashboard (Environments → copy)

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
- **Some tenancy actions exist only in the API.** Rotating an environment's API
  key (`POST /environments/{id}/rotate_api_key/`), editing an environment, and
  changing someone's organization role
  (`PATCH /tenancy/organization-memberships/{id}/`) all work over HTTP but have
  no screen — today the dashboard changes an organization role by removing the
  member and inviting them again.
- **`test_admin_api.py` is a stub.** Its 25 tests are `pass` bodies with
  `# TODO: Implement admin authentication`, so the environment/flag/rule/condition
  CRUD has no automated coverage yet.

## Models

| Model | Purpose |
|-------|---------|
| **Organization** | Top of the tenancy hierarchy; carries the plan and its seat ceiling |
| **Project** | Groups environments inside one organization; `key` unique per organization |
| **OrganizationMembership** | A user's role in an organization: `ADMIN` or `USER` |
| **ProjectMembership** | A user's role in one project: `ADMIN`, `EDITOR`, `OPERATOR`, `VIEWER` |
| **EnvironmentMembership** | The same four roles, on one environment |
| **Invitation** | Single-use link into an organization; only the token's SHA-256 is stored |
| **Environment** | Deployment target (production, staging, dev) inside a project; `key` unique per project |
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
