"""Verify infra compat layer — old and new import paths work."""
def test_circuit_breaker_same_class():
    from shared.infra.circuit_breaker import CircuitBreaker as New
    from shared.services.circuit_breaker import CircuitBreaker as Old
    assert New is Old

def test_agent_client_same_class():
    from shared.infra.agent_client import AgentClient as New
    from shared.services.agent_client import AgentClient as Old
    assert New is Old
