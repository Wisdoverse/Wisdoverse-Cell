package feishu

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sync"
	"time"
)

const (
	baseURL           = "https://open.feishu.cn/open-apis"
	tokenURL          = baseURL + "/auth/v3/tenant_access_token/internal"
	sendMessageURL    = baseURL + "/im/v1/messages"
	replyMessageURL   = baseURL + "/im/v1/messages/%s/reply"
	updateCardURL     = baseURL + "/interactive/v1/card/update"
	patchMessageURL   = baseURL + "/im/v1/messages/%s"
)

// Client is the Feishu API client.
type Client struct {
	appID       string
	appSecret   string
	httpClient  *http.Client

	// Token caching
	token       string
	tokenExpiry time.Time
	tokenMu     sync.RWMutex
}

// NewClient creates a new Feishu API client.
func NewClient(appID, appSecret string) *Client {
	return &Client{
		appID:      appID,
		appSecret:  appSecret,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

// GetTenantAccessToken gets or refreshes the tenant access token.
func (c *Client) GetTenantAccessToken(ctx context.Context) (string, error) {
	c.tokenMu.RLock()
	if c.token != "" && time.Now().Before(c.tokenExpiry) {
		token := c.token
		c.tokenMu.RUnlock()
		return token, nil
	}
	c.tokenMu.RUnlock()

	c.tokenMu.Lock()
	defer c.tokenMu.Unlock()

	// Double-check after acquiring write lock
	if c.token != "" && time.Now().Before(c.tokenExpiry) {
		return c.token, nil
	}

	reqBody := map[string]string{
		"app_id":     c.appID,
		"app_secret": c.appSecret,
	}
	body, _ := json.Marshal(reqBody)

	req, err := http.NewRequestWithContext(ctx, "POST", tokenURL, bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("request token: %w", err)
	}
	defer resp.Body.Close()

	var result struct {
		Code   int    `json:"code"`
		Msg    string `json:"msg"`
		Token  string `json:"tenant_access_token"`
		Expire int    `json:"expire"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("decode response: %w", err)
	}

	if result.Code != 0 {
		return "", fmt.Errorf("feishu error: %s (code=%d)", result.Msg, result.Code)
	}

	c.token = result.Token
	// Refresh 5 minutes before expiry
	c.tokenExpiry = time.Now().Add(time.Duration(result.Expire-300) * time.Second)

	return c.token, nil
}

// SendMessage sends a message to a chat or user.
func (c *Client) SendMessage(ctx context.Context, receiveIDType, receiveID, msgType, content string) error {
	token, err := c.GetTenantAccessToken(ctx)
	if err != nil {
		return err
	}

	url := fmt.Sprintf("%s?receive_id_type=%s", sendMessageURL, receiveIDType)
	reqBody := map[string]string{
		"receive_id": receiveID,
		"msg_type":   msgType,
		"content":    content,
	}
	body, _ := json.Marshal(reqBody)

	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("send message: %w", err)
	}
	defer resp.Body.Close()

	return c.checkResponse(resp)
}

// ReplyMessage replies to a specific message.
func (c *Client) ReplyMessage(ctx context.Context, messageID, msgType, content string) error {
	token, err := c.GetTenantAccessToken(ctx)
	if err != nil {
		return err
	}

	url := fmt.Sprintf(replyMessageURL, messageID)
	reqBody := map[string]string{
		"msg_type": msgType,
		"content":  content,
	}
	body, _ := json.Marshal(reqBody)

	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("reply message: %w", err)
	}
	defer resp.Body.Close()

	return c.checkResponse(resp)
}

// SendCard sends an interactive card message.
func (c *Client) SendCard(ctx context.Context, receiveIDType, receiveID string, card *Card) error {
	content, err := json.Marshal(card)
	if err != nil {
		return fmt.Errorf("marshal card: %w", err)
	}
	return c.SendMessage(ctx, receiveIDType, receiveID, "interactive", string(content))
}

// ReplyCard replies with an interactive card.
func (c *Client) ReplyCard(ctx context.Context, messageID string, card *Card) error {
	content, err := json.Marshal(card)
	if err != nil {
		return fmt.Errorf("marshal card: %w", err)
	}
	return c.ReplyMessage(ctx, messageID, "interactive", string(content))
}

// UpdateCard updates an existing card.
func (c *Client) UpdateCard(ctx context.Context, token string, card *Card) error {
	accessToken, err := c.GetTenantAccessToken(ctx)
	if err != nil {
		return err
	}

	reqBody := map[string]interface{}{
		"token": token,
		"card":  card,
	}
	body, _ := json.Marshal(reqBody)

	req, err := http.NewRequestWithContext(ctx, "POST", updateCardURL, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+accessToken)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("update card: %w", err)
	}
	defer resp.Body.Close()

	return c.checkResponse(resp)
}

// PatchCard updates an existing card message by message ID.
func (c *Client) PatchCard(ctx context.Context, messageID string, card *Card) error {
	token, err := c.GetTenantAccessToken(ctx)
	if err != nil {
		return err
	}

	cardJSON, err := json.Marshal(card)
	if err != nil {
		return fmt.Errorf("marshal card: %w", err)
	}

	reqBody := map[string]string{
		"content": string(cardJSON),
	}
	body, _ := json.Marshal(reqBody)

	url := fmt.Sprintf(patchMessageURL, messageID)
	req, err := http.NewRequestWithContext(ctx, "PATCH", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("patch card: %w", err)
	}
	defer resp.Body.Close()

	return c.checkResponse(resp)
}

func (c *Client) checkResponse(resp *http.Response) error {
	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read response body: %w", err)
	}

	var result struct {
		Code int    `json:"code"`
		Msg  string `json:"msg"`
	}
	if err := json.Unmarshal(bodyBytes, &result); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}

	if result.Code != 0 {
		return fmt.Errorf("feishu error: %s (code=%d)", result.Msg, result.Code)
	}

	return nil
}
