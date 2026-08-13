import pytest

from app.services.personal_skills import (
    PersonalSkillLimitError,
    PersonalSkillValidationError,
    normalize_skill_path,
    parse_skill_metadata,
    render_default_skill,
    strip_skill_frontmatter,
)


def test_default_skill_round_trips_metadata_and_body() -> None:
    content = render_default_skill("Deploy Review", "Review deployment changes")

    metadata = parse_skill_metadata(content)

    assert metadata.name == "Deploy Review"
    assert metadata.description == "Review deployment changes"
    assert strip_skill_frontmatter(content).startswith("# Deploy Review")


@pytest.mark.parametrize(
    "path",
    ["/absolute.md", "../escape.md", "references//file.md", "./file.md", "references/../x"],
)
def test_skill_path_rejects_unsafe_values(path: str) -> None:
    with pytest.raises(PersonalSkillValidationError):
        normalize_skill_path(path)


def test_skill_path_accepts_nested_reference() -> None:
    assert normalize_skill_path("references/api/auth.md") == "references/api/auth.md"


def test_skill_path_enforces_depth(monkeypatch) -> None:
    from app.services import personal_skills

    settings = personal_skills.get_settings()
    monkeypatch.setattr(settings, "personal_skill_max_depth", 2)

    with pytest.raises(PersonalSkillLimitError):
        normalize_skill_path("one/two/three.md")
