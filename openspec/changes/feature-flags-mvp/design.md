# Design: Feature Flags SaaS MVP

**Date**: 2026-08-26
**Status**: Complete
**Phase**: sdd-design
**Change**: feature-flags-mvp

## Technical Approach

Modular Django apps with DRF for REST API and Django async for SSE. Redis Streams for durable messaging. Local evaluation pattern where SDKs download rules and evaluate locally.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| API Framework | DRF | Django Ninja, FastAPI | User expertise, mature ecosystem, good async support via Django views |
| Messaging | Redis Streams | Redis Pub/Sub, RabbitMQ | Durable, consumer groups, replay capability, < 50ms latency |
| Evaluation | Local in SDK | Server-side evaluation | Reduces backend load, < 1ms latency, offline support |
| Primary Keys | UUID v4 | Auto-increment int | Distributed-friendly, SDK-safe, no sequential leaking |
| Database | PostgreSQL | MySQL, SQLite | JSONField support, robust, production-ready |
| SSE Transport | Django async views | Channels, third-party | Native Django, no extra dependencies, simple implementation |

## Data Flow

### Flag Update Flow

```
Admin API → Django View → Database Save → Redis Stream Publish → SSE View → SDK Client
```

### SDK Evaluation Flow

```
SDK → API Gateway → Auth Check → Flag Service → Evaluation Engine → Response
```

### SSE Connection Flow

```
SDK → SSE Endpoint → Redis Subscribe → Initial Snapshot → Event Stream
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `config/settings.py` | Create | Django settings, Redis config, installed apps |
| `config/asgi.py` | Create | ASGI application for async support |
| `config/urls.py` | Create | URL routing for API and SDK endpoints |
| `core_flags/__init__.py` | Create | Core flags app initialization |
| `core_flags/models.py` | Create | Environment, FeatureFlag, StrategyRule, Condition, FlagOverride |
| `core_flags/services.py` | Create | Flag evaluation engine, rule resolver |
| `core_flags/api/__init__.py` | Create | DRF serializers and viewsets |
| `core_flags/api/serializers.py` | Create | Model serializers for CRUD |
| `core_flags/api/views.py` | Create | Admin API endpoints |
| `sdk/__init__.py` | Create | SDK app initialization |
| `sdk/models.py` | Create | SDKRegistration, EvaluationLog |
| `sdk/api/__init__.py` | Create | SDK-specific endpoints |
| `sdk/api/views.py` | Create | SDK auth, flags, evaluate, stream |
| `sdk/services.py` | Create | Key management, usage tracking |
| `tests/__init__.py` | Create | Test suite initialization |
| `tests/unit/__init__.py` | Create | Unit tests |
| `tests/integration/__init__.py` | Create | Integration tests |
| `requirements/base.txt` | Create | Core dependencies |
| `requirements/dev.txt` | Create | Development dependencies |
| `manage.py` | Create | Django management script |

## Interfaces / Contracts

### SDK Flag Response

```json
{
  "environment": "sk_test_123",
  "flags": [
    {
      "key": "new-dashboard",
      "is_enabled": true,
      "flag_type": "BOOLEAN",
      "rules": [
        {
          "priority": 0,
          "operator_logic": "AND",
          "conditions": [
            {
              "attribute": "country",
              "operator": "EQUALS",
              "value": "US"
            }
          ]
        }
      ]
    }
  ]
}
```

### SSE Event Format

```
event: flag_update
id: 12345
data: {"flag_key": "new-dashboard", "is_enabled": true, ...}
```

### Evaluation Request

```json
{
  "context": {
    "country": "US",
    "plan": "premium",
    "age": 25
  }
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Evaluation engine, operators, rule logic | pytest with factory_boy, 90%+ coverage |
| Integration | API endpoints, Redis Streams, SSE | httpx + pytest-asyncio, 80%+ coverage |
| E2E | Full SDK flow, real-time updates | Playwright or httpx, critical paths |
| SSE | Connection, events, reconnect | pytest-asyncio, mock Redis |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Migration / Rollout

**Phase 1: Core Engine**
- Deploy core_flags app with models and evaluation engine
- Run migrations to create tables
- Seed test data

**Phase 2: SDK Integration**
- Deploy SDK endpoints
- Test with Python SDK
- Monitor evaluation logs

**Phase 3: SSE Streaming**
- Deploy Redis Streams integration
- Test real-time updates
- Monitor latency metrics

**Phase 4: Production**
- Deploy to production environment
- Enable monitoring and alerting
- Document SDK integration guide

## Open Questions

- [ ] Redis deployment strategy: single instance vs. cluster?
- [ ] Authentication mechanism for admin API: JWT vs. session vs. API key?
- [ ] Rate limiting strategy for SDK endpoints?
- [ ] Monitoring and alerting stack: Prometheus + Grafana vs. alternatives?
- [ ] CI/CD pipeline: GitHub Actions vs. GitLab CI vs. other?
