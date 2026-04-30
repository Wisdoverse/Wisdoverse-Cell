package service

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	// Session key prefix
	sessionKeyPrefix = "session:"
	// Default session TTL
	defaultSessionTTL = 5 * time.Minute
)

// SessionState represents the current state of a conversation session.
type SessionState string

const (
	StateIdle             SessionState = "idle"
	StateAwaitingConfirm  SessionState = "awaiting_confirm"
	StateAwaitingReject   SessionState = "awaiting_reject"
	StateAwaitingInput    SessionState = "awaiting_input"
)

// Session represents a user conversation session.
type Session struct {
	// Unique identifier (chat_id:user_id)
	ID string `json:"id"`
	// Current conversation state
	State SessionState `json:"state"`
	// Context data for the current operation
	Context map[string]interface{} `json:"context,omitempty"`
	// Last active timestamp
	LastActive time.Time `json:"last_active"`
	// Session creation time
	CreatedAt time.Time `json:"created_at"`
	// Pending requirement ID (if any)
	PendingRequirementID string `json:"pending_requirement_id,omitempty"`
	// Message history for context
	MessageHistory []SessionMessage `json:"message_history,omitempty"`
}

// SessionMessage represents a message in session history.
type SessionMessage struct {
	Role      string    `json:"role"` // user, assistant
	Content   string    `json:"content"`
	Timestamp time.Time `json:"timestamp"`
}

// SessionManager manages user sessions using Redis.
type SessionManager struct {
	client *redis.Client
	ttl    time.Duration
}

// NewSessionManager creates a new session manager.
func NewSessionManager(client *redis.Client, ttl time.Duration) *SessionManager {
	if ttl == 0 {
		ttl = defaultSessionTTL
	}
	return &SessionManager{
		client: client,
		ttl:    ttl,
	}
}

// GetSession retrieves a session by chat and user ID.
func (m *SessionManager) GetSession(ctx context.Context, chatID, userID string) (*Session, error) {
	key := m.sessionKey(chatID, userID)

	data, err := m.client.Get(ctx, key).Bytes()
	if err == redis.Nil {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("get session: %w", err)
	}

	var session Session
	if err := json.Unmarshal(data, &session); err != nil {
		return nil, fmt.Errorf("unmarshal session: %w", err)
	}

	return &session, nil
}

// GetOrCreateSession gets an existing session or creates a new one.
func (m *SessionManager) GetOrCreateSession(ctx context.Context, chatID, userID string) (*Session, error) {
	session, err := m.GetSession(ctx, chatID, userID)
	if err != nil {
		return nil, err
	}

	if session != nil {
		return session, nil
	}

	// Create new session
	session = &Session{
		ID:         fmt.Sprintf("%s:%s", chatID, userID),
		State:      StateIdle,
		Context:    make(map[string]interface{}),
		LastActive: time.Now(),
		CreatedAt:  time.Now(),
	}

	if err := m.SaveSession(ctx, chatID, userID, session); err != nil {
		return nil, err
	}

	return session, nil
}

// SaveSession saves a session to Redis.
func (m *SessionManager) SaveSession(ctx context.Context, chatID, userID string, session *Session) error {
	key := m.sessionKey(chatID, userID)
	session.LastActive = time.Now()

	data, err := json.Marshal(session)
	if err != nil {
		return fmt.Errorf("marshal session: %w", err)
	}

	if err := m.client.Set(ctx, key, data, m.ttl).Err(); err != nil {
		return fmt.Errorf("save session: %w", err)
	}

	return nil
}

// UpdateState updates the session state.
func (m *SessionManager) UpdateState(ctx context.Context, chatID, userID string, state SessionState) error {
	session, err := m.GetOrCreateSession(ctx, chatID, userID)
	if err != nil {
		return err
	}

	session.State = state
	return m.SaveSession(ctx, chatID, userID, session)
}

// SetPendingRequirement sets the pending requirement for confirmation/rejection.
func (m *SessionManager) SetPendingRequirement(ctx context.Context, chatID, userID, reqID string) error {
	session, err := m.GetOrCreateSession(ctx, chatID, userID)
	if err != nil {
		return err
	}

	session.PendingRequirementID = reqID
	session.State = StateAwaitingConfirm
	return m.SaveSession(ctx, chatID, userID, session)
}

// ClearPendingRequirement clears the pending requirement.
func (m *SessionManager) ClearPendingRequirement(ctx context.Context, chatID, userID string) error {
	session, err := m.GetSession(ctx, chatID, userID)
	if err != nil {
		return err
	}
	if session == nil {
		return nil
	}

	session.PendingRequirementID = ""
	session.State = StateIdle
	return m.SaveSession(ctx, chatID, userID, session)
}

// AddMessage adds a message to the session history.
func (m *SessionManager) AddMessage(ctx context.Context, chatID, userID, role, content string) error {
	session, err := m.GetOrCreateSession(ctx, chatID, userID)
	if err != nil {
		return err
	}

	msg := SessionMessage{
		Role:      role,
		Content:   content,
		Timestamp: time.Now(),
	}

	session.MessageHistory = append(session.MessageHistory, msg)

	// Keep only last 10 messages
	if len(session.MessageHistory) > 10 {
		session.MessageHistory = session.MessageHistory[len(session.MessageHistory)-10:]
	}

	return m.SaveSession(ctx, chatID, userID, session)
}

// SetContext sets a context value.
func (m *SessionManager) SetContext(ctx context.Context, chatID, userID, key string, value interface{}) error {
	session, err := m.GetOrCreateSession(ctx, chatID, userID)
	if err != nil {
		return err
	}

	if session.Context == nil {
		session.Context = make(map[string]interface{})
	}
	session.Context[key] = value

	return m.SaveSession(ctx, chatID, userID, session)
}

// GetContext gets a context value.
func (m *SessionManager) GetContext(ctx context.Context, chatID, userID, key string) (interface{}, error) {
	session, err := m.GetSession(ctx, chatID, userID)
	if err != nil {
		return nil, err
	}
	if session == nil || session.Context == nil {
		return nil, nil
	}

	return session.Context[key], nil
}

// DeleteSession removes a session.
func (m *SessionManager) DeleteSession(ctx context.Context, chatID, userID string) error {
	key := m.sessionKey(chatID, userID)
	return m.client.Del(ctx, key).Err()
}

// RefreshTTL extends the session TTL.
func (m *SessionManager) RefreshTTL(ctx context.Context, chatID, userID string) error {
	key := m.sessionKey(chatID, userID)
	return m.client.Expire(ctx, key, m.ttl).Err()
}

func (m *SessionManager) sessionKey(chatID, userID string) string {
	return fmt.Sprintf("%s%s:%s", sessionKeyPrefix, chatID, userID)
}
