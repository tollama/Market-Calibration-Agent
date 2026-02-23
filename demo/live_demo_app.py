from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import streamlit as st

API_BASE = os.getenv("LIVE_DEMO_API_BASE", "http://127.0.0.1:8000")
_PLACEHOLDER_TOKENS = {
    "",
    "changemeplease",
    "your-token",
    "demo-token",
    "dev-token",
    "tsfm-dev-token",
    "example",
    "changeme",
    "placeholder",
}


def _is_placeholder_token(value: str | None) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in _PLACEHOLDER_TOKENS


def _is_forecast_enabled() -> bool:
    raw_value = (os.getenv("DEMO_FORECAST_ENABLED", "") or "").strip().lower()
    if raw_value in {"1", "true", "on", "yes", "y"}:
        return True
    if raw_value in {"0", "false", "off", "no", "n", ""}:
        return False
    return bool(FORECAST_TOKEN)


RAW_FORECAST_TOKEN = os.getenv("TSFM_FORECAST_API_TOKEN") or os.getenv("AUTH_TOKEN", "")
FORECAST_TOKEN = RAW_FORECAST_TOKEN if not _is_placeholder_token(RAW_FORECAST_TOKEN) else ""
FORECAST_TOKEN_VALID = bool(FORECAST_TOKEN)
DEMO_FORECAST_ENABLED = _is_forecast_enabled()
SAMPLE_DATA_PATH = Path(__file__).resolve().parents[1] / "artifacts/demo/live_demo_sample_data.json"

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
        "forecast_token_hint": "Forecast requires a valid TSFM token. Placeholder values are not supported (e.g., 'changeme', 'your-token', 'demo-token').\nUse a real token like: TSFM_FORECAST_API_TOKEN=abc123... (or set AUTH_TOKEN).",
        "forecast_token_invalid": "The saved token is invalid or expired. Please update to a real TSFM token and restart the app (e.g., TSFM_FORECAST_API_TOKEN=abc123...).",
        "invalid_series": "Please input valid comma-separated numbers between 0 and 1.",
        "overview_help": "Use trust, alerts, and segment signals together. Single metrics can be noisy.",
        "trust_card": "Trust score combines calibration quality and alert context.",
        "uncertainty_card": "Wider q10-q90 bands indicate higher forecast uncertainty.",
        "help_label": "What does this mean?",
        "overview_kpi_help": "Calibrated markets shows scoreboard coverage. Top list markets shows how many markets are in the live sample top list. Avg trust is overall reliability (higher is better). High alerts are priority issues to check first.",
        "overview_trust_alert_help": "Trust table ranks markets by confidence. Alerts chart shows where risks are concentrated by severity.",
        "detail_forecast_help": "q50 is the most typical path. q10 and q90 are lower/upper likely bounds. A wider gap means less certainty.",
        "compare_help": "Baseline is fallback logic. Tollama is the model path. Δ q50 is the median difference at the last step (near 0 = similar).",
        "compare_warn_invalid_quantiles": "Some forecast quantiles are missing or invalid. Showing available values only.",
        "compare_warn_quantile_trim": "Quantile lengths differ; using the shortest valid overlap.",
        "obs_help": "Requests = total forecast calls. Error rate = failed call share. Fallback = backup path used when primary fails. Cache hit rate = reused results share.",
        "market_source_sample": "Using local live sample markets.",
        "market_source_api": "Using API market list.",
        "market_meta_sample_fallback": "Live API detail not found (404). Showing sample metadata.",
        "top_n_markets": "Top N markets",
        "top_markets_title": "Top markets",
        "top_markets_help": "Top list by latest YES price.",
        "kpi_calibrated_markets": "Calibrated markets",
        "kpi_top_list_markets": "Top list markets",
        "kpi_avg_trust": "Avg trust",
        "kpi_high_alerts": "High alerts",
        "storyline_source_note": "Top list count comes from live sample list; Calibrated markets comes from scoreboard coverage.",
        "so_what": "So what?",
        "evidence": "Evidence",
        "confidence": "Confidence / Caution",
        "reliability_gate": "Reliability Gate",
        "why_this_badge": "Why this badge?",
        "live_change": "Live change",
        "battleboard": "Baseline vs Tollama battleboard",
        "holdout_eval": "Light holdout evaluation",
        "na_reason": "N/A (insufficient data)",
        "question_why": "Why important?",
        "question_risk": "Current risk?",
        "question_summary": "One-line summary",
        "quick_answers": "Quick questions",
        "metric_na": "N/A",
        "na_not_provided": "not provided",
        "na_short_window": "short test window",
        "fallback_status": "Fallback",
        "latency": "Latency",
        "freshness": "Freshness",
        "impact_mode": "Impact Mode",
        "wow_center": "⚡ WOW Command Center",
        "what_matters_now": "What matters now",
        "confidence_risk": "Confidence / Risk",
        "evidence_now": "Evidence now",
        "caution": "Caution",
        "safety_note": "Safety note: This is a live demo signal, not investment advice.",
        "top_movers_now": "🚀 Top Movers Now (Δ5m)",
        "market_id": "market_id",
        "question_short": "question",
        "last_price": "last_price",
        "delta_5m": "delta_5m",
        "signal": "signal",
        "signal_up": "up",
        "signal_down": "down",
        "signal_flat": "flat",
        "live_storyline": "🧭 Live Storyline",
        "story_pulse": "Pulse",
        "story_model_edge": "Model Edge",
        "story_risk_gate": "Risk Gate",
        "no_markets": "No markets available.",
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
        "forecast_token_hint": "Forecast를 실행하려면 유효한 TSFM 토큰이 필요합니다. 'changeme', 'your-token', 'demo-token' 같은 placeholder는 허용되지 않습니다.\n실제 토큰 예시: TSFM_FORECAST_API_TOKEN=abc123... (또는 AUTH_TOKEN).",
        "forecast_token_invalid": "저장된 토큰이 만료되었거나 유효하지 않습니다. 유효한 TSFM 토큰으로 변경한 뒤 앱을 다시 시작해 주세요 (예: TSFM_FORECAST_API_TOKEN=abc123...).",
        "invalid_series": "0~1 범위의 숫자를 쉼표로 구분해 입력해 주세요.",
        "overview_help": "신뢰점수, 경보, 세그먼트 신호를 함께 보세요. 단일 지표는 노이즈가 있을 수 있습니다.",
        "trust_card": "신뢰점수는 캘리브레이션 품질과 경보 맥락을 함께 반영합니다.",
        "uncertainty_card": "q10-q90 구간 폭이 넓을수록 예측 불확실성이 큽니다.",
        "help_label": "이 결과가 의미하는 것",
        "overview_kpi_help": "캘리브레이션 마켓은 스코어보드 커버리지 기준 마켓 수입니다. Top list 마켓은 라이브 샘플 상위 목록의 마켓 수입니다. Avg trust는 전체 신뢰도(높을수록 좋음)이고, High alerts는 우선 확인이 필요한 이슈 수입니다.",
        "overview_trust_alert_help": "신뢰 테이블은 마켓을 신뢰도 순으로 보여줍니다. 경보 차트는 심각도별로 위험이 어디에 몰렸는지 보여줍니다.",
        "detail_forecast_help": "q50은 가장 대표적인 경로입니다. q10/q90은 하단/상단 가능 범위입니다. 간격이 넓을수록 확신이 낮습니다.",
        "compare_help": "Baseline은 기본(대체) 로직, Tollama는 모델 예측입니다. Δ q50은 마지막 시점 중앙값 차이(0에 가까우면 유사)입니다.",
        "compare_warn_invalid_quantiles": "일부 예측 분위수 데이터가 없거나 유효하지 않습니다. 사용 가능한 값만 표시합니다.",
        "compare_warn_quantile_trim": "분위수 길이가 달라 가장 짧은 유효 구간으로 맞춰 계산합니다.",
        "obs_help": "Requests는 총 예측 호출 수, Error rate는 실패 비율, Fallback은 기본 경로로 대체된 횟수, Cache hit rate는 재사용된 결과 비율입니다.",
        "market_source_sample": "로컬 live 샘플 마켓 목록을 사용 중입니다.",
        "market_source_api": "API 마켓 목록을 사용 중입니다.",
        "market_meta_sample_fallback": "Live API 상세(404)를 찾지 못해 샘플 메타데이터를 표시합니다.",
        "top_n_markets": "상위 N개 마켓",
        "top_markets_title": "상위 마켓",
        "top_markets_help": "최신 YES 가격 기준 상위 목록입니다.",
        "kpi_calibrated_markets": "캘리브레이션 마켓",
        "kpi_top_list_markets": "Top list 마켓",
        "kpi_avg_trust": "평균 신뢰도",
        "kpi_high_alerts": "High 경보",
        "storyline_source_note": "Top list 수치는 라이브 샘플 목록 기준이며, 캘리브레이션 마켓 수는 스코어보드 커버리지 기준입니다.",
        "so_what": "핵심 요약",
        "evidence": "근거",
        "confidence": "확신 / 주의",
        "reliability_gate": "신뢰성 게이트",
        "why_this_badge": "이 배지 이유",
        "live_change": "실시간 변화",
        "battleboard": "Baseline vs Tollama 배틀보드",
        "holdout_eval": "간단 홀드아웃 평가",
        "na_reason": "N/A (데이터 부족)",
        "question_why": "왜 중요한가요?",
        "question_risk": "현재 리스크는?",
        "question_summary": "한 줄 요약",
        "quick_answers": "빠른 질문",
        "metric_na": "N/A",
        "na_not_provided": "제공되지 않음",
        "na_short_window": "테스트 구간이 짧음",
        "fallback_status": "대체 경로",
        "latency": "지연시간",
        "freshness": "신선도",
        "impact_mode": "임팩트 모드",
        "wow_center": "⚡ WOW 커맨드 센터",
        "what_matters_now": "지금 중요한 포인트",
        "confidence_risk": "확신 / 리스크",
        "evidence_now": "현재 근거",
        "caution": "주의",
        "safety_note": "안내: 본 내용은 라이브 데모 신호이며 투자 조언이 아닙니다.",
        "top_movers_now": "🚀 지금 급변 마켓 (Δ5분)",
        "market_id": "market_id",
        "question_short": "질문",
        "last_price": "현재가",
        "delta_5m": "Δ5분",
        "signal": "시그널",
        "signal_up": "상승",
        "signal_down": "하락",
        "signal_flat": "보합",
        "live_storyline": "🧭 라이브 스토리라인",
        "story_pulse": "시장 펄스",
        "story_model_edge": "모델 우위",
        "story_risk_gate": "리스크 게이트",
        "no_markets": "표시할 마켓이 없습니다.",
    },
}


lang = st.sidebar.selectbox(
    "Language / 언어",
    options=["en", "kr"],
    format_func=lambda x: "English" if x == "en" else "한국어",
)
T = I18N[lang]

impact_mode = st.sidebar.toggle(T["impact_mode"], value=True)

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


@st.cache_data(ttl=30)
def load_sample_markets() -> list[dict[str, Any]]:
    if not SAMPLE_DATA_PATH.exists():
        return []
    try:
        payload = json.loads(SAMPLE_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        market_id = str(item.get("market_id", "")).strip()
        if not market_id:
            continue
        y_vals = item.get("y", [])
        y = [float(v) for v in y_vals if isinstance(v, (int, float)) and 0 <= float(v) <= 1]
        cleaned.append(
            {
                "market_id": market_id,
                "title": str(item.get("title") or "").strip(),
                "question": str(item.get("question") or "").strip(),
                "as_of_ts": item.get("as_of_ts"),
                "y": y,
            }
        )
    return cleaned


def market_label(item: dict[str, Any]) -> str:
    prompt = item.get("question") or item.get("title") or "-"
    return f"{item.get('market_id')} | {prompt}"


def _coerce_float(val: Any) -> float | None:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if not math.isnan(f) else None


def latest_yes_price(item: dict[str, Any]) -> float | None:
    y = item.get("y")
    if isinstance(y, list) and y:
        last = _coerce_float(y[-1])
        if last is not None and 0 <= last <= 1:
            return last
    for key in ("latest_yes_price", "yes_price", "last_yes_price", "last_price", "price"):
        price = _coerce_float(item.get(key))
        if price is not None:
            return price
    return None


def market_as_of(item: dict[str, Any]) -> Any:
    for key in ("as_of_ts", "updated_at", "as_of", "timestamp"):
        if item.get(key) is not None:
            return item.get(key)
    return "-"


def build_top_markets_df(items: list[dict[str, Any]], top_n: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "market_id": str(item.get("market_id") or "-"),
                "question/title": item.get("question") or item.get("title") or "-",
                "latest_yes_price": latest_yes_price(item),
                "as_of_ts": market_as_of(item),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["market_id", "question/title", "latest_yes_price", "as_of_ts"])
    df = pd.DataFrame(rows)
    return df.sort_values(by="latest_yes_price", ascending=False, na_position="last").head(top_n).reset_index(drop=True)




def get_column_case_insensitive(df: pd.DataFrame, target: str) -> str | None:
    lookup = {str(c).strip().lower(): c for c in df.columns}
    return lookup.get(target.strip().lower())


def is_calibrated_market_id(market_id: Any) -> bool:
    return str(market_id or "").strip().lower().startswith("mkt-")

def parse_series(series_text: str) -> list[float]:
    vals: list[float] = []
    for raw in (series_text or "").split(","):
        token = raw.strip()
        if not token:
            continue
        coerced = _coerce_float(token)
        if coerced is None or coerced < 0 or coerced > 1:
            raise ValueError("invalid series")
        vals.append(coerced)
    if not vals:
        raise ValueError("invalid series")
    return vals


def coerce_prob_series(values: Any, *, limit: int = 256) -> list[float]:
    if not isinstance(values, list):
        return []
    out: list[float] = []
    for v in values[:limit]:
        fv = _coerce_float(v)
        if fv is not None and 0 <= fv <= 1:
            out.append(fv)
    return out


def sanitize_quantile_series(values: Any) -> list[float]:
    if not isinstance(values, list):
        return []
    out: list[float] = []
    for v in values:
        fv = _coerce_float(v)
        if fv is None:
            continue
        out.append(fv)
    return out


def sanitize_yhat_q_map(yhat_q: Any) -> dict[str, list[float]]:
    if not isinstance(yhat_q, dict):
        return {}
    return {q: sanitize_quantile_series(seq) for q, seq in yhat_q.items() if isinstance(q, str)}


def overlap_quantiles(block: dict[str, list[float]], quantiles: list[str]) -> tuple[dict[str, list[float]], int, bool]:
    lengths = [len(block.get(q, [])) for q in quantiles if len(block.get(q, [])) > 0]
    if not lengths:
        return ({q: [] for q in quantiles}, 0, False)
    min_len = min(lengths)
    trimmed = {q: block.get(q, [])[:min_len] for q in quantiles}
    return trimmed, min_len, len(set(lengths)) > 1


def value_from_top_or_meta(payload: Any, key: str) -> Any:
    if not isinstance(payload, dict):
        return None
    if key in payload:
        return payload.get(key)
    meta_obj = payload.get("meta")
    if isinstance(meta_obj, dict) and key in meta_obj:
        return meta_obj.get(key)
    return None


def value_from_top_or_meta_aliases(payload: Any, keys: list[str]) -> Any:
    if not isinstance(payload, dict):
        return None
    meta_obj = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    for key in keys:
        if key in payload:
            return payload.get(key)
        if key in meta_obj:
            return meta_obj.get(key)
    return None


def coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    return None


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


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def streamlit_notice(level: str, message: str) -> None:
    """Render a notice with a safe Streamlit method mapping.

    Supports success/info/warning/error, and falls back to info for unknown labels
    (e.g., legacy "secondary").
    """
    notice_map = {
        "success": st.success,
        "info": st.info,
        "warning": st.warning,
        "error": st.error,
    }
    renderer = notice_map.get((level or "").strip().lower(), st.info)
    renderer(message)


def compute_live_change(y: list[float]) -> tuple[str, str]:
    if len(y) < 2:
        return ("secondary", "Not enough history for a 5-minute comparison." if lang == "en" else "5분 변화 비교를 위한 데이터가 부족합니다.")
    now_v = y[-1]
    prev_v = y[-2]
    delta = now_v - prev_v
    if abs(delta) < 0.002:
        return ("secondary", (f"5-minute change: flat ({now_v:.3f})." if lang == "en" else f"5분 변화: 보합 ({now_v:.3f})."))
    color = "success" if delta > 0 else "error"
    msg = (
        f"5-minute change: {delta:+.3f} ({'up' if delta > 0 else 'down'})."
        if lang == "en"
        else f"5분 변화: {delta:+.3f} ({'상승' if delta > 0 else '하락'})."
    )
    return color, msg


def calc_metrics(actual: list[float], pred_q50: list[float], train: list[float], pred_quantiles: dict[str, list[float]] | None = None) -> dict[str, float | None]:
    if not actual or not pred_q50 or len(actual) != len(pred_q50):
        return {"mae": None, "mape": None, "mase": None, "pinball_0.1": None, "pinball_0.5": None, "pinball_0.9": None}
    n = len(actual)
    abs_err = [abs(a - p) for a, p in zip(actual, pred_q50)]
    mae = sum(abs_err) / n
    mape_vals = [abs((a - p) / a) for a, p in zip(actual, pred_q50) if abs(a) > 1e-8]
    mape = (sum(mape_vals) / len(mape_vals)) if mape_vals else None
    naive_scale = None
    if len(train) > 1:
        diffs = [abs(train[i] - train[i - 1]) for i in range(1, len(train))]
        naive_scale = (sum(diffs) / len(diffs)) if diffs else None
    mase = (mae / naive_scale) if naive_scale and naive_scale > 1e-8 else None

    def pinball(q: float, pred: list[float]) -> float | None:
        if not pred or len(pred) != len(actual):
            return None
        vals = []
        for a, p in zip(actual, pred):
            e = a - p
            vals.append(max(q * e, (q - 1) * e))
        return sum(vals) / len(vals)

    pqs = pred_quantiles or {}
    p10 = pqs.get("0.1") if isinstance(pqs, dict) else None
    p50 = pqs.get("0.5") if isinstance(pqs, dict) else None
    p90 = pqs.get("0.9") if isinstance(pqs, dict) else None

    return {
        "mae": mae,
        "mape": mape,
        "mase": mase,
        "pinball_0.1": pinball(0.1, p10 if isinstance(p10, list) else pred_q50),
        "pinball_0.5": pinball(0.5, p50 if isinstance(p50, list) else pred_q50),
        "pinball_0.9": pinball(0.9, p90 if isinstance(p90, list) else pred_q50),
    }


def reliability_gate(as_of_ts: Any, used_fallback: bool, width: float | None) -> tuple[str, list[str], str]:
    reasons: list[str] = []
    score = 0
    dt = _parse_dt(as_of_ts)
    freshness_min = None
    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        freshness_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
    if freshness_min is None:
        score += 1
        reasons.append(T["freshness"] + ": " + ("unknown" if lang == "en" else "알 수 없음"))
    elif freshness_min > 30:
        score += 2
        reasons.append(T["freshness"] + (f": {freshness_min:.0f}m old" if lang == "en" else f": {freshness_min:.0f}분 경과"))
    elif freshness_min > 10:
        score += 1
        reasons.append(T["freshness"] + (f": {freshness_min:.0f}m old" if lang == "en" else f": {freshness_min:.0f}분 경과"))

    if used_fallback:
        score += 2
        reasons.append(T["fallback_status"] + ": ON")

    if width is None:
        score += 1
        reasons.append("Uncertainty width: unknown" if lang == "en" else "불확실성 폭: 알 수 없음")
    elif width > 0.20:
        score += 2
        reasons.append((f"Uncertainty width: {width:.3f} (wide)" if lang == "en" else f"불확실성 폭: {width:.3f} (넓음)"))
    elif width > 0.12:
        score += 1
        reasons.append((f"Uncertainty width: {width:.3f} (medium)" if lang == "en" else f"불확실성 폭: {width:.3f} (보통)"))

    if score <= 1:
        return ("🟢 Green" if lang == "en" else "🟢 양호", reasons or (["Signal quality is stable." if lang == "en" else "신호 품질이 안정적입니다."]), "success")
    if score <= 3:
        return ("🟡 Watch" if lang == "en" else "🟡 주의", reasons, "warning")
    return ("🔴 Caution" if lang == "en" else "🔴 경계", reasons, "error")


def info_toggle(key: str, text: str) -> None:
    state_key = f"info_toggle_{key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = False

    left, right = st.columns([0.95, 0.05])
    left.caption(T["help_label"])
    if right.button("ℹ️", key=f"btn_{state_key}"):
        st.session_state[state_key] = not st.session_state[state_key]

    if st.session_state[state_key]:
        st.info(text)


def short_text(s: str, max_len: int = 64) -> str:
    txt = (s or "").strip()
    if len(txt) <= max_len:
        return txt
    return txt[: max_len - 1].rstrip() + "…"


def market_delta_5m(item: dict[str, Any]) -> float | None:
    y = item.get("y")
    if not isinstance(y, list) or len(y) < 2:
        return None
    last = _coerce_float(y[-1])
    prev = _coerce_float(y[-2])
    if last is None or prev is None:
        return None
    return last - prev


def signal_label(delta: float | None) -> str:
    if delta is None or abs(delta) < 0.002:
        return T["signal_flat"]
    return T["signal_up"] if delta > 0 else T["signal_down"]


def build_top_movers_df(items: list[dict[str, Any]], top_n: int) -> pd.DataFrame:
    ranked = sorted(items, key=lambda it: latest_yes_price(it) if latest_yes_price(it) is not None else -1.0, reverse=True)[:top_n]
    rows: list[dict[str, Any]] = []
    for item in ranked:
        delta = market_delta_5m(item)
        price = latest_yes_price(item)
        rows.append(
            {
                T["market_id"]: str(item.get("market_id") or "-"),
                T["question_short"]: short_text(str(item.get("question") or item.get("title") or "-"), 68),
                T["last_price"]: round(price, 3) if price is not None else None,
                T["delta_5m"]: round(delta, 3) if delta is not None else None,
                T["signal"]: signal_label(delta),
                "_abs_delta": abs(delta) if delta is not None else -1.0,
            }
        )
    if not rows:
        return pd.DataFrame(columns=[T["market_id"], T["question_short"], T["last_price"], T["delta_5m"], T["signal"]])
    df = pd.DataFrame(rows).sort_values(by="_abs_delta", ascending=False).drop(columns=["_abs_delta"])
    return df.reset_index(drop=True)


def trust_for_thresholds(avg_trust: float) -> float:
    if math.isnan(avg_trust):
        return avg_trust
    return avg_trust / 100.0 if avg_trust > 1 else avg_trust


def wow_badge(avg_trust: float, high_alerts: int) -> tuple[str, str, str]:
    trust_value = trust_for_thresholds(avg_trust)
    if not math.isnan(trust_value) and trust_value >= 0.72 and high_alerts <= 2:
        return ("🟢 Green", "success", "steady") if lang == "en" else ("🟢 Green", "success", "안정")
    if (not math.isnan(trust_value) and trust_value >= 0.55) and high_alerts <= 6:
        return ("🟡 Yellow", "warning", "watch") if lang == "en" else ("🟡 Yellow", "warning", "주의")
    return ("🔴 Red", "error", "elevated") if lang == "en" else ("🔴 Red", "error", "높음")


if pages[page] == "overview":
    sample_items = load_sample_markets()
    top_n = st.sidebar.slider(T["top_n_markets"], min_value=3, max_value=20, value=10, step=1)

    market_items: list[dict[str, Any]] = []
    using_sample = bool(sample_items)
    mk_err = None

    if using_sample:
        market_items = sample_items
        st.caption(T["market_source_sample"])
    else:
        markets, mk_err = safe_get("/markets")
        market_items = [m for m in (markets or {}).get("items", []) if m.get("market_id")]
        st.caption(T["market_source_api"])

    scoreboard, sc_err = safe_get("/scoreboard?window=90d")
    alerts, al_err = safe_get("/alerts?limit=50")

    if mk_err:
        st.error(T["safe_api_error"])
        st.caption(f"markets={mk_err}")

    top_df = build_top_markets_df(market_items, top_n)
    st.write(f"### {T['top_markets_title']} ({len(top_df)})")
    st.caption(T["top_markets_help"])
    if top_df.empty:
        st.caption(T["no_markets"])
    else:
        st.dataframe(top_df, use_container_width=True, hide_index=True)

    score_items = (scoreboard or {}).get("items", [])
    alert_items = (alerts or {}).get("items", [])
    score_df = pd.DataFrame(score_items)
    alert_df = pd.DataFrame(alert_items)

    market_count = len(score_df)
    top_list_count = len(top_df)

    trust_col = get_column_case_insensitive(score_df, "trust_score")
    trust_series = pd.to_numeric(score_df[trust_col], errors="coerce") if trust_col else pd.Series(dtype=float)
    trust_series = trust_series[trust_series.apply(math.isfinite)] if not trust_series.empty else trust_series
    avg_trust = float(trust_series.mean()) if not trust_series.empty else float("nan")

    sev_col = get_column_case_insensitive(alert_df, "severity")
    high_alerts = int((alert_df[sev_col].astype(str).str.upper() == "HIGH").sum()) if sev_col else 0

    if impact_mode:
        st.write(f"### {T['wow_center']}")
        spotlight = market_items[0] if market_items else {}
        if not top_df.empty:
            top_market_id = str(top_df.iloc[0]["market_id"])
            for it in market_items:
                if str(it.get("market_id")) == top_market_id:
                    spotlight = it
                    break

        sp_q = str(spotlight.get("question") or spotlight.get("title") or "-")
        sp_price = latest_yes_price(spotlight)
        sp_delta = market_delta_5m(spotlight)
        badge_text, badge_style, risk_word = wow_badge(avg_trust, high_alerts)

        hero = (
            f"{T['what_matters_now']}: {short_text(sp_q, 96)}"
            if lang == "en"
            else f"{T['what_matters_now']}: {short_text(sp_q, 96)}"
        )
        st.markdown(f"#### {hero}")
        streamlit_notice(badge_style, f"{T['confidence_risk']}: {badge_text}")

        bullets = [
            (f"Spotlight market: {spotlight.get('market_id', '-')}" if lang == "en" else f"스포트라이트 마켓: {spotlight.get('market_id', '-') }"),
            (f"Last price: {sp_price:.3f}" if sp_price is not None else ("Last price: N/A" if lang == "en" else "현재가: N/A")),
            (f"5m move: {sp_delta:+.3f} ({signal_label(sp_delta)})" if sp_delta is not None else ("5m move: N/A" if lang == "en" else "5분 변화: N/A")),
        ]
        for b in bullets:
            st.write(f"- {b}")

        caution = (
            f"{T['caution']}: Risk is {risk_word}. React to change, don't overreact to noise."
            if lang == "en"
            else f"{T['caution']}: 현재 리스크는 {risk_word} 수준입니다. 노이즈보다 변화 방향에 집중하세요."
        )
        st.caption(caution)
        st.caption(T["safety_note"])

        movers_df = build_top_movers_df(market_items, top_n)
        st.write(f"### {T['top_movers_now']}")
        if movers_df.empty:
            st.caption(T["no_markets"])
        else:
            st.dataframe(movers_df, use_container_width=True, hide_index=True)

        st.write(f"### {T['live_storyline']}")
        st.caption(T["storyline_source_note"])
        tab1, tab2, tab3 = st.tabs([T["story_pulse"], T["story_model_edge"], T["story_risk_gate"]])
        with tab1:
            pulse_txt = (
                f"Market pulse is {signal_label(sp_delta)}. The spotlight market is at {sp_price:.3f} and moving {sp_delta:+.3f} over 5 minutes."
                if sp_price is not None and sp_delta is not None
                else "Pulse is mixed right now. Watch the next few updates for direction."
            )
            if lang == "kr":
                pulse_txt = (
                    f"시장 펄스는 {signal_label(sp_delta)} 입니다. 스포트라이트 마켓은 {sp_price:.3f}, 최근 5분 {sp_delta:+.3f} 변화입니다."
                    if sp_price is not None and sp_delta is not None
                    else "현재 펄스가 혼재되어 있습니다. 다음 몇 번의 업데이트에서 방향을 확인하세요."
                )
            st.info(pulse_txt)
        with tab2:
            trust_value = trust_for_thresholds(avg_trust)
            edge_txt = (
                f"Model edge looks {'healthy' if not math.isnan(trust_value) and trust_value >= 0.65 else 'fragile'} with average trust {avg_trust:.3f}."
                if not math.isnan(avg_trust)
                else "Model edge is unclear because trust data is limited."
            )
            if lang == "kr":
                edge_txt = (
                    f"평균 신뢰도 {avg_trust:.3f} 기준 모델 우위는 {'양호' if not math.isnan(trust_value) and trust_value >= 0.65 else '취약'}합니다."
                    if not math.isnan(avg_trust)
                    else "신뢰도 데이터가 제한되어 모델 우위를 판단하기 어렵습니다."
                )
            st.info(edge_txt)
        with tab3:
            risk_txt = (
                f"Risk gate is {badge_text}. High alerts: {high_alerts}. Use smaller position size until risk cools down."
                if lang == "en"
                else f"리스크 게이트는 {badge_text} 상태이며 High alerts는 {high_alerts}건입니다. 리스크 완화 전에는 보수적으로 대응하세요."
            )
            st.info(risk_txt)

    if sc_err or al_err:
        st.error(T["safe_api_error"])
        st.caption(f"scoreboard={sc_err}, alerts={al_err}")
    else:

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(T["kpi_calibrated_markets"], market_count)
        c2.metric(T["kpi_top_list_markets"], top_list_count)
        c3.metric(T["kpi_avg_trust"], "-" if math.isnan(avg_trust) else f"{avg_trust:.3f}")
        c4.metric(T["kpi_high_alerts"], high_alerts)
        info_toggle("overview_kpi", T["overview_kpi_help"])

        st.info(T["overview_help"])

        left, right = st.columns(2)
        with left:
            st.write("### Trust by market")
            market_id_col = get_column_case_insensitive(score_df, "market_id")
            trust_col = get_column_case_insensitive(score_df, "trust_score")
            if not score_df.empty and market_id_col and trust_col:
                display_cols = [market_id_col, trust_col]
                for optional in ["brier", "ece", "liquidity_bucket", "category"]:
                    col = get_column_case_insensitive(score_df, optional)
                    if col:
                        display_cols.append(col)
                st.dataframe(
                    score_df[display_cols].sort_values(by=trust_col, ascending=False),
                    use_container_width=True,
                )
            else:
                st.caption("No scoreboard rows.")

        with right:
            st.write("### Alerts by severity")
            sev_col = get_column_case_insensitive(alert_df, "severity")
            if not alert_df.empty and sev_col:
                sev = alert_df.groupby(sev_col).size().rename("count").to_frame()
                st.bar_chart(sev)
            else:
                st.caption("No alerts.")

        info_toggle("overview_trust_alert", T["overview_trust_alert_help"])

        st.write("### Trust / Uncertainty Explainability")
        ex1, ex2 = st.columns(2)
        ex1.success("🧭 " + T["trust_card"])
        ex2.warning("🌫️ " + T["uncertainty_card"])

elif pages[page] == "detail":
    sample_items = load_sample_markets()
    sample_by_id = {m["market_id"]: m for m in sample_items}

    market_items: list[dict[str, Any]] = []
    using_sample = bool(sample_items)
    mk_err = None

    if using_sample:
        market_items = sample_items
        st.caption(T["market_source_sample"])
    else:
        markets, mk_err = safe_get("/markets")
        market_items = [m for m in (markets or {}).get("items", []) if m.get("market_id")]
        st.caption(T["market_source_api"])

    if mk_err:
        st.error(T["safe_api_error"])
        st.caption(f"markets={mk_err}")
    elif not market_items:
        st.warning("No markets available.")
    else:
        labels = {market_label(item): item for item in market_items}
        selected_label = st.selectbox("Market", list(labels.keys()))
        selected = labels[selected_label]
        market_id = str(selected.get("market_id"))

        detail = None
        dt_err = None
        if is_calibrated_market_id(market_id):
            detail, dt_err = safe_get(f"/markets/{market_id}")

        if (dt_err == "HTTP 404" or not is_calibrated_market_id(market_id)) and market_id in sample_by_id:
            sample_meta = sample_by_id[market_id]
            st.info(T["market_meta_sample_fallback"])
            d1, d2, d3 = st.columns(3)
            d1.metric("Market ID", market_id)
            d2.metric("Question", sample_meta.get("question") or sample_meta.get("title") or "-")
            d3.metric("As of", str(sample_meta.get("as_of_ts") or "-"))
        elif dt_err and dt_err != "HTTP 404":
            st.error(T["safe_api_error"])
            st.caption(f"detail={dt_err}")
        elif detail:
            d1, d2, d3 = st.columns(3)
            d1.metric("Trust", f"{detail.get('trust_score', 0):.3f}" if detail.get("trust_score") is not None else "-")
            d2.metric("Category", detail.get("category") or "-")
            d3.metric("Liquidity", detail.get("liquidity_bucket") or "-")

        default_y = coerce_prob_series(selected.get("y"), limit=128)
        default_y_text = ",".join(f"{v:.4f}".rstrip("0").rstrip(".") for v in default_y[:128])
        if not default_y_text:
            default_y_text = "0.45,0.46,0.47,0.48,0.49,0.50,0.52,0.51,0.53,0.54"

        y = st.text_area(
            "Input y values (comma-separated)",
            default_y_text,
            key=f"detail-y-{market_id}",
        )
        detail_state = st.session_state.setdefault("detail_results_by_market", {})
        detail_answers = st.session_state.setdefault("detail_quick_answers_by_market", {})

        forecast_enabled = DEMO_FORECAST_ENABLED and FORECAST_TOKEN_VALID
        if not forecast_enabled:
            st.warning(T["forecast_token_hint"])

        if st.button("Run forecast", disabled=not forecast_enabled):
            try:
                vals = parse_series(y)
            except ValueError:
                st.warning(T["invalid_series"])
                vals = []
                if market_id in detail_state:
                    detail_state[market_id]["stale_warning"] = "Input parsing failed on latest rerun. Showing previous result."

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
                    if fc_err.startswith("HTTP 401") or fc_err.startswith("HTTP 403"):
                        st.warning(T["forecast_token_invalid"])
                        if market_id in detail_state:
                            detail_state[market_id]["stale_warning"] = "Forecast call blocked: invalid/expired token."
                    else:
                        st.error(T["safe_api_error"])
                        st.caption(f"forecast={fc_err}")
                        if market_id in detail_state:
                            detail_state[market_id]["stale_warning"] = f"Latest rerun failed ({fc_err}). Showing previous result."
                else:
                    detail_state[market_id] = {
                        "vals": vals,
                        "forecast": fc,
                        "as_of_ts": selected.get("as_of_ts"),
                        "stale_warning": None,
                    }
                    detail_answers[market_id] = {}

        saved_detail = detail_state.get(market_id)
        if not saved_detail:
            if not forecast_enabled:
                st.caption(T["forecast_token_hint"])
            else:
                st.caption("Run forecast to see results and quick answers." if lang == "en" else "예측 실행 후 결과와 빠른 질문 답변이 표시됩니다.")
        else:
            stale_warning = str(saved_detail.get("stale_warning") or "").strip()
            if stale_warning:
                st.caption(f"⚠️ {stale_warning}")

            vals = coerce_prob_series(saved_detail.get("vals", []), limit=512)
            fc = saved_detail.get("forecast", {}) if isinstance(saved_detail.get("forecast", {}), dict) else {}
            yhat = fc.get("yhat_q", {}) if isinstance(fc.get("yhat_q", {}), dict) else {}
            q10_raw = sanitize_quantile_series(yhat.get("0.1", []))
            q50_raw = sanitize_quantile_series(yhat.get("0.5", []))
            q90_raw = sanitize_quantile_series(yhat.get("0.9", []))

            lens = [len(q10_raw), len(q50_raw), len(q90_raw)]
            min_len = min(lens) if all(l > 0 for l in lens) else 0
            q_len_mismatch = len(set(lens)) > 1 and min_len > 0

            if min_len <= 0:
                st.write("### Forecast (q10 / q50 / q90)")
                info_toggle("detail_forecast", T["detail_forecast_help"])
                st.caption("Forecast quantiles unavailable or invalid." if lang == "en" else "예측 분위수 데이터가 없거나 유효하지 않습니다.")
                q10, q50, q90 = [], [], []
                fc_df = pd.DataFrame(columns=["step", "q10", "q50", "q90"])
            else:
                q10 = q10_raw[:min_len]
                q50 = q50_raw[:min_len]
                q90 = q90_raw[:min_len]
                horizon = list(range(1, min_len + 1))
                fc_df = pd.DataFrame({"step": horizon, "q10": q10, "q50": q50, "q90": q90})

                st.write("### Forecast (q10 / q50 / q90)")
                info_toggle("detail_forecast", T["detail_forecast_help"])
                if q_len_mismatch:
                    st.caption("Quantile length mismatch detected; trimmed to shortest series." if lang == "en" else "분위수 길이 불일치로 가장 짧은 길이에 맞춰 표시합니다.")
                st.line_chart(fc_df.set_index("step"))
                st.dataframe(fc_df, use_container_width=True)

            width = None
            if q10 and q90 and q50:
                width = q90[-1] - q10[-1]
                st.write("### Explainability")
                e1, e2 = st.columns(2)
                e1.info(f"Median path (q50) last step: {q50[-1]:.3f}")
                e2.warning(f"Uncertainty width (q90-q10) last step: {width:.3f}")

            st.write(f"### {T['live_change']}")
            live_color, live_msg = compute_live_change(vals)
            streamlit_notice(live_color, live_msg)
            if q90 and q10 and len(q90) >= 2 and len(q10) >= 2:
                prev_w = q90[-2] - q10[-2]
                now_w = q90[-1] - q10[-1]
                wmsg = (
                    "Uncertainty trend: widening."
                    if now_w - prev_w > 0.01
                    else "Uncertainty trend: narrowing."
                    if prev_w - now_w > 0.01
                    else "Uncertainty trend: stable."
                )
                if lang == "kr":
                    wmsg = "불확실성 추세: 확대." if now_w - prev_w > 0.01 else "불확실성 추세: 축소." if prev_w - now_w > 0.01 else "불확실성 추세: 안정."
                st.caption(wmsg)

            badge, reasons, badge_style = reliability_gate(saved_detail.get("as_of_ts"), bool(fc.get("used_fallback")), width)
            st.write(f"### {T['reliability_gate']}")
            streamlit_notice(badge_style, badge)
            with st.expander(T["why_this_badge"], expanded=False):
                for r in reasons:
                    st.write(f"- {r}")

            st.write(f"### {T['so_what']}")
            last_obs = vals[-1] if vals else None
            direction_up = bool(q50 and last_obs is not None and q50[-1] >= last_obs)
            conclusion = (
                f"Expected direction: {'up' if direction_up else 'down'} (confidence: {'high' if (width or 1) < 0.12 else 'moderate'})."
                if lang == "en"
                else f"예상 방향: {'상승' if direction_up else '하락'} (신뢰도: {'높음' if (width or 1) < 0.12 else '보통'})."
            )
            st.info(conclusion)
            bullets = [
                (f"Last observed value: {last_obs:.3f}" if (lang == "en" and last_obs is not None) else (f"최근 관측값: {last_obs:.3f}" if last_obs is not None else T["na_reason"])),
                (f"Forecast median (last step): {q50[-1]:.3f}" if q50 else T["na_reason"]),
                (f"Uncertainty width: {width:.3f}" if width is not None else T["na_reason"]),
            ]
            for b in bullets[:3]:
                st.write(f"- {b}")
            st.caption(("Use caution when uncertainty is wide." if (width or 1) > 0.18 else "Suitable for directional monitoring.") if lang == "en" else ("불확실성 폭이 넓어 해석에 주의가 필요합니다." if (width or 1) > 0.18 else "방향성 모니터링에 활용할 수 있습니다."))

            st.write(f"### {T['quick_answers']}")
            q1, q2, q3 = st.columns(3)
            market_answers = detail_answers.setdefault(market_id, {})
            if q1.button(T["question_why"], key=f"qwhy-{market_id}"):
                market_answers["why"] = ("Helps spot momentum changes early." if lang == "en" else "모멘텀 변화를 초기에 파악하는 데 도움이 됩니다.")
            if q2.button(T["question_risk"], key=f"qrisk-{market_id}"):
                market_answers["risk"] = (("Risk is elevated right now." if (width or 1) > 0.18 or fc.get("used_fallback") else "Risk is manageable right now.") if lang == "en" else ("현재 리스크가 높은 편입니다." if (width or 1) > 0.18 or fc.get("used_fallback") else "현재 리스크는 관리 가능한 수준입니다."))
            if q3.button(T["question_summary"], key=f"qsum-{market_id}"):
                market_answers["summary"] = conclusion

            for qa_key in ["why", "risk", "summary"]:
                msg = market_answers.get(qa_key)
                if msg:
                    st.info(msg)

        pm = None
        pm_err = None
        if is_calibrated_market_id(market_id):
            pm, pm_err = safe_get(f"/postmortem/{market_id}")
        elif market_id in sample_by_id:
            pm = {"content": sample_by_id[market_id].get("question") or sample_by_id[market_id].get("title") or ""}

        if not pm_err and pm:
            with st.expander("Latest Postmortem", expanded=False):
                st.markdown(pm.get("content", ""))
        elif pm_err == "HTTP 404" and is_calibrated_market_id(market_id):
            with st.expander("Latest Postmortem", expanded=False):
                st.caption("No postmortem available yet for this calibrated market." if lang == "en" else "이 캘리브레이션 마켓의 포스트모템이 아직 없습니다.")

elif pages[page] == "compare":
    sample_items = load_sample_markets()
    using_sample = bool(sample_items)
    mk_err = None

    if using_sample:
        market_items = sample_items
        st.caption(T["market_source_sample"])
    else:
        markets, mk_err = safe_get("/markets")
        market_items = [m for m in (markets or {}).get("items", []) if m.get("market_id")]
        st.caption(T["market_source_api"])

    if mk_err:
        st.error(T["safe_api_error"])
        st.caption(f"markets={mk_err}")
    elif not market_items:
        st.warning("No markets available.")
    else:
        labels = {market_label(item): item for item in market_items}
        selected_label = st.selectbox("Market", list(labels.keys()), key="cmp-market")
        selected = labels[selected_label]
        market_id = str(selected.get("market_id"))

        default_y = coerce_prob_series(selected.get("y"), limit=128)
        default_y_text = ",".join(f"{v:.4f}".rstrip("0").rstrip(".") for v in default_y[:128])
        if not default_y_text:
            default_y_text = "0.41,0.42,0.43,0.44,0.45,0.46,0.47,0.48,0.49,0.50"

        y = st.text_area("Input y values", default_y_text, key=f"cmp-y-{market_id}")

        cmp_state = st.session_state.setdefault("compare_results_by_market", {})
        cmp_answers = st.session_state.setdefault("compare_quick_answers_by_market", {})

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
                    cmp_state[market_id] = {
                        "vals": vals,
                        "cmp_result": cmp_result,
                        "as_of_ts": selected.get("as_of_ts"),
                    }
                    cmp_answers[market_id] = {}

        saved = cmp_state.get(market_id)
        if not saved:
            st.caption("Run comparison to see results and quick answers." if lang == "en" else "비교 실행 후 결과와 빠른 질문 답변이 표시됩니다.")
        else:
            vals = coerce_prob_series(saved.get("vals", []), limit=512)
            cmp_result = saved.get("cmp_result", {}) if isinstance(saved.get("cmp_result", {}), dict) else {}
            baseline_full = cmp_result.get("baseline", {}) if isinstance(cmp_result.get("baseline", {}), dict) else {}
            tollama_full = cmp_result.get("tollama", {}) if isinstance(cmp_result.get("tollama", {}), dict) else {}
            baseline = sanitize_yhat_q_map(baseline_full.get("yhat_q"))
            tollama = sanitize_yhat_q_map(tollama_full.get("yhat_q"))

            compare_warnings: list[str] = []
            if not baseline or not tollama:
                compare_warnings.append(T["compare_warn_invalid_quantiles"])

            baseline_last, _, baseline_trimmed = overlap_quantiles(baseline, ["0.1", "0.5", "0.9"])
            tollama_last, _, tollama_trimmed = overlap_quantiles(tollama, ["0.1", "0.5", "0.9"])
            if baseline_trimmed or tollama_trimmed:
                compare_warnings.append(T["compare_warn_quantile_trim"])

            def last_val(block: dict[str, list[float]], q: str) -> float | None:
                seq = block.get(q, [])
                return seq[-1] if seq else None

            rows = []
            for q in ["0.1", "0.5", "0.9"]:
                b = last_val(baseline_last, q)
                t = last_val(tollama_last, q)
                d = (t - b) if b is not None and t is not None else None
                rows.append({"quantile": q, "baseline_last": b, "tollama_last": t, "delta": d})

            cmp_df = pd.DataFrame(rows)
            st.write(f"### {T['battleboard']}")
            for warn_msg in dict.fromkeys(compare_warnings):
                st.caption(f"⚠️ {warn_msg}")
            st.dataframe(cmp_df, use_container_width=True)

            n = len(vals)
            split = max(3, int(n * 0.7))
            test_y = vals[split:]
            horizon = len(test_y)

            def quantile_preds_for_horizon(block: dict[str, list[float]], target_horizon: int) -> dict[str, list[float]]:
                if target_horizon <= 0:
                    return {"0.1": [], "0.5": [], "0.9": []}
                return {q: block.get(q, [])[:target_horizon] for q in ["0.1", "0.5", "0.9"]}

            b_preds = quantile_preds_for_horizon(baseline, horizon)
            t_preds = quantile_preds_for_horizon(tollama, horizon)
            bq50 = b_preds.get("0.5", [])
            tq50 = t_preds.get("0.5", [])
            b_metrics = calc_metrics(test_y, bq50, vals[:split], b_preds) if horizon > 0 and len(bq50) == horizon else calc_metrics([], [], [])
            t_metrics = calc_metrics(test_y, tq50, vals[:split], t_preds) if horizon > 0 and len(tq50) == horizon else calc_metrics([], [], [])

            def metric_or_na(v: float | None, reason: str) -> str:
                return f"{v:.4f}" if (v is not None and math.isfinite(v)) else f"{T['metric_na']} ({reason})"

            b_latency_raw = value_from_top_or_meta(baseline_full, "latency_ms")
            if b_latency_raw is None:
                b_latency_raw = cmp_result.get("baseline_latency_ms")
            t_latency_raw = value_from_top_or_meta(tollama_full, "latency_ms")
            if t_latency_raw is None:
                t_latency_raw = cmp_result.get("tollama_latency_ms")
            b_latency = _coerce_float(b_latency_raw)
            t_latency = _coerce_float(t_latency_raw)

            b_runtime_raw = value_from_top_or_meta(baseline_full, "runtime")
            t_runtime_raw = value_from_top_or_meta(tollama_full, "runtime")

            b_fallback_raw = value_from_top_or_meta_aliases(baseline_full, ["used_fallback", "fallback_used"])
            t_fallback_raw = value_from_top_or_meta_aliases(tollama_full, ["used_fallback", "fallback_used"])
            b_fallback = coerce_optional_bool(b_fallback_raw)
            t_fallback = coerce_optional_bool(t_fallback_raw)

            def latency_text(latency_ms: float | None, runtime_raw: Any) -> str:
                if latency_ms is not None:
                    return f"{float(latency_ms):.1f}ms"
                runtime = _coerce_float(runtime_raw)
                if runtime is not None:
                    return f"{runtime:.3f}s"
                return f"{T['metric_na']} ({T['na_not_provided']})"

            reason = T["na_short_window"]
            board = pd.DataFrame(
                [
                    {
                        "model": "Baseline",
                        "MAE": metric_or_na(b_metrics["mae"], reason),
                        "MAPE": metric_or_na(b_metrics["mape"], reason),
                        "MASE": metric_or_na(b_metrics["mase"], reason),
                        "Pinball q10": metric_or_na(b_metrics["pinball_0.1"], reason),
                        "Pinball q50": metric_or_na(b_metrics["pinball_0.5"], reason),
                        "Pinball q90": metric_or_na(b_metrics["pinball_0.9"], reason),
                        T["latency"]: latency_text(b_latency, b_runtime_raw),
                        T["fallback_status"]: ("ON" if b_fallback else "OFF") if b_fallback is not None else f"{T['metric_na']} ({T['na_not_provided']})",
                    },
                    {
                        "model": "Tollama",
                        "MAE": metric_or_na(t_metrics["mae"], reason),
                        "MAPE": metric_or_na(t_metrics["mape"], reason),
                        "MASE": metric_or_na(t_metrics["mase"], reason),
                        "Pinball q10": metric_or_na(t_metrics["pinball_0.1"], reason),
                        "Pinball q50": metric_or_na(t_metrics["pinball_0.5"], reason),
                        "Pinball q90": metric_or_na(t_metrics["pinball_0.9"], reason),
                        T["latency"]: latency_text(t_latency, t_runtime_raw),
                        T["fallback_status"]: ("ON" if t_fallback else "OFF") if t_fallback is not None else f"{T['metric_na']} ({T['na_not_provided']})",
                    },
                ]
            )
            st.write(f"### {T['holdout_eval']}")
            st.dataframe(board, use_container_width=True, hide_index=True)

            d50 = _coerce_float(cmp_result.get("delta_last_q50"))
            if d50 is None:
                st.info("Δ q50 unavailable")
            elif abs(d50) < 0.01:
                st.success(f"Δ q50: {d50:+.4f} (aligned)")
            elif abs(d50) < 0.03:
                st.warning(f"Δ q50: {d50:+.4f} (watch)")
            else:
                st.error(f"Δ q50: {d50:+.4f} (large)")

            width = None
            t_q90_last = last_val(tollama_last, "0.9")
            t_q10_last = last_val(tollama_last, "0.1")
            if t_q90_last is not None and t_q10_last is not None:
                width = t_q90_last - t_q10_last
            badge, reasons, badge_style = reliability_gate(saved.get("as_of_ts"), bool(t_fallback), width)
            st.write(f"### {T['reliability_gate']}")
            streamlit_notice(badge_style, badge)
            with st.expander(T["why_this_badge"], expanded=False):
                for r in reasons:
                    st.write(f"- {r}")

            st.write(f"### {T['so_what']}")
            winner = "Tollama" if (t_metrics.get("mae") is not None and b_metrics.get("mae") is not None and t_metrics["mae"] <= b_metrics["mae"]) else "Baseline"
            st.info((f"Current lead: {winner} for this market." if lang == "en" else f"현재 이 마켓의 우세 모델: {winner}."))
            ev = [
                (f"MAE: Baseline {metric_or_na(b_metrics['mae'], reason)} vs Tollama {metric_or_na(t_metrics['mae'], reason)}"),
                (f"Pinball q50: Baseline {metric_or_na(b_metrics['pinball_0.5'], reason)} vs Tollama {metric_or_na(t_metrics['pinball_0.5'], reason)}"),
                (f"Fallback: Baseline {(b_fallback if b_fallback is not None else 'N/A')}, Tollama {(t_fallback if t_fallback is not None else 'N/A')}"),
            ]
            for b in ev[:3]:
                st.write(f"- {b}")
            st.caption(("Use caution when the holdout window is short." if lang == "en" else "홀드아웃 구간이 짧으면 해석에 주의하세요."))

            st.write(f"### {T['live_change']}")
            lc, lm = compute_live_change(vals)
            streamlit_notice(lc, lm)

            st.write(f"### {T['quick_answers']}")
            q1, q2, q3 = st.columns(3)
            market_answers = cmp_answers.setdefault(market_id, {})
            if q1.button(T["question_why"], key=f"cmp-qwhy-{market_id}"):
                market_answers["why"] = ("Checks whether model gains hold against fallback." if lang == "en" else "모델 개선이 대체 경로 대비 유효한지 확인합니다.")
            if q2.button(T["question_risk"], key=f"cmp-qrisk-{market_id}"):
                high_risk = bool(t_fallback) or (width is not None and width > 0.18)
                market_answers["risk"] = (("Risk is elevated right now." if high_risk else "Risk is moderate right now.") if lang == "en" else ("현재 리스크가 높은 편입니다." if high_risk else "현재 리스크는 보통 수준입니다."))
            if q3.button(T["question_summary"], key=f"cmp-qsum-{market_id}"):
                market_answers["summary"] = (f"Based on current evidence, {winner} is ahead." if lang == "en" else f"현재 근거 기준으로 {winner}가 우세합니다.")

            for qa_key in ["why", "risk", "summary"]:
                msg = market_answers.get(qa_key)
                if msg:
                    st.info(msg)

            info_toggle("compare", T["compare_help"])

elif pages[page] == "obs":
    try:
        metrics_text = httpx.get(f"{API_BASE}/metrics", timeout=10.0)
        metrics_text.raise_for_status()
    except httpx.HTTPError:
        st.error(T["safe_api_error"])
    else:
        parsed = parse_prom_metrics(metrics_text.text)

        def first_metric(*names: str) -> float | None:
            for name in names:
                v = _coerce_float(parsed.get(name))
                if v is not None:
                    return v
            return None

        req = first_metric("tsfm_request_total", "tsfm_requests_total") or 0.0
        err = first_metric("tsfm_errors_total") or 0.0

        lat_ms_sum = first_metric("tsfm_request_latency_ms_sum")
        lat_ms_cnt = first_metric("tsfm_request_latency_ms_count")
        lat_s_sum = first_metric("tsfm_latency_seconds_sum")
        lat_s_cnt = first_metric("tsfm_latency_seconds_count")

        avg_latency_s: float | None = None
        if lat_ms_sum is not None and lat_ms_cnt is not None and lat_ms_cnt > 0:
            avg_latency_s = (lat_ms_sum / lat_ms_cnt) / 1000.0
        elif lat_s_sum is not None and lat_s_cnt is not None and lat_s_cnt > 0:
            avg_latency_s = lat_s_sum / lat_s_cnt

        cache_hit = first_metric("tsfm_cache_hit_total", "tsfm_cache_hits_total") or 0.0
        cache_miss = first_metric("tsfm_cache_miss_total", "tsfm_cache_misses_total")
        fallback = first_metric("tsfm_fallback_total") or 0.0

        err_rate = (err / req) if req > 0 else 0.0
        hit_rate: float | None = None
        hit_rate_reason: str | None = None
        if cache_miss is None:
            hit_rate_reason = "miss metric not provided"
        elif (cache_hit + cache_miss) <= 0:
            hit_rate_reason = "no cache events"
        else:
            hit_rate = cache_hit / (cache_hit + cache_miss)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Requests", int(req))
        c2.metric("Error rate", f"{err_rate:.2%}")
        c3.metric("Fallback (cumulative)", int(fallback))
        c4.metric("Avg latency", f"{avg_latency_s:.3f}s" if avg_latency_s is not None else T["metric_na"])
        c5.metric("Cache hit rate", f"{hit_rate:.2%}" if hit_rate is not None else f"{T['metric_na']} ({hit_rate_reason or T['na_not_provided']})")
        info_toggle("obs", T["obs_help"])

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
