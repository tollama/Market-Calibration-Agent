from __future__ import annotations

import json

import pandas as pd

from scripts.generate_real_data_forecasting_pack import generate_real_data_pack


def test_generate_real_data_pack_writes_blocked_status_when_no_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = generate_real_data_pack(tmp_path / "real_data_pack", search_root=tmp_path)

    assert result["status"] == "blocked_no_local_resolved_data"
    assert (tmp_path / "real_data_pack" / "status.json").exists()
    assert (tmp_path / "real_data_pack" / "README.md").exists()


def test_generate_real_data_pack_uses_local_dataset_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data" / "derived" / "resolved"
    data_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = data_dir / "resolved_dataset.csv"
    pd.DataFrame(
        [
            {
                "market_id": f"m{idx}",
                "snapshot_ts": f"2026-01-01T0{idx}:00:00Z",
                "resolution_ts": f"2026-01-01T1{idx}:00:00Z",
                "label": 1 if idx % 2 == 0 else 0,
                "market_prob": 0.55 if idx % 2 == 0 else 0.45,
                "returns": 0.05 if idx % 2 == 0 else -0.05,
                "vol": 0.02 + idx * 0.001,
                "volume_velocity": 0.1 + idx * 0.01,
                "oi_change": 0.03 if idx % 2 == 0 else -0.02,
                "tte_seconds": 3600 + idx * 60,
                "horizon_hours": 24,
                "liquidity_bucket_id": idx % 3,
                "category": "politics" if idx % 2 == 0 else "sports",
                "liquidity_bucket": "HIGH" if idx % 2 == 0 else "LOW",
                "tte_bucket": "0-6h",
                "template_group": "politics" if idx % 2 == 0 else "sports",
                "market_template": "politics_candidate" if idx % 2 == 0 else "sports_match",
                "template_confidence": 0.85 if idx % 2 == 0 else 0.7,
                "template_entity_count": 2,
                "event_id": f"e{idx}",
            }
            for idx in range(12)
        ]
    ).to_csv(dataset_path, index=False)

    result = generate_real_data_pack(tmp_path / "real_data_pack", search_root=tmp_path)

    assert result["status"] == "ok"
    assert result["selected_input"]["kind"] == "dataset"
    assert (tmp_path / "real_data_pack" / "promotion_decision.json").exists()
    assert result["training_summary"]["sample_weight_scheme"] == "segment_balanced"
    assert result["training_summary"]["routing_strategy"] == "crypto_vs_rest"
    manifest = json.loads((tmp_path / "real_data_pack" / "status.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "ok"
    readme = (tmp_path / "real_data_pack" / "README.md").read_text(encoding="utf-8")
    assert "Promotion summary:" in readme
    assert "overall decision:" in readme


def test_generate_real_data_pack_accepts_explicit_input_path(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    explicit_path = tmp_path / "manual_resolved_dataset.csv"
    pd.DataFrame(
        [
            {
                "market_id": f"m{idx}",
                "snapshot_ts": f"2026-01-01T0{idx}:00:00Z",
                "resolution_ts": f"2026-01-01T1{idx}:00:00Z",
                "label": 1 if idx % 2 == 0 else 0,
                "market_prob": 0.55 if idx % 2 == 0 else 0.45,
                "returns": 0.05 if idx % 2 == 0 else -0.05,
                "vol": 0.02 + idx * 0.001,
                "volume_velocity": 0.1 + idx * 0.01,
                "oi_change": 0.03 if idx % 2 == 0 else -0.02,
                "tte_seconds": 3600 + idx * 60,
                "horizon_hours": 24,
                "liquidity_bucket_id": idx % 3,
                "category": "politics" if idx % 2 == 0 else "sports",
                "liquidity_bucket": "HIGH" if idx % 2 == 0 else "LOW",
                "tte_bucket": "0-6h",
                "template_group": "politics" if idx % 2 == 0 else "sports",
                "market_template": "politics_candidate" if idx % 2 == 0 else "sports_match",
                "template_confidence": 0.85 if idx % 2 == 0 else 0.7,
                "template_entity_count": 2,
                "event_id": f"e{idx}",
            }
            for idx in range(12)
        ]
    ).to_csv(explicit_path, index=False)

    result = generate_real_data_pack(
        tmp_path / "real_data_pack",
        search_root=tmp_path,
        input_path=explicit_path,
    )

    assert result["status"] == "ok"
    assert result["selected_input"]["path"] == str(explicit_path)


def test_generate_real_data_pack_excludes_test_markets_from_training_dataset(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    explicit_path = tmp_path / "manual_resolved_dataset.csv"
    rows = [
        {
            "market_id": f"real-{idx}",
            "snapshot_ts": f"2026-01-01T0{idx}:00:00Z",
            "resolution_ts": f"2026-01-01T1{idx}:00:00Z",
            "label": 1 if idx % 2 == 0 else 0,
            "market_prob": 0.55 if idx % 2 == 0 else 0.45,
            "returns": 0.05 if idx % 2 == 0 else -0.05,
            "vol": 0.02 + idx * 0.001,
            "volume_velocity": 0.1 + idx * 0.01,
            "oi_change": 0.03 if idx % 2 == 0 else -0.02,
            "tte_seconds": 3600 + idx * 60,
            "horizon_hours": 24,
            "liquidity_bucket_id": idx % 3,
            "category": "politics" if idx % 2 == 0 else "sports",
            "liquidity_bucket": "HIGH" if idx % 2 == 0 else "LOW",
            "tte_bucket": "6-24h",
            "template_group": "politics" if idx % 2 == 0 else "sports",
            "market_template": "politics_candidate" if idx % 2 == 0 else "sports_match",
            "template_confidence": 0.85 if idx % 2 == 0 else 0.7,
            "template_entity_count": 2,
            "event_id": f"e{idx}",
            "title": f"Real market {idx}",
        }
        for idx in range(12)
    ]
    rows.append(
        {
            "market_id": "test-1",
            "snapshot_ts": "2026-01-02T00:00:00Z",
            "resolution_ts": "2026-01-02T10:00:00Z",
            "label": 0,
            "market_prob": 0.5,
            "returns": 0.0,
            "vol": 0.01,
            "volume_velocity": 0.0,
            "oi_change": 0.0,
            "tte_seconds": 3600,
            "horizon_hours": 24,
            "liquidity_bucket_id": 0,
            "category": "test",
            "liquidity_bucket": "LOW",
            "tte_bucket": "6-24h",
            "template_group": "test",
            "market_template": "test_market",
            "template_confidence": 0.2,
            "template_entity_count": 0,
            "event_id": "e-test",
            "title": "Daily market",
        }
    )
    pd.DataFrame(rows).to_csv(explicit_path, index=False)

    result = generate_real_data_pack(
        tmp_path / "real_data_pack",
        search_root=tmp_path,
        input_path=explicit_path,
    )

    assert result["status"] == "ok"
    assert result["cleaning_summary"]["excluded_rows"] == 1
    assert result["dataset_summary"]["rows"] == 12


def test_generate_real_data_pack_excludes_non_standard_market_structures(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    explicit_path = tmp_path / "manual_resolved_dataset.csv"
    rows = [
        {
            "market_id": f"real-{idx}",
            "snapshot_ts": f"2026-01-01T0{idx}:00:00Z",
            "resolution_ts": f"2026-01-01T1{idx}:00:00Z",
            "label": 1 if idx % 2 == 0 else 0,
            "market_prob": 0.55 if idx % 2 == 0 else 0.45,
            "returns": 0.05 if idx % 2 == 0 else -0.05,
            "vol": 0.02 + idx * 0.001,
            "volume_velocity": 0.1 + idx * 0.01,
            "oi_change": 0.03 if idx % 2 == 0 else -0.02,
            "tte_seconds": 3600 + idx * 60,
            "horizon_hours": 24,
            "liquidity_bucket_id": idx % 3,
            "category": "us_current_affairs" if idx % 2 == 0 else "sports",
            "platform": "polymarket" if idx % 2 == 0 else "kalshi",
            "liquidity_bucket": "HIGH" if idx % 2 == 0 else "LOW",
            "tte_bucket": "6-24h",
            "template_group": "politics" if idx % 2 == 0 else "sports",
            "market_template": "politics_candidate" if idx % 2 == 0 else "sports_match",
            "template_confidence": 0.85 if idx % 2 == 0 else 0.7,
            "template_entity_count": 2,
            "event_id": f"e{idx}",
            "title": f"Real market {idx}",
            "slug": f"real-market-{idx}",
        }
        for idx in range(12)
    ]
    rows.append(
        {
            "market_id": "kalshi:KXMVECROSSCATEGORY-1",
            "snapshot_ts": "2026-01-02T00:00:00Z",
            "resolution_ts": "2026-01-02T10:00:00Z",
            "label": 1,
            "market_prob": 0.61,
            "returns": 0.0,
            "vol": 0.01,
            "volume_velocity": 0.0,
            "oi_change": 0.0,
            "tte_seconds": 3600,
            "horizon_hours": 24,
            "liquidity_bucket_id": 1,
            "category": "sports",
            "platform": "kalshi",
            "liquidity_bucket": "LOW",
            "tte_bucket": "6-24h",
            "template_group": "sports",
            "market_template": "sports_combo",
            "template_confidence": 0.4,
            "template_entity_count": 3,
            "event_id": "e-combo",
            "title": "yes Golden State,yes Portland,yes Over 230.5 points scored",
            "slug": "kxmvecrosscategory-1",
        }
    )
    pd.DataFrame(rows).to_csv(explicit_path, index=False)

    result = generate_real_data_pack(
        tmp_path / "real_data_pack",
        search_root=tmp_path,
        input_path=explicit_path,
    )

    assert result["status"] == "ok"
    assert result["cleaning_summary"]["excluded_rows"] == 1
    assert result["cleaning_summary"]["reasons"]["market_structure:non_standard"] == 1
    assert result["dataset_summary"]["rows"] == 12
    assert "canonical_categories" in result["dataset_summary"]
    assert "market_structures" in result["dataset_summary"]


def test_generate_real_data_pack_blocks_on_invalid_explicit_input(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    explicit_path = tmp_path / "bad_input.csv"
    pd.DataFrame([{"foo": 1, "bar": 2}]).to_csv(explicit_path, index=False)

    result = generate_real_data_pack(
        tmp_path / "real_data_pack",
        search_root=tmp_path,
        input_path=explicit_path,
    )

    assert result["status"] == "blocked_no_local_resolved_data"
    assert "accepted schema" in result["reason"].lower()
