use async_trait::async_trait;
use std::{error::Error, fmt, time::Duration};

#[async_trait]
pub trait FeishuEventForwarder: Send + Sync {
    async fn forward(&self, body: &[u8]) -> Result<(), FeishuForwardError>;
}

#[derive(Clone, Default)]
pub struct NoopFeishuEventForwarder;

#[async_trait]
impl FeishuEventForwarder for NoopFeishuEventForwarder {
    async fn forward(&self, _body: &[u8]) -> Result<(), FeishuForwardError> {
        Ok(())
    }
}

#[derive(Clone)]
pub struct HttpFeishuEventForwarder {
    url: String,
    internal_key: String,
    http: reqwest::Client,
}

impl HttpFeishuEventForwarder {
    pub fn new(chat_agent_addr: impl Into<String>, internal_key: impl Into<String>) -> Self {
        let chat_agent_addr = chat_agent_addr.into();
        let base_url =
            if chat_agent_addr.starts_with("http://") || chat_agent_addr.starts_with("https://") {
                chat_agent_addr.trim_end_matches('/').to_string()
            } else {
                format!("http://{}", chat_agent_addr.trim_end_matches('/'))
            };

        Self {
            url: format!("{base_url}/webhook/feishu"),
            internal_key: internal_key.into(),
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("build Feishu forward HTTP client"),
        }
    }
}

#[async_trait]
impl FeishuEventForwarder for HttpFeishuEventForwarder {
    async fn forward(&self, body: &[u8]) -> Result<(), FeishuForwardError> {
        let mut request = self
            .http
            .post(&self.url)
            .header("content-type", "application/json")
            .body(body.to_vec());

        if !self.internal_key.is_empty() {
            request = request.header("x-internal-key", self.internal_key.as_str());
        }

        let response = request.send().await?;
        let status = response.status();
        if !status.is_success() {
            return Err(FeishuForwardError::Status(status.as_u16()));
        }
        Ok(())
    }
}

#[derive(Debug)]
pub enum FeishuForwardError {
    Http(reqwest::Error),
    Status(u16),
}

impl fmt::Display for FeishuForwardError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(err) => write!(f, "feishu forward http error: {err}"),
            Self::Status(status) => write!(f, "feishu forward returned HTTP {status}"),
        }
    }
}

impl Error for FeishuForwardError {}

impl From<reqwest::Error> for FeishuForwardError {
    fn from(value: reqwest::Error) -> Self {
        Self::Http(value)
    }
}

#[cfg(test)]
mod tests {
    use super::{FeishuEventForwarder, HttpFeishuEventForwarder};
    use axum::{
        body::Bytes,
        extract::State,
        http::{HeaderMap, StatusCode},
        routing::post,
        Router,
    };
    use std::{
        net::SocketAddr,
        sync::{Arc, Mutex},
    };
    use tokio::net::TcpListener;

    #[tokio::test]
    async fn forwards_raw_body_with_internal_key_header() {
        let recorder = Arc::new(Mutex::new(RecordedForward::default()));
        let addr = spawn_forward_recorder(recorder.clone()).await;
        let forwarder = HttpFeishuEventForwarder::new(addr.to_string(), "secret-key");

        forwarder
            .forward(br#"{"type":"event_callback"}"#)
            .await
            .expect("forward event");

        let recorded = recorder.lock().unwrap();
        assert_eq!(recorded.internal_key, "secret-key");
        assert_eq!(recorded.content_type, "application/json");
        assert_eq!(recorded.body, br#"{"type":"event_callback"}"#);
    }

    #[tokio::test]
    async fn returns_error_for_failed_downstream_status() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let app = Router::new().route(
            "/webhook/feishu",
            post(|| async { StatusCode::INTERNAL_SERVER_ERROR }),
        );

        tokio::spawn(async move {
            axum::serve(listener, app)
                .await
                .expect("recording forward server");
        });

        let forwarder = HttpFeishuEventForwarder::new(addr.to_string(), "");
        let err = forwarder
            .forward(br#"{"type":"event_callback"}"#)
            .await
            .expect_err("downstream HTTP 500 should fail");

        assert_eq!(err.to_string(), "feishu forward returned HTTP 500");
    }

    #[derive(Default)]
    struct RecordedForward {
        internal_key: String,
        content_type: String,
        body: Vec<u8>,
    }

    async fn spawn_forward_recorder(recorder: Arc<Mutex<RecordedForward>>) -> SocketAddr {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let app = Router::new()
            .route("/webhook/feishu", post(record_forward))
            .with_state(recorder);

        tokio::spawn(async move {
            axum::serve(listener, app)
                .await
                .expect("recording forward server");
        });
        addr
    }

    async fn record_forward(
        State(recorder): State<Arc<Mutex<RecordedForward>>>,
        headers: HeaderMap,
        body: Bytes,
    ) -> &'static str {
        let mut recorded = recorder.lock().unwrap();
        recorded.internal_key = headers
            .get("x-internal-key")
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default()
            .to_string();
        recorded.content_type = headers
            .get("content-type")
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default()
            .to_string();
        recorded.body = body.to_vec();
        "ok"
    }
}
