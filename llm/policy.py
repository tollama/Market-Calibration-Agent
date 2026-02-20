"""Deterministic sampling policy utilities for LLM requests."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SEED = 42
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TOP_P = 1.0


@dataclass(frozen=True)
class SamplingPolicy:
    """Sampling parameters used for deterministic LLM generations."""

    seed: int | None = DEFAULT_SEED
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P

    def __post_init__(self) -> None:
        if not (0.0 < self.top_p <= 1.0):
            raise ValueError("top_p must be in the interval (0, 1]")

    def as_metadata(self) -> dict[str, int | float | None]:
        """Return a stable metadata mapping for cache-key inputs."""
        return {
            "seed": self.seed,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }


def resolve_sampling_policy(
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    top_p: float = DEFAULT_TOP_P,
    seed: int | None = DEFAULT_SEED,
) -> SamplingPolicy:
    """Build a sampling policy with deterministic defaults."""
    return SamplingPolicy(seed=seed, temperature=temperature, top_p=top_p)
