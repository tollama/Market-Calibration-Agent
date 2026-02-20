from __future__ import annotations

from pathlib import Path

import yaml


def test_prod_tsfm_config_rejects_research_only_models() -> None:
    config = yaml.safe_load(Path("configs/tsfm_models.yaml").read_text(encoding="utf-8"))
    models = config["models"]
    prod_allowed = config["environments"]["prod"]["allowed_models"]

    for alias in prod_allowed:
        assert models[alias]["license_tag"] == "commercial_ok"
