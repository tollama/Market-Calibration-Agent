"""File-driven live market scanner for trained resolved models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from features.external_enrichment import ExternalEnrichmentConfig, enrich_with_external_features
from features.market_templates import build_market_template_features
from features.trust_snapshot_ingest import TrustSnapshotConfig, enrich_with_trust_snapshots
from pipelines.train_resolved_model import ResolvedLinearModel


def scan_live_markets(
    rows: pd.DataFrame,
    *,
    model: ResolvedLinearModel,
    news_csv_path: str | None = None,
    polls_csv_path: str | None = None,
    news_trust_snapshot: str | None = None,
    financial_trust_snapshot: str | None = None,
    symbol_map_path: str | None = None,
    edge_threshold: float = 0.03,
) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()

    frame = rows.copy()
    if "market_prob" not in frame.columns and "p_yes" in frame.columns:
        frame["market_prob"] = pd.to_numeric(frame["p_yes"], errors="coerce")
    if "market_template" not in frame.columns:
        template_df = frame.apply(build_market_template_features, axis=1, result_type="expand")
        frame = pd.concat([frame, template_df], axis=1)
    if news_csv_path or polls_csv_path:
        snapshot_col = "snapshot_ts" if "snapshot_ts" in frame.columns else "ts"
        frame[snapshot_col] = frame.get(snapshot_col, frame.get("ts"))
        frame = enrich_with_external_features(
            frame,
            ExternalEnrichmentConfig(
                news_csv_path=news_csv_path,
                polls_csv_path=polls_csv_path,
                snapshot_time_col=snapshot_col,
            ),
        )
    if news_trust_snapshot or financial_trust_snapshot:
        frame = enrich_with_trust_snapshots(
            frame,
            TrustSnapshotConfig(
                news_snapshot_path=news_trust_snapshot,
                financial_snapshot_path=financial_trust_snapshot,
                symbol_map_path=symbol_map_path,
            ),
        )
    preds = model.predict_frame(frame)
    frame = pd.concat([frame.reset_index(drop=True), preds.reset_index(drop=True)], axis=1)
    frame["edge"] = frame["recalibrated_pred"] - frame["baseline_pred"]
    frame["abs_edge"] = frame["edge"].abs()
    spread = _numeric_series(frame, "spread", default=0.01).clip(lower=0.0)
    liquidity = _numeric_series(frame, "liquidity", fallback_key="volume_24h", default=0.0).clip(lower=0.0)
    news_term = _numeric_series(frame, "news_articles_24h", default=0.0).clip(lower=0.0)
    template_term = _numeric_series(frame, "template_confidence", default=0.0).clip(lower=0.0, upper=1.0)
    frame["ranking_score"] = frame["abs_edge"] * (1.0 + liquidity / (liquidity + 1000.0)) * (1.0 + news_term / 10.0) * (0.95 + 0.05 * template_term) * (1.0 - spread.clip(upper=0.25))
    frame["signal"] = "PASS"
    frame.loc[frame["edge"] >= float(edge_threshold), "signal"] = "LONG_YES"
    frame.loc[frame["edge"] <= -float(edge_threshold), "signal"] = "LONG_NO"
    return frame.sort_values(["ranking_score", "abs_edge"], ascending=False).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Score live snapshot rows with a trained resolved model")
    parser.add_argument("--input", required=True, help="input csv/parquet/jsonl path")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output", default="artifacts/live_scan.csv")
    parser.add_argument("--edge-threshold", type=float, default=0.03)
    parser.add_argument("--news-csv", default="")
    parser.add_argument("--polls-csv", default="")
    parser.add_argument("--news-trust-snapshot", default="", help="news trust snapshot JSONL path")
    parser.add_argument("--financial-trust-snapshot", default="", help="financial trust snapshot JSONL path")
    parser.add_argument("--symbol-map", default="", help="market template to symbol map YAML path")
    args = parser.parse_args()

    frame = _load_table(Path(args.input))
    model = ResolvedLinearModel.load(args.model_path)
    scanned = scan_live_markets(
        frame,
        model=model,
        news_csv_path=str(args.news_csv or "") or None,
        polls_csv_path=str(args.polls_csv or "") or None,
        news_trust_snapshot=str(args.news_trust_snapshot or "") or None,
        financial_trust_snapshot=str(args.financial_trust_snapshot or "") or None,
        symbol_map_path=str(args.symbol_map or "") or None,
        edge_threshold=float(args.edge_threshold),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    scanned.to_csv(output, index=False)
    print(json.dumps({"rows": len(scanned), "output": str(output)}, sort_keys=True))
    return 0


def _load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ValueError(f"Unsupported input format: {path}")


def _numeric_series(
    frame: pd.DataFrame,
    key: str,
    *,
    fallback_key: str | None = None,
    default: float,
) -> pd.Series:
    if key in frame.columns:
        source = frame[key]
    elif fallback_key is not None and fallback_key in frame.columns:
        source = frame[fallback_key]
    else:
        return pd.Series([default] * len(frame), index=frame.index, dtype=float)
    return pd.to_numeric(source, errors="coerce").fillna(default)


if __name__ == "__main__":
    raise SystemExit(main())
