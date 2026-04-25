"""Products API routes."""

from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import actor_reference_payload, resolve_owner_map
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_actor_service, get_product_service
from pms.api.models import ProductCreate, ProductResponse, ProductUpdate
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import PaginatedResponse
from pms.models import ProductStatus
from pms.models.api_key import ApiKey
from pms.services.actor_service import ActorService
from pms.services.product_service import ProductService

router = APIRouter()


def _product_response(
    product: object,
    owner_map: dict[str, object],
) -> ProductResponse:
    return ProductResponse(
        id=product.id,
        name=product.name,
        description=product.description,
        status=product.status.value,
        vision=product.vision,
        repository_url=product.repository_url,
        owner=actor_reference_payload(
            product.owner,
            owner_map,
            actor_id=product.owner_id,
        ),
        product_type=product.product_type,
        tags=list(product.tags),
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


class ProductSummaryStatsPayload(TypedDict):
    """Rollup statistics for a product summary."""

    total_projects: int
    total_tasks: int
    completed_tasks: int
    total_complexity_points: int
    total_goals: int
    completed_goals: int
    avg_goal_progress: float
    health_score: float


class ProductSummaryResponsePayload(TypedDict):
    """Product summary payload."""

    product: ProductResponse
    stats: ProductSummaryStatsPayload
    health_score: float


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    data: ProductCreate,
    product_service: ProductService = Depends(get_product_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PRODUCTS_WRITE)),
) -> ProductResponse:
    """Create a new product."""
    product = await product_service.create_product(
        name=data.name,
        description=data.description,
        vision=data.vision,
        repository_url=data.repository_url,
        owner=data.owner,
        product_type=data.product_type,
        tags=data.tags,
    )

    owner_map = await resolve_owner_map(actor_service, [product])
    return _product_response(product, owner_map)


@router.get("/products")
async def list_products(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    product_service: ProductService = Depends(get_product_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PRODUCTS_READ)),
) -> PaginatedResponse[ProductResponse]:
    """List all products."""
    status_filter = ProductStatus(status) if status else None
    result = await product_service.list_products(
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    params: QueryParamMap = {
        "status": status,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/products", params)
    next_path = next_page_path(
        path="/api/v1/products",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/products/{product_id}",
        "GET /api/v1/products/{product_id}/summary",
        "GET /api/v1/goals?product_id=<product_id>",
    )

    owner_map = await resolve_owner_map(actor_service, result.items)
    return {
        "items": [_product_response(p, owner_map) for p in result.items],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    product_service: ProductService = Depends(get_product_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PRODUCTS_READ)),
) -> ProductResponse:
    """Get a product by ID."""
    product = await product_service.get_product(product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    owner_map = await resolve_owner_map(actor_service, [product])
    return _product_response(product, owner_map)


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    data: ProductUpdate,
    product_service: ProductService = Depends(get_product_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PRODUCTS_WRITE)),
) -> ProductResponse:
    """Update a product."""
    # Convert status string to enum if provided
    status_enum = ProductStatus(data.status) if data.status else None

    product = await product_service.update_product(
        product_id=product_id,
        name=data.name,
        description=data.description,
        vision=data.vision,
        repository_url=data.repository_url,
        owner=data.owner,
        product_type=data.product_type,
        status=status_enum,
        tags=data.tags,
    )

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    owner_map = await resolve_owner_map(actor_service, [product])
    return _product_response(product, owner_map)


@router.get("/products/{product_id}/summary")
async def get_product_summary(
    product_id: str,
    product_service: ProductService = Depends(get_product_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PRODUCTS_READ)),
) -> ProductSummaryResponsePayload:
    """Get product summary with statistics."""
    summary = await product_service.get_product_summary(product_id)

    if summary is None:
        raise HTTPException(status_code=404, detail="Product not found")

    owner_map = await resolve_owner_map(actor_service, [summary.product])
    return {
        "product": _product_response(summary.product, owner_map),
        "stats": {
            "total_projects": summary.stats.total_projects if summary.stats else 0,
            "total_tasks": summary.stats.total_tasks if summary.stats else 0,
            "completed_tasks": summary.stats.completed_tasks if summary.stats else 0,
            "total_complexity_points": summary.stats.total_complexity_points
            if summary.stats
            else 0,
            "total_goals": summary.stats.total_goals if summary.stats else 0,
            "completed_goals": summary.stats.completed_goals if summary.stats else 0,
            "avg_goal_progress": summary.stats.avg_goal_progress
            if summary.stats
            else 0,
            "health_score": summary.stats.health_score if summary.stats else 100,
        },
        "health_score": summary.health_score,
    }


@router.post("/products/{product_id}/archive")
async def archive_product(
    product_id: str,
    product_service: ProductService = Depends(get_product_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PRODUCTS_WRITE)),
) -> dict[str, str]:
    """Archive a product."""
    product = await product_service.archive_product(product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return {"status": "archived", "product_id": product.id}
