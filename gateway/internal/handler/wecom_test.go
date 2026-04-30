package handler

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Wisdoverse/project-cell/gateway/internal/config"
	"github.com/Wisdoverse/project-cell/gateway/internal/service"
	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

func TestNewWecomHandler(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret123",
		Token:          "token123",
		EncodingAESKey: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG", // 43 chars
	}
	matcher := service.NewMatcher()

	h, err := NewWecomHandler(cfg, nil, matcher, nil, nil, logger)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if h.cfg != cfg {
		t.Error("cfg not set correctly")
	}

	if h.matcher != matcher {
		t.Error("matcher not set correctly")
	}

	if h.wecomClient == nil {
		t.Error("wecomClient should not be nil")
	}

	if h.crypto == nil {
		t.Error("crypto should not be nil")
	}
}

func TestNewWecomHandler_InvalidKey(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret123",
		Token:          "token123",
		EncodingAESKey: "too-short", // Invalid
	}

	_, err := NewWecomHandler(cfg, nil, service.NewMatcher(), nil, nil, logger)
	if err == nil {
		t.Error("expected error for invalid encoding key")
	}
}

func TestWecomHandler_MethodNotAllowed(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret123",
		Token:          "token123",
		EncodingAESKey: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
	}

	h, _ := NewWecomHandler(cfg, nil, service.NewMatcher(), nil, nil, logger)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodPut, "/api/wecom/webhook", nil)

	h.Webhook(c)

	if w.Code != http.StatusMethodNotAllowed {
		t.Errorf("status = %d, want %d", w.Code, http.StatusMethodNotAllowed)
	}
}

func TestWecomHandler_URLVerification_InvalidSignature(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret123",
		Token:          "token123",
		EncodingAESKey: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
	}

	h, _ := NewWecomHandler(cfg, nil, service.NewMatcher(), nil, nil, logger)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/api/wecom/webhook?msg_signature=invalid&timestamp=123&nonce=abc&echostr=test", nil)

	h.Webhook(c)

	if w.Code != http.StatusForbidden {
		t.Errorf("status = %d, want %d", w.Code, http.StatusForbidden)
	}
}

func TestWecomHandler_MessageCallback_InvalidBody(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret123",
		Token:          "token123",
		EncodingAESKey: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
	}

	h, _ := NewWecomHandler(cfg, nil, service.NewMatcher(), nil, nil, logger)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `<xml><invalid>not encrypted</invalid></xml>`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/wecom/webhook?msg_signature=sig&timestamp=123&nonce=abc", bytes.NewBufferString(body))

	h.Webhook(c)

	// Should return forbidden when decryption fails
	if w.Code != http.StatusForbidden {
		t.Errorf("status = %d, want %d", w.Code, http.StatusForbidden)
	}
}

func TestWecomHandler_PriorityEmoji(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret123",
		Token:          "token123",
		EncodingAESKey: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
	}

	h, _ := NewWecomHandler(cfg, nil, service.NewMatcher(), nil, nil, logger)

	tests := []struct {
		priority string
		want     string
	}{
		{"P0", "🔴"},
		{"P1", "🟠"},
		{"P2", "🟡"},
		{"P3", "🟢"},
		{"unknown", "🟢"},
		{"", "🟢"},
	}

	for _, tt := range tests {
		t.Run(tt.priority, func(t *testing.T) {
			got := h.priorityEmoji(tt.priority)
			if got != tt.want {
				t.Errorf("priorityEmoji(%q) = %q, want %q", tt.priority, got, tt.want)
			}
		})
	}
}

func TestWecomHandler_BuildHelpMarkdown(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret123",
		Token:          "token123",
		EncodingAESKey: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
	}

	h, _ := NewWecomHandler(cfg, nil, service.NewMatcher(), nil, nil, logger)

	md := h.buildHelpMarkdown()

	// Check key content
	if md == "" {
		t.Error("help markdown should not be empty")
	}

	// Should contain commands
	expectedCommands := []string{"/list", "/confirm", "/reject", "/help"}
	for _, cmd := range expectedCommands {
		if !containsString(md, cmd) {
			t.Errorf("help markdown should contain %q", cmd)
		}
	}
}

func containsString(s, substr string) bool {
	return bytes.Contains([]byte(s), []byte(substr))
}

func TestWecomHandler_WebhookGET(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret123",
		Token:          "token123",
		EncodingAESKey: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
	}

	h, _ := NewWecomHandler(cfg, nil, service.NewMatcher(), nil, nil, logger)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/api/wecom/webhook?msg_signature=test&timestamp=123&nonce=abc&echostr=test", nil)

	h.Webhook(c)

	// Will fail signature verification, but proves GET path is taken
	if w.Code != http.StatusForbidden {
		t.Errorf("status = %d, want %d", w.Code, http.StatusForbidden)
	}
}

func TestWecomHandler_WebhookPOST(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret123",
		Token:          "token123",
		EncodingAESKey: "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
	}

	h, _ := NewWecomHandler(cfg, nil, service.NewMatcher(), nil, nil, logger)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `<xml><ToUserName>corp</ToUserName><Encrypt>test</Encrypt></xml>`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/wecom/webhook?msg_signature=test&timestamp=123&nonce=abc", bytes.NewBufferString(body))

	h.Webhook(c)

	// Will fail decryption, but proves POST path is taken
	if w.Code != http.StatusForbidden {
		t.Errorf("status = %d, want %d", w.Code, http.StatusForbidden)
	}
}
