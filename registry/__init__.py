"""Registry package exports."""

from .build_registry import RegistryBuildResult, build_market_registry, build_registry
from .conflict_rules import (
    CONFLICT_ENABLE_ORDERBOOK_MISMATCH,
    CONFLICT_EVENT_ID_MISMATCH,
    CONFLICT_MARKET_ID_MISMATCH,
    CONFLICT_MISSING_REQUIRED_FIELD,
    CONFLICT_OUTCOMES_MISMATCH,
    CONFLICT_SLUG_REUSED,
    REQUIRED_REGISTRY_FIELDS,
    build_slug_history_row,
    canonicalize_market_record,
    make_conflict,
    merge_canonical_ids,
    merge_canonical_records,
    missing_required_fields,
    normalize_slug,
    should_record_slug_change,
)

__all__ = [
    "RegistryBuildResult",
    "build_market_registry",
    "build_registry",
    "CONFLICT_ENABLE_ORDERBOOK_MISMATCH",
    "CONFLICT_EVENT_ID_MISMATCH",
    "CONFLICT_MARKET_ID_MISMATCH",
    "CONFLICT_MISSING_REQUIRED_FIELD",
    "CONFLICT_OUTCOMES_MISMATCH",
    "CONFLICT_SLUG_REUSED",
    "REQUIRED_REGISTRY_FIELDS",
    "build_slug_history_row",
    "canonicalize_market_record",
    "make_conflict",
    "merge_canonical_ids",
    "merge_canonical_records",
    "missing_required_fields",
    "normalize_slug",
    "should_record_slug_change",
]
