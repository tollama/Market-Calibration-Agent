from __future__ import annotations

import pytest

from tests.helpers.prd2_fixtures import fixture_expectation, fixture_request


@pytest.mark.parametrize(
    "name,expected_runtime",
    [
        ("D1_normal", "tollama"),
        ("D2_jumpy", "tollama"),
        ("D3_illiquid", "baseline"),
        ("D4_failure-template", "baseline"),
    ],
)
def test_fixture_loader_returns_expected_runtime(name: str, expected_runtime: str) -> None:
    request = fixture_request(name)
    expect = fixture_expectation(name)

    assert request["market_id"].startswith("prd2-")
    assert expect["runtime"] == expected_runtime
