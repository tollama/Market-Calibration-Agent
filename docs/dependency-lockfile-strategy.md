# Dependency lockfile strategy (TODO)

Current state uses `pyproject.toml` without a committed lockfile.

Suggested minimal lockfile path:

- Choose one tool for deterministic installs (example): `uv`.
- Generate and review lockfile before release:
  - `uv pip compile pyproject.toml --all-extras -o requirements.lock`
- TODO: add a small CI step to regenerate/update `requirements.lock` from a reviewed commit and verify installs with `uv pip install -r requirements.lock`.

This keeps dependencies explicit in `pyproject.toml` while adding a reproducible, optional locking workflow.
