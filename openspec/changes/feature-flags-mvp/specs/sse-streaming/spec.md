# SSE Streaming Specification

**Date**: 2026-08-26
**Capability**: sse-streaming
**Status**: New

## Purpose

Server-Sent Events infrastructure for pushing flag updates to connected SDKs. This enables real-time synchronization between backend and SDKs.

## Requirements

### Requirement: SSE Connection Management

The system MUST manage SSE connections with proper lifecycle.

#### Scenario: Establish SSE connection

- GIVEN a valid API key
- WHEN client sends GET /api/v1/sdk/stream/
- THEN system establishes SSE connection
- AND sends initial event: type=connected, data={snapshot of all flags}

#### Scenario: Connection keepalive

- GIVEN an established SSE connection
- WHEN no events are sent for 30 seconds
- THEN system sends keepalive comment (: keepalive)
- AND connection remains open

#### Scenario: Connection cleanup

- GIVEN an SSE connection that has been idle for 5 minutes
- WHEN no activity detected
- THEN system closes connection gracefully
- AND logs disconnection event

### Requirement: Redis Streams Integration

The system MUST use Redis Streams for durable message delivery.

#### Scenario: Subscribe to Redis Stream

- GIVEN an environment with api_key="sk_test_123"
- WHEN SSE connection is established
- THEN system subscribes to Redis Stream "flags:sk_test_123"
- AND reads from latest message

#### Scenario: Publish flag change to stream

- GIVEN a flag in environment "sk_test_123" is updated
- WHEN admin saves the flag
- THEN system publishes event to Redis Stream "flags:sk_test_123"
- AND event contains full flag payload

#### Scenario: Consumer group for multiple instances

- GIVEN 3 backend instances serving SSE connections
- WHEN flag change is published
- THEN each instance receives the event once
- AND no duplicate events are sent to clients

### Requirement: Event Format

The system MUST send events in standard SSE format.

#### Scenario: Flag update event

- GIVEN a flag is updated
- WHEN SSE event is sent
- THEN format is:
  ```
  event: flag_update
  id: {unique-event-id}
  data: {"flag_key": "...", "is_enabled": true, ...}
  ```

#### Scenario: Initial snapshot event

- GIVEN SSE connection is established
- WHEN initial snapshot is sent
- THEN format is:
  ```
  event: snapshot
  id: {unique-event-id}
  data: {"flags": [...], "environment": "..."}
  ```

#### Scenario: Flag deletion event

- GIVEN a flag is deleted
- WHEN SSE event is sent
- THEN format is:
  ```
  event: flag_delete
  id: {unique-event-id}
  data: {"flag_key": "..."}
  ```

### Requirement: Reconnection with Event ID

The system MUST support reconnection with event ID tracking.

#### Scenario: Client reconnects with Last-Event-ID

- GIVEN client was connected but connection dropped
- WHEN client sends GET /api/v1/sdk/stream/ with Last-Event-ID: 123
- THEN system reads events from Redis Stream after ID 123
- AND sends all missed events in order

#### Scenario: Event ID not found in stream

- GIVEN client reconnects with Last-Event-ID: 999
- WHEN Redis Stream has events starting from ID 1000
- THEN system sends events from ID 1000
- AND sends note: "Some events may have been missed"

### Requirement: Performance

The system MUST meet latency requirements for real-time updates.

#### Scenario: Sub-50ms delivery

- GIVEN an SDK connected via SSE
- WHEN admin updates a flag via API
- THEN SDK receives the SSE event within 50ms
- AND measurement includes: API processing + Redis publish + SSE delivery

#### Scenario: Multiple concurrent connections

- GIVEN 1000 SDKs connected via SSE
- WHEN a flag is updated
- THEN all 1000 SDKs receive the event within 100ms
- AND no connection is dropped due to load

### Requirement: Error Handling

The system MUST handle errors gracefully without crashing.

#### Scenario: Redis connection lost

- GIVEN SSE connection is active
- WHEN Redis connection is temporarily lost
- THEN system sends error event to client
- AND attempts reconnection with exponential backoff

#### Scenario: Invalid event data

- GIVEN SSE connection is active
- WHEN Redis Stream contains corrupted event
- THEN system skips the event
- AND logs error for debugging

## Key Learnings

1. SSE streaming specs define the real-time update mechanism for SDKs.
2. Redis Streams provide durable messaging with consumer groups for horizontal scaling.
3. Event ID tracking enables reliable reconnection after disconnections.
4. Performance requirements target < 50ms for flag updates to reach SDKs.