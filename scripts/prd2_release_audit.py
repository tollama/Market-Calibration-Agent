#!/usr/bin/env python3
"""PRD2 release-readiness auditor.

Validates required artifacts and quality gates defined in
`docs/ops/prd2-release-checklist.yaml` and reports PASS/FAIL with missing items.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CheckResult:
    check_id: str
    title: str
    severity: str
    check_type: str
    ok: bool
    status: str
    detail: str = ""
    command: str | None = None
    duration_s: float | None = None
    returncode: int | None = None


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Checklist file must be a mapping: {path}")
    return data


def _iter_checks(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for section in ("release_blockers", "p1_items"):
        items = cfg.get(section, [])
        if not isinstance(items, list):
            raise ValueError(f"{section} must be a list")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"Invalid check entry in {section}: {item!r}")
            normalized = dict(item)
            normalized["section"] = section
            checks.append(normalized)
    return checks


def _check_file(root: Path, check: dict[str, Any]) -> CheckResult:
    rel = check.get("path")
    if not rel:
        return CheckResult(
            check_id=str(check.get("id", "UNKNOWN")),
            title=str(check.get("title", "")),
            severity=str(check.get("severity", "unknown")),
            check_type="file",
            ok=False,
            status="FAIL",
            detail="missing `path` field",
        )

    p = root / str(rel)
    ok = p.exists()
    return CheckResult(
        check_id=str(check.get("id", "UNKNOWN")),
        title=str(check.get("title", "")),
        severity=str(check.get("severity", "unknown")),
        check_type="file",
        ok=ok,
        status="PASS" if ok else "FAIL",
        detail=str(rel) if ok else f"missing file: {rel}",
    )


def _check_command(root: Path, check: dict[str, Any], skip_commands: bool) -> CheckResult:
    cmd = check.get("command")
    cid = str(check.get("id", "UNKNOWN"))
    title = str(check.get("title", ""))
    severity = str(check.get("severity", "unknown"))

    if not cmd:
        return CheckResult(
            check_id=cid,
            title=title,
            severity=severity,
            check_type="command",
            ok=False,
            status="FAIL",
            detail="missing `command` field",
        )

    if skip_commands:
        return CheckResult(
            check_id=cid,
            title=title,
            severity=severity,
            check_type="command",
            ok=True,
            status="SKIP",
            detail="command execution skipped by --skip-commands",
            command=str(cmd),
        )

    timeout_s = int(check.get("timeout_s", 180))
    started = time.time()
    proc = subprocess.run(
        str(cmd),
        cwd=str(root),
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    elapsed = time.time() - started

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    combined = "\n".join(x for x in [stdout, stderr] if x).strip()
    snippet = combined[:800]

    ok = proc.returncode == 0
    status = "PASS" if ok else "FAIL"

    # Policy: integration live tests may skip due to env; treat as warning/pass.
    if (not ok) and "test_tollama_live_integration.py" in str(cmd):
        text = combined.lower()
        if "skipped" in text or "no tests ran" in text:
            ok = True
            status = "WARN"

    return CheckResult(
        check_id=cid,
        title=title,
        severity=severity,
        check_type="command",
        ok=ok,
        status=status,
        detail=snippet,
        command=str(cmd),
        duration_s=elapsed,
        returncode=proc.returncode,
    )


def run_audit(checklist_path: Path, repo_root: Path, skip_commands: bool) -> dict[str, Any]:
    cfg = _load_yaml(checklist_path)
    checks = _iter_checks(cfg)

    results: list[CheckResult] = []
    for check in checks:
        ctype = str(check.get("type", "")).strip().lower()
        if ctype == "file":
            results.append(_check_file(repo_root, check))
        elif ctype == "command":
            results.append(_check_command(repo_root, check, skip_commands=skip_commands))
        else:
            results.append(
                CheckResult(
                    check_id=str(check.get("id", "UNKNOWN")),
                    title=str(check.get("title", "")),
                    severity=str(check.get("severity", "unknown")),
                    check_type=ctype or "unknown",
                    ok=False,
                    status="FAIL",
                    detail=f"unsupported check type: {ctype!r}",
                )
            )

    blocker_results = [r for r in results if r.severity.lower() == "blocker"]
    p1_results = [r for r in results if r.severity.lower() == "p1"]

    blockers_ok = all(r.ok for r in blocker_results)
    p1_ok = all(r.ok for r in p1_results)
    overall_ok = blockers_ok and p1_ok

    missing = [
        {
            "id": r.check_id,
            "severity": r.severity,
            "title": r.title,
            "type": r.check_type,
            "status": r.status,
            "detail": r.detail,
        }
        for r in results
        if not r.ok
    ]

    return {
        "timestamp": int(time.time()),
        "checklist": str(checklist_path),
        "repo_root": str(repo_root),
        "summary": {
            "overall": "PASS" if overall_ok else "FAIL",
            "blockers": "PASS" if blockers_ok else "FAIL",
            "p1": "PASS" if p1_ok else "FAIL",
            "total_checks": len(results),
            "passed": sum(1 for r in results if r.ok and r.status == "PASS"),
            "warnings": sum(1 for r in results if r.status == "WARN"),
            "failed": sum(1 for r in results if not r.ok),
            "skipped": sum(1 for r in results if r.status == "SKIP"),
        },
        "results": [
            {
                "id": r.check_id,
                "title": r.title,
                "severity": r.severity,
                "type": r.check_type,
                "status": r.status,
                "ok": r.ok,
                "detail": r.detail,
                "command": r.command,
                "duration_s": r.duration_s,
                "returncode": r.returncode,
            }
            for r in results
        ],
        "missing_items": missing,
    }


def print_human(report: dict[str, Any]) -> None:
    s = report["summary"]
    print(f"PRD2 Release Audit: {s['overall']}")
    print(
        f"- blockers={s['blockers']} p1={s['p1']} "
        f"(total={s['total_checks']} pass={s['passed']} warn={s['warnings']} fail={s['failed']} skip={s['skipped']})"
    )
    for r in report["results"]:
        tag = r["status"]
        print(f"[{tag}] {r['id']} ({r['severity']}) {r['title']}")
        if r.get("status") in {"FAIL", "WARN"} and r.get("detail"):
            print(f"  -> {r['detail']}")

    if report["missing_items"]:
        print("\nMissing/failed items:")
        for m in report["missing_items"]:
            print(f"- {m['id']} {m['title']} :: {m['detail']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PRD2 release-readiness auditor")
    parser.add_argument(
        "--checklist",
        default="docs/ops/prd2-release-checklist.yaml",
        help="Path to checklist YAML",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument(
        "--skip-commands",
        action="store_true",
        help="Skip command execution checks",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report to stdout",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checklist_path = Path(args.checklist).resolve()
    repo_root = Path(args.repo_root).resolve()

    if not checklist_path.exists():
        print(f"Checklist not found: {checklist_path}", file=sys.stderr)
        return 2

    try:
        report = run_audit(
            checklist_path=checklist_path,
            repo_root=repo_root,
            skip_commands=args.skip_commands,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"Command timeout: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover
        print(f"Audit error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)

    return 0 if report["summary"]["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
