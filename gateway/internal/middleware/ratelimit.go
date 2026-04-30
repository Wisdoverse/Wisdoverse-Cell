// Package middleware provides HTTP middleware for the gateway.
package middleware

import (
	"net/http"
	"sync"

	"github.com/gin-gonic/gin"
	"go.uber.org/ratelimit"
)

// RateLimiter wraps uber's ratelimit for use as Gin middleware.
type RateLimiter struct {
	limiter ratelimit.Limiter
	enabled bool
}

// NewRateLimiter creates a new rate limiter.
func NewRateLimiter(rps int, enabled bool) *RateLimiter {
	return &RateLimiter{
		limiter: ratelimit.New(rps),
		enabled: enabled,
	}
}

// Middleware returns a Gin middleware that applies rate limiting.
func (r *RateLimiter) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		if !r.enabled {
			c.Next()
			return
		}

		// Take a token (blocks if rate exceeded)
		r.limiter.Take()
		c.Next()
	}
}

// IPRateLimiter provides per-IP rate limiting.
type IPRateLimiter struct {
	limiters map[string]ratelimit.Limiter
	mu       sync.RWMutex
	rps      int
	enabled  bool
}

// NewIPRateLimiter creates a new per-IP rate limiter.
func NewIPRateLimiter(rps int, enabled bool) *IPRateLimiter {
	return &IPRateLimiter{
		limiters: make(map[string]ratelimit.Limiter),
		rps:      rps,
		enabled:  enabled,
	}
}

// getLimiter returns the rate limiter for a given IP.
func (r *IPRateLimiter) getLimiter(ip string) ratelimit.Limiter {
	r.mu.RLock()
	limiter, exists := r.limiters[ip]
	r.mu.RUnlock()

	if exists {
		return limiter
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	// Double-check after acquiring write lock
	if limiter, exists = r.limiters[ip]; exists {
		return limiter
	}

	limiter = ratelimit.New(r.rps)
	r.limiters[ip] = limiter
	return limiter
}

// Middleware returns a Gin middleware that applies per-IP rate limiting.
func (r *IPRateLimiter) Middleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		if !r.enabled {
			c.Next()
			return
		}

		ip := c.ClientIP()
		limiter := r.getLimiter(ip)
		limiter.Take()
		c.Next()
	}
}

// RateLimitExceeded returns a handler for when rate limit is exceeded.
func RateLimitExceeded() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
			"code":    429,
			"message": "rate limit exceeded",
		})
	}
}
