#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from typing import Any


def _parse_required(path_method: str) -> tuple[str, str]:
    if ":" in path_method:
        path, method = path_method.split(":", 1)
    else:
        path, method = path_method, "get"
    return path.strip(), method.strip().lower()


def _load_spec(base_url: str) -> dict[str, Any]:
    target = base_url.rstrip("/") + "/openapi.json"
    with urlopen(target, timeout=15) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"openapi endpoint returned {resp.status}")
        data = resp.read().decode("utf-8")
    return json.loads(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for FastAPI OpenAPI contract")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument(
        "--required",
        action="append",
        default=[
            "/scoreboard:get",
            "/alerts:get",
            "/markets:get",
            "/markets/{market_id}:get",
            "/markets/{market_id}/metrics:get",
            "/markets/{market_id}/comparison:post",
            "/postmortem/{market_id}:get",
            "/tsfm/forecast:post",
            "/metrics:get",
            "/tsfm/metrics:get",
        ],
        help="Required route to validate (default: canonical API+TSFM paths).",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="OpenAPI GET timeout (seconds)")
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args()

    failures: list[str] = []
    warnings: list[str] = []

    try:
        spec = _load_spec(args.base_url)
    except (HTTPError, URLError, ValueError, RuntimeError) as exc:
        failures.append(f"failed to fetch or parse /openapi.json: {exc}")
        print("OPENAPI_SMOKE_FAIL")
        print("\n".join(f" - {item}" for item in failures))
        if args.output:
            payload = {"status": "FAIL", "openapi_url": args.base_url.rstrip("/") + "/openapi.json", "failures": failures, "warnings": warnings}
            Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 1

    if not isinstance(spec, dict):
        failures.append("openapi payload is not a JSON object")
    else:
        if not spec.get("openapi"):
            warnings.append("missing openapi version field")
        if "paths" not in spec or not isinstance(spec.get("paths"), dict):
            failures.append("missing/invalid paths section")
        else:
            paths = spec["paths"]
            for requirement in args.required:
                requirement = requirement.strip()
                if not requirement:
                    continue

                path, method = _parse_required(requirement)
                operations = paths.get(path)
                if operations is None:
                    failures.append(f"missing path: {path}")
                    continue
                if not isinstance(operations, dict):
                    failures.append(f"invalid path object for: {path}")
                    continue
                if method not in operations:
                    failures.append(f"missing method for {path}: {method.upper()}")

    if failures:
        print("OPENAPI_SMOKE_FAIL")
        print("\n".join(f" - {item}" for item in failures))
        if warnings:
            print("WARNINGS:")
            print("\n".join(f" - {item}" for item in warnings))
        if args.output:
            payload = {
                "status": "FAIL",
                "openapi_url": args.base_url.rstrip("/") + "/openapi.json",
                "openapi_version": spec.get("openapi") if isinstance(spec, dict) else None,
                "failures": failures,
                "warnings": warnings,
            }
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.write("\n")
        return 1

    print("OPENAPI_SMOKE_PASS")
    print(f"openapi={spec.get('openapi', 'n/a')}")
    if args.output:
        payload = {
            "status": "PASS",
            "openapi_url": args.base_url.rstrip("/") + "/openapi.json",
            "openapi_version": spec.get("openapi"),
            "title": spec.get("info", {}).get("title"),
            "version": spec.get("info", {}).get("version"),
            "required_checked": args.required,
            "warnings": warnings,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
