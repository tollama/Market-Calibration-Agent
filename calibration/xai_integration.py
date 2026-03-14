"""
market_calibration.xai — XAI Integration for Market Calibration Agent

v3.8 Phase 2a: Trust Score Breakdown 제품화
"왜 이 외부 신호를 반영해야 하는가?"에 대한 정량적 근거 생성.

기존 Trust Score 산출 파이프라인의 출력을 확장하여:
- 각 구성요소별 기여도 분해
- 신뢰 수준 평가 (High/Medium/Low)
- 시간에 따른 calibration drift 감지
- Decision-ready evidence package 생성
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


class TrustScoreExplainer:
    """
    Extends Market Calibration Agent's Trust Score with structured explanations.

    Trust Score = composite of:
    - Brier Score (probability accuracy)
    - Log Loss (confidence penalization)
    - ECE (calibration quality)
    - Volume (information quality proxy)
    - Recency (signal freshness)
    - Resolution clarity (outcome definiteness)
    """

    THRESHOLDS = {
        "high_trust": 0.75,
        "medium_trust": 0.50,
        "low_trust": 0.25,
    }

    METRIC_WEIGHTS = {
        "brier_score": 0.30,
        "log_loss": 0.20,
        "ece": 0.25,
        "volume": 0.10,
        "recency": 0.10,
        "resolution_clarity": 0.05,
    }

    def explain_trust_score(
        self,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate Trust Score explanation from market calibration data.

        Parameters
        ----------
        market_data : dict
            Market Calibration Agent output:
              - market_id: str
              - current_probability: float
              - trust_score: float
              - metrics: {brier_score, log_loss, ece, ...}
              - tsfm_signal: {forecast: [...]}
              - metadata: {...}

        Returns
        -------
        dict with structured trust explanation
        """
        trust_score = market_data.get("trust_score", 0.0)
        metrics = market_data.get("metrics", {})
        market_id = market_data.get("market_id", "unknown")
        current_prob = market_data.get("current_probability", 0.0)

        # Trust level assessment
        trust_level = self._assess_trust_level(trust_score)

        # Component breakdown
        breakdown = self._decompose_components(metrics)

        # Calibration quality assessment
        calibration = self._assess_calibration(metrics)

        # TSFM signal comparison
        tsfm_comparison = self._compare_with_tsfm(
            current_prob, market_data.get("tsfm_signal", {})
        )

        # Generate explanation text
        explanation_text = self._generate_explanation(
            trust_score, trust_level, breakdown, calibration, tsfm_comparison
        )

        # Build evidence package
        evidence = {
            "market_id": market_id,
            "current_probability": current_prob,
            "trust_score": trust_score,
            "trust_level": trust_level,
            "component_breakdown": breakdown,
            "calibration_assessment": calibration,
            "tsfm_comparison": tsfm_comparison,
            "explanation": explanation_text,
            "recommendation": self._generate_recommendation(
                trust_score, trust_level, calibration
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "xai_version": "0.1.0",
        }

        return evidence

    def explain_calibration_drift(
        self,
        historical_scores: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Detect and explain calibration drift over time.

        Parameters
        ----------
        historical_scores : list[dict]
            List of {timestamp, trust_score, metrics} over time

        Returns
        -------
        dict with drift analysis
        """
        if len(historical_scores) < 2:
            return {"drift_detected": False, "reason": "Insufficient history"}

        scores = [s.get("trust_score", 0) for s in historical_scores]
        recent = scores[-min(5, len(scores)):]
        older = scores[:max(1, len(scores) - 5)]

        recent_avg = sum(recent) / len(recent) if recent else 0
        older_avg = sum(older) / len(older) if older else 0
        drift = recent_avg - older_avg

        drift_detected = abs(drift) > 0.1  # 10% change threshold

        return {
            "drift_detected": drift_detected,
            "drift_magnitude": round(drift, 4),
            "direction": "improving" if drift > 0 else "degrading",
            "recent_average": round(recent_avg, 4),
            "historical_average": round(older_avg, 4),
            "n_observations": len(historical_scores),
            "explanation": (
                f"Trust score has {'improved' if drift > 0 else 'degraded'} "
                f"by {abs(drift):.2f} over recent observations. "
                f"{'Action may be needed.' if drift_detected and drift < 0 else ''}"
            ),
        }

    def build_signal_evidence_package(
        self,
        trust_explanation: dict[str, Any],
        market_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build a complete evidence package for decision input stage.

        This is the artifact consumed by ExplanationEngine's input_explanation.
        """
        return {
            "signal_type": "prediction_market",
            "source": market_data.get("source", market_data.get("platform", "polymarket")),
            "market_id": market_data.get("market_id", ""),
            "probability": market_data.get("current_probability", 0.0),
            "trust_score": trust_explanation.get("trust_score", 0.0),
            "trust_level": trust_explanation.get("trust_level", "unknown"),
            "why_trusted": trust_explanation.get("explanation", ""),
            "key_metrics": {
                k: v.get("value")
                for k, v in trust_explanation.get("component_breakdown", {}).items()
                if v.get("value") is not None
            },
            "recommendation": trust_explanation.get("recommendation", ""),
            "evidence_quality": "quantitative",
            "audit_ready": True,
        }

    # ── Private methods ──

    def _assess_trust_level(self, score: float) -> str:
        if score >= self.THRESHOLDS["high_trust"]:
            return "high"
        elif score >= self.THRESHOLDS["medium_trust"]:
            return "medium"
        elif score >= self.THRESHOLDS["low_trust"]:
            return "low"
        return "very_low"

    def _decompose_components(self, metrics: dict[str, float]) -> dict[str, Any]:
        breakdown = {}
        for component, weight in self.METRIC_WEIGHTS.items():
            value = metrics.get(component)
            if value is None:
                breakdown[component] = {
                    "value": None,
                    "weight": weight,
                    "contribution": 0.0,
                    "quality": "unavailable",
                }
                continue

            # Normalize (component-specific)
            if component in ("brier_score", "log_loss", "ece"):
                # Lower is better
                good_threshold = {"brier_score": 0.2, "log_loss": 0.5, "ece": 0.05}
                normalized = max(0, 1 - (value / (good_threshold.get(component, 0.5) * 3)))
            else:
                # Higher is better
                normalized = min(1.0, value)

            contribution = normalized * weight
            if normalized >= 0.8:
                quality = "excellent"
            elif normalized >= 0.6:
                quality = "good"
            elif normalized >= 0.4:
                quality = "fair"
            else:
                quality = "poor"

            breakdown[component] = {
                "value": round(value, 4),
                "weight": weight,
                "normalized": round(normalized, 4),
                "contribution": round(contribution, 4),
                "quality": quality,
            }

        return breakdown

    def _assess_calibration(self, metrics: dict[str, float]) -> dict[str, Any]:
        ece = metrics.get("ece")
        brier = metrics.get("brier_score")

        if ece is None and brier is None:
            return {"status": "unknown", "detail": "Calibration metrics not available"}

        quality = "unknown"
        if ece is not None:
            if ece < 0.05:
                quality = "well_calibrated"
            elif ece < 0.10:
                quality = "moderately_calibrated"
            else:
                quality = "poorly_calibrated"

        return {
            "status": quality,
            "ece": ece,
            "brier_score": brier,
            "detail": {
                "well_calibrated": "Predicted probabilities closely match actual frequencies",
                "moderately_calibrated": "Reasonable calibration with room for improvement",
                "poorly_calibrated": "Significant gap between predictions and outcomes",
            }.get(quality, ""),
        }

    def _compare_with_tsfm(
        self,
        market_prob: float,
        tsfm_signal: dict[str, Any],
    ) -> dict[str, Any]:
        forecasts = tsfm_signal.get("forecast", [])
        if not forecasts:
            return {"available": False}

        tsfm_avg = sum(forecasts) / len(forecasts)
        divergence = abs(market_prob - tsfm_avg)

        return {
            "available": True,
            "market_probability": market_prob,
            "tsfm_average": round(tsfm_avg, 4),
            "divergence": round(divergence, 4),
            "alignment": (
                "aligned" if divergence < 0.05
                else "moderate_divergence" if divergence < 0.15
                else "significant_divergence"
            ),
            "note": (
                f"TSFM forecast ({tsfm_avg:.2f}) "
                f"{'aligns with' if divergence < 0.05 else 'diverges from'} "
                f"market probability ({market_prob:.2f})"
            ),
        }

    def _generate_explanation(
        self,
        score: float,
        level: str,
        breakdown: dict,
        calibration: dict,
        tsfm: dict,
    ) -> str:
        level_text = {
            "high": "High trust",
            "medium": "Moderate trust",
            "low": "Low trust — exercise caution",
            "very_low": "Very low trust — not recommended as primary signal",
        }

        text = f"{level_text.get(level, 'Unknown')} (score: {score:.2f}). "

        # Highlight strong components
        strong = [
            k for k, v in breakdown.items()
            if v.get("quality") in ("excellent", "good") and v.get("value") is not None
        ]
        if strong:
            text += f"Strong on: {', '.join(strong)}. "

        # Calibration
        cal_status = calibration.get("status", "unknown")
        if cal_status == "well_calibrated":
            text += "Well-calibrated predictions. "
        elif cal_status == "poorly_calibrated":
            text += "Calibration quality is poor — probabilities may be unreliable. "

        # TSFM comparison
        if tsfm.get("available"):
            alignment = tsfm.get("alignment", "")
            if alignment == "significant_divergence":
                text += (
                    f"Warning: significant divergence between market "
                    f"({tsfm.get('market_probability', 0):.2f}) and TSFM "
                    f"({tsfm.get('tsfm_average', 0):.2f}). "
                )

        return text.strip()

    def _generate_recommendation(
        self,
        score: float,
        level: str,
        calibration: dict,
    ) -> str:
        if level == "high":
            return "Signal can be used as a primary input with standard confidence."
        elif level == "medium":
            return (
                "Signal acceptable as supporting input. "
                "Combine with additional sources for critical decisions."
            )
        elif level == "low":
            return (
                "Signal quality insufficient for standalone use. "
                "Supplement with corroborating signals and domain expertise."
            )
        return (
            "Signal not recommended for decision input. "
            "Seek alternative signal sources."
        )
