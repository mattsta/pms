"""Services for test server registration and lookup."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from pms.db.connection import Database

LOCAL_TEST_SERVER_ID = "local"
LOCAL_TEST_SERVER_NAME = "local"


@dataclass(frozen=True)
class TestServerRegistration:
    """A registered test server."""

    id: str
    name: str
    project_id: str | None
    state: str
    region: str
    availability_zone: str
    created: bool


class TestServerService:
    """Manage test server registrations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def ensure_local_server(
        self, project_id: str | None = None
    ) -> TestServerRegistration:
        """Ensure a reusable local test server registration exists."""
        row = await self.db.fetch_one(
            """
            SELECT id, name, project_id, state, region, availability_zone
            FROM test_servers
            WHERE id = ?
            """,
            (LOCAL_TEST_SERVER_ID,),
        )
        if row is not None:
            return TestServerRegistration(
                id=str(row["id"]),
                name=str(row["name"]),
                project_id=str(row["project_id"]) if row["project_id"] else None,
                state=str(row["state"]),
                region=str(row["region"]),
                availability_zone=str(row["availability_zone"]),
                created=False,
            )

        launched_at = datetime.now(UTC).isoformat()
        config = {"kind": "local", "description": "Local test runner"}
        await self.db.execute(
            """
            INSERT INTO test_servers (
                id, name, project_id, config, state, region,
                availability_zone, hourly_price, estimated_cost, launched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                LOCAL_TEST_SERVER_ID,
                LOCAL_TEST_SERVER_NAME,
                project_id,
                json.dumps(config),
                "running",
                "local",
                "local",
                0.0,
                0.0,
                launched_at,
            ),
        )
        await self.db.commit()
        return TestServerRegistration(
            id=LOCAL_TEST_SERVER_ID,
            name=LOCAL_TEST_SERVER_NAME,
            project_id=project_id,
            state="running",
            region="local",
            availability_zone="local",
            created=True,
        )
