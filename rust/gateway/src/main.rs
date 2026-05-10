use std::net::SocketAddr;

use std::sync::Arc;

use tracing::{info, warn};
use tracing_subscriber::{fmt, EnvFilter};
use wisdoverse_cell_rust_gateway::{
    bitable_forward::{
        BitableActionForwarder, HttpBitableActionForwarder, NoopBitableActionForwarder,
    },
    feishu_forward::{FeishuEventForwarder, HttpFeishuEventForwarder, NoopFeishuEventForwarder},
    feishu_outbound::{FeishuApiClient, FeishuMessenger, NoopFeishuMessenger},
    pjm_forward::{HttpPjmActionForwarder, NoopPjmActionForwarder, PjmActionForwarder},
    requirement_client::RequirementClient,
    router_with_components,
    state::{GatewayStateStore, InMemoryStateStore, RedisStateStore},
    wecom_outbound::{NoopWecomMessenger, WecomApiClient, WecomMessenger},
    GatewayComponents, GatewayConfig,
};

#[tokio::main]
async fn main() {
    let config = GatewayConfig::from_env();
    init_tracing(&config);

    let addr = SocketAddr::from(([0, 0, 0, 0], config.server_port));
    let state_store = build_state_store(&config).await;
    let requirement_client = build_requirement_client(&config);
    let bitable_forwarder = build_bitable_forwarder(&config);
    let feishu_forwarder = build_feishu_forwarder(&config);
    let feishu_messenger = build_feishu_messenger(&config);
    let pjm_forwarder = build_pjm_forwarder(&config);
    let wecom_messenger = build_wecom_messenger(&config);
    let app = router_with_components(
        config.clone(),
        state_store,
        GatewayComponents {
            requirement_client,
            bitable_forwarder,
            feishu_forwarder,
            feishu_messenger,
            pjm_forwarder,
            wecom_messenger,
        },
    );
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("bind rust gateway listener");

    info!(
        port = config.server_port,
        ai_service_addr = %config.grpc_ai_service_addr,
        "starting rust gateway"
    );

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .expect("run rust gateway");
}

async fn build_state_store(config: &GatewayConfig) -> Arc<dyn GatewayStateStore> {
    match RedisStateStore::from_addr(&config.redis_addr) {
        Ok(store) => {
            if let Err(err) = store.ping().await {
                warn!(error = %err, redis_addr = %config.redis_addr, "redis unavailable, using in-memory gateway state");
                Arc::new(InMemoryStateStore::new())
            } else {
                info!(redis_addr = %config.redis_addr, "redis state store connected");
                Arc::new(store)
            }
        }
        Err(err) => {
            warn!(error = %err, redis_addr = %config.redis_addr, "redis configuration invalid, using in-memory gateway state");
            Arc::new(InMemoryStateStore::new())
        }
    }
}

fn build_requirement_client(config: &GatewayConfig) -> Option<RequirementClient> {
    let timeout = config.grpc_timeout_duration();
    match RequirementClient::connect_lazy(&config.grpc_ai_service_addr, timeout) {
        Ok(client) => Some(client),
        Err(err) => {
            warn!(
                error = %err,
                ai_service_addr = %config.grpc_ai_service_addr,
                "requirement gRPC client configuration invalid"
            );
            None
        }
    }
}

fn build_feishu_messenger(config: &GatewayConfig) -> Arc<dyn FeishuMessenger> {
    if config.feishu_app_id.is_empty() || config.feishu_app_secret.is_empty() {
        warn!("feishu outbound client is not configured");
        return Arc::new(NoopFeishuMessenger);
    }

    Arc::new(FeishuApiClient::new(
        config.feishu_app_id.clone(),
        config.feishu_app_secret.clone(),
        config.feishu_open_api_base_url.clone(),
    ))
}

fn build_feishu_forwarder(config: &GatewayConfig) -> Arc<dyn FeishuEventForwarder> {
    if config.feishu_chat_agent_addr.is_empty() {
        warn!("feishu chat-agent forwarder is not configured");
        return Arc::new(NoopFeishuEventForwarder);
    }

    Arc::new(HttpFeishuEventForwarder::new(
        config.feishu_chat_agent_addr.clone(),
        config.feishu_internal_service_key.clone(),
    ))
}

fn build_bitable_forwarder(config: &GatewayConfig) -> Arc<dyn BitableActionForwarder> {
    if config.feishu_chat_agent_addr.is_empty() {
        warn!("feishu bitable action forwarder is not configured");
        return Arc::new(NoopBitableActionForwarder);
    }

    Arc::new(HttpBitableActionForwarder::new(
        config.feishu_chat_agent_addr.clone(),
        config.feishu_internal_service_key.clone(),
    ))
}

fn build_pjm_forwarder(config: &GatewayConfig) -> Arc<dyn PjmActionForwarder> {
    if config.feishu_pjm_agent_addr.is_empty() {
        warn!("pjm-agent action forwarder is not configured");
        return Arc::new(NoopPjmActionForwarder);
    }

    Arc::new(HttpPjmActionForwarder::new(
        config.feishu_pjm_agent_addr.clone(),
        config.feishu_internal_service_key.clone(),
    ))
}

fn build_wecom_messenger(config: &GatewayConfig) -> Arc<dyn WecomMessenger> {
    if config.wecom_corp_id.is_empty()
        || config.wecom_agent_id.is_empty()
        || config.wecom_secret.is_empty()
    {
        warn!("wecom outbound client is not configured");
        return Arc::new(NoopWecomMessenger);
    }

    let Ok(agent_id) = config.wecom_agent_id.parse::<u64>() else {
        warn!(
            agent_id = %config.wecom_agent_id,
            "wecom outbound client has invalid agent id"
        );
        return Arc::new(NoopWecomMessenger);
    };

    Arc::new(WecomApiClient::new(
        config.wecom_corp_id.clone(),
        agent_id,
        config.wecom_secret.clone(),
        config.wecom_api_base_url.clone(),
    ))
}

fn init_tracing(config: &GatewayConfig) {
    let filter = EnvFilter::try_from_default_env()
        .or_else(|_| EnvFilter::try_new(&config.log_level))
        .unwrap_or_else(|_| EnvFilter::new("info"));

    let subscriber = fmt().with_env_filter(filter);
    if config.log_format.eq_ignore_ascii_case("json") {
        subscriber.json().init();
    } else {
        subscriber.init();
    }
}

async fn shutdown_signal() {
    let ctrl_c = async {
        if let Err(err) = tokio::signal::ctrl_c().await {
            warn!(error = %err, "failed to install ctrl-c handler");
        }
    };

    #[cfg(unix)]
    let terminate = async {
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            Ok(mut signal) => {
                signal.recv().await;
            }
            Err(err) => warn!(error = %err, "failed to install terminate handler"),
        }
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }

    info!("shutting down rust gateway");
}
