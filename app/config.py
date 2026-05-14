from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    feishu_app_id: str = Field(..., alias="FEISHU_APP_ID")
    feishu_app_secret: str = Field(..., alias="FEISHU_APP_SECRET")
    feishu_app_token: str = Field(..., alias="FEISHU_APP_TOKEN")
    feishu_table_id: str = Field(..., alias="FEISHU_TABLE_ID")
    feishu_webhook_secret: str = Field(..., alias="FEISHU_WEBHOOK_SECRET")

    admin_token: str = Field(..., alias="ADMIN_TOKEN")
    fernet_key: str = Field(..., alias="FERNET_KEY")

    supabase_url: str = Field(..., alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(..., alias="SUPABASE_SERVICE_ROLE_KEY")

    zhuiguang_base_url: str = Field("https://zhuiguang.xyz", alias="ZHUIGUANG_BASE_URL")
    display: str = Field(":99", alias="DISPLAY")
    novnc_port: int = Field(6080, alias="NOVNC_PORT")
    port: int = Field(8000, alias="PORT")

    link_field_name: str = Field("节目详情追光链接", alias="FEISHU_LINK_FIELD")


@lru_cache
def get_settings() -> Settings:
    return Settings()
