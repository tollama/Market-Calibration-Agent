from __future__ import annotations

from api.app import app


def test_p2_09_metrics_endpoint_is_exposed_for_runtime_observability() -> None:
    """Traceability: PRD2 P2-09 (runtime observability metrics emission)."""
    paths = {route.path for route in app.routes}

    # Gap matrix requires in-process metrics emission wiring.
    # A conventional acceptance probe is an exported /metrics endpoint.
    assert "/metrics" in paths
