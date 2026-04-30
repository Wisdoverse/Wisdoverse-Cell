package wecom

import (
	"encoding/json"
	"encoding/xml"
	"testing"
)

func TestReceivedMessage_XMLUnmarshal(t *testing.T) {
	xmlData := `<xml>
		<ToUserName><![CDATA[corp123]]></ToUserName>
		<FromUserName><![CDATA[user456]]></FromUserName>
		<CreateTime>1704067200</CreateTime>
		<MsgType><![CDATA[text]]></MsgType>
		<MsgId>123456789</MsgId>
		<AgentID>1000001</AgentID>
		<Content><![CDATA[Hello World]]></Content>
	</xml>`

	var msg ReceivedMessage
	if err := xml.Unmarshal([]byte(xmlData), &msg); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	if msg.ToUserName != "corp123" {
		t.Errorf("ToUserName = %q, want %q", msg.ToUserName, "corp123")
	}

	if msg.FromUserName != "user456" {
		t.Errorf("FromUserName = %q, want %q", msg.FromUserName, "user456")
	}

	if msg.CreateTime != 1704067200 {
		t.Errorf("CreateTime = %d, want %d", msg.CreateTime, 1704067200)
	}

	if msg.MsgType != "text" {
		t.Errorf("MsgType = %q, want %q", msg.MsgType, "text")
	}

	if msg.MsgID != 123456789 {
		t.Errorf("MsgID = %d, want %d", msg.MsgID, 123456789)
	}

	if msg.AgentID != 1000001 {
		t.Errorf("AgentID = %d, want %d", msg.AgentID, 1000001)
	}

	if msg.Content != "Hello World" {
		t.Errorf("Content = %q, want %q", msg.Content, "Hello World")
	}
}

func TestReceivedMessage_ImageMessage(t *testing.T) {
	xmlData := `<xml>
		<ToUserName><![CDATA[corp123]]></ToUserName>
		<FromUserName><![CDATA[user456]]></FromUserName>
		<CreateTime>1704067200</CreateTime>
		<MsgType><![CDATA[image]]></MsgType>
		<PicUrl><![CDATA[http://example.com/pic.jpg]]></PicUrl>
		<MediaId><![CDATA[media123]]></MediaId>
	</xml>`

	var msg ReceivedMessage
	if err := xml.Unmarshal([]byte(xmlData), &msg); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	if msg.MsgType != "image" {
		t.Errorf("MsgType = %q, want %q", msg.MsgType, "image")
	}

	if msg.PicURL != "http://example.com/pic.jpg" {
		t.Errorf("PicURL = %q, want %q", msg.PicURL, "http://example.com/pic.jpg")
	}

	if msg.MediaID != "media123" {
		t.Errorf("MediaID = %q, want %q", msg.MediaID, "media123")
	}
}

func TestReceivedMessage_VoiceMessage(t *testing.T) {
	xmlData := `<xml>
		<ToUserName><![CDATA[corp123]]></ToUserName>
		<FromUserName><![CDATA[user456]]></FromUserName>
		<CreateTime>1704067200</CreateTime>
		<MsgType><![CDATA[voice]]></MsgType>
		<Format><![CDATA[amr]]></Format>
		<MediaId><![CDATA[media123]]></MediaId>
		<Recognition><![CDATA[This is voice recognition result]]></Recognition>
	</xml>`

	var msg ReceivedMessage
	if err := xml.Unmarshal([]byte(xmlData), &msg); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	if msg.MsgType != "voice" {
		t.Errorf("MsgType = %q, want %q", msg.MsgType, "voice")
	}

	if msg.Format != "amr" {
		t.Errorf("Format = %q, want %q", msg.Format, "amr")
	}

	if msg.Recognition != "This is voice recognition result" {
		t.Errorf("Recognition = %q, want expected value", msg.Recognition)
	}
}

func TestReceivedMessage_LocationMessage(t *testing.T) {
	xmlData := `<xml>
		<ToUserName><![CDATA[corp123]]></ToUserName>
		<FromUserName><![CDATA[user456]]></FromUserName>
		<CreateTime>1704067200</CreateTime>
		<MsgType><![CDATA[location]]></MsgType>
		<Location_X>31.2344</Location_X>
		<Location_Y>121.4567</Location_Y>
		<Scale>15</Scale>
		<Label><![CDATA[Shanghai, China]]></Label>
	</xml>`

	var msg ReceivedMessage
	if err := xml.Unmarshal([]byte(xmlData), &msg); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	if msg.MsgType != "location" {
		t.Errorf("MsgType = %q, want %q", msg.MsgType, "location")
	}

	if msg.LocationX != 31.2344 {
		t.Errorf("LocationX = %f, want %f", msg.LocationX, 31.2344)
	}

	if msg.LocationY != 121.4567 {
		t.Errorf("LocationY = %f, want %f", msg.LocationY, 121.4567)
	}

	if msg.Scale != 15 {
		t.Errorf("Scale = %d, want %d", msg.Scale, 15)
	}

	if msg.Label != "Shanghai, China" {
		t.Errorf("Label = %q, want %q", msg.Label, "Shanghai, China")
	}
}

func TestReceivedMessage_EventMessage(t *testing.T) {
	xmlData := `<xml>
		<ToUserName><![CDATA[corp123]]></ToUserName>
		<FromUserName><![CDATA[user456]]></FromUserName>
		<CreateTime>1704067200</CreateTime>
		<MsgType><![CDATA[event]]></MsgType>
		<Event><![CDATA[click]]></Event>
		<EventKey><![CDATA[menu_item_1]]></EventKey>
		<AgentID>1000001</AgentID>
	</xml>`

	var msg ReceivedMessage
	if err := xml.Unmarshal([]byte(xmlData), &msg); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	if msg.MsgType != "event" {
		t.Errorf("MsgType = %q, want %q", msg.MsgType, "event")
	}

	if msg.Event != "click" {
		t.Errorf("Event = %q, want %q", msg.Event, "click")
	}

	if msg.EventKey != "menu_item_1" {
		t.Errorf("EventKey = %q, want %q", msg.EventKey, "menu_item_1")
	}
}

func TestNewTextReply(t *testing.T) {
	reply := NewTextReply("user123", "corp456", 1704067200, "Hello!")

	if reply.ToUserName != "user123" {
		t.Errorf("ToUserName = %q, want %q", reply.ToUserName, "user123")
	}

	if reply.FromUserName != "corp456" {
		t.Errorf("FromUserName = %q, want %q", reply.FromUserName, "corp456")
	}

	if reply.CreateTime != 1704067200 {
		t.Errorf("CreateTime = %d, want %d", reply.CreateTime, 1704067200)
	}

	if reply.MsgType != MsgTypeText {
		t.Errorf("MsgType = %q, want %q", reply.MsgType, MsgTypeText)
	}

	if reply.Content != "Hello!" {
		t.Errorf("Content = %q, want %q", reply.Content, "Hello!")
	}
}

func TestTextReply_XMLMarshal(t *testing.T) {
	reply := NewTextReply("user123", "corp456", 1704067200, "Hello!")

	data, err := xml.Marshal(reply)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	// Verify it can be unmarshaled
	var decoded TextReply
	if err := xml.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	if decoded.Content != "Hello!" {
		t.Errorf("Content = %q, want %q", decoded.Content, "Hello!")
	}
}

func TestParseMessageContent(t *testing.T) {
	tests := []struct {
		name    string
		msg     *ReceivedMessage
		want    string
	}{
		{
			name: "text message",
			msg: &ReceivedMessage{
				MsgType: MsgTypeText,
				Content: "Hello World",
			},
			want: "Hello World",
		},
		{
			name: "voice with recognition",
			msg: &ReceivedMessage{
				MsgType:     MsgTypeVoice,
				Recognition: "Voice text",
			},
			want: "Voice text",
		},
		{
			name: "voice without recognition",
			msg: &ReceivedMessage{
				MsgType: MsgTypeVoice,
			},
			want: "[语音消息]",
		},
		{
			name: "image message",
			msg: &ReceivedMessage{
				MsgType: MsgTypeImage,
			},
			want: "[图片消息]",
		},
		{
			name: "video message",
			msg: &ReceivedMessage{
				MsgType: MsgTypeVideo,
			},
			want: "[视频消息]",
		},
		{
			name: "location message",
			msg: &ReceivedMessage{
				MsgType: MsgTypeLocation,
			},
			want: "[位置消息]",
		},
		{
			name: "link message",
			msg: &ReceivedMessage{
				MsgType:     MsgTypeLink,
				Title:       "Link Title",
				Description: "Link Desc",
			},
			want: "Link Title Link Desc",
		},
		{
			name: "unknown type",
			msg: &ReceivedMessage{
				MsgType: "unknown",
			},
			want: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ParseMessageContent(tt.msg)
			if got != tt.want {
				t.Errorf("ParseMessageContent() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestNewTextMessage(t *testing.T) {
	msg := NewTextMessage(1000001, "user123", "Hello!")

	if msg.MsgType != "text" {
		t.Errorf("MsgType = %q, want %q", msg.MsgType, "text")
	}

	if msg.AgentID != 1000001 {
		t.Errorf("AgentID = %d, want %d", msg.AgentID, 1000001)
	}

	if msg.Text == nil {
		t.Fatal("Text should not be nil")
	}

	if msg.Text.Content != "Hello!" {
		t.Errorf("Text.Content = %q, want %q", msg.Text.Content, "Hello!")
	}
}

func TestNewMarkdownMessage(t *testing.T) {
	msg := NewMarkdownMessage(1000001, "**Bold** text")

	if msg.MsgType != "markdown" {
		t.Errorf("MsgType = %q, want %q", msg.MsgType, "markdown")
	}

	if msg.AgentID != 1000001 {
		t.Errorf("AgentID = %d, want %d", msg.AgentID, 1000001)
	}

	if msg.Card == nil {
		t.Fatal("Card should not be nil")
	}
}

func TestCardMessage_ToJSON(t *testing.T) {
	msg := NewTextMessage(1000001, "user123", "Hello!")

	data, err := msg.ToJSON()
	if err != nil {
		t.Fatalf("failed to convert to JSON: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("failed to unmarshal JSON: %v", err)
	}

	if decoded["msgtype"] != "text" {
		t.Errorf("msgtype = %v, want text", decoded["msgtype"])
	}
}

func TestMsgTypeConstants(t *testing.T) {
	tests := []struct {
		constant string
		value    string
	}{
		{MsgTypeText, "text"},
		{MsgTypeImage, "image"},
		{MsgTypeVoice, "voice"},
		{MsgTypeVideo, "video"},
		{MsgTypeLocation, "location"},
		{MsgTypeLink, "link"},
		{MsgTypeEvent, "event"},
	}

	for _, tt := range tests {
		if tt.constant != tt.value {
			t.Errorf("constant = %q, want %q", tt.constant, tt.value)
		}
	}
}

func TestEventTypeConstants(t *testing.T) {
	tests := []struct {
		constant string
		value    string
	}{
		{EventTypeSubscribe, "subscribe"},
		{EventTypeUnsubscribe, "unsubscribe"},
		{EventTypeEnterAgent, "enter_agent"},
		{EventTypeClick, "click"},
		{EventTypeView, "view"},
	}

	for _, tt := range tests {
		if tt.constant != tt.value {
			t.Errorf("constant = %q, want %q", tt.constant, tt.value)
		}
	}
}

func TestSendMessageRequest_JSON(t *testing.T) {
	req := &SendMessageRequest{
		ToUser:  "user123",
		MsgType: "text",
		AgentID: 1000001,
		Text: &TextContent{
			Content: "Hello!",
		},
	}

	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	if decoded["touser"] != "user123" {
		t.Errorf("touser = %v, want user123", decoded["touser"])
	}

	if decoded["msgtype"] != "text" {
		t.Errorf("msgtype = %v, want text", decoded["msgtype"])
	}

	text := decoded["text"].(map[string]interface{})
	if text["content"] != "Hello!" {
		t.Errorf("content = %v, want Hello!", text["content"])
	}
}

func TestTextCardContent_JSON(t *testing.T) {
	card := &TextCardContent{
		Title:       "Test Title",
		Description: "Test Description",
		URL:         "https://example.com",
		BtnTxt:      "View More",
	}

	data, err := json.Marshal(card)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	if decoded["title"] != "Test Title" {
		t.Errorf("title = %v, want Test Title", decoded["title"])
	}

	if decoded["description"] != "Test Description" {
		t.Errorf("description = %v, want Test Description", decoded["description"])
	}

	if decoded["url"] != "https://example.com" {
		t.Errorf("url = %v, want https://example.com", decoded["url"])
	}

	if decoded["btntxt"] != "View More" {
		t.Errorf("btntxt = %v, want View More", decoded["btntxt"])
	}
}
