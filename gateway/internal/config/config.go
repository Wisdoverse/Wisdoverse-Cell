// Package config provides configuration management for the gateway service.
package config

import (
	"strings"
	"time"

	"github.com/spf13/viper"
)

// Config holds all configuration for the gateway.
type Config struct {
	Server   ServerConfig
	GRPC     GRPCConfig
	Redis    RedisConfig
	Feishu   FeishuConfig
	Wecom    WecomConfig
	RateLimit RateLimitConfig
	Log      LogConfig
}

// ServerConfig holds HTTP server settings.
type ServerConfig struct {
	Port         int           `mapstructure:"port"`
	ReadTimeout  time.Duration `mapstructure:"read_timeout"`
	WriteTimeout time.Duration `mapstructure:"write_timeout"`
	Mode         string        `mapstructure:"mode"` // debug, release, test
}

// GRPCConfig holds gRPC client settings.
type GRPCConfig struct {
	AIServiceAddr string        `mapstructure:"ai_service_addr"`
	Timeout       time.Duration `mapstructure:"timeout"`
	MaxRetries    int           `mapstructure:"max_retries"`
}

// RedisConfig holds Redis connection settings.
type RedisConfig struct {
	Addr     string `mapstructure:"addr"`
	Password string `mapstructure:"password"`
	DB       int    `mapstructure:"db"`
}

// FeishuConfig holds Feishu integration settings.
type FeishuConfig struct {
	AppID              string   `mapstructure:"app_id"`
	AppSecret          string   `mapstructure:"app_secret"`
	VerificationToken  string   `mapstructure:"verification_token"`
	EncryptKey         string   `mapstructure:"encrypt_key"`
	VerifySignature    bool     `mapstructure:"verify_signature"`
	MonitoredChatIDs   []string `mapstructure:"monitored_chat_ids"`
	SessionTimeout     int      `mapstructure:"session_timeout"`    // seconds
	ChatAgentAddr      string   `mapstructure:"chat_agent_addr"`
	PMAgentAddr        string   `mapstructure:"pjm_agent_addr"`
	InternalServiceKey string   `mapstructure:"internal_service_key"`
}

// WecomConfig holds WeCom integration settings.
type WecomConfig struct {
	CorpID         string `mapstructure:"corp_id"`
	AgentID        int    `mapstructure:"agent_id"`
	Secret         string `mapstructure:"secret"`
	Token          string `mapstructure:"token"`
	EncodingAESKey string `mapstructure:"encoding_aes_key"`
}

// RateLimitConfig holds rate limiting settings.
type RateLimitConfig struct {
	Enabled    bool `mapstructure:"enabled"`
	RPS        int  `mapstructure:"rps"`         // requests per second
	BurstSize  int  `mapstructure:"burst_size"`
}

// LogConfig holds logging settings.
type LogConfig struct {
	Level  string `mapstructure:"level"` // debug, info, warn, error
	Format string `mapstructure:"format"` // json, console
}

// Load reads configuration from environment and config files.
func Load() (*Config, error) {
	v := viper.New()

	// Set defaults
	setDefaults(v)

	// Read from environment
	v.SetEnvPrefix("GATEWAY")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()

	// Read from config file if exists
	v.SetConfigName("config")
	v.SetConfigType("yaml")
	v.AddConfigPath(".")
	v.AddConfigPath("./config")
	v.AddConfigPath("/etc/gateway")

	if err := v.ReadInConfig(); err != nil {
		// Config file not found is OK, we use env vars
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, err
		}
	}

	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, err
	}

	return &cfg, nil
}

func setDefaults(v *viper.Viper) {
	// Server
	v.SetDefault("server.port", 8080)
	v.SetDefault("server.read_timeout", 30*time.Second)
	v.SetDefault("server.write_timeout", 30*time.Second)
	v.SetDefault("server.mode", "release")

	// gRPC
	v.SetDefault("grpc.ai_service_addr", "localhost:50051")
	v.SetDefault("grpc.timeout", 30*time.Second)
	v.SetDefault("grpc.max_retries", 3)

	// Redis
	v.SetDefault("redis.addr", "localhost:6379")
	v.SetDefault("redis.password", "")
	v.SetDefault("redis.db", 0)

	// Feishu
	v.SetDefault("feishu.verify_signature", true)
	v.SetDefault("feishu.session_timeout", 300)
	v.SetDefault("feishu.chat_agent_addr", "")
	v.SetDefault("feishu.pjm_agent_addr", "")
	v.SetDefault("feishu.internal_service_key", "")

	// Rate limit
	v.SetDefault("ratelimit.enabled", true)
	v.SetDefault("ratelimit.rps", 100)
	v.SetDefault("ratelimit.burst_size", 200)

	// Log
	v.SetDefault("log.level", "info")
	v.SetDefault("log.format", "json")
}
