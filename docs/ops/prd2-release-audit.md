# PRD2 Release Audit Automation

This document describes the automated release-readiness audit for PRD2.

## Python runtime requirement (important)

PRD2 audit and gate commands require **Python 3.11+**.

Why: PRD2 code/test paths include 3.11-era runtime assumptions (e.g. `StrEnum`-dependent paths).

Quick fix if your default `python3` is too old:

```bash
# Option A) pass interpreter per command
PYTHON_BIN=python3.11 python3 scripts/prd2_release_audit.py

# Option B) use explicit CLI flag
python3 scripts/prd2_release_audit.py --python-bin python3.11
```

If the runtime precheck fails, the auditor exits with code `2` and prints actionable remediation.

## Purpose

The audit checks PRD2 release blockers and P1 items using a machine-readable checklist:

- Checklist: `docs/ops/prd2-release-checklist.yaml`
- Auditor: `scripts/prd2_release_audit.py`

The auditor validates:

1. Required files/artifacts exist.
2. Required verification commands pass.
3. Overall status for **blockers** and **P1** is reported as PASS/FAIL.
4. Python runtime precheck (3.11+) passes before command gates run.

## Usage

From repository root:

```bash
python3 scripts/prd2_release_audit.py
```

### Use specific Python interpreter (recommended in mixed environments)

```bash
PYTHON_BIN=python3.11 python3 scripts/prd2_release_audit.py
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
- `2`: audit error (invalid config, timeout, runtime error, or Python runtime precheck failure)

## Example output

```text
Using Python runtime: python3.11 (3.11)
PRD2 Release Audit: PASS
- python_bin=python3.11
- blockers=PASS p1=PASS (total=17 pass=16 warn=1 fail=0 skip=0)
[PASS] RB-000 (blocker) Python runtime is 3.11+ (StrEnum-compatible)
...
[WARN] P1-005 (p1) Live integration tests are runnable (may skip if env not configured)
```

## Notes

- Command checks in the checklist use `{PYTHON_BIN}` placeholder and are rendered by the auditor, so all Python gate commands run with one consistent interpreter.
- Live integration checks may be skipped when `LIVE_TOLLAMA_TESTS` or runtime connectivity is not configured. In that case, the audit marks the check as `WARN` rather than hard fail for P1 policy tracking.
- Release decision should primarily gate on **all blockers passing**.
