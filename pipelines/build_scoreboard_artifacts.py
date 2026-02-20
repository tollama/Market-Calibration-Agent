"""Build scoreboard rows and write scoreboard artifacts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from calibration.metrics import segment_metrics, summarize_metrics
from calibration.trust_score import compute_trust_components, compute_trust_score
from storage.writers import ParquetWriter, normalize_dt

_REQUIRED_ROW_KEYS = ("pred", "label", "market_id", "liquidity_bucket", "category")
_TRUST_COMPONENT_DEFAULTS: dict[str, float] = {
    "liquidity_depth": 0.5,
    "stability": 0.5,
    "question_quality": 0.5,
    "manipulation_suspect": 0.5,
}


def build_scoreboard_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Build per-market scoreboard rows plus global/segment summary metrics."""
    normalized_rows = _normalize_rows(rows)
    preds = [row["pred"] for row in normalized_rows]
    labels = [row["label"] for row in normalized_rows]

    summary_metrics: dict[str, object] = {
        "global": summarize_metrics(preds, labels),
        "by_category": segment_metrics(normalized_rows, "category"),
        "by_liquidity_bucket": segment_metrics(normalized_rows, "liquidity_bucket"),
    }

    market_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in normalized_rows:
        market_rows[str(row["market_id"])].append(row)

    score_rows: list[dict[str, object]] = []
    for market_id in sorted(market_rows):
        grouped = market_rows[market_id]
        category = grouped[0]["category"]
        liquidity_bucket = grouped[0]["liquidity_bucket"]
        _validate_market_segment_consistency(
            market_id=market_id,
            grouped_rows=grouped,
            category=category,
            liquidity_bucket=liquidity_bucket,
        )

        market_preds = [row["pred"] for row in grouped]
        market_labels = [row["label"] for row in grouped]
        market_metrics = summarize_metrics(market_preds, market_labels)

        averaged_components = _average_trust_components(grouped)
        trust_score = compute_trust_score(averaged_components)

        score_rows.append(
            {
                "market_id": market_id,
                "category": category,
                "liquidity_bucket": liquidity_bucket,
                "sample_size": len(grouped),
                "trust_score": trust_score,
                "brier": market_metrics["brier"],
                "log_loss": market_metrics["log_loss"],
                "ece": market_metrics["ece"],
                "liquidity_depth": averaged_components["liquidity_depth"],
                "stability": averaged_components["stability"],
                "question_quality": averaged_components["question_quality"],
                "manipulation_suspect": averaged_components["manipulation_suspect"],
            }
        )

    score_rows.sort(key=lambda row: (-float(row["trust_score"]), str(row["market_id"])))
    return score_rows, summary_metrics


def render_scoreboard_markdown(
    score_rows: Sequence[Mapping[str, object]],
    summary_metrics: Mapping[str, object],
) -> str:
    """Render a markdown report for scoreboard metrics and market rows."""
    global_metrics = summary_metrics.get("global")
    if isinstance(global_metrics, Mapping):
        global_section = global_metrics
    else:
        global_section = {}

    lines: list[str] = [
        "# Scoreboard Report",
        "",
        "## Global Metrics",
        f"- Market count: {len(score_rows)}",
        f"- Brier: {_format_float(global_section.get('brier'))}",
        f"- Log Loss: {_format_float(global_section.get('log_loss'))}",
        f"- ECE: {_format_float(global_section.get('ece'))}",
        "",
    ]

    lines.extend(
        _render_segment_table(
            "## Segment Metrics (Category)",
            summary_metrics.get("by_category"),
        )
    )
    lines.append("")
    lines.extend(
        _render_segment_table(
            "## Segment Metrics (Liquidity Bucket)",
            summary_metrics.get("by_liquidity_bucket"),
        )
    )
    lines.append("")
    lines.append("## Market Scoreboard")

    if not score_rows:
        lines.append("- No markets.")
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            "| Market ID | Category | Liquidity Bucket | N | Trust Score | Brier | Log Loss | ECE |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in score_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("market_id", "")),
                    str(row.get("category", "")),
                    str(row.get("liquidity_bucket", "")),
                    str(row.get("sample_size", "")),
                    _format_float(row.get("trust_score"), digits=2),
                    _format_float(row.get("brier")),
                    _format_float(row.get("log_loss")),
                    _format_float(row.get("ece")),
                ]
            )
            + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_scoreboard_artifacts(
    score_rows: Sequence[Mapping[str, object]],
    summary_metrics: Mapping[str, object],
    *,
    root: str | Path,
    dt: object = None,
) -> tuple[Path, Path]:
    """
    Write scoreboard parquet and markdown artifacts under derived/.

    Parquet path: derived/metrics/dt=YYYY-MM-DD/scoreboard.parquet
    Markdown path: derived/reports/scoreboard-YYYY-MM-DD.md
    """
    root_path = Path(root)
    normalized_dt = normalize_dt(dt)

    parquet_writer = ParquetWriter(root_path)
    parquet_path = parquet_writer.write(
        score_rows,
        dataset="metrics",
        dt=normalized_dt,
        filename="scoreboard.parquet",
    )

    markdown = render_scoreboard_markdown(score_rows, summary_metrics)
    report_path = root_path / "derived" / "reports" / f"scoreboard-{normalized_dt}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown, encoding="utf-8")

    return parquet_path, report_path


def _normalize_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if not rows:
        raise ValueError("rows must be non-empty")

    normalized_rows: list[dict[str, object]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"rows[{idx}] must be a mapping")
        copied = dict(row)
        for required_key in _REQUIRED_ROW_KEYS:
            if required_key not in copied:
                raise ValueError(f"rows[{idx}] missing required key: {required_key}")
        normalized_rows.append(copied)
    return normalized_rows


def _average_trust_components(rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    summed = {
        "liquidity_depth": 0.0,
        "stability": 0.0,
        "question_quality": 0.0,
        "manipulation_suspect": 0.0,
    }

    for row in rows:
        components = compute_trust_components(
            liquidity_depth=row.get(
                "liquidity_depth",
                _TRUST_COMPONENT_DEFAULTS["liquidity_depth"],
            ),
            stability=row.get("stability", _TRUST_COMPONENT_DEFAULTS["stability"]),
            question_quality=row.get(
                "question_quality",
                _TRUST_COMPONENT_DEFAULTS["question_quality"],
            ),
            manipulation_suspect=row.get(
                "manipulation_suspect",
                _TRUST_COMPONENT_DEFAULTS["manipulation_suspect"],
            ),
        )
        for key in summed:
            summed[key] += components[key]

    count = float(len(rows))
    return {key: summed[key] / count for key in summed}


def _validate_market_segment_consistency(
    *,
    market_id: str,
    grouped_rows: Sequence[Mapping[str, object]],
    category: object,
    liquidity_bucket: object,
) -> None:
    for idx, row in enumerate(grouped_rows):
        if row["category"] != category:
            raise ValueError(
                f"market_id {market_id!r} has mixed category values; mismatch at row {idx}"
            )
        if row["liquidity_bucket"] != liquidity_bucket:
            raise ValueError(
                "market_id "
                f"{market_id!r} has mixed liquidity_bucket values; mismatch at row {idx}"
            )


def _render_segment_table(title: str, payload: object) -> list[str]:
    lines = [title]
    if not isinstance(payload, Mapping) or len(payload) == 0:
        lines.append("- No segment rows.")
        return lines

    lines.extend(
        [
            "| Segment | Brier | Log Loss | ECE |",
            "| --- | ---: | ---: | ---: |",
        ]
    )

    sorted_keys = sorted(payload.keys(), key=lambda key: str(key))
    for key in sorted_keys:
        metrics = payload[key]
        if not isinstance(metrics, Mapping):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(key),
                    _format_float(metrics.get("brier")),
                    _format_float(metrics.get("log_loss")),
                    _format_float(metrics.get("ece")),
                ]
            )
            + " |"
        )
    return lines


def _format_float(value: Any, digits: int = 6) -> str:
    if isinstance(value, bool):
        return "NA"
    if isinstance(value, (float, int)):
        return f"{float(value):.{digits}f}"
    return "NA"


__all__ = [
    "build_scoreboard_rows",
    "render_scoreboard_markdown",
    "write_scoreboard_artifacts",
]
