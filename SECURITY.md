# Security Policy

## Supported versions

Flagward is pre-1.0. Security fixes land on `main` and are released from there.
Please make sure you can reproduce an issue against the latest `main` before
reporting it.

| Version | Supported |
|---------|-----------|
| `main`  | ✅ |
| tagged pre-1.0 releases | ❌ |

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

Additional notes:

- Auth cookies are marked `Secure` automatically whenever `DEBUG` is `False`,
  so production must be served over HTTPS or login will not work.
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
