from __future__ import annotations

from agents.explain_validator import validate_evidence_bound


def test_validate_evidence_bound_nominal_case() -> None:
    source = "공식 발표에 따르면 2026-02-20 확정이며 확률은 45%다."
    lines = [
        "공식 발표 기준 2026년 2월 20일 확률 45%를 반영했다",
        "확정된 일정에 맞춰 해석한다",
        "시장 반응을 함께 본다",
        "추가 변수는 남아 있다",
        "투자 판단은 신중히 한다",
    ]

    result = validate_evidence_bound(lines=lines, source_text=source)

    assert result["is_valid"] is True
    assert result["violation_lines"] == []
    assert result["reason_codes"] == []


def test_validate_evidence_bound_flags_new_numeric_token() -> None:
    source = "시장 분위기는 중립적이다."
    lines = [
        "확률은 73%로 본다",
        "추가 해설",
        "맥락 정리",
        "리스크 유의",
        "결론 요약",
    ]

    result = validate_evidence_bound(lines=lines, source_text=source)

    assert result["is_valid"] is False
    assert result["violation_lines"] == [1]
    assert "NEW_NUMERIC_TOKEN" in result["reason_codes"]


def test_validate_evidence_bound_flags_unsupported_absolute_claim() -> None:
    source = "정보가 제한적이어서 방향성은 불확실하다."
    lines = [
        "반드시 상승한다",
        "시장 맥락",
        "변수 점검",
        "리스크 정리",
        "최종 요약",
    ]

    result = validate_evidence_bound(lines=lines, source_text=source)

    assert result["is_valid"] is False
    assert result["violation_lines"] == [1]
    assert "UNSUPPORTED_ABSOLUTE_CLAIM" in result["reason_codes"]


def test_validate_evidence_bound_accumulates_reason_codes() -> None:
    source = "방향성은 아직 가변적이다."
    lines = [
        "반드시 90% 이상 오른다",
        "맥락 정리",
        "변수 점검",
        "리스크 관리",
        "요약",
    ]

    result = validate_evidence_bound(lines=lines, source_text=source)

    assert result["is_valid"] is False
    assert result["violation_lines"] == [1]
    assert result["reason_codes"] == ["NEW_NUMERIC_TOKEN", "UNSUPPORTED_ABSOLUTE_CLAIM"]
