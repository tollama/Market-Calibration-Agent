"""Market template inference for resolved-dataset enrichment."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Mapping

_STOPWORDS = {
    "a",
    "an",
    "and",
    "approval",
    "by",
    "for",
    "if",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "will",
    "with",
}
_POLITICS_WORDS = {
    "election",
    "president",
    "presidential",
    "senate",
    "governor",
    "house",
    "congress",
    "campaign",
    "candidate",
    "vote",
    "voting",
    "ballot",
    "poll",
    "approval",
    "approve",
    "disapprove",
}
_WAR_WORDS = {
    "war",
    "ceasefire",
    "peace",
    "attack",
    "strike",
    "troops",
    "sanction",
    "hostage",
    "missile",
}
_ETF_WORDS = {"etf", "sec", "19b-4", "s-1", "approval", "approve", "spot"}
_SPORTS_WORDS = {
    "sports",
    "nba",
    "nfl",
    "mlb",
    "nhl",
    "ufc",
    "soccer",
    "football",
    "basketball",
    "tennis",
}
_SPORTS_PROP_WORDS = {
    "points",
    "rebounds",
    "assists",
    "yards",
    "touchdowns",
    "goals",
    "shots",
    "saves",
    "strikeouts",
}


@dataclass(frozen=True)
class MarketTemplateFeatures:
    market_template: str = "generic"
    template_group: str = "generic"
    template_confidence: float = 0.35
    template_entity_count: int = 0
    query_terms: list[str] = field(default_factory=list)
    poll_mode: str = "none"


def infer_market_template(
    *,
    question: str,
    category: str = "",
    slug: str = "",
) -> MarketTemplateFeatures:
    question_text = str(question or "").strip()
    category_text = str(category or "").strip()
    slug_text = str(slug or "").replace("-", " ").strip()
    corpus = " ".join(part for part in (question_text, category_text, slug_text) if part).lower()
    entity_terms = _extract_entity_terms(question_text)
    query_terms = _build_query_terms(question_text, slug_text, entity_terms)
    category_lower = category_text.lower()

    has_etf_context = any(word in corpus for word in ("etf", "sec", "19b-4", "s-1", "spot"))
    if has_etf_context and any(word in corpus for word in _ETF_WORDS):
        return MarketTemplateFeatures(
            market_template="etf_approval",
            template_group="finance",
            template_confidence=0.9,
            template_entity_count=len(entity_terms),
            query_terms=query_terms,
            poll_mode="none",
        )
    if _contains_any(corpus, _POLITICS_WORDS) or "politics" in category_lower:
        market_template = "politics_candidate"
        poll_mode = "candidate"
        confidence = 0.82
        if "approval" in corpus or "disapprove" in corpus:
            market_template = "politics_approval"
            poll_mode = "approval"
            confidence = 0.9
        elif "generic ballot" in corpus:
            market_template = "politics_generic_ballot"
            poll_mode = "generic_ballot"
            confidence = 0.9
        elif "control" in corpus and any(word in corpus for word in ("senate", "house", "congress")):
            market_template = "politics_party_control"
            poll_mode = "none"
            confidence = 0.87
        return MarketTemplateFeatures(
            market_template=market_template,
            template_group="politics",
            template_confidence=confidence,
            template_entity_count=len(entity_terms),
            query_terms=query_terms,
            poll_mode=poll_mode,
        )
    if _contains_any(corpus, _WAR_WORDS):
        return MarketTemplateFeatures(
            market_template="war_diplomacy",
            template_group="geopolitics",
            template_confidence=0.84,
            template_entity_count=len(entity_terms),
            query_terms=query_terms,
            poll_mode="none",
        )
    if _contains_any(corpus, _SPORTS_WORDS) or "sports" in category_lower:
        template = "sports_player_prop" if _contains_any(corpus, _SPORTS_PROP_WORDS) else "sports_match"
        return MarketTemplateFeatures(
            market_template=template,
            template_group="sports",
            template_confidence=0.8 if template == "sports_player_prop" else 0.76,
            template_entity_count=len(entity_terms),
            query_terms=query_terms,
            poll_mode="none",
        )
    return MarketTemplateFeatures(
        market_template="generic",
        template_group="generic",
        template_confidence=0.35,
        template_entity_count=len(entity_terms),
        query_terms=query_terms,
        poll_mode="none",
    )


def build_market_template_features(row: Mapping[str, Any]) -> dict[str, Any]:
    question = str(row.get("question") or row.get("title") or "")
    category = str(row.get("category") or "")
    slug = str(row.get("slug") or "")
    return asdict(infer_market_template(question=question, category=category, slug=slug))


def _contains_any(text: str, tokens: set[str]) -> bool:
    return any(token in text for token in tokens)


def _extract_entity_terms(question: str) -> list[str]:
    matches = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", question or "")
    seen: set[str] = set()
    entities: list[str] = []
    for match in matches:
        token = match.strip()
        if token.lower() in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        entities.append(token)
    return entities


def _build_query_terms(question: str, slug: str, entity_terms: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for entity in entity_terms:
        lowered = entity.lower()
        if lowered not in seen:
            seen.add(lowered)
            terms.append(lowered)

    token_source = f"{question} {slug}".lower()
    for token in re.findall(r"[a-z0-9]+", token_source):
        if token in _STOPWORDS or len(token) < 3 or token in seen:
            continue
        seen.add(token)
        terms.append(token)
        if len(terms) >= 6:
            break
    return terms


__all__ = [
    "MarketTemplateFeatures",
    "build_market_template_features",
    "infer_market_template",
]
