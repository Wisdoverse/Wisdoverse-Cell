package service

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	// Dedup key prefix
	dedupKeyPrefix = "dedup:"
	// Default dedup TTL (Feishu may retry within 3 seconds)
	defaultDedupTTL = 10 * time.Second
)

// Deduplicator handles message deduplication using Redis.
type Deduplicator struct {
	client *redis.Client
	ttl    time.Duration
}

// NewDeduplicator creates a new message deduplicator.
func NewDeduplicator(client *redis.Client, ttl time.Duration) *Deduplicator {
	if ttl == 0 {
		ttl = defaultDedupTTL
	}
	return &Deduplicator{
		client: client,
		ttl:    ttl,
	}
}

// IsDuplicate checks if a message has been processed recently.
// Returns true if this is a duplicate message.
func (d *Deduplicator) IsDuplicate(ctx context.Context, messageID string) (bool, error) {
	key := d.dedupKey(messageID)

	// Try to set the key with NX (only if not exists)
	ok, err := d.client.SetNX(ctx, key, "1", d.ttl).Result()
	if err != nil {
		return false, fmt.Errorf("check duplicate: %w", err)
	}

	// If SetNX returned false, key already exists = duplicate
	return !ok, nil
}

// MarkProcessed explicitly marks a message as processed.
func (d *Deduplicator) MarkProcessed(ctx context.Context, messageID string) error {
	key := d.dedupKey(messageID)
	return d.client.Set(ctx, key, "1", d.ttl).Err()
}

// IsProcessed checks if a message has been marked as processed.
func (d *Deduplicator) IsProcessed(ctx context.Context, messageID string) (bool, error) {
	key := d.dedupKey(messageID)
	exists, err := d.client.Exists(ctx, key).Result()
	if err != nil {
		return false, fmt.Errorf("check processed: %w", err)
	}
	return exists > 0, nil
}

func (d *Deduplicator) dedupKey(messageID string) string {
	return fmt.Sprintf("%s%s", dedupKeyPrefix, messageID)
}

// EventDeduplicator handles event deduplication for webhook callbacks.
type EventDeduplicator struct {
	client *redis.Client
	ttl    time.Duration
}

// NewEventDeduplicator creates a new event deduplicator.
func NewEventDeduplicator(client *redis.Client, ttl time.Duration) *EventDeduplicator {
	if ttl == 0 {
		ttl = 5 * time.Minute
	}
	return &EventDeduplicator{
		client: client,
		ttl:    ttl,
	}
}

// IsDuplicateEvent checks if an event has been processed.
// Uses event_id from Feishu webhook header.
func (d *EventDeduplicator) IsDuplicateEvent(ctx context.Context, eventID string) (bool, error) {
	if eventID == "" {
		return false, nil
	}

	key := fmt.Sprintf("event:%s", eventID)
	ok, err := d.client.SetNX(ctx, key, "1", d.ttl).Result()
	if err != nil {
		return false, fmt.Errorf("check event duplicate: %w", err)
	}

	return !ok, nil
}
