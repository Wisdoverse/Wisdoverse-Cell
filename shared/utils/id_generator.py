"""
ID Generator - centralized ID generation.

Uses ULID (Universally Unique Lexicographically Sortable Identifier).
- Ordered: sortable by time.
- Readable: shorter than UUID.
- Distributed-safe: no centralized generator required.

Format: {prefix}_{ulid}
Examples:
  - req_01HQ3K4N5M6P7Q8R9S0T  (requirement)
  - mtg_01HQ3K4N5M6P7Q8R9S0T  (meeting)
  - evt_01HQ3K4N5M6P7Q8R9S0T  (event)
  - usr_01HQ3K4N5M6P7Q8R9S0T  (user)
"""
import ulid


def generate_id(prefix: str) -> str:
    """
    Generate a prefixed ULID.

    Args:
        prefix: ID prefix such as "req", "mtg", or "evt".

    Returns:
        Formatted ID such as "req_01HQ3K4N5M6P7Q8R9S0T".
    """
    return f"{prefix}_{str(ulid.ULID()).lower()}"


def generate_ulid() -> str:
    """
    Generate a plain ULID without a prefix.

    Returns:
        A 26-character ULID string.
    """
    return str(ulid.ULID())


# Predefined prefix constants
class IDPrefix:
    """ID prefix constants."""
    EVENT = "evt"           # event
    REQUIREMENT = "req"     # requirement
    MEETING = "mtg"         # meeting
    QUESTION = "qst"        # question
    USER = "usr"            # user
    CUSTOMER = "cus"        # customer
    DEVICE = "dev"          # device
    TICKET = "tkt"          # ticket
    APPROVAL = "apr"        # approval
    DOCUMENT = "doc"        # document
    SESSION = "ses"         # session
    MESSAGE = "msg"         # message
    COMPANY = "cmp"         # company context
    GOAL = "goal"           # goal
    AGENT_ROLE = "role"     # agent role
    WORK_ITEM = "work"      # work item
    AGENT_RUN = "run"       # agent run
    DECISION = "dec"        # decision
    ARTIFACT = "art"        # artifact
    BUDGET = "bud"          # budget
    BUDGET_USAGE = "busg"   # budget usage
    AUDIT_EVENT = "aud"     # audit event
    EVOLUTION_PROPOSAL = "evp"  # evolution proposal
