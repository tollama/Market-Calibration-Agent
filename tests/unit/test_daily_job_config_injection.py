import pipelines.daily_job as daily_job


def _discover_with_feature_seed(context) -> dict[str, object]:
    context.state["market_ids"] = ["mkt-1"]
    context.state["feature_rows"] = [
        {
            "market_id": "mkt-1",
            "ts": "2026-02-20T10:00:00Z",
            "pred": 0.61,
            "label": 1,
            "liquidity_bucket": "high",
            "category": "sports",
            "p_yes": 0.61,
            "q10": 0.40,
            "q90": 0.80,
            "trust_score": 72.0,
        }
    ]
    return {"stage": "discover", "market_count": 1}


def _fake_stage_build_features(context) -> dict[str, object]:
    feature_rows = context.state.get("feature_rows")
    if feature_rows is None:
        feature_rows = []
    context.state["feature_rows"] = list(feature_rows)
    return {"feature_count": len(context.state["feature_rows"])}


def test_metrics_stage_injects_config_loaded_policy_kwargs(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_load_trust_weights(config_path):
        captured["trust_config_path"] = config_path
        return {"stability": 0.9}

    def fake_load_alert_thresholds(config_path):
        captured["alert_config_path_for_thresholds"] = config_path
        return {"wide_ci": 0.3}

    def fake_load_alert_min_trust_score(config_path):
        captured["alert_config_path_for_min_trust"] = config_path
        return 65.0

    def fake_build_scoreboard_rows(rows, trust_weights=None):
        captured["scoreboard_rows"] = list(rows)
        captured["scoreboard_trust_weights"] = trust_weights
        return [{"market_id": "mkt-1", "trust_score": 88.0}], {"global": {"brier": 0.1}}

    def fake_build_alert_feed_rows(rows, *, thresholds=None, min_trust_score=None):
        captured["alert_rows"] = list(rows)
        captured["alert_thresholds"] = thresholds
        captured["alert_min_trust_score"] = min_trust_score
        return [{"alert_id": "alert-1", "market_id": "mkt-1", "severity": "HIGH"}]

    monkeypatch.setattr(daily_job, "_stage_discover", _discover_with_feature_seed)
    monkeypatch.setattr(daily_job, "stage_build_features", _fake_stage_build_features)
    monkeypatch.setattr(daily_job, "load_trust_weights", fake_load_trust_weights)
    monkeypatch.setattr(daily_job, "load_alert_thresholds", fake_load_alert_thresholds)
    monkeypatch.setattr(daily_job, "load_alert_min_trust_score", fake_load_alert_min_trust_score)
    monkeypatch.setattr(daily_job, "build_scoreboard_rows", fake_build_scoreboard_rows)
    monkeypatch.setattr(daily_job, "build_alert_feed_rows", fake_build_alert_feed_rows)

    result = daily_job.run_daily_job(
        run_id="daily-config-injection",
        trust_config_path="/tmp/trust-policy.yaml",
        alert_config_path="/tmp/alert-policy.yaml",
    )
    outputs = {stage["name"]: stage["output"] for stage in result["stages"]}

    assert result["success"] is True
    assert captured["trust_config_path"] == "/tmp/trust-policy.yaml"
    assert captured["alert_config_path_for_thresholds"] == "/tmp/alert-policy.yaml"
    assert captured["alert_config_path_for_min_trust"] == "/tmp/alert-policy.yaml"
    assert captured["scoreboard_trust_weights"] == {"stability": 0.9}
    assert captured["alert_thresholds"] == {"wide_ci": 0.3}
    assert captured["alert_min_trust_score"] == 65.0

    assert outputs["metrics"]["scoreboard_count"] == 1
    assert outputs["metrics"]["alert_count"] == 1
    assert outputs["metrics"]["trust_policy_loaded"] is True
    assert outputs["metrics"]["alert_policy_loaded"] is True


def test_metrics_stage_loader_failure_falls_back_to_default_policy_kwargs(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_missing_loader(_config_path):
        raise ModuleNotFoundError("simulated loader import failure")

    def fake_build_scoreboard_rows(rows, trust_weights=None):
        captured["scoreboard_rows"] = list(rows)
        captured["scoreboard_trust_weights"] = trust_weights
        return [{"market_id": "mkt-1", "trust_score": 70.0}], {"global": {}}

    def fake_build_alert_feed_rows(rows, *, thresholds=None, min_trust_score=None):
        captured["alert_rows"] = list(rows)
        captured["alert_thresholds"] = thresholds
        captured["alert_min_trust_score"] = min_trust_score
        return [{"alert_id": "alert-1", "market_id": "mkt-1", "severity": "MED"}]

    monkeypatch.setattr(daily_job, "_stage_discover", _discover_with_feature_seed)
    monkeypatch.setattr(daily_job, "stage_build_features", _fake_stage_build_features)
    monkeypatch.setattr(daily_job, "load_trust_weights", fake_missing_loader)
    monkeypatch.setattr(daily_job, "load_alert_thresholds", fake_missing_loader)
    monkeypatch.setattr(daily_job, "load_alert_min_trust_score", fake_missing_loader)
    monkeypatch.setattr(daily_job, "build_scoreboard_rows", fake_build_scoreboard_rows)
    monkeypatch.setattr(daily_job, "build_alert_feed_rows", fake_build_alert_feed_rows)

    result = daily_job.run_daily_job(
        run_id="daily-config-loader-fallback",
        trust_config_path="/tmp/missing-trust-policy.yaml",
        alert_config_path="/tmp/missing-alert-policy.yaml",
    )
    outputs = {stage["name"]: stage["output"] for stage in result["stages"]}

    assert result["success"] is True
    assert captured["scoreboard_trust_weights"] is None
    assert captured["alert_thresholds"] is None
    assert captured["alert_min_trust_score"] is None
    assert outputs["metrics"]["scoreboard_count"] == 1
    assert outputs["metrics"]["alert_count"] == 1
    assert outputs["metrics"]["trust_policy_loaded"] is False
    assert outputs["metrics"]["alert_policy_loaded"] is False
