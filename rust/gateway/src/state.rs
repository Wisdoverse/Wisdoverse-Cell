use async_trait::async_trait;
use redis::AsyncCommands;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::HashMap,
    error::Error,
    fmt,
    sync::{Arc, Mutex},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const DEDUP_KEY_PREFIX: &str = "dedup:";
const EVENT_KEY_PREFIX: &str = "event:";
const SESSION_KEY_PREFIX: &str = "session:";
const DEFAULT_DEDUP_TTL: Duration = Duration::from_secs(10);
const DEFAULT_EVENT_TTL: Duration = Duration::from_secs(5 * 60);
const DEFAULT_SESSION_TTL: Duration = Duration::from_secs(5 * 60);
const MAX_MESSAGE_HISTORY: usize = 10;

#[derive(Debug)]
pub enum StateError {
    Redis(redis::RedisError),
    Serde(serde_json::Error),
    Poisoned,
}

impl fmt::Display for StateError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Redis(err) => write!(f, "redis state error: {err}"),
            Self::Serde(err) => write!(f, "state serialization error: {err}"),
            Self::Poisoned => write!(f, "state store lock poisoned"),
        }
    }
}

impl Error for StateError {}

impl From<redis::RedisError> for StateError {
    fn from(value: redis::RedisError) -> Self {
        Self::Redis(value)
    }
}

impl From<serde_json::Error> for StateError {
    fn from(value: serde_json::Error) -> Self {
        Self::Serde(value)
    }
}

#[async_trait]
pub trait GatewayStateStore: Send + Sync {
    async fn set_nx_with_ttl(
        &self,
        key: &str,
        value: &[u8],
        ttl: Duration,
    ) -> Result<bool, StateError>;
    async fn set_with_ttl(&self, key: &str, value: &[u8], ttl: Duration) -> Result<(), StateError>;
    async fn get(&self, key: &str) -> Result<Option<Vec<u8>>, StateError>;
    async fn exists(&self, key: &str) -> Result<bool, StateError>;
    async fn delete(&self, key: &str) -> Result<(), StateError>;
    async fn expire(&self, key: &str, ttl: Duration) -> Result<bool, StateError>;
}

#[derive(Clone)]
pub struct RedisStateStore {
    client: redis::Client,
}

impl RedisStateStore {
    pub fn from_addr(addr: &str) -> Result<Self, StateError> {
        let url = if addr.starts_with("redis://") || addr.starts_with("rediss://") {
            addr.to_string()
        } else {
            format!("redis://{addr}")
        };
        let client = redis::Client::open(url)?;
        Ok(Self { client })
    }

    pub async fn ping(&self) -> Result<(), StateError> {
        let mut connection = self.client.get_multiplexed_async_connection().await?;
        let _: String = redis::cmd("PING").query_async(&mut connection).await?;
        Ok(())
    }
}

#[async_trait]
impl GatewayStateStore for RedisStateStore {
    async fn set_nx_with_ttl(
        &self,
        key: &str,
        value: &[u8],
        ttl: Duration,
    ) -> Result<bool, StateError> {
        let mut connection = self.client.get_multiplexed_async_connection().await?;
        let result: Option<String> = redis::cmd("SET")
            .arg(key)
            .arg(value)
            .arg("NX")
            .arg("PX")
            .arg(ttl.as_millis().max(1))
            .query_async(&mut connection)
            .await?;
        Ok(result.is_some())
    }

    async fn set_with_ttl(&self, key: &str, value: &[u8], ttl: Duration) -> Result<(), StateError> {
        let mut connection = self.client.get_multiplexed_async_connection().await?;
        let _: () = connection.set_ex(key, value, ttl.as_secs().max(1)).await?;
        Ok(())
    }

    async fn get(&self, key: &str) -> Result<Option<Vec<u8>>, StateError> {
        let mut connection = self.client.get_multiplexed_async_connection().await?;
        let value: Option<Vec<u8>> = connection.get(key).await?;
        Ok(value)
    }

    async fn exists(&self, key: &str) -> Result<bool, StateError> {
        let mut connection = self.client.get_multiplexed_async_connection().await?;
        let exists: bool = connection.exists(key).await?;
        Ok(exists)
    }

    async fn delete(&self, key: &str) -> Result<(), StateError> {
        let mut connection = self.client.get_multiplexed_async_connection().await?;
        let _: () = connection.del(key).await?;
        Ok(())
    }

    async fn expire(&self, key: &str, ttl: Duration) -> Result<bool, StateError> {
        let mut connection = self.client.get_multiplexed_async_connection().await?;
        let changed: bool = connection.expire(key, ttl.as_secs().max(1) as i64).await?;
        Ok(changed)
    }
}

#[derive(Default)]
pub struct InMemoryStateStore {
    entries: Mutex<HashMap<String, MemoryEntry>>,
}

struct MemoryEntry {
    value: Vec<u8>,
    expires_at: Instant,
}

impl InMemoryStateStore {
    pub fn new() -> Self {
        Self::default()
    }

    fn remove_if_expired(entries: &mut HashMap<String, MemoryEntry>, key: &str) {
        let expired = entries
            .get(key)
            .map(|entry| Instant::now() >= entry.expires_at)
            .unwrap_or(false);
        if expired {
            entries.remove(key);
        }
    }
}

#[async_trait]
impl GatewayStateStore for InMemoryStateStore {
    async fn set_nx_with_ttl(
        &self,
        key: &str,
        value: &[u8],
        ttl: Duration,
    ) -> Result<bool, StateError> {
        let mut entries = self.entries.lock().map_err(|_| StateError::Poisoned)?;
        Self::remove_if_expired(&mut entries, key);
        if entries.contains_key(key) {
            return Ok(false);
        }
        entries.insert(
            key.to_string(),
            MemoryEntry {
                value: value.to_vec(),
                expires_at: Instant::now() + ttl,
            },
        );
        Ok(true)
    }

    async fn set_with_ttl(&self, key: &str, value: &[u8], ttl: Duration) -> Result<(), StateError> {
        let mut entries = self.entries.lock().map_err(|_| StateError::Poisoned)?;
        entries.insert(
            key.to_string(),
            MemoryEntry {
                value: value.to_vec(),
                expires_at: Instant::now() + ttl,
            },
        );
        Ok(())
    }

    async fn get(&self, key: &str) -> Result<Option<Vec<u8>>, StateError> {
        let mut entries = self.entries.lock().map_err(|_| StateError::Poisoned)?;
        Self::remove_if_expired(&mut entries, key);
        Ok(entries.get(key).map(|entry| entry.value.clone()))
    }

    async fn exists(&self, key: &str) -> Result<bool, StateError> {
        let mut entries = self.entries.lock().map_err(|_| StateError::Poisoned)?;
        Self::remove_if_expired(&mut entries, key);
        Ok(entries.contains_key(key))
    }

    async fn delete(&self, key: &str) -> Result<(), StateError> {
        let mut entries = self.entries.lock().map_err(|_| StateError::Poisoned)?;
        entries.remove(key);
        Ok(())
    }

    async fn expire(&self, key: &str, ttl: Duration) -> Result<bool, StateError> {
        let mut entries = self.entries.lock().map_err(|_| StateError::Poisoned)?;
        Self::remove_if_expired(&mut entries, key);
        if let Some(entry) = entries.get_mut(key) {
            entry.expires_at = Instant::now() + ttl;
            Ok(true)
        } else {
            Ok(false)
        }
    }
}

#[derive(Clone)]
pub struct Deduplicator {
    store: Arc<dyn GatewayStateStore>,
    ttl: Duration,
}

impl Deduplicator {
    pub fn new(store: Arc<dyn GatewayStateStore>, ttl: Duration) -> Self {
        Self {
            store,
            ttl: ttl_or_default(ttl, DEFAULT_DEDUP_TTL),
        }
    }

    pub async fn is_duplicate(&self, message_id: &str) -> Result<bool, StateError> {
        let inserted = self
            .store
            .set_nx_with_ttl(&dedup_key(message_id), b"1", self.ttl)
            .await?;
        Ok(!inserted)
    }

    pub async fn mark_processed(&self, message_id: &str) -> Result<(), StateError> {
        self.store
            .set_with_ttl(&dedup_key(message_id), b"1", self.ttl)
            .await
    }

    pub async fn is_processed(&self, message_id: &str) -> Result<bool, StateError> {
        self.store.exists(&dedup_key(message_id)).await
    }
}

#[derive(Clone)]
pub struct EventDeduplicator {
    store: Arc<dyn GatewayStateStore>,
    ttl: Duration,
}

impl EventDeduplicator {
    pub fn new(store: Arc<dyn GatewayStateStore>, ttl: Duration) -> Self {
        Self {
            store,
            ttl: ttl_or_default(ttl, DEFAULT_EVENT_TTL),
        }
    }

    pub async fn is_duplicate_event(&self, event_id: &str) -> Result<bool, StateError> {
        if event_id.is_empty() {
            return Ok(false);
        }
        let inserted = self
            .store
            .set_nx_with_ttl(&event_key(event_id), b"1", self.ttl)
            .await?;
        Ok(!inserted)
    }
}

#[derive(Clone)]
pub struct SessionManager {
    store: Arc<dyn GatewayStateStore>,
    ttl: Duration,
}

impl SessionManager {
    pub fn new(store: Arc<dyn GatewayStateStore>, ttl: Duration) -> Self {
        Self {
            store,
            ttl: ttl_or_default(ttl, DEFAULT_SESSION_TTL),
        }
    }

    pub async fn get_session(
        &self,
        chat_id: &str,
        user_id: &str,
    ) -> Result<Option<Session>, StateError> {
        let Some(data) = self.store.get(&session_key(chat_id, user_id)).await? else {
            return Ok(None);
        };
        Ok(Some(serde_json::from_slice(&data)?))
    }

    pub async fn get_or_create_session(
        &self,
        chat_id: &str,
        user_id: &str,
    ) -> Result<Session, StateError> {
        if let Some(session) = self.get_session(chat_id, user_id).await? {
            return Ok(session);
        }

        let now = now_millis();
        let session = Session {
            id: format!("{chat_id}:{user_id}"),
            state: SessionState::Idle,
            context: HashMap::new(),
            last_active: now,
            created_at: now,
            pending_requirement_id: String::new(),
            message_history: Vec::new(),
        };
        self.save_session(chat_id, user_id, &session).await?;
        Ok(session)
    }

    pub async fn save_session(
        &self,
        chat_id: &str,
        user_id: &str,
        session: &Session,
    ) -> Result<(), StateError> {
        let mut session = session.clone();
        session.last_active = now_millis();
        let data = serde_json::to_vec(&session)?;
        self.store
            .set_with_ttl(&session_key(chat_id, user_id), &data, self.ttl)
            .await
    }

    pub async fn update_state(
        &self,
        chat_id: &str,
        user_id: &str,
        state: SessionState,
    ) -> Result<(), StateError> {
        let mut session = self.get_or_create_session(chat_id, user_id).await?;
        session.state = state;
        self.save_session(chat_id, user_id, &session).await
    }

    pub async fn set_pending_requirement(
        &self,
        chat_id: &str,
        user_id: &str,
        requirement_id: &str,
    ) -> Result<(), StateError> {
        let mut session = self.get_or_create_session(chat_id, user_id).await?;
        session.pending_requirement_id = requirement_id.to_string();
        session.state = SessionState::AwaitingConfirm;
        self.save_session(chat_id, user_id, &session).await
    }

    pub async fn clear_pending_requirement(
        &self,
        chat_id: &str,
        user_id: &str,
    ) -> Result<(), StateError> {
        let Some(mut session) = self.get_session(chat_id, user_id).await? else {
            return Ok(());
        };
        session.pending_requirement_id.clear();
        session.state = SessionState::Idle;
        self.save_session(chat_id, user_id, &session).await
    }

    pub async fn add_message(
        &self,
        chat_id: &str,
        user_id: &str,
        role: &str,
        content: &str,
    ) -> Result<(), StateError> {
        let mut session = self.get_or_create_session(chat_id, user_id).await?;
        session.message_history.push(SessionMessage {
            role: role.to_string(),
            content: content.to_string(),
            timestamp: now_millis(),
        });
        if session.message_history.len() > MAX_MESSAGE_HISTORY {
            let start = session.message_history.len() - MAX_MESSAGE_HISTORY;
            session.message_history = session.message_history[start..].to_vec();
        }
        self.save_session(chat_id, user_id, &session).await
    }

    pub async fn set_context(
        &self,
        chat_id: &str,
        user_id: &str,
        key: &str,
        value: Value,
    ) -> Result<(), StateError> {
        let mut session = self.get_or_create_session(chat_id, user_id).await?;
        session.context.insert(key.to_string(), value);
        self.save_session(chat_id, user_id, &session).await
    }

    pub async fn get_context(
        &self,
        chat_id: &str,
        user_id: &str,
        key: &str,
    ) -> Result<Option<Value>, StateError> {
        let Some(session) = self.get_session(chat_id, user_id).await? else {
            return Ok(None);
        };
        Ok(session.context.get(key).cloned())
    }

    pub async fn delete_session(&self, chat_id: &str, user_id: &str) -> Result<(), StateError> {
        self.store.delete(&session_key(chat_id, user_id)).await
    }

    pub async fn refresh_ttl(&self, chat_id: &str, user_id: &str) -> Result<bool, StateError> {
        self.store
            .expire(&session_key(chat_id, user_id), self.ttl)
            .await
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SessionState {
    Idle,
    AwaitingConfirm,
    AwaitingReject,
    AwaitingInput,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Session {
    pub id: String,
    pub state: SessionState,
    #[serde(default)]
    pub context: HashMap<String, Value>,
    pub last_active: u128,
    pub created_at: u128,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub pending_requirement_id: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub message_history: Vec<SessionMessage>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct SessionMessage {
    pub role: String,
    pub content: String,
    pub timestamp: u128,
}

pub fn dedup_key(message_id: &str) -> String {
    format!("{DEDUP_KEY_PREFIX}{message_id}")
}

pub fn event_key(event_id: &str) -> String {
    format!("{EVENT_KEY_PREFIX}{event_id}")
}

pub fn session_key(chat_id: &str, user_id: &str) -> String {
    format!("{SESSION_KEY_PREFIX}{chat_id}:{user_id}")
}

fn ttl_or_default(ttl: Duration, default_ttl: Duration) -> Duration {
    if ttl.is_zero() {
        default_ttl
    } else {
        ttl
    }
}

fn now_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

#[cfg(test)]
mod tests {
    use super::{
        dedup_key, event_key, session_key, Deduplicator, EventDeduplicator, InMemoryStateStore,
        SessionManager, SessionState,
    };
    use serde_json::json;
    use std::{sync::Arc, time::Duration};

    #[test]
    fn state_keys_match_go_gateway_contract() {
        assert_eq!(dedup_key("msg_123"), "dedup:msg_123");
        assert_eq!(event_key("evt_abc"), "event:evt_abc");
        assert_eq!(session_key("chat1", "user1"), "session:chat1:user1");
    }

    #[tokio::test]
    async fn deduplicator_detects_recent_duplicates() {
        let store = Arc::new(InMemoryStateStore::new());
        let dedup = Deduplicator::new(store, Duration::from_secs(60));

        assert!(!dedup.is_duplicate("msg_123").await.unwrap());
        assert!(dedup.is_duplicate("msg_123").await.unwrap());
        assert!(!dedup.is_duplicate("msg_456").await.unwrap());
    }

    #[tokio::test]
    async fn deduplicator_marks_processed_messages() {
        let store = Arc::new(InMemoryStateStore::new());
        let dedup = Deduplicator::new(store, Duration::from_secs(60));

        dedup.mark_processed("msg_789").await.unwrap();

        assert!(dedup.is_processed("msg_789").await.unwrap());
        assert!(!dedup.is_processed("msg_999").await.unwrap());
    }

    #[tokio::test]
    async fn event_deduplicator_ignores_empty_id_and_detects_duplicates() {
        let store = Arc::new(InMemoryStateStore::new());
        let dedup = EventDeduplicator::new(store, Duration::from_secs(60));

        assert!(!dedup.is_duplicate_event("").await.unwrap());
        assert!(!dedup.is_duplicate_event("evt_abc").await.unwrap());
        assert!(dedup.is_duplicate_event("evt_abc").await.unwrap());
    }

    #[tokio::test]
    async fn state_store_expires_entries() {
        let store = Arc::new(InMemoryStateStore::new());
        let dedup = Deduplicator::new(store, Duration::from_millis(5));

        assert!(!dedup.is_duplicate("msg_123").await.unwrap());
        tokio::time::sleep(Duration::from_millis(10)).await;
        assert!(!dedup.is_duplicate("msg_123").await.unwrap());
    }

    #[tokio::test]
    async fn session_manager_gets_or_creates_session() {
        let manager = test_session_manager();

        let session = manager
            .get_or_create_session("chat1", "user1")
            .await
            .unwrap();
        assert_eq!(session.id, "chat1:user1");
        assert_eq!(session.state, SessionState::Idle);

        let loaded = manager
            .get_or_create_session("chat1", "user1")
            .await
            .unwrap();
        assert_eq!(loaded.id, session.id);
    }

    #[tokio::test]
    async fn session_manager_updates_state_and_pending_requirement() {
        let manager = test_session_manager();

        manager
            .update_state("chat1", "user1", SessionState::AwaitingReject)
            .await
            .unwrap();
        let session = manager
            .get_session("chat1", "user1")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(session.state, SessionState::AwaitingReject);

        manager
            .set_pending_requirement("chat1", "user1", "req_123")
            .await
            .unwrap();
        let session = manager
            .get_session("chat1", "user1")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(session.pending_requirement_id, "req_123");
        assert_eq!(session.state, SessionState::AwaitingConfirm);

        manager
            .clear_pending_requirement("chat1", "user1")
            .await
            .unwrap();
        let session = manager
            .get_session("chat1", "user1")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(session.pending_requirement_id, "");
        assert_eq!(session.state, SessionState::Idle);
    }

    #[tokio::test]
    async fn session_manager_keeps_last_ten_messages() {
        let manager = test_session_manager();

        for index in 0..15 {
            manager
                .add_message("chat1", "user1", "user", &format!("message-{index}"))
                .await
                .unwrap();
        }

        let session = manager
            .get_session("chat1", "user1")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(session.message_history.len(), 10);
        assert_eq!(session.message_history[0].content, "message-5");
    }

    #[tokio::test]
    async fn session_manager_stores_context_values() {
        let manager = test_session_manager();

        manager
            .set_context("chat1", "user1", "page", json!(2))
            .await
            .unwrap();

        assert_eq!(
            manager.get_context("chat1", "user1", "page").await.unwrap(),
            Some(json!(2))
        );
        assert_eq!(
            manager
                .get_context("chat1", "user1", "missing")
                .await
                .unwrap(),
            None
        );
    }

    #[tokio::test]
    async fn session_manager_deletes_sessions() {
        let manager = test_session_manager();

        let _ = manager
            .get_or_create_session("chat1", "user1")
            .await
            .unwrap();
        manager.delete_session("chat1", "user1").await.unwrap();

        assert!(manager
            .get_session("chat1", "user1")
            .await
            .unwrap()
            .is_none());
    }

    fn test_session_manager() -> SessionManager {
        SessionManager::new(Arc::new(InMemoryStateStore::new()), Duration::from_secs(60))
    }
}
