use regex::Regex;
use std::collections::HashMap;

#[derive(Clone, Debug, PartialEq)]
pub struct SkillMatch {
    pub skill_name: String,
    pub confidence: f64,
    pub parameters: HashMap<String, String>,
    pub match_type: MatchType,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum MatchType {
    Command,
    Pattern,
}

#[derive(Clone, Default)]
pub struct Matcher {
    commands: HashMap<String, String>,
    patterns: Vec<(String, Regex)>,
}

impl Matcher {
    pub fn new() -> Self {
        let mut matcher = Self::default();

        matcher.register_command("/list", "list");
        matcher.register_command("/需求", "list");
        matcher.register_command("/confirm", "confirm");
        matcher.register_command("/reject", "reject");
        matcher.register_command("/help", "help");
        matcher.register_command("/skills", "help");
        matcher.register_command("/export_prd", "export_prd");
        matcher.register_command("/prd", "export_prd");
        matcher.register_command("/search", "search");
        matcher.register_command("/stats", "stats");

        matcher.register_pattern("list", r"(?i)^(查看|列出|显示).*(需求|待确认)");
        matcher.register_pattern("list", r"(?i)^待确认");
        matcher.register_pattern("confirm", r"(?i)^确认\s+(req_\w+|REQ_\w+)");
        matcher.register_pattern("reject", r"(?i)^拒绝\s+(req_\w+|REQ_\w+)");
        matcher.register_pattern("help", r"(?i)^(有什么技能|能做什么|帮助)");

        matcher
    }

    pub fn register_command(&mut self, command: &str, skill_name: &str) {
        self.commands
            .insert(command.to_lowercase(), skill_name.to_string());
    }

    pub fn register_pattern(&mut self, skill_name: &str, pattern: &str) {
        if let Ok(pattern) = Regex::new(pattern) {
            self.patterns.push((skill_name.to_string(), pattern));
        }
    }

    pub fn match_message(&self, message: &str) -> Option<SkillMatch> {
        let message = message.trim();
        if message.is_empty() {
            return None;
        }

        self.match_command(message)
            .or_else(|| self.match_pattern(message))
    }

    fn match_command(&self, message: &str) -> Option<SkillMatch> {
        let parts = message.split_whitespace().collect::<Vec<_>>();
        let command = parts.first()?.to_lowercase();
        let skill_name = self.commands.get(&command)?.clone();
        let mut parameters = HashMap::new();

        match skill_name.as_str() {
            "confirm" => {
                if let Some(requirement_id) = parts.get(1) {
                    parameters.insert("requirement_id".to_string(), (*requirement_id).to_string());
                }
            }
            "reject" => {
                if let Some(requirement_id) = parts.get(1) {
                    parameters.insert("requirement_id".to_string(), (*requirement_id).to_string());
                }
                if parts.len() > 2 {
                    parameters.insert("reason".to_string(), parts[2..].join(" "));
                }
            }
            "search" => {
                if parts.len() > 1 {
                    parameters.insert("keyword".to_string(), parts[1..].join(" "));
                }
            }
            "list" => {
                if let Some(page) = parts.get(1) {
                    parameters.insert("page".to_string(), (*page).to_string());
                }
            }
            _ => {}
        }

        Some(SkillMatch {
            skill_name,
            confidence: 1.0,
            parameters,
            match_type: MatchType::Command,
        })
    }

    fn match_pattern(&self, message: &str) -> Option<SkillMatch> {
        for (skill_name, pattern) in &self.patterns {
            let Some(captures) = pattern.captures(message) else {
                continue;
            };
            let mut parameters = HashMap::new();

            if matches!(skill_name.as_str(), "confirm" | "reject") {
                if let Some(requirement_id) = captures.get(1) {
                    parameters.insert(
                        "requirement_id".to_string(),
                        requirement_id.as_str().to_string(),
                    );
                }
            }

            return Some(SkillMatch {
                skill_name: skill_name.clone(),
                confidence: 0.8,
                parameters,
                match_type: MatchType::Pattern,
            });
        }

        None
    }
}

pub fn is_command(message: &str) -> bool {
    message.trim_start().starts_with('/')
}

#[cfg(test)]
mod tests {
    use super::{is_command, MatchType, Matcher};
    use std::collections::HashMap;

    #[test]
    fn command_matching_matches_gateway_contract() {
        let matcher = Matcher::new();
        let cases = [
            ("list command", "/list", "list", HashMap::new()),
            (
                "list command with page",
                "/list 2",
                "list",
                HashMap::from([("page", "2")]),
            ),
            ("chinese list command", "/需求", "list", HashMap::new()),
            (
                "confirm command",
                "/confirm req_abc123",
                "confirm",
                HashMap::from([("requirement_id", "req_abc123")]),
            ),
            (
                "reject command with reason",
                "/reject req_abc123 不符合规划",
                "reject",
                HashMap::from([("requirement_id", "req_abc123"), ("reason", "不符合规划")]),
            ),
            ("help command", "/help", "help", HashMap::new()),
            ("skills command", "/skills", "help", HashMap::new()),
            (
                "search command",
                "/search 录音功能",
                "search",
                HashMap::from([("keyword", "录音功能")]),
            ),
        ];

        for (name, message, skill_name, parameters) in cases {
            let matched = matcher.match_message(message).unwrap_or_else(|| {
                panic!("expected match for {name}");
            });
            assert_eq!(matched.skill_name, skill_name, "{name}");
            assert_eq!(matched.match_type, MatchType::Command, "{name}");
            for (key, expected) in parameters {
                assert_eq!(
                    matched.parameters.get(key).map(String::as_str),
                    Some(expected),
                    "{name}"
                );
            }
        }
    }

    #[test]
    fn pattern_matching_matches_gateway_contract() {
        let matcher = Matcher::new();
        let cases = [
            ("chinese list pattern", "查看需求", "list", HashMap::new()),
            (
                "chinese list pattern 2",
                "显示待确认需求",
                "list",
                HashMap::new(),
            ),
            ("pending pattern", "待确认", "list", HashMap::new()),
            (
                "confirm pattern",
                "确认 req_abc123",
                "confirm",
                HashMap::from([("requirement_id", "req_abc123")]),
            ),
            (
                "reject pattern",
                "拒绝 REQ_ABC123",
                "reject",
                HashMap::from([("requirement_id", "REQ_ABC123")]),
            ),
            ("help pattern", "有什么技能", "help", HashMap::new()),
            ("help pattern 2", "能做什么", "help", HashMap::new()),
        ];

        for (name, message, skill_name, parameters) in cases {
            let matched = matcher.match_message(message).unwrap_or_else(|| {
                panic!("expected match for {name}");
            });
            assert_eq!(matched.skill_name, skill_name, "{name}");
            assert_eq!(matched.match_type, MatchType::Pattern, "{name}");
            for (key, expected) in parameters {
                assert_eq!(
                    matched.parameters.get(key).map(String::as_str),
                    Some(expected),
                    "{name}"
                );
            }
        }
    }

    #[test]
    fn unmatched_messages_return_none() {
        let matcher = Matcher::new();

        for message in ["hello", "random message", "今天天气不错", "", "   "] {
            assert_eq!(matcher.match_message(message), None, "{message}");
        }
    }

    #[test]
    fn detects_slash_commands() {
        assert!(is_command("/list"));
        assert!(is_command("/help"));
        assert!(is_command("  /list"));
        assert!(!is_command("hello"));
        assert!(!is_command("list"));
        assert!(!is_command(""));
    }
}
