"""Deterministic evidence-bound validator for explain lines."""

from __future__ import annotations

import re

_REASON_NEW_NUMERIC_TOKEN = "NEW_NUMERIC_TOKEN"
_REASON_UNSUPPORTED_ABSOLUTE_CLAIM = "UNSUPPORTED_ABSOLUTE_CLAIM"

_ABSOLUTE_PHRASES = (
    "반드시",
    "확실",
    "확정",
    "절대",
    "무조건",
    "틀림없",
    "분명",
    "보장",
    "100%",
)
_ABSOLUTE_BASIS_CUES = (
    "공식",
    "발표",
    "확정",
    "판결",
    "결정",
    "확인",
    "수치",
    "통계",
    "데이터",
    "근거",
)

_DATE_NUMERIC_RE = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_DATE_KR_FULL_RE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
_DATE_KR_MONTH_DAY_RE = re.compile(r"(?<!\d)(\d{1,2})월\s*(\d{1,2})일")
_PERCENT_RE = re.compile(r"(?<!\w)([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*%")
_NUMBER_RE = re.compile(r"(?<!\w)[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w)")


def validate_evidence_bound(lines: list[str], source_text: str) -> dict:
    """Validate that lines stay grounded in source text evidence."""
    source = source_text or ""
    source_tokens = _extract_quantitative_tokens(source)

    violation_lines: set[int] = set()
    reason_codes: set[str] = set()

    for line_no, line in enumerate(lines, start=1):
        content = line or ""

        line_tokens = _extract_quantitative_tokens(content)
        if any(token not in source_tokens for token in line_tokens):
            violation_lines.add(line_no)
            reason_codes.add(_REASON_NEW_NUMERIC_TOKEN)

        if _contains_absolute_phrase(content) and not _has_absolute_basis(source):
            violation_lines.add(line_no)
            reason_codes.add(_REASON_UNSUPPORTED_ABSOLUTE_CLAIM)

    ordered_lines = sorted(violation_lines)
    ordered_reasons = sorted(reason_codes)
    return {
        "is_valid": not ordered_lines,
        "violation_lines": ordered_lines,
        "reason_codes": ordered_reasons,
    }


def _extract_quantitative_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    consumed_spans: list[tuple[int, int]] = []

    for match in _DATE_NUMERIC_RE.finditer(text):
        consumed_spans.append(match.span())
        year, month, day = match.groups()
        tokens.add(f"date:{int(year)}-{int(month)}-{int(day)}")

    for match in _DATE_KR_FULL_RE.finditer(text):
        consumed_spans.append(match.span())
        year, month, day = match.groups()
        tokens.add(f"date:{int(year)}-{int(month)}-{int(day)}")

    for match in _DATE_KR_MONTH_DAY_RE.finditer(text):
        if _overlaps(match.span(), consumed_spans):
            continue
        consumed_spans.append(match.span())
        month, day = match.groups()
        tokens.add(f"month_day:{int(month)}-{int(day)}")

    for match in _PERCENT_RE.finditer(text):
        if _overlaps(match.span(), consumed_spans):
            continue
        consumed_spans.append(match.span())
        normalized_number = _normalize_number(match.group(1))
        if normalized_number is not None:
            tokens.add(f"pct:{normalized_number}")

    for match in _NUMBER_RE.finditer(text):
        if _overlaps(match.span(), consumed_spans):
            continue
        normalized_number = _normalize_number(match.group())
        if normalized_number is not None:
            tokens.add(f"num:{normalized_number}")

    return tokens


def _normalize_number(raw: str) -> str | None:
    token = raw.strip().replace(",", "")
    token = token.replace(" ", "")
    if token.startswith("+"):
        token = token[1:]

    if not re.fullmatch(r"-?\d+(?:\.\d+)?", token):
        return None

    sign = ""
    if token.startswith("-"):
        sign = "-"
        token = token[1:]

    if "." in token:
        integer_part, fractional_part = token.split(".", maxsplit=1)
        integer_part = integer_part.lstrip("0") or "0"
        fractional_part = fractional_part.rstrip("0")
        normalized = integer_part if not fractional_part else f"{integer_part}.{fractional_part}"
    else:
        normalized = token.lstrip("0") or "0"

    if normalized == "0":
        sign = ""
    return f"{sign}{normalized}"


def _overlaps(span: tuple[int, int], consumed_spans: list[tuple[int, int]]) -> bool:
    start, end = span
    for consumed_start, consumed_end in consumed_spans:
        if start < consumed_end and consumed_start < end:
            return True
    return False


def _contains_absolute_phrase(text: str) -> bool:
    return any(phrase in text for phrase in _ABSOLUTE_PHRASES)


def _has_absolute_basis(source_text: str) -> bool:
    return any(cue in source_text for cue in _ABSOLUTE_BASIS_CUES)

