from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.config import FieldSpec, get_settings

OPEN_API_BASE = "https://open.feishu.cn/open-apis"
PAGE_SIZE = 200


class FeishuClient:
    def __init__(self) -> None:
        s = get_settings()
        self._app_id = s.feishu_app_id
        self._app_secret = s.feishu_app_secret
        self._app_token = s.feishu_app_token
        self._table_id = s.feishu_table_id
        self._specs = s.field_specs()
        self._token: Optional[str] = None
        self._token_expire_at: float = 0.0
        self._http = httpx.Client(timeout=20.0)

    def _tenant_token(self) -> str:
        if self._token and time.time() < self._token_expire_at - 60:
            return self._token
        r = self._http.post(
            f"{OPEN_API_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
        self._token = data["tenant_access_token"]
        self._token_expire_at = time.time() + data["expire"]
        return self._token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._tenant_token()}"}

    def get_record(self, record_id: str) -> dict:
        url = (
            f"{OPEN_API_BASE}/bitable/v1/apps/{self._app_token}"
            f"/tables/{self._table_id}/records/{record_id}"
        )
        r = self._http.get(url, headers=self._auth_headers())
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"读取记录失败: {data}")
        return data["data"]["record"]

    def list_records(self) -> list[dict]:
        url = (
            f"{OPEN_API_BASE}/bitable/v1/apps/{self._app_token}"
            f"/tables/{self._table_id}/records"
        )
        items: list[dict] = []
        page_token: Optional[str] = None
        while True:
            params: dict[str, Any] = {"page_size": PAGE_SIZE}
            if page_token:
                params["page_token"] = page_token
            r = self._http.get(url, headers=self._auth_headers(), params=params)
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                raise RuntimeError(f"列出记录失败: {data}")
            payload = data.get("data") or {}
            items.extend(payload.get("items") or [])
            if not payload.get("has_more"):
                break
            page_token = payload.get("page_token")
            if not page_token:
                break
        return items

    def update_record(self, record_id: str, fields: dict[str, Any]) -> dict:
        url = (
            f"{OPEN_API_BASE}/bitable/v1/apps/{self._app_token}"
            f"/tables/{self._table_id}/records/{record_id}"
        )
        r = self._http.put(
            url,
            headers=self._auth_headers(),
            json={"fields": _normalize_fields(fields, self._specs)},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"更新记录失败: {data}")
        return data["data"]["record"]


def _normalize_fields(fields: dict[str, Any], specs: list[FieldSpec]) -> dict[str, Any]:
    kind_by_name = {spec.name: spec.kind for spec in specs}
    out: dict[str, Any] = {}
    for name, value in fields.items():
        # 跳过"无数据"——None / 空串 / 空列表都不写，避免把飞书里已有的值覆盖成空白。
        # 注意用显式比较而非 `not value`，否则数字 0 / 0.0 也会被误当成空。
        if value is None or value == "" or value == []:
            continue
        kind = kind_by_name.get(name)
        if kind in ("number", "duration"):
            try:
                out[name] = float(value)
            except (TypeError, ValueError):
                continue
        elif kind == "progress":
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            if v > 1.0:
                v = v / 100.0
            out[name] = max(0.0, min(1.0, v))
        elif kind == "multi_select":
            if isinstance(value, str):
                items = [v.strip() for v in value.split(",") if v.strip()]
            else:
                items = [str(v).strip() for v in value if str(v).strip()]
            if not items:  # 解析后为空也跳过，不覆盖已有多选
                continue
            out[name] = items
        else:
            out[name] = value
    return out


def extract_link(record: dict, link_field: str) -> Optional[str]:
    fields = record.get("fields", {})
    v = fields.get(link_field)
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return v.get("link") or v.get("text")
    if isinstance(v, list) and v:
        first = v[0]
        if isinstance(first, dict):
            return first.get("link") or first.get("text")
        return str(first)
    return None
