import pipelines.daily_job as daily_job


def test_run_daily_job_uses_realtime_stage_hooks_from_context_state(monkeypatch) -> None:
    calls: list[str] = []

    def ingest_hook(context):
        calls.append("ingest")
        context.state["raw_records"] = [{"market_id": "m1"}, {"market_id": "m2"}]
        return {"hook": "ingest"}

    def cutoff_hook(context):
        calls.append("cutoff")
        context.state["cutoff_snapshots"] = [{"market_id": "m1"}]
        return {"hook": "cutoff"}

    def feature_hook(context):
        calls.append("features")
        context.state["feature_rows"] = [{"market_id": "m1"}, {"market_id": "m2"}]
        return {"hook": "features"}

    def metric_hook(context):
        calls.append("metrics")
        context.state["metrics"] = [{"market_id": "m1"}]
        return {"hook": "metrics"}

    def publish_hook(context):
        calls.append("publish")
        context.state["published_records"] = [{"market_id": "m1"}]
        return {"hook": "publish"}

    def discover_with_hooks(context):
        context.state["market_ids"] = ["m1", "m2"]
        context.state["ingest_fn"] = ingest_hook
        context.state["cutoff_fn"] = cutoff_hook
        context.state["feature_fn"] = feature_hook
        context.state["metric_fn"] = metric_hook
        context.state["publish_fn"] = publish_hook
        return {"stage": "discover", "market_count": 2}

    monkeypatch.setattr(daily_job, "_stage_discover", discover_with_hooks)

    result = daily_job.run_daily_job(run_id="daily-realtime-hooks")
    outputs = {stage["name"]: stage["output"] for stage in result["stages"]}

    assert result["success"] is True
    assert calls == ["ingest", "cutoff", "features", "metrics", "publish"]

    assert outputs["ingest"]["hook"] == "ingest"
    assert outputs["ingest"]["market_count"] == 2
    assert outputs["ingest"]["raw_record_count"] == 2

    assert outputs["cutoff"]["hook"] == "cutoff"
    assert outputs["cutoff"]["market_count"] == 2
    assert outputs["cutoff"]["snapshot_count"] == 1

    assert outputs["features"]["hook"] == "features"
    assert outputs["features"]["market_count"] == 2
    assert outputs["features"]["feature_count"] == 2

    assert outputs["metrics"]["hook"] == "metrics"
    assert outputs["metrics"]["feature_count"] == 2
    assert outputs["metrics"]["metric_count"] == 1

    assert outputs["publish"]["hook"] == "publish"
    assert outputs["publish"]["metric_count"] == 1
    assert outputs["publish"]["published_count"] == 1
