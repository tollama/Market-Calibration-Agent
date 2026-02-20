from __future__ import annotations

import pytest

from runners.tollama_adapter import TollamaError
from runners.tsfm_service import TSFMRunnerService
from tests.helpers.prd2_fixtures import (
    fixture_adapter_quantiles,
    fixture_expectation,
    fixture_request,
    load_prd2_fixture,
)


class _FixtureAdapter:
    def __init__(self, fixture_name: str):
        payload = load_prd2_fixture(fixture_name)
        self._mode = payload["adapter"]["mode"]
        self._error_message = payload["adapter"].get("error_message", "fixture_error")
        self._quantiles = fixture_adapter_quantiles(fixture_name)
        self._meta = payload["adapter"].get("meta", {"runtime": "tollama"})

    def forecast(self, **_: object):
        if self._mode == "error":
            raise TollamaError(self._error_message)
        return self._quantiles, self._meta


@pytest.mark.parametrize(
    "fixture_name",
    ["D1_normal", "D2_jumpy", "D3_illiquid", "D4_failure-template"],
)
def test_prd2_fixture_scenarios_end_to_end(fixture_name: str) -> None:
    service = TSFMRunnerService(adapter=_FixtureAdapter(fixture_name))
    response = service.forecast(fixture_request(fixture_name))
    expect = fixture_expectation(fixture_name)

    assert response["meta"]["runtime"] == expect["runtime"]
    assert response["meta"]["fallback_used"] is expect["fallback_used"]
    assert set(response["yhat_q"]) == {"0.1", "0.5", "0.9"}

    for warning in expect.get("warnings_include", []):
        assert any(warning in w for w in response["meta"]["warnings"])
