// Package service contains business logic for the gateway.
package service

import (
	"regexp"
	"strings"
)

// SkillMatch represents a matched skill with parameters.
type SkillMatch struct {
	SkillName  string
	Confidence float64
	Parameters map[string]string
	MatchType  string // "command", "pattern"
}

// Matcher handles command and pattern matching for skills.
type Matcher struct {
	commands map[string]string          // command -> skill name
	patterns map[string]*regexp.Regexp  // skill name -> pattern
}

// NewMatcher creates a new skill matcher with predefined skills.
func NewMatcher() *Matcher {
	m := &Matcher{
		commands: make(map[string]string),
		patterns: make(map[string]*regexp.Regexp),
	}

	// Register commands
	m.RegisterCommand("/list", "list")
	m.RegisterCommand("/需求", "list")
	m.RegisterCommand("/confirm", "confirm")
	m.RegisterCommand("/reject", "reject")
	m.RegisterCommand("/help", "help")
	m.RegisterCommand("/skills", "help")
	m.RegisterCommand("/export_prd", "export_prd")
	m.RegisterCommand("/prd", "export_prd")
	m.RegisterCommand("/search", "search")
	m.RegisterCommand("/stats", "stats")

	// Register patterns
	m.RegisterPattern("list", `(?i)^(查看|列出|显示).*(需求|待确认)`)
	m.RegisterPattern("list", `(?i)^待确认`)
	m.RegisterPattern("confirm", `(?i)^确认\s+(req_\w+|REQ_\w+)`)
	m.RegisterPattern("reject", `(?i)^拒绝\s+(req_\w+|REQ_\w+)`)
	m.RegisterPattern("help", `(?i)^(有什么技能|能做什么|帮助)`)

	return m
}

// RegisterCommand registers a command -> skill mapping.
func (m *Matcher) RegisterCommand(command, skillName string) {
	m.commands[strings.ToLower(command)] = skillName
}

// RegisterPattern registers a regex pattern for a skill.
func (m *Matcher) RegisterPattern(skillName, pattern string) {
	re, err := regexp.Compile(pattern)
	if err != nil {
		return
	}
	m.patterns[skillName+"_"+pattern] = re
}

// Match attempts to match a message to a skill.
func (m *Matcher) Match(message string) *SkillMatch {
	message = strings.TrimSpace(message)
	if message == "" {
		return nil
	}

	// 1. Command matching (highest priority)
	if match := m.matchCommand(message); match != nil {
		return match
	}

	// 2. Pattern matching
	if match := m.matchPattern(message); match != nil {
		return match
	}

	return nil
}

// matchCommand checks if message starts with a registered command.
func (m *Matcher) matchCommand(message string) *SkillMatch {
	parts := strings.Fields(message)
	if len(parts) == 0 {
		return nil
	}

	cmd := strings.ToLower(parts[0])
	skillName, ok := m.commands[cmd]
	if !ok {
		return nil
	}

	params := make(map[string]string)

	// Parse command-specific parameters
	switch skillName {
	case "confirm":
		if len(parts) > 1 {
			params["requirement_id"] = parts[1]
		}
	case "reject":
		if len(parts) > 1 {
			params["requirement_id"] = parts[1]
		}
		if len(parts) > 2 {
			params["reason"] = strings.Join(parts[2:], " ")
		}
	case "search":
		if len(parts) > 1 {
			params["keyword"] = strings.Join(parts[1:], " ")
		}
	case "list":
		// Check for page parameter: /list 2
		if len(parts) > 1 {
			params["page"] = parts[1]
		}
	}

	return &SkillMatch{
		SkillName:  skillName,
		Confidence: 1.0,
		Parameters: params,
		MatchType:  "command",
	}
}

// matchPattern checks if message matches any registered pattern.
func (m *Matcher) matchPattern(message string) *SkillMatch {
	for key, re := range m.patterns {
		matches := re.FindStringSubmatch(message)
		if matches != nil {
			// Extract skill name from key (format: "skillname_pattern")
			skillName := strings.Split(key, "_")[0]

			params := make(map[string]string)

			// Extract captured groups as parameters
			if len(matches) > 1 {
				switch skillName {
				case "confirm", "reject":
					params["requirement_id"] = matches[1]
				}
			}

			return &SkillMatch{
				SkillName:  skillName,
				Confidence: 0.8,
				Parameters: params,
				MatchType:  "pattern",
			}
		}
	}
	return nil
}

// IsCommand checks if the message starts with a command prefix.
func IsCommand(message string) bool {
	return strings.HasPrefix(strings.TrimSpace(message), "/")
}
