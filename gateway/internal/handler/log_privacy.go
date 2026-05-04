package handler

import (
	"crypto/sha256"
	"fmt"
	"sort"

	"go.uber.org/zap"
)

func bytesFingerprintFields(name string, body []byte) []zap.Field {
	sum := sha256.Sum256(body)
	return []zap.Field{
		zap.Int(name+"_len", len(body)),
		zap.String(name+"_sha256", fmt.Sprintf("%x", sum)[:16]),
	}
}

func mapSummaryFields(name string, value map[string]interface{}) []zap.Field {
	keys := make([]string, 0, len(value))
	for key := range value {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	fields := []zap.Field{zap.Strings(name+"_keys", keys)}
	if action, ok := value["action"].(string); ok {
		fields = append(fields, zap.String(name+"_action", action))
	}
	return fields
}

func stringMapSummaryFields(name string, value map[string]string) []zap.Field {
	keys := make([]string, 0, len(value))
	for key := range value {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	fields := []zap.Field{zap.Strings(name+"_keys", keys)}
	if keyword := value["keyword"]; keyword != "" {
		fields = append(fields, zap.String("keyword_hash", shortLogHash(keyword)))
	}
	if reason := value["reason"]; reason != "" {
		fields = append(fields, zap.String("reason_hash", shortLogHash(reason)))
	}
	return fields
}
