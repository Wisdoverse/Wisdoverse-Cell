package config

import (
	"os"
	"testing"
	"time"
)

func TestLoad_Defaults(t *testing.T) {
	// Clear any env vars that might interfere
	os.Unsetenv("GATEWAY_SERVER_PORT")
	os.Unsetenv("GATEWAY_GRPC_AI_SERVICE_ADDR")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("failed to load config: %v", err)
	}

	// Check server defaults
	if cfg.Server.Port != 8080 {
		t.Errorf("Server.Port = %d, want 8080", cfg.Server.Port)
	}

	if cfg.Server.ReadTimeout != 30*time.Second {
		t.Errorf("Server.ReadTimeout = %v, want 30s", cfg.Server.ReadTimeout)
	}

	if cfg.Server.WriteTimeout != 30*time.Second {
		t.Errorf("Server.WriteTimeout = %v, want 30s", cfg.Server.WriteTimeout)
	}

	if cfg.Server.Mode != "release" {
		t.Errorf("Server.Mode = %q, want release", cfg.Server.Mode)
	}

	// Check gRPC defaults
	if cfg.GRPC.AIServiceAddr != "localhost:50051" {
		t.Errorf("GRPC.AIServiceAddr = %q, want localhost:50051", cfg.GRPC.AIServiceAddr)
	}

	if cfg.GRPC.Timeout != 30*time.Second {
		t.Errorf("GRPC.Timeout = %v, want 30s", cfg.GRPC.Timeout)
	}

	if cfg.GRPC.MaxRetries != 3 {
		t.Errorf("GRPC.MaxRetries = %d, want 3", cfg.GRPC.MaxRetries)
	}

	// Check Redis defaults
	if cfg.Redis.Addr != "localhost:6379" {
		t.Errorf("Redis.Addr = %q, want localhost:6379", cfg.Redis.Addr)
	}

	if cfg.Redis.DB != 0 {
		t.Errorf("Redis.DB = %d, want 0", cfg.Redis.DB)
	}

	// Check rate limit defaults
	if !cfg.RateLimit.Enabled {
		t.Error("RateLimit.Enabled should be true by default")
	}

	if cfg.RateLimit.RPS != 100 {
		t.Errorf("RateLimit.RPS = %d, want 100", cfg.RateLimit.RPS)
	}

	if cfg.RateLimit.BurstSize != 200 {
		t.Errorf("RateLimit.BurstSize = %d, want 200", cfg.RateLimit.BurstSize)
	}

	// Check log defaults
	if cfg.Log.Level != "info" {
		t.Errorf("Log.Level = %q, want info", cfg.Log.Level)
	}

	if cfg.Log.Format != "json" {
		t.Errorf("Log.Format = %q, want json", cfg.Log.Format)
	}

	// Check feishu defaults
	if !cfg.Feishu.VerifySignature {
		t.Error("Feishu.VerifySignature should be true by default")
	}

	if cfg.Feishu.SessionTimeout != 300 {
		t.Errorf("Feishu.SessionTimeout = %d, want 300", cfg.Feishu.SessionTimeout)
	}
}

func TestLoad_EnvOverride(t *testing.T) {
	// Set some env vars
	os.Setenv("GATEWAY_SERVER_PORT", "9090")
	os.Setenv("GATEWAY_LOG_LEVEL", "debug")
	defer func() {
		os.Unsetenv("GATEWAY_SERVER_PORT")
		os.Unsetenv("GATEWAY_LOG_LEVEL")
	}()

	cfg, err := Load()
	if err != nil {
		t.Fatalf("failed to load config: %v", err)
	}

	if cfg.Server.Port != 9090 {
		t.Errorf("Server.Port = %d, want 9090", cfg.Server.Port)
	}

	if cfg.Log.Level != "debug" {
		t.Errorf("Log.Level = %q, want debug", cfg.Log.Level)
	}
}

func TestServerConfig_Struct(t *testing.T) {
	cfg := ServerConfig{
		Port:         8080,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		Mode:         "debug",
	}

	if cfg.Port != 8080 {
		t.Errorf("Port = %d, want 8080", cfg.Port)
	}

	if cfg.Mode != "debug" {
		t.Errorf("Mode = %q, want debug", cfg.Mode)
	}
}

func TestGRPCConfig_Struct(t *testing.T) {
	cfg := GRPCConfig{
		AIServiceAddr: "ai-service:50051",
		Timeout:       10 * time.Second,
		MaxRetries:    5,
	}

	if cfg.AIServiceAddr != "ai-service:50051" {
		t.Errorf("AIServiceAddr = %q, want ai-service:50051", cfg.AIServiceAddr)
	}

	if cfg.MaxRetries != 5 {
		t.Errorf("MaxRetries = %d, want 5", cfg.MaxRetries)
	}
}

func TestRedisConfig_Struct(t *testing.T) {
	cfg := RedisConfig{
		Addr:     "redis:6379",
		Password: "secret",
		DB:       1,
	}

	if cfg.Addr != "redis:6379" {
		t.Errorf("Addr = %q, want redis:6379", cfg.Addr)
	}

	if cfg.Password != "secret" {
		t.Errorf("Password = %q, want secret", cfg.Password)
	}

	if cfg.DB != 1 {
		t.Errorf("DB = %d, want 1", cfg.DB)
	}
}

func TestFeishuConfig_Struct(t *testing.T) {
	cfg := FeishuConfig{
		AppID:             "cli_xxx",
		AppSecret:         "secret",
		VerificationToken: "token",
		EncryptKey:        "key",
		VerifySignature:   true,
		MonitoredChatIDs:  []string{"oc_xxx", "oc_yyy"},
		SessionTimeout:    600,
	}

	if cfg.AppID != "cli_xxx" {
		t.Errorf("AppID = %q, want cli_xxx", cfg.AppID)
	}

	if len(cfg.MonitoredChatIDs) != 2 {
		t.Errorf("MonitoredChatIDs length = %d, want 2", len(cfg.MonitoredChatIDs))
	}
}

func TestWecomConfig_Struct(t *testing.T) {
	cfg := WecomConfig{
		CorpID:         "corp123",
		AgentID:        1000001,
		Secret:         "secret",
		Token:          "token",
		EncodingAESKey: "key43chars",
	}

	if cfg.CorpID != "corp123" {
		t.Errorf("CorpID = %q, want corp123", cfg.CorpID)
	}

	if cfg.AgentID != 1000001 {
		t.Errorf("AgentID = %d, want 1000001", cfg.AgentID)
	}
}

func TestRateLimitConfig_Struct(t *testing.T) {
	cfg := RateLimitConfig{
		Enabled:   true,
		RPS:       50,
		BurstSize: 100,
	}

	if !cfg.Enabled {
		t.Error("Enabled should be true")
	}

	if cfg.RPS != 50 {
		t.Errorf("RPS = %d, want 50", cfg.RPS)
	}

	if cfg.BurstSize != 100 {
		t.Errorf("BurstSize = %d, want 100", cfg.BurstSize)
	}
}

func TestLogConfig_Struct(t *testing.T) {
	cfg := LogConfig{
		Level:  "warn",
		Format: "console",
	}

	if cfg.Level != "warn" {
		t.Errorf("Level = %q, want warn", cfg.Level)
	}

	if cfg.Format != "console" {
		t.Errorf("Format = %q, want console", cfg.Format)
	}
}
