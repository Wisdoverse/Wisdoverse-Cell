"""Core ID generation contracts."""

import ulid


def generate_id(prefix: str) -> str:
    """
    Generate a prefixed ULID.

    Args:
        prefix: ID prefix such as "req", "mtg", or "evt".

    Returns:
        Formatted ID such as "req_01hq3k4n5m6p7q8r9s0t".
    """
    return f"{prefix}_{str(ulid.ULID()).lower()}"


def generate_ulid() -> str:
    """
    Generate a plain ULID without a prefix.

    Returns:
        A 26-character ULID string.
    """
    return str(ulid.ULID())


class IDPrefix:
    """Stable ID prefix constants for runtime and control-plane objects."""

    EVENT = "evt"
    REQUIREMENT = "req"
    MEETING = "mtg"
    QUESTION = "qst"
    USER = "usr"
    CUSTOMER = "cus"
    DEVICE = "dev"
    TICKET = "tkt"
    APPROVAL = "apr"
    DOCUMENT = "doc"
    SESSION = "ses"
    MESSAGE = "msg"
    COMPANY = "cmp"
    GOAL = "goal"
    AGENT_ROLE = "role"
    WORK_ITEM = "work"
    AGENT_RUN = "run"
    DECISION = "dec"
    ARTIFACT = "art"
    BUDGET = "bud"
    BUDGET_USAGE = "busg"
    AUDIT_EVENT = "aud"
    EVOLUTION_PROPOSAL = "evp"
