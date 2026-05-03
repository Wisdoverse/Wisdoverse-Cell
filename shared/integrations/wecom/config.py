# shared/integrations/wecom/config.py
"""
WecomConfig - WeCom configuration.

Loads WeCom-related configuration from environment variables.
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WecomConfig(BaseSettings):
    """
    WeCom configuration.

    Environment variable prefix: WECOM_
    """
    model_config = SettingsConfigDict(
        env_prefix="WECOM_",
        env_file=".env",
        extra="ignore",
    )

    # Required configuration.
    corp_id: str = Field(default="", description="Corporate ID")
    agent_id: int = Field(default=0, description="Application AgentId")
    secret: str = Field(default="", description="Application secret")
    token: str = Field(default="", description="Callback token")
    encoding_aes_key: str = Field(default="", description="Callback EncodingAESKey")

    # Optional configuration.
    enabled: bool = Field(default=False, description="Enable WeCom integration")
    api_base_url: str = Field(
        default="https://qyapi.weixin.qq.com/cgi-bin",
        description="API base URL"
    )
    token_refresh_buffer: int = Field(
        default=300,
        description="Token refresh buffer in seconds"
    )

    # Feature flags.
    bot_enabled: bool = Field(default=True, description="Enable bot message handling")
    card_enabled: bool = Field(default=True, description="Enable card callback handling")


# Global configuration instance.
_wecom_config: WecomConfig | None = None


def get_wecom_config() -> WecomConfig:
    """Get the WeCom configuration singleton."""
    global _wecom_config
    if _wecom_config is None:
        _wecom_config = WecomConfig()
    return _wecom_config
