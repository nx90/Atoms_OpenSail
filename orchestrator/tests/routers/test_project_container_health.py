from types import SimpleNamespace
from uuid import UUID

from app.routers.projects import _resolve_container_health_route_name


def test_root_container_health_uses_deployment_route_name() -> None:
    container = SimpleNamespace(
        id=UUID("b6031448-c2dc-4eca-8c59-73a5770531f7"),
        name="app",
        directory=".",
    )

    assert _resolve_container_health_route_name(container, "docker") == "app"
    assert _resolve_container_health_route_name(container, "kubernetes") == "b6031448c2dc"