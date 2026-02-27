"""Safe no-op calibration entrypoint for dryRun=false canary validation."""

from __future__ import annotations

from datetime import datetime, timezone


def run_calibration(run_id: str | None = None, **_: object) -> dict[str, object]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "run_id": run_id or "noop-canary",
        "success": True,
        "stages": [
            {"name": "noop_preflight", "status": "ok"},
            {"name": "noop_finalize", "status": "ok"},
        ],
        "meta": {
            "entrypoint": "pipelines.noop_calibration_entrypoint",
            "generated_at": now,
            "note": "No external trading side effects.",
        },
    }
