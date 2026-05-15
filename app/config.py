from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str  # number | duration | progress | multi_select


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── 飞书凭证与目标表 ───────────────────────────────────────
    feishu_app_id: str = Field(..., alias="FEISHU_APP_ID")
    feishu_app_secret: str = Field(..., alias="FEISHU_APP_SECRET")
    feishu_app_token: str = Field(..., alias="FEISHU_APP_TOKEN")
    feishu_table_id: str = Field(..., alias="FEISHU_TABLE_ID")
    feishu_webhook_secret: str = Field(..., alias="FEISHU_WEBHOOK_SECRET")

    # ── 服务密钥 & 持久化 ─────────────────────────────────────
    admin_token: str = Field(..., alias="ADMIN_TOKEN")
    fernet_key: str = Field(..., alias="FERNET_KEY")
    state_dir: str = Field("/data", alias="STATE_DIR")

    # ── 飞书列名（默认即正确；改飞书列名时同步改这里）──────────────
    feishu_link_field: str = Field("节目详情追光链接", alias="FEISHU_LINK_FIELD")
    field_subscribers: str = Field("订阅数", alias="FIELD_SUBSCRIBERS")
    field_avg_listen: str = Field("平均收听量", alias="FIELD_AVG_LISTEN")
    field_avg_duration: str = Field("平均节目时长", alias="FIELD_AVG_DURATION")
    field_avg_play: str = Field("平均播放时长", alias="FIELD_AVG_PLAY")
    field_avg_comments: str = Field("平均评论数", alias="FIELD_AVG_COMMENTS")
    field_female_ratio: str = Field("订阅用户女性占比", alias="FIELD_FEMALE_RATIO")
    field_age_distribution: str = Field(
        "订阅用户主要年龄分布", alias="FIELD_AGE_DISTRIBUTION"
    )
    field_location_distribution: str = Field(
        "用户主要地域分布", alias="FIELD_LOCATION_DISTRIBUTION"
    )
    field_iphone_ratio: str = Field(
        "订阅用户设备iphone占比", alias="FIELD_IPHONE_RATIO"
    )

    # ── 容器内部（一般不用动）──────────────────────────────────
    display: str = Field(":99", alias="DISPLAY")
    novnc_port: int = Field(6080, alias="NOVNC_PORT")
    port: int = Field(8000, alias="PORT")

    def field_specs(self) -> list[FieldSpec]:
        return [
            FieldSpec(name=self.field_subscribers, kind="number"),
            FieldSpec(name=self.field_avg_listen, kind="number"),
            FieldSpec(name=self.field_avg_duration, kind="duration"),
            FieldSpec(name=self.field_avg_play, kind="duration"),
            FieldSpec(name=self.field_avg_comments, kind="number"),
            FieldSpec(name=self.field_female_ratio, kind="progress"),
            FieldSpec(name=self.field_age_distribution, kind="multi_select"),
            FieldSpec(name=self.field_location_distribution, kind="multi_select"),
            FieldSpec(name=self.field_iphone_ratio, kind="progress"),
        ]

    @property
    def link_field_name(self) -> str:
        return self.feishu_link_field


@lru_cache
def get_settings() -> Settings:
    return Settings()
