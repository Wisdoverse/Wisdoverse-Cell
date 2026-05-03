package feishu

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"strings"
	"testing"
)

func TestVerifySignature_Valid(t *testing.T) {
	timestamp := "1704067200"
	nonce := "abc123"
	encryptKey := "test-encrypt-key"
	body := []byte(`{"event":"test"}`)

	// Calculate expected signature
	data := fmt.Sprintf("%s%s%s%s", timestamp, nonce, encryptKey, string(body))
	hash := sha256.Sum256([]byte(data))
	signature := hex.EncodeToString(hash[:])

	if !VerifySignature(timestamp, nonce, encryptKey, body, signature) {
		t.Error("expected valid signature to pass verification")
	}
}

func TestVerifySignature_Invalid(t *testing.T) {
	timestamp := "1704067200"
	nonce := "abc123"
	encryptKey := "test-encrypt-key"
	body := []byte(`{"event":"test"}`)
	invalidSignature := "invalid-signature"

	if VerifySignature(timestamp, nonce, encryptKey, body, invalidSignature) {
		t.Error("expected invalid signature to fail verification")
	}
}

func TestVerifySignature_EmptyEncryptKey(t *testing.T) {
	if VerifySignature("ts", "nonce", "", []byte("body"), "any-signature") {
		t.Error("expected verification to fail when encrypt key is empty")
	}
}

func TestVerifySignature_DifferentTimestamp(t *testing.T) {
	timestamp := "1704067200"
	nonce := "abc123"
	encryptKey := "test-encrypt-key"
	body := []byte(`{"event":"test"}`)

	// Calculate signature with original timestamp
	data := fmt.Sprintf("%s%s%s%s", timestamp, nonce, encryptKey, string(body))
	hash := sha256.Sum256([]byte(data))
	signature := hex.EncodeToString(hash[:])

	// Verify with different timestamp should fail
	differentTimestamp := "1704067201"
	if VerifySignature(differentTimestamp, nonce, encryptKey, body, signature) {
		t.Error("expected verification to fail with different timestamp")
	}
}

func TestVerifySignature_DifferentBody(t *testing.T) {
	timestamp := "1704067200"
	nonce := "abc123"
	encryptKey := "test-encrypt-key"
	body := []byte(`{"event":"test"}`)

	// Calculate signature with original body
	data := fmt.Sprintf("%s%s%s%s", timestamp, nonce, encryptKey, string(body))
	hash := sha256.Sum256([]byte(data))
	signature := hex.EncodeToString(hash[:])

	// Verify with different body should fail
	differentBody := []byte(`{"event":"modified"}`)
	if VerifySignature(timestamp, nonce, encryptKey, differentBody, signature) {
		t.Error("expected verification to fail with different body")
	}
}

func TestVerifySignature_EmptyBody(t *testing.T) {
	timestamp := "1704067200"
	nonce := "abc123"
	encryptKey := "test-encrypt-key"
	body := []byte("")

	// Calculate expected signature
	data := fmt.Sprintf("%s%s%s%s", timestamp, nonce, encryptKey, string(body))
	hash := sha256.Sum256([]byte(data))
	signature := hex.EncodeToString(hash[:])

	if !VerifySignature(timestamp, nonce, encryptKey, body, signature) {
		t.Error("expected valid signature with empty body to pass")
	}
}

func TestDecryptMessage_EncryptedPayload(t *testing.T) {
	input := `{"test":"data"}`
	encryptKey := "test-encrypt-key"
	encrypted := encryptForTest(t, input, encryptKey)

	result, err := DecryptMessage(encrypted, encryptKey)

	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}

	if string(result) != input {
		t.Errorf("result = %q, want %q", string(result), input)
	}
}

func TestDecryptMessage_InvalidInputs(t *testing.T) {
	tests := []struct {
		name       string
		encrypted  string
		encryptKey string
		wantErr    string
	}{
		{"missing key", "payload", "", "encrypt key is required"},
		{"invalid base64", "not-base64", "key", "decode encrypted payload"},
		{"too short", base64.StdEncoding.EncodeToString([]byte("short")), "key", "too short"},
		{"no json", encryptForTest(t, "not-json", "key"), "key", "does not contain JSON"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := DecryptMessage(tt.encrypted, tt.encryptKey)
			if err == nil || !strings.Contains(err.Error(), tt.wantErr) {
				t.Fatalf("error = %v, want it to contain %q", err, tt.wantErr)
			}
		})
	}
}

func encryptForTest(t *testing.T, plainText string, encryptKey string) string {
	t.Helper()

	key := sha256.Sum256([]byte(encryptKey))
	block, err := aes.NewCipher(key[:])
	if err != nil {
		t.Fatalf("create cipher: %v", err)
	}

	iv := []byte("1234567890abcdef")
	padding := aes.BlockSize - len(plainText)%aes.BlockSize
	padded := append([]byte(plainText), bytes.Repeat([]byte{byte(padding)}, padding)...)

	cipherText := make([]byte, len(padded))
	cipher.NewCBCEncrypter(block, iv).CryptBlocks(cipherText, padded)
	payload := append(append([]byte{}, iv...), cipherText...)
	return base64.StdEncoding.EncodeToString(payload)
}
