package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestNewRateLimiter(t *testing.T) {
	rl := NewRateLimiter(100, true)

	if rl.limiter == nil {
		t.Error("limiter should not be nil")
	}

	if !rl.enabled {
		t.Error("enabled should be true")
	}
}

func TestRateLimiter_Middleware_Enabled(t *testing.T) {
	rl := NewRateLimiter(100, true)

	router := gin.New()
	router.Use(rl.Middleware())
	router.GET("/test", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestRateLimiter_Middleware_Disabled(t *testing.T) {
	rl := NewRateLimiter(100, false)

	router := gin.New()
	router.Use(rl.Middleware())
	router.GET("/test", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	// Should pass immediately when disabled
	for i := 0; i < 10; i++ {
		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("request %d: status = %d, want %d", i, w.Code, http.StatusOK)
		}
	}
}

func TestNewIPRateLimiter(t *testing.T) {
	rl := NewIPRateLimiter(100, true)

	if rl.limiters == nil {
		t.Error("limiters map should not be nil")
	}

	if rl.rps != 100 {
		t.Errorf("rps = %d, want 100", rl.rps)
	}

	if !rl.enabled {
		t.Error("enabled should be true")
	}
}

func TestIPRateLimiter_GetLimiter(t *testing.T) {
	rl := NewIPRateLimiter(100, true)

	// Get limiter for first IP
	l1 := rl.getLimiter("192.168.1.1")
	if l1 == nil {
		t.Fatal("limiter should not be nil")
	}

	// Same IP should return same limiter
	l1Again := rl.getLimiter("192.168.1.1")
	if l1 != l1Again {
		t.Error("same IP should return same limiter instance")
	}

	// Different IP should return different limiter
	l2 := rl.getLimiter("192.168.1.2")
	if l1 == l2 {
		t.Error("different IPs should have different limiters")
	}
}

func TestIPRateLimiter_Middleware_Enabled(t *testing.T) {
	rl := NewIPRateLimiter(100, true)

	router := gin.New()
	router.Use(rl.Middleware())
	router.GET("/test", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	req.RemoteAddr = "192.168.1.1:12345"
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
}

func TestIPRateLimiter_Middleware_Disabled(t *testing.T) {
	rl := NewIPRateLimiter(100, false)

	router := gin.New()
	router.Use(rl.Middleware())
	router.GET("/test", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	// Should pass immediately when disabled
	for i := 0; i < 10; i++ {
		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("request %d: status = %d, want %d", i, w.Code, http.StatusOK)
		}
	}
}

func TestRateLimitExceeded(t *testing.T) {
	router := gin.New()
	router.GET("/limited", RateLimitExceeded())

	req := httptest.NewRequest(http.MethodGet, "/limited", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusTooManyRequests {
		t.Errorf("status = %d, want %d", w.Code, http.StatusTooManyRequests)
	}

	// Check response body
	body := w.Body.String()
	if body == "" {
		t.Error("response body should not be empty")
	}
}

func TestIPRateLimiter_ConcurrentAccess(t *testing.T) {
	rl := NewIPRateLimiter(100, true)

	// Simulate concurrent access from multiple goroutines
	done := make(chan bool)
	for i := 0; i < 10; i++ {
		go func(ip string) {
			for j := 0; j < 10; j++ {
				_ = rl.getLimiter(ip)
			}
			done <- true
		}("192.168.1." + string(rune('0'+i)))
	}

	// Wait for all goroutines
	for i := 0; i < 10; i++ {
		<-done
	}

	// Should have created 10 limiters
	if len(rl.limiters) != 10 {
		t.Errorf("limiters count = %d, want 10", len(rl.limiters))
	}
}
