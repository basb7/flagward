# Security Policy

## Supported versions

Flagward is pre-1.0 and self-hosted: you deploy it from source, so what you
are running is a commit, not a download. Two things are supported — the
latest tagged release, and `main`.

| Version | Supported |
|---------|-----------|
| latest tagged release | ✅ |
| `main` | ✅ |
| earlier releases | ❌ |

Security fixes land on `main` first and are tagged from there. Please
reproduce an issue against `main` or the latest release before reporting it,
and say which one you are on — with no version to name, a report cannot be
placed in time.

Flagward and the JavaScript SDKs (`@flagward/core`, `@flagward/react`,
`@flagward/vue`) are
versioned **independently**, and so are the SDKs from each other. Matching
version numbers are a coincidence, not a pairing — do not read one as
requiring the other.

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Report it privately through GitHub Security Advisories:

👉 https://github.com/basb7/flagward/security/advisories/new

Only the repository maintainers can see reports filed this way.

Please include:

- A description of the vulnerability and its impact
- Steps to reproduce, or a proof of concept
- The affected version or commit
- Any suggested mitigation you are aware of

You can expect an initial response within 7 days. If the report is confirmed we
will agree a disclosure timeline with you and credit you in the advisory unless
you prefer to stay anonymous.

## Tenant isolation

Flagward is multi-tenant. Every object it stores hangs off one ownership
chain, and every dashboard endpoint is scoped to it:

```
Organization → Project → Environment → FeatureFlag → StrategyRule → Condition
```

This is the guarantee a report can be measured against:

- **Nothing is visible without an explicit membership.** Access comes only from
  `OrganizationMembership`, `ProjectMembership` and `EnvironmentMembership`
  rows, unioned; there is no ambient or inherited-by-default access. A plain
  organization member (role `USER`) holding no project or environment grant
  sees the organization's name and nothing more — the project, environment and
  flag collections all come back empty.
- **A resource in another tenant answers 404, not 403.** Objects outside the
  caller's scope are filtered out before the view sees them, so fetching one by
  UUID is indistinguishable from fetching one that does not exist. A 403 would
  confirm the UUID exists. 403 is reserved for a resource the caller can see
  but lacks the capability to change; 400 for a write aimed at a parent object
  in another tenant.
- **Django's `is_superuser` grants nothing through the API.** Superadmin work
  happens through `/admin/`. A superuser with no membership is scoped exactly
  like any other user, and sees no tenant data.
- **`Environment.api_key` is the SDK's only credential.** It is sent as
  `X-API-Key`, and it carries no organization, project or user context — which
  is why it is globally unique rather than unique per project: the key alone
  has to resolve to exactly one environment. It grants access to that one
  environment's flag data and nothing above or beside it, and it is not a
  dashboard credential.

A cross-tenant read that returns data, a 403 where the model above says 404, or
an API key that reaches a second environment is a vulnerability worth
reporting.

## Deployment hardening

Flagward ships with development defaults so it runs out of the box. Those
defaults are **not** safe for a deployment. Before exposing an instance:

| Setting | Development default | Required in production |
|---------|--------------------|------------------------|
| `SECRET_KEY` | a known placeholder | a unique random value, never committed |
| `DEBUG` | `True` | `False` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | your real hostnames |
| `CSRF_TRUSTED_ORIGINS` | localhost origins | your real origins |
| `CORS_ALLOWED_ORIGINS` | localhost origins | your real origins |
| `DB_PASSWORD` | `postgres` | a strong, unique password |
| `DJANGO_SUPERUSER_PASSWORD` | `admin` | a strong, unique password, or omit and create the user manually |
| `FRONTEND_BASE_URL` | `http://localhost:3000` | the dashboard's real public URL |
| `EMAIL_HOST` | unset | your SMTP host, if password reset is to work at all |

Additional notes:

- Auth cookies are marked `Secure` automatically whenever `DEBUG` is `False`,
  so production must be served over HTTPS or login will not work.
- A password-reset token is a bearer credential, so an unconfigured production
  instance discards the message rather than printing it. With no `EMAIL_HOST`
  and `DEBUG` off, Flagward selects Django's **dummy** email backend, not the
  console one: the console backend would write the token to stdout, which
  production routinely ships to log aggregators, and logging a bearer
  credential where it does not need to be is worse than not delivering it.
  Setting `EMAIL_HOST` switches to real SMTP; `DEBUG` on with no SMTP falls
  back to the console backend, which is why that combination belongs on a
  developer's machine only.
- The reset link is built from `FRONTEND_BASE_URL` (as is the invitation link),
  so it must point at the real dashboard. Whether the reset flow is usable at
  all is reported to the frontend through the unauthenticated
  `GET /api/v1/auth/config/`, so a deployment with no mail server offers no
  "forgot password" link rather than silently swallowing the request.
- Environment API keys are generated per environment and grant read access to
  that environment's flags. Rotate them if one leaks.
- `.env` is git-ignored. Keep it that way — only `.env.example`, which contains
  placeholders, belongs in the repository.

## Scope

In scope: the Django backend, the SDK API, the SSE stream, the JWT cookie
authentication, and the dashboard.

Out of scope: vulnerabilities that require an already-compromised host,
issues that only affect the documented development defaults listed above when
used locally, and denial of service through unbounded self-inflicted load.
