from app.services.default_agent import (
    SYSTEM_DEFAULT_AGENT_FIELDS,
    get_system_default_listing_dict,
)


def test_system_default_agent_inherits_deployment_model() -> None:
    assert SYSTEM_DEFAULT_AGENT_FIELDS["model"] is None


def test_system_default_listing_merges_per_user_overrides() -> None:
    listing = get_system_default_listing_dict(
        overrides={
            "name": "My Default",
            "description": "Personal description",
            "system_prompt": "Personal prompt",
            "config": {"context_window": 64000},
        }
    )

    assert listing["name"] == "My Default"
    assert listing["description"] == "Personal description"
    assert listing["system_prompt"] == "Personal prompt"
    assert listing["config"] == {"context_window": 64000}