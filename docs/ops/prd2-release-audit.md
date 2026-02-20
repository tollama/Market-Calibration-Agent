# PRD2 Release Audit Automation

This document describes the automated release-readiness audit for PRD2.

## Purpose

The audit checks PRD2 release blockers and P1 items using a machine-readable checklist:

- Checklist: `docs/ops/prd2-release-checklist.yaml`
- Auditor: `scripts/prd2_release_audit.py`

The auditor validates:

1. Required files/artifacts exist.
2. Required verification commands pass.
3. Overall status for **blockers** and **P1** is reported as PASS/FAIL.

## Usage

From repository root:

```bash
python3 scripts/prd2_release_audit.py
```

### JSON output

```bash
python3 scripts/prd2_release_audit.py --json
```

### Skip command execution (file-only audit)

```bash
python3 scripts/prd2_release_audit.py --skip-commands
```

### Custom checklist / repo root

```bash
python3 scripts/prd2_release_audit.py \
  --checklist docs/ops/prd2-release-checklist.yaml \
  --repo-root .
```

## Exit codes

- `0`: overall PASS
- `1`: overall FAIL (missing/failed checks)
- `2`: audit error (invalid config, timeout, runtime error)

## Example output

```text
PRD2 Release Audit: PASS
- blockers=PASS p1=PASS (total=16 pass=15 warn=1 fail=0 skip=0)
[PASS] RB-001 (blocker) TSFM forecast API contract implemented
...
[WARN] P1-005 (p1) Live integration tests are runnable (may skip if env not configured)
```

## Notes

- Live integration checks may be skipped when `LIVE_TOLLAMA_TESTS` or runtime connectivity is not configured. In that case, the audit marks the check as `WARN` rather than hard fail for P1 policy tracking.
- Release decision should primarily gate on **all blockers passing**.
