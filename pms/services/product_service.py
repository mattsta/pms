"""Product service for high-level product operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import Product, ProductStats, ProductStatus, Project, ProjectStatus
from pms.repositories.base import QueryResult, RepositoryContext
from pms.repositories.product_repository import ProductRepository
from pms.repositories.project_repository import ProjectRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


@dataclass
class ProductSummary:
    """Summary of a product with key metrics."""

    product: Product
    stats: ProductStats | None
    projects: list[Project]
    health_score: float = 0.0  # 0.0 to 1.0


@dataclass
class ProductDashboard:
    """Dashboard view for a specific product."""

    product: Product
    stats: ProductStats
    active_projects: list[Project]
    completed_projects: list[Project]
    total_complexity_points: int = 0
    total_duration_hours: float = 0.0


class ProductService:
    """
    Service for product management operations.

    Coordinates between repositories and provides high-level
    business operations with proper event sourcing and metrics.
    """

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        self.db = db
        self.events = event_store
        self.revisions = revision_store
        self.metrics = metrics

        self._product_repo = ProductRepository(db, event_store, revision_store, metrics)
        self._project_repo = ProjectRepository(db, event_store, revision_store, metrics)
        self._context = RepositoryContext()

    def with_context(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ProductService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._product_repo.with_context(self._context)
        self._project_repo.with_context(self._context)
        return self

    async def _resolve_owner_identity(
        self,
        owner: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve owner input to canonical actor-facing value plus actor id."""
        if owner is None:
            return None, None
        from pms.services.actor_service import ActorService

        actor_service = ActorService(self.db, self.events, self.revisions, self.metrics)
        actor_service.with_context(
            user_id=self._context.user_id,
            session_id=self._context.session_id,
            correlation_id=self._context.correlation_id,
        )
        return await actor_service.canonicalize_actor_reference(owner)

    async def create_product(
        self,
        name: str,
        description: str | None = None,
        vision: str | None = None,
        repository_url: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        product_type: str = "service",
    ) -> Product:
        """Create a new product."""
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self._product_repo.db.transaction():
            product = await self._product_repo.create(
                name=name,
                description=description,
                vision=vision,
                repository_url=repository_url,
                owner=canonical_owner,
                owner_id=owner_id,
                tags=tags,
                product_type=product_type,
                message=f"Created product '{name}'",
            )

            await self.metrics.record_counter(
                "product.created",
                labels={"name": name, "type": product_type},
            )
            await self.metrics.flush()

        return product

    async def get_product(self, product_id: str) -> Product | None:
        """Get a product by ID."""
        return await self._product_repo.get_by_id(product_id)

    async def get_product_by_name(self, name: str) -> Product | None:
        """Get a product by name."""
        return await self._product_repo.get_by_name(name)

    async def list_products(
        self,
        status: ProductStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Product]:
        """List products with optional filtering."""
        if status:
            return await self._product_repo.get_by_status(status, limit, offset)
        return await self._product_repo.get_all(limit, offset)

    async def update_product(
        self,
        product_id: str,
        name: str | None = None,
        description: str | None = None,
        vision: str | None = None,
        repository_url: str | None = None,
        owner: str | None = None,
        clear_owner: bool = False,
        product_type: str | None = None,
        status: ProductStatus | None = None,
        tags: list[str] | None = None,
    ) -> Product | None:
        """Update product details."""
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self._product_repo.db.transaction():
            product = await self._product_repo.update(
                product_id=product_id,
                name=name,
                description=description,
                vision=vision,
                repository_url=repository_url,
                owner=canonical_owner,
                owner_id=owner_id,
                clear_owner=clear_owner,
                product_type=product_type,
                status=status,
                tags=tags,
            )

            if product:
                await self.metrics.record_counter("product.updated")
                await self.metrics.flush()

        return product

    async def archive_product(self, product_id: str) -> Product | None:
        """Archive a product."""
        async with self._product_repo.db.transaction():
            product = await self._product_repo.archive(product_id)

            if product:
                await self.metrics.record_counter("product.archived")
                await self.metrics.flush()

        return product

    async def sunset_product(self, product_id: str) -> Product | None:
        """Mark product for sunset/EOL."""
        async with self._product_repo.db.transaction():
            product = await self._product_repo.sunset(product_id)

            if product:
                await self.metrics.record_counter("product.sunset")
                await self.metrics.flush()

        return product

    async def get_product_summary(self, product_id: str) -> ProductSummary | None:
        """Get product summary with statistics and projects."""
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            return None

        stats = await self._product_repo.get_stats(product_id)
        projects_result = await self._product_repo.get_projects(product_id, limit=1000)

        health_score = self._calculate_health_score(stats)

        return ProductSummary(
            product=product,
            stats=stats,
            projects=projects_result.items,
            health_score=health_score,
        )

    async def get_product_dashboard(self, product_id: str) -> ProductDashboard | None:
        """Get dashboard view for a product."""
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            return None

        stats = await self._product_repo.get_stats(product_id)
        if stats is None:
            stats = ProductStats(product_id=product_id)

        # Get active and completed projects
        active_result = await self._product_repo.get_projects(
            product_id, status=ProjectStatus.ACTIVE, limit=100
        )
        completed_result = await self._product_repo.get_projects(
            product_id, status=ProjectStatus.COMPLETED, limit=100
        )

        return ProductDashboard(
            product=product,
            stats=stats,
            active_projects=active_result.items,
            completed_projects=completed_result.items,
            total_complexity_points=stats.total_complexity_points,
            total_duration_hours=stats.total_duration_hours,
        )

    async def create_project_in_product(
        self,
        product_id: str,
        project_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> Project:
        """Create a new project within a product."""
        # Verify product exists
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            raise ValueError(f"Product {product_id} not found")

        async with self._product_repo.db.transaction():
            # Create project
            project = await self._project_repo.create(
                name=project_name,
                description=description,
                tags=tags,
                message=f"Created project '{project_name}' in product '{product.name}'",
            )

            # Assign to product
            project = await self._project_repo.assign_to_product(
                project.id,
                product_id,
                message=f"Assigned to product '{product.name}'",
            )

            if project is None:
                raise ValueError(f"Failed to assign project to product")
            assert project is not None

            await self.metrics.record_counter(
                "project.created",
                labels={"product_id": product_id, "name": project_name},
            )
            await self.metrics.flush()

        return project

    async def assign_project_to_product(
        self,
        project_id: str,
        product_id: str,
    ) -> Project | None:
        """Assign an existing project to a product."""
        # Verify product exists
        product = await self._product_repo.get_by_id(product_id)
        if product is None:
            raise ValueError(f"Product {product_id} not found")

        async with self._product_repo.db.transaction():
            project = await self._project_repo.assign_to_product(
                project_id,
                product_id,
                message=f"Assigned to product '{product.name}'",
            )

            if project:
                await self.metrics.record_counter(
                    "project.assigned_to_product",
                    labels={"product_id": product_id, "project_id": project_id},
                )
                await self.metrics.flush()

        return project

    def _calculate_health_score(self, stats: ProductStats | None) -> float:
        """
        Calculate product health score (0.0 to 1.0).

        Weighted by:
        - Task completion rate (40%)
        - Project completion rate (30%)
        - Blocked task ratio (20%)
        - Active project ratio (10%)
        """
        if stats is None or stats.total_tasks == 0:
            return 1.0  # New product with no tasks is healthy

        task_completion = stats.completion_rate / 100 * 0.4

        project_completion = 0.0
        if stats.total_projects > 0:
            project_completion = stats.project_completion_rate / 100 * 0.3

        blocked_ratio = stats.blocked_tasks / stats.total_tasks
        blocked_penalty = blocked_ratio * 0.2

        active_ratio = 1.0
        if stats.total_projects > 0:
            active_ratio = stats.active_projects / stats.total_projects
        active_factor = active_ratio * 0.1

        score = task_completion + project_completion - blocked_penalty + active_factor
        return min(1.0, max(0.0, score))
