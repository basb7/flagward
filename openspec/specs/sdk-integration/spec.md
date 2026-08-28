# SDK Integration Specification

**Date**: 2026-08-26
**Capability**: sdk-integration
**Status**: Active
**Promoted from**: changes/feature-flags-mvp (2026-08-28)

## Purpose

SDK endpoints for flag retrieval, context evaluation, and SSE real-time updates. This is the interface that SDKs use to interact with the feature flag system.

## Requirements

### Requirement: SDK Authentication

The system MUST authenticate SDKs using API keys.

#### Scenario: Valid API key authentication

- GIVEN an environment with api_key="sk_test_123"
- WHEN SDK sends request with header X-API-Key: sk_test_123
- THEN system authenticates the request
- AND grants access to that environment's flags

#### Scenario: Invalid API key rejection

- GIVEN an environment with api_key="sk_test_123"
- WHEN SDK sends request with header X-API-Key: sk_wrong
- THEN system returns 401 Unauthorized
- AND logs the failed authentication attempt

#### Scenario: Missing API key rejection

- GIVEN any environment exists
- WHEN SDK sends request without X-API-Key header
- THEN system returns 401 Unauthorized

### Requirement: Flag Retrieval

The system MUST provide SDK endpoint to fetch all flags for an environment.

#### Scenario: Get flags for environment

- GIVEN an environment with 3 flags (2 enabled, 1 disabled)
- WHEN SDK sends GET /api/v1/sdk/flags/
- THEN system returns JSON with all flags
- AND response includes flag key, is_enabled, flag_type, rules, conditions
- AND response is optimized for local evaluation

#### Scenario: Empty environment returns empty list

- GIVEN an environment with no flags
- WHEN SDK sends GET /api/v1/sdk/flags/
- THEN system returns empty array

#### Scenario: Response format for local evaluation

- GIVEN a flag with rules and conditions
- WHEN SDK fetches flags
- THEN response includes complete rule tree
- AND conditions include attribute, operator, value
- AND SDK can evaluate locally without additional requests

### Requirement: Context Evaluation

The system MUST provide SDK endpoint to evaluate flags with context.

#### Scenario: Evaluate single flag

- GIVEN a flag with is_enabled=True and matching rules
- WHEN SDK sends POST /api/v1/sdk/evaluate/ with flag_key and context
- THEN system returns {flag_key: "result", value: true}

#### Scenario: Evaluate multiple flags

- GIVEN 5 flags with varying states
- WHEN SDK sends POST /api/v1/sdk/evaluate/ with context and no flag_key
- THEN system returns results for all flags
- AND response is a map of flag_key to result

#### Scenario: Missing flag returns null

- GIVEN no flag with key="nonexistent"
- WHEN SDK evaluates flag_key="nonexistent"
- THEN system returns {flag_key: "nonexistent", value: null}

### Requirement: SSE Connection

The system MUST provide SSE endpoint for real-time updates.

#### Scenario: Connect to SSE stream

- GIVEN a valid API key
- WHEN SDK sends GET /api/v1/sdk/stream/
- THEN system establishes SSE connection
- AND sends initial snapshot of all flags

#### Scenario: Receive flag update

- GIVEN SDK is connected to SSE stream
- WHEN admin updates a flag via API
- THEN SDK receives SSE event within 50ms
- AND event contains updated flag payload

#### Scenario: Reconnection handling

- GIVEN SDK was connected but connection dropped
- WHEN SDK reconnects with Last-Event-ID header
- THEN system sends missed events since that ID
- AND SDK receives complete update history

### Requirement: SDK Registration

The system MUST track SDK registrations for observability.

#### Scenario: Register SDK instance

- GIVEN a valid API key
- WHEN SDK sends POST /api/v1/sdk/register/ with sdk_type, version
- THEN system creates SDKRegistration record
- AND associates with the environment

#### Scenario: Track last seen

- GIVEN an SDK is registered
- WHEN SDK makes any request
- THEN system updates last_seen_at timestamp

### Requirement: Evaluation Logging

The system MUST log flag evaluations for analytics.

#### Scenario: Log evaluation result

- GIVEN a flag evaluation request
- WHEN SDK evaluates a flag
- THEN system creates EvaluationLog record
- AND log includes flag_id, context hash, result, timestamp

#### Scenario: Batch logging

- GIVEN SDK evaluates 10 flags in one request
- WHEN evaluation completes
- THEN system creates 10 EvaluationLog records
- AND logging does not block the response

## Key Learnings

1. SDK integration specs define the contract between backend and SDKs.
2. Local evaluation pattern requires complete rule tree in flag retrieval response.
3. SSE connection provides real-time updates with < 50ms latency target.
4. Evaluation logging enables analytics without blocking SDK responses.