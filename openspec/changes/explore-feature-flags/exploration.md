# Exploration: Feature Flags SaaS MVP

**Date**: 2026-08-26
**Status**: Complete
**Phase**: sdd-explore

## Current State

Empty project at the project root. Only has .venv with Python 3.14 and Django installed. No application code exists yet.

## Affected Areas (Future Modules)

### Core Applications

- `core_flags/` — Core feature flag engine (Community edition)
  - Models: Environment, FeatureFlag, StrategyRule, Condition, FlagOverride
  - Services: Flag evaluation engine, rule resolver
  - API: SDK endpoints, admin CRUD
  - SSE: Real-time push via Redis Streams

- `sdk/` — SDK-specific logic (NEW recommendation)
  - Models: SDKRegistration, EvaluationLog
  - API: SDK handshake, evaluation endpoint, SSE connection
  - Services: SDK key management, usage tracking

- `enterprise_billing/` — SaaS layer (Enterprise edition)
  - Models: Organization, OrganizationEnvironment, Membership
  - Services: Stripe integration, RBAC
  - API: Org management, billing webhooks

### Infrastructure

- `config/` — Django settings, ASGI config, Redis config
- `requirements/` — Dependencies (django-ninja, redis, etc.)
- `tests/` — Test suite structure

## Approaches

### Approach 1: Monolithic Django App (NOT recommended)

- **Description**: Single Django app with all models in one place
- **Pros**: Simpler initially, less configuration
- **Cons**: Hard to separate Community/Enterprise later, tight coupling, testing nightmare
- **Effort**: Low initially, Very High later

### Approach 2: Modular Django Apps (RECOMMENDED)

- **Description**: Separate apps for core_flags, sdk, enterprise_billing
- **Pros**: Clean separation of concerns, easy to defer Enterprise features, independent testing, clear boundaries
- **Cons**: More initial setup, need to manage inter-app dependencies
- **Effort**: Medium initially, Low later

### Approach 3: Full Microservices (Overkill)

- **Description**: Separate services for each module
- **Pros**: Independent deployment, scaling
- **Cons**: Massive complexity for MVP, network overhead, debugging harder
- **Effort**: Very High

## Recommendation

**Approach 2: Modular Django Apps** with the following structure:

```
flagward/
├── config/              # Django settings, ASGI, URLs
├── core_flags/          # Core flag engine (Community)
│   ├── models.py        # Environment, FeatureFlag, StrategyRule, Condition, FlagOverride
│   ├── services.py      # Evaluation engine, rule resolver
│   ├── api/             # DRF/Ninja serializers and views
│   └── sse.py           # SSE streaming via Redis Streams
├── sdk/                 # SDK-specific logic
│   ├── models.py        # SDKRegistration, EvaluationLog
│   ├── api/             # SDK endpoints
│   └── services.py      # Key management, usage tracking
├── enterprise_billing/  # SaaS layer (Enterprise, deferred)
│   ├── models.py        # Organization, Membership
│   └── services.py      # Stripe, RBAC
├── tests/               # Test suite
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── requirements/        # Dependencies
```

## Key Technical Decisions

1. **Django Ninja over DRF**: Better async support for SSE, Pydantic validation, cleaner code
2. **Redis Streams over Pub/Sub**: Durable messaging, consumer groups, replay capability
3. **UUID Primary Keys**: Distributed-friendly, SDK-safe
4. **Local Evaluation**: SDKs download rules, evaluate locally (< 1ms), backend pushes updates via SSE

## Testing Strategy

| Layer | Scope | Tools | Coverage Target |
|-------|-------|-------|-----------------|
| Unit | Models, evaluation engine | pytest, factory_boy | 90%+ |
| Integration | API endpoints, Redis Streams | httpx, pytest-asyncio | 80%+ |
| E2E | Full SDK flow | playwright or httpx | Critical paths |
| SSE | Connection, events, reconnect | pytest-asyncio, mock Redis | 100% of SSE logic |

## MVP Scope

### IN SCOPE (First Delivery)

- Core models (Environment, FeatureFlag, StrategyRule, Condition)
- Flag evaluation engine (local evaluation logic)
- SDK API endpoints (get flags, evaluate)
- SSE streaming (basic connection, initial snapshot, updates)
- Admin API (CRUD for flags)
- Basic tests (unit + integration)

### DEFERRED

- Enterprise billing (Organization, Membership, Stripe)
- SDK language-specific SDKs (Python, JavaScript, Go)
- Advanced features (multivariate flags, percentage rollouts)
- Webhooks, analytics, audit logs
- Rate limiting, quotas

## Risks

1. **Redis Streams complexity**: Consumer groups and acknowledgment patterns add complexity. Mitigation: Start with simple consumer, add groups later.
2. **SSE connection management**: Handling reconnections, multiple instances. Mitigation: Use Redis Streams consumer groups for horizontal scaling.
3. **Flag evaluation edge cases**: Complex rule combinations, operator precedence. Mitigation: Extensive unit tests for evaluation engine.
4. **SDK versioning**: Breaking changes in flag format. Mitigation: Version the API response format from day one.

## Ready for Proposal

**Yes** — The exploration is complete. The modular architecture is well-defined, testing strategy is clear, and MVP scope is bounded. Ready to proceed to sdd-proposal.
