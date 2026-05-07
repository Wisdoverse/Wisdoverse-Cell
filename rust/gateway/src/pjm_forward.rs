use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::{error::Error, fmt, time::Duration};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct PjmDecompositionResult {
    #[serde(default)]
    pub success: bool,
    #[serde(default)]
    pub wp_id: i64,
    #[serde(default)]
    pub action: String,
    #[serde(default)]
    pub message: String,
    #[serde(default)]
    pub subject: String,
    #[serde(default)]
    pub story_count: i32,
    #[serde(default)]
    pub task_count: i32,
}

#[async_trait]
pub trait PjmActionForwarder: Send + Sync {
    async fn forward_decomposition_action(
        &self,
        wp_id: i64,
        action: &str,
        operator: &str,
    ) -> Result<PjmDecompositionResult, PjmForwardError>;
}

#[derive(Clone, Default)]
pub struct NoopPjmActionForwarder;

#[async_trait]
impl PjmActionForwarder for NoopPjmActionForwarder {
    async fn forward_decomposition_action(
        &self,
        _wp_id: i64,
        _action: &str,
        _operator: &str,
    ) -> Result<PjmDecompositionResult, PjmForwardError> {
        Err(PjmForwardError::NotConfigured)
    }
}

#[derive(Clone)]
pub struct HttpPjmActionForwarder {
    base_url: String,
    internal_key: String,
    http: reqwest::Client,
}

impl HttpPjmActionForwarder {
    pub fn new(pjm_agent_addr: impl Into<String>, internal_key: impl Into<String>) -> Self {
        let pjm_agent_addr = pjm_agent_addr.into();
        let base_url =
            if pjm_agent_addr.starts_with("http://") || pjm_agent_addr.starts_with("https://") {
                pjm_agent_addr.trim_end_matches('/').to_string()
            } else {
                format!("http://{}", pjm_agent_addr.trim_end_matches('/'))
            };

        Self {
            base_url,
            internal_key: internal_key.into(),
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(12))
                .build()
                .expect("build PJM forward HTTP client"),
        }
    }
}

#[async_trait]
impl PjmActionForwarder for HttpPjmActionForwarder {
    async fn forward_decomposition_action(
        &self,
        wp_id: i64,
        action: &str,
        operator: &str,
    ) -> Result<PjmDecompositionResult, PjmForwardError> {
        let mut request = self
            .http
            .post(format!(
                "{}/api/v1/pm/decompose/{}/{}",
                self.base_url, wp_id, action
            ))
            .header("content-type", "application/json")
            .json(&DecompositionActionRequest { operator });

        if !self.internal_key.is_empty() {
            request = request.header("x-internal-key", self.internal_key.as_str());
        }

        let response = request.send().await?;
        let status = response.status();
        if !status.is_success() {
            return Err(PjmForwardError::Status(status.as_u16()));
        }

        Ok(response.json::<PjmDecompositionResult>().await?)
    }
}

#[derive(Debug)]
pub enum PjmForwardError {
    NotConfigured,
    Http(reqwest::Error),
    Status(u16),
}

impl PjmForwardError {
    pub fn is_timeout(&self) -> bool {
        matches!(self, Self::Http(err) if err.is_timeout())
    }
}

impl fmt::Display for PjmForwardError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NotConfigured => write!(f, "pjm-agent forwarding is not configured"),
            Self::Http(err) => write!(f, "pjm forward http error: {err}"),
            Self::Status(status) => write!(f, "pjm-agent returned HTTP {status}"),
        }
    }
}

impl Error for PjmForwardError {}

impl From<reqwest::Error> for PjmForwardError {
    fn from(value: reqwest::Error) -> Self {
        Self::Http(value)
    }
}

#[derive(Debug, Serialize)]
struct DecompositionActionRequest<'a> {
    operator: &'a str,
}

#[cfg(test)]
mod tests {
    use super::{HttpPjmActionForwarder, PjmActionForwarder};
    use axum::{extract::State, http::HeaderMap, routing::post, Json, Router};
    use serde_json::{json, Value};
    use std::{
        net::SocketAddr,
        sync::{Arc, Mutex},
    };
    use tokio::net::TcpListener;

    #[tokio::test]
    async fn forwards_decomposition_action_to_pjm_api_with_internal_key() {
        let recorder = Arc::new(Mutex::new(RecordedPjmForward::default()));
        let addr = spawn_pjm_recorder(recorder.clone()).await;
        let forwarder = HttpPjmActionForwarder::new(addr.to_string(), "secret-key");

        let result = forwarder
            .forward_decomposition_action(42, "approve", "ou_operator")
            .await
            .expect("forward decomposition action");

        assert_eq!(result.action, "approve");
        assert_eq!(result.wp_id, 42);
        let recorded = recorder.lock().unwrap();
        assert_eq!(recorded.path, "/api/v1/pm/decompose/42/approve");
        assert_eq!(recorded.internal_key, "secret-key");
        assert_eq!(recorded.body["operator"], "ou_operator");
    }

    #[derive(Default)]
    struct RecordedPjmForward {
        path: String,
        internal_key: String,
        body: Value,
    }

    async fn spawn_pjm_recorder(recorder: Arc<Mutex<RecordedPjmForward>>) -> SocketAddr {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let app = Router::new()
            .route("/api/v1/pm/decompose/42/approve", post(record_pjm_forward))
            .with_state(recorder);

        tokio::spawn(async move {
            axum::serve(listener, app)
                .await
                .expect("recording pjm forward server");
        });
        addr
    }

    async fn record_pjm_forward(
        State(recorder): State<Arc<Mutex<RecordedPjmForward>>>,
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
            "success": true,
            "wp_id": 42,
            "action": "approve",
            "message": "Written to OP",
            "subject": "Split feature",
            "story_count": 1,
            "task_count": 3
        }))
    }
}
