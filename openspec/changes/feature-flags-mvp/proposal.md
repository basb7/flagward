# Proposal: Feature Flags SaaS MVP

**Date**: 2026-08-26
**Status**: Complete
**Phase**: sdd-proposal
**Change**: feature-flags-mvp

## Intent

Build a production-ready Feature Flags platform that enables real-time feature toggling with local SDK evaluation. The system must support both Community (open source) and Enterprise (SaaS) editions from day one through modular architecture.

## Scope

### In Scope

- Core flag engine: Environment, FeatureFlag, StrategyRule, Condition models
- Flag evaluation engine: Local evaluation logic for SDKs
- SDK API endpoints: Get flags, evaluate context, SSE connection
- SSE streaming: Real-time updates via Redis Streams
- Admin API: CRUD operations for flags
- Unit + integration tests

### Out of Scope

- Enterprise billing (Organization, Membership, Stripe) — deferred
- Language-specific SDKs (Python, JavaScript, Go) — deferred
- Multivariate flags, percentage rollouts — deferred
- Webhooks, analytics, audit logs — deferred
- Rate limiting, quotas — deferred

## Capabilities

### New Capabilities

- `flag-management`: CRUD operations for environments, feature flags, rules, and conditions
- `flag-evaluation`: Local evaluation engine that processes flag rules and returns boolean/multivariate results
- `sdk-integration`: SDK endpoints for flag retrieval, context evaluation, and SSE real-time updates
- `sse-streaming`: Server-Sent Events infrastructure for pushing flag updates to connected SDKs

### Modified Capabilities

None — this is a greenfield project.

## Approach

**Modular Django Apps + DRF + Redis Streams**

1. **Core Flags App**: Models with UUIDs, DRF serializers, evaluation service
2. **SDK App**: SDK-specific endpoints, key management, evaluation logging
3. **Infrastructure**: Redis Streams for durable messaging, Django async for SSE
4. **Testing**: pytest with factory_boy, httpx for API tests, pytest-asyncio for SSE

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `core_flags/` | New | Core models, evaluation engine, API endpoints |
| `sdk/` | New | SDK endpoints, key management, usage tracking |
| `config/` | New | Django settings, ASGI config, Redis config |
| `tests/` | New | Unit, integration, E2E test structure |
| `requirements/` | New | Dependencies (django, drf, redis, etc.) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Redis Streams complexity | Medium | Start simple, add consumer groups later |
| SSE reconnection handling | Medium | Use proven SSE patterns, test reconnection |
| Flag evaluation edge cases | Low | Extensive unit tests for evaluation engine |
| SDK versioning | Low | Version API response from day one |

## Rollback Plan

1. Git revert to last known good commit
2. Redis: Flush stream data if corrupted
3. Database: Reverse migrations in reverse order
4. No external dependencies to unwind

## Dependencies

- Python 3.14 (already installed)
- Django (already installed)
- Redis server (must be installed/configured)
- djangorestframework
- django-redis
- pytest, pytest-django, pytest-asyncio

## Success Criteria

- [ ] All core models created with UUIDs and proper relationships
- [ ] Flag evaluation engine returns correct results for all operator types
- [ ] SDK can fetch flags and receive SSE updates
- [ ] Admin can CRUD flags via API
- [ ] Unit test coverage > 90% for evaluation engine
- [ ] Integration test coverage > 80% for API endpoints
- [ ] SSE streaming works with < 50ms latency
