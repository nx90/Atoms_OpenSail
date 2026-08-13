import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.services.orchestration.docker import DockerOrchestrator


class FakeProcess:
    returncode = 0

    async def communicate(self):
        return b"", b""


def test_named_volume_ownership_uses_uid_1000(monkeypatch) -> None:
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    orchestrator = DockerOrchestrator.__new__(DockerOrchestrator)
    orchestrator.use_volumes = True

    asyncio.run(orchestrator._ensure_project_volume_ownership("example-project"))

    args, _ = calls[0]
    assert args[:3] == ("docker", "run", "--rm")
    assert "tesslate-projects-data:/projects" in args
    assert "1000:1000" in args
    assert args[-1] == "/projects/example-project"


def test_bind_mount_mode_skips_ownership_helper(monkeypatch) -> None:
    async def fail_exec(*args, **kwargs):
        raise AssertionError("docker must not be called")

    monkeypatch.setattr("asyncio.create_subprocess_exec", fail_exec)
    orchestrator = DockerOrchestrator.__new__(DockerOrchestrator)
    orchestrator.use_volumes = False

    asyncio.run(orchestrator._ensure_project_volume_ownership("example-project"))


def test_compose_allows_the_generated_vite_preview_hostname() -> None:
    orchestrator = DockerOrchestrator.__new__(DockerOrchestrator)
    orchestrator.use_volumes = True
    orchestrator.settings = SimpleNamespace(app_domain="preview.example.com")

    async def fake_container_config(project, container):
        return "npm run dev", 5173

    orchestrator._get_container_config = fake_container_config
    project = SimpleNamespace(slug="example-project", id=uuid4())
    container = SimpleNamespace(
        id=uuid4(),
        name="Web App",
        container_type="base",
        environment_vars={},
        port=None,
        internal_port=5173,
        directory=".",
    )

    config = asyncio.run(
        orchestrator._generate_compose_config(project, [container], [], uuid4())
    )

    assert config["services"]["web-app"]["environment"][
        "__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS"
    ] == "example-project-web-app.preview.example.com"


def test_delete_project_uses_captured_slug_after_database_delete(
    monkeypatch, tmp_path
) -> None:
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append(args)
        return FakeProcess()

    async def fail_slug_lookup(project_id):
        raise AssertionError("deleted projects cannot be resolved from the database")

    deleted_directories = []

    async def fake_delete_directory(project_slug):
        deleted_directories.append(project_slug)
        return True

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    orchestrator = DockerOrchestrator.__new__(DockerOrchestrator)
    orchestrator.compose_files_dir = str(tmp_path)
    orchestrator._get_project_slug = fail_slug_lookup
    orchestrator.delete_project_directory = fake_delete_directory
    (tmp_path / "example-project.yml").write_text("services: {}", encoding="utf-8")

    asyncio.run(
        orchestrator.delete_project_namespace(
            uuid4(), uuid4(), project_slug="example-project"
        )
    )

    assert calls[0][:6] == (
        "docker",
        "compose",
        "-f",
        str(tmp_path / "example-project.yml"),
        "-p",
        "example-project",
    )
    assert calls[0][-3:] == ("down", "--remove-orphans", "--volumes")
    assert deleted_directories == ["example-project"]