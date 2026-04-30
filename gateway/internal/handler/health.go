// Package handler provides HTTP handlers for the gateway.
package handler

import (
	"net/http"

	"github.com/Wisdoverse/project-cell/gateway/internal/client"
	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
)

// HealthHandler handles health check endpoints.
type HealthHandler struct {
	reqClient *client.RequirementClient
	logger    *zap.Logger
	version   string
}

// NewHealthHandler creates a new health handler.
func NewHealthHandler(reqClient *client.RequirementClient, logger *zap.Logger, version string) *HealthHandler {
	return &HealthHandler{
		reqClient: reqClient,
		logger:    logger,
		version:   version,
	}
}

// HealthResponse represents the health check response.
type HealthResponse struct {
	Status   string            `json:"status"`
	Version  string            `json:"version"`
	Services map[string]string `json:"services"`
}

// Health handles GET /health - basic liveness check.
func (h *HealthHandler) Health(c *gin.Context) {
	c.JSON(http.StatusOK, HealthResponse{
		Status:  "ok",
		Version: h.version,
	})
}

// Ready handles GET /ready - readiness check including dependencies.
func (h *HealthHandler) Ready(c *gin.Context) {
	services := make(map[string]string)

	// Check AI service (Python gRPC)
	aiStatus := "ok"
	if h.reqClient != nil {
		resp, err := h.reqClient.HealthCheck(c.Request.Context())
		if err != nil {
			aiStatus = "error: " + err.Error()
		} else if !resp.Healthy {
			aiStatus = "unhealthy"
		}
	} else {
		aiStatus = "not configured"
	}
	services["ai_service"] = aiStatus

	// Determine overall status
	status := "ok"
	httpStatus := http.StatusOK

	if aiStatus != "ok" {
		status = "degraded"
		// Don't fail readiness for AI service - gateway can still handle some requests
	}

	c.JSON(httpStatus, HealthResponse{
		Status:   status,
		Version:  h.version,
		Services: services,
	})
}
