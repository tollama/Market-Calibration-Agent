from __future__ import annotations

import pipelines.daily_job as daily_job


def test_i15_ingest_to_publish_alert_regression_with_real_gate_pipeline(
    monkeypatch,
    tmp_path,
) -> None:
    alert_config = tmp_path / "alerts.yaml"
    alert_config.write_text(
        """
thresholds:
  low_oi_confirmation: -0.15
  low_ambiguity: 0.35
  volume_spike: 2.0
min_trust_score: 60.0
""".strip()
        + "\n",
        encoding="utf-8",
    )

    def discover_seed(context):
        context.state["market_ids"] = ["m-emit", "m-trust-block", "m-gate-block"]
        context.state["root_path"] = str(tmp_path)
        context.state["events"] = [
            {"market_id": "m-emit", "event_id": "evt-1"},
            {"market_id": "m-trust-block", "event_id": "evt-2"},
            {"market_id": "m-gate-block", "event_id": "evt-3"},
        ]
        context.state["raw_records"] = [
            {
                "market_id": "m-emit",
                "ts": "2026-02-21T00:00:00Z",
                "cutoff_type": "T-1h",
                "cutoff_ts": "2026-02-21T00:30:00Z",
                "pred": 0.75,
                "label": 1,
                "category": "politics",
                "liquidity_bucket": "high",
                "p_yes": 0.75,
                "q10": 0.40,
                "q90": 0.60,
                "open_interest_change_1h": -0.25,
                "ambiguity_score": 0.10,
                "volume_velocity": 3.0,
                "trust_score": 80.0,
                "strict_gate_passed": True,
            },
            {
                "market_id": "m-trust-block",
                "ts": "2026-02-21T00:00:00Z",
                "cutoff_type": "T-1h",
                "cutoff_ts": "2026-02-21T00:30:00Z",
                "pred": 0.78,
                "label": 1,
                "category": "sports",
                "liquidity_bucket": "mid",
                "p_yes": 0.78,
                "q10": 0.40,
                "q90": 0.60,
                "open_interest_change_1h": -0.22,
                "ambiguity_score": 0.15,
                "volume_velocity": 2.5,
                "trust_score": 50.0,
                "strict_gate_passed": True,
            },
            {
                "market_id": "m-gate-block",
                "ts": "2026-02-21T00:00:00Z",
                "cutoff_type": "T-1h",
                "cutoff_ts": "2026-02-21T00:30:00Z",
                "pred": 0.82,
                "label": 1,
                "category": "crypto",
                "liquidity_bucket": "high",
                "p_yes": 0.82,
                "q10": 0.40,
                "q90": 0.60,
                "open_interest_change_1h": -0.20,
                "ambiguity_score": 0.20,
                "volume_velocity": 2.6,
                "trust_score": 90.0,
                "strict_gate_passed": False,
            },
        ]
        return {"stage": "discover", "market_count": 3}

    def pass_through_features(context):
        # End-to-end glue intent: preserve ingested/normalized fields into metric stage.
        context.state["feature_rows"] = list(context.state.get("normalized_records") or [])
        return {"feature_count": len(context.state["feature_rows"])}

    monkeypatch.setattr(daily_job, "_stage_discover", discover_seed)
    monkeypatch.setattr(daily_job, "stage_build_features", pass_through_features)

    result = daily_job.run_daily_job(
        run_id="i15-ingest-publish-regression",
        alert_config_path=str(alert_config),
    )
    outputs = {stage["name"]: stage["output"] for stage in result["stages"]}

    assert result["success"] is True
    assert result["stage_order"] == list(daily_job.DAILY_STAGE_NAMES)

    assert outputs["ingest"]["market_count"] == 3
    assert outputs["ingest"]["raw_record_count"] == 3
    assert outputs["normalize"]["normalized_record_count"] == 3

    # I-15 regression target:
    # - m-emit survives trust + strict gate => emitted alert
    # - m-trust-block suppressed by min_trust_score
    # - m-gate-block downgraded to FYI by strict gate and excluded from feed
    assert outputs["metrics"]["alert_count"] == 1
    assert outputs["publish"]["alert_count"] == 1
    assert outputs["metrics"]["alert_policy_loaded"] is True
