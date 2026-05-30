import json
import threading
from typing import Any

from settings import DATA_DIR, DATA_FILE

_lock = threading.Lock()


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_all() -> dict[str, Any]:
    _ensure_data_dir()
    if not DATA_FILE.exists():
        return {}
    with _lock:
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}


def save_all(data: dict[str, Any]) -> None:
    _ensure_data_dir()
    with _lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
