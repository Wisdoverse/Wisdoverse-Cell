use axum::{
    body::Bytes,
    extract::{Query, State},
    http::{
        header::{HeaderName, HeaderValue, USER_AGENT},
        HeaderMap, Request, StatusCode,
    },
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashMap},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tracing::{error, info, warn};

use crate::{
    bitable_forward::{BitableActionForwarder, BitableError, NoopBitableActionForwarder},
    config::GatewayConfig,
    feishu,
    feishu_forward::{FeishuEventForwarder, NoopFeishuEventForwarder},
    feishu_outbound::{
        build_bitable_cancel_card, build_bitable_duplicate_card, build_bitable_error_card,
        build_decomposition_action_result_card, build_decomposition_error_card,
        build_decomposition_processing_card, build_help_card, build_operation_result_card,
        build_requirements_list_card, build_requirements_search_card, CardRequirement,
        FeishuMessenger, NoopFeishuMessenger,
    },
    matcher::{MatchType, Matcher, SkillMatch},
    pjm_forward::{NoopPjmActionForwarder, PjmActionForwarder, PjmForwardError},
    rate_limit::RateLimiter,
    requirement_client::RequirementClient,
    state::{Deduplicator, GatewayStateStore, InMemoryStateStore, SessionManager},
    wecom::WecomCrypto,
    wecom_outbound::{
        build_error_text, build_help_markdown as build_wecom_help_markdown,
        build_operation_text as build_wecom_operation_text,
        build_requirements_markdown as build_wecom_requirements_markdown,
        build_requirements_search_markdown as build_wecom_requirements_search_markdown,
        build_template_card_result as build_wecom_template_card_result, NoopWecomMessenger,
        WecomMessenger, WecomRequirement,
    },
};

pub const VERSION: &str = "0.1.0-rust";
static REQUEST_COUNTER: AtomicU64 = AtomicU64::new(1);
static X_REQUEST_ID: HeaderName = HeaderName::from_static("x-request-id");
static X_TRACE_ID: HeaderName = HeaderName::from_static("x-trace-id");

#[derive(Clone)]
pub struct AppState {
    pub config: Arc<GatewayConfig>,
    pub state_store: Arc<dyn GatewayStateStore>,
    pub requirement_client: Option<RequirementClient>,
    pub matcher: Matcher,
    pub deduplicator: Deduplicator,
    pub session_manager: SessionManager,
    pub bitable_forwarder: Arc<dyn BitableActionForwarder>,
    pub feishu_forwarder: Arc<dyn FeishuEventForwarder>,
    pub feishu_messenger: Arc<dyn FeishuMessenger>,
    pub pjm_forwarder: Arc<dyn PjmActionForwarder>,
    pub wecom_messenger: Arc<dyn WecomMessenger>,
}

pub struct GatewayComponents {
    pub requirement_client: Option<RequirementClient>,
    pub bitable_forwarder: Arc<dyn BitableActionForwarder>,
    pub feishu_forwarder: Arc<dyn FeishuEventForwarder>,
    pub feishu_messenger: Arc<dyn FeishuMessenger>,
    pub pjm_forwarder: Arc<dyn PjmActionForwarder>,
    pub wecom_messenger: Arc<dyn WecomMessenger>,
}

impl Default for GatewayComponents {
    fn default() -> Self {
        Self {
            requirement_client: None,
            bitable_forwarder: Arc::new(NoopBitableActionForwarder),
            feishu_forwarder: Arc::new(NoopFeishuEventForwarder),
            feishu_messenger: Arc::new(NoopFeishuMessenger),
            pjm_forwarder: Arc::new(NoopPjmActionForwarder),
            wecom_messenger: Arc::new(NoopWecomMessenger),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequestContext {
    pub request_id: String,
    pub trace_id: String,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: &'static str,
    version: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    services: Option<BTreeMap<&'static str, String>>,
}

#[derive(Debug, Deserialize)]
struct FeishuWebhookRequest {
    #[serde(default)]
    r#type: String,
    #[serde(default)]
    challenge: String,
    #[serde(default)]
    action: Value,
    #[serde(default)]
    event: Value,
    #[serde(default)]
    header: Option<FeishuEventHeader>,
}

#[derive(Debug, Deserialize)]
struct FeishuEventHeader {
    #[serde(default)]
    event_id: String,
    #[serde(default)]
    event_type: String,
}

#[derive(Debug, Deserialize)]
struct FeishuCardActionTriggerEvent {
    operator: FeishuCardActionOperator,
    action: FeishuCardActionDetail,
}

#[derive(Debug, Deserialize)]
struct FeishuCardActionOperator {
    #[serde(default)]
    open_id: String,
}

#[derive(Debug, Deserialize)]
struct FeishuLegacyCardAction {
    #[serde(default)]
    open_id: String,
    action: FeishuCardActionDetail,
}

#[derive(Debug, Deserialize)]
struct FeishuCardActionDetail {
    #[serde(default)]
    value: Value,
}

#[derive(Debug)]
struct FeishuCardActionContext {
    action_type: String,
    requirement_id: String,
    operator_id: String,
    action_value: Value,
}

#[derive(Debug, Deserialize)]
struct EncryptedWebhookRequest {
    #[serde(default)]
    encrypt: String,
}

pub fn router(config: GatewayConfig) -> Router {
    router_with_state_store(config, Arc::new(InMemoryStateStore::new()))
}

pub fn router_with_state_store(
    config: GatewayConfig,
    state_store: Arc<dyn GatewayStateStore>,
) -> Router {
    router_with_services(config, state_store, None)
}

pub fn router_with_services(
    config: GatewayConfig,
    state_store: Arc<dyn GatewayStateStore>,
    requirement_client: Option<RequirementClient>,
) -> Router {
    router_with_components(
        config,
        state_store,
        GatewayComponents {
            requirement_client,
            ..GatewayComponents::default()
        },
    )
}

pub fn router_with_components(
    config: GatewayConfig,
    state_store: Arc<dyn GatewayStateStore>,
    components: GatewayComponents,
) -> Router {
    let GatewayComponents {
        requirement_client,
        bitable_forwarder,
        feishu_forwarder,
        feishu_messenger,
        pjm_forwarder,
        wecom_messenger,
    } = components;
    let deduplicator = Deduplicator::new(state_store.clone(), Duration::from_secs(10));
    let session_manager = SessionManager::new(state_store.clone(), Duration::from_secs(5 * 60));
    let state = AppState {
        config: Arc::new(config),
        state_store,
        requirement_client,
        matcher: Matcher::new(),
        deduplicator,
        session_manager,
        bitable_forwarder,
        feishu_forwarder,
        feishu_messenger,
        pjm_forwarder,
        wecom_messenger,
    };

    let rate_limiter = RateLimiter::from_config(&state.config);

    Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/api/feishu/webhook", post(feishu_webhook))
        .route("/api/wecom/webhook", get(wecom_verify).post(wecom_webhook))
        .route("/webhook/feishu", post(feishu_webhook))
        .route("/webhook/wecom", get(wecom_verify).post(wecom_webhook))
        .with_state(state)
        .layer(middleware::from_fn_with_state(
            rate_limiter,
            rate_limit_middleware,
        ))
        .layer(middleware::from_fn(request_context_middleware))
}

async fn request_context_middleware(
    mut request: Request<axum::body::Body>,
    next: Next,
) -> Response {
    let started_at = Instant::now();
    let method = request.method().clone();
    let uri = request.uri().clone();
    let user_agent = request
        .headers()
        .get(USER_AGENT)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
        .to_string();
    let context = request_context_from_headers(request.headers());

    request.extensions_mut().insert(context.clone());

    let mut response = next.run(request).await;
    insert_header(response.headers_mut(), &X_REQUEST_ID, &context.request_id);
    insert_header(response.headers_mut(), &X_TRACE_ID, &context.trace_id);

    let status = response.status();
    let latency = started_at.elapsed();
    let path = uri.path();
    let query = uri.query().unwrap_or_default();
    let content_length = response
        .headers()
        .get(axum::http::header::CONTENT_LENGTH)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();

    match status.as_u16() {
        500..=599 => error!(
            status = status.as_u16(),
            method = %method,
            path,
            query,
            user_agent,
            body_size = content_length,
            latency_ms = latency.as_millis(),
            request_id = %context.request_id,
            trace_id = %context.trace_id,
            "request completed"
        ),
        400..=499 => warn!(
            status = status.as_u16(),
            method = %method,
            path,
            query,
            user_agent,
            body_size = content_length,
            latency_ms = latency.as_millis(),
            request_id = %context.request_id,
            trace_id = %context.trace_id,
            "request completed"
        ),
        _ => info!(
            status = status.as_u16(),
            method = %method,
            path,
            query,
            user_agent,
            body_size = content_length,
            latency_ms = latency.as_millis(),
            request_id = %context.request_id,
            trace_id = %context.trace_id,
            "request completed"
        ),
    }

    response
}

async fn rate_limit_middleware(
    State(rate_limiter): State<RateLimiter>,
    request: Request<axum::body::Body>,
    next: Next,
) -> Response {
    rate_limiter.acquire().await;
    next.run(request).await
}

fn request_context_from_headers(headers: &HeaderMap) -> RequestContext {
    let request_id = header_string(headers, &X_REQUEST_ID).unwrap_or_else(generate_request_id);
    let trace_id = header_string(headers, &X_TRACE_ID).unwrap_or_else(|| request_id.clone());

    RequestContext {
        request_id,
        trace_id,
    }
}

fn header_string(headers: &HeaderMap, name: &HeaderName) -> Option<String> {
    headers
        .get(name)
        .and_then(|value| value.to_str().ok())
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn insert_header(headers: &mut HeaderMap, name: &HeaderName, value: &str) {
    if let Ok(value) = HeaderValue::from_str(value) {
        headers.insert(name, value);
    }
}

fn generate_request_id() -> String {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default();
    let counter = REQUEST_COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("req_{millis:x}_{counter:x}")
}

async fn health() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok",
        version: VERSION,
        services: None,
    })
}

async fn ready(State(state): State<AppState>) -> Json<HealthResponse> {
    let mut services = BTreeMap::new();
    services.insert(
        "ai_service",
        format!("configured: {}", state.config.grpc_ai_service_addr),
    );
    services.insert("redis", format!("configured: {}", state.config.redis_addr));

    let mut status = "ok";
    if let Some(client) = state.requirement_client {
        match client.health_check().await {
            Ok(response) if response.healthy => {
                services.insert(
                    "requirement_service",
                    format!("healthy: {}", response.version),
                );
            }
            Ok(response) => {
                status = "degraded";
                services.insert(
                    "requirement_service",
                    format!("unhealthy: {}", response.version),
                );
            }
            Err(err) => {
                status = "degraded";
                services.insert("requirement_service", format!("error: {}", err.code()));
            }
        }
    }

    Json(HealthResponse {
        status,
        version: VERSION,
        services: Some(services),
    })
}

async fn feishu_webhook(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let (parse_body, encrypted_body) = match decrypt_feishu_body(&body, &state.config) {
        Ok(result) => result,
        Err(response) => return *response,
    };

    let payload: FeishuWebhookRequest = match serde_json::from_slice(&parse_body) {
        Ok(payload) => payload,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({ "code": -1, "msg": "invalid json" })),
            )
                .into_response();
        }
    };

    if let Err(response) =
        verify_feishu_request(&headers, &body, &state.config, &payload, encrypted_body)
    {
        return *response;
    }

    if payload.r#type == "url_verification" {
        return Json(json!({ "challenge": payload.challenge })).into_response();
    }

    if let Some(header) = payload.header.as_ref() {
        if header.event_type == "im.message.receive_v1" {
            handle_feishu_message_event(&state, header, &payload.event, &parse_body).await;
            return Json(json!({ "code": 0 })).into_response();
        }
        if header.event_type == "card.action.trigger" {
            return handle_feishu_card_action_trigger(&state, &payload.event).await;
        }
        return Json(json!({ "code": 0 })).into_response();
    }

    if payload.r#type == "card_action" || !payload.action.is_null() {
        return handle_feishu_legacy_card_action(&state, &parse_body).await;
    }

    if payload.r#type == "event_callback" {
        return Json(json!({ "code": 0 })).into_response();
    }

    Json(json!({ "code": 0 })).into_response()
}

async fn handle_feishu_message_event(
    state: &AppState,
    header: &FeishuEventHeader,
    event: &Value,
    forward_body: &[u8],
) {
    if !header.event_id.is_empty()
        && matches!(
            state.deduplicator.is_duplicate(&header.event_id).await,
            Ok(true)
        )
    {
        return;
    }

    let Ok(event) = serde_json::from_value::<feishu::MessageEvent>(event.clone()) else {
        return;
    };

    if !event.message.message_id.is_empty()
        && matches!(
            state
                .deduplicator
                .is_duplicate(&event.message.message_id)
                .await,
            Ok(true)
        )
    {
        return;
    }

    let content =
        feishu::parse_message_content(&event.message.message_type, &event.message.content);
    let user_id = event.sender.sender_id.open_id;
    let chat_id = event.message.chat_id;

    let _ = state
        .session_manager
        .add_message(&chat_id, &user_id, "user", &content)
        .await;

    let Some(skill_match) = state.matcher.match_message(&content) else {
        if let Err(err) = state.feishu_forwarder.forward(forward_body).await {
            warn!(
                error = %err,
                event_id = %header.event_id,
                "failed to forward unmatched Feishu message to Python chat gateway",
            );
        }
        return;
    };

    execute_feishu_requirement_skill(
        state,
        &skill_match,
        &chat_id,
        &user_id,
        &event.message.message_id,
    )
    .await;
}

async fn handle_feishu_card_action_trigger(state: &AppState, event: &Value) -> Response {
    let Ok(event) = serde_json::from_value::<FeishuCardActionTriggerEvent>(event.clone()) else {
        return Json(json!({ "code": 0 })).into_response();
    };

    let action_context = feishu_card_action_context(event.operator.open_id, event.action.value);
    let Some(card) = dispatch_feishu_card_action(state, &action_context).await else {
        return Json(json!({ "code": 0 })).into_response();
    };

    Json(json!({
        "card": {
            "type": "raw",
            "data": card,
        }
    }))
    .into_response()
}

async fn handle_feishu_legacy_card_action(state: &AppState, body: &[u8]) -> Response {
    let Ok(action) = serde_json::from_slice::<FeishuLegacyCardAction>(body) else {
        return Json(json!({ "code": 0 })).into_response();
    };

    let action_context = feishu_card_action_context(action.open_id, action.action.value);
    let Some(card) = dispatch_feishu_card_action(state, &action_context).await else {
        return Json(json!({ "code": 0 })).into_response();
    };

    Json(card).into_response()
}

fn feishu_card_action_context(operator_id: String, action_value: Value) -> FeishuCardActionContext {
    let action_type = action_value
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let requirement_id = action_value
        .get("requirement_id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();

    FeishuCardActionContext {
        action_type,
        requirement_id,
        operator_id,
        action_value,
    }
}

async fn dispatch_feishu_card_action(
    state: &AppState,
    action_context: &FeishuCardActionContext,
) -> Option<crate::feishu_outbound::Card> {
    match action_context.action_type.as_str() {
        "confirm" => {
            if action_context.requirement_id.is_empty() {
                return None;
            }
            let card = match state.requirement_client.as_ref() {
                Some(client) => match client
                    .confirm_requirement(
                        &action_context.requirement_id,
                        &action_context.operator_id,
                    )
                    .await
                {
                    Ok(response) if response.success => {
                        let requirement = response
                            .requirement
                            .as_ref()
                            .map(card_requirement_from_proto);
                        build_operation_result_card("confirm", true, requirement.as_ref(), "")
                    }
                    Ok(response) => {
                        build_operation_result_card("confirm", false, None, &response.error)
                    }
                    Err(err) => {
                        build_operation_result_card("confirm", false, None, &err.to_string())
                    }
                },
                None => return None,
            };
            Some(card)
        }
        "reject" => {
            if action_context.requirement_id.is_empty() {
                return None;
            }
            let reason = action_context
                .action_value
                .get("reason")
                .and_then(Value::as_str)
                .unwrap_or_default();
            let card = match state.requirement_client.as_ref() {
                Some(client) => match client
                    .reject_requirement(
                        &action_context.requirement_id,
                        reason,
                        &action_context.operator_id,
                    )
                    .await
                {
                    Ok(response) if response.success => {
                        let requirement = response
                            .requirement
                            .as_ref()
                            .map(card_requirement_from_proto);
                        build_operation_result_card("reject", true, requirement.as_ref(), "")
                    }
                    Ok(response) => {
                        build_operation_result_card("reject", false, None, &response.error)
                    }
                    Err(err) => {
                        build_operation_result_card("reject", false, None, &err.to_string())
                    }
                },
                None => return None,
            };
            Some(card)
        }
        "list_page" => {
            let client = state.requirement_client.as_ref()?;
            let page = parse_page_action_value(action_context.action_value.get("page"));
            let Ok(response) = client.list_requirements("PENDING", page, 5).await else {
                return None;
            };
            let requirements = response
                .requirements
                .iter()
                .map(card_requirement_from_proto)
                .collect::<Vec<_>>();
            Some(build_requirements_list_card(
                &requirements,
                page,
                response.total_pages,
                response.total,
            ))
        }
        "confirm_bitable_update" => {
            if dedup_bitable_action(state, "confirm_update", &action_context.action_value).await {
                return Some(build_bitable_duplicate_card());
            }
            let card = match state
                .bitable_forwarder
                .confirm_update(&action_context.action_value, &action_context.operator_id)
                .await
            {
                Ok(card) => card,
                Err(err) if err.is_timeout() => build_decomposition_processing_card(),
                Err(BitableError::NotConfigured) => {
                    build_bitable_error_card("聊天服务未配置，无法执行更新")
                }
                Err(err) => build_bitable_error_card(&format!("转发确认请求失败：{err}")),
            };
            Some(card)
        }
        "reject_bitable_update" => {
            let card = match state
                .bitable_forwarder
                .reject_operation(
                    &action_context.action_value,
                    &action_context.operator_id,
                    "update",
                )
                .await
            {
                Ok(card) => card,
                Err(_) => build_bitable_cancel_card(),
            };
            Some(card)
        }
        "confirm_bitable_create" => {
            if dedup_bitable_action(state, "confirm_create", &action_context.action_value).await {
                return Some(build_bitable_duplicate_card());
            }
            let card = match state
                .bitable_forwarder
                .create_record(&action_context.action_value, &action_context.operator_id)
                .await
            {
                Ok(card) => card,
                Err(err) if err.is_timeout() => build_decomposition_processing_card(),
                Err(BitableError::NotConfigured) => {
                    build_bitable_error_card("聊天服务未配置，无法创建任务")
                }
                Err(err) => build_bitable_error_card(&format!("转发创建请求失败：{err}")),
            };
            Some(card)
        }
        "reject_bitable_create" => {
            let card = match state
                .bitable_forwarder
                .reject_operation(
                    &action_context.action_value,
                    &action_context.operator_id,
                    "create",
                )
                .await
            {
                Ok(card) => card,
                Err(_) => build_bitable_cancel_card(),
            };
            Some(card)
        }
        "approve_decomposition" | "reject_decomposition" => {
            let wp_id = parse_i64_action_value(action_context.action_value.get("wp_id"))?;
            let action = if action_context.action_type == "approve_decomposition" {
                "approve"
            } else {
                "reject"
            };
            let card = match state
                .pjm_forwarder
                .forward_decomposition_action(wp_id, action, &action_context.operator_id)
                .await
            {
                Ok(result) => build_decomposition_action_result_card(
                    action,
                    wp_id,
                    &result.subject,
                    result.story_count,
                    result.task_count,
                ),
                Err(PjmForwardError::NotConfigured) => {
                    build_decomposition_error_card("PJM Agent 服务未配置")
                }
                Err(err) if err.is_timeout() => build_decomposition_processing_card(),
                Err(err) => build_decomposition_error_card(&err.to_string()),
            };
            Some(card)
        }
        _ => None,
    }
}

async fn dedup_bitable_action(state: &AppState, action_type: &str, value: &Value) -> bool {
    let raw = serde_json::to_vec(value).unwrap_or_default();
    let mut hasher = Sha256::new();
    hasher.update(&raw);
    let hash = hex::encode(hasher.finalize());
    let key = format!("dedup:bitable:{action_type}:{}", &hash[..16]);

    match state
        .state_store
        .set_nx_with_ttl(&key, b"1", Duration::from_secs(30))
        .await
    {
        Ok(inserted) => !inserted,
        Err(_) => false,
    }
}

async fn execute_feishu_requirement_skill(
    state: &AppState,
    skill_match: &SkillMatch,
    chat_id: &str,
    user_id: &str,
    message_id: &str,
) {
    match skill_match.skill_name.as_str() {
        "list" => {
            let Some(client) = state.requirement_client.as_ref() else {
                return;
            };
            let page = skill_match
                .parameters
                .get("page")
                .map(String::as_str)
                .map(parse_page_param)
                .unwrap_or(1);
            let Ok(response) = client.list_requirements("PENDING", page, 5).await else {
                return;
            };
            let requirements = response
                .requirements
                .iter()
                .map(card_requirement_from_proto)
                .collect::<Vec<_>>();
            let card = build_requirements_list_card(
                &requirements,
                page,
                response.total_pages,
                response.total,
            );
            let _ = state
                .feishu_messenger
                .send_card("chat_id", chat_id, &card)
                .await;
        }
        "confirm" => {
            let Some(requirement_id) = skill_match.parameters.get("requirement_id") else {
                return;
            };
            let card = match state.requirement_client.as_ref() {
                Some(client) => match client.confirm_requirement(requirement_id, user_id).await {
                    Ok(response) if response.success => {
                        let requirement = response
                            .requirement
                            .as_ref()
                            .map(card_requirement_from_proto);
                        build_operation_result_card("confirm", true, requirement.as_ref(), "")
                    }
                    Ok(response) => {
                        build_operation_result_card("confirm", false, None, &response.error)
                    }
                    Err(err) => {
                        build_operation_result_card("confirm", false, None, &err.to_string())
                    }
                },
                None => build_operation_result_card(
                    "confirm",
                    false,
                    None,
                    "requirement service is not configured",
                ),
            };
            let _ = state.feishu_messenger.reply_card(message_id, &card).await;
        }
        "reject" => {
            let Some(requirement_id) = skill_match.parameters.get("requirement_id") else {
                return;
            };
            let reason = skill_match
                .parameters
                .get("reason")
                .map(String::as_str)
                .unwrap_or_default();
            let card = match state.requirement_client.as_ref() {
                Some(client) => match client
                    .reject_requirement(requirement_id, reason, user_id)
                    .await
                {
                    Ok(response) if response.success => {
                        let requirement = response
                            .requirement
                            .as_ref()
                            .map(card_requirement_from_proto);
                        build_operation_result_card("reject", true, requirement.as_ref(), "")
                    }
                    Ok(response) => {
                        build_operation_result_card("reject", false, None, &response.error)
                    }
                    Err(err) => {
                        build_operation_result_card("reject", false, None, &err.to_string())
                    }
                },
                None => build_operation_result_card(
                    "reject",
                    false,
                    None,
                    "requirement service is not configured",
                ),
            };
            let _ = state.feishu_messenger.reply_card(message_id, &card).await;
        }
        "search" => {
            let keyword = skill_match
                .parameters
                .get("keyword")
                .map(|value| value.trim())
                .unwrap_or_default();
            if keyword.is_empty() {
                let card = build_operation_result_card(
                    "search",
                    false,
                    None,
                    "请输入 /search <关键词> 搜索需求。",
                );
                let _ = state.feishu_messenger.reply_card(message_id, &card).await;
                return;
            }
            let Some(client) = state.requirement_client.as_ref() else {
                return;
            };
            let Ok(response) = client.search_requirements(keyword, chat_id, 1, 5).await else {
                return;
            };
            let requirements = response
                .requirements
                .iter()
                .map(card_requirement_from_proto)
                .collect::<Vec<_>>();
            let card = build_requirements_search_card(keyword, &requirements, response.total);
            let _ = state.feishu_messenger.reply_card(message_id, &card).await;
        }
        "help" => {
            let card = build_help_card();
            let _ = state.feishu_messenger.reply_card(message_id, &card).await;
        }
        _ => {}
    }
}

fn card_requirement_from_proto(
    requirement: &crate::requirement_client::proto::Requirement,
) -> CardRequirement {
    CardRequirement {
        id: requirement.id.clone(),
        title: requirement.title.clone(),
        description: requirement.description.clone(),
        status: requirement.status.clone(),
        priority: requirement.priority.clone(),
        category: requirement.category.clone(),
    }
}

async fn execute_wecom_requirement_skill(
    state: &AppState,
    skill_match: &SkillMatch,
    chat_id: &str,
    user_id: &str,
) {
    match skill_match.skill_name.as_str() {
        "list" => {
            let Some(client) = state.requirement_client.as_ref() else {
                send_wecom_error(state, user_id, "需求服务未配置").await;
                return;
            };
            let page = skill_match
                .parameters
                .get("page")
                .map(String::as_str)
                .map(parse_page_param)
                .unwrap_or(1);
            match client.list_requirements("PENDING", page, 5).await {
                Ok(response) => {
                    let requirements = response
                        .requirements
                        .iter()
                        .map(wecom_requirement_from_proto)
                        .collect::<Vec<_>>();
                    let markdown = build_wecom_requirements_markdown(
                        &requirements,
                        page,
                        response.total_pages,
                        response.total,
                    );
                    let _ = state
                        .wecom_messenger
                        .send_markdown(user_id, &markdown)
                        .await;
                }
                Err(_) => send_wecom_error(state, user_id, "获取需求列表失败").await,
            }
        }
        "confirm" => {
            let Some(requirement_id) = skill_match.parameters.get("requirement_id") else {
                send_wecom_error(state, user_id, "请提供需求ID").await;
                return;
            };
            let Some(client) = state.requirement_client.as_ref() else {
                send_wecom_error(state, user_id, "需求服务未配置").await;
                return;
            };
            match client.confirm_requirement(requirement_id, user_id).await {
                Ok(response) if response.success => {
                    let text = build_wecom_operation_text("confirm", requirement_id);
                    let _ = state.wecom_messenger.send_text(user_id, &text).await;
                }
                Ok(response) => {
                    let message = format!("确认失败: {}", response.error);
                    send_wecom_error(state, user_id, &message).await;
                }
                Err(err) => {
                    let message = format!("确认失败: {err}");
                    send_wecom_error(state, user_id, &message).await;
                }
            }
        }
        "reject" => {
            let Some(requirement_id) = skill_match.parameters.get("requirement_id") else {
                send_wecom_error(state, user_id, "请提供需求ID").await;
                return;
            };
            let reason = skill_match
                .parameters
                .get("reason")
                .map(String::as_str)
                .unwrap_or_default();
            let Some(client) = state.requirement_client.as_ref() else {
                send_wecom_error(state, user_id, "需求服务未配置").await;
                return;
            };
            match client
                .reject_requirement(requirement_id, reason, user_id)
                .await
            {
                Ok(response) if response.success => {
                    let text = build_wecom_operation_text("reject", requirement_id);
                    let _ = state.wecom_messenger.send_text(user_id, &text).await;
                }
                Ok(response) => {
                    let message = format!("拒绝失败: {}", response.error);
                    send_wecom_error(state, user_id, &message).await;
                }
                Err(err) => {
                    let message = format!("拒绝失败: {err}");
                    send_wecom_error(state, user_id, &message).await;
                }
            }
        }
        "search" => {
            let keyword = skill_match
                .parameters
                .get("keyword")
                .map(|value| value.trim())
                .unwrap_or_default();
            if keyword.is_empty() {
                send_wecom_error(state, user_id, "请输入 /search <关键词> 搜索需求").await;
                return;
            }
            let Some(client) = state.requirement_client.as_ref() else {
                send_wecom_error(state, user_id, "需求服务未配置").await;
                return;
            };
            match client.search_requirements(keyword, chat_id, 1, 5).await {
                Ok(response) => {
                    let requirements = response
                        .requirements
                        .iter()
                        .map(wecom_requirement_from_proto)
                        .collect::<Vec<_>>();
                    let markdown = build_wecom_requirements_search_markdown(
                        keyword,
                        &requirements,
                        response.total,
                    );
                    let _ = state
                        .wecom_messenger
                        .send_markdown(user_id, &markdown)
                        .await;
                }
                Err(_) => send_wecom_error(state, user_id, "搜索需求失败").await,
            }
        }
        "help" => {
            let _ = state
                .wecom_messenger
                .send_markdown(user_id, build_wecom_help_markdown())
                .await;
        }
        _ => {}
    }
}

fn wecom_requirement_from_proto(
    requirement: &crate::requirement_client::proto::Requirement,
) -> WecomRequirement {
    WecomRequirement {
        id: requirement.id.clone(),
        title: requirement.title.clone(),
        description: requirement.description.clone(),
        priority: requirement.priority.clone(),
    }
}

async fn send_wecom_error(state: &AppState, user_id: &str, message: &str) {
    let text = build_error_text(message);
    let _ = state.wecom_messenger.send_text(user_id, &text).await;
}

fn parse_page_param(value: &str) -> i32 {
    value
        .parse::<i32>()
        .ok()
        .filter(|page| *page > 0)
        .unwrap_or(1)
}

fn parse_page_action_value(value: Option<&Value>) -> i32 {
    match value {
        Some(Value::Number(number)) => {
            if let Some(page) = number.as_i64() {
                i32::try_from(page)
                    .ok()
                    .filter(|page| *page > 0)
                    .unwrap_or(1)
            } else if let Some(page) = number.as_u64() {
                i32::try_from(page)
                    .ok()
                    .filter(|page| *page > 0)
                    .unwrap_or(1)
            } else {
                1
            }
        }
        Some(Value::String(value)) => parse_page_param(value),
        _ => 1,
    }
}

fn parse_i64_action_value(value: Option<&Value>) -> Option<i64> {
    match value {
        Some(Value::Number(number)) => number
            .as_i64()
            .or_else(|| number.as_u64().and_then(|value| i64::try_from(value).ok())),
        Some(Value::String(value)) => value.parse::<i64>().ok(),
        _ => None,
    }
    .filter(|value| *value > 0)
}

fn decrypt_feishu_body(
    body: &[u8],
    config: &GatewayConfig,
) -> Result<(Vec<u8>, bool), Box<Response>> {
    let wrapper = serde_json::from_slice::<EncryptedWebhookRequest>(body).ok();
    let Some(wrapper) = wrapper.filter(|wrapper| !wrapper.encrypt.is_empty()) else {
        return Ok((body.to_vec(), false));
    };

    if config.feishu_encrypt_key.is_empty() {
        return Err(Box::new(
            (
                StatusCode::BAD_REQUEST,
                Json(json!({ "code": -1, "msg": "invalid encrypted body" })),
            )
                .into_response(),
        ));
    }

    feishu::decrypt_message(&wrapper.encrypt, &config.feishu_encrypt_key)
        .map(|body| (body, true))
        .map_err(|_| {
            Box::new(
                (
                    StatusCode::BAD_REQUEST,
                    Json(json!({ "code": -1, "msg": "invalid encrypted body" })),
                )
                    .into_response(),
            )
        })
}

fn verify_feishu_request(
    headers: &HeaderMap,
    raw_body: &[u8],
    config: &GatewayConfig,
    payload: &FeishuWebhookRequest,
    encrypted_body: bool,
) -> Result<(), Box<Response>> {
    if !config.feishu_verify_signature {
        return Ok(());
    }

    let timestamp = required_header(headers, "x-lark-request-timestamp");
    let nonce = required_header(headers, "x-lark-request-nonce");
    let signature = required_header(headers, "x-lark-signature");

    let unsigned_encrypted_challenge = encrypted_body
        && payload.r#type == "url_verification"
        && timestamp.is_none()
        && nonce.is_none()
        && signature.is_none();
    if unsigned_encrypted_challenge {
        return Ok(());
    }

    let (Some(timestamp), Some(nonce), Some(signature)) = (timestamp, nonce, signature) else {
        return Err(invalid_feishu_signature_response());
    };

    if config.feishu_encrypt_key.is_empty() {
        return Err(Box::new(
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({ "code": -1, "msg": "signature verification is not configured" })),
            )
                .into_response(),
        ));
    }

    if !feishu::verify_signature(
        timestamp,
        nonce,
        &config.feishu_encrypt_key,
        raw_body,
        signature,
    ) {
        return Err(invalid_feishu_signature_response());
    }

    Ok(())
}

fn required_header<'a>(headers: &'a HeaderMap, name: &str) -> Option<&'a str> {
    headers
        .get(name)
        .and_then(|value| value.to_str().ok())
        .filter(|value| !value.is_empty())
}

fn invalid_feishu_signature_response() -> Box<Response> {
    Box::new(
        (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "code": -1, "msg": "invalid signature" })),
        )
            .into_response(),
    )
}

fn required_query<'a>(params: &'a HashMap<String, String>, key: &str) -> Option<&'a str> {
    params
        .get(key)
        .map(String::as_str)
        .filter(|value| !value.is_empty())
}

async fn wecom_verify(
    State(state): State<AppState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    let crypt = match wecom_crypto(&state.config) {
        Ok(crypt) => crypt,
        Err(response) => return *response,
    };

    let (Some(msg_signature), Some(timestamp), Some(nonce), Some(echo_str)) = (
        required_query(&params, "msg_signature"),
        required_query(&params, "timestamp"),
        required_query(&params, "nonce"),
        required_query(&params, "echostr"),
    ) else {
        return (StatusCode::FORBIDDEN, "verification failed").into_response();
    };

    match crypt.verify_url(msg_signature, timestamp, nonce, echo_str) {
        Ok(echo) => (StatusCode::OK, echo).into_response(),
        Err(_) => (StatusCode::FORBIDDEN, "verification failed").into_response(),
    }
}

async fn wecom_webhook(
    State(state): State<AppState>,
    Query(params): Query<HashMap<String, String>>,
    body: Bytes,
) -> Response {
    let crypt = match wecom_crypto(&state.config) {
        Ok(crypt) => crypt,
        Err(response) => return *response,
    };

    let (Some(msg_signature), Some(timestamp), Some(nonce)) = (
        required_query(&params, "msg_signature"),
        required_query(&params, "timestamp"),
        required_query(&params, "nonce"),
    ) else {
        return (StatusCode::FORBIDDEN, "decrypt failed").into_response();
    };

    match crypt.decrypt_msg(msg_signature, timestamp, nonce, &body) {
        Ok(plain) => {
            handle_wecom_message(&state, &plain).await;
            (StatusCode::OK, "success").into_response()
        }
        Err(_) => (StatusCode::FORBIDDEN, "decrypt failed").into_response(),
    }
}

async fn handle_wecom_message(state: &AppState, plain: &[u8]) {
    let Ok(message) = crate::wecom::parse_received_message(plain) else {
        return;
    };

    if !message.msg_id.is_empty()
        && matches!(
            state.deduplicator.is_duplicate(&message.msg_id).await,
            Ok(true)
        )
    {
        return;
    }

    match message.msg_type.as_str() {
        "text" | "voice" => {
            let content = crate::wecom::parse_message_content(&message);
            let _ = state
                .session_manager
                .add_message("", &message.from_user_name, "user", &content)
                .await;

            if let Some(skill_match) = state.matcher.match_message(&content) {
                execute_wecom_requirement_skill(state, &skill_match, "", &message.from_user_name)
                    .await;
            }
        }
        "event" if message.event == "click" && message.event_key == "list_requirements" => {
            let skill_match = SkillMatch {
                skill_name: "list".to_string(),
                confidence: 1.0,
                parameters: HashMap::new(),
                match_type: MatchType::Command,
            };
            execute_wecom_requirement_skill(state, &skill_match, "", &message.from_user_name).await;
        }
        "event" if message.event == "click" && message.event_key == "help" => {
            let _ = state
                .wecom_messenger
                .send_markdown(&message.from_user_name, build_wecom_help_markdown())
                .await;
        }
        "event" if message.event == "template_card_event" => {
            handle_wecom_template_card_event(state, &message).await;
        }
        _ => {}
    }
}

async fn handle_wecom_template_card_event(
    state: &AppState,
    message: &crate::wecom::ReceivedMessage,
) {
    let Some(action) = crate::wecom::parse_template_action(&message.event_key) else {
        return;
    };

    info!(
        action_id = %action.action_id,
        response_code = %message.response_code,
        task_id = %message.task_id,
        "wecom template card action received"
    );

    match action.action_id.as_str() {
        "confirm" | "confirm_requirement" => {
            let requirement_id =
                first_string_value(&action.value, &["requirement_id", "req_id", "id", "value"]);
            if requirement_id.is_empty() {
                send_wecom_error(state, &message.from_user_name, "请提供需求ID").await;
                return;
            }
            confirm_wecom_template_requirement(
                state,
                &message.from_user_name,
                &message.response_code,
                &requirement_id,
            )
            .await;
        }
        "reject" | "reject_requirement" => {
            let requirement_id =
                first_string_value(&action.value, &["requirement_id", "req_id", "id", "value"]);
            if requirement_id.is_empty() {
                send_wecom_error(state, &message.from_user_name, "请提供需求ID").await;
                return;
            }
            let reason = first_string_value(&action.value, &["reason"]);
            reject_wecom_template_requirement(
                state,
                &message.from_user_name,
                &message.response_code,
                &requirement_id,
                &reason,
            )
            .await;
        }
        "list" | "list_requirements" => {
            let skill_match = SkillMatch {
                skill_name: "list".to_string(),
                confidence: 1.0,
                parameters: HashMap::new(),
                match_type: MatchType::Command,
            };
            execute_wecom_requirement_skill(state, &skill_match, "", &message.from_user_name).await;
        }
        "help" => {
            let _ = state
                .wecom_messenger
                .send_markdown(&message.from_user_name, build_wecom_help_markdown())
                .await;
        }
        _ => {}
    }
}

async fn confirm_wecom_template_requirement(
    state: &AppState,
    user_id: &str,
    response_code: &str,
    requirement_id: &str,
) {
    let Some(client) = state.requirement_client.as_ref() else {
        send_wecom_error(state, user_id, "需求服务未配置").await;
        return;
    };

    match client.confirm_requirement(requirement_id, user_id).await {
        Ok(response) if response.success => {
            let text = build_wecom_operation_text("confirm", requirement_id);
            update_wecom_template_card_or_text(state, user_id, response_code, "需求已确认", &text)
                .await;
        }
        Ok(response) => {
            let message = format!("确认失败: {}", response.error);
            send_wecom_error(state, user_id, &message).await;
        }
        Err(err) => {
            let message = format!("确认失败: {err}");
            send_wecom_error(state, user_id, &message).await;
        }
    }
}

async fn reject_wecom_template_requirement(
    state: &AppState,
    user_id: &str,
    response_code: &str,
    requirement_id: &str,
    reason: &str,
) {
    let Some(client) = state.requirement_client.as_ref() else {
        send_wecom_error(state, user_id, "需求服务未配置").await;
        return;
    };

    match client
        .reject_requirement(requirement_id, reason, user_id)
        .await
    {
        Ok(response) if response.success => {
            let text = build_wecom_operation_text("reject", requirement_id);
            update_wecom_template_card_or_text(state, user_id, response_code, "需求已拒绝", &text)
                .await;
        }
        Ok(response) => {
            let message = format!("拒绝失败: {}", response.error);
            send_wecom_error(state, user_id, &message).await;
        }
        Err(err) => {
            let message = format!("拒绝失败: {err}");
            send_wecom_error(state, user_id, &message).await;
        }
    }
}

async fn update_wecom_template_card_or_text(
    state: &AppState,
    user_id: &str,
    response_code: &str,
    title: &str,
    fallback_text: &str,
) {
    if response_code.is_empty() {
        let _ = state
            .wecom_messenger
            .send_text(user_id, fallback_text)
            .await;
        return;
    }

    let card = build_wecom_template_card_result(title, fallback_text);
    if state
        .wecom_messenger
        .update_template_card(response_code, &card)
        .await
        .is_err()
    {
        let _ = state
            .wecom_messenger
            .send_text(user_id, fallback_text)
            .await;
    }
}

fn first_string_value(value: &Value, keys: &[&str]) -> String {
    keys.iter()
        .find_map(|key| value.get(*key).and_then(Value::as_str))
        .unwrap_or_default()
        .to_string()
}

fn wecom_crypto(config: &GatewayConfig) -> Result<WecomCrypto, Box<Response>> {
    if config.wecom_corp_id.is_empty()
        || config.wecom_token.is_empty()
        || config.wecom_encoding_aes_key.is_empty()
    {
        return Err(Box::new(
            (StatusCode::SERVICE_UNAVAILABLE, "wecom is not configured").into_response(),
        ));
    }

    WecomCrypto::new(
        config.wecom_token.clone(),
        &config.wecom_encoding_aes_key,
        config.wecom_corp_id.clone(),
    )
    .map_err(|_| {
        Box::new(
            (
                StatusCode::SERVICE_UNAVAILABLE,
                "wecom crypto is not configured",
            )
                .into_response(),
        )
    })
}

#[cfg(test)]
mod tests {
    use super::{
        request_context_from_headers, router, router_with_components, router_with_services,
        GatewayComponents, X_REQUEST_ID, X_TRACE_ID,
    };
    use crate::bitable_forward::{BitableActionForwarder, BitableError};
    use crate::config::GatewayConfig;
    use crate::feishu::verify_signature;
    use crate::feishu_forward::{FeishuEventForwarder, FeishuForwardError};
    use crate::feishu_outbound::{Card, FeishuError, FeishuMessenger};
    use crate::pjm_forward::{PjmActionForwarder, PjmDecompositionResult, PjmForwardError};
    use crate::requirement_client::{
        proto::{
            requirement_service_server::{RequirementService, RequirementServiceServer},
            ConfirmRequest, ExtractRequest, ExtractResponse, GetRequest, HealthRequest,
            HealthResponse as RequirementHealthResponse, ListRequest, ListResponse,
            OperationResponse, RejectRequest, Requirement, SearchRequest, SearchResponse,
        },
        RequirementClient,
    };
    use crate::state::InMemoryStateStore;
    use crate::wecom::{decode_encoding_aes_key, WecomCrypto};
    use crate::wecom_outbound::{WecomError, WecomMessenger};
    use aes::Aes256;
    use axum::{
        body::{to_bytes, Body},
        http::{HeaderMap, HeaderValue, Method, Request, StatusCode},
    };
    use base64::{engine::general_purpose, Engine as _};
    use cbc::cipher::{block_padding::Pkcs7, BlockEncryptMut, KeyIvInit};
    use serde_json::Value;
    use std::{
        net::SocketAddr,
        sync::{
            atomic::{AtomicU64, Ordering},
            Arc, Mutex,
        },
        time::{Duration, Instant, SystemTime, UNIX_EPOCH},
    };
    use tokio::net::TcpListener;
    use tokio_stream::wrappers::TcpListenerStream;
    use tonic::{Response as TonicResponse, Status};
    use tower::ServiceExt;

    type Aes256CbcEnc = cbc::Encryptor<Aes256>;

    const WECOM_TOKEN: &str = "test-token";
    const WECOM_KEY: &str = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";
    const WECOM_CORP_ID: &str = "corp123";

    #[tokio::test]
    async fn health_contract_matches_gateway_liveness() {
        let app = router(GatewayConfig::from_lookup(|_| None));

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        assert!(response.headers().get("x-request-id").is_some());
        assert!(response.headers().get("x-trace-id").is_some());
        let body = response.into_body();
        let body = to_bytes(body, usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["status"], "ok");
        assert_eq!(json["version"], "0.1.0-rust");
    }

    #[tokio::test]
    async fn request_context_preserves_trace_and_request_headers() {
        let app = router(GatewayConfig::from_lookup(|_| None));

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("x-request-id", "request-id-123")
                    .header("x-trace-id", "trace-id-123")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers().get("x-request-id").unwrap(),
            "request-id-123"
        );
        assert_eq!(
            response.headers().get("x-trace-id").unwrap(),
            "trace-id-123"
        );
    }

    #[test]
    fn request_context_uses_request_id_as_trace_fallback() {
        let mut headers = HeaderMap::new();
        headers.insert(&X_REQUEST_ID, HeaderValue::from_static("request-only"));

        let context = request_context_from_headers(&headers);

        assert_eq!(context.request_id, "request-only");
        assert_eq!(context.trace_id, "request-only");
    }

    #[test]
    fn request_context_generates_missing_ids() {
        let context = request_context_from_headers(&HeaderMap::new());

        assert!(context.request_id.starts_with("req_"));
        assert_eq!(context.trace_id, context.request_id);
    }

    #[test]
    fn request_context_preserves_independent_trace_header() {
        let mut headers = HeaderMap::new();
        headers.insert(&X_REQUEST_ID, HeaderValue::from_static("request-id"));
        headers.insert(&X_TRACE_ID, HeaderValue::from_static("trace-id"));

        let context = request_context_from_headers(&headers);

        assert_eq!(context.request_id, "request-id");
        assert_eq!(context.trace_id, "trace-id");
    }

    #[tokio::test]
    async fn ready_reports_configured_dependencies() {
        let app = router(GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_GRPC_AI_SERVICE_ADDR" => Some("ai-core:50051".to_string()),
            "GATEWAY_REDIS_ADDR" => Some("redis:6379".to_string()),
            _ => None,
        }));

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/ready")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["services"]["ai_service"], "configured: ai-core:50051");
        assert_eq!(json["services"]["redis"], "configured: redis:6379");
    }

    #[tokio::test]
    async fn global_rate_limiter_waits_after_burst_is_spent() {
        let app = router(GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_RATELIMIT_ENABLED" => Some("true".to_string()),
            "GATEWAY_RATELIMIT_RPS" => Some("50".to_string()),
            "GATEWAY_RATELIMIT_BURST_SIZE" => Some("1".to_string()),
            _ => None,
        }));

        let first = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(first.status(), StatusCode::OK);

        let start = Instant::now();
        let second = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(second.status(), StatusCode::OK);
        assert!(start.elapsed() >= Duration::from_millis(10));
    }

    #[tokio::test]
    async fn ready_reports_requirement_service_health() {
        let requirement_addr = spawn_requirement_health_server(true).await;
        let client =
            RequirementClient::connect_lazy(&requirement_addr.to_string(), Duration::from_secs(5))
                .expect("build requirement client");
        let app = router_with_services(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_GRPC_AI_SERVICE_ADDR" => Some(requirement_addr.to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            Some(client),
        );

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/ready")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["status"], "ok");
        assert_eq!(json["services"]["requirement_service"], "healthy: mock");
    }

    #[tokio::test]
    async fn feishu_text_skill_confirm_calls_requirement_service_once() {
        let (requirement_addr, calls) = spawn_recording_requirement_server().await;
        let feishu = Arc::new(RecordingFeishuMessenger::default());
        let client =
            RequirementClient::connect_lazy(&requirement_addr.to_string(), Duration::from_secs(5))
                .expect("build requirement client");
        let app = router_with_components(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
                "GATEWAY_GRPC_AI_SERVICE_ADDR" => Some(requirement_addr.to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                requirement_client: Some(client),
                feishu_messenger: feishu.clone(),
                ..GatewayComponents::default()
            },
        );
        let body = serde_json::json!({
            "header": {
                "event_id": "evt_confirm_1",
                "event_type": "im.message.receive_v1"
            },
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_user_1"}
                },
                "message": {
                    "message_id": "msg_confirm_1",
                    "chat_id": "oc_chat_1",
                    "message_type": "text",
                    "content": "{\"text\":\"/confirm req_123\"}"
                }
            }
        });

        for _ in 0..2 {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::POST)
                        .uri("/api/feishu/webhook")
                        .header("content-type", "application/json")
                        .body(Body::from(body.to_string()))
                        .unwrap(),
                )
                .await
                .unwrap();

            assert_eq!(response.status(), StatusCode::OK);
        }

        let calls = calls.lock().unwrap();
        assert_eq!(
            calls.confirm,
            vec![("req_123".to_string(), "ou_user_1".to_string())]
        );
        let replies = feishu.replies.lock().unwrap();
        assert_eq!(replies.len(), 1);
        assert_eq!(replies[0].0, "msg_confirm_1");
        assert_eq!(replies[0].1["header"]["template"], "green");
    }

    #[tokio::test]
    async fn feishu_unmatched_message_forwards_raw_callback_to_chat_agent() {
        let forwarder = Arc::new(RecordingFeishuForwarder::default());
        let app = router_with_components(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                feishu_forwarder: forwarder.clone(),
                ..GatewayComponents::default()
            },
        );
        let body = serde_json::json!({
            "header": {
                "event_id": "evt_forward_1",
                "event_type": "im.message.receive_v1"
            },
            "event": {
                "sender": {
                    "sender_id": {"open_id": "ou_user_forward"}
                },
                "message": {
                    "message_id": "msg_forward_1",
                    "chat_id": "oc_chat_forward",
                    "message_type": "text",
                    "content": "{\"text\":\"hello ordinary question\"}"
                }
            }
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let forwarded = forwarder.bodies.lock().unwrap();
        assert_eq!(forwarded.len(), 1);
        let forwarded_json: Value = serde_json::from_slice(&forwarded[0]).unwrap();
        assert_eq!(forwarded_json, body);
    }

    #[tokio::test]
    async fn feishu_v2_card_action_confirm_returns_raw_card() {
        let (requirement_addr, calls) = spawn_recording_requirement_server().await;
        let client =
            RequirementClient::connect_lazy(&requirement_addr.to_string(), Duration::from_secs(5))
                .expect("build requirement client");
        let app = router_with_components(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
                "GATEWAY_GRPC_AI_SERVICE_ADDR" => Some(requirement_addr.to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                requirement_client: Some(client),
                ..GatewayComponents::default()
            },
        );
        let body = serde_json::json!({
            "header": {
                "event_id": "evt_card_confirm_1",
                "event_type": "card.action.trigger"
            },
            "event": {
                "operator": {"open_id": "ou_operator_1"},
                "action": {
                    "value": {
                        "action": "confirm",
                        "requirement_id": "req_card_1"
                    }
                }
            }
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["card"]["type"], "raw");
        assert_eq!(json["card"]["data"]["header"]["template"], "green");
        let calls = calls.lock().unwrap();
        assert_eq!(
            calls.confirm,
            vec![("req_card_1".to_string(), "ou_operator_1".to_string())]
        );
    }

    #[tokio::test]
    async fn feishu_legacy_card_action_reject_returns_direct_card() {
        let (requirement_addr, calls) = spawn_recording_requirement_server().await;
        let client =
            RequirementClient::connect_lazy(&requirement_addr.to_string(), Duration::from_secs(5))
                .expect("build requirement client");
        let app = router_with_components(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
                "GATEWAY_GRPC_AI_SERVICE_ADDR" => Some(requirement_addr.to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                requirement_client: Some(client),
                ..GatewayComponents::default()
            },
        );
        let body = serde_json::json!({
            "type": "card_action",
            "open_id": "ou_operator_2",
            "action": {
                "value": {
                    "action": "reject",
                    "requirement_id": "req_card_2",
                    "reason": "needs more detail"
                }
            }
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["header"]["template"], "green");
        assert!(json["elements"].to_string().contains("req_card_2"));
        let calls = calls.lock().unwrap();
        assert_eq!(
            calls.reject,
            vec![(
                "req_card_2".to_string(),
                "needs more detail".to_string(),
                "ou_operator_2".to_string()
            )]
        );
    }

    #[tokio::test]
    async fn feishu_card_action_list_page_returns_list_card() {
        let (requirement_addr, calls) = spawn_recording_requirement_server().await;
        let client =
            RequirementClient::connect_lazy(&requirement_addr.to_string(), Duration::from_secs(5))
                .expect("build requirement client");
        let app = router_with_components(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
                "GATEWAY_GRPC_AI_SERVICE_ADDR" => Some(requirement_addr.to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                requirement_client: Some(client),
                ..GatewayComponents::default()
            },
        );
        let body = serde_json::json!({
            "type": "card_action",
            "open_id": "ou_operator_3",
            "action": {
                "value": {
                    "action": "list_page",
                    "page": 2
                }
            }
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["header"]["template"], "blue");
        assert!(json["elements"].to_string().contains("req_list_1"));
        let calls = calls.lock().unwrap();
        assert_eq!(calls.list, vec![("PENDING".to_string(), 2, 5)]);
    }

    #[tokio::test]
    async fn feishu_card_action_confirm_bitable_update_forwards_to_chat_agent() {
        let bitable = Arc::new(RecordingBitableForwarder::default());
        let app = router_with_components(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                bitable_forwarder: bitable.clone(),
                ..GatewayComponents::default()
            },
        );
        let body = serde_json::json!({
            "header": {
                "event_id": "evt_bitable_confirm_1",
                "event_type": "card.action.trigger"
            },
            "event": {
                "operator": {"open_id": "ou_bitable_operator"},
                "action": {
                    "value": {
                        "action": "confirm_bitable_update",
                        "record_id": "rec_abc123",
                        "table_id": "tbl_1",
                        "fields": {"状态": "已完成"}
                    }
                }
            }
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["card"]["data"]["header"]["template"], "green");
        assert_eq!(
            json["card"]["data"]["header"]["title"]["content"],
            "表格更新完成"
        );
        let calls = bitable.confirm_updates.lock().unwrap();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].0, "ou_bitable_operator");
        assert_eq!(calls[0].1["record_id"], "rec_abc123");
        assert_eq!(calls[0].1["fields"]["状态"], "已完成");
    }

    #[tokio::test]
    async fn feishu_card_action_confirm_bitable_update_deduplicates_repeat_click() {
        let bitable = Arc::new(RecordingBitableForwarder::default());
        let app = router_with_components(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                bitable_forwarder: bitable.clone(),
                ..GatewayComponents::default()
            },
        );
        let body = serde_json::json!({
            "header": {
                "event_id": "evt_bitable_confirm_repeat",
                "event_type": "card.action.trigger"
            },
            "event": {
                "operator": {"open_id": "ou_bitable_operator"},
                "action": {
                    "value": {
                        "action": "confirm_bitable_update",
                        "record_id": "rec_repeat",
                        "table_id": "tbl_1",
                        "fields": {"状态": "已完成"}
                    }
                }
            }
        });

        for _ in 0..2 {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::POST)
                        .uri("/api/feishu/webhook")
                        .header("content-type", "application/json")
                        .body(Body::from(body.to_string()))
                        .unwrap(),
                )
                .await
                .unwrap();

            assert_eq!(response.status(), StatusCode::OK);
            let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
            let json: Value = serde_json::from_slice(&body).unwrap();
            if bitable.confirm_updates.lock().unwrap().len() == 1
                && json["card"]["data"]["header"]["title"]["content"] == "已处理"
            {
                assert_eq!(json["card"]["data"]["header"]["template"], "green");
            }
        }

        let calls = bitable.confirm_updates.lock().unwrap();
        assert_eq!(calls.len(), 1);
    }

    #[tokio::test]
    async fn feishu_card_action_reject_bitable_create_forwards_cancel() {
        let bitable = Arc::new(RecordingBitableForwarder::default());
        let app = router_with_components(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                bitable_forwarder: bitable.clone(),
                ..GatewayComponents::default()
            },
        );
        let body = serde_json::json!({
            "type": "card_action",
            "open_id": "ou_bitable_rejector",
            "action": {
                "value": {
                    "action": "reject_bitable_create",
                    "table_id": "tbl_2",
                    "fields": {"标题": "Task"}
                }
            }
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["header"]["template"], "grey");
        let calls = bitable.rejects.lock().unwrap();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].0, "ou_bitable_rejector");
        assert_eq!(calls[0].1, "create");
        assert_eq!(calls[0].2["fields"]["标题"], "Task");
    }

    #[tokio::test]
    async fn feishu_card_action_approve_decomposition_forwards_to_pjm() {
        let pjm = Arc::new(RecordingPjmForwarder::default());
        let app = router_with_components(
            GatewayConfig::from_lookup(|key| match key {
                "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
                _ => None,
            }),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                pjm_forwarder: pjm.clone(),
                ..GatewayComponents::default()
            },
        );
        let body = serde_json::json!({
            "header": {
                "event_id": "evt_pjm_approve_1",
                "event_type": "card.action.trigger"
            },
            "event": {
                "operator": {"open_id": "ou_pjm_operator"},
                "action": {
                    "value": {
                        "action": "approve_decomposition",
                        "wp_id": 42
                    }
                }
            }
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["card"]["data"]["header"]["template"], "green");
        assert_eq!(
            json["card"]["data"]["header"]["title"]["content"],
            "任务拆解已批准"
        );
        let calls = pjm.calls.lock().unwrap();
        assert_eq!(
            calls.as_slice(),
            &[(42, "approve".to_string(), "ou_pjm_operator".to_string())]
        );
    }

    #[tokio::test]
    async fn feishu_url_verification_returns_challenge() {
        let app = router(GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
            _ => None,
        }));

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        r#"{"type":"url_verification","challenge":"abc"}"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["challenge"], "abc");
    }

    #[tokio::test]
    async fn feishu_event_acknowledges_callback() {
        let app = router(GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_FEISHU_VERIFY_SIGNATURE" => Some("false".to_string()),
            _ => None,
        }));

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/webhook/feishu")
                    .header("content-type", "application/json")
                    .body(Body::from(r#"{"type":"event_callback"}"#))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["code"], 0);
    }

    #[tokio::test]
    async fn feishu_rejects_unsigned_request_when_signature_is_enabled() {
        let app = router(GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_FEISHU_ENCRYPT_KEY" => Some("test-encrypt-key".to_string()),
            _ => None,
        }));

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .body(Body::from(r#"{"type":"event_callback"}"#))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn feishu_accepts_valid_signature() {
        let body = br#"{"type":"event_callback"}"#;
        let timestamp = "1704067200";
        let nonce = test_nonce();
        let encrypt_key = "test-encrypt-key";
        let signature = signature_for(timestamp, &nonce, encrypt_key, body);
        assert!(verify_signature(
            timestamp,
            &nonce,
            encrypt_key,
            body,
            &signature
        ));

        let app = router(GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_FEISHU_ENCRYPT_KEY" => Some(encrypt_key.to_string()),
            _ => None,
        }));

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/feishu/webhook")
                    .header("content-type", "application/json")
                    .header("x-lark-request-timestamp", timestamp)
                    .header("x-lark-request-nonce", nonce.as_str())
                    .header("x-lark-signature", signature)
                    .body(Body::from(body.as_slice()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let json: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["code"], 0);
    }

    #[tokio::test]
    async fn wecom_get_verifies_url() {
        let crypt = WecomCrypto::new(WECOM_TOKEN, WECOM_KEY, WECOM_CORP_ID).unwrap();
        let encrypted = encrypt_wecom_for_test("echo-ok", WECOM_KEY, WECOM_CORP_ID);
        let nonce = test_nonce();
        let signature = crypt.generate_signature("1704067200", &nonce, &encrypted);
        let app = router(wecom_test_config());

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri(format!(
                        "/api/wecom/webhook?msg_signature={}&timestamp=1704067200&nonce={nonce}&echostr={}",
                        signature,
                        encode_query_component(&encrypted)
                    ))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert_eq!(&body[..], b"echo-ok");
    }

    #[tokio::test]
    async fn wecom_post_decrypts_and_acknowledges_callback() {
        let crypt = WecomCrypto::new(WECOM_TOKEN, WECOM_KEY, WECOM_CORP_ID).unwrap();
        let plain =
            "<xml><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[hello]]></Content></xml>";
        let encrypted = encrypt_wecom_for_test(plain, WECOM_KEY, WECOM_CORP_ID);
        let nonce = test_nonce();
        let signature = crypt.generate_signature("1704067200", &nonce, &encrypted);
        let xml = format!(
            "<xml><ToUserName><![CDATA[{WECOM_CORP_ID}]]></ToUserName><Encrypt><![CDATA[{encrypted}]]></Encrypt><AgentID>1</AgentID></xml>"
        );
        let app = router(wecom_test_config());

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri(format!(
                        "/api/wecom/webhook?msg_signature={signature}&timestamp=1704067200&nonce={nonce}"
                    ))
                    .body(Body::from(xml))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert_eq!(&body[..], b"success");
    }

    #[tokio::test]
    async fn wecom_text_skill_confirm_calls_requirement_service_once() {
        let (requirement_addr, calls) = spawn_recording_requirement_server().await;
        let wecom = Arc::new(RecordingWecomMessenger::default());
        let client =
            RequirementClient::connect_lazy(&requirement_addr.to_string(), Duration::from_secs(5))
                .expect("build requirement client");
        let crypt = WecomCrypto::new(WECOM_TOKEN, WECOM_KEY, WECOM_CORP_ID).unwrap();
        let plain = "<xml><FromUserName><![CDATA[wecom_user_1]]></FromUserName><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[/confirm req_wecom_1]]></Content><MsgId>777</MsgId></xml>";
        let encrypted = encrypt_wecom_for_test(plain, WECOM_KEY, WECOM_CORP_ID);
        let nonce = test_nonce();
        let signature = crypt.generate_signature("1704067200", &nonce, &encrypted);
        let xml = format!(
            "<xml><ToUserName><![CDATA[{WECOM_CORP_ID}]]></ToUserName><Encrypt><![CDATA[{encrypted}]]></Encrypt><AgentID>1</AgentID></xml>"
        );
        let app = router_with_components(
            wecom_test_config(),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                requirement_client: Some(client),
                wecom_messenger: wecom.clone(),
                ..GatewayComponents::default()
            },
        );

        for _ in 0..2 {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::POST)
                        .uri(format!(
                            "/api/wecom/webhook?msg_signature={signature}&timestamp=1704067200&nonce={nonce}"
                        ))
                        .body(Body::from(xml.clone()))
                        .unwrap(),
                )
                .await
                .unwrap();

            assert_eq!(response.status(), StatusCode::OK);
            let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
            assert_eq!(&body[..], b"success");
        }

        let calls = calls.lock().unwrap();
        assert_eq!(
            calls.confirm,
            vec![("req_wecom_1".to_string(), "wecom_user_1".to_string())]
        );
        let texts = wecom.texts.lock().unwrap();
        assert_eq!(texts.len(), 1);
        assert_eq!(texts[0].0, "wecom_user_1");
        assert_eq!(texts[0].1, "✅ 需求 req_wecom_1 已确认");
    }

    #[tokio::test]
    async fn wecom_click_list_sends_markdown_response() {
        let (requirement_addr, _calls) = spawn_recording_requirement_server().await;
        let wecom = Arc::new(RecordingWecomMessenger::default());
        let client =
            RequirementClient::connect_lazy(&requirement_addr.to_string(), Duration::from_secs(5))
                .expect("build requirement client");
        let crypt = WecomCrypto::new(WECOM_TOKEN, WECOM_KEY, WECOM_CORP_ID).unwrap();
        let plain = "<xml><FromUserName><![CDATA[wecom_user_2]]></FromUserName><MsgType><![CDATA[event]]></MsgType><Event><![CDATA[click]]></Event><EventKey><![CDATA[list_requirements]]></EventKey><MsgId>778</MsgId></xml>";
        let encrypted = encrypt_wecom_for_test(plain, WECOM_KEY, WECOM_CORP_ID);
        let nonce = test_nonce();
        let signature = crypt.generate_signature("1704067200", &nonce, &encrypted);
        let xml = format!(
            "<xml><ToUserName><![CDATA[{WECOM_CORP_ID}]]></ToUserName><Encrypt><![CDATA[{encrypted}]]></Encrypt><AgentID>1</AgentID></xml>"
        );
        let app = router_with_components(
            wecom_test_config(),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                requirement_client: Some(client),
                wecom_messenger: wecom.clone(),
                ..GatewayComponents::default()
            },
        );

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri(format!(
                        "/api/wecom/webhook?msg_signature={signature}&timestamp=1704067200&nonce={nonce}"
                    ))
                    .body(Body::from(xml))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let markdowns = wecom.markdowns.lock().unwrap();
        assert_eq!(markdowns.len(), 1);
        assert_eq!(markdowns[0].0, "wecom_user_2");
        assert!(markdowns[0].1.contains("待确认需求"));
    }

    #[tokio::test]
    async fn wecom_template_card_confirm_event_calls_requirement_service() {
        let (requirement_addr, calls) = spawn_recording_requirement_server().await;
        let wecom = Arc::new(RecordingWecomMessenger::default());
        let client =
            RequirementClient::connect_lazy(&requirement_addr.to_string(), Duration::from_secs(5))
                .expect("build requirement client");
        let crypt = WecomCrypto::new(WECOM_TOKEN, WECOM_KEY, WECOM_CORP_ID).unwrap();
        let plain = r#"<xml><FromUserName><![CDATA[wecom_user_3]]></FromUserName><MsgType><![CDATA[event]]></MsgType><Event><![CDATA[template_card_event]]></Event><EventKey><![CDATA[confirm:{"req_id":"req_wecom_card_1"}]]></EventKey><ResponseCode><![CDATA[resp_card_1]]></ResponseCode><TaskId><![CDATA[task_card_1]]></TaskId><MsgId>779</MsgId></xml>"#;
        let encrypted = encrypt_wecom_for_test(plain, WECOM_KEY, WECOM_CORP_ID);
        let nonce = test_nonce();
        let signature = crypt.generate_signature("1704067200", &nonce, &encrypted);
        let xml = format!(
            "<xml><ToUserName><![CDATA[{WECOM_CORP_ID}]]></ToUserName><Encrypt><![CDATA[{encrypted}]]></Encrypt><AgentID>1</AgentID></xml>"
        );
        let app = router_with_components(
            wecom_test_config(),
            Arc::new(InMemoryStateStore::new()),
            GatewayComponents {
                requirement_client: Some(client),
                wecom_messenger: wecom.clone(),
                ..GatewayComponents::default()
            },
        );

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri(format!(
                        "/api/wecom/webhook?msg_signature={signature}&timestamp=1704067200&nonce={nonce}"
                    ))
                    .body(Body::from(xml))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert_eq!(&body[..], b"success");
        let calls = calls.lock().unwrap();
        assert_eq!(
            calls.confirm,
            vec![("req_wecom_card_1".to_string(), "wecom_user_3".to_string())]
        );
        let updates = wecom.card_updates.lock().unwrap();
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0].0, "resp_card_1");
        assert_eq!(updates[0].1["main_title"]["title"], "需求已确认");
        assert_eq!(
            updates[0].1["sub_title_text"],
            "✅ 需求 req_wecom_card_1 已确认"
        );
        let texts = wecom.texts.lock().unwrap();
        assert!(texts.is_empty());
    }

    #[tokio::test]
    async fn wecom_rejects_unconfigured_route() {
        let app = router(GatewayConfig::from_lookup(|_| None));

        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/wecom/webhook")
                    .body(Body::from("<xml></xml>"))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    fn signature_for(timestamp: &str, nonce: &str, encrypt_key: &str, body: &[u8]) -> String {
        use sha2::{Digest, Sha256};

        let mut hasher = Sha256::new();
        hasher.update(timestamp.as_bytes());
        hasher.update(nonce.as_bytes());
        hasher.update(encrypt_key.as_bytes());
        hasher.update(body);
        hex::encode(hasher.finalize())
    }

    fn test_nonce() -> String {
        static NONCE_COUNTER: AtomicU64 = AtomicU64::new(1);
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let counter = NONCE_COUNTER.fetch_add(1, Ordering::Relaxed);
        format!("{nanos:x}{counter:x}")
    }

    fn wecom_test_config() -> GatewayConfig {
        GatewayConfig::from_lookup(|key| match key {
            "GATEWAY_WECOM_CORP_ID" => Some(WECOM_CORP_ID.to_string()),
            "GATEWAY_WECOM_TOKEN" => Some(WECOM_TOKEN.to_string()),
            "GATEWAY_WECOM_ENCODING_AES_KEY" => Some(WECOM_KEY.to_string()),
            _ => None,
        })
    }

    fn encrypt_wecom_for_test(plain_text: &str, encoding_aes_key: &str, corp_id: &str) -> String {
        let aes_key = decode_encoding_aes_key(encoding_aes_key).unwrap();
        let mut plain = Vec::new();
        plain.extend_from_slice(&test_random_prefix());
        plain.extend_from_slice(&(plain_text.len() as u32).to_be_bytes());
        plain.extend_from_slice(plain_text.as_bytes());
        plain.extend_from_slice(corp_id.as_bytes());

        let msg_len = plain.len();
        plain.resize(msg_len + 16, 0);
        let cipher_text = Aes256CbcEnc::new_from_slices(&aes_key, &aes_key[..16])
            .unwrap()
            .encrypt_padded_mut::<Pkcs7>(&mut plain, msg_len)
            .unwrap();

        general_purpose::STANDARD.encode(cipher_text)
    }

    fn test_random_prefix() -> [u8; 16] {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
            .to_be_bytes()
    }

    fn encode_query_component(value: &str) -> String {
        value
            .replace('%', "%25")
            .replace('+', "%2B")
            .replace('/', "%2F")
            .replace('=', "%3D")
    }

    async fn spawn_requirement_health_server(healthy: bool) -> SocketAddr {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let incoming = TcpListenerStream::new(listener);
        tokio::spawn(async move {
            tonic::transport::Server::builder()
                .add_service(RequirementServiceServer::new(
                    HealthOnlyRequirementService { healthy },
                ))
                .serve_with_incoming(incoming)
                .await
                .expect("mock requirement health server");
        });
        addr
    }

    struct HealthOnlyRequirementService {
        healthy: bool,
    }

    #[tonic::async_trait]
    impl RequirementService for HealthOnlyRequirementService {
        async fn extract_requirements(
            &self,
            _request: tonic::Request<ExtractRequest>,
        ) -> Result<TonicResponse<ExtractResponse>, Status> {
            Err(Status::unimplemented("not needed"))
        }

        async fn list_requirements(
            &self,
            _request: tonic::Request<ListRequest>,
        ) -> Result<TonicResponse<ListResponse>, Status> {
            Err(Status::unimplemented("not needed"))
        }

        async fn get_requirement(
            &self,
            _request: tonic::Request<GetRequest>,
        ) -> Result<TonicResponse<Requirement>, Status> {
            Err(Status::unimplemented("not needed"))
        }

        async fn confirm_requirement(
            &self,
            _request: tonic::Request<ConfirmRequest>,
        ) -> Result<TonicResponse<OperationResponse>, Status> {
            Err(Status::unimplemented("not needed"))
        }

        async fn reject_requirement(
            &self,
            _request: tonic::Request<RejectRequest>,
        ) -> Result<TonicResponse<OperationResponse>, Status> {
            Err(Status::unimplemented("not needed"))
        }

        async fn search_requirements(
            &self,
            _request: tonic::Request<SearchRequest>,
        ) -> Result<TonicResponse<SearchResponse>, Status> {
            Err(Status::unimplemented("not needed"))
        }

        async fn health_check(
            &self,
            _request: tonic::Request<HealthRequest>,
        ) -> Result<TonicResponse<RequirementHealthResponse>, Status> {
            Ok(TonicResponse::new(RequirementHealthResponse {
                healthy: self.healthy,
                version: "mock".to_string(),
                services: [("db".to_string(), self.healthy)].into_iter().collect(),
            }))
        }
    }

    #[derive(Default)]
    struct RecordingFeishuMessenger {
        sent: Mutex<Vec<(String, String, Value)>>,
        replies: Mutex<Vec<(String, Value)>>,
    }

    #[async_trait::async_trait]
    impl FeishuMessenger for RecordingFeishuMessenger {
        async fn send_card(
            &self,
            receive_id_type: &str,
            receive_id: &str,
            card: &Card,
        ) -> Result<(), FeishuError> {
            self.sent.lock().unwrap().push((
                receive_id_type.to_string(),
                receive_id.to_string(),
                serde_json::to_value(card).unwrap(),
            ));
            Ok(())
        }

        async fn reply_card(&self, message_id: &str, card: &Card) -> Result<(), FeishuError> {
            self.replies
                .lock()
                .unwrap()
                .push((message_id.to_string(), serde_json::to_value(card).unwrap()));
            Ok(())
        }
    }

    #[derive(Default)]
    struct RecordingFeishuForwarder {
        bodies: Mutex<Vec<Vec<u8>>>,
    }

    #[async_trait::async_trait]
    impl FeishuEventForwarder for RecordingFeishuForwarder {
        async fn forward(&self, body: &[u8]) -> Result<(), FeishuForwardError> {
            self.bodies.lock().unwrap().push(body.to_vec());
            Ok(())
        }
    }

    #[derive(Default)]
    struct RecordingBitableForwarder {
        confirm_updates: Mutex<Vec<(String, Value)>>,
        creates: Mutex<Vec<(String, Value)>>,
        rejects: Mutex<Vec<(String, String, Value)>>,
    }

    #[async_trait::async_trait]
    impl BitableActionForwarder for RecordingBitableForwarder {
        async fn confirm_update(
            &self,
            value: &Value,
            operator: &str,
        ) -> Result<Card, BitableError> {
            self.confirm_updates
                .lock()
                .unwrap()
                .push((operator.to_string(), value.clone()));
            Ok(test_card("表格更新完成", "green"))
        }

        async fn create_record(&self, value: &Value, operator: &str) -> Result<Card, BitableError> {
            self.creates
                .lock()
                .unwrap()
                .push((operator.to_string(), value.clone()));
            Ok(test_card("表格创建完成", "green"))
        }

        async fn reject_operation(
            &self,
            value: &Value,
            operator: &str,
            action_type: &str,
        ) -> Result<Card, BitableError> {
            self.rejects.lock().unwrap().push((
                operator.to_string(),
                action_type.to_string(),
                value.clone(),
            ));
            Ok(test_card("已取消", "grey"))
        }
    }

    fn test_card(title: &str, template: &str) -> Card {
        Card {
            config: None,
            header: Some(serde_json::json!({
                "title": {"tag": "plain_text", "content": title},
                "template": template,
            })),
            elements: vec![serde_json::json!({"tag": "markdown", "content": "ok"})],
        }
    }

    #[derive(Default)]
    struct RecordingPjmForwarder {
        calls: Mutex<Vec<(i64, String, String)>>,
    }

    #[async_trait::async_trait]
    impl PjmActionForwarder for RecordingPjmForwarder {
        async fn forward_decomposition_action(
            &self,
            wp_id: i64,
            action: &str,
            operator: &str,
        ) -> Result<PjmDecompositionResult, PjmForwardError> {
            self.calls
                .lock()
                .unwrap()
                .push((wp_id, action.to_string(), operator.to_string()));
            Ok(PjmDecompositionResult {
                success: true,
                wp_id,
                action: action.to_string(),
                message: "Written to OP".to_string(),
                subject: "Split feature".to_string(),
                story_count: 1,
                task_count: 3,
            })
        }
    }

    #[derive(Default)]
    struct RecordingWecomMessenger {
        texts: Mutex<Vec<(String, String)>>,
        markdowns: Mutex<Vec<(String, String)>>,
        card_updates: Mutex<Vec<(String, Value)>>,
    }

    #[async_trait::async_trait]
    impl WecomMessenger for RecordingWecomMessenger {
        async fn send_text(&self, user_id: &str, content: &str) -> Result<(), WecomError> {
            self.texts
                .lock()
                .unwrap()
                .push((user_id.to_string(), content.to_string()));
            Ok(())
        }

        async fn send_markdown(&self, user_id: &str, content: &str) -> Result<(), WecomError> {
            self.markdowns
                .lock()
                .unwrap()
                .push((user_id.to_string(), content.to_string()));
            Ok(())
        }

        async fn update_template_card(
            &self,
            response_code: &str,
            card: &Value,
        ) -> Result<(), WecomError> {
            self.card_updates
                .lock()
                .unwrap()
                .push((response_code.to_string(), card.clone()));
            Ok(())
        }
    }

    #[derive(Default)]
    struct RecordedRequirementCalls {
        confirm: Vec<(String, String)>,
        reject: Vec<(String, String, String)>,
        list: Vec<(String, i32, i32)>,
    }

    async fn spawn_recording_requirement_server(
    ) -> (SocketAddr, Arc<Mutex<RecordedRequirementCalls>>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let incoming = TcpListenerStream::new(listener);
        let calls = Arc::new(Mutex::new(RecordedRequirementCalls::default()));
        let service = RecordingRequirementService {
            calls: calls.clone(),
        };

        tokio::spawn(async move {
            tonic::transport::Server::builder()
                .add_service(RequirementServiceServer::new(service))
                .serve_with_incoming(incoming)
                .await
                .expect("recording requirement server");
        });

        (addr, calls)
    }

    struct RecordingRequirementService {
        calls: Arc<Mutex<RecordedRequirementCalls>>,
    }

    #[tonic::async_trait]
    impl RequirementService for RecordingRequirementService {
        async fn extract_requirements(
            &self,
            _request: tonic::Request<ExtractRequest>,
        ) -> Result<TonicResponse<ExtractResponse>, Status> {
            Err(Status::unimplemented("not needed"))
        }

        async fn list_requirements(
            &self,
            request: tonic::Request<ListRequest>,
        ) -> Result<TonicResponse<ListResponse>, Status> {
            let request = request.into_inner();
            self.calls.lock().unwrap().list.push((
                request.status.clone(),
                request.page,
                request.page_size,
            ));
            Ok(TonicResponse::new(ListResponse {
                requirements: vec![test_requirement("req_list_1")],
                total: 6,
                total_pages: 2,
            }))
        }

        async fn get_requirement(
            &self,
            request: tonic::Request<GetRequest>,
        ) -> Result<TonicResponse<Requirement>, Status> {
            Ok(TonicResponse::new(test_requirement(
                &request.into_inner().id,
            )))
        }

        async fn confirm_requirement(
            &self,
            request: tonic::Request<ConfirmRequest>,
        ) -> Result<TonicResponse<OperationResponse>, Status> {
            let request = request.into_inner();
            self.calls
                .lock()
                .unwrap()
                .confirm
                .push((request.id.clone(), request.confirmed_by.clone()));
            Ok(TonicResponse::new(OperationResponse {
                success: true,
                requirement: Some(test_requirement(&request.id)),
                error: String::new(),
            }))
        }

        async fn reject_requirement(
            &self,
            request: tonic::Request<RejectRequest>,
        ) -> Result<TonicResponse<OperationResponse>, Status> {
            let request = request.into_inner();
            self.calls.lock().unwrap().reject.push((
                request.id.clone(),
                request.reason.clone(),
                request.rejected_by.clone(),
            ));
            Ok(TonicResponse::new(OperationResponse {
                success: true,
                requirement: Some(test_requirement(&request.id)),
                error: request.reason,
            }))
        }

        async fn search_requirements(
            &self,
            _request: tonic::Request<SearchRequest>,
        ) -> Result<TonicResponse<SearchResponse>, Status> {
            Ok(TonicResponse::new(SearchResponse {
                requirements: Vec::new(),
                total: 0,
            }))
        }

        async fn health_check(
            &self,
            _request: tonic::Request<HealthRequest>,
        ) -> Result<TonicResponse<RequirementHealthResponse>, Status> {
            Ok(TonicResponse::new(RequirementHealthResponse {
                healthy: true,
                version: "recording".to_string(),
                services: Default::default(),
            }))
        }
    }

    fn test_requirement(id: &str) -> Requirement {
        Requirement {
            id: id.to_string(),
            title: "Requirement".to_string(),
            description: "description".to_string(),
            status: "PENDING".to_string(),
            priority: "MEDIUM".to_string(),
            category: "product".to_string(),
            source_quote: String::new(),
            confirmed_by: String::new(),
            confirmed_at: 0,
            rejection_reason: String::new(),
            created_at: 0,
            updated_at: 0,
        }
    }
}
