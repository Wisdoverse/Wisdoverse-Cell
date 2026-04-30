package feishu

import (
	"encoding/json"
	"strings"
	"testing"
)

// cardJSON marshals a card to JSON string for substring checks.
func cardJSON(t *testing.T, card *Card) string {
	t.Helper()
	b, err := json.Marshal(card)
	if err != nil {
		t.Fatalf("marshal card: %v", err)
	}
	return string(b)
}

// --- BuildRequirementsListCard ---

func TestBuildRequirementsListCard_Empty(t *testing.T) {
	card := BuildRequirementsListCard(nil, 1, 1, 0)
	js := cardJSON(t, card)

	if !strings.Contains(js, "暂无待确认的需求 ✨") {
		t.Error("empty list card should contain empty message")
	}
	if !strings.Contains(js, "📋 待确认需求 (0)") {
		t.Error("header should show total count 0")
	}
}

func TestBuildRequirementsListCard_WithItems(t *testing.T) {
	reqs := []Requirement{
		{ID: "req-001", Title: "Login Feature", Description: "Add login", Status: "PENDING", Priority: "P0", Category: "FEATURE"},
		{ID: "req-002", Title: "Fix Bug", Description: "Fix crash", Status: "PENDING", Priority: "P1", Category: "BUG"},
	}
	card := BuildRequirementsListCard(reqs, 1, 1, 2)
	js := cardJSON(t, card)

	// Header shows total
	if !strings.Contains(js, "📋 待确认需求 (2)") {
		t.Error("header should show total count 2")
	}
	// Requirement titles present
	if !strings.Contains(js, "Login Feature") {
		t.Error("should contain first requirement title")
	}
	if !strings.Contains(js, "Fix Bug") {
		t.Error("should contain second requirement title")
	}
	// Confirm/reject buttons
	if !strings.Contains(js, "✓ 确认") {
		t.Error("should contain confirm button text")
	}
	if !strings.Contains(js, "✗ 拒绝") {
		t.Error("should contain reject button text")
	}
	// Requirement IDs in button values
	if !strings.Contains(js, "req-001") {
		t.Error("should contain first requirement ID")
	}
	if !strings.Contains(js, "req-002") {
		t.Error("should contain second requirement ID")
	}
	// Note footer
	if !strings.Contains(js, "第 1/1 页 | 共 2 条") {
		t.Error("should contain page note")
	}
}

func TestBuildRequirementsListCard_Pagination(t *testing.T) {
	tests := []struct {
		name       string
		page       int
		totalPages int
		wantPrev   bool
		wantNext   bool
	}{
		{"first page", 1, 3, false, true},
		{"middle page", 2, 3, true, true},
		{"last page", 3, 3, true, false},
		{"single page", 1, 1, false, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			reqs := []Requirement{{ID: "r1", Title: "T", Description: "D", Priority: "P0", Category: "FEATURE"}}
			card := BuildRequirementsListCard(reqs, tt.page, tt.totalPages, 15)
			js := cardJSON(t, card)

			hasPrev := strings.Contains(js, "◀ 上一页")
			hasNext := strings.Contains(js, "下一页 ▶")

			if hasPrev != tt.wantPrev {
				t.Errorf("prev button: got %v, want %v", hasPrev, tt.wantPrev)
			}
			if hasNext != tt.wantNext {
				t.Errorf("next button: got %v, want %v", hasNext, tt.wantNext)
			}
		})
	}
}

// --- BuildRequirementDetailCard ---

func TestBuildRequirementDetailCard(t *testing.T) {
	t.Run("with actions and PENDING status", func(t *testing.T) {
		req := Requirement{ID: "req-100", Title: "My Feature", Description: "Detailed desc", Status: "PENDING", Priority: "P1", Category: "IMPROVEMENT"}
		card := BuildRequirementDetailCard(req, true)
		js := cardJSON(t, card)

		if !strings.Contains(js, "📝 My Feature") {
			t.Error("header should contain title")
		}
		// PENDING → orange header
		if card.Header.Template != "orange" {
			t.Errorf("header template: got %s, want orange", card.Header.Template)
		}
		if !strings.Contains(js, "✓ 确认") {
			t.Error("should show confirm button for PENDING with showActions=true")
		}
		if !strings.Contains(js, "✗ 拒绝") {
			t.Error("should show reject button for PENDING with showActions=true")
		}
		if !strings.Contains(js, "⏳ 待确认") {
			t.Error("should show status label")
		}
		if !strings.Contains(js, "🟠 P1") {
			t.Error("should show priority label")
		}
		if !strings.Contains(js, "📈 优化") {
			t.Error("should show category label")
		}
	})

	t.Run("without actions", func(t *testing.T) {
		req := Requirement{ID: "req-200", Title: "Another", Description: "Desc", Status: "PENDING", Priority: "P2", Category: "BUG"}
		card := BuildRequirementDetailCard(req, false)
		js := cardJSON(t, card)

		if strings.Contains(js, "✓ 确认") {
			t.Error("should not show confirm button when showActions=false")
		}
	})

	t.Run("confirmed status hides actions even if showActions true", func(t *testing.T) {
		req := Requirement{ID: "req-300", Title: "Done", Description: "Done desc", Status: "CONFIRMED", Priority: "P0", Category: "FEATURE"}
		card := BuildRequirementDetailCard(req, true)
		js := cardJSON(t, card)

		if strings.Contains(js, "✓ 确认") {
			t.Error("should not show confirm button for CONFIRMED status")
		}
		if card.Header.Template != "green" {
			t.Errorf("header template: got %s, want green", card.Header.Template)
		}
	})
}

// --- BuildOperationResultCard ---

func TestBuildOperationResultCard(t *testing.T) {
	t.Run("confirm success", func(t *testing.T) {
		req := &Requirement{ID: "req-1", Title: "My Req"}
		card := BuildOperationResultCard("confirm", true, req, "")
		js := cardJSON(t, card)

		if !strings.Contains(js, "✅ 需求已确认") {
			t.Error("should show confirm success title")
		}
		if card.Header.Template != "green" {
			t.Errorf("header template: got %s, want green", card.Header.Template)
		}
		if !strings.Contains(js, "My Req") {
			t.Error("should contain requirement title")
		}
	})

	t.Run("reject success", func(t *testing.T) {
		req := &Requirement{ID: "req-2", Title: "Rejected Req"}
		card := BuildOperationResultCard("reject", true, req, "")
		js := cardJSON(t, card)

		if !strings.Contains(js, "❌ 需求已拒绝") {
			t.Error("should show reject success title")
		}
	})

	t.Run("generic success", func(t *testing.T) {
		card := BuildOperationResultCard("other_op", true, nil, "")
		js := cardJSON(t, card)

		if !strings.Contains(js, "✅ 操作成功") {
			t.Error("should show generic success title")
		}
	})

	t.Run("failure", func(t *testing.T) {
		card := BuildOperationResultCard("confirm", false, nil, "not found")
		js := cardJSON(t, card)

		if !strings.Contains(js, "⚠️ 操作失败") {
			t.Error("should show failure title")
		}
		if card.Header.Template != "red" {
			t.Errorf("header template: got %s, want red", card.Header.Template)
		}
		if !strings.Contains(js, "错误: not found") {
			t.Error("should contain error message")
		}
	})
}

// --- BuildHelpCard ---

func TestBuildHelpCard(t *testing.T) {
	card := BuildHelpCard()
	js := cardJSON(t, card)

	commands := []string{"/list", "/confirm", "/reject", "/search", "/help"}
	for _, cmd := range commands {
		if !strings.Contains(js, cmd) {
			t.Errorf("help card should contain command %s", cmd)
		}
	}

	if !strings.Contains(js, "🤖 Wisdoverse Cell 帮助") {
		t.Error("header should match expected title")
	}
	if !strings.Contains(js, "Wisdoverse Cell - AI Native OS") {
		t.Error("should contain note text")
	}
}

// --- truncate ---

func TestTruncate(t *testing.T) {
	tests := []struct {
		name   string
		input  string
		max    int
		expect string
	}{
		{"short string", "hello", 10, "hello"},
		{"exact length", "hello", 5, "hello"},
		{"too long", "hello world", 5, "hello..."},
		{"newlines replaced", "line1\nline2\nline3", 50, "line1 line2 line3"},
		{"long with newlines", "abcde\nfghij", 8, "abcde fg..."},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := truncate(tt.input, tt.max)
			if got != tt.expect {
				t.Errorf("truncate(%q, %d) = %q, want %q", tt.input, tt.max, got, tt.expect)
			}
		})
	}
}

// --- Label helpers ---

func TestLabelHelpers(t *testing.T) {
	t.Run("priorityLabel", func(t *testing.T) {
		tests := []struct {
			input, want string
		}{
			{"P0", "🔴 P0"},
			{"P1", "🟠 P1"},
			{"P2", "🟡 P2"},
			{"P3", "🟢 P3"},
			{"UNKNOWN", "UNKNOWN"},
		}
		for _, tt := range tests {
			got := priorityLabel(tt.input)
			if got != tt.want {
				t.Errorf("priorityLabel(%q) = %q, want %q", tt.input, got, tt.want)
			}
		}
	})

	t.Run("categoryLabel", func(t *testing.T) {
		tests := []struct {
			input, want string
		}{
			{"FEATURE", "✨ 功能"},
			{"BUG", "🐛 Bug"},
			{"IMPROVEMENT", "📈 优化"},
			{"QUESTION", "❓ 问题"},
			{"OTHER", "OTHER"},
		}
		for _, tt := range tests {
			got := categoryLabel(tt.input)
			if got != tt.want {
				t.Errorf("categoryLabel(%q) = %q, want %q", tt.input, got, tt.want)
			}
		}
	})

	t.Run("statusLabel", func(t *testing.T) {
		tests := []struct {
			input, want string
		}{
			{"PENDING", "⏳ 待确认"},
			{"CONFIRMED", "✅ 已确认"},
			{"REJECTED", "❌ 已拒绝"},
			{"UNKNOWN", "UNKNOWN"},
		}
		for _, tt := range tests {
			got := statusLabel(tt.input)
			if got != tt.want {
				t.Errorf("statusLabel(%q) = %q, want %q", tt.input, got, tt.want)
			}
		}
	})

	t.Run("statusColor", func(t *testing.T) {
		tests := []struct {
			input, want string
		}{
			{"PENDING", "orange"},
			{"CONFIRMED", "green"},
			{"REJECTED", "red"},
			{"UNKNOWN", "blue"},
		}
		for _, tt := range tests {
			got := statusColor(tt.input)
			if got != tt.want {
				t.Errorf("statusColor(%q) = %q, want %q", tt.input, got, tt.want)
			}
		}
	})
}
