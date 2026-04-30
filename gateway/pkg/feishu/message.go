package feishu

import (
	"encoding/json"
	"strings"
)

// EventType constants for Feishu events.
const (
	EventTypeURLVerification = "url_verification"
	EventTypeCallback        = "event_callback"
	EventTypeCardAction      = "card_action"

	// Message event types
	MessageReceiveV1 = "im.message.receive_v1"

	// Card action event types (v2 event subscription)
	CardActionTrigger = "card.action.trigger"
)

// CardActionContext contains context about the card message.
type CardActionContext struct {
	OpenMessageID string `json:"open_message_id"`
	OpenChatID    string `json:"open_chat_id"`
}

// CardActionTriggerEvent represents the event payload for card.action.trigger.
type CardActionTriggerEvent struct {
	Operator struct {
		OpenID    string `json:"open_id"`
		UserID    string `json:"user_id"`
		TenantKey string `json:"tenant_key"`
	} `json:"operator"`
	Token   string             `json:"token"`
	Action  CardActionDetail   `json:"action"`
	Context *CardActionContext `json:"context,omitempty"`
}

// WebhookRequest represents the incoming webhook request from Feishu.
type WebhookRequest struct {
	Type      string          `json:"type"`
	Challenge string          `json:"challenge,omitempty"`
	Token     string          `json:"token,omitempty"`
	Header    *EventHeader    `json:"header,omitempty"`
	Event     json.RawMessage `json:"event,omitempty"`
	Action    json.RawMessage `json:"action,omitempty"`
}

// EventHeader contains metadata about the event.
type EventHeader struct {
	EventID    string `json:"event_id"`
	EventType  string `json:"event_type"`
	CreateTime string `json:"create_time"`
	Token      string `json:"token"`
	AppID      string `json:"app_id"`
	TenantKey  string `json:"tenant_key"`
}

// MessageEvent represents a message receive event.
type MessageEvent struct {
	Sender  Sender  `json:"sender"`
	Message Message `json:"message"`
}

// Sender contains information about the message sender.
type Sender struct {
	SenderID   SenderID `json:"sender_id"`
	SenderType string   `json:"sender_type"`
	TenantKey  string   `json:"tenant_key"`
}

// SenderID contains different ID formats for the sender.
type SenderID struct {
	UnionID string `json:"union_id"`
	UserID  string `json:"user_id"`
	OpenID  string `json:"open_id"`
}

// Message contains the message details.
type Message struct {
	MessageID   string   `json:"message_id"`
	RootID      string   `json:"root_id,omitempty"`
	ParentID    string   `json:"parent_id,omitempty"`
	CreateTime  string   `json:"create_time"`
	ChatID      string   `json:"chat_id"`
	ChatType    string   `json:"chat_type"`
	MessageType string   `json:"message_type"`
	Content     string   `json:"content"`
	Mentions    []Mention `json:"mentions,omitempty"`
}

// Mention represents a user mention in the message.
type Mention struct {
	Key       string   `json:"key"`
	ID        MentionID `json:"id"`
	Name      string   `json:"name"`
	TenantKey string   `json:"tenant_key"`
}

// MentionID contains the mentioned user's IDs.
type MentionID struct {
	UnionID string `json:"union_id"`
	UserID  string `json:"user_id"`
	OpenID  string `json:"open_id"`
}

// TextContent represents text message content.
type TextContent struct {
	Text string `json:"text"`
}

// CardAction represents a card button click action.
type CardAction struct {
	OpenID     string            `json:"open_id"`
	UserID     string            `json:"user_id"`
	OpenChatID string            `json:"open_chat_id"`
	TenantKey  string            `json:"tenant_key"`
	Token      string            `json:"token"`
	Action     CardActionDetail  `json:"action"`
}

// CardActionDetail contains the action details.
type CardActionDetail struct {
	Value map[string]interface{} `json:"value"`
	Tag   string                 `json:"tag"`
}

// ParseMessageContent extracts text from message content JSON.
func ParseMessageContent(messageType, content string) string {
	switch messageType {
	case "text":
		var tc TextContent
		if err := json.Unmarshal([]byte(content), &tc); err != nil {
			return content
		}
		return tc.Text
	case "post":
		return parsePostContent(content)
	case "image":
		return "[图片]"
	case "file":
		return "[文件]"
	case "audio":
		return "[语音]"
	case "video":
		return "[视频]"
	default:
		return "[" + messageType + "]"
	}
}

// parsePostContent extracts plain text from rich text (post) content.
func parsePostContent(content string) string {
	var post struct {
		Title   string          `json:"title"`
		Content [][]interface{} `json:"content"`
	}
	if err := json.Unmarshal([]byte(content), &post); err != nil {
		return content
	}

	var texts []string
	if post.Title != "" {
		texts = append(texts, post.Title)
	}

	for _, paragraph := range post.Content {
		for _, elem := range paragraph {
			if elemMap, ok := elem.(map[string]interface{}); ok {
				if tag, _ := elemMap["tag"].(string); tag == "text" || tag == "a" {
					if text, _ := elemMap["text"].(string); text != "" {
						texts = append(texts, text)
					}
				}
			}
		}
	}

	return strings.Join(texts, " ")
}

// IsBotMentioned checks if the bot was mentioned in the message.
func IsBotMentioned(mentions []Mention, botOpenID string) bool {
	for _, m := range mentions {
		if m.ID.OpenID == botOpenID {
			return true
		}
	}
	return false
}
