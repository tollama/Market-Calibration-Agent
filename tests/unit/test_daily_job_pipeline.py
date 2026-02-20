import pipelines.daily_job as daily_job


def test_run_daily_job_stage_order_and_success_payload_shape() -> None:
    result = daily_job.run_daily_job(run_id="daily-test-stage-order")

    expected_order = list(daily_job.DAILY_STAGE_NAMES)
    assert result["run_id"] == "daily-test-stage-order"
    assert result["success"] is True
    assert result["stage_order"] == expected_order
    assert [stage["name"] for stage in result["stages"]] == expected_order

    for stage in result["stages"]:
        assert set(stage) == {"name", "status", "output", "error"}
        assert stage["status"] == "success"
        assert stage["error"] is None
        assert isinstance(stage["output"], dict)
        assert any(key.endswith("_count") for key in stage["output"])

    outputs = {stage["name"]: stage["output"] for stage in result["stages"]}
    assert outputs["discover"]["market_count"] == 0
    assert outputs["cutoff"]["snapshot_count"] == 0
    assert outputs["features"]["feature_count"] == 0


def test_run_daily_job_monkeypatches_cutoff_and_features_handlers(monkeypatch) -> None:
    calls: list[str] = []

    def fake_cutoff_handler(context):
        calls.append("cutoff")
        context.state["cutoff_snapshots"] = [{"market_id": "m1"}]
        return {"snapshot_count": 1}

    def fake_feature_handler(context):
        calls.append("features")
        context.state["feature_rows"] = [{"market_id": "m1"}, {"market_id": "m2"}]
        return {"feature_count": 2}

    monkeypatch.setattr(daily_job, "stage_build_cutoff_snapshots", fake_cutoff_handler)
    monkeypatch.setattr(daily_job, "stage_build_features", fake_feature_handler)

    result = daily_job.run_daily_job(run_id="daily-test-monkeypatched-stages")
    outputs = {stage["name"]: stage["output"] for stage in result["stages"]}

    assert result["success"] is True
    assert calls == ["cutoff", "features"]
    assert outputs["cutoff"]["snapshot_count"] == 1
    assert outputs["cutoff"]["market_count"] == 0
    assert outputs["features"]["feature_count"] == 2
    assert outputs["features"]["market_count"] == 0
