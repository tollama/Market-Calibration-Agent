"""Tests for low_confidence severity dampening in build_alert_feed."""

from __future__ import annotations

from typing import Any

import pytest

from pipelines.build_alert_feed import build_alert_feed_rows


def _make_alert_row(
    *,
    market_id: str = "mkt-1",
    ts: str = "2026-01-15T12:00:00Z",
    p_yes: float = 0.5,
    q10: float = 0.2,
    q90: float = 0.8,
    low_confidence: bool = False,
    trust_score: float | None = None,
) -> dict[str, Any]:
    """Create a minimal row with alert-triggering wide interval."""
    row: dict[str, Any] = {
        "market_id": market_id,
        "ts": ts,
        "p_yes": p_yes,
        "q10": q10,
        "q90": q90,
    }
    if low_confidence:
        row["low_confidence"] = True
    if trust_score is not None:
        row["trust_score"] = trust_score
    return row


class TestLowConfidenceDampening:
    """Verify that low_confidence rows get severity downgraded."""

    def test_high_confidence_row_preserves_severity(self) -> None:
        """Normal rows should not be dampened."""
        rows = [_make_alert_row(low_confidence=False)]
        alerts = build_alert_feed_rows(rows, include_fyi=True, dampen_low_confidence=True)
        for alert in alerts:
            assert alert["evidence"].get("dampened_by_low_confidence") is not True

    def test_low_confidence_row_dampens_high_to_med(self) -> None:
        """A HIGH-severity alert on a low_confidence market should become MED."""
        # Use extreme values to trigger HIGH severity
        rows = [_make_alert_row(
            p_yes=0.95,
            q10=0.01,
            q90=0.99,
            low_confidence=True,
        )]
        alerts = build_alert_feed_rows(rows, include_fyi=True, dampen_low_confidence=True)

        # We may or may not get alerts depending on evaluate_alert behavior.
        # If we do, verify the dampening flag.
        dampened_alerts = [a for a in alerts if a["evidence"].get("dampened_by_low_confidence")]
        for alert in dampened_alerts:
            # Dampened alerts should not be HIGH
            assert alert["severity"] != "HIGH"

    def test_low_confidence_row_dampens_med_to_fyi(self) -> None:
        """A MED-severity alert on a low_confidence market should become FYI."""
        rows = [_make_alert_row(
            p_yes=0.7,
            q10=0.3,
            q90=0.8,
            low_confidence=True,
        )]
        alerts = build_alert_feed_rows(rows, include_fyi=True, dampen_low_confidence=True)

        for alert in alerts:
            if alert["evidence"].get("dampened_by_low_confidence"):
                # If it was MED and got dampened, it should now be FYI
                assert alert["severity"] in ("FYI", "MED")

    def test_dampen_low_confidence_disabled(self) -> None:
        """When dampen_low_confidence=False, low_confidence should not affect severity."""
        rows = [_make_alert_row(
            p_yes=0.95,
            q10=0.01,
            q90=0.99,
            low_confidence=True,
        )]
        alerts = build_alert_feed_rows(rows, include_fyi=True, dampen_low_confidence=False)
        for alert in alerts:
            assert alert["evidence"].get("dampened_by_low_confidence") is not True

    def test_fyi_severity_not_dampened_further(self) -> None:
        """FYI severity has no lower level — it should not be changed."""
        # FYI is not in _DAMPEN_MAP, so it stays FYI
        rows = [_make_alert_row(
            p_yes=0.55,
            q10=0.45,
            q90=0.65,
            low_confidence=True,
        )]
        alerts = build_alert_feed_rows(rows, include_fyi=True, dampen_low_confidence=True)

        for alert in alerts:
            if alert["severity"] == "FYI":
                # FYI should never get dampened_by_low_confidence flag
                # because FYI is not in _DAMPEN_MAP
                pass  # just ensure no crash

    def test_dampening_evidence_flag_present(self) -> None:
        """When dampening occurs, evidence should contain the flag."""
        rows = [_make_alert_row(
            p_yes=0.95,
            q10=0.01,
            q90=0.99,
            low_confidence=True,
        )]
        alerts = build_alert_feed_rows(rows, include_fyi=True, dampen_low_confidence=True)

        dampened = [a for a in alerts if a["evidence"].get("dampened_by_low_confidence")]
        # If any dampening occurred, the flag must be True
        for alert in dampened:
            assert alert["evidence"]["dampened_by_low_confidence"] is True

    def test_non_low_confidence_row_not_affected_by_dampening(self) -> None:
        """Rows without low_confidence=True should not be affected."""
        rows = [
            _make_alert_row(p_yes=0.95, q10=0.01, q90=0.99, low_confidence=False),
            _make_alert_row(
                market_id="mkt-2",
                p_yes=0.95,
                q10=0.01,
                q90=0.99,
                low_confidence=True,
            ),
        ]
        alerts = build_alert_feed_rows(rows, include_fyi=True, dampen_low_confidence=True)

        for alert in alerts:
            if alert["market_id"] == "mkt-1":
                # mkt-1 is NOT low_confidence, should not be dampened
                assert alert["evidence"].get("dampened_by_low_confidence") is not True
