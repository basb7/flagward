# Flag Evaluation Specification

**Date**: 2026-08-26
**Capability**: flag-evaluation
**Status**: New

## Purpose

Local evaluation engine that processes flag rules and returns boolean/multivariate results. This is the core logic that SDKs use to determine flag states.

## Requirements

### Requirement: Boolean Flag Evaluation

The system MUST evaluate boolean flags based on rules and conditions.

#### Scenario: Flag disabled returns false

- GIVEN a flag with is_enabled=False
- WHEN evaluating the flag with any context
- THEN result is False

#### Scenario: Flag enabled with no rules returns true

- GIVEN a flag with is_enabled=True and no rules
- WHEN evaluating the flag with any context
- THEN result is True

#### Scenario: Flag enabled with matching rule returns true

- GIVEN a flag with is_enabled=True
- AND a rule with operator_logic=AND and conditions that match context
- WHEN evaluating the flag with matching context
- THEN result is True

#### Scenario: Flag enabled with non-matching rule returns false

- GIVEN a flag with is_enabled=True
- AND a rule with operator_logic=AND and conditions that don't match context
- WHEN evaluating the flag with non-matching context
- THEN result is False

### Requirement: Rule Evaluation Logic

The system MUST evaluate rules using AND/OR operator logic.

#### Scenario: AND logic requires all conditions

- GIVEN a rule with operator_logic=AND
- AND conditions: country=US, plan=premium
- WHEN evaluating with context {country: "US", plan: "premium"}
- THEN rule evaluates to True

#### Scenario: AND logic fails on any condition

- GIVEN a rule with operator_logic=AND
- AND conditions: country=US, plan=premium
- WHEN evaluating with context {country: "US", plan: "free"}
- THEN rule evaluates to False

#### Scenario: OR logic requires any condition

- GIVEN a rule with operator_logic=OR
- AND conditions: country=US, plan=premium
- WHEN evaluating with context {country: "US", plan: "free"}
- THEN rule evaluates to True

#### Scenario: OR logic fails on all conditions

- GIVEN a rule with operator_logic=OR
- AND conditions: country=US, plan=premium
- WHEN evaluating with context {country: "AR", plan: "free"}
- THEN rule evaluates to False

### Requirement: Condition Operators

The system MUST support all specified condition operators.

#### Scenario: EQUALS operator

- GIVEN a condition with attribute="country", operator=EQUALS, value="US"
- WHEN evaluating with context {country: "US"}
- THEN condition evaluates to True

#### Scenario: NOT_EQUALS operator

- GIVEN a condition with attribute="country", operator=NOT_EQUALS, value="US"
- WHEN evaluating with context {country: "AR"}
- THEN condition evaluates to True

#### Scenario: GREATER_THAN operator

- GIVEN a condition with attribute="age", operator=GREATER_THAN, value=18
- WHEN evaluating with context {age: 21}
- THEN condition evaluates to True

#### Scenario: LESS_THAN operator

- GIVEN a condition with attribute="age", operator=LESS_THAN, value=18
- WHEN evaluating with context {age: 15}
- THEN condition evaluates to True

#### Scenario: IN_LIST operator

- GIVEN a condition with attribute="plan", operator=IN_LIST, value=["premium", "enterprise"]
- WHEN evaluating with context {plan: "premium"}
- THEN condition evaluates to True

#### Scenario: CONTAINS operator

- GIVEN a condition with attribute="tags", operator=CONTAINS, value="beta"
- WHEN evaluating with context {tags: ["beta", "test"]}
- THEN condition evaluates to True

### Requirement: Multivariate Flag Evaluation

The system MUST evaluate multivariate flags with multiple variants.

#### Scenario: Multivariate with matching rule returns variant

- GIVEN a multivariate flag with variants: control, treatment_a, treatment_b
- AND a rule for treatment_a with matching conditions
- WHEN evaluating the flag with matching context
- THEN result is "treatment_a"

#### Scenario: Multivariate with no matching rule returns control

- GIVEN a multivariate flag with variants: control, treatment_a
- AND no rules match the context
- WHEN evaluating the flag with any context
- THEN result is "control"

### Requirement: Rule Priority Ordering

The system MUST evaluate rules in priority order.

#### Scenario: First matching rule wins

- GIVEN a flag with rules at priorities 0, 1, 2
- AND rule 0 matches context
- WHEN evaluating the flag
- THEN rule 0's result is returned
- AND rules 1 and 2 are not evaluated

#### Scenario: Skip non-matching rules

- GIVEN a flag with rules at priorities 0, 1
- AND rule 0 does not match context
- AND rule 1 matches context
- WHEN evaluating the flag
- THEN rule 1's result is returned

## Key Learnings

1. Flag evaluation is deterministic: same inputs always produce same outputs.
2. Rule priority ordering ensures predictable evaluation sequence.
3. AND/OR operator logic provides flexible condition combinations.
4. Multivariate flags return control variant when no rules match.