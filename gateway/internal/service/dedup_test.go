package service

import (
	"context"
	"testing"
	"time"
)

func TestDeduplicator_IsDuplicate(t *testing.T) {
	client, cleanup := setupTestRedis(t)
	defer cleanup()

	dedup := NewDeduplicator(client, time.Minute)
	ctx := context.Background()

	// First call should not be duplicate
	isDup, err := dedup.IsDuplicate(ctx, "msg_123")
	if err != nil {
		t.Fatalf("IsDuplicate failed: %v", err)
	}
	if isDup {
		t.Errorf("first call should not be duplicate")
	}

	// Second call should be duplicate
	isDup, err = dedup.IsDuplicate(ctx, "msg_123")
	if err != nil {
		t.Fatalf("IsDuplicate (second) failed: %v", err)
	}
	if !isDup {
		t.Errorf("second call should be duplicate")
	}

	// Different message should not be duplicate
	isDup, err = dedup.IsDuplicate(ctx, "msg_456")
	if err != nil {
		t.Fatalf("IsDuplicate (different) failed: %v", err)
	}
	if isDup {
		t.Errorf("different message should not be duplicate")
	}
}

func TestDeduplicator_MarkProcessed(t *testing.T) {
	client, cleanup := setupTestRedis(t)
	defer cleanup()

	dedup := NewDeduplicator(client, time.Minute)
	ctx := context.Background()

	// Mark as processed
	if err := dedup.MarkProcessed(ctx, "msg_789"); err != nil {
		t.Fatalf("MarkProcessed failed: %v", err)
	}

	// Should be processed
	processed, err := dedup.IsProcessed(ctx, "msg_789")
	if err != nil {
		t.Fatalf("IsProcessed failed: %v", err)
	}
	if !processed {
		t.Errorf("message should be marked as processed")
	}

	// Unprocessed message
	processed, _ = dedup.IsProcessed(ctx, "msg_999")
	if processed {
		t.Errorf("unprocessed message should not be marked")
	}
}

func TestEventDeduplicator_IsDuplicateEvent(t *testing.T) {
	client, cleanup := setupTestRedis(t)
	defer cleanup()

	dedup := NewEventDeduplicator(client, time.Minute)
	ctx := context.Background()

	// Empty event ID should not be duplicate
	isDup, err := dedup.IsDuplicateEvent(ctx, "")
	if err != nil {
		t.Fatalf("IsDuplicateEvent (empty) failed: %v", err)
	}
	if isDup {
		t.Errorf("empty event ID should not be duplicate")
	}

	// First event should not be duplicate
	isDup, err = dedup.IsDuplicateEvent(ctx, "evt_abc")
	if err != nil {
		t.Fatalf("IsDuplicateEvent failed: %v", err)
	}
	if isDup {
		t.Errorf("first event should not be duplicate")
	}

	// Second event should be duplicate
	isDup, err = dedup.IsDuplicateEvent(ctx, "evt_abc")
	if err != nil {
		t.Fatalf("IsDuplicateEvent (second) failed: %v", err)
	}
	if !isDup {
		t.Errorf("second event should be duplicate")
	}
}
