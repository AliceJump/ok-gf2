"""Shared, account-independent acknowledgement storage."""

import json
import os
import tempfile
import threading
from pathlib import Path


_lock = threading.Lock()


def _state_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path)
    from ok.util.file import get_relative_path
    return Path(get_relative_path("configs", "notice_state.json"))


def load_read_ids(path: str | Path | None = None) -> set[str]:
    try:
        with _state_path(path).open(encoding="utf-8") as state_file:
            data = json.load(state_file)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return set()
    if not isinstance(data, dict) or not isinstance(data.get("read_ids"), list):
        return set()
    return {item for item in data["read_ids"] if isinstance(item, str)}


def mark_read(notice_id: str, path: str | Path | None = None) -> None:
    state_path = _state_path(path)
    with _lock:
        read_ids = load_read_ids(state_path)
        if notice_id in read_ids:
            return
        read_ids.add(notice_id)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=state_path.parent,
                                             prefix=f"{state_path.name}.", suffix=".tmp", delete=False) as state_file:
                temporary_path = state_file.name
                json.dump({"read_ids": sorted(read_ids)}, state_file, ensure_ascii=False, indent=2)
                state_file.flush()
                os.fsync(state_file.fileno())
            os.replace(temporary_path, state_path)
        finally:
            if temporary_path is not None and os.path.exists(temporary_path):
                os.unlink(temporary_path)
