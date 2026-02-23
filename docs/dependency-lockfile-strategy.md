# Dependency lockfile strategy

## Current state

`pyproject.toml` defines constraints and we keep a committed lockfile:
- `requirements.lock`

Dependency install in CI and production scripts is expected to use lockfile sync:

```bash
uv pip sync requirements.lock

# CI / non-venv runner
uv pip sync --system requirements.lock
```

This guarantees deterministic installs and blocks accidental drift at install time.

## Lockfile generation / refresh process

After `pyproject.toml` changes, regenerate and review:

```bash
uv pip compile pyproject.toml --all-extras -o requirements.lock
```

Then commit both `pyproject.toml` and `requirements.lock` together.

## CI alignment check

CI verifies the committed lockfile stays synchronized with `pyproject.toml`:

```bash
uv pip compile pyproject.toml --all-extras -o /tmp/requirements.lock.expected
python - <<'PY'
import pathlib

def normalize(path):
    lines = pathlib.Path(path).read_text(encoding='utf-8').splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith('#')]

assert normalize('requirements.lock') == normalize('/tmp/requirements.lock.expected')
PY
```

If this check fails, the branch must update `requirements.lock` before merge.
