package wecom

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestNewClient(t *testing.T) {
	client := NewClient("corp123", 1000001, "secret123")

	if client.corpID != "corp123" {
		t.Errorf("corpID = %q, want %q", client.corpID, "corp123")
	}
	if client.agentID != 1000001 {
		t.Errorf("agentID = %d, want %d", client.agentID, 1000001)
	}
	if client.secret != "secret123" {
		t.Errorf("secret = %q, want %q", client.secret, "secret123")
	}
	if client.httpClient == nil {
		t.Error("httpClient should not be nil")
	}
}

// newTestClientWithServer creates a Client whose tokenURL and sendMsgURL
// point to the given httptest.Server. Since the package uses package-level
// const URLs, we work around this by pre-setting the token cache (for
// SendMessage tests) or by overriding the httpClient transport to rewrite
// URLs to the test server.
func newTestClientWithServer(server *httptest.Server) *Client {
	// Use a custom transport that rewrites all requests to the test server.
	transport := &rewriteTransport{
		base:      server.Client().Transport,
		targetURL: server.URL,
	}
	return &Client{
		corpID:     "corp123",
		agentID:    1000001,
		secret:     "secret123",
		httpClient: &http.Client{Transport: transport, Timeout: 5 * time.Second},
	}
}

// rewriteTransport redirects all requests to the test server while preserving
// path and query parameters.
type rewriteTransport struct {
	base      http.RoundTripper
	targetURL string
}

func (rt *rewriteTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	// Rewrite scheme+host to test server, keep path+query.
	req.URL.Scheme = "http"
	// Extract host from targetURL
	req.URL.Host = strings.TrimPrefix(rt.targetURL, "http://")
	if rt.base != nil {
		return rt.base.RoundTrip(req)
	}
	return http.DefaultTransport.RoundTrip(req)
}

// ---------------------------------------------------------------------------
// GetAccessToken
// ---------------------------------------------------------------------------

func TestGetAccessToken_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.URL.Query().Get("corpid"); got != "corp123" {
			t.Errorf("corpid = %q, want %q", got, "corp123")
		}
		if got := r.URL.Query().Get("corpsecret"); got != "secret123" {
			t.Errorf("corpsecret = %q, want %q", got, "secret123")
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"errcode":      0,
			"errmsg":       "ok",
			"access_token": "tok_abc",
			"expires_in":   7200,
		})
	}))
	defer server.Close()

	client := newTestClientWithServer(server)
	token, err := client.GetAccessToken(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if token != "tok_abc" {
		t.Errorf("token = %q, want %q", token, "tok_abc")
	}
}

func TestGetAccessToken_Caching(t *testing.T) {
	callCount := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		callCount++
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"errcode":      0,
			"errmsg":       "ok",
			"access_token": fmt.Sprintf("tok_%d", callCount),
			"expires_in":   7200,
		})
	}))
	defer server.Close()

	client := newTestClientWithServer(server)
	// Pre-set a valid cached token
	client.token = "cached-token"
	client.tokenExpiry = time.Now().Add(1 * time.Hour)

	token, err := client.GetAccessToken(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if token != "cached-token" {
		t.Errorf("token = %q, want %q", token, "cached-token")
	}
	if callCount != 0 {
		t.Errorf("server called %d times, want 0 (should use cache)", callCount)
	}
}

func TestGetAccessToken_CacheExpired_Refreshes(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"errcode":      0,
			"errmsg":       "ok",
			"access_token": "new-token",
			"expires_in":   7200,
		})
	}))
	defer server.Close()

	client := newTestClientWithServer(server)
	client.token = "expired-token"
	client.tokenExpiry = time.Now().Add(-1 * time.Hour)

	token, err := client.GetAccessToken(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if token != "new-token" {
		t.Errorf("token = %q, want %q", token, "new-token")
	}
}

func TestGetAccessToken_APIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"errcode": 40001,
			"errmsg":  "invalid credential",
		})
	}))
	defer server.Close()

	client := newTestClientWithServer(server)
	_, err := client.GetAccessToken(context.Background())
	if err == nil {
		t.Fatal("expected error for invalid credential, got nil")
	}
	if !strings.Contains(err.Error(), "invalid credential") {
		t.Errorf("error = %q, want it to contain 'invalid credential'", err.Error())
	}
}

// ---------------------------------------------------------------------------
// SendMessage / SendTextMessage / SendMarkdownMessage / SendTextCard
// ---------------------------------------------------------------------------

func TestSendMessage_Success(t *testing.T) {
	var receivedBody map[string]interface{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" {
			_ = json.NewDecoder(r.Body).Decode(&receivedBody)
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"errcode": 0,
			"errmsg":  "ok",
		})
	}))
	defer server.Close()

	client := newTestClientWithServer(server)
	// Pre-cache a token so SendMessage doesn't need a token fetch
	client.token = "valid-token"
	client.tokenExpiry = time.Now().Add(1 * time.Hour)

	msg := &SendMessageRequest{
		ToUser:  "user123",
		MsgType: "text",
		Text:    &TextContent{Content: "Hello!"},
	}
	err := client.SendMessage(context.Background(), msg)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Verify the agent ID was injected
	if int(receivedBody["agentid"].(float64)) != 1000001 {
		t.Errorf("agentid = %v, want 1000001", receivedBody["agentid"])
	}
	if receivedBody["touser"] != "user123" {
		t.Errorf("touser = %v, want user123", receivedBody["touser"])
	}
}

func TestSendMessage_APIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"errcode": 45009,
			"errmsg":  "api freq out of limit",
		})
	}))
	defer server.Close()

	client := newTestClientWithServer(server)
	client.token = "valid-token"
	client.tokenExpiry = time.Now().Add(1 * time.Hour)

	err := client.SendMessage(context.Background(), &SendMessageRequest{
		ToUser:  "user1",
		MsgType: "text",
		Text:    &TextContent{Content: "hi"},
	})
	if err == nil {
		t.Fatal("expected error for rate limit, got nil")
	}
	if !strings.Contains(err.Error(), "api freq out of limit") {
		t.Errorf("error = %q, want it to contain 'api freq out of limit'", err.Error())
	}
}

func TestSendTextMessage_Success(t *testing.T) {
	var receivedBody map[string]interface{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" {
			_ = json.NewDecoder(r.Body).Decode(&receivedBody)
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"errcode": 0, "errmsg": "ok"})
	}))
	defer server.Close()

	client := newTestClientWithServer(server)
	client.token = "valid-token"
	client.tokenExpiry = time.Now().Add(1 * time.Hour)

	err := client.SendTextMessage(context.Background(), "user456", "Test content")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if receivedBody["msgtype"] != "text" {
		t.Errorf("msgtype = %v, want text", receivedBody["msgtype"])
	}
	text := receivedBody["text"].(map[string]interface{})
	if text["content"] != "Test content" {
		t.Errorf("content = %v, want 'Test content'", text["content"])
	}
}

func TestSendMarkdownMessage_Success(t *testing.T) {
	var receivedBody map[string]interface{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" {
			_ = json.NewDecoder(r.Body).Decode(&receivedBody)
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"errcode": 0, "errmsg": "ok"})
	}))
	defer server.Close()

	client := newTestClientWithServer(server)
	client.token = "valid-token"
	client.tokenExpiry = time.Now().Add(1 * time.Hour)

	err := client.SendMarkdownMessage(context.Background(), "user789", "**bold**")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if receivedBody["msgtype"] != "markdown" {
		t.Errorf("msgtype = %v, want markdown", receivedBody["msgtype"])
	}
	md := receivedBody["markdown"].(map[string]interface{})
	if md["content"] != "**bold**" {
		t.Errorf("content = %v, want '**bold**'", md["content"])
	}
}

func TestSendTextCard_Success(t *testing.T) {
	var receivedBody map[string]interface{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" {
			_ = json.NewDecoder(r.Body).Decode(&receivedBody)
		}
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"errcode": 0, "errmsg": "ok"})
	}))
	defer server.Close()

	client := newTestClientWithServer(server)
	client.token = "valid-token"
	client.tokenExpiry = time.Now().Add(1 * time.Hour)

	err := client.SendTextCard(context.Background(), "user111", &TextCardContent{
		Title:       "Card Title",
		Description: "Card Desc",
		URL:         "https://example.com",
		BtnTxt:      "Go",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if receivedBody["msgtype"] != "textcard" {
		t.Errorf("msgtype = %v, want textcard", receivedBody["msgtype"])
	}
	tc := receivedBody["textcard"].(map[string]interface{})
	if tc["title"] != "Card Title" {
		t.Errorf("title = %v, want 'Card Title'", tc["title"])
	}
	if tc["url"] != "https://example.com" {
		t.Errorf("url = %v, want 'https://example.com'", tc["url"])
	}
}

// ---------------------------------------------------------------------------
// checkResponse
// ---------------------------------------------------------------------------

func TestCheckResponse_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"errcode": 0, "errmsg": "ok"})
	}))
	defer server.Close()

	client := &Client{httpClient: server.Client()}
	resp, _ := client.httpClient.Get(server.URL)
	if err := client.checkResponse(resp); err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestCheckResponse_Error(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"errcode": 40001,
			"errmsg":  "invalid credential",
		})
	}))
	defer server.Close()

	client := &Client{httpClient: server.Client()}
	resp, _ := client.httpClient.Get(server.URL)
	err := client.checkResponse(resp)
	if err == nil {
		t.Fatal("expected error for invalid credential")
	}
	if !strings.Contains(err.Error(), "40001") {
		t.Errorf("error = %q, want it to contain '40001'", err.Error())
	}
}

func TestSendMessageRequest_OmitEmpty(t *testing.T) {
	msg := &SendMessageRequest{
		ToUser:  "user123",
		MsgType: "text",
		AgentID: 1000001,
		Text:    &TextContent{Content: "Hello!"},
	}

	data, err := json.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}

	var decoded map[string]interface{}
	_ = json.Unmarshal(data, &decoded)

	if _, ok := decoded["toparty"]; ok {
		t.Error("toparty should be omitted when empty")
	}
	if _, ok := decoded["totag"]; ok {
		t.Error("totag should be omitted when empty")
	}
	if _, ok := decoded["markdown"]; ok {
		t.Error("markdown should be omitted when nil")
	}
	if _, ok := decoded["textcard"]; ok {
		t.Error("textcard should be omitted when nil")
	}
}
