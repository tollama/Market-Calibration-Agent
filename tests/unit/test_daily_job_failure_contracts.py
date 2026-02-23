import pytest

import pipelines.daily_job as daily_job
from pipelines.common import PipelineRunContext, PipelineState


def test_run_daily_job_recoverable_stage_failure_continues_by_default(monkeypatch) -> None:
    def seeded_discover(context):
        context.state["market_ids"] = ["m1"]
        return {"market_count": 1}

    def recoverable_features(context):
        return {
            "stage": "features",
            "status": "failed",
            "reason": "optional feature sink unavailable",
            "failure": {
                "source": "pipeline",
                "message": "optional feature sink unavailable",
                "recoverable": True,
            },
        }

    def publish_hook(context):
        context.state["published_records"] = [{"market_id": "m1"}]
        return {"hook": "publish"}

    monkeypatch.setattr(daily_job, "_stage_discover", seeded_discover)
    monkeypatch.setattr(daily_job, "_stage_features", recoverable_features)
    monkeypatch.setattr(daily_job, "_stage_publish", publish_hook)

    result = daily_job.run_daily_job(run_id="daily-recoverable-fail-continues")

    feature_stage = next(stage for stage in result["stages"] if stage["name"] == "features")
    publish_stage = next(stage for stage in result["stages"] if stage["name"] == "publish")

    assert result["success"] is False
    assert result["stage_order"] == list(daily_job.DAILY_STAGE_NAMES)
    assert feature_stage["status"] == "failed"
    assert feature_stage["output"]["failure"]["recoverable"] is True
    assert feature_stage["output"]["failure"]["classification"] == "recoverable"
    assert feature_stage["output"].get("stopped") is None
    assert publish_stage["status"] == "success"
    assert publish_stage["output"].get("hook") == "publish"
    assert "failure" in result
    assert result["failure"]["classification"] == "recoverable"
    assert result["failure"]["recoverable"] is True
    assert result.get("stopped_early") is None


def test_run_daily_job_critical_stage_failure_marks_stopped_and_fail_reason(
    monkeypatch,
) -> None:
    def seeded_discover(context):
        context.state["market_ids"] = ["m1"]
        return {"market_count": 1}

    def critical_features(context):
        return {
            "stage": "features",
            "status": "failed",
            "reason": "mandatory feature dependency missing",
            "failure": {
                "source": "stage",
                "message": "mandatory feature dependency missing",
                "recoverable": False,
            },
        }

    monkeypatch.setattr(daily_job, "_stage_discover", seeded_discover)
    monkeypatch.setattr(daily_job, "_stage_features", critical_features)

    result = daily_job.run_daily_job(run_id="daily-critical-fail-stops")

    feature_stage = next(stage for stage in result["stages"] if stage["name"] == "features")
    assert result["success"] is False
    assert result["stage_order"] == ["discover", "ingest", "normalize", "snapshots", "cutoff", "features"]
    assert feature_stage["status"] == "failed"
    assert feature_stage["output"]["stopped"] is True
    assert feature_stage["output"]["stop_condition"] == "continue_on_stage_failure=false"
    assert feature_stage["output"]["failure"]["classification"] == "critical"
    assert result["failure"]["stage"] == "features"
    assert result["failure"]["reason"] == "mandatory feature dependency missing"
    assert result["stopped_early"] is True
    assert result["stopped_on_stage"] == "features"


def test_pipeline_run_context_state_contract_rejects_invalid_state_type() -> None:
    with pytest.raises(TypeError):
        PipelineRunContext(run_id="bad-state", state=[])


def test_pipeline_state_setitem_rejects_non_string_key() -> None:
    state = PipelineState()
    with pytest.raises(TypeError):
        state[123] = "bad"
