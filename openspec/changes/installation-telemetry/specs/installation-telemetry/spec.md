# Installation Telemetry Specification

## Purpose

Let Flagward maintainers learn how self-hosted installations are used — versions, runtime, feature adoption, SDK adoption and evaluation volume — through an anonymous, aggregate-only, opt-out daily heartbeat.

## ADDED Requirements

### Requirement: Opt-out Control

The system MUST send telemetry by default and MUST stop all telemetry activity when the operator disables it with `FLAGWARD_TELEMETRY`.

Resolution of the effective setting:

| `FLAGWARD_TELEMETRY` | `CI` | Effective |
|----------------------|------|-----------|
| unset or empty | unset/falsy | enabled |
| unset or empty | truthy | disabled |
| `true` (any truthy value) | any | enabled |
| `false` (any falsy value) | any | disabled |

`DEBUG` does not affect whether telemetry is enabled; it only determines the reported `mode`.

#### Scenario: Default production install sends telemetry

- GIVEN `FLAGWARD_TELEMETRY` is not set
- AND `DEBUG` is False
- WHEN the server starts
- THEN telemetry is enabled

#### Scenario: Kill switch produces zero outbound activity

- GIVEN `FLAGWARD_TELEMETRY=false`
- WHEN the server starts and runs for more than 24 hours
- THEN no HTTP request is made to the telemetry URL
- AND no `InstallationIdentity` row is created
- AND no telemetry thread is started

#### Scenario: Development install sends telemetry too

- GIVEN `DEBUG=True` and `FLAGWARD_TELEMETRY` is not set
- AND `CI` is not set
- WHEN the server starts
- THEN telemetry is enabled

#### Scenario: CI stays silent by default

- GIVEN `CI=true` and `FLAGWARD_TELEMETRY` is not set
- WHEN the server starts
- THEN telemetry is disabled

#### Scenario: CI can opt in explicitly

- GIVEN `CI=true` and `FLAGWARD_TELEMETRY=true`
- WHEN the server starts
- THEN telemetry is enabled

#### Scenario: CI flag reaches the dev container

- GIVEN the GitHub Actions runner sets `CI=true`
- WHEN `docker compose -f compose.dev.yml up` starts the backend
- THEN the backend container sees `CI=true` and telemetry is disabled

### Requirement: Anonymous Installation Identity

The system MUST identify an installation with a random UUID v4 persisted in the database and MUST NOT derive it from `SECRET_KEY`, hostname, domain, IP, or any user data.

#### Scenario: First run creates the identity

- GIVEN telemetry is enabled and no `InstallationIdentity` exists
- WHEN the first heartbeat is attempted
- THEN exactly one `InstallationIdentity` is created with a random UUID v4 and `first_seen_at` set to now

#### Scenario: Identity is stable across restarts

- GIVEN an existing `InstallationIdentity`
- WHEN the server restarts
- THEN the same `installation_id` is used

### Requirement: Payload Contract

The system MUST send a JSON payload matching `schema_version: 1` exactly, containing only the fields defined in the proposal, and MUST NOT include personal or customer data.

Forbidden in any field: emails, usernames, organization/project/environment names or slugs, flag keys or names, variant names, condition values, API keys, hostnames, domains, IPs, `SECRET_KEY`.

#### Scenario: Payload contains only approved fields

- GIVEN an installation with organizations, flags, rules and SDK registrations
- WHEN the payload is built
- THEN its set of keys (recursively) equals the schema v1 key set

#### Scenario: Payload contains no customer strings

- GIVEN a flag keyed `secret-launch`, an organization named `Acme`, and a user `ana@acme.com`
- WHEN the payload is built
- THEN the serialized payload contains none of those strings

#### Scenario: Unknown SDK type is anonymized

- GIVEN an `SDKRegistration` with `sdk_type="my-internal-thing"`
- WHEN the payload is built
- THEN that SDK is reported with `type="other"`

#### Scenario: Non-semver SDK version is anonymized

- GIVEN an `SDKRegistration` with `version="build-acme-42"`
- WHEN the payload is built
- THEN that SDK is reported with `version="unknown"`

#### Scenario: Only recently active SDKs are counted

- GIVEN one SDK registration seen 2 days ago and one seen 10 days ago, same type and version
- WHEN the payload is built
- THEN that type/version entry reports `active_7d=1`

#### Scenario: Evaluation volume is bucketed

- GIVEN 4,321 evaluation logs in the last 24 hours
- WHEN the payload is built
- THEN `evaluations_24h_bucket` is `"1k-10k"`

#### Scenario: Application version is reported

- GIVEN `config/version.py` declares `__version__ = "0.6.0"` and `FLAGWARD_VERSION` is not set
- WHEN the payload is built
- THEN `flagward_version` is `"0.6.0"`

#### Scenario: Environment override wins

- GIVEN `__version__ = "0.6.0"` and `FLAGWARD_VERSION=0.6.1-rc1`
- WHEN the payload is built
- THEN `flagward_version` is `"0.6.1-rc1"`

#### Scenario: Missing version does not break the payload

- GIVEN `FLAGWARD_VERSION` is not set and `__version__` is empty or not semver
- WHEN the payload is built
- THEN `flagward_version` is `"unknown"`

### Requirement: Installation Mode

The system MUST report whether the installation runs in production or development mode and which server runs it.

#### Scenario: Production install

- GIVEN `DEBUG=False` and the app served through `config/asgi.py` by gunicorn/uvicorn
- WHEN the payload is built
- THEN `mode` is `"production"` and `server` is `"asgi"`

#### Scenario: Development install

- GIVEN `DEBUG=True` and the app served by `manage.py runserver`
- WHEN the payload is built
- THEN `mode` is `"development"` and `server` is `"runserver"`

#### Scenario: Production mode on a dev server is still distinguishable

- GIVEN `DEBUG=False` and the app served by `manage.py runserver`
- WHEN the payload is built
- THEN `mode` is `"production"` and `server` is `"runserver"`

#### Scenario: Preview outside a server process

- GIVEN the operator runs `manage.py telemetry --show`
- WHEN the payload is built
- THEN `server` is `"unknown"` and `mode` follows `DEBUG`

### Requirement: Daily Heartbeat Without Duplicates

The system MUST send at most one heartbeat per installation per 24 hours, regardless of the number of workers or replicas sharing the database.

#### Scenario: One heartbeat across concurrent workers

- GIVEN 4 workers start at the same time and the last heartbeat was more than 24 hours ago
- WHEN all of them attempt to send
- THEN exactly one of them claims the slot and sends

#### Scenario: No heartbeat inside the 24-hour window

- GIVEN the last heartbeat was sent 3 hours ago
- WHEN a worker attempts to send
- THEN nothing is sent

#### Scenario: Failed send does not retry within the window

- GIVEN a worker claimed the slot and the HTTP request failed
- WHEN another attempt happens within 24 hours
- THEN nothing is sent

### Requirement: Failure Isolation

Telemetry MUST NOT raise into, block, or slow down request handling or startup.

#### Scenario: Collector unreachable

- GIVEN the telemetry URL is unreachable or times out
- WHEN a heartbeat is sent
- THEN the error is logged at `DEBUG` level only
- AND the application keeps serving requests normally

#### Scenario: Database not migrated yet

- GIVEN the telemetry table does not exist yet
- WHEN a heartbeat is attempted
- THEN the attempt is skipped silently and retried on the next check

### Requirement: Transparency

The system MUST let operators see exactly what is sent.

#### Scenario: Startup notice

- GIVEN telemetry is enabled
- WHEN the server starts
- THEN one `INFO` log line states that anonymous telemetry is on and how to disable it (`FLAGWARD_TELEMETRY=false`)

#### Scenario: Preview command

- GIVEN any telemetry setting
- WHEN the operator runs `manage.py telemetry --show`
- THEN the exact payload JSON is printed
- AND no HTTP request is made

#### Scenario: Forced send for validation

- GIVEN telemetry is enabled
- WHEN the operator runs `manage.py telemetry --send`
- THEN the payload is sent immediately, ignoring the 24-hour window
- AND the command prints the HTTP status or the error

#### Scenario: Forced send respects the kill switch

- GIVEN telemetry is disabled
- WHEN the operator runs `manage.py telemetry --send`
- THEN nothing is sent and the command explains telemetry is disabled
