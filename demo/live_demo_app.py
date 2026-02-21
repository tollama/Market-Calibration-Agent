from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
import streamlit as st

API_BASE = os.getenv("LIVE_DEMO_API_BASE", "http://127.0.0.1:8000")

st.set_page_config(page_title="Market Calibration LIVE Demo", layout="wide")

KR_EN = {
    "overview": "개요 / Overview",
    "detail": "마켓 상세 / Market Detail",
    "compare": "비교 / Compare",
    "obs": "관측성 / Observability",
}


def get_json(path: str):
    with httpx.Client(timeout=10.0) as client:
        res = client.get(f"{API_BASE}{path}")
        res.raise_for_status()
        return res.json()


def post_json(path: str, payload: dict):
    with httpx.Client(timeout=20.0) as client:
        res = client.post(f"{API_BASE}{path}", json=payload)
        res.raise_for_status()
        return res.json()


st.title("📊 Market Calibration LIVE Demo")
st.caption("투자 조언이 아닙니다. / Not investment advice.")

page = st.sidebar.radio("Page", list(KR_EN.values()))

if page == KR_EN["overview"]:
    st.subheader("Scoreboard + Alerts")
    scoreboard = get_json("/scoreboard?window=90d")
    alerts = get_json("/alerts?limit=20")

    st.write("### Explainability / 설명")
    st.info("신뢰점수, 경보 심각도, 최근 이슈를 함께 보며 시장 상태를 빠르게 파악합니다.")

    st.dataframe(scoreboard.get("items", []), use_container_width=True)
    st.write("#### Recent Alerts / 최근 경보")
    st.dataframe(alerts.get("items", []), use_container_width=True)

elif page == KR_EN["detail"]:
    markets = get_json("/markets")
    ids = [m["market_id"] for m in markets.get("items", [])]
    if not ids:
        st.warning("No markets available.")
    else:
        market_id = st.selectbox("Market", ids)
        detail = get_json(f"/markets/{market_id}")
        st.json(detail)

        y = st.text_input("Input y values (comma-separated)", "0.45,0.46,0.47,0.48,0.49,0.5,0.52,0.51,0.53,0.54")
        vals = [float(v.strip()) for v in y.split(",") if v.strip()]
        payload = {
            "market_id": market_id,
            "as_of_ts": datetime.now(timezone.utc).isoformat(),
            "freq": "5m",
            "horizon_steps": 6,
            "quantiles": [0.1, 0.5, 0.9],
            "y": vals,
        }
        token = os.getenv("TSFM_FORECAST_API_TOKEN", "tsfm-dev-token")
        with httpx.Client(timeout=20.0, headers={"Authorization": f"Bearer {token}"}) as client:
            r = client.post(f"{API_BASE}/tsfm/forecast", json=payload)
            if r.status_code == 200:
                fc = r.json()
                st.write("### Forecast q10/q50/q90")
                st.json(fc.get("yhat_q", {}))
            else:
                st.error(f"Forecast failed: {r.status_code} {r.text}")

        pm = httpx.get(f"{API_BASE}/postmortem/{market_id}", timeout=10.0)
        if pm.status_code == 200:
            st.write("### Latest Postmortem")
            st.markdown(pm.json().get("content", ""))

elif page == KR_EN["compare"]:
    markets = get_json("/markets")
    ids = [m["market_id"] for m in markets.get("items", [])]
    if ids:
        market_id = st.selectbox("Market", ids, key="cmp-market")
        y = st.text_input("Input y values", "0.41,0.42,0.43,0.44,0.45,0.46,0.47,0.48,0.49,0.5")
        vals = [float(v.strip()) for v in y.split(",") if v.strip()]
        if st.button("Run comparison"):
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
            cmp_result = post_json(f"/markets/{market_id}/comparison", payload)
            st.write("### Explainability / 설명")
            st.success("baseline fallback과 tollama 경로의 q50 차이를 마지막 스텝 기준으로 제시합니다.")
            st.json(cmp_result)

elif page == KR_EN["obs"]:
    st.subheader("Metrics Summary")
    metrics_text = httpx.get(f"{API_BASE}/metrics", timeout=10.0).text
    lines = [line for line in metrics_text.splitlines() if line and not line.startswith("#")]
    st.code("\n".join(lines[:80]))
