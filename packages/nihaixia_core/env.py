from __future__ import annotations

import os
from pathlib import Path


_LOADED_ENV_FILES: set[Path] = set()


def parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return key, value


def load_env_file(path: str | Path = ".env", override: bool = False) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists() or not env_path.is_file():
        return {}

    resolved = env_path.resolve()
    if resolved in _LOADED_ENV_FILES:
        return {}
    _LOADED_ENV_FILES.add(resolved)

    loaded: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def load_default_env() -> None:
    for env_path in candidate_env_paths():
        loaded = load_env_file(env_path, override=False)
        if loaded:
            return


def candidate_env_paths() -> list[Path]:
    candidates: list[Path] = []
    for start in (Path.cwd(), Path(__file__).resolve()):
        current = start if start.is_dir() else start.parent
        for parent in (current, *current.parents):
            candidate = parent / ".env"
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates
