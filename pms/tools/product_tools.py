"""MCP tools for product management."""

from typing import Any

from pms.models import ProductStatus
from pms.services.product_service import ProductService


async def create_product(
    product_service: ProductService,
    name: str,
    description: str | None = None,
    vision: str | None = None,
    repository_url: str | None = None,
    owner: str | None = None,
    product_type: str = "service",
) -> dict[str, Any]:
    """Create a new product."""
    product = await product_service.create_product(
        name=name,
        description=description,
        vision=vision,
        repository_url=repository_url,
        owner=owner,
        product_type=product_type,
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created product: {product.name}\nID: {product.id}\nStatus: {product.status.value}",
            }
        ]
    }


async def list_products(
    product_service: ProductService,
    status: str | None = None,
) -> dict[str, Any]:
    """List all products."""
    status_filter = ProductStatus(status) if status else None
    result = await product_service.list_products(status=status_filter)

    products_list = "\n".join(
        f"- {p.name} ({p.status.value}) - {p.id}" for p in result.items
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Products ({result.total_count}):\n{products_list}",
            }
        ]
    }


async def get_product_summary(
    product_service: ProductService,
    product_id: str,
) -> dict[str, Any]:
    """Get product summary with statistics."""
    summary = await product_service.get_product_summary(product_id)

    if summary is None:
        return {
            "content": [{"type": "text", "text": f"Product {product_id} not found"}],
            "isError": True,
        }

    stats = summary.stats
    text = f"""Product: {summary.product.name}
ID: {summary.product.id}
Status: {summary.product.status.value}
Vision: {summary.product.vision or "N/A"}

Statistics:
- Projects: {stats.total_projects} ({stats.active_projects} active)
- Tasks: {stats.completed_tasks}/{stats.total_tasks} completed
- Complexity: {stats.total_complexity_points} points
- Efficiency: {stats.avg_efficiency_score:.1f} pts/hr
- Health Score: {stats.health_score:.0f}%
"""

    return {"content": [{"type": "text", "text": text}]}


async def assign_project_to_product(
    product_service: ProductService,
    project_id: str,
    product_id: str,
) -> dict[str, Any]:
    """Assign an existing project to a product."""
    project = await product_service.assign_project_to_product(project_id, product_id)

    if project is None:
        return {
            "content": [{"type": "text", "text": "Failed to assign project"}],
            "isError": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Assigned project {project.name} to product {product_id}",
            }
        ]
    }
