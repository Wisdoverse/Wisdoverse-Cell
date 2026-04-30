package feishu

import (
	"testing"
)

func TestParseMessageContent(t *testing.T) {
	tests := []struct {
		name        string
		messageType string
		content     string
		want        string
	}{
		{
			name:        "text message with valid JSON",
			messageType: "text",
			content:     `{"text":"hello world"}`,
			want:        "hello world",
		},
		{
			name:        "text message with invalid JSON falls back to raw content",
			messageType: "text",
			content:     `not valid json`,
			want:        "not valid json",
		},
		{
			name:        "image message returns placeholder",
			messageType: "image",
			content:     `{"image_key":"img_xxx"}`,
			want:        "[图片]",
		},
		{
			name:        "file message returns placeholder",
			messageType: "file",
			content:     `{"file_key":"file_xxx"}`,
			want:        "[文件]",
		},
		{
			name:        "audio message returns placeholder",
			messageType: "audio",
			content:     `{"file_key":"audio_xxx"}`,
			want:        "[语音]",
		},
		{
			name:        "video message returns placeholder",
			messageType: "video",
			content:     `{"file_key":"video_xxx"}`,
			want:        "[视频]",
		},
		{
			name:        "unknown message type returns bracketed type",
			messageType: "sticker",
			content:     `{}`,
			want:        "[sticker]",
		},
		{
			name:        "post with title and text elements",
			messageType: "post",
			content:     `{"title":"My Title","content":[[{"tag":"text","text":"Hello"},{"tag":"text","text":"World"}]]}`,
			want:        "My Title Hello World",
		},
		{
			name:        "post with link (a tag) elements",
			messageType: "post",
			content:     `{"title":"","content":[[{"tag":"a","text":"click here","href":"https://example.com"}]]}`,
			want:        "click here",
		},
		{
			name:        "post with image elements are skipped",
			messageType: "post",
			content:     `{"title":"","content":[[{"tag":"text","text":"before"},{"tag":"img","image_key":"img_xxx"},{"tag":"text","text":"after"}]]}`,
			want:        "before after",
		},
		{
			name:        "post with invalid JSON falls back to raw content",
			messageType: "post",
			content:     `{bad json`,
			want:        "{bad json",
		},
		{
			name:        "post with empty content and no title",
			messageType: "post",
			content:     `{"title":"","content":[]}`,
			want:        "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ParseMessageContent(tt.messageType, tt.content)
			if got != tt.want {
				t.Errorf("ParseMessageContent(%q, %q) = %q, want %q", tt.messageType, tt.content, got, tt.want)
			}
		})
	}
}

func TestIsBotMentioned(t *testing.T) {
	tests := []struct {
		name      string
		mentions  []Mention
		botOpenID string
		want      bool
	}{
		{
			name: "bot found in mentions",
			mentions: []Mention{
				{Key: "@_user_1", ID: MentionID{OpenID: "ou_user1"}, Name: "User1"},
				{Key: "@_user_2", ID: MentionID{OpenID: "ou_bot123"}, Name: "Bot"},
			},
			botOpenID: "ou_bot123",
			want:      true,
		},
		{
			name: "bot not found in mentions",
			mentions: []Mention{
				{Key: "@_user_1", ID: MentionID{OpenID: "ou_user1"}, Name: "User1"},
			},
			botOpenID: "ou_bot123",
			want:      false,
		},
		{
			name:      "empty bot ID never matches",
			mentions:  []Mention{{Key: "@_user_1", ID: MentionID{OpenID: "ou_user1"}}},
			botOpenID: "",
			want:      false,
		},
		{
			name:      "nil mentions slice returns false",
			mentions:  nil,
			botOpenID: "ou_bot123",
			want:      false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := IsBotMentioned(tt.mentions, tt.botOpenID)
			if got != tt.want {
				t.Errorf("IsBotMentioned(%v, %q) = %v, want %v", tt.mentions, tt.botOpenID, got, tt.want)
			}
		})
	}
}
