import pipelines.daily_job as daily_job
from pipelines.common import load_checkpoint


def test_run_daily_job_checkpoint_save_and_resume(monkeypatch, tmp_path) -> None:
    checkpoint_path = tmp_path / "daily-checkpoint.json"

    def fake_discover(context):
        context.state["market_ids"] = ["mkt-1"]
        return {"stage": "discover", "market_count": 1}

    def fake_cutoff_handler(context):
        context.state["cutoff_snapshots"] = [{"market_id": "mkt-1"}]
        return {"snapshot_count": 1}

    def fake_feature_handler(context):
        context.state["feature_rows"] = [{"market_id": "mkt-1"}]
        return {"feature_count": 1}

    monkeypatch.setattr(daily_job, "_stage_discover", fake_discover)
    monkeypatch.setattr(daily_job, "stage_build_cutoff_snapshots", fake_cutoff_handler)
    monkeypatch.setattr(daily_job, "stage_build_features", fake_feature_handler)

    first_result = daily_job.run_daily_job(
        run_id="daily-checkpoint-initial",
        checkpoint_path=str(checkpoint_path),
    )

    assert first_result["success"] is True
    assert checkpoint_path.exists()

    checkpoint_payload = load_checkpoint(str(checkpoint_path))
    assert checkpoint_payload["run_id"] == "daily-checkpoint-initial"
    assert set(checkpoint_payload["stages"]) == set(daily_job.DAILY_STAGE_NAMES)
    assert checkpoint_payload["stages"]["discover"]["status"] == "success"
    assert checkpoint_payload["stages"]["discover"]["output"]["market_count"] == 1

    def should_not_run(_context):
        raise AssertionError("resume should skip already-success stages")

    monkeypatch.setattr(daily_job, "_stage_discover", should_not_run)
    monkeypatch.setattr(daily_job, "stage_build_cutoff_snapshots", should_not_run)
    monkeypatch.setattr(daily_job, "stage_build_features", should_not_run)

    resumed_result = daily_job.run_daily_job(
        run_id="daily-checkpoint-resume",
        checkpoint_path=str(checkpoint_path),
        resume_from_checkpoint=True,
    )

    assert resumed_result["run_id"] == "daily-checkpoint-resume"
    assert resumed_result["success"] is True
    assert resumed_result["stage_order"] == list(daily_job.DAILY_STAGE_NAMES)
    assert resumed_result["checkpoint_path"] == str(checkpoint_path)
    assert resumed_result["resume_from_checkpoint"] is True
    assert resumed_result["stages"][0]["output"]["market_count"] == 1


def test_run_daily_job_backfill_metadata(monkeypatch) -> None:
    def fake_discover(context):
        assert context.state["backfill_days"] == 3
        context.state["market_ids"] = []
        return {"stage": "discover", "market_count": 0}

    monkeypatch.setattr(daily_job, "_stage_discover", fake_discover)

    result = daily_job.run_daily_job(run_id="daily-backfill", backfill_days=3)

    assert result["success"] is True
    assert result["backfill_days"] == 3
