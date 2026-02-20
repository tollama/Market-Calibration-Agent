import pipelines.daily_job as daily_job


def test_run_daily_job_default_end_to_end_glue_path(monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    def discover_with_seed_data(context):
        context.state["market_ids"] = ["mkt-1", "mkt-2"]
        context.state["root_path"] = str(tmp_path)
        context.state["raw_records"] = [
            {
                "market_id": "mkt-1",
                "ts": "2026-02-20T10:00:00Z",
                "cutoff_type": "T-24h",
                "cutoff_ts": "2026-02-20T12:00:00Z",
                "pred": 0.75,
                "label": 1,
                "liquidity_bucket": "high",
                "category": "sports",
                "p_yes": 0.75,
                "q10": 0.60,
                "q90": 0.85,
            },
            {
                "market_id": "mkt-2",
                "ts": "2026-02-20T10:05:00Z",
                "cutoff_type": "T-24h",
                "cutoff_ts": "2026-02-20T12:00:00Z",
                "pred": 0.35,
                "label": 0,
                "liquidity_bucket": "low",
                "category": "politics",
                "p_yes": 0.35,
                "q10": 0.20,
                "q90": 0.50,
            },
        ]
        context.state["registry_rows"] = [
            {"market_id": "mkt-1", "event_id": "evt-1", "status": "active"},
            {"market_id": "mkt-2", "event_id": "evt-2", "status": "active"},
        ]
        context.state["events"] = [
            {"market_id": "mkt-1", "event_id": "evt-1"},
            {"market_id": "mkt-2", "event_id": "evt-2"},
        ]
        return {"stage": "discover", "market_count": 2}

    def fake_link_registry_to_snapshots(snapshot_rows, registry_rows):
        calls.append("registry_linker")
        registry_by_market_id = {row["market_id"]: row for row in registry_rows}
        enriched_rows = []
        for row in snapshot_rows:
            enriched = dict(row)
            registry_row = registry_by_market_id.get(enriched.get("market_id"))
            if registry_row is not None:
                enriched["event_id"] = registry_row["event_id"]
                enriched["status"] = registry_row["status"]
            enriched_rows.append(enriched)
        return enriched_rows

    def fake_build_cutoff_snapshots(*, market_ids, source_rows, **_kwargs):
        calls.append("build_cutoff_snapshots")
        assert market_ids == ["mkt-1", "mkt-2"]
        assert len(source_rows) == 2
        assert all("event_id" in row for row in source_rows)
        return [dict(row) for row in source_rows]

    def fake_stage_build_features(context):
        calls.append("stage_build_features")
        context.state["feature_rows"] = [dict(row) for row in context.state["cutoff_snapshot_rows"]]
        return {"feature_count": len(context.state["feature_rows"])}

    def fake_build_scoreboard_rows(rows):
        calls.append("build_scoreboard_rows")
        assert len(rows) == 2
        assert all("event_id" in row for row in rows)
        score_rows = [{"market_id": row["market_id"], "trust_score": 0.99} for row in rows]
        summary_metrics = {"global": {"brier": 0.1, "log_loss": 0.2, "ece": 0.3}}
        return score_rows, summary_metrics

    def fake_build_alert_feed_rows(rows):
        calls.append("build_alert_feed_rows")
        assert len(rows) == 2
        return [{"alert_id": "alert-1", "market_id": "mkt-1", "severity": "HIGH"}]

    def fake_build_and_write_postmortems(events, *, root):
        calls.append("build_and_write_postmortems")
        assert root == str(tmp_path)
        return {
            "written_count": len(events),
            "skipped_count": 0,
            "output_paths": [f"{root}/{event['market_id']}.md" for event in events],
        }

    monkeypatch.setattr(daily_job, "_stage_discover", discover_with_seed_data)
    monkeypatch.setattr(daily_job, "link_registry_to_snapshots", fake_link_registry_to_snapshots)
    monkeypatch.setattr(daily_job, "build_cutoff_snapshots", fake_build_cutoff_snapshots)
    monkeypatch.setattr(daily_job, "stage_build_features", fake_stage_build_features)
    monkeypatch.setattr(daily_job, "build_scoreboard_rows", fake_build_scoreboard_rows)
    monkeypatch.setattr(daily_job, "build_alert_feed_rows", fake_build_alert_feed_rows)
    monkeypatch.setattr(daily_job, "build_and_write_postmortems", fake_build_and_write_postmortems)

    result = daily_job.run_daily_job(run_id="daily-end-to-end-glue")
    outputs = {stage["name"]: stage["output"] for stage in result["stages"]}

    assert result["success"] is True
    assert result["stage_order"] == list(daily_job.DAILY_STAGE_NAMES)
    assert calls == [
        "registry_linker",
        "build_cutoff_snapshots",
        "stage_build_features",
        "build_scoreboard_rows",
        "build_alert_feed_rows",
        "build_and_write_postmortems",
    ]

    assert outputs["ingest"]["market_count"] == 2
    assert outputs["ingest"]["raw_record_count"] == 2
    assert outputs["ingest"]["event_count"] == 2

    assert outputs["normalize"]["raw_record_count"] == 2
    assert outputs["normalize"]["normalized_record_count"] == 2

    assert outputs["snapshots"]["normalized_record_count"] == 2
    assert outputs["snapshots"]["registry_row_count"] == 2
    assert outputs["snapshots"]["snapshot_count"] == 2

    assert outputs["cutoff"]["market_count"] == 2
    assert outputs["cutoff"]["source_snapshot_count"] == 2
    assert outputs["cutoff"]["snapshot_count"] == 2

    assert outputs["features"]["market_count"] == 2
    assert outputs["features"]["feature_count"] == 2

    assert outputs["metrics"]["feature_count"] == 2
    assert outputs["metrics"]["metric_count"] == 2
    assert outputs["metrics"]["scoreboard_count"] == 2
    assert outputs["metrics"]["alert_count"] == 1

    assert outputs["publish"]["metric_count"] == 2
    assert outputs["publish"]["alert_count"] == 1
    assert outputs["publish"]["postmortem_written_count"] == 2
    assert outputs["publish"]["postmortem_skipped_count"] == 0
    assert outputs["publish"]["published_count"] == 2

    for stage in result["stages"]:
        assert any(key.endswith("_count") for key in stage["output"])
