package service

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func setupTestRedis(t *testing.T) (*redis.Client, func()) {
	t.Helper()

	mr, err := miniredis.Run()
	if err != nil {
		t.Fatalf("failed to create miniredis: %v", err)
	}

	client := redis.NewClient(&redis.Options{
		Addr: mr.Addr(),
	})

	cleanup := func() {
		client.Close()
		mr.Close()
	}

	return client, cleanup
}

func TestSessionManager_GetOrCreateSession(t *testing.T) {
	client, cleanup := setupTestRedis(t)
	defer cleanup()

	mgr := NewSessionManager(client, time.Minute)
	ctx := context.Background()

	// Create new session
	session, err := mgr.GetOrCreateSession(ctx, "chat1", "user1")
	if err != nil {
		t.Fatalf("GetOrCreateSession failed: %v", err)
	}

	if session.ID != "chat1:user1" {
		t.Errorf("session ID = %q, want %q", session.ID, "chat1:user1")
	}
	if session.State != StateIdle {
		t.Errorf("session state = %q, want %q", session.State, StateIdle)
	}

	// Get existing session
	session2, err := mgr.GetOrCreateSession(ctx, "chat1", "user1")
	if err != nil {
		t.Fatalf("GetOrCreateSession (second) failed: %v", err)
	}
	if session2.ID != session.ID {
		t.Errorf("got different session ID")
	}
}

func TestSessionManager_UpdateState(t *testing.T) {
	client, cleanup := setupTestRedis(t)
	defer cleanup()

	mgr := NewSessionManager(client, time.Minute)
	ctx := context.Background()

	// Create session
	_, err := mgr.GetOrCreateSession(ctx, "chat1", "user1")
	if err != nil {
		t.Fatalf("GetOrCreateSession failed: %v", err)
	}

	// Update state
	if err := mgr.UpdateState(ctx, "chat1", "user1", StateAwaitingConfirm); err != nil {
		t.Fatalf("UpdateState failed: %v", err)
	}

	// Verify state
	session, err := mgr.GetSession(ctx, "chat1", "user1")
	if err != nil {
		t.Fatalf("GetSession failed: %v", err)
	}
	if session.State != StateAwaitingConfirm {
		t.Errorf("state = %q, want %q", session.State, StateAwaitingConfirm)
	}
}

func TestSessionManager_PendingRequirement(t *testing.T) {
	client, cleanup := setupTestRedis(t)
	defer cleanup()

	mgr := NewSessionManager(client, time.Minute)
	ctx := context.Background()

	// Set pending requirement
	if err := mgr.SetPendingRequirement(ctx, "chat1", "user1", "req_123"); err != nil {
		t.Fatalf("SetPendingRequirement failed: %v", err)
	}

	// Verify
	session, _ := mgr.GetSession(ctx, "chat1", "user1")
	if session.PendingRequirementID != "req_123" {
		t.Errorf("pending requirement = %q, want %q", session.PendingRequirementID, "req_123")
	}
	if session.State != StateAwaitingConfirm {
		t.Errorf("state = %q, want %q", session.State, StateAwaitingConfirm)
	}

	// Clear pending requirement
	if err := mgr.ClearPendingRequirement(ctx, "chat1", "user1"); err != nil {
		t.Fatalf("ClearPendingRequirement failed: %v", err)
	}

	session, _ = mgr.GetSession(ctx, "chat1", "user1")
	if session.PendingRequirementID != "" {
		t.Errorf("pending requirement should be empty")
	}
	if session.State != StateIdle {
		t.Errorf("state = %q, want %q", session.State, StateIdle)
	}
}

func TestSessionManager_MessageHistory(t *testing.T) {
	client, cleanup := setupTestRedis(t)
	defer cleanup()

	mgr := NewSessionManager(client, time.Minute)
	ctx := context.Background()

	// Add messages
	for i := 0; i < 15; i++ {
		if err := mgr.AddMessage(ctx, "chat1", "user1", "user", "message"); err != nil {
			t.Fatalf("AddMessage failed: %v", err)
		}
	}

	// Verify only last 10 are kept
	session, _ := mgr.GetSession(ctx, "chat1", "user1")
	if len(session.MessageHistory) != 10 {
		t.Errorf("message history length = %d, want 10", len(session.MessageHistory))
	}
}

func TestSessionManager_Context(t *testing.T) {
	client, cleanup := setupTestRedis(t)
	defer cleanup()

	mgr := NewSessionManager(client, time.Minute)
	ctx := context.Background()

	// Set context
	if err := mgr.SetContext(ctx, "chat1", "user1", "page", 2); err != nil {
		t.Fatalf("SetContext failed: %v", err)
	}

	// Get context
	val, err := mgr.GetContext(ctx, "chat1", "user1", "page")
	if err != nil {
		t.Fatalf("GetContext failed: %v", err)
	}

	// JSON unmarshaling converts numbers to float64
	if page, ok := val.(float64); !ok || page != 2 {
		t.Errorf("context value = %v, want 2", val)
	}
}

func TestSessionManager_DeleteSession(t *testing.T) {
	client, cleanup := setupTestRedis(t)
	defer cleanup()

	mgr := NewSessionManager(client, time.Minute)
	ctx := context.Background()

	// Create and delete
	_, _ = mgr.GetOrCreateSession(ctx, "chat1", "user1")
	if err := mgr.DeleteSession(ctx, "chat1", "user1"); err != nil {
		t.Fatalf("DeleteSession failed: %v", err)
	}

	// Verify deleted
	session, _ := mgr.GetSession(ctx, "chat1", "user1")
	if session != nil {
		t.Errorf("session should be nil after delete")
	}
}
