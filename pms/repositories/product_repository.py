"""Product repository with event sourcing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventType
from pms.models import Product, ProductStats, ProductStatus, ProjectStatus
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class ProductRepository(EventSourcedRepository[Product]):
    """Repository for Product entities with full event sourcing."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        super().__init__(db, event_store, revision_store, metrics)

    @property
    def entity_type(self) -> str:
        return "product"

    @property
    def table_name(self) -> str:
        return "products"

    def _model_from_row(self, row: dict[str, Any]) -> Product:
        """Convert database row to Product."""
        # Parse JSON fields
        tags_raw = row.get("tags", "[]")
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw

        team_raw = row.get("team", "[]")
        team = json.loads(team_raw) if isinstance(team_raw, str) else team_raw

        service_urls_raw = row.get("service_urls", "[]")
        service_urls = (
            json.loads(service_urls_raw)
            if isinstance(service_urls_raw, str)
            else service_urls_raw
        )

        # Parse workflow metadata
        workflow_metadata_raw = row.get("workflow_metadata", "{}")
        workflow_metadata = (
            json.loads(workflow_metadata_raw)
            if isinstance(workflow_metadata_raw, str)
            else workflow_metadata_raw
        )

        return Product(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            status=ProductStatus(row["status"]),
            vision=row.get("vision"),
            repository_url=row.get("repository_url"),
            service_urls=tuple(service_urls),
            owner=row.get("owner"),
            owner_id=row.get("owner_id"),
            team=tuple(team),
            tags=tuple(tags),
            product_type=row.get("product_type", "service"),
            workflow_id=row.get("workflow_id"),
            current_state=row.get("current_state"),
            workflow_metadata=workflow_metadata,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: Product) -> dict[str, Any]:
        """Convert Product to database row."""
        return {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "status": model.status.value,
            "vision": model.vision,
            "repository_url": model.repository_url,
            "service_urls": json.dumps(list(model.service_urls)),
            "owner": model.owner,
            "owner_id": model.owner_id,
            "team": json.dumps(list(model.team)),
            "tags": json.dumps(list(model.tags)),
            "product_type": model.product_type,
            "workflow_id": model.workflow_id,
            "current_state": model.current_state,
            "workflow_metadata": json.dumps(model.workflow_metadata),
            "created_at": model.created_at.isoformat()
            if hasattr(model.created_at, "isoformat")
            else model.created_at,
            "updated_at": model.updated_at.isoformat()
            if hasattr(model.updated_at, "isoformat")
            else model.updated_at,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def create(
        self,
        name: str,
        description: str | None = None,
        vision: str | None = None,
        repository_url: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        tags: list[str] | None = None,
        product_type: str = "service",
        message: str | None = None,
    ) -> Product:
        """Create a new product."""
        product = Product(
            name=name,
            description=description,
            vision=vision,
            repository_url=repository_url,
            owner=owner,
            owner_id=owner_id,
            tags=tuple(tags) if tags else (),
            product_type=product_type,
        )

        payload = {
            "name": name,
            "description": description,
            "vision": vision,
            "repository_url": repository_url,
            "owner": owner,
            "owner_id": owner_id,
            "tags": tags or [],
            "product_type": product_type,
        }

        return await self.save(
            product,
            EventType.PRODUCT_CREATED,
            payload,
            message=message or f"Created product '{name}'",
        )

    async def update(
        self,
        product_id: str,
        name: str | None = None,
        description: str | None = None,
        vision: str | None = None,
        repository_url: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        product_type: str | None = None,
        status: ProductStatus | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Product | None:
        """Update an existing product."""
        product = await self.get_by_id(product_id)
        if product is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != product.name:
            changes["name"] = (product.name, name)
            product.name = name
        if description is not None and description != product.description:
            changes["description"] = (product.description, description)
            product.description = description
        if vision is not None and vision != product.vision:
            changes["vision"] = (product.vision, vision)
            product.vision = vision
        if repository_url is not None and repository_url != product.repository_url:
            changes["repository_url"] = (product.repository_url, repository_url)
            product.repository_url = repository_url
        if clear_owner:
            if product.owner is not None or product.owner_id is not None:
                changes["owner"] = (product.owner, None)
                changes["owner_id"] = (product.owner_id, None)
                product.owner = None
                product.owner_id = None
        elif owner is not None and (
            owner != product.owner or owner_id != product.owner_id
        ):
            changes["owner"] = (product.owner, owner)
            changes["owner_id"] = (product.owner_id, owner_id)
            product.owner = owner
            product.owner_id = owner_id
        if product_type is not None and product_type != product.product_type:
            changes["product_type"] = (product.product_type, product_type)
            product.product_type = product_type
        if status is not None and status != product.status:
            changes["status"] = (product.status.value, status.value)
            product.status = status
        if tags is not None and tuple(tags) != product.tags:
            changes["tags"] = (list(product.tags), tags)
            product.tags = tuple(tags)

        if not changes:
            return product  # No changes

        product.touch()

        return await self.save(
            product,
            EventType.PRODUCT_UPDATED,
            {"changes": changes},
            message=message,
        )

    async def archive(
        self, product_id: str, message: str | None = None
    ) -> Product | None:
        """Archive a product."""
        product = await self.get_by_id(product_id)
        if product is None:
            return None

        old_status = product.status
        product.archive()

        return await self.save(
            product,
            EventType.PRODUCT_ARCHIVED,
            {"old_status": old_status.value, "new_status": product.status.value},
            message=message or "Product archived",
        )

    async def sunset(
        self, product_id: str, message: str | None = None
    ) -> Product | None:
        """Mark product for sunset/EOL."""
        product = await self.get_by_id(product_id)
        if product is None:
            return None

        old_status = product.status
        product.sunset()

        return await self.save(
            product,
            EventType.PRODUCT_SUNSET,
            {"old_status": old_status.value, "new_status": product.status.value},
            message=message or "Product marked for sunset",
        )

    async def get_by_name(self, name: str) -> Product | None:
        """Get product by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM products WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        return self._model_from_row(row)

    async def get_by_status(
        self,
        status: ProductStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Product]:
        """Get products by status."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM products WHERE status = ?",
            (status.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM products
            WHERE status = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (status.value, limit, offset),
        )

        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def search(
        self,
        query: str,
        status: ProductStatus | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[Product]:
        """Search products by name, description, vision, or tags."""
        sql = """
            SELECT * FROM products
            WHERE (name LIKE ? OR description LIKE ? OR vision LIKE ?)
        """
        params: list[Any] = [f"%{query}%", f"%{query}%", f"%{query}%"]

        if status:
            sql += " AND status = ?"
            params.append(status.value)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(sql, tuple(params))
        products = [self._model_from_row(row) for row in rows]

        # Filter by tags if specified
        if tags:
            products = [p for p in products if any(tag in p.tags for tag in tags)]

        return products

    async def get_stats(self, product_id: str) -> ProductStats | None:
        """Get computed statistics for a product aggregated across all projects."""
        product = await self.get_by_id(product_id)
        if product is None:
            return None

        # Query project statistics
        project_stats_row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_projects,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_projects,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_projects
            FROM projects
            WHERE product_id = ?
            """,
            (product_id,),
        )

        # Query aggregated task statistics across all projects in product
        task_stats_row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_tasks,
                SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END) as completed_tasks,
                SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress_tasks,
                SUM(CASE WHEN t.status = 'blocked' THEN 1 ELSE 0 END) as blocked_tasks,
                SUM(COALESCE(t.complexity_points, 0)) as total_complexity_points,
                AVG(COALESCE(t.complexity_points, 0)) as avg_complexity_per_task
            FROM tasks t
            INNER JOIN projects p ON t.project_id = p.id
            WHERE p.product_id = ?
            """,
            (product_id,),
        )

        # Calculate total duration from state transitions
        duration_row = await self.db.fetch_one(
            """
            SELECT
                SUM(COALESCE(tst.duration_in_state_seconds, 0)) / 3600.0 as total_duration_hours
            FROM task_state_transitions tst
            INNER JOIN tasks t ON tst.task_id = t.id
            INNER JOIN projects p ON t.project_id = p.id
            WHERE p.product_id = ?
            AND tst.from_state IN ('in_progress', 'in_review')
            """,
            (product_id,),
        )

        # Calculate efficiency
        efficiency_row = await self.db.fetch_one(
            """
            SELECT AVG(efficiency) as avg_efficiency_score
            FROM (
                SELECT
                    CASE
                        WHEN total_duration > 0 AND t.complexity_points > 0
                        THEN CAST(t.complexity_points AS REAL) / total_duration
                        ELSE NULL
                    END as efficiency
                FROM tasks t
                INNER JOIN projects p ON t.project_id = p.id
                LEFT JOIN (
                    SELECT task_id, SUM(COALESCE(duration_in_state_seconds, 0)) / 3600.0 as total_duration
                    FROM task_state_transitions
                    WHERE from_state IN ('in_progress', 'in_review')
                    GROUP BY task_id
                ) tst ON t.id = tst.task_id
                WHERE p.product_id = ? AND t.status = 'done'
            )
            WHERE efficiency IS NOT NULL
            """,
            (product_id,),
        )

        # Query AWS costs if applicable
        aws_cost_row = await self.db.fetch_one(
            """
            SELECT SUM(COALESCE(cost_usd, 0)) as total_cost
            FROM aws_costs c
            INNER JOIN test_servers s ON c.server_id = s.id
            INNER JOIN projects p ON s.project_id = p.id
            WHERE p.product_id = ?
            """,
            (product_id,),
        )

        goal_stats_row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_goals,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_goals,
                AVG(COALESCE(progress_percent, 0)) as avg_goal_progress
            FROM goals
            WHERE product_id = ?
            """,
            (product_id,),
        )

        return ProductStats(
            product_id=product_id,
            total_projects=project_stats_row["total_projects"]
            if project_stats_row
            else 0 or 0,
            active_projects=project_stats_row["active_projects"]
            if project_stats_row
            else 0 or 0,
            completed_projects=project_stats_row["completed_projects"]
            if project_stats_row
            else 0 or 0,
            total_tasks=task_stats_row["total_tasks"] if task_stats_row else 0 or 0,
            completed_tasks=task_stats_row["completed_tasks"]
            if task_stats_row
            else 0 or 0,
            in_progress_tasks=task_stats_row["in_progress_tasks"]
            if task_stats_row
            else 0 or 0,
            blocked_tasks=task_stats_row["blocked_tasks"] if task_stats_row else 0 or 0,
            total_complexity_points=task_stats_row["total_complexity_points"]
            if task_stats_row
            else 0 or 0,
            avg_complexity_per_task=task_stats_row["avg_complexity_per_task"]
            if task_stats_row
            else 0.0 or 0.0,
            total_duration_hours=duration_row["total_duration_hours"]
            if duration_row
            else 0.0 or 0.0,
            avg_efficiency_score=efficiency_row["avg_efficiency_score"]
            if efficiency_row
            else 0.0 or 0.0,
            total_aws_cost=aws_cost_row["total_cost"] if aws_cost_row else 0.0 or 0.0,
            total_goals=goal_stats_row["total_goals"] if goal_stats_row else 0 or 0,
            completed_goals=goal_stats_row["completed_goals"]
            if goal_stats_row
            else 0 or 0,
            avg_goal_progress=goal_stats_row["avg_goal_progress"]
            if goal_stats_row and goal_stats_row["avg_goal_progress"] is not None
            else 0.0,
        )

    async def get_projects(
        self,
        product_id: str,
        status: ProjectStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Any]:
        """Get all projects for a product."""

        sql = "SELECT * FROM projects WHERE product_id = ?"
        params: list[Any] = [product_id]

        if status:
            sql += " AND status = ?"
            params.append(status.value)

        # Count query
        count_sql = sql.replace("SELECT *", "SELECT COUNT(*) as count")
        count_result = await self.db.fetch_one(count_sql, tuple(params))
        total = count_result["count"] if count_result else 0

        # Data query
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = await self.db.fetch_all(sql, tuple(params))

        # Import ProjectRepository to convert rows
        from pms.repositories.project_repository import ProjectRepository

        temp_repo = ProjectRepository(
            self.db, self.events, self.revisions, self.metrics
        )
        projects = [temp_repo._model_from_row(row) for row in rows]

        return QueryResult(
            items=projects,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> Product | None:
        """Rebuild product state from events."""
        if not events:
            return None

        product = None

        for event in events:
            match event.event_type:
                case EventType.PRODUCT_CREATED:
                    p = event.payload
                    product = Product(
                        id=event.aggregate_id,
                        name=p.get("name", ""),
                        description=p.get("description"),
                        vision=p.get("vision"),
                        repository_url=p.get("repository_url"),
                        service_urls=tuple(p.get("service_urls", [])),
                        owner=p.get("owner"),
                        owner_id=p.get("owner_id"),
                        team=tuple(p.get("team", [])),
                        tags=tuple(p.get("tags", [])),
                        product_type=p.get("product_type", "service"),
                    )
                case EventType.PRODUCT_UPDATED if product:
                    p2 = event.payload
                    changes = p2.get("changes", {})
                    for field, (old_val, new_val) in changes.items():
                        match field:
                            case "name":
                                product.name = new_val
                            case "description":
                                product.description = new_val
                            case "vision":
                                product.vision = new_val
                            case "status":
                                product.status = ProductStatus(new_val)
                            case "owner":
                                product.owner = new_val
                            case "owner_id":
                                product.owner_id = new_val
                            case "tags":
                                product.tags = tuple(new_val)
                            case _:
                                pass
                case EventType.PRODUCT_ARCHIVED if product:
                    product.status = ProductStatus.ARCHIVED
                case EventType.PRODUCT_SUNSET if product:
                    product.status = ProductStatus.SUNSET

        return product
