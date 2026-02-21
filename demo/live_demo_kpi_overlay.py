from __future__ import annotations

import math
import re
from collections import defaultdict

import streamlit as st

# Text snippets adapted from artifacts/demo/live_demo_kpi_dashboard_spec.md
KPI_HINTS = {
    "nsm": "NSM (15m): fallback-adjusted quantile quality score. Higher is better.",
    "latency": "Latency uses forecast response meta.latency_ms first, then edge request timing.",
    "fallback": "Fallback rate = fallback_count / request_count. Reasons include too_few_points, baseline_only_liquidity_bucket, max_gap_exceeded, degradation_baseline_only, circuit_breaker_open, tollama_error:*, stale_if_error.",
}

_METRIC_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([0-9.eE+-]+)$")
_LABEL_RE = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)=\"([^\"]*)\"")


def _parse_labels(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    inner = raw.strip()[1:-1]
    return {k: v for k, v in _LABEL_RE.findall(inner)}


def _parse_metrics(metrics_text: str) -> list[tuple[str, dict[str, str], float]]:
    rows: list[tuple[str, dict[str, str], float]] = []
    for line in metrics_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _METRIC_RE.match(line)
        if not m:
            continue
        name, labels_raw, val = m.groups()
        try:
            value = float(val)
        except ValueError:
            continue
        rows.append((name, _parse_labels(labels_raw), value))
    return rows


def _histogram_quantile(q: float, buckets: list[tuple[float, float]]) -> float | None:
    if not buckets:
        return None
    buckets = sorted(buckets, key=lambda x: x[0])
    total = buckets[-1][1]
    if total <= 0:
        return None
    target = q * total
    prev_le = 0.0
    prev_count = 0.0
    for le, count in buckets:
        if count >= target:
            bucket_count = count - prev_count
            if bucket_count <= 0:
                return le
            frac = (target - prev_count) / bucket_count
            return prev_le + frac * (le - prev_le)
        prev_le, prev_count = le, count
    return buckets[-1][0]


def render_kpi_panel(metrics_text: str) -> None:
    rows = _parse_metrics(metrics_text)

    total_requests = 0.0
    fallback_total = 0.0
    fallback_reasons: dict[str, float] = defaultdict(float)
    latency_buckets: dict[float, float] = defaultdict(float)

    for name, labels, value in rows:
        if name == "tsfm_request_total":
            total_requests += value
        elif name == "tsfm_fallback_total":
            fallback_total += value
            fallback_reasons[labels.get("reason", "unknown")] += value
        elif name == "tsfm_request_latency_ms_bucket":
            le_raw = labels.get("le")
            if not le_raw or le_raw == "+Inf":
                continue
            try:
                le = float(le_raw)
            except ValueError:
                continue
            latency_buckets[le] += value

    fallback_rate = (fallback_total / total_requests) if total_requests > 0 else 0.0
    p50 = _histogram_quantile(0.50, list(latency_buckets.items()))
    p95 = _histogram_quantile(0.95, list(latency_buckets.items()))
    p99 = _histogram_quantile(0.99, list(latency_buckets.items()))

    st.markdown("### KPI Quick Panel")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Requests (total)", f"{int(total_requests)}")
    c2.metric("Fallback rate", f"{fallback_rate * 100:.1f}%")
    c3.metric("Latency p50 (ms)", "-" if p50 is None or math.isinf(p50) else f"{p50:.1f}")
    c4.metric("Latency p95/p99 (ms)", "-" if p95 is None or p99 is None else f"{p95:.1f} / {p99:.1f}")

    with st.expander("KPI Definitions (from demo KPI spec)", expanded=True):
        st.markdown(
            "- **North Star Metric (NSM)**: `max(0, 1 - pinball_mean / pinball_ref) * (1 - fallback_rate)`\n"
            "- **Pinball mean**: average of `pinball_q10`, `pinball_q50`, `pinball_q90`\n"
            "- **Fallback rate**: `fallback_count / request_count`\n"
            "- **Latency**: track p50, p95, p99"
        )
        st.caption(KPI_HINTS["nsm"])
        st.caption(KPI_HINTS["latency"])
        st.caption(KPI_HINTS["fallback"])

    st.markdown("#### Fallback Reasons")
    if fallback_reasons:
        rows = [
            {"reason": reason, "count": int(count), "share_%": round((count / fallback_total) * 100, 1) if fallback_total else 0.0}
            for reason, count in sorted(fallback_reasons.items(), key=lambda kv: kv[1], reverse=True)
        ]
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("No fallback events observed yet.")
