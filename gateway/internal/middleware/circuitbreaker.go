package middleware

import (
	"fmt"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/sony/gobreaker/v2"
)

// CircuitBreaker wraps sony/gobreaker for use as Gin middleware.
type CircuitBreaker struct {
	cb *gobreaker.CircuitBreaker[interface{}]
}

// NewCircuitBreaker creates a new circuit breaker with sensible defaults.
func NewCircuitBreaker() *CircuitBreaker {
	return NewCircuitBreakerWithName("gateway")
}

// NewCircuitBreakerWithName creates a new circuit breaker with the given name.
func NewCircuitBreakerWithName(name string) *CircuitBreaker {
	settings := gobreaker.Settings{
		Name:        name,
		MaxRequests: 3,                // Allow 3 requests in half-open state
		Interval:    10 * time.Second, // Clear counts after 10s
		Timeout:     30 * time.Second, // Stay open for 30s before trying half-open
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			// Trip if failure rate > 50% with at least 5 requests
			return counts.Requests >= 5 && float64(counts.TotalFailures)/float64(counts.Requests) > 0.5
		},
		OnStateChange: func(name string, from, to gobreaker.State) {
			// Could log state changes here
		},
	}

	return &CircuitBreaker{
		cb: gobreaker.NewCircuitBreaker[interface{}](settings),
	}
}

// Execute runs a function through the circuit breaker.
func (cb *CircuitBreaker) Execute(fn func() error) error {
	_, err := cb.cb.Execute(func() (interface{}, error) {
		return nil, fn()
	})
	return err
}

// State returns the current state of the circuit breaker.
func (cb *CircuitBreaker) State() gobreaker.State {
	return cb.cb.State()
}

// Middleware returns a Gin middleware that applies circuit breaking.
// This middleware wraps the entire request handling inside the circuit breaker Execute callback.
func (cb *CircuitBreaker) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		_, err := cb.cb.Execute(func() (interface{}, error) {
			c.Next()
			if c.Writer.Status() >= 500 {
				return nil, &serviceError{status: c.Writer.Status()}
			}
			return nil, nil
		})
		if err != nil {
			if c.Writer.Written() {
				return
			}
			c.AbortWithStatusJSON(http.StatusServiceUnavailable, gin.H{
				"code":    503,
				"message": "service temporarily unavailable",
			})
		}
	}
}

type serviceError struct {
	status int
}

func (e *serviceError) Error() string {
	return fmt.Sprintf("service error: status %d", e.status)
}
