# PRD2 test fixtures

Reusable fixture pack for PRD2 TSFM tests lives in `tests/fixtures/prd2/`.

## Fixture set

- `D1_normal.json`: normal healthy runtime path.
- `D2_jumpy.json`: jumpy/crossed quantiles to exercise clipping + crossing fix.
- `D3_illiquid.json`: low-liquidity baseline-only fallback path.
- `D4_failure-template.json`: adapter/runtime failure fallback template.

Each fixture includes:

- `request`: request payload compatible with `TSFMRunnerService.forecast` and API tests.
- `adapter`: synthetic adapter behavior (`mode=ok|error`, optional quantiles/meta/error_message).
- `expect`: expected runtime/fallback/warning assertions.

## Helper loader

Use `tests/helpers/prd2_fixtures.py`:

- `load_prd2_fixture(name)`
- `fixture_request(name)`
- `fixture_adapter_quantiles(name)`
- `fixture_expectation(name)`

## Example

```python
from runners.tsfm_service import TSFMRunnerService
from tests.helpers.prd2_fixtures import fixture_request, fixture_expectation

request = fixture_request("D1_normal")
response = TSFMRunnerService(adapter=my_adapter).forecast(request)
expect = fixture_expectation("D1_normal")
assert response["meta"]["runtime"] == expect["runtime"]
```

## Current test consumers

- Unit: `tests/unit/test_tsfm_runner_service.py`
- Unit/API: `tests/unit/test_api_tsfm_forecast.py`
- Integration: `tests/integration/test_prd2_fixture_scenarios.py`
