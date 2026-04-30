package wecom

import (
	"crypto/sha1"
	"encoding/base64"
	"fmt"
	"sort"
	"strings"
	"testing"
)

func TestNewWXBizMsgCrypt_ValidKey(t *testing.T) {
	// Valid 43-character key that decodes to 32 bytes
	token := "test-token"
	encodingAESKey := "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
	corpID := "corp123"

	crypt, err := NewWXBizMsgCrypt(token, encodingAESKey, corpID)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if crypt.token != token {
		t.Errorf("token = %q, want %q", crypt.token, token)
	}

	if crypt.corpID != corpID {
		t.Errorf("corpID = %q, want %q", crypt.corpID, corpID)
	}

	if len(crypt.aesKey) != 32 {
		t.Errorf("aesKey length = %d, want 32", len(crypt.aesKey))
	}
}

func TestNewWXBizMsgCrypt_InvalidKeyLength(t *testing.T) {
	tests := []struct {
		name   string
		keyLen int
	}{
		{"too short", 42},
		{"too long", 44},
		{"empty", 0},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			key := strings.Repeat("a", tt.keyLen)
			_, err := NewWXBizMsgCrypt("token", key, "corp")
			if err == nil {
				t.Error("expected error for invalid key length")
			}
		})
	}
}

func TestWXBizMsgCrypt_GenerateSignature(t *testing.T) {
	token := "test-token"
	encodingAESKey := "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
	corpID := "corp123"

	crypt, err := NewWXBizMsgCrypt(token, encodingAESKey, corpID)
	if err != nil {
		t.Fatalf("failed to create crypt: %v", err)
	}

	timestamp := "1704067200"
	nonce := "abc123"
	encrypted := "encrypted-data"

	signature := crypt.generateSignature(timestamp, nonce, encrypted)

	// Manually verify the signature
	strs := []string{token, timestamp, nonce, encrypted}
	sort.Strings(strs)
	joined := strings.Join(strs, "")
	hash := sha1.Sum([]byte(joined))
	expected := fmt.Sprintf("%x", hash)

	if signature != expected {
		t.Errorf("signature = %q, want %q", signature, expected)
	}
}

func TestWXBizMsgCrypt_VerifySignature(t *testing.T) {
	token := "test-token"
	encodingAESKey := "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
	corpID := "corp123"

	crypt, err := NewWXBizMsgCrypt(token, encodingAESKey, corpID)
	if err != nil {
		t.Fatalf("failed to create crypt: %v", err)
	}

	timestamp := "1704067200"
	nonce := "abc123"
	encrypted := "encrypted-data"

	// Generate valid signature
	validSignature := crypt.generateSignature(timestamp, nonce, encrypted)

	tests := []struct {
		name      string
		signature string
		want      bool
	}{
		{"valid signature", validSignature, true},
		{"invalid signature", "invalid-sig", false},
		{"empty signature", "", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := crypt.verifySignature(tt.signature, timestamp, nonce, encrypted)
			if got != tt.want {
				t.Errorf("verifySignature() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestWXBizMsgCrypt_EncryptDecrypt_RoundTrip(t *testing.T) {
	token := "test-token"
	encodingAESKey := "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
	corpID := "corp123"

	crypt, err := NewWXBizMsgCrypt(token, encodingAESKey, corpID)
	if err != nil {
		t.Fatalf("failed to create crypt: %v", err)
	}

	originalMsg := "Hello, WeChat!"

	encrypted, err := crypt.encrypt(originalMsg)
	if err != nil {
		t.Fatalf("encrypt failed: %v", err)
	}

	if encrypted == originalMsg {
		t.Error("encrypted message should not equal original")
	}

	// Verify it's valid base64
	_, err = base64.StdEncoding.DecodeString(encrypted)
	if err != nil {
		t.Errorf("encrypted is not valid base64: %v", err)
	}

	decrypted, err := crypt.decrypt(encrypted)
	if err != nil {
		t.Fatalf("decrypt failed: %v", err)
	}

	if decrypted != originalMsg {
		t.Errorf("decrypted = %q, want %q", decrypted, originalMsg)
	}
}

func TestWXBizMsgCrypt_EncryptMsg(t *testing.T) {
	token := "test-token"
	encodingAESKey := "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
	corpID := "corp123"

	crypt, err := NewWXBizMsgCrypt(token, encodingAESKey, corpID)
	if err != nil {
		t.Fatalf("failed to create crypt: %v", err)
	}

	replyMsg := "<xml><ToUserName>user</ToUserName></xml>"
	timestamp := "1704067200"
	nonce := "random123"

	result, err := crypt.EncryptMsg(replyMsg, timestamp, nonce)
	if err != nil {
		t.Fatalf("EncryptMsg failed: %v", err)
	}

	// Check XML structure
	resultStr := string(result)
	if !strings.Contains(resultStr, "<xml>") {
		t.Error("result should contain <xml>")
	}
	if !strings.Contains(resultStr, "<Encrypt>") {
		t.Error("result should contain <Encrypt>")
	}
	if !strings.Contains(resultStr, "<MsgSignature>") {
		t.Error("result should contain <MsgSignature>")
	}
	if !strings.Contains(resultStr, "<TimeStamp>"+timestamp+"</TimeStamp>") {
		t.Error("result should contain timestamp")
	}
	if !strings.Contains(resultStr, "<Nonce>") {
		t.Error("result should contain <Nonce>")
	}
}

func TestWXBizMsgCrypt_DecryptMsg_InvalidSignature(t *testing.T) {
	token := "test-token"
	encodingAESKey := "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
	corpID := "corp123"

	crypt, err := NewWXBizMsgCrypt(token, encodingAESKey, corpID)
	if err != nil {
		t.Fatalf("failed to create crypt: %v", err)
	}

	postData := []byte(`<xml><ToUserName>corp</ToUserName><Encrypt>test</Encrypt><AgentID>1</AgentID></xml>`)

	_, err = crypt.DecryptMsg("invalid-signature", "timestamp", "nonce", postData)
	if err == nil {
		t.Error("expected error for invalid signature")
	}
}

func TestWXBizMsgCrypt_DecryptMsg_InvalidXML(t *testing.T) {
	token := "test-token"
	encodingAESKey := "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
	corpID := "corp123"

	crypt, err := NewWXBizMsgCrypt(token, encodingAESKey, corpID)
	if err != nil {
		t.Fatalf("failed to create crypt: %v", err)
	}

	postData := []byte(`not valid xml`)

	_, err = crypt.DecryptMsg("sig", "timestamp", "nonce", postData)
	if err == nil {
		t.Error("expected error for invalid XML")
	}
}

func TestPKCS7Pad(t *testing.T) {
	tests := []struct {
		name      string
		dataLen   int
		blockSize int
		wantLen   int
	}{
		{"needs 1 byte padding", 15, 16, 16},
		{"needs full block padding", 16, 16, 32},
		{"needs 8 bytes padding", 8, 16, 16},
		{"empty data", 0, 16, 16},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data := make([]byte, tt.dataLen)
			padded := pkcs7Pad(data, tt.blockSize)
			if len(padded) != tt.wantLen {
				t.Errorf("padded length = %d, want %d", len(padded), tt.wantLen)
			}
			// Check padding value
			paddingByte := padded[len(padded)-1]
			if int(paddingByte) != tt.wantLen-tt.dataLen {
				t.Errorf("padding byte = %d, want %d", paddingByte, tt.wantLen-tt.dataLen)
			}
		})
	}
}

func TestPKCS7Unpad(t *testing.T) {
	tests := []struct {
		name    string
		data    []byte
		wantLen int
		wantErr bool
	}{
		{
			name:    "valid padding",
			data:    append([]byte("hello"), 3, 3, 3),
			wantLen: 5,
			wantErr: false,
		},
		{
			name:    "single byte padding",
			data:    append([]byte("hello12345678"), 1),
			wantLen: 13,
			wantErr: false,
		},
		{
			name:    "empty data",
			data:    []byte{},
			wantLen: 0,
			wantErr: true,
		},
		{
			name:    "invalid padding - too large",
			data:    []byte{1, 2, 3, 20}, // padding byte > data length
			wantLen: 0,
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := pkcs7Unpad(tt.data)
			if (err != nil) != tt.wantErr {
				t.Errorf("pkcs7Unpad() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && len(result) != tt.wantLen {
				t.Errorf("result length = %d, want %d", len(result), tt.wantLen)
			}
		})
	}
}

func TestWXBizMsgCrypt_Decrypt_ShortCiphertext(t *testing.T) {
	token := "test-token"
	encodingAESKey := "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
	corpID := "corp123"

	crypt, err := NewWXBizMsgCrypt(token, encodingAESKey, corpID)
	if err != nil {
		t.Fatalf("failed to create crypt: %v", err)
	}

	// Base64 of very short data
	shortCipher := base64.StdEncoding.EncodeToString([]byte("short"))

	_, err = crypt.decrypt(shortCipher)
	if err == nil {
		t.Error("expected error for short ciphertext")
	}
}

func TestWXBizMsgCrypt_Decrypt_InvalidBase64(t *testing.T) {
	token := "test-token"
	encodingAESKey := "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
	corpID := "corp123"

	crypt, err := NewWXBizMsgCrypt(token, encodingAESKey, corpID)
	if err != nil {
		t.Fatalf("failed to create crypt: %v", err)
	}

	_, err = crypt.decrypt("not-valid-base64!!!")
	if err == nil {
		t.Error("expected error for invalid base64")
	}
}
