use async_trait::async_trait;
use serde_json::{json, Map, Value};
use std::{error::Error, fmt, time::Duration};

use crate::feishu_outbound::Card;

#[async_trait]
pub trait BitableActionForwarder: Send + Sync {
    async fn confirm_update(&self, value: &Value, operator: &str) -> Result<Card, BitableError>;
    async fn create_record(&self, value: &Value, operator: &str) -> Result<Card, BitableError>;
    async fn reject_operation(
        &self,
        value: &Value,
        operator: &str,
        action_type: &str,
    ) -> Result<Card, BitableError>;
}

#[derive(Clone, Default)]
pub struct NoopBitableActionForwarder;

#[async_trait]
impl BitableActionForwarder for NoopBitableActionForwarder {
    async fn confirm_update(&self, _value: &Value, _operator: &str) -> Result<Card, BitableError> {
        Err(BitableError::NotConfigured)
    }

    async fn create_record(&self, _value: &Value, _operator: &str) -> Result<Card, BitableError> {
        Err(BitableError::NotConfigured)
    }

    async fn reject_operation(
        &self,
        _value: &Value,
        _operator: &str,
        _action_type: &str,
    ) -> Result<Card, BitableError> {
        Err(BitableError::NotConfigured)
    }
}

#[derive(Clone)]
pub struct HttpBitableActionForwarder {
    base_url: String,
    internal_key: String,
    http: reqwest::Client,
}

impl HttpBitableActionForwarder {
    pub fn new(chat_agent_addr: impl Into<String>, internal_key: impl Into<String>) -> Self {
        let chat_agent_addr = chat_agent_addr.into();
        let base_url =
            if chat_agent_addr.starts_with("http://") || chat_agent_addr.starts_with("https://") {
                chat_agent_addr.trim_end_matches('/').to_string()
            } else {
                format!("http://{}", chat_agent_addr.trim_end_matches('/'))
            };

        Self {
            base_url,
            internal_key: internal_key.into(),
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(12))
                .build()
                .expect("build Bitable forward HTTP client"),
        }
    }

    async fn post_card(&self, path: &str, payload: Value) -> Result<Card, BitableError> {
        let mut request = self
            .http
            .post(format!("{}{}", self.base_url, path))
            .header("content-type", "application/json")
            .json(&payload);

        if !self.internal_key.is_empty() {
            request = request.header("x-internal-key", self.internal_key.as_str());
        }

        let response = request.send().await?;
        let status = response.status();
        if !status.is_success() {
            return Err(BitableError::Status(status.as_u16()));
        }

        let card = response.json::<Card>().await?;
        if card.header.is_none() && card.elements.is_empty() {
            return Err(BitableError::EmptyCard);
        }
        Ok(card)
    }
}

#[async_trait]
impl BitableActionForwarder for HttpBitableActionForwarder {
    async fn confirm_update(&self, value: &Value, operator: &str) -> Result<Card, BitableError> {
        self.post_card(
            "/api/bitable/confirm",
            json!({
                "record_id": string_field(value, "record_id"),
                "fields": object_field(value, "fields"),
                "table_id": string_field(value, "table_id"),
                "user_id": operator,
                "action_id": string_field(value, "action_id"),
            }),
        )
        .await
    }

    async fn create_record(&self, value: &Value, operator: &str) -> Result<Card, BitableError> {
        self.post_card(
            "/api/bitable/create",
            json!({
                "fields": object_field(value, "fields"),
                "table_id": string_field(value, "table_id"),
                "user_id": operator,
                "action_id": string_field(value, "action_id"),
            }),
        )
        .await
    }

    async fn reject_operation(
        &self,
        value: &Value,
        operator: &str,
        action_type: &str,
    ) -> Result<Card, BitableError> {
        self.post_card(
            "/api/bitable/reject",
            json!({
                "action_type": action_type,
                "user_id": operator,
                "fields": object_field(value, "fields"),
                "table_id": string_field(value, "table_id"),
                "record_id": string_field(value, "record_id"),
            }),
        )
        .await
    }
}

#[derive(Debug)]
pub enum BitableError {
    NotConfigured,
    Http(reqwest::Error),
    Status(u16),
    EmptyCard,
}

impl BitableError {
    pub fn is_timeout(&self) -> bool {
        matches!(self, Self::Http(err) if err.is_timeout())
    }
}

impl fmt::Display for BitableError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NotConfigured => write!(f, "chat service is not configured"),
            Self::Http(err) => write!(f, "bitable forward http error: {err}"),
            Self::Status(status) => write!(f, "bitable service returned HTTP {status}"),
            Self::EmptyCard => write!(f, "bitable service returned an empty card"),
        }
    }
}

impl Error for BitableError {}

impl From<reqwest::Error> for BitableError {
    fn from(value: reqwest::Error) -> Self {
        Self::Http(value)
    }
}

fn string_field(value: &Value, field: &str) -> String {
    value
        .get(field)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

fn object_field(value: &Value, field: &str) -> Value {
    value
        .get(field)
        .and_then(Value::as_object)
        .cloned()
        .map(Value::Object)
        .unwrap_or_else(|| Value::Object(Map::new()))
}

#[cfg(test)]
mod tests {
    use super::{BitableActionForwarder, HttpBitableActionForwarder};
    use axum::{extract::State, http::HeaderMap, routing::post, Json, Router};
    use serde_json::{json, Value};
    use std::{
        net::SocketAddr,
        sync::{Arc, Mutex},
    };
    use tokio::net::TcpListener;

    #[tokio::test]
    async fn forwards_confirm_update_payload_and_parses_card() {
        let recorder = Arc::new(Mutex::new(RecordedBitableForward::default()));
        let addr = spawn_bitable_recorder(recorder.clone()).await;
        let forwarder = HttpBitableActionForwarder::new(addr.to_string(), "secret-key");

        let card = forwarder
            .confirm_update(
                &json!({
                    "record_id": "rec_1",
                    "table_id": "tbl_1",
                    "fields": {"状态": "已完成"},
                }),
                "ou_user",
            )
            .await
            .expect("forward confirm update");

        assert_eq!(card.header.unwrap()["template"], "green");
        let recorded = recorder.lock().unwrap();
        assert_eq!(recorded.path, "/api/bitable/confirm");
        assert_eq!(recorded.internal_key, "secret-key");
        assert_eq!(recorded.body["record_id"], "rec_1");
        assert_eq!(recorded.body["table_id"], "tbl_1");
        assert_eq!(recorded.body["user_id"], "ou_user");
        assert_eq!(recorded.body["fields"]["状态"], "已完成");
    }

    #[tokio::test]
    async fn forwards_reject_operation_payload() {
        let recorder = Arc::new(Mutex::new(RecordedBitableForward::default()));
        let addr = spawn_bitable_recorder(recorder.clone()).await;
        let forwarder = HttpBitableActionForwarder::new(addr.to_string(), "secret-key");

        forwarder
            .reject_operation(
                &json!({
                    "record_id": "rec_2",
                    "table_id": "tbl_2",
                    "fields": {"标题": "Task"},
                }),
                "ou_user",
                "update",
            )
            .await
            .expect("forward reject update");

        let recorded = recorder.lock().unwrap();
        assert_eq!(recorded.path, "/api/bitable/reject");
        assert_eq!(recorded.body["action_type"], "update");
        assert_eq!(recorded.body["record_id"], "rec_2");
    }

    #[derive(Default)]
    struct RecordedBitableForward {
        path: String,
        internal_key: String,
        body: Value,
    }

    async fn spawn_bitable_recorder(recorder: Arc<Mutex<RecordedBitableForward>>) -> SocketAddr {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let app = Router::new()
            .route("/api/bitable/confirm", post(record_bitable_forward))
            .route("/api/bitable/create", post(record_bitable_forward))
            .route("/api/bitable/reject", post(record_bitable_forward))
            .with_state(recorder);

        tokio::spawn(async move {
            axum::serve(listener, app)
                .await
                .expect("recording bitable forward server");
        });
        addr
    }

    async fn record_bitable_forward(
        State(recorder): State<Arc<Mutex<RecordedBitableForward>>>,
        headers: HeaderMap,
        uri: axum::http::Uri,
        Json(body): Json<Value>,
    ) -> Json<Value> {
        let mut recorded = recorder.lock().unwrap();
        recorded.path = uri.path().to_string();
        recorded.internal_key = headers
            .get("x-internal-key")
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default()
            .to_string();
        recorded.body = body;
        Json(json!({
            "header": {
                "title": {"tag": "plain_text", "content": "表格操作完成"},
                "template": "green"
            },
            "elements": [{"tag": "markdown", "content": "ok"}]
        }))
    }
}
