// Package feishu provides Feishu (Lark) integration utilities.
package feishu

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"fmt"
)

// VerifySignature verifies the Feishu webhook signature.
// Signature = sha256(timestamp + nonce + encrypt_key + body)
func VerifySignature(timestamp, nonce, encryptKey string, body []byte, signature string) bool {
	if encryptKey == "" {
		return false
	}

	data := fmt.Sprintf("%s%s%s%s", timestamp, nonce, encryptKey, string(body))
	hash := sha256.Sum256([]byte(data))
	expected := hex.EncodeToString(hash[:])

	return subtle.ConstantTimeCompare([]byte(expected), []byte(signature)) == 1
}

// DecryptMessage decrypts an encrypted Feishu message.
// For simplicity, we assume messages are not encrypted in this implementation.
// Full implementation would use AES-256-CBC decryption.
func DecryptMessage(encrypted string, encryptKey string) ([]byte, error) {
	// TODO: Implement AES decryption if needed
	return []byte(encrypted), nil
}
