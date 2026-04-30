package feishu

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// rewriteTransport redirects all requests to a test server regardless of the
// original URL. It preserves the request path and query string so tests can
// assert on them.
type rewriteTransport struct {
	Base http.RoundTripper
	URL  string // test-server base URL
}

func (t *rewriteTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	// Rewrite the scheme+host but keep path+query.
	req.URL.Scheme = "http"
	req.URL.Host = strings.TrimPrefix(t.URL, "http://")
	return t.Base.RoundTrip(req)
}

// newTestClient creates a Client wired to the given test server.
func newTestClient(ts *httptest.Server) *Client {
	c := NewClient("test-app-id", "test-app-secret")
	c.httpClient = &http.Client{
		Timeout: 5 * time.Second,
		Transport: &rewriteTransport{
			Base: http.DefaultTransport,
			URL:  ts.URL,
		},
	}
	return c
}

// tokenHandler returns a handler that responds with a valid tenant access token.
func tokenHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"code":                0,
			"msg":                 "ok",
			"tenant_access_token": "t-test-token-123",
			"expire":             7200,
		})
	}
}

// successHandler returns a handler that responds with code=0.
func successHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"code": 0,
			"msg":  "success",
		})
	}
}

// ---------- Tests ----------

func TestNewClient(t *testing.T) {
	c := NewClient("my-app", "my-secret")
	if c.appID != "my-app" {
		t.Errorf("appID = %q, want %q", c.appID, "my-app")
	}
	if c.appSecret != "my-secret" {
		t.Errorf("appSecret = %q, want %q", c.appSecret, "my-secret")
	}
	if c.httpClient == nil {
		t.Fatal("httpClient is nil")
	}
	if c.token != "" {
		t.Errorf("token should be empty, got %q", c.token)
	}
}

func TestGetTenantAccessToken_Success(t *testing.T) {
	var reqBody map[string]string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &reqBody)
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"code":                0,
			"msg":                 "ok",
			"tenant_access_token": "t-fresh-token",
			"expire":             7200,
		})
	}))
	defer ts.Close()

	c := newTestClient(ts)
	token, err := c.GetTenantAccessToken(context.Background())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if token != "t-fresh-token" {
		t.Errorf("token = %q, want %q", token, "t-fresh-token")
	}
	// Verify the request body sent the correct credentials.
	if reqBody["app_id"] != "test-app-id" {
		t.Errorf("app_id = %q, want %q", reqBody["app_id"], "test-app-id")
	}
	if reqBody["app_secret"] != "test-app-secret" {
		t.Errorf("app_secret = %q, want %q", reqBody["app_secret"], "test-app-secret")
	}
}

func TestGetTenantAccessToken_Cached(t *testing.T) {
	var callCount int32
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&callCount, 1)
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"code":                0,
			"msg":                 "ok",
			"tenant_access_token": "t-cached-token",
			"expire":             7200,
		})
	}))
	defer ts.Close()

	c := newTestClient(ts)
	ctx := context.Background()

	// First call — hits the server.
	tok1, err := c.GetTenantAccessToken(ctx)
	if err != nil {
		t.Fatalf("first call error: %v", err)
	}

	// Second call — should use cache.
	tok2, err := c.GetTenantAccessToken(ctx)
	if err != nil {
		t.Fatalf("second call error: %v", err)
	}

	if tok1 != tok2 {
		t.Errorf("tokens differ: %q vs %q", tok1, tok2)
	}
	if count := atomic.LoadInt32(&callCount); count != 1 {
		t.Errorf("server called %d times, want 1 (cached)", count)
	}
}

func TestGetTenantAccessToken_Error(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"code": 99991,
			"msg":  "invalid app_id or app_secret",
		})
	}))
	defer ts.Close()

	c := newTestClient(ts)
	_, err := c.GetTenantAccessToken(context.Background())
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	if !strings.Contains(err.Error(), "invalid app_id or app_secret") {
		t.Errorf("error message = %q, want it to contain credential error", err.Error())
	}
	if !strings.Contains(err.Error(), "99991") {
		t.Errorf("error message = %q, want it to contain error code 99991", err.Error())
	}
}

func TestSendMessage_Success(t *testing.T) {
	var capturedPath string
	var capturedAuth string
	var capturedBody map[string]string

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/auth/") {
			tokenHandler()(w, r)
			return
		}
		capturedPath = r.URL.RequestURI()
		capturedAuth = r.Header.Get("Authorization")
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &capturedBody)
		successHandler()(w, r)
	}))
	defer ts.Close()

	c := newTestClient(ts)
	err := c.SendMessage(context.Background(), "chat_id", "oc_abc123", "text", `{"text":"hello"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Verify path includes receive_id_type query parameter.
	if !strings.Contains(capturedPath, "/im/v1/messages") {
		t.Errorf("path = %q, want to contain /im/v1/messages", capturedPath)
	}
	if !strings.Contains(capturedPath, "receive_id_type=chat_id") {
		t.Errorf("path = %q, want receive_id_type=chat_id", capturedPath)
	}
	// Verify auth header.
	if capturedAuth != "Bearer t-test-token-123" {
		t.Errorf("Authorization = %q, want %q", capturedAuth, "Bearer t-test-token-123")
	}
	// Verify body fields.
	if capturedBody["receive_id"] != "oc_abc123" {
		t.Errorf("receive_id = %q, want %q", capturedBody["receive_id"], "oc_abc123")
	}
	if capturedBody["msg_type"] != "text" {
		t.Errorf("msg_type = %q, want %q", capturedBody["msg_type"], "text")
	}
}

func TestReplyMessage_Success(t *testing.T) {
	var capturedPath string
	var capturedBody map[string]string

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/auth/") {
			tokenHandler()(w, r)
			return
		}
		capturedPath = r.URL.Path
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &capturedBody)
		successHandler()(w, r)
	}))
	defer ts.Close()

	c := newTestClient(ts)
	err := c.ReplyMessage(context.Background(), "om_msg123", "text", `{"text":"reply"}`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	expectedPath := "/open-apis/im/v1/messages/om_msg123/reply"
	if capturedPath != expectedPath {
		t.Errorf("path = %q, want %q", capturedPath, expectedPath)
	}
	if capturedBody["msg_type"] != "text" {
		t.Errorf("msg_type = %q, want %q", capturedBody["msg_type"], "text")
	}
	if capturedBody["content"] != `{"text":"reply"}` {
		t.Errorf("content = %q, want %q", capturedBody["content"], `{"text":"reply"}`)
	}
}

func TestSendCard_Success(t *testing.T) {
	var capturedBody map[string]string

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/auth/") {
			tokenHandler()(w, r)
			return
		}
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &capturedBody)
		successHandler()(w, r)
	}))
	defer ts.Close()

	c := newTestClient(ts)
	card := NewCardBuilder().SetHeader("Test", "blue").Build()
	err := c.SendCard(context.Background(), "chat_id", "oc_abc", card)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if capturedBody["msg_type"] != "interactive" {
		t.Errorf("msg_type = %q, want %q", capturedBody["msg_type"], "interactive")
	}
	// Content should be a JSON-encoded card.
	if capturedBody["content"] == "" {
		t.Error("content is empty, want JSON-encoded card")
	}
	// Verify the card content is valid JSON containing the header.
	var parsedCard Card
	if err := json.Unmarshal([]byte(capturedBody["content"]), &parsedCard); err != nil {
		t.Fatalf("content is not valid card JSON: %v", err)
	}
	if parsedCard.Header == nil || parsedCard.Header.Title.Content != "Test" {
		t.Error("card header title not found in content")
	}
}

func TestUpdateCard_Success(t *testing.T) {
	var capturedPath string
	var capturedAuth string
	var capturedBody map[string]interface{}

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/auth/") {
			tokenHandler()(w, r)
			return
		}
		capturedPath = r.URL.Path
		capturedAuth = r.Header.Get("Authorization")
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &capturedBody)
		successHandler()(w, r)
	}))
	defer ts.Close()

	c := newTestClient(ts)
	card := NewCardBuilder().SetHeader("Updated", "green").Build()
	err := c.UpdateCard(context.Background(), "card-token-xyz", card)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	expectedPath := "/open-apis/interactive/v1/card/update"
	if capturedPath != expectedPath {
		t.Errorf("path = %q, want %q", capturedPath, expectedPath)
	}
	if capturedAuth != "Bearer t-test-token-123" {
		t.Errorf("Authorization = %q, want Bearer token", capturedAuth)
	}
	if capturedBody["token"] != "card-token-xyz" {
		t.Errorf("token = %v, want %q", capturedBody["token"], "card-token-xyz")
	}
	if capturedBody["card"] == nil {
		t.Error("card field is nil in request body")
	}
}

func TestPatchCard_Success(t *testing.T) {
	var capturedPath string
	var capturedMethod string
	var capturedBody map[string]string

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/auth/") {
			tokenHandler()(w, r)
			return
		}
		capturedPath = r.URL.Path
		capturedMethod = r.Method
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &capturedBody)
		successHandler()(w, r)
	}))
	defer ts.Close()

	c := newTestClient(ts)
	card := NewCardBuilder().SetHeader("Patched", "orange").Build()
	err := c.PatchCard(context.Background(), "om_msg456", card)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if capturedMethod != "PATCH" {
		t.Errorf("method = %q, want PATCH", capturedMethod)
	}
	expectedPath := "/open-apis/im/v1/messages/om_msg456"
	if capturedPath != expectedPath {
		t.Errorf("path = %q, want %q", capturedPath, expectedPath)
	}
	// Body should have "content" key with JSON card string.
	if capturedBody["content"] == "" {
		t.Error("content is empty in patch body")
	}
}

func TestCheckResponse_APIError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/auth/") {
			tokenHandler()(w, r)
			return
		}
		// Return an API-level error.
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"code": 230001,
			"msg":  "bot not in chat",
		})
	}))
	defer ts.Close()

	c := newTestClient(ts)
	err := c.SendMessage(context.Background(), "chat_id", "oc_xxx", "text", `{"text":"hi"}`)
	if err == nil {
		t.Fatal("expected error, got nil")
	}
	// Verify the error message follows the format: "feishu error: <msg> (code=<code>)"
	if !strings.Contains(err.Error(), "bot not in chat") {
		t.Errorf("error = %q, want it to contain %q", err.Error(), "bot not in chat")
	}
	if !strings.Contains(err.Error(), "230001") {
		t.Errorf("error = %q, want it to contain error code", err.Error())
	}
}
