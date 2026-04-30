// Package main is the entry point for the gateway service.
package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Wisdoverse/project-cell/gateway/internal/client"
	"github.com/Wisdoverse/project-cell/gateway/internal/config"
	"github.com/Wisdoverse/project-cell/gateway/internal/handler"
	"github.com/Wisdoverse/project-cell/gateway/internal/middleware"
	"github.com/Wisdoverse/project-cell/gateway/internal/service"
	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

const version = "0.1.0"

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to load config: %v\n", err)
		os.Exit(1)
	}

	// Initialize logger
	logger, err := initLogger(cfg.Log)
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to init logger: %v\n", err)
		os.Exit(1)
	}
	defer func() { _ = logger.Sync() }()

	logger.Info("starting gateway",
		zap.String("version", version),
		zap.Int("port", cfg.Server.Port),
		zap.String("grpc_addr", cfg.GRPC.AIServiceAddr),
	)

	// Initialize Redis client
	redisClient := redis.NewClient(&redis.Options{
		Addr:     cfg.Redis.Addr,
		Password: cfg.Redis.Password,
		DB:       cfg.Redis.DB,
	})
	defer redisClient.Close()

	// Test Redis connection
	if err := redisClient.Ping(context.Background()).Err(); err != nil {
		logger.Warn("redis connection failed, session features disabled", zap.Error(err))
	} else {
		logger.Info("redis connected", zap.String("addr", cfg.Redis.Addr))
	}

	// Initialize gRPC client for AI service
	reqClient, err := client.NewRequirementClient(
		cfg.GRPC.AIServiceAddr,
		cfg.GRPC.Timeout,
		logger,
	)
	if err != nil {
		logger.Error("failed to create requirement client", zap.Error(err))
		os.Exit(1)
	}
	defer reqClient.Close()

	// Initialize services
	matcher := service.NewMatcher()
	sessionMgr := service.NewSessionManager(redisClient, time.Duration(cfg.Feishu.SessionTimeout)*time.Second)
	dedup := service.NewDeduplicator(redisClient, 10*time.Second)

	// Set Gin mode
	gin.SetMode(cfg.Server.Mode)

	// Create router
	router := gin.New()

	// Global middleware
	router.Use(gin.Recovery())
	router.Use(middleware.RequestID())
	router.Use(middleware.Logger(logger))

	// Rate limiting
	if cfg.RateLimit.Enabled {
		rateLimiter := middleware.NewRateLimiter(cfg.RateLimit.RPS, true)
		router.Use(rateLimiter.Middleware())
	}

	// Health endpoints (no rate limiting)
	healthHandler := handler.NewHealthHandler(reqClient, logger, version)
	router.GET("/health", healthHandler.Health)
	router.GET("/ready", healthHandler.Ready)

	// API routes
	cb := middleware.NewCircuitBreaker()
	api := router.Group("/api")
	api.Use(cb.Middleware())
	{
		// Feishu webhook
		feishuHandler := handler.NewFeishuHandler(&cfg.Feishu, reqClient, matcher, sessionMgr, dedup, cfg.Feishu.ChatAgentAddr, cfg.Feishu.PMAgentAddr, logger)
		api.POST("/feishu/webhook", feishuHandler.Webhook)

		// WeChat Work webhook
		if cfg.Wecom.CorpID != "" {
			wecomHandler, err := handler.NewWecomHandler(&cfg.Wecom, reqClient, matcher, sessionMgr, dedup, logger)
			if err != nil {
				logger.Warn("failed to init wecom handler", zap.Error(err))
			} else {
				api.GET("/wecom/webhook", wecomHandler.Webhook)  // URL verification
				api.POST("/wecom/webhook", wecomHandler.Webhook) // Message callback
				logger.Info("wecom webhook enabled")
			}
		}
	}

	// Create HTTP server
	srv := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Server.Port),
		Handler:      router,
		ReadTimeout:  cfg.Server.ReadTimeout,
		WriteTimeout: cfg.Server.WriteTimeout,
	}

	// Start server in goroutine
	errCh := make(chan error, 1)
	go func() {
		logger.Info("server listening", zap.Int("port", cfg.Server.Port))
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
			return
		}
	}()

	// Wait for interrupt signal or server error
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	select {
	case <-quit:
	case err := <-errCh:
		logger.Error("server error", zap.Error(err))
	}

	logger.Info("shutting down server...")

	// Graceful shutdown with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		logger.Error("server forced to shutdown", zap.Error(err))
	}

	logger.Info("server stopped")
}

func initLogger(cfg config.LogConfig) (*zap.Logger, error) {
	var level zapcore.Level
	if err := level.UnmarshalText([]byte(cfg.Level)); err != nil {
		level = zapcore.InfoLevel
	}

	var zapCfg zap.Config
	if cfg.Format == "console" {
		zapCfg = zap.NewDevelopmentConfig()
	} else {
		zapCfg = zap.NewProductionConfig()
	}
	zapCfg.Level = zap.NewAtomicLevelAt(level)

	return zapCfg.Build()
}

