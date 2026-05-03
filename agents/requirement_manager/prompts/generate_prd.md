You are a technical documentation expert. Generate a professional product
requirements document (PRD).

## Project Information
Project name: {project_name}
Version: {version}
Generated date: {date}
Total requirements: {total_requirements}

## Requirements
{requirements_json}

## Task
Generate a clear, professional PRD from the requirement list above. Write the
PRD in the dominant language of the input requirements.

## Output Format (Markdown)

```markdown
# {project_name} - Product Requirements Document

> Version: {version}
> Generated date: {date}
> Status: Auto-generated

---

## 1. Document Overview

### 1.1 Purpose
[Briefly explain the purpose of this document]

### 1.2 Requirement Statistics
| Status | Count |
|--------|-------|
| Confirmed | X |
| Pending confirmation | X |
| Changed | X |

| Priority | Count |
|----------|-------|
| High | X |
| Medium | X |
| Low | X |

---

## 2. Requirement Overview

| ID | Title | Category | Priority | Status |
|----|-------|----------|----------|--------|
[Requirements table sorted by category]

---

## 3. Functional Requirements

### 3.1 [Category Name]

#### REQ-XXX: [Requirement Title]
- **Priority**: [High/Medium/Low]
- **Status**: [Confirmed/Pending confirmation]
- **Description**: [Detailed description]
- **Source**: [Original quote if available]

[Repeat the format above for all requirements, grouped by category]

---

## 4. Non-Functional Requirements

[List performance, security, or other non-functional requirements separately when present]

---

## 5. Open Questions

[List all questions that still need confirmation]

---

## 6. Appendix

### 6.1 Glossary
[Explain domain-specific terms when needed]

### 6.2 Change History
| Date | Version | Change |
|------|---------|--------|
| {date} | {version} | Initial generation |
```

## Generation Principles
1. Group related requirements by category.
2. Put high-priority requirements first within each category.
3. Keep a professional, concise technical-documentation style.
4. If a requirement description is incomplete, add it to Open Questions.
5. Use stable IDs for traceability, such as REQ-001 and REQ-002.

## Notes
- Output the Markdown document only; do not add extra explanation.
- Ensure Markdown formatting is valid and tables are aligned.
- Preserve all key information from the original requirements.
