from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.supabase_client import supabase

TABLE = "auth_state"
ROW_ID = "zhuiguang"


def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


def save_state(state: dict) -> None:
    blob = _fernet().encrypt(json.dumps(state, ensure_ascii=False).encode()).decode()
    row = {
        "id": ROW_ID,
        "encrypted_state": blob,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase().table(TABLE).upsert(row).execute()


def load_state() -> Optional[dict]:
    res = supabase().table(TABLE).select("encrypted_state").eq("id", ROW_ID).limit(1).execute()
    rows = res.data or []
    if not rows:
        return None
    blob = rows[0]["encrypted_state"]
    try:
        plain = _fernet().decrypt(blob.encode()).decode()
    except InvalidToken:
        return None
    return json.loads(plain)


def clear_state() -> None:
    supabase().table(TABLE).delete().eq("id", ROW_ID).execute()


def has_state() -> bool:
    return load_state() is not None
