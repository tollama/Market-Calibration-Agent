import pipelines.daily_job as daily_job


def test_daily_job_optional_resolved_dataset_and_model_flow(tmp_path) -> None:
    def feature_fn(context):
        context.state["feature_frame"] = None
        context.state["feature_rows"] = [
            {
                "market_id": "m1",
                "question": "Will Candidate A win the election?",
                "category": "Politics",
                "ts": "2026-01-01T00:00:00Z",
                "resolution_ts": "2026-01-01T03:00:00Z",
                "label_status": "RESOLVED_TRUE",
                "p_yes": 0.45,
                "returns": 0.05,
                "vol": 0.02,
                "volume_velocity": 0.1,
                "oi_change": 0.02,
                "tte_seconds": 7200,
                "liquidity_bucket": "HIGH",
                "liquidity_bucket_id": 2,
            },
            {
                "market_id": "m1",
                "question": "Will Candidate A win the election?",
                "category": "Politics",
                "ts": "2026-01-01T02:00:00Z",
                "resolution_ts": "2026-01-01T03:00:00Z",
                "label_status": "RESOLVED_TRUE",
                "p_yes": 0.62,
                "returns": 0.04,
                "vol": 0.03,
                "volume_velocity": 0.12,
                "oi_change": 0.03,
                "tte_seconds": 3600,
                "liquidity_bucket": "HIGH",
                "liquidity_bucket_id": 2,
            },
            {
                "market_id": "m2",
                "question": "Will Team X win tonight?",
                "category": "Sports",
                "ts": "2026-01-01T00:00:00Z",
                "resolution_ts": "2026-01-01T04:00:00Z",
                "label_status": "RESOLVED_FALSE",
                "p_yes": 0.58,
                "returns": -0.03,
                "vol": 0.02,
                "volume_velocity": 0.08,
                "oi_change": -0.01,
                "tte_seconds": 10800,
                "liquidity_bucket": "LOW",
                "liquidity_bucket_id": 0,
            },
            {
                "market_id": "m2",
                "question": "Will Team X win tonight?",
                "category": "Sports",
                "ts": "2026-01-01T03:00:00Z",
                "resolution_ts": "2026-01-01T04:00:00Z",
                "label_status": "RESOLVED_FALSE",
                "p_yes": 0.49,
                "returns": -0.02,
                "vol": 0.02,
                "volume_velocity": 0.05,
                "oi_change": -0.02,
                "tte_seconds": 3600,
                "liquidity_bucket": "LOW",
                "liquidity_bucket_id": 0,
            },
        ]
        context.state["features"] = context.state["feature_rows"]
        return {"feature_count": 4}

    result = daily_job.run_daily_job(
        state={
            "market_ids": ["m1", "m2"],
            "feature_fn": feature_fn,
            "build_resolved_dataset": True,
            "train_resolved_model": True,
            "backtest_report_dir": str(tmp_path / "report"),
            "continue_on_stage_failure": True,
        },
        continue_on_stage_failure=True,
    )

    outputs = {stage["name"]: stage["output"] for stage in result["stages"]}
    assert outputs["features"]["resolved_dataset_count"] >= 2
    assert outputs["metrics"]["resolved_model_rows"] >= 2
