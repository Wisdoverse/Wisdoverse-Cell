package wecom

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/sha1"
	"encoding/base64"
	"encoding/binary"
	"encoding/xml"
	"errors"
	"fmt"
	"sort"
	"strings"
)

// WXBizMsgCrypt handles WeChat message encryption/decryption.
type WXBizMsgCrypt struct {
	token          string
	encodingAESKey string
	corpID         string
	aesKey         []byte
}

// NewWXBizMsgCrypt creates a new WXBizMsgCrypt instance.
func NewWXBizMsgCrypt(token, encodingAESKey, corpID string) (*WXBizMsgCrypt, error) {
	if len(encodingAESKey) != 43 {
		return nil, errors.New("encodingAESKey must be 43 characters")
	}

	aesKey, err := base64.StdEncoding.DecodeString(encodingAESKey + "=")
	if err != nil {
		return nil, fmt.Errorf("decode AES key: %w", err)
	}

	return &WXBizMsgCrypt{
		token:          token,
		encodingAESKey: encodingAESKey,
		corpID:         corpID,
		aesKey:         aesKey,
	}, nil
}

// VerifyURL verifies the callback URL and returns the decrypted echostr.
func (w *WXBizMsgCrypt) VerifyURL(msgSignature, timestamp, nonce, echoStr string) (string, error) {
	// Verify signature
	if !w.verifySignature(msgSignature, timestamp, nonce, echoStr) {
		return "", errors.New("signature verification failed")
	}

	// Decrypt echostr
	plainText, err := w.decrypt(echoStr)
	if err != nil {
		return "", fmt.Errorf("decrypt echostr: %w", err)
	}

	return plainText, nil
}

// DecryptMsg decrypts a message from WeChat.
func (w *WXBizMsgCrypt) DecryptMsg(msgSignature, timestamp, nonce string, postData []byte) ([]byte, error) {
	// Parse encrypted message
	var encMsg struct {
		ToUserName string `xml:"ToUserName"`
		Encrypt    string `xml:"Encrypt"`
		AgentID    string `xml:"AgentID"`
	}
	if err := xml.Unmarshal(postData, &encMsg); err != nil {
		return nil, fmt.Errorf("parse encrypted message: %w", err)
	}

	// Verify signature
	if !w.verifySignature(msgSignature, timestamp, nonce, encMsg.Encrypt) {
		return nil, errors.New("signature verification failed")
	}

	// Decrypt message
	plainText, err := w.decrypt(encMsg.Encrypt)
	if err != nil {
		return nil, fmt.Errorf("decrypt message: %w", err)
	}

	return []byte(plainText), nil
}

// EncryptMsg encrypts a message for WeChat.
func (w *WXBizMsgCrypt) EncryptMsg(replyMsg, timestamp, nonce string) ([]byte, error) {
	// Encrypt message
	encrypted, err := w.encrypt(replyMsg)
	if err != nil {
		return nil, fmt.Errorf("encrypt message: %w", err)
	}

	// Generate signature
	signature := w.generateSignature(timestamp, nonce, encrypted)

	// Build response XML
	response := fmt.Sprintf(`<xml>
<Encrypt><![CDATA[%s]]></Encrypt>
<MsgSignature><![CDATA[%s]]></MsgSignature>
<TimeStamp>%s</TimeStamp>
<Nonce><![CDATA[%s]]></Nonce>
</xml>`, encrypted, signature, timestamp, nonce)

	return []byte(response), nil
}

func (w *WXBizMsgCrypt) verifySignature(msgSignature, timestamp, nonce, encrypted string) bool {
	expected := w.generateSignature(timestamp, nonce, encrypted)
	return msgSignature == expected
}

func (w *WXBizMsgCrypt) generateSignature(timestamp, nonce, encrypted string) string {
	strs := []string{w.token, timestamp, nonce, encrypted}
	sort.Strings(strs)
	joined := strings.Join(strs, "")

	hash := sha1.Sum([]byte(joined))
	return fmt.Sprintf("%x", hash)
}

func (w *WXBizMsgCrypt) decrypt(encrypted string) (string, error) {
	cipherText, err := base64.StdEncoding.DecodeString(encrypted)
	if err != nil {
		return "", fmt.Errorf("base64 decode: %w", err)
	}

	block, err := aes.NewCipher(w.aesKey)
	if err != nil {
		return "", fmt.Errorf("new cipher: %w", err)
	}

	if len(cipherText) < aes.BlockSize {
		return "", errors.New("ciphertext too short")
	}

	iv := w.aesKey[:aes.BlockSize]
	mode := cipher.NewCBCDecrypter(block, iv)

	plainText := make([]byte, len(cipherText))
	mode.CryptBlocks(plainText, cipherText)

	// Remove PKCS7 padding
	plainText, err = pkcs7Unpad(plainText)
	if err != nil {
		return "", fmt.Errorf("unpad: %w", err)
	}

	// Parse plain text: random(16) + msgLen(4) + msg + corpID
	if len(plainText) < 20 {
		return "", errors.New("plaintext too short")
	}

	msgLen := binary.BigEndian.Uint32(plainText[16:20])
	if uint32(len(plainText)) < 20+msgLen {
		return "", errors.New("invalid message length")
	}

	msg := plainText[20 : 20+msgLen]
	corpID := string(plainText[20+msgLen:])

	if corpID != w.corpID {
		return "", fmt.Errorf("corpID mismatch: got %s, want %s", corpID, w.corpID)
	}

	return string(msg), nil
}

func (w *WXBizMsgCrypt) encrypt(plainText string) (string, error) {
	// Build plain text: random(16) + msgLen(4) + msg + corpID
	random := make([]byte, 16)
	for i := range random {
		random[i] = byte(i)
	}

	msgLen := make([]byte, 4)
	binary.BigEndian.PutUint32(msgLen, uint32(len(plainText)))

	plain := bytes.NewBuffer(random)
	plain.Write(msgLen)
	plain.WriteString(plainText)
	plain.WriteString(w.corpID)

	// PKCS7 padding
	padded := pkcs7Pad(plain.Bytes(), aes.BlockSize)

	block, err := aes.NewCipher(w.aesKey)
	if err != nil {
		return "", fmt.Errorf("new cipher: %w", err)
	}

	iv := w.aesKey[:aes.BlockSize]
	mode := cipher.NewCBCEncrypter(block, iv)

	cipherText := make([]byte, len(padded))
	mode.CryptBlocks(cipherText, padded)

	return base64.StdEncoding.EncodeToString(cipherText), nil
}

func pkcs7Pad(data []byte, blockSize int) []byte {
	padding := blockSize - len(data)%blockSize
	padText := bytes.Repeat([]byte{byte(padding)}, padding)
	return append(data, padText...)
}

func pkcs7Unpad(data []byte) ([]byte, error) {
	if len(data) == 0 {
		return nil, errors.New("empty data")
	}
	padding := int(data[len(data)-1])
	if padding > len(data) || padding > aes.BlockSize {
		return nil, errors.New("invalid padding")
	}
	return data[:len(data)-padding], nil
}
