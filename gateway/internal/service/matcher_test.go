package service

import (
	"testing"
)

func TestMatcher_CommandMatching(t *testing.T) {
	m := NewMatcher()

	tests := []struct {
		name       string
		message    string
		wantSkill  string
		wantParams map[string]string
	}{
		{
			name:      "list command",
			message:   "/list",
			wantSkill: "list",
		},
		{
			name:      "list command with page",
			message:   "/list 2",
			wantSkill: "list",
			wantParams: map[string]string{
				"page": "2",
			},
		},
		{
			name:      "chinese list command",
			message:   "/需求",
			wantSkill: "list",
		},
		{
			name:      "confirm command",
			message:   "/confirm req_abc123",
			wantSkill: "confirm",
			wantParams: map[string]string{
				"requirement_id": "req_abc123",
			},
		},
		{
			name:      "reject command with reason",
			message:   "/reject req_abc123 不符合规划",
			wantSkill: "reject",
			wantParams: map[string]string{
				"requirement_id": "req_abc123",
				"reason":         "不符合规划",
			},
		},
		{
			name:      "help command",
			message:   "/help",
			wantSkill: "help",
		},
		{
			name:      "skills command",
			message:   "/skills",
			wantSkill: "help",
		},
		{
			name:      "search command",
			message:   "/search 录音功能",
			wantSkill: "search",
			wantParams: map[string]string{
				"keyword": "录音功能",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			match := m.Match(tt.message)

			if match == nil {
				t.Fatalf("expected match for %q, got nil", tt.message)
			}

			if match.SkillName != tt.wantSkill {
				t.Errorf("skill = %q, want %q", match.SkillName, tt.wantSkill)
			}

			if match.MatchType != "command" {
				t.Errorf("match_type = %q, want %q", match.MatchType, "command")
			}

			for key, wantVal := range tt.wantParams {
				if gotVal := match.Parameters[key]; gotVal != wantVal {
					t.Errorf("param[%s] = %q, want %q", key, gotVal, wantVal)
				}
			}
		})
	}
}

func TestMatcher_PatternMatching(t *testing.T) {
	m := NewMatcher()

	tests := []struct {
		name       string
		message    string
		wantSkill  string
		wantParams map[string]string
	}{
		{
			name:      "chinese list pattern",
			message:   "查看需求",
			wantSkill: "list",
		},
		{
			name:      "chinese list pattern 2",
			message:   "显示待确认需求",
			wantSkill: "list",
		},
		{
			name:      "pending pattern",
			message:   "待确认",
			wantSkill: "list",
		},
		{
			name:      "confirm pattern",
			message:   "确认 req_abc123",
			wantSkill: "confirm",
			wantParams: map[string]string{
				"requirement_id": "req_abc123",
			},
		},
		{
			name:      "reject pattern",
			message:   "拒绝 REQ_ABC123",
			wantSkill: "reject",
			wantParams: map[string]string{
				"requirement_id": "REQ_ABC123",
			},
		},
		{
			name:      "help pattern",
			message:   "有什么技能",
			wantSkill: "help",
		},
		{
			name:      "help pattern 2",
			message:   "能做什么",
			wantSkill: "help",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			match := m.Match(tt.message)

			if match == nil {
				t.Fatalf("expected match for %q, got nil", tt.message)
			}

			if match.SkillName != tt.wantSkill {
				t.Errorf("skill = %q, want %q", match.SkillName, tt.wantSkill)
			}

			if match.MatchType != "pattern" {
				t.Errorf("match_type = %q, want %q", match.MatchType, "pattern")
			}

			for key, wantVal := range tt.wantParams {
				if gotVal := match.Parameters[key]; gotVal != wantVal {
					t.Errorf("param[%s] = %q, want %q", key, gotVal, wantVal)
				}
			}
		})
	}
}

func TestMatcher_NoMatch(t *testing.T) {
	m := NewMatcher()

	messages := []string{
		"hello",
		"random message",
		"今天天气不错",
		"",
		"   ",
	}

	for _, msg := range messages {
		t.Run(msg, func(t *testing.T) {
			match := m.Match(msg)
			if match != nil {
				t.Errorf("expected no match for %q, got %+v", msg, match)
			}
		})
	}
}

func TestIsCommand(t *testing.T) {
	tests := []struct {
		message string
		want    bool
	}{
		{"/list", true},
		{"/help", true},
		{"  /list", true},
		{"hello", false},
		{"list", false},
		{"", false},
	}

	for _, tt := range tests {
		t.Run(tt.message, func(t *testing.T) {
			if got := IsCommand(tt.message); got != tt.want {
				t.Errorf("IsCommand(%q) = %v, want %v", tt.message, got, tt.want)
			}
		})
	}
}
