from __future__ import annotations

import json
import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def load_seen_keys(path: str | Path) -> set[str]:
    state_path = Path(path)
    if not state_path.exists():
        return set()

    try:
        with state_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        LOGGER.warning("Invalid seen state at %s: %s", state_path, exc)
        return set()

    if not isinstance(data, list):
        LOGGER.warning("Invalid seen state format at %s: expected a JSON list", state_path)
        return set()

    return {item for item in data if isinstance(item, str) and item}


def save_seen_keys(path: str | Path, keys: set[str]) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with state_path.open("w", encoding="utf-8") as file:
        json.dump(sorted(keys), file, ensure_ascii=True, indent=2)
        file.write("\n")
