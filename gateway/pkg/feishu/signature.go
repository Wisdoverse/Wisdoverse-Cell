// Package feishu provides Feishu (Lark) integration utilities.
package feishu

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
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
func DecryptMessage(encrypted string, encryptKey string) ([]byte, error) {
	if encryptKey == "" {
		return nil, errors.New("encrypt key is required")
	}

	cipherText, err := base64.StdEncoding.DecodeString(encrypted)
	if err != nil {
		return nil, fmt.Errorf("decode encrypted payload: %w", err)
	}
	if len(cipherText) < aes.BlockSize {
		return nil, errors.New("encrypted payload is too short")
	}

	key := sha256.Sum256([]byte(encryptKey))
	block, err := aes.NewCipher(key[:])
	if err != nil {
		return nil, fmt.Errorf("create AES cipher: %w", err)
	}

	iv := cipherText[:aes.BlockSize]
	payload := cipherText[aes.BlockSize:]
	if len(payload)%aes.BlockSize != 0 {
		return nil, errors.New("encrypted payload block size is invalid")
	}

	plain := make([]byte, len(payload))
	cipher.NewCBCDecrypter(block, iv).CryptBlocks(plain, payload)

	start := strings.IndexByte(string(plain), '{')
	end := strings.LastIndexByte(string(plain), '}')
	if start < 0 || end < start {
		return nil, errors.New("decrypted payload does not contain JSON")
	}

	return plain[start : end+1], nil
}
