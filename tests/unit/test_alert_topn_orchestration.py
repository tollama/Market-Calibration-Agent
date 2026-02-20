from __future__ import annotations

from pipelines.alert_topn_orchestration import (
    orchestrate_top_n_alert_decisions,
    rank_top_n_markets,
)


class _StubTSFMService:
    def forecast(self, request):
        _ = request
        return {
            "market_id": request["market_id"],
            "as_of_ts": "2026-02-21T00:00:00Z",
            "yhat_q": {
                "0.1": [0.40] * 12,
                "0.5": [0.50] * 12,
                "0.9": [0.60] * 12,
            },
            "meta": {"runtime": "tollama", "fallback_used": False},
        }


def test_rank_top_n_markets_prioritizes_watchlist_then_alert_candidate_then_score() -> None:
    rows = [
        {"market_id": "m3", "volume_24h": 10, "open_interest": 10, "trust_score": 50},
        {"market_id": "m2", "volume_24h": 100, "open_interest": 100, "trust_score": 50},
        {"market_id": "m1", "volume_24h": 1, "open_interest": 1, "trust_score": 1, "is_alert_candidate": True},
        {"market_id": "m4", "volume_24h": 0, "open_interest": 0, "trust_score": 0},
    ]

    ranked = rank_top_n_markets(rows, top_n=3, watchlist_market_ids=["m4"])

    assert [row["market_id"] for row in ranked] == ["m4", "m1", "m2"]
    assert [row["top_n_rank"] for row in ranked] == [1, 2, 3]


def test_orchestrate_top_n_alert_decisions_outputs_emit_and_suppress_records() -> None:
    rows = [
        {
            "market_id": "m-emit",
            "ts": "2026-02-21T00:00:00Z",
            "forecast_request": {
                "market_id": "m-emit",
                "y": [0.5] * 64,
                "freq": "5m",
                "horizon_steps": 12,
                "quantiles": [0.1, 0.5, 0.9],
            },
            "p_yes": 0.75,
            "open_interest_change_1h": -0.2,
            "ambiguity_score": 0.2,
            "volume_velocity": 3.2,
            "strict_gate_passed": True,
            "trust_score": 80.0,
            "volume_24h": 100,
            "open_interest": 100,
        },
        {
            "market_id": "m-low-trust",
            "forecast_request": {
                "market_id": "m-low-trust",
                "y": [0.5] * 64,
            },
            "trust_score": 20.0,
            "volume_24h": 90,
            "open_interest": 90,
        },
        {
            "market_id": "m-excluded",
            "forecast_request": {
                "market_id": "m-excluded",
                "y": [0.5] * 64,
            },
            "trust_score": 90.0,
            "volume_24h": 1,
            "open_interest": 1,
        },
    ]

    decisions = orchestrate_top_n_alert_decisions(
        rows,
        tsfm_service=_StubTSFMService(),
        top_n=2,
        min_trust_score=60.0,
    )

    by_market = {row["market_id"]: row for row in decisions}

    assert by_market["m-emit"]["decision"] == "EMIT"
    assert by_market["m-emit"]["severity"] in {"MED", "HIGH"}

    assert by_market["m-low-trust"]["decision"] == "SUPPRESS"
    assert by_market["m-low-trust"]["suppression_reason"] == "TRUST_GATE"

    assert by_market["m-excluded"]["decision"] == "SUPPRESS"
    assert by_market["m-excluded"]["suppression_reason"] == "TOP_N_EXCLUDED"


def test_orchestrate_top_n_alert_decisions_missing_trust_is_conservative_default() -> None:
    rows = [
        {
            "market_id": "m-missing-trust",
            "forecast_request": {
                "market_id": "m-missing-trust",
                "y": [0.5] * 64,
            },
            "volume_24h": 100,
            "open_interest": 100,
        }
    ]

    decisions = orchestrate_top_n_alert_decisions(
        rows,
        tsfm_service=_StubTSFMService(),
        top_n=1,
        min_trust_score=60.0,
    )

    assert decisions == [
        {
            "market_id": "m-missing-trust",
            "selected_top_n": True,
            "top_n_rank": 1,
            "decision": "SUPPRESS",
            "suppression_reason": "TRUST_GATE",
            "trust_score": None,
            "required_min_trust_score": 60.0,
        }
    ]
