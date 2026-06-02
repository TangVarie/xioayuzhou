from __future__ import annotations

import json
import os
import uuid
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
    # 每次写用独立的临时文件名（pid + 随机），否则两个并发的抓取/登录会抢同一个
    # storage_state.enc.tmp，其中一个被另一个移走后 replace 抛错，把本来成功的抓取
    # 变成异常。最终 replace 是原子的，谁最后写谁生效，对登录态而言无所谓。
    tmp = p.with_suffix(p.suffix + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(blob)
        tmp.replace(p)
    finally:
        try:
            tmp.unlink()  # replace 成功后 tmp 已不存在；失败时清理残留
        except FileNotFoundError:
            pass


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
