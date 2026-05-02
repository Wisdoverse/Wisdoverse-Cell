"""
ID Generator - 统一的ID生成器

使用ULID (Universally Unique Lexicographically Sortable Identifier)
- 有序：可按时间排序
- 可读：比UUID短
- 分布式安全：无需中心化生成

格式: {prefix}_{ulid}
示例:
  - req_01HQ3K4N5M6P7Q8R9S0T  (需求)
  - mtg_01HQ3K4N5M6P7Q8R9S0T  (会议)
  - evt_01HQ3K4N5M6P7Q8R9S0T  (事件)
  - usr_01HQ3K4N5M6P7Q8R9S0T  (用户)
"""
import ulid


def generate_id(prefix: str) -> str:
    """
    生成带前缀的ULID

    Args:
        prefix: ID前缀，如 "req", "mtg", "evt"

    Returns:
        格式化的ID，如 "req_01HQ3K4N5M6P7Q8R9S0T"
    """
    return f"{prefix}_{str(ulid.ULID()).lower()}"


def generate_ulid() -> str:
    """
    生成纯 ULID（不带前缀）

    Returns:
        26 字符的 ULID 字符串
    """
    return str(ulid.ULID())


# 预定义的前缀常量
class IDPrefix:
    """ID前缀常量"""
    EVENT = "evt"           # 事件
    REQUIREMENT = "req"     # 需求
    MEETING = "mtg"         # 会议
    QUESTION = "qst"        # 问题
    USER = "usr"            # 用户
    CUSTOMER = "cus"        # 客户
    DEVICE = "dev"          # 设备
    TICKET = "tkt"          # 工单
    APPROVAL = "apr"        # 审批
    DOCUMENT = "doc"        # 文档
    SESSION = "ses"         # 会话
    MESSAGE = "msg"         # 消息
    COMPANY = "cmp"         # 公司上下文
    GOAL = "goal"           # 目标
    AGENT_ROLE = "role"     # Agent 角色
    WORK_ITEM = "work"      # 工作项
    AGENT_RUN = "run"       # Agent 运行
    DECISION = "dec"        # 决策
    ARTIFACT = "art"        # 产物
    BUDGET = "bud"          # 预算
    BUDGET_USAGE = "busg"   # 预算使用
    AUDIT_EVENT = "aud"     # 审计事件
    EVOLUTION_PROPOSAL = "evp"  # 自进化提案
