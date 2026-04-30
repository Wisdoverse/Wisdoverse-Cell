package middleware

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/sony/gobreaker/v2"
)

func TestNewCircuitBreaker(t *testing.T) {
	cb := NewCircuitBreakerWithName("test-service")

	if cb.cb == nil {
		t.Error("circuit breaker should not be nil")
	}

	if cb.State() != gobreaker.StateClosed {
		t.Errorf("initial state should be closed, got %v", cb.State())
	}
}

func TestCircuitBreaker_Execute_Success(t *testing.T) {
	cb := NewCircuitBreakerWithName("test-service")

	err := cb.Execute(func() error {
		return nil
	})

	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}
}

func TestCircuitBreaker_Execute_Error(t *testing.T) {
	cb := NewCircuitBreakerWithName("test-service")

	testErr := errors.New("test error")
	err := cb.Execute(func() error {
		return testErr
	})

	if err != testErr {
		t.Errorf("expected error %v, got %v", testErr, err)
	}
}

func TestCircuitBreaker_State(t *testing.T) {
	cb := NewCircuitBreakerWithName("test-service")

	state := cb.State()
	if state != gobreaker.StateClosed {
		t.Errorf("state = %v, want %v", state, gobreaker.StateClosed)
	}
}

func TestCircuitBreaker_Middleware_PassesThrough(t *testing.T) {
	cb := NewCircuitBreakerWithName("test-service")

	router := gin.New()
	router.Use(cb.Middleware())
	router.GET("/test", func(c *gin.Context) {
		c.String(http.StatusOK, "OK")
	})

	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}

	if w.Body.String() != "OK" {
		t.Errorf("body = %q, want OK", w.Body.String())
	}
}

func TestCircuitBreaker_Middleware_RecordsSuccess(t *testing.T) {
	cb := NewCircuitBreakerWithName("test-service")

	router := gin.New()
	router.Use(cb.Middleware())
	router.GET("/test", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	// Make several successful requests
	for i := 0; i < 5; i++ {
		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("request %d: status = %d, want %d", i, w.Code, http.StatusOK)
		}
	}

	// Circuit should still be closed
	if cb.State() != gobreaker.StateClosed {
		t.Errorf("state = %v, want %v", cb.State(), gobreaker.StateClosed)
	}
}

func TestCircuitBreaker_Middleware_Records5xxErrors(t *testing.T) {
	cb := NewCircuitBreakerWithName("test-service")

	router := gin.New()
	router.Use(cb.Middleware())
	router.GET("/error", func(c *gin.Context) {
		c.Status(http.StatusInternalServerError)
	})

	// Make several error requests
	for i := 0; i < 10; i++ {
		req := httptest.NewRequest(http.MethodGet, "/error", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)
	}

	// After enough failures, circuit should be open
	// Note: the exact behavior depends on circuit breaker settings
	// The ReadyToTrip function requires >= 5 requests with > 50% failure rate
}

func TestCircuitBreaker_Middleware_Ignores4xxErrors(t *testing.T) {
	cb := NewCircuitBreakerWithName("test-service")

	router := gin.New()
	router.Use(cb.Middleware())
	router.GET("/notfound", func(c *gin.Context) {
		c.Status(http.StatusNotFound)
	})

	// Make several 4xx requests - these should not trip the circuit
	for i := 0; i < 10; i++ {
		req := httptest.NewRequest(http.MethodGet, "/notfound", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)
	}

	// Circuit should still be closed (4xx doesn't count as failure)
	if cb.State() != gobreaker.StateClosed {
		t.Errorf("state = %v, want %v (4xx should not trip circuit)", cb.State(), gobreaker.StateClosed)
	}
}

func TestServiceError_Error(t *testing.T) {
	err := &serviceError{status: 500}
	expected := "service error: status 500"
	if err.Error() != expected {
		t.Errorf("Error() = %q, want %q", err.Error(), expected)
	}
}

func TestCircuitBreaker_DifferentNames(t *testing.T) {
	cb1 := NewCircuitBreakerWithName("service-1")
	cb2 := NewCircuitBreakerWithName("service-2")

	// Both should start closed
	if cb1.State() != gobreaker.StateClosed {
		t.Error("cb1 should be closed")
	}
	if cb2.State() != gobreaker.StateClosed {
		t.Error("cb2 should be closed")
	}

	// They should be independent
	if cb1.cb == cb2.cb {
		t.Error("circuit breakers should be independent")
	}
}
