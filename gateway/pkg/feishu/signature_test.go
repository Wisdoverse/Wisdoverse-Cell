package feishu

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
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

func TestDecryptMessage_Passthrough(t *testing.T) {
	// Current implementation is passthrough
	input := `{"test":"data"}`
	result, err := DecryptMessage(input, "any-key")

	if err != nil {
		t.Errorf("unexpected error: %v", err)
	}

	if string(result) != input {
		t.Errorf("result = %q, want %q", string(result), input)
	}
}
