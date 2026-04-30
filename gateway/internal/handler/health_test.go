package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

func init() {
	gin.SetMode(gin.TestMode)
}

func TestHealthHandler_Health(t *testing.T) {
	logger := zap.NewNop()
	h := NewHealthHandler(nil, logger, "1.0.0-test")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/health", nil)

	h.Health(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	var resp HealthResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if resp.Status != "ok" {
		t.Errorf("status = %q, want %q", resp.Status, "ok")
	}

	if resp.Version != "1.0.0-test" {
		t.Errorf("version = %q, want %q", resp.Version, "1.0.0-test")
	}
}

func TestHealthHandler_Ready_NoClient(t *testing.T) {
	logger := zap.NewNop()
	h := NewHealthHandler(nil, logger, "1.0.0-test")

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/ready", nil)

	h.Ready(c)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	var resp HealthResponse
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to unmarshal response: %v", err)
	}

	if resp.Services["ai_service"] != "not configured" {
		t.Errorf("ai_service = %q, want %q", resp.Services["ai_service"], "not configured")
	}
}

func TestHealthResponse_JSONStructure(t *testing.T) {
	resp := HealthResponse{
		Status:  "ok",
		Version: "1.0.0",
		Services: map[string]string{
			"ai_service": "ok",
			"redis":      "ok",
		},
	}

	data, err := json.Marshal(resp)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	if decoded["status"] != "ok" {
		t.Errorf("status = %v, want ok", decoded["status"])
	}

	if decoded["version"] != "1.0.0" {
		t.Errorf("version = %v, want 1.0.0", decoded["version"])
	}

	services := decoded["services"].(map[string]interface{})
	if services["ai_service"] != "ok" {
		t.Errorf("ai_service = %v, want ok", services["ai_service"])
	}
}
