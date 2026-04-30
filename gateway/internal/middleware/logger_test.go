package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"go.uber.org/zap/zaptest/observer"
)

func init() {
	gin.SetMode(gin.TestMode)
}

func TestLogger_InfoLog(t *testing.T) {
	core, recorded := observer.New(zap.InfoLevel)
	logger := zap.New(core)

	router := gin.New()
	router.Use(Logger(logger))
	router.GET("/test", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	req.Header.Set("User-Agent", "test-agent")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	// Check log was recorded
	logs := recorded.All()
	if len(logs) == 0 {
		t.Fatal("expected log entry, got none")
	}

	entry := logs[0]
	if entry.Message != "Request completed" {
		t.Errorf("message = %q, want %q", entry.Message, "Request completed")
	}

	// Check fields using ContextMap
	contextMap := entry.ContextMap()

	if methodVal, ok := contextMap["method"]; !ok || methodVal != "GET" {
		t.Errorf("method = %v, want GET", contextMap["method"])
	}

	if pathVal, ok := contextMap["path"]; !ok || pathVal != "/test" {
		t.Errorf("path = %v, want /test", contextMap["path"])
	}
}

func TestLogger_WarnLogFor4xx(t *testing.T) {
	core, recorded := observer.New(zap.WarnLevel)
	logger := zap.New(core)

	router := gin.New()
	router.Use(Logger(logger))
	router.GET("/notfound", func(c *gin.Context) {
		c.Status(http.StatusNotFound)
	})

	req := httptest.NewRequest(http.MethodGet, "/notfound", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	logs := recorded.All()
	if len(logs) == 0 {
		t.Fatal("expected warn log entry, got none")
	}

	if logs[0].Message != "Client error" {
		t.Errorf("message = %q, want %q", logs[0].Message, "Client error")
	}
}

func TestLogger_ErrorLogFor5xx(t *testing.T) {
	core, recorded := observer.New(zap.ErrorLevel)
	logger := zap.New(core)

	router := gin.New()
	router.Use(Logger(logger))
	router.GET("/error", func(c *gin.Context) {
		c.Status(http.StatusInternalServerError)
	})

	req := httptest.NewRequest(http.MethodGet, "/error", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	logs := recorded.All()
	if len(logs) == 0 {
		t.Fatal("expected error log entry, got none")
	}

	if logs[0].Message != "Server error" {
		t.Errorf("message = %q, want %q", logs[0].Message, "Server error")
	}
}

func TestLogger_WithTraceID(t *testing.T) {
	core, recorded := observer.New(zap.InfoLevel)
	logger := zap.New(core)

	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set("trace_id", "test-trace-123")
		c.Next()
	})
	router.Use(Logger(logger))
	router.GET("/traced", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/traced", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	logs := recorded.All()
	if len(logs) == 0 {
		t.Fatal("expected log entry, got none")
	}

	// Check trace_id field
	found := false
	for _, f := range logs[0].Context {
		if f.Key == "trace_id" && f.String == "test-trace-123" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected trace_id field in log")
	}
}

func TestRequestID_GeneratesID(t *testing.T) {
	router := gin.New()
	router.Use(RequestID())
	router.GET("/test", func(c *gin.Context) {
		traceID, exists := c.Get("trace_id")
		if !exists {
			t.Error("trace_id not set in context")
			return
		}
		if traceID == "" {
			t.Error("trace_id is empty")
		}
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	// Check response header
	if w.Header().Get("X-Trace-ID") == "" {
		t.Error("X-Trace-ID header not set")
	}
}

func TestRequestID_UsesExistingTraceID(t *testing.T) {
	router := gin.New()
	router.Use(RequestID())
	router.GET("/test", func(c *gin.Context) {
		traceID := c.GetString("trace_id")
		if traceID != "existing-trace-id" {
			t.Errorf("trace_id = %q, want existing-trace-id", traceID)
		}
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	req.Header.Set("X-Trace-ID", "existing-trace-id")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)
}

func TestRequestID_UsesRequestIDHeader(t *testing.T) {
	router := gin.New()
	router.Use(RequestID())
	router.GET("/test", func(c *gin.Context) {
		traceID := c.GetString("trace_id")
		if traceID != "request-id-123" {
			t.Errorf("trace_id = %q, want request-id-123", traceID)
		}
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	req.Header.Set("X-Request-ID", "request-id-123")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)
}

func TestGenerateTraceID(t *testing.T) {
	id1 := generateTraceID()
	id2 := generateTraceID()

	if id1 == "" {
		t.Error("generated trace ID is empty")
	}

	if id1 == id2 {
		t.Error("generated trace IDs should be unique")
	}

	// Check format: should have date prefix
	if len(id1) < 14 {
		t.Errorf("trace ID too short: %s", id1)
	}
}

func TestRandomString(t *testing.T) {
	s := randomString(8)
	if len(s) != 8 {
		t.Errorf("length = %d, want 8", len(s))
	}

	// Check characters are alphanumeric
	for _, c := range s {
		if !((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) {
			t.Errorf("invalid character in random string: %c", c)
		}
	}
}
