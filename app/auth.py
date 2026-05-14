from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

STATE_FILENAME = "storage_state.enc"


def _path() -> Path:
    return Path(get_settings().state_dir) / STATE_FILENAME


def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


def save_state(state: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    blob = _fernet().encrypt(json.dumps(state, ensure_ascii=False).encode())
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(blob)
    tmp.replace(p)


def load_state() -> Optional[dict]:
    p = _path()
    if not p.exists():
        return None
    try:
        plain = _fernet().decrypt(p.read_bytes()).decode()
    except InvalidToken:
        return None
    return json.loads(plain)


def clear_state() -> None:
    p = _path()
    if p.exists():
        p.unlink()


def has_state() -> bool:
    return _path().exists()
