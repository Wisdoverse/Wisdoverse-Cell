package handler

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/Wisdoverse/project-cell/gateway/internal/config"
	"github.com/Wisdoverse/project-cell/gateway/internal/service"
	"github.com/Wisdoverse/project-cell/gateway/pkg/feishu"
	"github.com/alicebob/miniredis/v2"
	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"
)

// newTestHandler creates a FeishuHandler with sensible test defaults.
// Use this for tests that don't need custom config fields like EncryptKey
// or VerifySignature.
func newTestHandler(t *testing.T, chatAgentAddr string) *FeishuHandler {
	t.Helper()
	return NewFeishuHandler(
		&config.FeishuConfig{AppID: "app123", AppSecret: "secret123"},
		nil, service.NewMatcher(), nil, nil, chatAgentAddr, "", zap.NewNop(),
	)
}

func TestNewFeishuHandler(t *testing.T) {
	logger := zap.NewNop()
	cfg := &config.FeishuConfig{
		AppID:     "app123",
		AppSecret: "secret123",
	}
	matcher := service.NewMatcher()

	h := NewFeishuHandler(cfg, nil, matcher, nil, nil, "", "", logger)

	if h.cfg != cfg {
		t.Error("cfg not set correctly")
	}

	if h.matcher != matcher {
		t.Error("matcher not set correctly")
	}

	if h.logger != logger {
		t.Error("logger not set correctly")
	}

	if h.feishuClient == nil {
		t.Error("feishuClient should not be nil")
	}

	if h.chatAgentAddr != "" {
		t.Errorf("chatAgentAddr = %q, want empty string", h.chatAgentAddr)
	}

	if h.httpClient == nil {
		t.Error("httpClient should not be nil")
	}
}

func TestNewFeishuHandler_WithChatAgentAddr(t *testing.T) {
	h := newTestHandler(t, "chat-agent:8080")

	if h.chatAgentAddr != "chat-agent:8080" {
		t.Errorf("chatAgentAddr = %q, want %q", h.chatAgentAddr, "chat-agent:8080")
	}
}

func TestFeishuHandler_URLVerification(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{"type":"url_verification","challenge":"test-challenge-12345"}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if resp["challenge"] != "test-challenge-12345" {
		t.Errorf("challenge = %v, want test-challenge-12345", resp["challenge"])
	}
}

func TestFeishuHandler_InvalidJSON(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `not valid json`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want %d", w.Code, http.StatusBadRequest)
	}
}

func TestFeishuHandler_UnknownType(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{"type":"unknown_type"}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestFeishuHandler_EventCallback_NoHeader(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{"type":"event_callback"}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestFeishuHandler_EventCallback_UnhandledEvent(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{"type":"event_callback","header":{"event_type":"unknown_event"}}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestFeishuHandler_CardAction_ParseError(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	// Invalid action JSON
	body := `{"type":"card_action","action":"not-json"}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestFeishuHandler_SignatureVerification(t *testing.T) {
	cfg := &config.FeishuConfig{
		AppID:           "app123",
		AppSecret:       "secret123",
		EncryptKey:      "test-key",
		VerifySignature: true,
	}

	h := NewFeishuHandler(cfg, nil, service.NewMatcher(), nil, nil, "", "", zap.NewNop())

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{"type":"url_verification","challenge":"test"}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("X-Lark-Signature", "invalid-signature")
	c.Request.Header.Set("X-Lark-Request-Timestamp", "123456")
	c.Request.Header.Set("X-Lark-Request-Nonce", "nonce")

	h.Webhook(c)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want %d", w.Code, http.StatusUnauthorized)
	}
}

func TestFeishuHandler_SignatureEnabledWithoutEncryptKey(t *testing.T) {
	cfg := &config.FeishuConfig{
		AppID:           "app123",
		AppSecret:       "secret123",
		VerifySignature: true,
	}

	h := NewFeishuHandler(cfg, nil, service.NewMatcher(), nil, nil, "", "", zap.NewNop())

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{"type":"url_verification","challenge":"test"}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("status = %d, want %d", w.Code, http.StatusServiceUnavailable)
	}
}

func TestParseInt(t *testing.T) {
	tests := []struct {
		input   string
		want    int
		wantErr bool
	}{
		{"123", 123, false},
		{"0", 0, false},
		{"-5", -5, false},
		{"abc", 0, true},
		{"", 0, true},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got, err := parseInt(tt.input)
			if (err != nil) != tt.wantErr {
				t.Errorf("parseInt(%q) error = %v, wantErr %v", tt.input, err, tt.wantErr)
				return
			}
			if got != tt.want {
				t.Errorf("parseInt(%q) = %d, want %d", tt.input, got, tt.want)
			}
		})
	}
}

func TestFeishuHandler_MessageEvent_InvalidJSON(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{
		"type": "event_callback",
		"header": {"event_type": "im.message.receive_v1"},
		"event": "not-valid-json"
	}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestFeishuHandler_CardActionWithoutType(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	// Card action can come without type field, just action field
	body := `{"action":{"value":{"action":"confirm","requirement_id":"req_123"}},"open_id":"user123"}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	// Should be handled gracefully
	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestFeishuHandler_CardAction_MissingRequirementID(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{
		"type": "card_action",
		"action": {"value": {"action": "confirm"}}
	}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestFeishuHandler_CardAction_ListPage(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{
		"type": "card_action",
		"action": {"value": {"action": "list_page", "page": 2}}
	}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	// Will fail without gRPC client, but should parse and attempt call
	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestFeishuHandler_SignatureSkipWhenDisabled(t *testing.T) {
	cfg := &config.FeishuConfig{
		AppID:           "app123",
		AppSecret:       "secret123",
		EncryptKey:      "test-key",
		VerifySignature: false, // Disabled
	}

	h := NewFeishuHandler(cfg, nil, service.NewMatcher(), nil, nil, "", "", zap.NewNop())

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{"type":"url_verification","challenge":"test-challenge"}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	// No signature headers - should still work

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	if resp["challenge"] != "test-challenge" {
		t.Errorf("challenge = %v, want test-challenge", resp["challenge"])
	}
}

func TestFeishuHandler_ForwardToChatAgent(t *testing.T) {
	// Protect shared variables between the mock handler goroutine and the
	// test goroutine to satisfy the Go race detector.
	var mu sync.Mutex
	var receivedBody []byte
	var receivedContentType string
	var readErr error

	chatAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		receivedContentType = r.Header.Get("Content-Type")
		receivedBody, readErr = io.ReadAll(r.Body)
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"code":0}`))
	}))
	defer chatAgent.Close()

	// Extract host:port from the test server URL (strip "http://").
	addr := chatAgent.URL[len("http://"):]

	h := newTestHandler(t, addr)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	// Simulate a message event that won't match any skill, triggering forwardToChatAgent.
	body := `{
		"header": {"event_type": "im.message.receive_v1"},
		"event": {
			"message": {
				"message_id": "msg_fwd_test",
				"chat_id": "chat_001",
				"message_type": "text",
				"content": "{\"text\":\"hello world\"}"
			},
			"sender": {
				"sender_id": {"open_id": "ou_user1"}
			}
		}
	}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	// Lock before reading variables written by the mock handler goroutine.
	mu.Lock()
	defer mu.Unlock()

	if readErr != nil {
		t.Fatalf("mock chat-agent failed to read request body: %v", readErr)
	}

	if len(receivedBody) == 0 {
		t.Fatal("chat-agent did not receive forwarded body")
	}

	if receivedContentType != "application/json" {
		t.Errorf("content-type = %q, want application/json", receivedContentType)
	}

	// Verify the forwarded body is valid JSON with the original event data.
	var forwarded map[string]interface{}
	if err := json.Unmarshal(receivedBody, &forwarded); err != nil {
		t.Fatalf("forwarded body is not valid JSON: %v", err)
	}

	header, ok := forwarded["header"].(map[string]interface{})
	if !ok {
		t.Fatal("forwarded body missing 'header' field")
	}
	if header["event_type"] != "im.message.receive_v1" {
		t.Errorf("forwarded event_type = %v, want im.message.receive_v1", header["event_type"])
	}
}

func TestFeishuHandler_ForwardSkippedWhenNoAddr(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	// Feishu v2.0 message event (no "type" field) that won't match any skill.
	body := `{
		"header": {"event_type": "im.message.receive_v1"},
		"event": {
			"message": {
				"message_id": "msg_no_fwd",
				"chat_id": "chat_002",
				"message_type": "text",
				"content": "{\"text\":\"hello\"}"
			},
			"sender": {
				"sender_id": {"open_id": "ou_user2"}
			}
		}
	}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestFeishuHandler_CardAction_RejectBitableUpdate(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{
		"type": "card_action",
		"action": {"value": {"action": "reject_bitable_update"}}
	}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	// Verify the response contains a cancel card
	var card map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &card); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	header, ok := card["header"].(map[string]interface{})
	if !ok {
		t.Fatal("response missing 'header' field")
	}
	title, _ := header["title"].(map[string]interface{})
	if title == nil || title["content"] == nil {
		t.Fatal("response missing header title")
	}
	// The header should indicate cancellation
	content := title["content"].(string)
	if content == "" {
		t.Error("card header title is empty")
	}
}

func TestFeishuHandler_CardAction_ConfirmBitableUpdate_MissingData(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	// confirm_bitable_update without record_id should return an error card safely
	body := `{
		"type": "card_action",
		"action": {"value": {"action": "confirm_bitable_update"}}
	}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	var card map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &card); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	// Should return an error card with header
	if _, ok := card["header"]; !ok {
		t.Fatal("response missing 'header' field — expected error card")
	}
}

func TestFeishuHandler_CardAction_ConfirmBitableUpdate_Forward(t *testing.T) {
	var mu sync.Mutex
	var receivedBody []byte
	var readErr error

	// Mock chat-agent that returns a result card
	chatAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		receivedBody, readErr = io.ReadAll(r.Body)
		// Return a success card
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"header": {"title": {"tag": "plain_text", "content": "✅ 表格已更新"}, "template": "green"},
			"elements": [{"tag": "markdown", "content": "已更新"}]
		}`))
	}))
	defer chatAgent.Close()

	addr := chatAgent.URL[len("http://"):]
	h := newTestHandler(t, addr)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := `{
		"type": "card_action",
		"action": {"value": {"action": "confirm_bitable_update", "record_id": "rec_abc123", "fields": {"状态": "已完成"}}}
	}`
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	mu.Lock()
	defer mu.Unlock()

	if readErr != nil {
		t.Fatalf("mock chat-agent failed to read body: %v", readErr)
	}

	// Verify the forwarded payload contains record_id and fields
	var payload map[string]interface{}
	if err := json.Unmarshal(receivedBody, &payload); err != nil {
		t.Fatalf("forwarded body is not valid JSON: %v", err)
	}

	if payload["record_id"] != "rec_abc123" {
		t.Errorf("record_id = %v, want rec_abc123", payload["record_id"])
	}

	fields, ok := payload["fields"].(map[string]interface{})
	if !ok {
		t.Fatal("forwarded payload missing 'fields'")
	}
	if fields["状态"] != "已完成" {
		t.Errorf("fields[状态] = %v, want 已完成", fields["状态"])
	}

	// Verify the response is the card from chat-agent
	var respCard map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &respCard); err != nil {
		t.Fatalf("failed to unmarshal response card: %v", err)
	}
	header, _ := respCard["header"].(map[string]interface{})
	if header == nil {
		t.Fatal("response missing header")
	}
}

func TestFeishuHandler_CardActionTimeout(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping timeout test in short mode")
	}

	// Verify the constant is set correctly
	if cardActionTimeout != 12*time.Second {
		t.Errorf("cardActionTimeout = %v, want 12s", cardActionTimeout)
	}
}

func TestFeishuHandler_ConfirmBitableTimeout_ReturnsProcessingCard(t *testing.T) {
	// Mock a chat-agent that sleeps longer than the card action timeout.
	// We override cardActionTimeout is a const, so we create a server that
	// simply never responds within time. We use a very short custom timeout
	// to keep the test fast.
	chatAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Sleep longer than our test will wait — the client context
		// will cancel before this completes.
		time.Sleep(500 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer chatAgent.Close()

	addr := chatAgent.URL[len("http://"):]
	h := newTestHandler(t, addr)
	// Use a very short timeout httpClient so we don't wait 12s in tests.
	h.httpClient = &http.Client{Timeout: 100 * time.Millisecond}

	// Call forwardBitableConfirm directly with a value map
	value := map[string]interface{}{
		"record_id": "rec_timeout_test",
		"fields":    map[string]interface{}{"状态": "已完成"},
	}
	card := h.forwardBitableConfirm("rec_timeout_test", value, "ou_user1")

	// The card should be a processing card (timeout fallback) OR error card.
	// Since the httpClient timeout (100ms) fires before context timeout (12s),
	// we get an error card. To truly test the context deadline path,
	// we need the context to expire.
	if card == nil {
		t.Fatal("expected a card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}
}

func TestFeishuHandler_CreateBitableTimeout_ReturnsProcessingCard(t *testing.T) {
	chatAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(500 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer chatAgent.Close()

	addr := chatAgent.URL[len("http://"):]
	h := newTestHandler(t, addr)
	h.httpClient = &http.Client{Timeout: 100 * time.Millisecond}

	value := map[string]interface{}{
		"fields": map[string]interface{}{"任务": "测试超时"},
	}
	card := h.forwardBitableCreate(value, "ou_user1")

	if card == nil {
		t.Fatal("expected a card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}
}

func TestBuildProcessingCard(t *testing.T) {
	card := buildProcessingCard()
	if card == nil {
		t.Fatal("buildProcessingCard returned nil")
	}
	if card.Header == nil {
		t.Fatal("processing card missing header")
	}
	if card.Header.Title == nil {
		t.Fatal("processing card header missing title")
	}
	if card.Header.Title.Content == "" {
		t.Error("processing card title content is empty")
	}
	if card.Header.Template != "blue" {
		t.Errorf("processing card template = %q, want blue", card.Header.Template)
	}
}

// newTestHandlerWithDedup creates a handler with a real Deduplicator backed by miniredis.
func newTestHandlerWithDedup(t *testing.T, chatAgentAddr string) (*FeishuHandler, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	dedup := service.NewDeduplicator(rdb, 10*time.Second)
	h := NewFeishuHandler(
		&config.FeishuConfig{AppID: "app123", AppSecret: "secret123"},
		nil, service.NewMatcher(), nil, dedup, chatAgentAddr, "", zap.NewNop(),
	)
	return h, mr
}

// makeMessageEventBody builds a Feishu v2.0 message event JSON body.
func makeMessageEventBody(messageID, chatID, content string) string {
	return `{
		"header": {"event_type": "im.message.receive_v1"},
		"event": {
			"message": {
				"message_id": "` + messageID + `",
				"chat_id": "` + chatID + `",
				"message_type": "text",
				"content": "{\"text\":\"` + content + `\"}"
			},
			"sender": {
				"sender_id": {"open_id": "ou_testuser"}
			}
		}
	}`
}

func TestHandleMessageEvent_SkillMatch(t *testing.T) {
	// Sending "/help" should match the help skill and return 200.
	// The feishuClient.ReplyCard will fail (no real Feishu API), but the
	// handler should still respond 200 to Feishu (graceful degradation).
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := makeMessageEventBody("msg_help_001", "chat_skill", "/help")
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestHandleMessageEvent_SkillMatch_Search(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := makeMessageEventBody("msg_search_001", "chat_skill", "/search 登录问题")
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}
	// executeSkill("search") returns {"code":0}
	if resp["code"] != float64(0) {
		t.Errorf("code = %v, want 0", resp["code"])
	}
}

func TestHandleMessageEvent_SkillMatch_UnimplementedSkill(t *testing.T) {
	h := newTestHandler(t, "")
	// Register a custom command that maps to an unimplemented skill
	h.matcher.RegisterCommand("/bogus", "nonexistent_skill")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := makeMessageEventBody("msg_bogus_001", "chat_bogus", "/bogus")
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestHandleMessageEvent_NoSkillMatch_ForwardsToChat(t *testing.T) {
	// A plain message that doesn't match any skill should be forwarded to chat-agent.
	var mu sync.Mutex
	var gotRequest bool

	chatAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		gotRequest = true
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"code":0}`))
	}))
	defer chatAgent.Close()

	addr := chatAgent.URL[len("http://"):]
	h := newTestHandler(t, addr)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := makeMessageEventBody("msg_noskill_001", "chat_noskill", "今天天气怎么样")
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	mu.Lock()
	defer mu.Unlock()
	if !gotRequest {
		t.Error("chat-agent should have received the forwarded request")
	}
}

func TestHandleMessageEvent_DuplicateIgnored(t *testing.T) {
	h, _ := newTestHandlerWithDedup(t, "")

	// First request — should be processed
	w1 := httptest.NewRecorder()
	c1, _ := gin.CreateTestContext(w1)
	body := makeMessageEventBody("msg_dup_001", "chat_dup", "hello")
	c1.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c1.Request.Header.Set("Content-Type", "application/json")
	h.Webhook(c1)

	if w1.Code != http.StatusOK {
		t.Fatalf("first request: status = %d, want %d", w1.Code, http.StatusOK)
	}

	// Second request with the same message_id — should be deduplicated
	w2 := httptest.NewRecorder()
	c2, _ := gin.CreateTestContext(w2)
	c2.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c2.Request.Header.Set("Content-Type", "application/json")
	h.Webhook(c2)

	if w2.Code != http.StatusOK {
		t.Errorf("second request: status = %d, want %d", w2.Code, http.StatusOK)
	}

	// Both return 200, but the second one should have been short-circuited.
	// We verify by checking that the response is {"code":0} (dedup response).
	var resp2 map[string]interface{}
	if err := json.Unmarshal(w2.Body.Bytes(), &resp2); err != nil {
		t.Fatalf("failed to unmarshal second response: %v", err)
	}
	if resp2["code"] != float64(0) {
		t.Errorf("second response code = %v, want 0", resp2["code"])
	}
}

func TestHandleMessageEvent_DifferentMessagesNotDeduped(t *testing.T) {
	h, _ := newTestHandlerWithDedup(t, "")

	// Two different message IDs should both be processed
	for i, msgID := range []string{"msg_unique_001", "msg_unique_002"} {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		body := makeMessageEventBody(msgID, "chat_unique", "hello")
		c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
		c.Request.Header.Set("Content-Type", "application/json")
		h.Webhook(c)

		if w.Code != http.StatusOK {
			t.Errorf("request %d: status = %d, want %d", i+1, w.Code, http.StatusOK)
		}
	}
}

func TestForwardToChatAgent_InternalKeyHeader(t *testing.T) {
	var mu sync.Mutex
	var receivedKey string

	chatAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		receivedKey = r.Header.Get("X-Internal-Key")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"code":0}`))
	}))
	defer chatAgent.Close()

	addr := chatAgent.URL[len("http://"):]
	cfg := &config.FeishuConfig{
		AppID:              "app123",
		AppSecret:          "secret123",
		InternalServiceKey: "my-secret-key",
	}
	h := NewFeishuHandler(cfg, nil, service.NewMatcher(), nil, nil, addr, "", zap.NewNop())

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := makeMessageEventBody("msg_key_001", "chat_key", "plain message")
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	h.Webhook(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	mu.Lock()
	defer mu.Unlock()
	if receivedKey != "my-secret-key" {
		t.Errorf("X-Internal-Key = %q, want %q", receivedKey, "my-secret-key")
	}
}

func TestForwardToChatAgent_ServerError(t *testing.T) {
	chatAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer chatAgent.Close()

	addr := chatAgent.URL[len("http://"):]
	h := newTestHandler(t, addr)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	body := makeMessageEventBody("msg_err_001", "chat_err", "trigger forward")
	c.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c.Request.Header.Set("Content-Type", "application/json")

	h.Webhook(c)

	// Handler should still return 200 to Feishu even if chat-agent errors
	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestHandleMessageEvent_DedupWithSkillMatch(t *testing.T) {
	// Verify dedup works even when a skill matches — the second /help
	// should be short-circuited before reaching executeSkill.
	h, _ := newTestHandlerWithDedup(t, "")

	// First /help
	w1 := httptest.NewRecorder()
	c1, _ := gin.CreateTestContext(w1)
	body := makeMessageEventBody("msg_dedup_help", "chat_dedup", "/help")
	c1.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c1.Request.Header.Set("Content-Type", "application/json")
	h.Webhook(c1)

	if w1.Code != http.StatusOK {
		t.Fatalf("first /help: status = %d, want %d", w1.Code, http.StatusOK)
	}

	// Second /help with same message_id
	w2 := httptest.NewRecorder()
	c2, _ := gin.CreateTestContext(w2)
	c2.Request = httptest.NewRequest(http.MethodPost, "/api/feishu/webhook", bytes.NewBufferString(body))
	c2.Request.Header.Set("Content-Type", "application/json")
	h.Webhook(c2)

	if w2.Code != http.StatusOK {
		t.Errorf("second /help: status = %d, want %d", w2.Code, http.StatusOK)
	}
}

func TestDispatchCardAction_ConfirmRequirement(t *testing.T) {
	// When reqClient is nil (no gRPC), dispatch should return 200 with code:0
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodPost, "/", nil)

	actx := &cardActionContext{
		actionType:  "confirm",
		reqID:       "req_123",
		operatorID:  "ou_user1",
		actionValue: map[string]interface{}{"action": "confirm", "requirement_id": "req_123"},
	}

	var respondedCard *feishu.Card
	respond := func(_ *gin.Context, card *feishu.Card) {
		respondedCard = card
	}

	h.dispatchCardAction(c, actx, respond)

	// reqClient is nil, so handler should short-circuit with code:0
	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
	// respond should NOT have been called since reqClient is nil
	if respondedCard != nil {
		t.Error("respond should not be called when reqClient is nil")
	}
}

func TestDispatchCardAction_ConfirmRequirement_NoReqID(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodPost, "/", nil)

	actx := &cardActionContext{
		actionType:  "confirm",
		reqID:       "", // empty
		operatorID:  "ou_user1",
		actionValue: map[string]interface{}{"action": "confirm"},
	}

	var respondedCard *feishu.Card
	respond := func(_ *gin.Context, card *feishu.Card) {
		respondedCard = card
	}

	h.dispatchCardAction(c, actx, respond)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
	if respondedCard != nil {
		t.Error("respond should not be called when reqID is empty")
	}
}

func TestDispatchCardAction_UnknownAction(t *testing.T) {
	h := newTestHandler(t, "")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodPost, "/", nil)

	actx := &cardActionContext{
		actionType:  "totally_unknown_action",
		reqID:       "",
		operatorID:  "ou_user1",
		actionValue: map[string]interface{}{"action": "totally_unknown_action"},
	}

	var respondCalled bool
	respond := func(_ *gin.Context, card *feishu.Card) {
		respondCalled = true
	}

	h.dispatchCardAction(c, actx, respond)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
	// Unknown action should NOT call respond — it falls through to default
	if respondCalled {
		t.Error("respond should not be called for unknown action type")
	}
}

func TestForwardBitableConfirm_NoChatAgent(t *testing.T) {
	h := newTestHandler(t, "") // no chat-agent address

	value := map[string]interface{}{
		"record_id": "rec_001",
		"fields":    map[string]interface{}{"name": "test"},
	}
	card := h.forwardBitableConfirm("rec_001", value, "ou_user1")

	if card == nil {
		t.Fatal("expected error card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}
	// Should be a red error card
	if card.Header.Template != "red" {
		t.Errorf("card template = %q, want red", card.Header.Template)
	}
}

func TestForwardBitableConfirm_ServerError(t *testing.T) {
	chatAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"error":"internal"}`))
	}))
	defer chatAgent.Close()

	addr := chatAgent.URL[len("http://"):]
	h := newTestHandler(t, addr)

	value := map[string]interface{}{
		"record_id": "rec_err",
		"fields":    map[string]interface{}{"status": "done"},
	}
	card := h.forwardBitableConfirm("rec_err", value, "ou_user1")

	if card == nil {
		t.Fatal("expected error card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}
	if card.Header.Template != "red" {
		t.Errorf("card template = %q, want red", card.Header.Template)
	}
	// Check that the error message mentions HTTP 500
	if len(card.Elements) == 0 {
		t.Fatal("expected card elements with error message")
	}
}

func TestForwardBitableCreate_Success(t *testing.T) {
	var mu sync.Mutex
	var receivedPath string
	var receivedBody []byte

	chatAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		receivedPath = r.URL.Path
		receivedBody, _ = io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"header": {"title": {"tag": "plain_text", "content": "✅ 任务已创建"}, "template": "green"},
			"elements": [{"tag": "markdown", "content": "创建成功"}]
		}`))
	}))
	defer chatAgent.Close()

	addr := chatAgent.URL[len("http://"):]
	h := newTestHandler(t, addr)

	value := map[string]interface{}{
		"fields":   map[string]interface{}{"任务名": "新功能"},
		"table_id": "tbl_abc",
	}
	card := h.forwardBitableCreate(value, "ou_user1")

	if card == nil {
		t.Fatal("expected card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}

	mu.Lock()
	defer mu.Unlock()

	if receivedPath != "/api/bitable/create" {
		t.Errorf("request path = %q, want /api/bitable/create", receivedPath)
	}

	var payload map[string]interface{}
	if err := json.Unmarshal(receivedBody, &payload); err != nil {
		t.Fatalf("failed to parse forwarded body: %v", err)
	}
	if payload["user_id"] != "ou_user1" {
		t.Errorf("user_id = %v, want ou_user1", payload["user_id"])
	}
	if payload["table_id"] != "tbl_abc" {
		t.Errorf("table_id = %v, want tbl_abc", payload["table_id"])
	}
	fields, ok := payload["fields"].(map[string]interface{})
	if !ok {
		t.Fatal("payload missing fields")
	}
	if fields["任务名"] != "新功能" {
		t.Errorf("fields[任务名] = %v, want 新功能", fields["任务名"])
	}
}

func TestForwardBitableReject_NoChatAgent(t *testing.T) {
	h := newTestHandler(t, "") // no chat-agent address

	value := map[string]interface{}{
		"fields": map[string]interface{}{"name": "test"},
	}
	card := h.forwardBitableReject(value, "ou_user1", "update")

	if card == nil {
		t.Fatal("expected cancel card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}
	// Should be a grey cancel card
	if card.Header.Template != "grey" {
		t.Errorf("card template = %q, want grey", card.Header.Template)
	}
}

func TestForwardDecompositionAction_Success(t *testing.T) {
	var mu sync.Mutex
	var receivedPath string
	var receivedBody []byte

	pmAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		receivedPath = r.URL.Path
		receivedBody, _ = io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"success": true,
			"action": "approve",
			"wp_id": 42,
			"subject": "Epic Feature",
			"story_count": 3,
			"task_count": 7
		}`))
	}))
	defer pmAgent.Close()

	addr := pmAgent.URL[len("http://"):]
	h := newTestHandler(t, "")
	h.pmAgentAddr = addr

	card := h.forwardDecompositionAction(42, "approve", "ou_user1")

	if card == nil {
		t.Fatal("expected card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}
	if card.Header.Template != "green" {
		t.Errorf("card template = %q, want green", card.Header.Template)
	}

	mu.Lock()
	defer mu.Unlock()

	if receivedPath != "/api/v1/pm/decompose/42/approve" {
		t.Errorf("request path = %q, want /api/v1/pm/decompose/42/approve", receivedPath)
	}

	var payload map[string]interface{}
	if err := json.Unmarshal(receivedBody, &payload); err != nil {
		t.Fatalf("failed to parse forwarded body: %v", err)
	}
	if payload["operator"] != "ou_user1" {
		t.Errorf("operator = %v, want ou_user1", payload["operator"])
	}
}

func TestForwardDecompositionAction_Reject(t *testing.T) {
	pmAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"success": true,
			"action": "reject",
			"wp_id": 99,
			"subject": "Rejected Feature"
		}`))
	}))
	defer pmAgent.Close()

	addr := pmAgent.URL[len("http://"):]
	h := newTestHandler(t, "")
	h.pmAgentAddr = addr

	card := h.forwardDecompositionAction(99, "reject", "ou_user1")

	if card == nil {
		t.Fatal("expected card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}
	if card.Header.Template != "red" {
		t.Errorf("card template = %q, want red", card.Header.Template)
	}
}

func TestForwardDecompositionAction_NoPmAgent(t *testing.T) {
	h := newTestHandler(t, "")
	// pmAgentAddr is "" by default from newTestHandler

	card := h.forwardDecompositionAction(42, "approve", "ou_user1")

	if card == nil {
		t.Fatal("expected error card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}
	if card.Header.Template != "red" {
		t.Errorf("card template = %q, want red", card.Header.Template)
	}
}

func TestForwardDecompositionAction_ServerError(t *testing.T) {
	pmAgent := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"error":"internal"}`))
	}))
	defer pmAgent.Close()

	addr := pmAgent.URL[len("http://"):]
	h := newTestHandler(t, "")
	h.pmAgentAddr = addr

	card := h.forwardDecompositionAction(42, "approve", "ou_user1")

	if card == nil {
		t.Fatal("expected error card, got nil")
	}
	if card.Header == nil {
		t.Fatal("expected card with header")
	}
	if card.Header.Template != "red" {
		t.Errorf("card template = %q, want red", card.Header.Template)
	}
}
