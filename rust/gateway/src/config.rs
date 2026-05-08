use std::env;
use std::time::Duration;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GatewayConfig {
    pub server_port: u16,
    pub server_mode: String,
    pub grpc_ai_service_addr: String,
    pub grpc_timeout: String,
    pub redis_addr: String,
    pub ratelimit_enabled: bool,
    pub ratelimit_rps: u32,
    pub ratelimit_burst_size: u32,
    pub feishu_app_id: String,
    pub feishu_app_secret: String,
    pub feishu_verification_token: String,
    pub feishu_encrypt_key: String,
    pub feishu_open_api_base_url: String,
    pub feishu_verify_signature: bool,
    pub feishu_chat_agent_addr: String,
    pub feishu_pjm_agent_addr: String,
    pub feishu_internal_service_key: String,
    pub wecom_corp_id: String,
    pub wecom_agent_id: String,
    pub wecom_secret: String,
    pub wecom_api_base_url: String,
    pub wecom_token: String,
    pub wecom_encoding_aes_key: String,
    pub log_level: String,
    pub log_format: String,
}

impl GatewayConfig {
    pub fn from_env() -> Self {
        Self::from_lookup(|key| env::var(key).ok())
    }

    pub fn from_lookup<F>(mut lookup: F) -> Self
    where
        F: FnMut(&str) -> Option<String>,
    {
        Self {
            server_port: parse_or(&mut lookup, "GATEWAY_SERVER_PORT", 8080),
            server_mode: value_or(&mut lookup, "GATEWAY_SERVER_MODE", "release"),
            grpc_ai_service_addr: value_or(
                &mut lookup,
                "GATEWAY_GRPC_AI_SERVICE_ADDR",
                "localhost:50051",
            ),
            grpc_timeout: value_or(&mut lookup, "GATEWAY_GRPC_TIMEOUT", "30s"),
            redis_addr: value_or(&mut lookup, "GATEWAY_REDIS_ADDR", "localhost:6379"),
            ratelimit_enabled: parse_bool_or(&mut lookup, "GATEWAY_RATELIMIT_ENABLED", true),
            ratelimit_rps: parse_or(&mut lookup, "GATEWAY_RATELIMIT_RPS", 100),
            ratelimit_burst_size: parse_or(&mut lookup, "GATEWAY_RATELIMIT_BURST_SIZE", 200),
            feishu_app_id: value_or(&mut lookup, "GATEWAY_FEISHU_APP_ID", ""),
            feishu_app_secret: value_or(&mut lookup, "GATEWAY_FEISHU_APP_SECRET", ""),
            feishu_verification_token: value_or(
                &mut lookup,
                "GATEWAY_FEISHU_VERIFICATION_TOKEN",
                "",
            ),
            feishu_encrypt_key: value_or(&mut lookup, "GATEWAY_FEISHU_ENCRYPT_KEY", ""),
            feishu_open_api_base_url: value_or(
                &mut lookup,
                "GATEWAY_FEISHU_OPEN_API_BASE_URL",
                "https://open.feishu.cn/open-apis",
            ),
            feishu_verify_signature: parse_bool_or(
                &mut lookup,
                "GATEWAY_FEISHU_VERIFY_SIGNATURE",
                true,
            ),
            feishu_chat_agent_addr: value_or(&mut lookup, "GATEWAY_FEISHU_CHAT_AGENT_ADDR", ""),
            feishu_pjm_agent_addr: value_or(&mut lookup, "GATEWAY_FEISHU_PM_AGENT_ADDR", ""),
            feishu_internal_service_key: value_or(
                &mut lookup,
                "GATEWAY_FEISHU_INTERNAL_SERVICE_KEY",
                "",
            ),
            wecom_corp_id: value_or(&mut lookup, "GATEWAY_WECOM_CORP_ID", ""),
            wecom_agent_id: value_or(&mut lookup, "GATEWAY_WECOM_AGENT_ID", ""),
            wecom_secret: value_or(&mut lookup, "GATEWAY_WECOM_SECRET", ""),
            wecom_api_base_url: value_or(
                &mut lookup,
                "GATEWAY_WECOM_API_BASE_URL",
                "https://qyapi.weixin.qq.com/cgi-bin",
            ),
            wecom_token: value_or(&mut lookup, "GATEWAY_WECOM_TOKEN", ""),
            wecom_encoding_aes_key: value_or(&mut lookup, "GATEWAY_WECOM_ENCODING_AES_KEY", ""),
            log_level: value_or(&mut lookup, "GATEWAY_LOG_LEVEL", "info"),
            log_format: value_or(&mut lookup, "GATEWAY_LOG_FORMAT", "json"),
        }
    }

    pub fn grpc_timeout_duration(&self) -> Duration {
        parse_duration_or(&self.grpc_timeout, Duration::from_secs(30))
    }
}

fn value_or<F>(lookup: &mut F, key: &str, default: &str) -> String
where
    F: FnMut(&str) -> Option<String>,
{
    lookup(key)
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| default.to_string())
}

fn parse_or<F, T>(lookup: &mut F, key: &str, default: T) -> T
where
    F: FnMut(&str) -> Option<String>,
    T: std::str::FromStr + Copy,
{
    lookup(key)
        .and_then(|value| value.parse::<T>().ok())
        .unwrap_or(default)
}

fn parse_bool_or<F>(lookup: &mut F, key: &str, default: bool) -> bool
where
    F: FnMut(&str) -> Option<String>,
{
    lookup(key)
        .map(|value| {
            matches!(
                value.to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(default)
}

fn parse_duration_or(value: &str, default: Duration) -> Duration {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return default;
    }

    if let Some(value) = trimmed.strip_suffix("ms") {
        return value
            .parse::<u64>()
            .map(Duration::from_millis)
            .unwrap_or(default);
    }
    if let Some(value) = trimmed.strip_suffix('s') {
        return value
            .parse::<u64>()
            .map(Duration::from_secs)
            .unwrap_or(default);
    }
    if let Some(value) = trimmed.strip_suffix('m') {
        return value
            .parse::<u64>()
            .map(|minutes| Duration::from_secs(minutes * 60))
            .unwrap_or(default);
    }

    trimmed
        .parse::<u64>()
        .map(Duration::from_secs)
        .unwrap_or(default)
}

#[cfg(test)]
mod tests {
    use super::GatewayConfig;
    use std::collections::HashMap;

    #[test]
    fn loads_stable_gateway_env_names() {
        let env = HashMap::from([
            ("GATEWAY_SERVER_PORT", "18080"),
            ("GATEWAY_GRPC_AI_SERVICE_ADDR", "ai-core:50051"),
            ("GATEWAY_RATELIMIT_ENABLED", "false"),
            ("GATEWAY_FEISHU_VERIFY_SIGNATURE", "true"),
            ("GATEWAY_FEISHU_INTERNAL_SERVICE_KEY", "internal-key"),
            ("GATEWAY_WECOM_API_BASE_URL", "http://wecom.local/cgi-bin"),
            ("GATEWAY_LOG_FORMAT", "console"),
        ]);

        let cfg = GatewayConfig::from_lookup(|key| env.get(key).map(|value| value.to_string()));

        assert_eq!(cfg.server_port, 18080);
        assert_eq!(cfg.grpc_ai_service_addr, "ai-core:50051");
        assert!(!cfg.ratelimit_enabled);
        assert!(cfg.feishu_verify_signature);
        assert_eq!(cfg.feishu_internal_service_key, "internal-key");
        assert_eq!(cfg.wecom_api_base_url, "http://wecom.local/cgi-bin");
        assert_eq!(cfg.log_format, "console");
    }

    #[test]
    fn parses_duration_style_grpc_timeout_values() {
        let cfg = GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_GRPC_TIMEOUT" => Some("750ms".to_string()),
            _ => None,
        });
        assert_eq!(cfg.grpc_timeout_duration().as_millis(), 750);

        let cfg = GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_GRPC_TIMEOUT" => Some("2m".to_string()),
            _ => None,
        });
        assert_eq!(cfg.grpc_timeout_duration().as_secs(), 120);

        let cfg = GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_GRPC_TIMEOUT" => Some("invalid".to_string()),
            _ => None,
        });
        assert_eq!(cfg.grpc_timeout_duration().as_secs(), 30);
    }

    #[test]
    fn defaults_match_current_gateway_contract() {
        let cfg = GatewayConfig::from_lookup(|_| None);

        assert_eq!(cfg.server_port, 8080);
        assert_eq!(cfg.server_mode, "release");
        assert_eq!(cfg.grpc_ai_service_addr, "localhost:50051");
        assert_eq!(cfg.redis_addr, "localhost:6379");
        assert_eq!(
            cfg.wecom_api_base_url,
            "https://qyapi.weixin.qq.com/cgi-bin"
        );
        assert!(cfg.ratelimit_enabled);
    }
}
