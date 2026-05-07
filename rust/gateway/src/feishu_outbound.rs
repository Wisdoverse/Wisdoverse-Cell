use std::{error::Error, fmt, sync::Arc, time::Duration};

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::sync::RwLock;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CardRequirement {
    pub id: String,
    pub title: String,
    pub description: String,
    pub status: String,
    pub priority: String,
    pub category: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Card {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub config: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub header: Option<Value>,
    #[serde(default)]
    pub elements: Vec<Value>,
}

impl Card {
    fn new() -> Self {
        Self {
            config: Some(json!({
                "wide_screen_mode": true,
                "enable_forward": true,
            })),
            header: None,
            elements: Vec::new(),
        }
    }

    fn set_header(mut self, title: impl Into<String>, template: impl Into<String>) -> Self {
        self.header = Some(json!({
            "title": {
                "tag": "plain_text",
                "content": title.into(),
            },
            "template": template.into(),
        }));
        self
    }

    fn add_markdown(mut self, content: impl Into<String>) -> Self {
        self.elements.push(json!({
            "tag": "markdown",
            "content": content.into(),
        }));
        self
    }

    fn add_divider(mut self) -> Self {
        self.elements.push(json!({ "tag": "hr" }));
        self
    }

    fn add_actions(mut self, actions: Vec<Value>) -> Self {
        self.elements.push(json!({
            "tag": "action",
            "actions": actions,
        }));
        self
    }

    fn add_note(mut self, content: impl Into<String>) -> Self {
        self.elements.push(json!({
            "tag": "note",
            "elements": [{
                "tag": "plain_text",
                "content": content.into(),
            }],
        }));
        self
    }
}

pub fn build_requirements_list_card(
    requirements: &[CardRequirement],
    page: i32,
    total_pages: i32,
    total: i32,
) -> Card {
    let mut card = Card::new().set_header(format!("待确认需求 ({total})"), "blue");

    if requirements.is_empty() {
        card = card.add_markdown("暂无待确认的需求");
    } else {
        for (index, req) in requirements.iter().enumerate() {
            let content = format!(
                "**{}. {}**\n{}\n\n`{}` | `{}` | ID: `{}`",
                (page - 1).max(0) * 5 + index as i32 + 1,
                req.title,
                truncate(&req.description, 100),
                priority_label(&req.priority),
                category_label(&req.category),
                req.id,
            );
            card = card.add_markdown(content).add_actions(vec![
                button(
                    "确认",
                    "primary",
                    json!({"action": "confirm", "requirement_id": req.id}),
                ),
                button(
                    "拒绝",
                    "danger",
                    json!({"action": "reject", "requirement_id": req.id}),
                ),
            ]);

            if index < requirements.len() - 1 {
                card = card.add_divider();
            }
        }
    }

    if total_pages > 1 {
        let mut buttons = Vec::new();
        if page > 1 {
            buttons.push(button(
                "上一页",
                "default",
                json!({"action": "list_page", "page": page - 1}),
            ));
        }
        if page < total_pages {
            buttons.push(button(
                "下一页",
                "default",
                json!({"action": "list_page", "page": page + 1}),
            ));
        }
        if !buttons.is_empty() {
            card = card.add_divider().add_actions(buttons);
        }
    }

    card.add_note(format!("第 {page}/{total_pages} 页 | 共 {total} 条"))
}

pub fn build_requirements_search_card(
    keyword: &str,
    requirements: &[CardRequirement],
    total: i32,
) -> Card {
    let mut card = Card::new().set_header(
        format!("搜索结果: {} ({total})", truncate(keyword, 30)),
        "blue",
    );

    if requirements.is_empty() {
        card = card.add_markdown("未找到匹配的需求。");
    } else {
        for (index, req) in requirements.iter().enumerate() {
            let content = format!(
                "**{}. {}**\n{}\n\n`{}` | `{}` | `{}` | ID: `{}`",
                index + 1,
                req.title,
                truncate(&req.description, 100),
                status_label(&req.status),
                priority_label(&req.priority),
                category_label(&req.category),
                req.id,
            );
            card = card.add_markdown(content);
            if req.status == "PENDING" {
                card = card.add_actions(vec![
                    button(
                        "确认",
                        "primary",
                        json!({"action": "confirm", "requirement_id": req.id}),
                    ),
                    button(
                        "拒绝",
                        "danger",
                        json!({"action": "reject", "requirement_id": req.id}),
                    ),
                ]);
            }
            if index < requirements.len() - 1 {
                card = card.add_divider();
            }
        }
    }

    card.add_note(format!("显示 {}/{total} 条匹配结果", requirements.len()))
}

pub fn build_operation_result_card(
    operation: &str,
    success: bool,
    requirement: Option<&CardRequirement>,
    error: &str,
) -> Card {
    let title = match (success, operation) {
        (true, "confirm") => "需求已确认",
        (true, "reject") => "需求已拒绝",
        (true, _) => "操作成功",
        (false, _) => "操作失败",
    };
    let template = if success { "green" } else { "red" };
    let mut card = Card::new().set_header(title, template);

    if success {
        if let Some(requirement) = requirement {
            card = card.add_markdown(format!(
                "**{}**\n\nID: `{}`",
                requirement.title, requirement.id
            ));
        }
    } else {
        card = card.add_markdown(format!("错误: {error}"));
    }

    card
}

pub fn build_help_card() -> Card {
    Card::new()
        .set_header("Wisdoverse Cell 帮助", "blue")
        .add_markdown(
            "**命令列表：**\n\n\
| 命令 | 说明 |\n\
|------|------|\n\
| /list | 查看待确认需求 |\n\
| /confirm <ID> | 确认需求 |\n\
| /reject <ID> [原因] | 拒绝需求 |\n\
| /search <关键词> | 搜索需求 |\n\
| /help | 显示帮助 |",
        )
        .add_divider()
        .add_note("Wisdoverse Cell - AI Native OS")
}

pub fn build_decomposition_action_result_card(
    action: &str,
    wp_id: i64,
    subject: &str,
    story_count: i32,
    task_count: i32,
) -> Card {
    let title = if action == "approve" {
        "任务拆解已批准"
    } else {
        "任务拆解已拒绝"
    };
    let template = if action == "approve" { "green" } else { "red" };
    let subject = if subject.is_empty() {
        format!("WP #{wp_id}")
    } else {
        subject.to_string()
    };

    let mut card = Card::new()
        .set_header(title, template)
        .add_markdown(format!("**{}**", subject));

    if action == "approve" {
        card = card.add_markdown("已写入 OpenProject");
        if story_count > 0 || task_count > 0 {
            card = card.add_markdown(format!(
                "**{}** 个 User Story，**{}** 个 Task",
                story_count, task_count
            ));
        }
    } else {
        card = card.add_markdown("此拆解方案已被拒绝，可重新触发拆解");
    }

    card.add_divider().add_note(format!("WP #{wp_id}"))
}

pub fn build_decomposition_error_card(message: &str) -> Card {
    Card::new()
        .set_header("操作失败", "red")
        .add_markdown(message)
}

pub fn build_decomposition_processing_card() -> Card {
    Card::new()
        .set_header("正在处理中", "blue")
        .add_markdown("请求正在后台处理，请稍候刷新查看结果...")
}

pub fn build_bitable_error_card(message: &str) -> Card {
    Card::new()
        .set_header("操作失败", "red")
        .add_markdown(message)
}

pub fn build_bitable_cancel_card() -> Card {
    Card::new()
        .set_header("已取消", "grey")
        .add_markdown("操作已取消")
}

pub fn build_bitable_duplicate_card() -> Card {
    Card::new()
        .set_header("已处理", "green")
        .add_markdown("该操作已执行，请勿重复点击")
}

fn button(text: &str, button_type: &str, value: Value) -> Value {
    json!({
        "tag": "button",
        "text": {
            "tag": "plain_text",
            "content": text,
        },
        "type": button_type,
        "value": value,
    })
}

fn truncate(value: &str, max_chars: usize) -> String {
    let value = value.replace('\n', " ");
    if value.chars().count() <= max_chars {
        return value;
    }
    let mut truncated = value.chars().take(max_chars).collect::<String>();
    truncated.push_str("...");
    truncated
}

fn priority_label(value: &str) -> &str {
    match value {
        "P0" => "P0",
        "P1" => "P1",
        "P2" => "P2",
        "P3" => "P3",
        _ => value,
    }
}

fn category_label(value: &str) -> &str {
    match value {
        "FEATURE" => "功能",
        "BUG" => "Bug",
        "IMPROVEMENT" => "优化",
        "QUESTION" => "问题",
        _ => value,
    }
}

fn status_label(value: &str) -> &str {
    match value {
        "PENDING" => "待确认",
        "CONFIRMED" => "已确认",
        "REJECTED" => "已拒绝",
        _ => value,
    }
}

#[async_trait]
pub trait FeishuMessenger: Send + Sync {
    async fn send_card(
        &self,
        receive_id_type: &str,
        receive_id: &str,
        card: &Card,
    ) -> Result<(), FeishuError>;
    async fn reply_card(&self, message_id: &str, card: &Card) -> Result<(), FeishuError>;
}

#[derive(Clone, Default)]
pub struct NoopFeishuMessenger;

#[async_trait]
impl FeishuMessenger for NoopFeishuMessenger {
    async fn send_card(
        &self,
        _receive_id_type: &str,
        _receive_id: &str,
        _card: &Card,
    ) -> Result<(), FeishuError> {
        Ok(())
    }

    async fn reply_card(&self, _message_id: &str, _card: &Card) -> Result<(), FeishuError> {
        Ok(())
    }
}

#[derive(Clone)]
pub struct FeishuApiClient {
    app_id: String,
    app_secret: String,
    base_url: String,
    http: reqwest::Client,
    token: Arc<RwLock<Option<TokenCache>>>,
}

#[derive(Clone, Debug)]
struct TokenCache {
    token: String,
    expires_at: std::time::Instant,
}

impl FeishuApiClient {
    pub fn new(
        app_id: impl Into<String>,
        app_secret: impl Into<String>,
        base_url: impl Into<String>,
    ) -> Self {
        Self {
            app_id: app_id.into(),
            app_secret: app_secret.into(),
            base_url: base_url.into().trim_end_matches('/').to_string(),
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .expect("build Feishu HTTP client"),
            token: Arc::new(RwLock::new(None)),
        }
    }

    async fn tenant_access_token(&self) -> Result<String, FeishuError> {
        if let Some(cache) = self.token.read().await.as_ref() {
            if std::time::Instant::now() < cache.expires_at {
                return Ok(cache.token.clone());
            }
        }

        let mut write = self.token.write().await;
        if let Some(cache) = write.as_ref() {
            if std::time::Instant::now() < cache.expires_at {
                return Ok(cache.token.clone());
            }
        }

        let response = self
            .http
            .post(format!(
                "{}/auth/v3/tenant_access_token/internal",
                self.base_url
            ))
            .json(&json!({
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            }))
            .send()
            .await?
            .json::<TenantTokenResponse>()
            .await?;

        if response.code != 0 {
            return Err(FeishuError::Api {
                code: response.code,
                message: response.msg,
            });
        }

        let token = response.tenant_access_token;
        let refresh_seconds = response.expire.saturating_sub(300).max(1) as u64;
        *write = Some(TokenCache {
            token: token.clone(),
            expires_at: std::time::Instant::now() + Duration::from_secs(refresh_seconds),
        });
        Ok(token)
    }

    async fn send_message(
        &self,
        receive_id_type: &str,
        receive_id: &str,
        msg_type: &str,
        content: String,
    ) -> Result<(), FeishuError> {
        let token = self.tenant_access_token().await?;
        let response = self
            .http
            .post(format!(
                "{}/im/v1/messages?receive_id_type={receive_id_type}",
                self.base_url
            ))
            .bearer_auth(token)
            .json(&json!({
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": content,
            }))
            .send()
            .await?
            .json::<ApiResponse>()
            .await?;
        response.into_result()
    }

    async fn reply_message(
        &self,
        message_id: &str,
        msg_type: &str,
        content: String,
    ) -> Result<(), FeishuError> {
        let token = self.tenant_access_token().await?;
        let response = self
            .http
            .post(format!(
                "{}/im/v1/messages/{message_id}/reply",
                self.base_url
            ))
            .bearer_auth(token)
            .json(&json!({
                "msg_type": msg_type,
                "content": content,
            }))
            .send()
            .await?
            .json::<ApiResponse>()
            .await?;
        response.into_result()
    }
}

#[async_trait]
impl FeishuMessenger for FeishuApiClient {
    async fn send_card(
        &self,
        receive_id_type: &str,
        receive_id: &str,
        card: &Card,
    ) -> Result<(), FeishuError> {
        self.send_message(
            receive_id_type,
            receive_id,
            "interactive",
            serde_json::to_string(card)?,
        )
        .await
    }

    async fn reply_card(&self, message_id: &str, card: &Card) -> Result<(), FeishuError> {
        self.reply_message(message_id, "interactive", serde_json::to_string(card)?)
            .await
    }
}

#[derive(Debug)]
pub enum FeishuError {
    Http(reqwest::Error),
    Serde(serde_json::Error),
    Api { code: i32, message: String },
}

impl fmt::Display for FeishuError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(err) => write!(f, "Feishu HTTP error: {err}"),
            Self::Serde(err) => write!(f, "Feishu JSON error: {err}"),
            Self::Api { code, message } => write!(f, "Feishu API error {code}: {message}"),
        }
    }
}

impl Error for FeishuError {}

impl From<reqwest::Error> for FeishuError {
    fn from(value: reqwest::Error) -> Self {
        Self::Http(value)
    }
}

impl From<serde_json::Error> for FeishuError {
    fn from(value: serde_json::Error) -> Self {
        Self::Serde(value)
    }
}

#[derive(Debug, Deserialize)]
struct TenantTokenResponse {
    code: i32,
    msg: String,
    tenant_access_token: String,
    expire: i32,
}

#[derive(Debug, Deserialize)]
struct ApiResponse {
    code: i32,
    msg: String,
}

impl ApiResponse {
    fn into_result(self) -> Result<(), FeishuError> {
        if self.code == 0 {
            Ok(())
        } else {
            Err(FeishuError::Api {
                code: self.code,
                message: self.msg,
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{
        build_help_card, build_operation_result_card, build_requirements_list_card,
        build_requirements_search_card, CardRequirement,
    };

    fn requirement(id: &str, status: &str) -> CardRequirement {
        CardRequirement {
            id: id.to_string(),
            title: format!("Requirement {id}"),
            description: "A long enough requirement description".to_string(),
            status: status.to_string(),
            priority: "P1".to_string(),
            category: "FEATURE".to_string(),
        }
    }

    #[test]
    fn builds_requirements_list_card_with_actions_and_pagination() {
        let card = build_requirements_list_card(&[requirement("req_1", "PENDING")], 1, 2, 6);
        let json = serde_json::to_value(card).unwrap();

        assert_eq!(json["header"]["template"], "blue");
        assert!(json["elements"].to_string().contains("req_1"));
        assert!(json["elements"].to_string().contains("list_page"));
    }

    #[test]
    fn builds_search_and_operation_cards() {
        let search =
            build_requirements_search_card("offline", &[requirement("req_2", "PENDING")], 1);
        let search_json = serde_json::to_value(search).unwrap();
        assert!(search_json["header"].to_string().contains("offline"));

        let operation = build_operation_result_card(
            "confirm",
            true,
            Some(&requirement("req_3", "CONFIRMED")),
            "",
        );
        let operation_json = serde_json::to_value(operation).unwrap();
        assert_eq!(operation_json["header"]["template"], "green");
        assert!(operation_json["elements"].to_string().contains("req_3"));
    }

    #[test]
    fn builds_help_card() {
        let card = build_help_card();
        let json = serde_json::to_value(card).unwrap();

        assert!(json["elements"].to_string().contains("/confirm"));
    }
}
