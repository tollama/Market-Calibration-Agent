"""Pipelines package exports.

Avoid eager imports here: some runtime modules transitively import optional
heavy dependencies during module import. Keep package import side effects low
and resolve exports lazily.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "DAILY_STAGE_NAMES",
    "ResolvedDatasetConfig",
    "WalkForwardConfig",
    "build_daily_stages",
    "build_resolved_training_dataset",
    "generate_backtest_report",
    "run_daily_job",
]


def __getattr__(name: str) -> Any:
    if name in {"DAILY_STAGE_NAMES", "build_daily_stages", "run_daily_job"}:
        module = import_module("pipelines.daily_job")
        return getattr(module, name)
    if name in {"ResolvedDatasetConfig", "build_resolved_training_dataset"}:
        module = import_module("pipelines.build_resolved_training_dataset")
        return getattr(module, name)
    if name in {"WalkForwardConfig", "generate_backtest_report"}:
        module = import_module("pipelines.generate_backtest_report")
        return getattr(module, name)
    raise AttributeError(name)
