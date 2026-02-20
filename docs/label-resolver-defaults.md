# Label Resolver Defaults

This document captures default assumptions and precedence in `agents/label_resolver.py`.

## Resolution Precedence

`resolve_label(metadata)` applies checks in this order:

1. **Metadata shape guard**
   - If `metadata` is not a mapping/object, return `UNRESOLVED` with reason `metadata_not_mapping`.
2. **VOID/invalid markers**
   - If any VOID marker is present, return `VOID` with reason `void_or_invalid`.
3. **Explicit unresolved markers**
   - If status/flags indicate market is still open or unsettled, return `UNRESOLVED` with reason `status_not_final`.
4. **Explicit winner extraction**
   - If a winner is found and maps to binary Yes/No semantics, return `RESOLVED_TRUE` or `RESOLVED_FALSE`.
   - If a winner exists but is non-binary, return `UNRESOLVED` with reason `non_binary_outcome`.
5. **Resolved marker without winner**
   - If resolved/closed markers are present, try price-based inference.
   - If inference succeeds, return resolved status with reason `inferred_from_prices`.
   - If inference fails, return `UNRESOLVED` with reason `resolved_without_binary_winner`.
6. **Fallback**
   - If nothing above applies, return `UNRESOLVED` with reason `insufficient_metadata`.

Why this order:

- It is conservative by design: explicit invalidation (VOID) and explicit non-final signals win over potentially stale winner fields.
- Resolved outcomes are emitted only when binary semantics can be established from winner fields or deterministic price patterns.

### Status Marker Precedence

When metadata contains conflicting status-like signals, precedence is:

1. `VOID` markers
2. `UNRESOLVED` markers
3. `RESOLVED` markers

Rationale:

- `VOID`/invalid must override all other signals because cancelled/invalid markets should never be force-labeled as true/false.
- `UNRESOLVED` markers are evaluated before resolved markers to avoid treating still-open markets as final because of stale flags.
- `RESOLVED` markers only enable inference when no stronger contradictory marker is present.

## Default Token Sets

The resolver normalizes text to lowercase and trims whitespace before token checks.

- `TRUE` tokens: `{"1", "true", "yes", "y"}`
- `FALSE` tokens: `{"0", "false", "no", "n"}`
- `VOID` tokens: `{"void", "invalid", "canceled", "cancelled"}`
- `UNRESOLVED status` tokens: `{"active", "open", "pending", "unresolved"}`
- `RESOLVED status` tokens: `{"closed", "finalized", "resolved", "settled"}`

Additional binary matching behavior:

- Any normalized winner token starting with `yes` is treated as `TRUE`.
- Any normalized winner token starting with `no` is treated as `FALSE`.

## Outcome ID Fallback Behavior

Outcome IDs are read from the first available list in this order:

1. `outcome_ids`
2. `clob_token_ids`
3. `token_ids`
4. `tokens`

Fallback defaults when token IDs are missing or incomplete:

- Winner-by-index path: if no token ID exists at that index, fallback `outcome_id = str(index)`.
- Price-inference path: if token IDs are missing, fallback to `"0"`/`"1"` based on inferred yes/no index.
- Winner-by-ID path: if supplied ID cannot be matched to provided `outcome_ids`, outcomes, or index coercion, preserve raw ID as-is (normalized) as `outcome_id`.

Examples:

- `winningOutcomeIndex=1`, no token IDs -> `outcome_id="1"`.
- Resolved from prices, yes at index `0`, no token IDs -> true case returns `outcome_id="0"`.
- `winningOutcomeId="abc123"` with no matching ID list -> `outcome_id="abc123"` if binary mapping can be inferred from token text.

## Reason Codes and Examples

- `metadata_not_mapping`
  - Trigger: input is not a mapping/object.
  - Example: `resolve_label(["not", "a", "mapping"])`.
- `void_or_invalid`
  - Trigger: VOID status/flags/outcome markers detected.
  - Example: `{"status": "VOID"}` or `{"is_invalid": true}`.
- `status_not_final`
  - Trigger: unresolved/open status markers or explicit `resolved=false` style flags.
  - Example: `{"status": "ACTIVE"}` or `{"is_resolved": false}`.
- `non_binary_outcome`
  - Trigger: winner found but not interpretable as binary true/false.
  - Example: `{"status": "RESOLVED", "winning_outcome": "maybe"}`.
- `inferred_from_prices`
  - Trigger: resolved markers exist, no explicit binary winner, and deterministic 0/1 prices imply yes/no winner.
  - Example: `{"status":"RESOLVED","outcomes":["Yes","No"],"outcome_prices":[1,0]}`.
- `resolved_without_binary_winner`
  - Trigger: resolved markers exist but binary winner cannot be established.
  - Example: `{"status":"RESOLVED","outcomes":["Up","Down"],"outcome_prices":[0.7,0.3]}`.
- `insufficient_metadata`
  - Trigger: no decisive markers and no winner info.
  - Example: `{}`.

Note: when explicit winner extraction yields `RESOLVED_TRUE` or `RESOLVED_FALSE`, `reason` is usually `null` unless price inference was used.

## Safe Handling Rules for Malformed Metadata

- Non-mapping metadata is safely downgraded to `UNRESOLVED` with `metadata_not_mapping` (no exception).
- Field names are normalized to snake_case, so mixed inputs like `winningOutcomeIndex` and `winning_outcome_index` are both handled.
- Sequence-like fields (`outcomes`, `outcome_ids`, prices) accept:
  - native arrays/lists,
  - JSON list strings,
  - comma-separated strings (best-effort split fallback).
- Invalid JSON in sequence strings does not fail hard; parser falls back to split behavior where applicable.
- Price parsing is fail-safe: any non-numeric entry causes price inference to abort (returns unresolved path, not an error).
- Boolean/index coercion is strict:
  - booleans are not treated as numeric indexes,
  - negative indexes are rejected.
- Out-of-range winner indexes are ignored rather than crashing.
- Missing metadata defaults to unresolved outcomes; resolver avoids raising for absent optional keys.
