from __future__ import annotations

from datetime import datetime, timezone

from pipelines.build_alert_feed import build_alert_feed_rows
from runners.tsfm_service import TSFMRunnerService


class _StableAdapter:
    def forecast(self, **_: object):
        return (
            {0.1: [0.20, 0.25], 0.5: [0.50, 0.55], 0.9: [0.80, 0.85]},
            {"runtime": "tollama", "latency_ms": 3.5},
        )


def _tsfm_request() -> dict[str, object]:
    return {
        "market_id": "prd2-market-1",
        "as_of_ts": datetime(2026, 2, 20, tzinfo=timezone.utc).isoformat(),
        "freq": "5m",
        "horizon_steps": 2,
        "quantiles": [0.1, 0.5, 0.9],
        "y": [0.42] * 64,
        "transform": {"space": "logit", "eps": 1e-6},
        "model": {"model_name": "chronos", "model_version": "v1", "params": {}},
    }


def test_prd1_i15_min_trust_score_boundary_is_inclusive() -> None:
    """Traceability: PRD1 I-15 AC (min_trust_score + strict gate boundary behavior)."""
    rows = [
        {
            "market_id": "mkt-at-threshold",
            "ts": "2026-02-20T12:00:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "volume_velocity": 2.5,
            "ambiguity_score": 0.30,
            "trust_score": 60.0,
            "strict_gate_passed": True,
        },
        {
            "market_id": "mkt-below-threshold",
            "ts": "2026-02-20T11:59:00Z",
            "p_yes": 0.95,
            "q10": 0.20,
            "q90": 0.90,
            "open_interest_change_1h": -0.20,
            "volume_velocity": 2.5,
            "ambiguity_score": 0.30,
            "trust_score": 59.99,
            "strict_gate_passed": True,
        },
    ]

    alerts = build_alert_feed_rows(rows, min_trust_score=60.0)

    assert [row["market_id"] for row in alerts] == ["mkt-at-threshold"]
    assert alerts[0]["severity"] == "HIGH"


def test_prd2_ac_operational_meta_contains_observability_fields() -> None:
    """Traceability: PRD2 AC#3 Operational (latency/fallback/circuit/degradation observability)."""
    service = TSFMRunnerService(adapter=_StableAdapter())

    response = service.forecast(_tsfm_request())
    meta = response["meta"]

    for key in (
        "runtime",
        "latency_ms",
        "fallback_used",
        "cache_hit",
        "cache_stale",
        "circuit_breaker_state",
        "degradation_state",
        "warnings",
    ):
        assert key in meta


def test_prd2_ac_product_alignment_band_breach_signal_is_deterministic() -> None:
    """Traceability: PRD2 AC#4 Product alignment (stable band-breach signal for Gate-1 alerting)."""
    service = TSFMRunnerService(adapter=_StableAdapter())
    first = service.forecast(_tsfm_request())
    second = service.forecast(_tsfm_request())

    row_template = {
        "market_id": "prd2-market-1",
        "ts": "2026-02-20T12:00:00Z",
        "p_yes": 0.95,
        "open_interest_change_1h": -0.20,
        "volume_velocity": 2.5,
        "ambiguity_score": 0.30,
        "strict_gate_passed": True,
        "trust_score": 80.0,
    }
    rows = [
        {**row_template, "q10": first["yhat_q"]["0.1"][0], "q90": first["yhat_q"]["0.9"][0]},
        {**row_template, "q10": second["yhat_q"]["0.1"][0], "q90": second["yhat_q"]["0.9"][0]},
    ]

    alerts = build_alert_feed_rows(rows, min_trust_score=60.0)

    assert len(alerts) == 2
    assert all("BAND_BREACH" in alert["reason_codes"] for alert in alerts)
    assert all(alert["severity"] == "HIGH" for alert in alerts)
    assert alerts[0]["reason_codes"] == alerts[1]["reason_codes"]
