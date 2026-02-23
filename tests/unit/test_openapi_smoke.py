from __future__ import annotations

import sys

from scripts import openapi_smoke


def _run_main_with_args(
    monkeypatch,
    *,
    args: list[str],
    spec: dict[str, object],
    output_path: str,
) -> int:
    monkeypatch.setattr(openapi_smoke, "_load_spec", lambda _base_url: spec)
    monkeypatch.setattr(sys, "argv", ["openapi_smoke.py", *args, "--output", str(output_path)])
    return openapi_smoke.main()


def test_openapi_smoke_reports_pass_for_required_routes(monkeypatch, tmp_path) -> None:
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "Market Calibration API", "version": "1.0.0"},
        "paths": {
            "/scoreboard": {"get": {}},
            "/alerts": {"get": {}},
            "/tsfm/forecast": {"post": {}},
            "/metrics": {"get": {}},
            "/tsfm/metrics": {"get": {}},
            "/markets": {"get": {}},
            "/markets/{market_id}": {"get": {}},
            "/markets/{market_id}/metrics": {"get": {}},
            "/markets/{market_id}/comparison": {"post": {}},
            "/postmortem/{market_id}": {"get": {}},
        },
    }

    out = tmp_path / "smoke_pass.json"
    code = _run_main_with_args(
        monkeypatch,
        args=[
            "--base-url",
            "http://127.0.0.1:8000",
            "--required",
            "/scoreboard:get",
            "--required",
            "/alerts:get",
            "--required",
            "/markets:get",
            "--required",
            "/markets/{market_id}:get",
            "--required",
            "/markets/{market_id}/metrics:get",
            "--required",
            "/markets/{market_id}/comparison:post",
            "--required",
            "/postmortem/{market_id}:get",
            "--required",
            "/tsfm/forecast:post",
            "--required",
            "/metrics:get",
            "--required",
            "/tsfm/metrics:get",
        ],
        spec=spec,
        output_path=str(out),
    )

    assert code == 0
    payload = out.read_text(encoding="utf-8")
    assert '"status": "PASS"' in payload


def test_openapi_smoke_treats_openapi_json_requirement_as_route(monkeypatch, tmp_path) -> None:
    spec = {
        "openapi": "3.0.3",
        "paths": {
            "/scoreboard": {"get": {}},
            "/alerts": {"get": {}},
            "/tsfm/forecast": {"post": {}},
            "/metrics": {"get": {}},
            "/tsfm/metrics": {"get": {}},
            "/markets": {"get": {}},
            "/markets/{market_id}": {"get": {}},
            "/markets/{market_id}/metrics": {"get": {}},
            "/markets/{market_id}/comparison": {"post": {}},
            "/postmortem/{market_id}": {"get": {}},
        },
    }

    out = tmp_path / "smoke_fail.json"
    code = _run_main_with_args(
        monkeypatch,
        args=[
            "--base-url",
            "http://127.0.0.1:8000",
            "--required",
            "/openapi.json",
            "--required",
            "/scoreboard:get",
            "--required",
            "/alerts:get",
            "--required",
            "/markets:get",
            "--required",
            "/markets/{market_id}:get",
            "--required",
            "/markets/{market_id}/metrics:get",
            "--required",
            "/markets/{market_id}/comparison:post",
            "--required",
            "/postmortem/{market_id}:get",
            "--required",
            "/tsfm/forecast:post",
            "--required",
            "/metrics:get",
            "--required",
            "/tsfm/metrics:get",
        ],
        spec=spec,
        output_path=str(out),
    )

    assert code == 1
    payload = out.read_text(encoding="utf-8")
    assert "missing path: /openapi.json" in payload
