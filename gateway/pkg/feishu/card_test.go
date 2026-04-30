package feishu

import (
	"encoding/json"
	"testing"
)

func TestNewDivider(t *testing.T) {
	d := NewDivider()

	if d.Tag != "hr" {
		t.Errorf("tag = %q, want %q", d.Tag, "hr")
	}
}

func TestNewMarkdown(t *testing.T) {
	content := "**Bold** text"
	md := NewMarkdown(content)

	if md.Tag != "markdown" {
		t.Errorf("tag = %q, want %q", md.Tag, "markdown")
	}

	if md.Content != content {
		t.Errorf("content = %q, want %q", md.Content, content)
	}
}

func TestNewButton(t *testing.T) {
	text := "Click me"
	btnType := "primary"
	value := map[string]interface{}{"action": "test"}

	btn := NewButton(text, btnType, value)

	if btn.Tag != "button" {
		t.Errorf("tag = %q, want %q", btn.Tag, "button")
	}

	if btn.Text.Content != text {
		t.Errorf("text.content = %q, want %q", btn.Text.Content, text)
	}

	if btn.Type != btnType {
		t.Errorf("type = %q, want %q", btn.Type, btnType)
	}

	if btn.Value["action"] != "test" {
		t.Errorf("value[action] = %v, want test", btn.Value["action"])
	}
}

func TestNewPrimaryButton(t *testing.T) {
	btn := NewPrimaryButton("Submit", map[string]interface{}{"id": "123"})

	if btn.Type != "primary" {
		t.Errorf("type = %q, want primary", btn.Type)
	}
}

func TestNewDangerButton(t *testing.T) {
	btn := NewDangerButton("Delete", map[string]interface{}{"id": "456"})

	if btn.Type != "danger" {
		t.Errorf("type = %q, want danger", btn.Type)
	}
}

func TestCard_JSONStructure(t *testing.T) {
	card := &Card{
		Config: &CardConfig{
			WideScreenMode: true,
			EnableForward:  false,
		},
		Header: &CardHeader{
			Title:    &CardText{Tag: "plain_text", Content: "Test Card"},
			Template: "blue",
		},
		Elements: []interface{}{
			NewMarkdown("Hello **world**"),
			NewDivider(),
		},
	}

	data, err := json.Marshal(card)
	if err != nil {
		t.Fatalf("failed to marshal card: %v", err)
	}

	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}

	// Check config
	config := decoded["config"].(map[string]interface{})
	if config["wide_screen_mode"] != true {
		t.Error("wide_screen_mode should be true")
	}

	// Check header
	header := decoded["header"].(map[string]interface{})
	if header["template"] != "blue" {
		t.Errorf("template = %v, want blue", header["template"])
	}

	// Check elements count
	elements := decoded["elements"].([]interface{})
	if len(elements) != 2 {
		t.Errorf("elements count = %d, want 2", len(elements))
	}
}

func TestCardText_TagOptions(t *testing.T) {
	tests := []struct {
		tag     string
		content string
	}{
		{"plain_text", "Plain text content"},
		{"lark_md", "**Markdown** content"},
	}

	for _, tt := range tests {
		t.Run(tt.tag, func(t *testing.T) {
			text := &CardText{Tag: tt.tag, Content: tt.content}
			data, _ := json.Marshal(text)

			var decoded map[string]string
			_ = json.Unmarshal(data, &decoded)

			if decoded["tag"] != tt.tag {
				t.Errorf("tag = %q, want %q", decoded["tag"], tt.tag)
			}
		})
	}
}

func TestCardActionBlock(t *testing.T) {
	block := &CardActionBlock{
		Tag:    "action",
		Layout: "bisected",
		Actions: []CardButton{
			*NewPrimaryButton("Confirm", map[string]interface{}{"action": "confirm"}),
			*NewDangerButton("Reject", map[string]interface{}{"action": "reject"}),
		},
	}

	data, err := json.Marshal(block)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	var decoded map[string]interface{}
	_ = json.Unmarshal(data, &decoded)

	if decoded["tag"] != "action" {
		t.Errorf("tag = %v, want action", decoded["tag"])
	}

	if decoded["layout"] != "bisected" {
		t.Errorf("layout = %v, want bisected", decoded["layout"])
	}

	actions := decoded["actions"].([]interface{})
	if len(actions) != 2 {
		t.Errorf("actions count = %d, want 2", len(actions))
	}
}

func TestCardDiv_WithFields(t *testing.T) {
	div := &CardDiv{
		Tag: "div",
		Fields: []CardField{
			{
				IsShort: true,
				Text:    &CardText{Tag: "lark_md", Content: "**Label:** Value"},
			},
			{
				IsShort: true,
				Text:    &CardText{Tag: "lark_md", Content: "**Status:** Active"},
			},
		},
	}

	data, err := json.Marshal(div)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	var decoded map[string]interface{}
	_ = json.Unmarshal(data, &decoded)

	if decoded["tag"] != "div" {
		t.Errorf("tag = %v, want div", decoded["tag"])
	}

	fields := decoded["fields"].([]interface{})
	if len(fields) != 2 {
		t.Errorf("fields count = %d, want 2", len(fields))
	}
}

func TestCardNote(t *testing.T) {
	note := &CardNote{
		Tag: "note",
		Elements: []CardText{
			{Tag: "plain_text", Content: "Note: This is important"},
		},
	}

	data, err := json.Marshal(note)
	if err != nil {
		t.Fatalf("failed to marshal: %v", err)
	}

	var decoded map[string]interface{}
	_ = json.Unmarshal(data, &decoded)

	if decoded["tag"] != "note" {
		t.Errorf("tag = %v, want note", decoded["tag"])
	}
}
