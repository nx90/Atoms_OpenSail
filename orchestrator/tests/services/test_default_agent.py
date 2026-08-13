from app.services.default_agent import SYSTEM_DEFAULT_AGENT_FIELDS


def test_system_default_agent_inherits_deployment_model() -> None:
    assert SYSTEM_DEFAULT_AGENT_FIELDS["model"] is None