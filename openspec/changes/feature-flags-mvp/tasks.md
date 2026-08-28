# Tasks: Feature Flags SaaS MVP

**Date**: 2026-08-26
**Status**: Complete
**Phase**: sdd-tasks
**Change**: feature-flags-mvp

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 2500-3500 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: Foundation → PR 2: Core Engine → PR 3: SDK API → PR 4: SSE Streaming → PR 5: Tests |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Base Branch | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|-------------|----------------------|-----------------|-------------------|
| 1 | Foundation: config, models, migrations | PR 1 | feature/flags-mvp | `pytest tests/unit/test_models.py` | Django test runner | config/, core_flags/models.py |
| 2 | Core evaluation engine | PR 2 | PR 1 branch | `pytest tests/unit/test_evaluation.py` | Unit tests | core_flags/services.py |
| 3 | SDK API endpoints | PR 3 | PR 2 branch | `pytest tests/integration/test_sdk_api.py` | httpx + test client | sdk/api/views.py |
| 4 | SSE streaming | PR 4 | PR 3 branch | `pytest tests/integration/test_sse.py` | pytest-asyncio | sdk/api/views.py (stream) |
| 5 | Integration tests + cleanup | PR 5 | PR 4 branch | `pytest tests/` | Full test suite | tests/ |

## Phase 1: Foundation / Infrastructure

- [ ] 1.1 Create `requirements/base.txt` with django, djangorestframework, django-redis, redis, psycopg2-binary
- [ ] 1.2 Create `requirements/dev.txt` with pytest, pytest-django, pytest-asyncio, factory_boy, httpx, coverage
- [ ] 1.3 Create `manage.py` with Django management script
- [ ] 1.4 Create `config/__init__.py` (empty)
- [ ] 1.5 Create `config/settings.py` with Django settings, Redis config, installed apps (core_flags, sdk, rest_framework)
- [ ] 1.6 Create `config/asgi.py` with ASGI application for async support
- [ ] 1.7 Create `config/urls.py` with URL routing for API and SDK endpoints
- [ ] 1.8 Create `core_flags/__init__.py` (empty)
- [ ] 1.9 Create `core_flags/models.py` with Environment, FeatureFlag, StrategyRule, Condition, FlagOverride models (UUIDs, relationships, enums)
- [ ] 1.10 Run `python manage.py makemigrations core_flags` to generate migrations
- [ ] 1.11 Run `python manage.py migrate` to create database tables

## Phase 2: Core Implementation

- [ ] 2.1 Create `core_flags/services.py` with FlagEvaluationService class
- [ ] 2.2 Implement `evaluate_flag(context)` method with boolean evaluation logic
- [ ] 2.3 Implement `evaluate_rules(rules, context)` with AND/OR operator logic
- [ ] 2.4 Implement `evaluate_condition(condition, context)` with all 6 operators (EQUALS, NOT_EQUALS, GREATER_THAN, LESS_THAN, IN_LIST, CONTAINS)
- [ ] 2.5 Implement `evaluate_multivariate(flag, context)` for multivariate flag support
- [ ] 2.6 Create `core_flags/api/__init__.py` (empty)
- [ ] 2.7 Create `core_flags/api/serializers.py` with ModelSerializer classes for all models
- [ ] 2.8 Create `core_flags/api/views.py` with ViewSet classes for admin CRUD operations
- [ ] 2.9 Register core_flags API routes in `config/urls.py`

## Phase 3: SDK Integration

- [ ] 3.1 Create `sdk/__init__.py` (empty)
- [ ] 3.2 Create `sdk/models.py` with SDKRegistration and EvaluationLog models
- [ ] 3.3 Create `sdk/services.py` with SDKKeyManager class for key validation
- [ ] 3.4 Create `sdk/api/__init__.py` (empty)
- [ ] 3.5 Create `sdk/api/views.py` with SDK auth middleware (X-API-Key header validation)
- [ ] 3.6 Implement `GET /api/v1/sdk/flags/` endpoint for flag retrieval
- [ ] 3.7 Implement `POST /api/v1/sdk/evaluate/` endpoint for context evaluation
- [ ] 3.8 Implement `POST /api/v1/sdk/register/` endpoint for SDK registration
- [ ] 3.9 Register SDK API routes in `config/urls.py`
- [ ] 3.10 Implement EvaluationLog creation in evaluation flow

## Phase 4: SSE Streaming

- [ ] 4.1 Create Redis Streams connection utility in `sdk/services.py`
- [ ] 4.2 Implement `GET /api/v1/sdk/stream/` async view for SSE connection
- [ ] 4.3 Implement initial snapshot sending on SSE connection
- [ ] 4.4 Implement Redis Stream subscription for flag updates
- [ ] 4.5 Implement SSE event formatting (event, id, data)
- [ ] 4.6 Implement reconnection with Last-Event-ID header
- [ ] 4.7 Implement Redis Stream publish on flag save (signal or override)
- [ ] 4.8 Add keepalive mechanism (30-second interval)

## Phase 5: Testing / Verification

- [ ] 5.1 Create `tests/__init__.py` (empty)
- [ ] 5.2 Create `tests/unit/__init__.py` (empty)
- [ ] 5.3 Create `tests/unit/test_models.py` with model tests (UUID generation, relationships, constraints)
- [ ] 5.4 Create `tests/unit/test_evaluation.py` with evaluation engine tests (all operators, AND/OR logic, multivariate)
- [ ] 5.5 Create `tests/integration/__init__.py` (empty)
- [ ] 5.6 Create `tests/integration/test_sdk_api.py` with SDK endpoint tests (auth, flags, evaluate)
- [ ] 5.7 Create `tests/integration/test_sse.py` with SSE tests (connection, events, reconnection)
- [ ] 5.8 Create `tests/integration/test_admin_api.py` with admin CRUD tests
- [ ] 5.9 Run full test suite and verify coverage > 80%
- [ ] 5.10 Fix any failing tests

## Phase 6: Cleanup / Documentation

- [ ] 6.1 Add docstrings to all public methods
- [ ] 6.2 Create README.md with setup instructions
- [ ] 6.3 Create .gitignore for Python/Django
- [ ] 6.4 Verify all imports are clean (no unused imports)
- [ ] 6.5 Run linter (ruff check) and fix any issues
