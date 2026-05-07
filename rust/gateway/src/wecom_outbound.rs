use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    error::Error,
    fmt,
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::sync::RwLock;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WecomRequirement {
    pub id: String,
    pub title: String,
    pub description: String,
    pub priority: String,
}

pub fn build_requirements_markdown(
    requirements: &[WecomRequirement],
    page: i32,
    total_pages: i32,
    total: i32,
) -> String {
    if requirements.is_empty() {
        return "📋 **待确认需求**\n\n暂无待确认的需求 ✨".to_string();
    }

    let mut markdown = format!("📋 **待确认需求** ({}条)\n\n", total);
    for (index, requirement) in requirements.iter().enumerate() {
        markdown.push_str(&format!(
            "{}. **{}** {}\n",
            index + 1,
            requirement.title,
            priority_emoji(&requirement.priority)
        ));
        markdown.push_str(&format!(
            "   {}\n",
            truncate_description(&requirement.description)
        ));
        markdown.push_str(&format!("   ID: `{}`\n\n", requirement.id));
    }

    markdown.push_str(&format!(
        "---\n第 {}/{} 页 | 回复 `/confirm <ID>` 确认",
        page.max(1),
        total_pages.max(1)
    ));
    markdown
}

pub fn build_requirements_search_markdown(
    keyword: &str,
    requirements: &[WecomRequirement],
    total: i32,
) -> String {
    if requirements.is_empty() {
        return format!("🔎 **需求搜索**\n\n没有找到与 `{}` 相关的需求。", keyword);
    }

    let mut markdown = format!("🔎 **需求搜索：{}** ({}条)\n\n", keyword, total);
    for (index, requirement) in requirements.iter().enumerate() {
        markdown.push_str(&format!(
            "{}. **{}** {}\n",
            index + 1,
            requirement.title,
            priority_emoji(&requirement.priority)
        ));
        markdown.push_str(&format!(
            "   {}\n",
            truncate_description(&requirement.description)
        ));
        markdown.push_str(&format!("   ID: `{}`\n\n", requirement.id));
    }
    markdown.push_str("---\n回复 `/confirm <ID>` 确认，或 `/reject <ID> <原因>` 拒绝。");
    markdown
}

pub fn build_help_markdown() -> &'static str {
    "🤖 **Wisdoverse Cell 帮助**\n\n**命令列表：**\n- /list - 查看待确认需求\n- /confirm <ID> - 确认需求\n- /reject <ID> [原因] - 拒绝需求\n- /search <关键词> - 搜索需求\n- /help - 显示帮助\n\n**快捷触发：**\n- 「待确认」「查看需求」→ 显示列表\n- 「确认 <ID>」→ 确认需求\n- 「拒绝 <ID>」→ 拒绝需求"
}

pub fn build_operation_text(action: &str, requirement_id: &str) -> String {
    match action {
        "confirm" => format!("✅ 需求 {} 已确认", requirement_id),
        "reject" => format!("❌ 需求 {} 已拒绝", requirement_id),
        _ => format!("需求 {} 操作已完成", requirement_id),
    }
}

pub fn build_error_text(message: &str) -> String {
    format!("⚠️ {}", message)
}

pub fn build_template_card_result(title: &str, description: &str) -> Value {
    json!({
        "card_type": "button_interaction",
        "source": {"desc": "Requirement Manager"},
        "main_title": {"title": title},
        "sub_title_text": description,
    })
}

fn priority_emoji(priority: &str) -> &'static str {
    match priority {
        "P0" => "🔴",
        "P1" => "🟠",
        "P2" => "🟡",
        _ => "🟢",
    }
}

fn truncate_description(description: &str) -> String {
    let mut chars = description.chars();
    let prefix = chars.by_ref().take(50).collect::<String>();
    if chars.next().is_some() {
        format!("{prefix}...")
    } else {
        prefix
    }
}

#[async_trait]
pub trait WecomMessenger: Send + Sync {
    async fn send_text(&self, user_id: &str, content: &str) -> Result<(), WecomError>;
    async fn send_markdown(&self, user_id: &str, content: &str) -> Result<(), WecomError>;
    async fn update_template_card(
        &self,
        response_code: &str,
        card: &Value,
    ) -> Result<(), WecomError>;
}

#[derive(Clone, Default)]
pub struct NoopWecomMessenger;

#[async_trait]
impl WecomMessenger for NoopWecomMessenger {
    async fn send_text(&self, _user_id: &str, _content: &str) -> Result<(), WecomError> {
        Ok(())
    }

    async fn send_markdown(&self, _user_id: &str, _content: &str) -> Result<(), WecomError> {
        Ok(())
    }

    async fn update_template_card(
        &self,
        _response_code: &str,
        _card: &Value,
    ) -> Result<(), WecomError> {
        Ok(())
    }
}

#[derive(Clone)]
pub struct WecomApiClient {
    corp_id: String,
    agent_id: u64,
    secret: String,
    base_url: String,
    http: reqwest::Client,
    token: Arc<RwLock<Option<TokenCache>>>,
}

#[derive(Clone, Debug)]
struct TokenCache {
    token: String,
    expires_at: Instant,
}

impl WecomApiClient {
    pub fn new(
        corp_id: impl Into<String>,
        agent_id: u64,
        secret: impl Into<String>,
        base_url: impl Into<String>,
    ) -> Self {
        Self {
            corp_id: corp_id.into(),
            agent_id,
            secret: secret.into(),
            base_url: base_url.into().trim_end_matches('/').to_string(),
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .expect("build WeCom HTTP client"),
            token: Arc::new(RwLock::new(None)),
        }
    }

    async fn access_token(&self) -> Result<String, WecomError> {
        if let Some(cache) = self.token.read().await.as_ref() {
            if Instant::now() < cache.expires_at {
                return Ok(cache.token.clone());
            }
        }

        let mut write = self.token.write().await;
        if let Some(cache) = write.as_ref() {
            if Instant::now() < cache.expires_at {
                return Ok(cache.token.clone());
            }
        }

        let response = self
            .http
            .get(format!("{}/gettoken", self.base_url))
            .query(&[
                ("corpid", self.corp_id.as_str()),
                ("corpsecret", self.secret.as_str()),
            ])
            .send()
            .await?
            .json::<TokenResponse>()
            .await?;

        if response.errcode != 0 {
            return Err(WecomError::Api {
                code: response.errcode,
                message: response.errmsg,
            });
        }

        let token = response.access_token;
        let refresh_seconds = response.expires_in.saturating_sub(300).max(1);
        *write = Some(TokenCache {
            token: token.clone(),
            expires_at: Instant::now() + Duration::from_secs(refresh_seconds),
        });
        Ok(token)
    }

    async fn send_message(&self, request: SendMessageRequest<'_>) -> Result<(), WecomError> {
        let token = self.access_token().await?;
        let response = self
            .http
            .post(format!("{}/message/send", self.base_url))
            .query(&[("access_token", token.as_str())])
            .json(&request)
            .send()
            .await?
            .json::<ApiResponse>()
            .await?;
        response.into_result()
    }

    async fn update_card(
        &self,
        response_code: &str,
        template_card: &Value,
    ) -> Result<(), WecomError> {
        let token = self.access_token().await?;
        let response = self
            .http
            .post(format!("{}/message/update_template_card", self.base_url))
            .query(&[("access_token", token.as_str())])
            .json(&UpdateTemplateCardRequest {
                userids: Vec::new(),
                agentid: self.agent_id,
                response_code,
                template_card,
            })
            .send()
            .await?
            .json::<ApiResponse>()
            .await?;
        response.into_result()
    }
}

#[async_trait]
impl WecomMessenger for WecomApiClient {
    async fn send_text(&self, user_id: &str, content: &str) -> Result<(), WecomError> {
        self.send_message(SendMessageRequest {
            touser: user_id,
            msgtype: "text",
            agentid: self.agent_id,
            text: Some(MessageContent { content }),
            markdown: None,
        })
        .await
    }

    async fn send_markdown(&self, user_id: &str, content: &str) -> Result<(), WecomError> {
        self.send_message(SendMessageRequest {
            touser: user_id,
            msgtype: "markdown",
            agentid: self.agent_id,
            text: None,
            markdown: Some(MessageContent { content }),
        })
        .await
    }

    async fn update_template_card(
        &self,
        response_code: &str,
        card: &Value,
    ) -> Result<(), WecomError> {
        self.update_card(response_code, card).await
    }
}

#[derive(Debug)]
pub enum WecomError {
    Http(reqwest::Error),
    Api { code: i32, message: String },
}

impl fmt::Display for WecomError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(err) => write!(f, "wecom http error: {err}"),
            Self::Api { code, message } => write!(f, "wecom api error {code}: {message}"),
        }
    }
}

impl Error for WecomError {}

impl From<reqwest::Error> for WecomError {
    fn from(value: reqwest::Error) -> Self {
        Self::Http(value)
    }
}

#[derive(Debug, Deserialize)]
struct TokenResponse {
    errcode: i32,
    #[serde(default)]
    errmsg: String,
    #[serde(default)]
    access_token: String,
    #[serde(default)]
    expires_in: u64,
}

#[derive(Debug, Deserialize)]
struct ApiResponse {
    errcode: i32,
    #[serde(default)]
    errmsg: String,
}

impl ApiResponse {
    fn into_result(self) -> Result<(), WecomError> {
        if self.errcode == 0 {
            Ok(())
        } else {
            Err(WecomError::Api {
                code: self.errcode,
                message: self.errmsg,
            })
        }
    }
}

#[derive(Debug, Serialize)]
struct SendMessageRequest<'a> {
    touser: &'a str,
    msgtype: &'static str,
    agentid: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    text: Option<MessageContent<'a>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    markdown: Option<MessageContent<'a>>,
}

#[derive(Debug, Serialize)]
struct MessageContent<'a> {
    content: &'a str,
}

#[derive(Debug, Serialize)]
struct UpdateTemplateCardRequest<'a> {
    userids: Vec<String>,
    agentid: u64,
    response_code: &'a str,
    template_card: &'a Value,
}

#[cfg(test)]
mod tests {
    use super::{
        build_error_text, build_operation_text, build_requirements_markdown,
        build_requirements_search_markdown, build_template_card_result, WecomApiClient,
        WecomMessenger, WecomRequirement,
    };
    use axum::{
        extract::{Query, State},
        routing::{get, post},
        Json, Router,
    };
    use serde_json::{json, Value};
    use std::{
        collections::HashMap,
        net::SocketAddr,
        sync::{Arc, Mutex},
    };
    use tokio::net::TcpListener;

    #[test]
    fn builds_requirements_markdown_with_truncated_description() {
        let requirements = vec![WecomRequirement {
            id: "req_1".to_string(),
            title: "Checkout flow".to_string(),
            description: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ".to_string(),
            priority: "P1".to_string(),
        }];

        let markdown = build_requirements_markdown(&requirements, 1, 3, 7);

        assert!(markdown.contains("**Checkout flow**"));
        assert!(markdown.contains("ID: `req_1`"));
        assert!(markdown.contains("第 1/3 页"));
        assert!(markdown.contains("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX..."));
    }

    #[test]
    fn builds_search_empty_state_and_operation_text() {
        let markdown = build_requirements_search_markdown("billing", &[], 0);

        assert!(markdown.contains("没有找到与 `billing` 相关的需求"));
        assert_eq!(
            build_operation_text("confirm", "req_2"),
            "✅ 需求 req_2 已确认"
        );
        assert_eq!(build_error_text("失败"), "⚠️ 失败");
        let card = build_template_card_result("Done", "Updated");
        assert_eq!(card["card_type"], "button_interaction");
        assert_eq!(card["main_title"]["title"], "Done");
    }

    #[tokio::test]
    async fn api_client_sends_go_compatible_message_payloads_and_reuses_token() {
        let api = RecordingWecomApi::default();
        let addr = spawn_recording_wecom_api(api.clone()).await;
        let client = WecomApiClient::new("corp_1", 42, "secret_1", format!("http://{addr}"));

        client
            .send_markdown("user_1", "**hello**")
            .await
            .expect("send markdown");
        client.send_text("user_2", "ok").await.expect("send text");
        client
            .update_template_card(
                "resp_1",
                &json!({
                    "card_type": "button_interaction",
                    "main_title": {"title": "Updated"},
                }),
            )
            .await
            .expect("update card");

        assert_eq!(*api.token_calls.lock().unwrap(), 1);
        let messages = api.messages.lock().unwrap();
        assert_eq!(messages.len(), 2);
        assert_eq!(messages[0]["query_access_token"], "token_1");
        assert_eq!(messages[0]["body"]["touser"], "user_1");
        assert_eq!(messages[0]["body"]["msgtype"], "markdown");
        assert_eq!(messages[0]["body"]["agentid"], 42);
        assert_eq!(messages[0]["body"]["markdown"]["content"], "**hello**");
        assert_eq!(messages[1]["body"]["touser"], "user_2");
        assert_eq!(messages[1]["body"]["msgtype"], "text");
        assert_eq!(messages[1]["body"]["text"]["content"], "ok");
        let updates = api.updates.lock().unwrap();
        assert_eq!(updates.len(), 1);
        assert_eq!(updates[0]["query_access_token"], "token_1");
        assert_eq!(updates[0]["body"]["response_code"], "resp_1");
        assert_eq!(updates[0]["body"]["agentid"], 42);
        assert_eq!(updates[0]["body"]["userids"], json!([]));
        assert_eq!(
            updates[0]["body"]["template_card"]["main_title"]["title"],
            "Updated"
        );
    }

    #[derive(Clone, Default)]
    struct RecordingWecomApi {
        token_calls: Arc<Mutex<usize>>,
        messages: Arc<Mutex<Vec<Value>>>,
        updates: Arc<Mutex<Vec<Value>>>,
    }

    async fn spawn_recording_wecom_api(api: RecordingWecomApi) -> SocketAddr {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let app = Router::new()
            .route("/gettoken", get(token_handler))
            .route("/message/send", post(message_handler))
            .route("/message/update_template_card", post(update_card_handler))
            .with_state(api);

        tokio::spawn(async move {
            axum::serve(listener, app)
                .await
                .expect("recording wecom api server");
        });
        addr
    }

    async fn token_handler(
        State(api): State<RecordingWecomApi>,
        Query(query): Query<HashMap<String, String>>,
    ) -> Json<Value> {
        assert_eq!(query.get("corpid").map(String::as_str), Some("corp_1"));
        assert_eq!(
            query.get("corpsecret").map(String::as_str),
            Some("secret_1")
        );
        *api.token_calls.lock().unwrap() += 1;
        Json(json!({
            "errcode": 0,
            "errmsg": "ok",
            "access_token": "token_1",
            "expires_in": 7200
        }))
    }

    async fn message_handler(
        State(api): State<RecordingWecomApi>,
        Query(query): Query<HashMap<String, String>>,
        Json(body): Json<Value>,
    ) -> Json<Value> {
        api.messages.lock().unwrap().push(json!({
            "query_access_token": query.get("access_token").cloned().unwrap_or_default(),
            "body": body,
        }));
        Json(json!({
            "errcode": 0,
            "errmsg": "ok"
        }))
    }

    async fn update_card_handler(
        State(api): State<RecordingWecomApi>,
        Query(query): Query<HashMap<String, String>>,
        Json(body): Json<Value>,
    ) -> Json<Value> {
        api.updates.lock().unwrap().push(json!({
            "query_access_token": query.get("access_token").cloned().unwrap_or_default(),
            "body": body,
        }));
        Json(json!({
            "errcode": 0,
            "errmsg": "ok"
        }))
    }
}
