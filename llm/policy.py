"""Deterministic sampling policy utilities for LLM requests."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SEED = 42
DEFAULT_TEMPERATURE = 0.0


@dataclass(frozen=True)
class SamplingPolicy:
    """Sampling parameters used for deterministic LLM generations."""

    seed: int | None = DEFAULT_SEED
    temperature: float = DEFAULT_TEMPERATURE

    def as_metadata(self) -> dict[str, int | float | None]:
        """Return a stable metadata mapping for cache-key inputs."""
        return {
            "seed": self.seed,
            "temperature": self.temperature,
        }


def resolve_sampling_policy(
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
) -> SamplingPolicy:
    """Build a sampling policy with deterministic defaults."""
    return SamplingPolicy(seed=seed, temperature=temperature)
