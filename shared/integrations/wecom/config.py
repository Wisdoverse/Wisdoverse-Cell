# shared/services/wecom/config.py
"""
WecomConfig - 企业微信配置

从环境变量加载企业微信相关配置。
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WecomConfig(BaseSettings):
    """
    企业微信配置

    环境变量前缀: WECOM_
    """
    model_config = SettingsConfigDict(
        env_prefix="WECOM_",
        env_file=".env",
        extra="ignore",
    )

    # 必填配置
    corp_id: str = Field(default="", description="企业 ID")
    agent_id: int = Field(default=0, description="应用 AgentId")
    secret: str = Field(default="", description="应用 Secret")
    token: str = Field(default="", description="回调 Token")
    encoding_aes_key: str = Field(default="", description="回调 EncodingAESKey")

    # 可选配置
    enabled: bool = Field(default=False, description="是否启用企微集成")
    api_base_url: str = Field(
        default="https://qyapi.weixin.qq.com/cgi-bin",
        description="API 基础 URL"
    )
    token_refresh_buffer: int = Field(
        default=300,
        description="Token 刷新缓冲时间（秒）"
    )

    # 功能开关
    bot_enabled: bool = Field(default=True, description="启用 Bot 消息处理")
    card_enabled: bool = Field(default=True, description="启用卡片回调处理")


# 全局配置实例
_wecom_config: WecomConfig | None = None


def get_wecom_config() -> WecomConfig:
    """获取企微配置单例"""
    global _wecom_config
    if _wecom_config is None:
        _wecom_config = WecomConfig()
    return _wecom_config
