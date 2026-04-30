package feishu

import (
	"fmt"
	"strings"
)

// Requirement represents a requirement for card rendering.
type Requirement struct {
	ID          string
	Title       string
	Description string
	Status      string
	Priority    string
	Category    string
}

// BuildRequirementsListCard builds a card showing a list of requirements.
func BuildRequirementsListCard(requirements []Requirement, page, totalPages, total int) *Card {
	builder := NewCardBuilder().
		SetHeader(fmt.Sprintf("📋 待确认需求 (%d)", total), "blue")

	if len(requirements) == 0 {
		builder.AddMarkdown("暂无待确认的需求 ✨")
	} else {
		for i, req := range requirements {
			// Requirement info
			content := fmt.Sprintf(
				"**%d. %s**\n%s\n\n`%s` | `%s` | ID: `%s`",
				(page-1)*5+i+1,
				req.Title,
				truncate(req.Description, 100),
				priorityLabel(req.Priority),
				categoryLabel(req.Category),
				req.ID,
			)
			builder.AddMarkdown(content)

			// Action buttons
			builder.AddActions(
				NewPrimaryButton("✓ 确认", map[string]interface{}{
					"action":         "confirm",
					"requirement_id": req.ID,
				}),
				NewDangerButton("✗ 拒绝", map[string]interface{}{
					"action":         "reject",
					"requirement_id": req.ID,
				}),
			)

			if i < len(requirements)-1 {
				builder.AddDivider()
			}
		}
	}

	// Pagination
	if totalPages > 1 {
		builder.AddDivider()

		var buttons []*CardButton
		if page > 1 {
			buttons = append(buttons, NewDefaultButton("◀ 上一页", map[string]interface{}{
				"action": "list_page",
				"page":   page - 1,
			}))
		}
		if page < totalPages {
			buttons = append(buttons, NewDefaultButton("下一页 ▶", map[string]interface{}{
				"action": "list_page",
				"page":   page + 1,
			}))
		}
		if len(buttons) > 0 {
			builder.AddActions(buttons...)
		}
	}

	builder.AddNote(fmt.Sprintf("第 %d/%d 页 | 共 %d 条", page, totalPages, total))

	return builder.Build()
}

// BuildRequirementDetailCard builds a card showing requirement details.
func BuildRequirementDetailCard(req Requirement, showActions bool) *Card {
	builder := NewCardBuilder().
		SetHeader(fmt.Sprintf("📝 %s", req.Title), statusColor(req.Status))

	content := fmt.Sprintf(
		"**描述：**\n%s\n\n**状态：** %s\n**优先级：** %s\n**分类：** %s\n**ID：** `%s`",
		req.Description,
		statusLabel(req.Status),
		priorityLabel(req.Priority),
		categoryLabel(req.Category),
		req.ID,
	)
	builder.AddMarkdown(content)

	if showActions && req.Status == "PENDING" {
		builder.AddDivider()
		builder.AddActions(
			NewPrimaryButton("✓ 确认", map[string]interface{}{
				"action":         "confirm",
				"requirement_id": req.ID,
			}),
			NewDangerButton("✗ 拒绝", map[string]interface{}{
				"action":         "reject",
				"requirement_id": req.ID,
			}),
		)
	}

	return builder.Build()
}

// BuildOperationResultCard builds a card showing operation result.
func BuildOperationResultCard(operation string, success bool, req *Requirement, errorMsg string) *Card {
	var title string
	var template string

	if success {
		switch operation {
		case "confirm":
			title = "✅ 需求已确认"
		case "reject":
			title = "❌ 需求已拒绝"
		default:
			title = "✅ 操作成功"
		}
		template = "green"
	} else {
		title = "⚠️ 操作失败"
		template = "red"
	}

	builder := NewCardBuilder().SetHeader(title, template)

	if success && req != nil {
		content := fmt.Sprintf("**%s**\n\nID: `%s`", req.Title, req.ID)
		builder.AddMarkdown(content)
	} else if !success {
		builder.AddMarkdown(fmt.Sprintf("错误: %s", errorMsg))
	}

	return builder.Build()
}

// BuildHelpCard builds a help card showing available commands.
func BuildHelpCard() *Card {
	builder := NewCardBuilder().
		SetHeader("🤖 Wisdoverse Cell 帮助", "blue")

	commands := `**命令列表：**

| 命令 | 说明 |
|------|------|
| /list | 查看待确认需求 |
| /confirm <ID> | 确认需求 |
| /reject <ID> [原因] | 拒绝需求 |
| /search <关键词> | 搜索需求 |
| /help | 显示帮助 |

**快捷触发：**

- 「待确认」「查看需求」→ 显示列表
- 「确认 <ID>」→ 确认需求
- 「拒绝 <ID>」→ 拒绝需求`

	builder.AddMarkdown(commands)
	builder.AddDivider()
	builder.AddNote("Wisdoverse Cell - AI Native OS")

	return builder.Build()
}

// Helper functions

func truncate(s string, max int) string {
	s = strings.ReplaceAll(s, "\n", " ")
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}

func priorityLabel(p string) string {
	switch p {
	case "P0":
		return "🔴 P0"
	case "P1":
		return "🟠 P1"
	case "P2":
		return "🟡 P2"
	case "P3":
		return "🟢 P3"
	default:
		return p
	}
}

func categoryLabel(c string) string {
	switch c {
	case "FEATURE":
		return "✨ 功能"
	case "BUG":
		return "🐛 Bug"
	case "IMPROVEMENT":
		return "📈 优化"
	case "QUESTION":
		return "❓ 问题"
	default:
		return c
	}
}

func statusLabel(s string) string {
	switch s {
	case "PENDING":
		return "⏳ 待确认"
	case "CONFIRMED":
		return "✅ 已确认"
	case "REJECTED":
		return "❌ 已拒绝"
	default:
		return s
	}
}

func statusColor(s string) string {
	switch s {
	case "PENDING":
		return "orange"
	case "CONFIRMED":
		return "green"
	case "REJECTED":
		return "red"
	default:
		return "blue"
	}
}
