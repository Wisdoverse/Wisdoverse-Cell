"""
Requirement analyzer.

Provides automatic categorization, priority recommendations, complexity
estimation, and dependency analysis.
"""
from datetime import UTC, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from shared.infra.llm_gateway import llm_gateway
from shared.utils.logger import get_logger

logger = get_logger("analyzer")


class AnalysisResult(BaseModel):
    """Analysis result."""
    model_config = ConfigDict(from_attributes=True)

    # Category recommendation.
    suggested_category: str
    category_confidence: float  # 0-1

    # Priority recommendation.
    suggested_priority: str  # high/medium/low
    priority_reasons: list[str]
    priority_confidence: float

    # Complexity estimate.
    complexity: str  # S/M/L/XL
    complexity_factors: list[str]
    estimated_effort_days: Optional[int] = None

    # Dependency analysis.
    dependencies: list[str]  # Requirement IDs or descriptions this depends on.
    blockers: list[str]  # Blocking factors.

    # Risk assessment.
    risk_level: str  # low/medium/high
    risk_factors: list[str]

    # Tag recommendations.
    suggested_tags: list[str]

    # Analysis timestamp.
    analyzed_at: datetime


class RequirementAnalyzer:
    """
    Intelligent requirement analyzer.

    Capabilities:
    - Automatic categorization
    - Priority recommendations
    - Complexity estimates
    - Dependency detection
    - Risk assessment
    """

    # Keyword-to-priority mapping.
    PRIORITY_KEYWORDS = {
        "high": [
            "必须", "一定要", "紧急", "立即", "关键", "核心",
            "must", "critical", "urgent", "blocker", "P0"
        ],
        "medium": [
            "应该", "需要", "重要", "建议",
            "should", "important", "P1", "P2"
        ],
        "low": [
            "可以", "最好", "将来", "后续", "优化",
            "nice to have", "future", "optional", "P3"
        ]
    }

    # Complexity keywords.
    COMPLEXITY_KEYWORDS = {
        "XL": ["重构", "架构", "迁移", "全面", "系统级"],
        "L": ["集成", "多模块", "复杂", "跨团队"],
        "M": ["新功能", "模块", "接口", "API"],
        "S": ["修复", "调整", "优化", "配置", "简单"]
    }

    # Category keywords.
    CATEGORY_KEYWORDS = {
        "功能": ["功能", "特性", "feature", "支持", "实现"],
        "性能": ["性能", "速度", "延迟", "优化", "performance"],
        "安全": ["安全", "权限", "加密", "认证", "security"],
        "UI": ["界面", "UI", "UX", "交互", "样式", "显示"],
        "硬件": ["硬件", "设备", "hardware", "传感器"],
        "集成": ["集成", "对接", "API", "接口", "第三方"]
    }

    async def analyze(
        self,
        title: str,
        description: str,
        source_quote: Optional[str] = None,
        existing_requirements: Optional[list[dict]] = None
    ) -> AnalysisResult:
        """
        Analyze a single requirement.

        Args:
            title: Requirement title.
            description: Requirement description.
            source_quote: Original source quote.
            existing_requirements: Existing requirements for dependency analysis.

        Returns:
            The analysis result.
        """
        content = f"{title} {description} {source_quote or ''}"

        # 1. Keyword analysis: fast and LLM-free.
        category, cat_conf = self._analyze_category(content)
        priority, pri_reasons, pri_conf = self._analyze_priority(content)
        complexity, comp_factors = self._analyze_complexity(content)
        tags = self._extract_tags(content)

        # 2. Dependency analysis based on keyword matching.
        dependencies, blockers = self._analyze_dependencies(
            content, existing_requirements or []
        )

        # 3. Risk assessment.
        risk_level, risk_factors = self._assess_risk(
            priority, complexity, dependencies, blockers
        )

        # 4. Effort estimate.
        effort = self._estimate_effort(complexity)

        logger.info(
            "analysis_completed",
            title=title[:50],
            category=category,
            priority=priority,
            complexity=complexity,
            risk=risk_level
        )

        return AnalysisResult(
            suggested_category=category,
            category_confidence=cat_conf,
            suggested_priority=priority,
            priority_reasons=pri_reasons,
            priority_confidence=pri_conf,
            complexity=complexity,
            complexity_factors=comp_factors,
            estimated_effort_days=effort,
            dependencies=dependencies,
            blockers=blockers,
            risk_level=risk_level,
            risk_factors=risk_factors,
            suggested_tags=tags,
            analyzed_at=datetime.now(UTC)
        )

    async def analyze_with_llm(
        self,
        title: str,
        description: str,
        source_quote: Optional[str] = None,
        context: Optional[str] = None
    ) -> AnalysisResult:
        """
        Use the LLM for deeper analysis.

        Use only when higher precision is worth the extra latency.
        """
        # Run baseline analysis first.
        basic = await self.analyze(title, description, source_quote)

        # Build the LLM prompt.
        prompt = f"""Analyze the following requirement and provide intelligent recommendations:

**Requirement title**: {title}
**Requirement description**: {description}
**Source quote**: {source_quote or 'none'}
**Context**: {context or 'none'}

Return a JSON object:
{{
    "category": "feature/performance/security/UI/hardware/integration/other",
    "priority": "high/medium/low",
    "priority_reasons": ["reason 1", "reason 2"],
    "complexity": "S/M/L/XL",
    "complexity_factors": ["factor 1", "factor 2"],
    "dependencies": ["dependency 1", "dependency 2"],
    "risk_factors": ["risk 1", "risk 2"],
    "tags": ["tag 1", "tag 2"]
}}

Write user-facing string values in the dominant language of the input
requirement. Output JSON only; do not add any other text."""

        try:
            response = await llm_gateway.complete(
                prompt=prompt,
                agent_id="requirement-manager",
                task_type="analysis",
                temperature=0,
                system_prompt=(
                    "You are a requirements analysis expert. You are skilled "
                    "at evaluating priority, complexity, dependencies, and risk."
                )
            )

            # Parse and merge the LLM response.
            import json
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            # Update the baseline analysis with LLM output.
            return AnalysisResult(
                suggested_category=self._normalize_category(
                    data.get("category", basic.suggested_category)
                ),
                category_confidence=0.9,  # LLM analysis has higher confidence.
                suggested_priority=data.get("priority", basic.suggested_priority),
                priority_reasons=data.get("priority_reasons", basic.priority_reasons),
                priority_confidence=0.85,
                complexity=data.get("complexity", basic.complexity),
                complexity_factors=data.get("complexity_factors", basic.complexity_factors),
                estimated_effort_days=self._estimate_effort(
                    data.get("complexity", basic.complexity)
                ),
                dependencies=data.get("dependencies", basic.dependencies),
                blockers=basic.blockers,
                risk_level=basic.risk_level,
                risk_factors=data.get("risk_factors", basic.risk_factors),
                suggested_tags=data.get("tags", basic.suggested_tags),
                analyzed_at=datetime.now(UTC)
            )

        except Exception as e:
            logger.warning("llm_analysis_failed", error=str(e))
            return basic

    def _normalize_category(self, category: str) -> str:
        """Normalize LLM category labels to the persisted category names."""
        normalized = category.lower()
        category_map = {
            "功能": "功能",
            "feature": "功能",
            "性能": "性能",
            "performance": "性能",
            "硬件": "硬件",
            "hardware": "硬件",
            "集成": "集成",
            "integration": "集成",
            "ui": "UI",
            "用户界面": "UI",
            "安全": "安全",
            "security": "安全",
        }
        return category_map.get(category, category_map.get(normalized, "其他"))

    def _analyze_category(self, content: str) -> tuple[str, float]:
        """Analyze category."""
        content_lower = content.lower()
        scores = {}

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in content_lower)
            if score > 0:
                scores[category] = score

        if not scores:
            return "功能", 0.5  # Default.

        best = max(scores, key=scores.get)
        confidence = min(scores[best] / 3, 1.0)  # Three keywords reach full confidence.
        return best, confidence

    def _analyze_priority(self, content: str) -> tuple[str, list[str], float]:
        """Analyze priority."""
        content_lower = content.lower()
        reasons = []
        matched_priority = None
        match_count = 0

        for priority, keywords in self.PRIORITY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in content_lower:
                    if matched_priority is None:
                        matched_priority = priority
                    if priority == matched_priority:
                        reasons.append(f"包含关键词 '{kw}'")
                        match_count += 1

        if matched_priority is None:
            return "medium", ["默认优先级"], 0.5

        confidence = min(match_count / 2, 1.0)
        return matched_priority, reasons, confidence

    def _analyze_complexity(self, content: str) -> tuple[str, list[str]]:
        """Analyze complexity."""
        content_lower = content.lower()
        factors = []

        for complexity, keywords in self.COMPLEXITY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in content_lower:
                    factors.append(f"涉及 '{kw}'")
                    return complexity, factors

        # Estimate from description length.
        if len(content) > 500:
            return "L", ["详细描述，可能较复杂"]
        elif len(content) > 200:
            return "M", ["中等描述长度"]
        else:
            return "S", ["简短描述"]

    def _analyze_dependencies(
        self,
        content: str,
        existing: list[dict]
    ) -> tuple[list[str], list[str]]:
        """Analyze dependencies."""
        dependencies = []
        blockers = []

        # Look for potential dependency keywords.
        dep_keywords = ["依赖", "需要先", "基于", "前提", "depends on"]
        for kw in dep_keywords:
            if kw in content.lower():
                # Match existing requirements after a dependency keyword is found.
                for req in existing:
                    if req.get("title", "")[:20] in content:
                        dependencies.append(req.get("id", req.get("title", "")))

        # Look for blocking factors.
        blocker_keywords = ["阻塞", "等待", "blocked", "pending"]
        for kw in blocker_keywords:
            if kw in content.lower():
                blockers.append(f"可能被 '{kw}' 相关因素阻塞")

        return dependencies, blockers

    def _assess_risk(
        self,
        priority: str,
        complexity: str,
        dependencies: list[str],
        blockers: list[str]
    ) -> tuple[str, list[str]]:
        """Assess risk."""
        risk_factors = []
        risk_score = 0

        # High priority plus high complexity means high risk.
        if priority == "high" and complexity in ["L", "XL"]:
            risk_score += 2
            risk_factors.append("高优先级且高复杂度")

        # Dependencies increase risk.
        if dependencies:
            risk_score += 1
            risk_factors.append(f"有 {len(dependencies)} 个依赖")

        # Blockers mean high risk.
        if blockers:
            risk_score += 2
            risk_factors.append("存在阻塞因素")

        # XL complexity increases risk.
        if complexity == "XL":
            risk_score += 1
            risk_factors.append("超大复杂度")

        if risk_score >= 3:
            return "high", risk_factors
        elif risk_score >= 1:
            return "medium", risk_factors
        else:
            return "low", ["无明显风险因素"]

    def _estimate_effort(self, complexity: str) -> int:
        """Estimate effort in days."""
        effort_map = {
            "S": 1,
            "M": 3,
            "L": 7,
            "XL": 14
        }
        return effort_map.get(complexity, 3)

    def _extract_tags(self, content: str) -> list[str]:
        """Extract tags."""
        tags = []
        content_lower = content.lower()

        # Technology-related tags.
        tech_tags = {
            "api": ["api", "接口", "endpoint"],
            "database": ["数据库", "database", "db", "sql"],
            "frontend": ["前端", "frontend", "ui", "页面"],
            "backend": ["后端", "backend", "服务端"],
            "mobile": ["移动端", "mobile", "app", "ios", "android"],
            "security": ["安全", "security", "权限", "加密"],
            "performance": ["性能", "performance", "优化", "速度"],
            "integration": ["集成", "对接", "第三方"]
        }

        for tag, keywords in tech_tags.items():
            if any(kw in content_lower for kw in keywords):
                tags.append(tag)

        return tags[:5]  # At most five tags.


# Global analyzer instance.
analyzer = RequirementAnalyzer()
