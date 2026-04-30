package wecom

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
	baseURL      = "https://qyapi.weixin.qq.com/cgi-bin"
	tokenURL     = baseURL + "/gettoken"
	sendMsgURL   = baseURL + "/message/send"
	uploadURL    = baseURL + "/media/upload"
)

// Client is the WeChat Work API client.
type Client struct {
	corpID     string
	agentID    int
	secret     string
	httpClient *http.Client

	// Token caching
	token       string
	tokenExpiry time.Time
	tokenMu     sync.RWMutex
}

// NewClient creates a new WeChat Work API client.
func NewClient(corpID string, agentID int, secret string) *Client {
	return &Client{
		corpID:     corpID,
		agentID:    agentID,
		secret:     secret,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

// GetAccessToken gets or refreshes the access token.
func (c *Client) GetAccessToken(ctx context.Context) (string, error) {
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

	url := fmt.Sprintf("%s?corpid=%s&corpsecret=%s", tokenURL, c.corpID, c.secret)
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return "", fmt.Errorf("create request: %w", err)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("request token: %w", err)
	}
	defer resp.Body.Close()

	var result struct {
		ErrCode     int    `json:"errcode"`
		ErrMsg      string `json:"errmsg"`
		AccessToken string `json:"access_token"`
		ExpiresIn   int    `json:"expires_in"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", fmt.Errorf("decode response: %w", err)
	}

	if result.ErrCode != 0 {
		return "", fmt.Errorf("wecom error: %s (code=%d)", result.ErrMsg, result.ErrCode)
	}

	c.token = result.AccessToken
	// Refresh 5 minutes before expiry
	c.tokenExpiry = time.Now().Add(time.Duration(result.ExpiresIn-300) * time.Second)

	return c.token, nil
}

// SendMessage sends a message to users.
func (c *Client) SendMessage(ctx context.Context, msg *SendMessageRequest) error {
	token, err := c.GetAccessToken(ctx)
	if err != nil {
		return err
	}

	// Set agent ID
	msg.AgentID = c.agentID

	body, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("marshal message: %w", err)
	}

	url := fmt.Sprintf("%s?access_token=%s", sendMsgURL, token)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("send message: %w", err)
	}
	defer resp.Body.Close()

	return c.checkResponse(resp)
}

// SendTextMessage sends a text message to a user.
func (c *Client) SendTextMessage(ctx context.Context, userID, content string) error {
	msg := &SendMessageRequest{
		ToUser:  userID,
		MsgType: "text",
		Text: &TextContent{
			Content: content,
		},
	}
	return c.SendMessage(ctx, msg)
}

// SendMarkdownMessage sends a markdown message to a user.
func (c *Client) SendMarkdownMessage(ctx context.Context, userID, content string) error {
	msg := &SendMessageRequest{
		ToUser:  userID,
		MsgType: "markdown",
		Markdown: &MarkdownContent{
			Content: content,
		},
	}
	return c.SendMessage(ctx, msg)
}

// SendTextCard sends a text card to a user.
func (c *Client) SendTextCard(ctx context.Context, userID string, card *TextCardContent) error {
	msg := &SendMessageRequest{
		ToUser:   userID,
		MsgType:  "textcard",
		TextCard: card,
	}
	return c.SendMessage(ctx, msg)
}

func (c *Client) checkResponse(resp *http.Response) error {
	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read response body: %w", err)
	}

	var result struct {
		ErrCode int    `json:"errcode"`
		ErrMsg  string `json:"errmsg"`
	}
	if err := json.Unmarshal(bodyBytes, &result); err != nil {
		return fmt.Errorf("decode response: %w", err)
	}

	if result.ErrCode != 0 {
		return fmt.Errorf("wecom error: %s (code=%d)", result.ErrMsg, result.ErrCode)
	}

	return nil
}

// SendMessageRequest is the request body for sending messages.
type SendMessageRequest struct {
	ToUser   string           `json:"touser,omitempty"`
	ToParty  string           `json:"toparty,omitempty"`
	ToTag    string           `json:"totag,omitempty"`
	MsgType  string           `json:"msgtype"`
	AgentID  int              `json:"agentid"`
	Text     *TextContent     `json:"text,omitempty"`
	Markdown *MarkdownContent `json:"markdown,omitempty"`
	TextCard *TextCardContent `json:"textcard,omitempty"`
}

// TextCardContent is text card content.
type TextCardContent struct {
	Title       string `json:"title"`
	Description string `json:"description"`
	URL         string `json:"url"`
	BtnTxt      string `json:"btntxt,omitempty"`
}
