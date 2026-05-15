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
    feishu_open_api_base: str = Field(
        "https://open.feishu.cn/open-apis", alias="FEISHU_OPEN_API_BASE"
    )  # 国际版 Lark 改成 https://open.larksuite.com/open-apis
    feishu_page_size: int = Field(200, alias="FEISHU_PAGE_SIZE")

    # ── 服务密钥 & 持久化 ─────────────────────────────────────
    admin_token: str = Field(..., alias="ADMIN_TOKEN")
    fernet_key: str = Field(..., alias="FERNET_KEY")
    state_dir: str = Field("/data", alias="STATE_DIR")

    # ── 飞书列名（默认即正确,改了之后飞书表和 zhuiguang 页面标签要一致）──
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

    # ── 抓取行为 ─────────────────────────────────────────────
    zhuiguang_base_url: str = Field("https://zhuiguang.xyz", alias="ZHUIGUANG_BASE_URL")
    zhuiguang_login_url: str = Field("https://zhuiguang.xyz/", alias="ZHUIGUANG_LOGIN_URL")
    login_success_url_hints: str = Field(
        "/advertiser,/dashboard,/home", alias="LOGIN_SUCCESS_URL_HINTS"
    )
    session_cookie_hints: str = Field(
        "session,token,auth,sid,passport,user", alias="SESSION_COOKIE_HINTS"
    )
    scrape_ready_selector: str = Field("text=订阅数", alias="SCRAPE_READY_SELECTOR")
    scrape_nav_timeout_ms: int = Field(60000, alias="SCRAPE_NAV_TIMEOUT_MS")
    scrape_ready_timeout_ms: int = Field(15000, alias="SCRAPE_READY_TIMEOUT_MS")
    screen_width: int = Field(1440, alias="SCREEN_WIDTH")
    screen_height: int = Field(900, alias="SCREEN_HEIGHT")

    # ── 调度 / 批量 ──────────────────────────────────────────
    enable_daily_scan: bool = Field(True, alias="ENABLE_DAILY_SCAN")
    daily_scan_hour_utc: int = Field(20, alias="DAILY_SCAN_HOUR_UTC")
    scan_delay_seconds: float = Field(1.0, alias="SCAN_DELAY_SECONDS")

    # ── 容器内部（一般不用改）──────────────────────────────────
    display: str = Field(":99", alias="DISPLAY")
    novnc_port: int = Field(6080, alias="NOVNC_PORT")
    port: int = Field(8000, alias="PORT")

    # 兼容旧别名
    link_field_name_legacy: str | None = Field(default=None, alias="LINK_FIELD_NAME")

    # ── 派生 ────────────────────────────────────────────────
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

    def login_success_hints_list(self) -> list[str]:
        return [s.strip() for s in self.login_success_url_hints.split(",") if s.strip()]

    def session_cookie_hints_list(self) -> list[str]:
        return [s.strip().lower() for s in self.session_cookie_hints.split(",") if s.strip()]

    @property
    def link_field_name(self) -> str:
        return self.link_field_name_legacy or self.feishu_link_field


@lru_cache
def get_settings() -> Settings:
    return Settings()
