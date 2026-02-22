import pipelines.daily_job as daily_job
from pipelines.common import load_checkpoint


def test_run_daily_job_retries_stage_then_succeeds(monkeypatch) -> None:
    attempts = {"discover": 0}

    def flaky_discover(context):
        attempts["discover"] += 1
        if attempts["discover"] == 1:
            raise RuntimeError("transient discover failure")
        context.state["market_ids"] = []
        return {"stage": "discover", "market_count": 0}

    monkeypatch.setattr(daily_job, "_stage_discover", flaky_discover)

    result = daily_job.run_daily_job(
        run_id="daily-retry-success",
        stage_retry_limit=1,
    )

    discover_stage = next(stage for stage in result["stages"] if stage["name"] == "discover")

    assert attempts["discover"] == 2
    assert result["success"] is True
    assert result["stage_order"] == list(daily_job.DAILY_STAGE_NAMES)
    assert discover_stage["status"] == "success"
    assert discover_stage["error"] is None
    assert discover_stage["output"]["retry_count"] == 1


def test_run_daily_job_continue_on_stage_failure_with_checkpoint(monkeypatch, tmp_path) -> None:
    attempts = {"normalize": 0}

    def always_fail_normalize(_context):
        attempts["normalize"] += 1
        raise RuntimeError("normalize failed")

    monkeypatch.setattr(daily_job, "_stage_normalize", always_fail_normalize)

    checkpoint_path = tmp_path / "daily-retry-continue-checkpoint.json"
    result = daily_job.run_daily_job(
        run_id="daily-retry-continue",
        checkpoint_path=str(checkpoint_path),
        stage_retry_limit=2,
        continue_on_stage_failure=True,
    )

    normalize_stage = next(stage for stage in result["stages"] if stage["name"] == "normalize")
    publish_stage = next(stage for stage in result["stages"] if stage["name"] == "publish")

    assert attempts["normalize"] == 3
    assert result["success"] is False
    assert result["stage_order"] == list(daily_job.DAILY_STAGE_NAMES)
    assert normalize_stage["status"] == "failed"
    assert normalize_stage["output"]["retry_count"] == 2
    assert "normalize failed" in normalize_stage["error"]
    assert publish_stage["status"] == "success"

    checkpoint_payload = load_checkpoint(str(checkpoint_path))
    assert checkpoint_payload["run_id"] == "daily-retry-continue"
    assert set(checkpoint_payload["stages"]) == set(daily_job.DAILY_STAGE_NAMES)
    assert checkpoint_payload["stages"]["normalize"]["status"] == "failed"
    assert checkpoint_payload["stages"]["normalize"]["output"]["retry_count"] == 2
    assert checkpoint_payload["stages"]["publish"]["status"] == "success"


def test_run_daily_job_treats_explicit_failed_stage_output_as_hard_stop(monkeypatch) -> None:
    attempts = {"ingest": 0}

    def failing_ingest(context):
        attempts["ingest"] += 1
        context.state["market_ids"] = ["m1"]
        return {
            "stage": "ingest",
            "status": "failed",
            "reason": "malformed ingest payload",
            "failure": {
                "source": "stage",
                "message": "malformed ingest payload",
            },
        }

    monkeypatch.setattr(daily_job, "_stage_ingest", failing_ingest)

    result = daily_job.run_daily_job(run_id="daily-explicit-fail-stop")

    ingest_stage = next(stage for stage in result["stages"] if stage["name"] == "ingest")

    assert attempts["ingest"] == 1
    assert result["success"] is False
    assert result["stage_order"] == ["discover", "ingest"]
    assert ingest_stage["status"] == "failed"
    assert ingest_stage["output"].get("status") == "failed"
    assert ingest_stage["output"].get("reason") == "malformed ingest payload"
    assert ingest_stage["output"].get("stopped") is True
    assert ingest_stage["output"].get("stop_condition") == "continue_on_stage_failure=false"


def test_run_daily_job_uses_recovery_policy_with_continuable_explicit_stage_failure(monkeypatch) -> None:
    attempts = {"features": 0}

    def failing_features(context):
        attempts["features"] += 1
        return {
            "stage": "features",
            "status": "failed",
            "reason": "optional feature sink unavailable",
            "failure": {
                "source": "stage",
                "message": "optional feature sink unavailable",
            },
        }

    def publish_hook(context):
        context.state["published_records"] = [{"market_id": "m1"}]
        return {"hook": "publish"}

    def seeded_discover(context):
        context.state["market_ids"] = ["m1", "m2"]
        return {"market_count": 2}

    monkeypatch.setattr(daily_job, "_stage_discover", seeded_discover)
    monkeypatch.setattr(daily_job, "_stage_features", failing_features)
    monkeypatch.setattr(daily_job, "_stage_publish", publish_hook)

    result = daily_job.run_daily_job(
        run_id="daily-explicit-fail-continue",
        continue_on_stage_failure=True,
    )

    features_stage = next(stage for stage in result["stages"] if stage["name"] == "features")
    publish_stage = next(stage for stage in result["stages"] if stage["name"] == "publish")

    assert attempts["features"] == 1
    assert result["success"] is False
    assert result["stage_order"] == list(daily_job.DAILY_STAGE_NAMES)
    assert features_stage["status"] == "failed"
    assert publish_stage["status"] == "success"
    assert publish_stage["output"].get("hook") == "publish"
