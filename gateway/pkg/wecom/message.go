package wecom

import (
	"encoding/json"
	"encoding/xml"
)

// Message types
const (
	MsgTypeText     = "text"
	MsgTypeImage    = "image"
	MsgTypeVoice    = "voice"
	MsgTypeVideo    = "video"
	MsgTypeLocation = "location"
	MsgTypeLink     = "link"
	MsgTypeEvent    = "event"
)

// Event types
const (
	EventTypeSubscribe   = "subscribe"
	EventTypeUnsubscribe = "unsubscribe"
	EventTypeEnterAgent  = "enter_agent"
	EventTypeClick       = "click"
	EventTypeView        = "view"
)

// ReceivedMessage represents a message received from WeChat.
type ReceivedMessage struct {
	XMLName      xml.Name `xml:"xml"`
	ToUserName   string   `xml:"ToUserName"`
	FromUserName string   `xml:"FromUserName"`
	CreateTime   int64    `xml:"CreateTime"`
	MsgType      string   `xml:"MsgType"`
	MsgID        int64    `xml:"MsgId"`
	AgentID      int64    `xml:"AgentID"`

	// Text message
	Content string `xml:"Content"`

	// Image message
	PicURL  string `xml:"PicUrl"`
	MediaID string `xml:"MediaId"`

	// Voice message
	Format      string `xml:"Format"`
	Recognition string `xml:"Recognition"` // Voice recognition result

	// Video message
	ThumbMediaID string `xml:"ThumbMediaId"`

	// Location message
	LocationX float64 `xml:"Location_X"`
	LocationY float64 `xml:"Location_Y"`
	Scale     int     `xml:"Scale"`
	Label     string  `xml:"Label"`

	// Link message
	Title       string `xml:"Title"`
	Description string `xml:"Description"`
	URL         string `xml:"Url"`

	// Event
	Event    string `xml:"Event"`
	EventKey string `xml:"EventKey"`
}

// ReplyMessage is the base for reply messages.
type ReplyMessage struct {
	XMLName      xml.Name `xml:"xml"`
	ToUserName   string   `xml:"ToUserName"`
	FromUserName string   `xml:"FromUserName"`
	CreateTime   int64    `xml:"CreateTime"`
	MsgType      string   `xml:"MsgType"`
}

// TextReply is a text reply message.
type TextReply struct {
	ReplyMessage
	Content string `xml:"Content"`
}

// NewTextReply creates a text reply message.
func NewTextReply(toUser, fromUser string, createTime int64, content string) *TextReply {
	return &TextReply{
		ReplyMessage: ReplyMessage{
			ToUserName:   toUser,
			FromUserName: fromUser,
			CreateTime:   createTime,
			MsgType:      MsgTypeText,
		},
		Content: content,
	}
}

// ParseMessageContent extracts text content from a message.
func ParseMessageContent(msg *ReceivedMessage) string {
	switch msg.MsgType {
	case MsgTypeText:
		return msg.Content
	case MsgTypeVoice:
		// Return voice recognition if available
		if msg.Recognition != "" {
			return msg.Recognition
		}
		return "[语音消息]"
	case MsgTypeImage:
		return "[图片消息]"
	case MsgTypeVideo:
		return "[视频消息]"
	case MsgTypeLocation:
		return "[位置消息]"
	case MsgTypeLink:
		return msg.Title + " " + msg.Description
	default:
		return ""
	}
}

// CardMessage represents a card message for WeChat.
type CardMessage struct {
	ChatID  string      `json:"chatid,omitempty"`
	MsgType string      `json:"msgtype"`
	AgentID int         `json:"agentid"`
	Card    interface{} `json:"markdown,omitempty"`
	Text    *TextContent `json:"text,omitempty"`
}

// TextContent is text content for messages.
type TextContent struct {
	Content string `json:"content"`
}

// MarkdownContent is markdown content for messages.
type MarkdownContent struct {
	Content string `json:"content"`
}

// NewTextMessage creates a text message.
func NewTextMessage(agentID int, userID, content string) *CardMessage {
	return &CardMessage{
		MsgType: "text",
		AgentID: agentID,
		Text: &TextContent{
			Content: content,
		},
	}
}

// NewMarkdownMessage creates a markdown message.
func NewMarkdownMessage(agentID int, content string) *CardMessage {
	return &CardMessage{
		MsgType: "markdown",
		AgentID: agentID,
		Card: &MarkdownContent{
			Content: content,
		},
	}
}

// ToJSON converts the message to JSON.
func (m *CardMessage) ToJSON() ([]byte, error) {
	return json.Marshal(m)
}
