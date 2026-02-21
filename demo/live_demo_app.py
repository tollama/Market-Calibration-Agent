from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd
import streamlit as st

API_BASE = os.getenv("LIVE_DEMO_API_BASE", "http://127.0.0.1:8000")
FORECAST_TOKEN = os.getenv("TSFM_FORECAST_API_TOKEN", "tsfm-dev-token")

st.set_page_config(page_title="Market Calibration LIVE Demo v2", layout="wide")

I18N = {
    "en": {
        "app_title": "📊 Market Calibration LIVE Demo v2",
        "disclaimer": "Not investment advice. Demo outputs are probabilistic and may be wrong.",
        "language": "Language",
        "page": "Page",
        "overview": "Overview",
        "detail": "Market Detail",
        "compare": "Compare",
        "obs": "Observability",
        "safe_api_error": "Unable to load data from API right now. Please retry in a moment.",
        "invalid_series": "Please input valid comma-separated numbers between 0 and 1.",
        "overview_help": "Use trust, alerts, and segment signals together. Single metrics can be noisy.",
        "trust_card": "Trust score combines calibration quality and alert context.",
        "uncertainty_card": "Wider q10-q90 bands indicate higher forecast uncertainty.",
    },
    "kr": {
        "app_title": "📊 마켓 캘리브레이션 LIVE 데모 v2",
        "disclaimer": "투자 조언이 아닙니다. 데모 결과는 확률 예측이며 오차가 있을 수 있습니다.",
        "language": "언어",
        "page": "페이지",
        "overview": "개요",
        "detail": "마켓 상세",
        "compare": "비교",
        "obs": "관측성",
        "safe_api_error": "현재 API 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요.",
        "invalid_series": "0~1 범위의 숫자를 쉼표로 구분해 입력해 주세요.",
        "overview_help": "신뢰점수, 경보, 세그먼트 신호를 함께 보세요. 단일 지표는 노이즈가 있을 수 있습니다.",
        "trust_card": "신뢰점수는 캘리브레이션 품질과 경보 맥락을 함께 반영합니다.",
        "uncertainty_card": "q10-q90 구간 폭이 넓을수록 예측 불확실성이 큽니다.",
    },
}


lang = st.sidebar.selectbox(
    "Language / 언어",
    options=["en", "kr"],
    format_func=lambda x: "English" if x == "en" else "한국어",
)
T = I18N[lang]

st.sidebar.warning("⚠️ " + T["disclaimer"])

pages = {
    T["overview"]: "overview",
    T["detail"]: "detail",
    T["compare"]: "compare",
    T["obs"]: "obs",
}
page = st.sidebar.radio(T["page"], list(pages.keys()))

st.title(T["app_title"])
st.caption(T["disclaimer"])


def safe_get(path: str) -> tuple[Any | None, str | None]:
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(f"{API_BASE}{path}")
            res.raise_for_status()
            return res.json(), None
    except httpx.HTTPStatusError as exc:
        return None, f"HTTP {exc.response.status_code}"
    except httpx.HTTPError:
        return None, "network-error"


def safe_post(path: str, payload: dict, *, auth: bool = False) -> tuple[Any | None, str | None]:
    headers = {"Authorization": f"Bearer {FORECAST_TOKEN}"} if auth else {}
    try:
        with httpx.Client(timeout=20.0, headers=headers) as client:
            res = client.post(f"{API_BASE}{path}", json=payload)
            res.raise_for_status()
            return res.json(), None
    except httpx.HTTPStatusError as exc:
        return None, f"HTTP {exc.response.status_code}"
    except httpx.HTTPError:
        return None, "network-error"


def parse_series(series_text: str) -> list[float]:
    vals = [float(v.strip()) for v in series_text.split(",") if v.strip()]
    if not vals or any(math.isnan(v) or v < 0 or v > 1 for v in vals):
        raise ValueError("invalid series")
    return vals


def parse_prom_metrics(text: str) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].split("{")[0]
        try:
            val = float(parts[-1])
        except ValueError:
            continue
        parsed[key] = parsed.get(key, 0.0) + val
    return parsed


if pages[page] == "overview":
    scoreboard, sc_err = safe_get("/scoreboard?window=90d")
    alerts, al_err = safe_get("/alerts?limit=50")

    if sc_err or al_err:
        st.error(T["safe_api_error"])
        st.caption(f"scoreboard={sc_err}, alerts={al_err}")
    else:
        score_items = scoreboard.get("items", [])
        alert_items = alerts.get("items", [])
        score_df = pd.DataFrame(score_items)
        alert_df = pd.DataFrame(alert_items)

        market_count = len(score_df)
        avg_trust = float(score_df["trust_score"].dropna().mean()) if "trust_score" in score_df else float("nan")
        high_alerts = int((alert_df["severity"] == "high").sum()) if "severity" in alert_df else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Markets", market_count)
        c2.metric("Avg trust", "-" if math.isnan(avg_trust) else f"{avg_trust:.3f}")
        c3.metric("High alerts", high_alerts)

        st.info(T["overview_help"])

        left, right = st.columns(2)
        with left:
            st.write("### Trust by market")
            if not score_df.empty and {"market_id", "trust_score"}.issubset(score_df.columns):
                st.dataframe(
                    score_df[["market_id", "trust_score", "brier", "ece", "liquidity_bucket", "category"]].sort_values(
                        by="trust_score", ascending=False
                    ),
                    use_container_width=True,
                )
            else:
                st.caption("No scoreboard rows.")

        with right:
            st.write("### Alerts by severity")
            if not alert_df.empty and "severity" in alert_df.columns:
                sev = alert_df.groupby("severity").size().rename("count").to_frame()
                st.bar_chart(sev)
            else:
                st.caption("No alerts.")

        st.write("### Trust / Uncertainty Explainability")
        ex1, ex2 = st.columns(2)
        ex1.success("🧭 " + T["trust_card"])
        ex2.warning("🌫️ " + T["uncertainty_card"])

elif pages[page] == "detail":
    markets, mk_err = safe_get("/markets")
    if mk_err:
        st.error(T["safe_api_error"])
        st.caption(f"markets={mk_err}")
    else:
        ids = [m.get("market_id") for m in markets.get("items", []) if m.get("market_id")]
        if not ids:
            st.warning("No markets available.")
        else:
            market_id = st.selectbox("Market", ids)
            detail, dt_err = safe_get(f"/markets/{market_id}")
            if dt_err:
                st.error(T["safe_api_error"])
                st.caption(f"detail={dt_err}")
            else:
                d1, d2, d3 = st.columns(3)
                d1.metric("Trust", f"{detail.get('trust_score', 0):.3f}" if detail.get("trust_score") is not None else "-")
                d2.metric("Category", detail.get("category") or "-")
                d3.metric("Liquidity", detail.get("liquidity_bucket") or "-")

            y = st.text_area(
                "Input y values (comma-separated)",
                "0.45,0.46,0.47,0.48,0.49,0.50,0.52,0.51,0.53,0.54",
            )
            if st.button("Run forecast"):
                try:
                    vals = parse_series(y)
                except ValueError:
                    st.warning(T["invalid_series"])
                    vals = []

                if vals:
                    payload = {
                        "market_id": market_id,
                        "as_of_ts": datetime.now(timezone.utc).isoformat(),
                        "freq": "5m",
                        "horizon_steps": 6,
                        "quantiles": [0.1, 0.5, 0.9],
                        "y": vals,
                    }
                    fc, fc_err = safe_post("/tsfm/forecast", payload, auth=True)
                    if fc_err:
                        st.error(T["safe_api_error"])
                        st.caption(f"forecast={fc_err}")
                    else:
                        yhat = fc.get("yhat_q", {})
                        q10 = yhat.get("0.1", [])
                        q50 = yhat.get("0.5", [])
                        q90 = yhat.get("0.9", [])
                        horizon = list(range(1, max(len(q10), len(q50), len(q90)) + 1))
                        fc_df = pd.DataFrame({"step": horizon})
                        fc_df["q10"] = q10[: len(horizon)]
                        fc_df["q50"] = q50[: len(horizon)]
                        fc_df["q90"] = q90[: len(horizon)]

                        st.write("### Forecast (q10 / q50 / q90)")
                        st.line_chart(fc_df.set_index("step"))
                        st.dataframe(fc_df, use_container_width=True)

                        if q10 and q90 and q50:
                            width = q90[-1] - q10[-1]
                            st.write("### Explainability")
                            e1, e2 = st.columns(2)
                            e1.info(f"Median path (q50) last step: {q50[-1]:.3f}")
                            e2.warning(f"Uncertainty width (q90-q10) last step: {width:.3f}")

            pm, pm_err = safe_get(f"/postmortem/{market_id}")
            if not pm_err and pm:
                with st.expander("Latest Postmortem", expanded=False):
                    st.markdown(pm.get("content", ""))

elif pages[page] == "compare":
    markets, mk_err = safe_get("/markets")
    if mk_err:
        st.error(T["safe_api_error"])
        st.caption(f"markets={mk_err}")
    else:
        ids = [m.get("market_id") for m in markets.get("items", []) if m.get("market_id")]
        if not ids:
            st.warning("No markets available.")
        else:
            market_id = st.selectbox("Market", ids, key="cmp-market")
            y = st.text_area("Input y values", "0.41,0.42,0.43,0.44,0.45,0.46,0.47,0.48,0.49,0.50", key="cmp-y")

            if st.button("Run comparison"):
                try:
                    vals = parse_series(y)
                except ValueError:
                    st.warning(T["invalid_series"])
                    vals = []

                if vals:
                    payload = {
                        "forecast": {
                            "market_id": market_id,
                            "as_of_ts": datetime.now(timezone.utc).isoformat(),
                            "freq": "5m",
                            "horizon_steps": 6,
                            "quantiles": [0.1, 0.5, 0.9],
                            "y": vals,
                        },
                        "baseline_liquidity_bucket": "low",
                    }
                    cmp_result, cmp_err = safe_post(f"/markets/{market_id}/comparison", payload)
                    if cmp_err:
                        st.error(T["safe_api_error"])
                        st.caption(f"comparison={cmp_err}")
                    else:
                        baseline = cmp_result.get("baseline", {}).get("yhat_q", {})
                        tollama = cmp_result.get("tollama", {}).get("yhat_q", {})

                        def last_val(block: dict[str, list[float]], q: str) -> float | None:
                            seq = block.get(q, [])
                            return seq[-1] if seq else None

                        rows = []
                        for q in ["0.1", "0.5", "0.9"]:
                            b = last_val(baseline, q)
                            t = last_val(tollama, q)
                            d = (t - b) if b is not None and t is not None else None
                            rows.append(
                                {
                                    "quantile": q,
                                    "baseline_last": b,
                                    "tollama_last": t,
                                    "delta": d,
                                }
                            )

                        cmp_df = pd.DataFrame(rows)
                        c1, c2 = st.columns(2)
                        with c1:
                            st.write("### Baseline vs Tollama (last step)")
                            st.dataframe(cmp_df, use_container_width=True)
                        with c2:
                            d50 = cmp_result.get("delta_last_q50")
                            if d50 is None:
                                st.info("Δ q50 unavailable")
                            elif abs(d50) < 0.01:
                                st.success(f"Δ q50: {d50:+.4f} (aligned)")
                            elif abs(d50) < 0.03:
                                st.warning(f"Δ q50: {d50:+.4f} (watch)")
                            else:
                                st.error(f"Δ q50: {d50:+.4f} (large)")

                        st.write("### Explainability")
                        st.info("Compare baseline fallback and tollama path; use Δq50 + interval width to judge trust.")

elif pages[page] == "obs":
    try:
        metrics_text = httpx.get(f"{API_BASE}/metrics", timeout=10.0)
        metrics_text.raise_for_status()
    except httpx.HTTPError:
        st.error(T["safe_api_error"])
    else:
        parsed = parse_prom_metrics(metrics_text.text)
        req = parsed.get("tsfm_requests_total", 0.0)
        err = parsed.get("tsfm_errors_total", 0.0)
        lat_sum = parsed.get("tsfm_latency_seconds_sum", 0.0)
        lat_cnt = parsed.get("tsfm_latency_seconds_count", 0.0)
        cache_hit = parsed.get("tsfm_cache_hits_total", 0.0)
        cache_miss = parsed.get("tsfm_cache_misses_total", 0.0)

        avg_latency = (lat_sum / lat_cnt) if lat_cnt > 0 else 0.0
        err_rate = (err / req) if req > 0 else 0.0
        hit_rate = (cache_hit / (cache_hit + cache_miss)) if (cache_hit + cache_miss) > 0 else 0.0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Requests", int(req))
        c2.metric("Error rate", f"{err_rate:.2%}")
        c3.metric("Avg latency", f"{avg_latency:.3f}s")
        c4.metric("Cache hit rate", f"{hit_rate:.2%}")

        st.write("### Parsed metric summaries")
        if parsed:
            metric_df = (
                pd.DataFrame([{"metric": k, "value": v} for k, v in parsed.items()])
                .sort_values(by="metric")
                .reset_index(drop=True)
            )
            st.dataframe(metric_df, use_container_width=True)
        else:
            st.caption("No parseable metrics returned.")

        with st.expander("Raw /metrics", expanded=False):
            st.code("\n".join(metrics_text.text.splitlines()[:120]))
