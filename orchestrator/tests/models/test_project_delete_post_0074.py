import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Project


def test_project_delete_does_not_query_dropped_agent_schedule_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    active_tables = [
        table
        for table in Base.metadata.tables.values()
        if table.name not in {"agent_schedules", "schedule_trigger_events"}
    ]
    Base.metadata.create_all(engine, tables=active_tables)

    project_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            Project.__table__.insert(),
            {
                "id": project_id,
                "name": "Post-0074 project",
                "slug": "post-0074-project",
                "owner_id": uuid.uuid4(),
                "team_id": uuid.uuid4(),
            },
        )

    with Session(engine) as session:
        project = session.get(Project, project_id)
        assert project is not None
        session.delete(project)
        session.commit()
        assert session.get(Project, project_id) is None

    engine.dispose()