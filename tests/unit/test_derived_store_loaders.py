from __future__ import annotations

import json

from api.dependencies import LocalDerivedStore


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_scoreboard_prefers_direct_file_over_partitions(tmp_path) -> None:
    derived = tmp_path / "derived"
    _write_json(
        derived / "metrics" / "scoreboard.json",
        [
            {
                "market_id": "direct",
                "window": "90d",
                "as_of": "2026-02-20T00:00:00Z",
            }
        ],
    )
    _write_json(
        derived / "metrics" / "dt=2026-02-20" / "scoreboard.json",
        [
            {
                "market_id": "partition",
                "window": "90d",
                "as_of": "2026-02-21T00:00:00Z",
            }
        ],
    )

    store = LocalDerivedStore(derived_root=derived)
    items = store.load_scoreboard(window="90d")

    assert [item["market_id"] for item in items] == ["direct"]


def test_load_scoreboard_scans_partitions_when_direct_missing(tmp_path) -> None:
    derived = tmp_path / "derived"
    _write_json(
        derived / "metrics" / "dt=2026-02-19" / "scoreboard.json",
        [
            {
                "market_id": "old",
                "window": "90d",
                "as_of": "2026-02-19T10:00:00Z",
            }
        ],
    )
    _write_json(
        derived / "metrics" / "dt=2026-02-20" / "scoreboard.json",
        [
            {
                "market_id": "new",
                "window": "90d",
                "as_of": "2026-02-20T10:00:00Z",
            }
        ],
    )
    _write_json(
        derived / "metrics" / "dt=2026-02-21" / "scoreboard.json",
        [
            {
                "market_id": "other-window",
                "window": "30d",
                "as_of": "2026-02-21T10:00:00Z",
            }
        ],
    )

    store = LocalDerivedStore(derived_root=derived)
    items = store.load_scoreboard(window="90d")

    assert [item["market_id"] for item in items] == ["new", "old"]


def test_load_alerts_prefers_direct_file_over_partitions(tmp_path) -> None:
    derived = tmp_path / "derived"
    _write_json(
        derived / "alerts" / "alerts.json",
        [
            {
                "alert_id": "direct",
                "market_id": "mkt-1",
                "ts": "2026-02-20T12:00:00Z",
            }
        ],
    )
    _write_json(
        derived / "alerts" / "dt=2026-02-20" / "alerts.json",
        [
            {
                "alert_id": "partition",
                "market_id": "mkt-2",
                "ts": "2026-02-21T12:00:00Z",
            }
        ],
    )

    store = LocalDerivedStore(derived_root=derived)
    items, total = store.load_alerts(since=None, limit=10, offset=0)

    assert total == 1
    assert [item["alert_id"] for item in items] == ["direct"]


def test_load_alerts_scans_partitions_with_dedup_and_stable_order(tmp_path) -> None:
    derived = tmp_path / "derived"
    _write_json(
        derived / "alerts" / "dt=2026-02-20" / "alerts.json",
        [
            {
                "alert_id": "a-dup",
                "market_id": "mkt-1",
                "ts": "2026-02-20T12:00:00Z",
                "severity": "HIGH",
            },
            {
                "market_id": "mkt-2",
                "ts": "2026-02-20T11:00:00Z",
                "severity": "HIGH",
            },
            {
                "alert_id": "a-tie-new",
                "market_id": "mkt-3",
                "ts": "2026-02-20T10:00:00Z",
            },
        ],
    )
    _write_json(
        derived / "alerts" / "dt=2026-02-19" / "alerts.json",
        [
            {
                "alert_id": "a-dup",
                "market_id": "mkt-1",
                "ts": "2026-02-20T09:00:00Z",
                "severity": "FYI",
            },
            {
                "market_id": "mkt-2",
                "ts": "2026-02-20T11:00:00Z",
                "severity": "FYI",
            },
            {
                "alert_id": "a-tie-old",
                "market_id": "mkt-4",
                "ts": "2026-02-20T10:00:00Z",
            },
        ],
    )

    store = LocalDerivedStore(derived_root=derived)
    items, total = store.load_alerts(since=None, limit=10, offset=0)

    assert total == 4
    assert items[0]["alert_id"] == "a-dup"
    assert items[1]["market_id"] == "mkt-2"
    assert items[1]["severity"] == "HIGH"
    assert [items[2]["alert_id"], items[3]["alert_id"]] == ["a-tie-new", "a-tie-old"]
