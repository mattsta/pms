"""API routes for authentication and API key management."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_auth_service
from pms.models.api_key import ApiKey
from pms.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Type alias for cleaner signatures
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


# Request/Response models
class CreateApiKeyRequest(BaseModel):
    """Request to create a new API key."""

    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(..., min_length=1)
    expires_in_days: int | None = Field(None, gt=0, le=3650)  # Max 10 years
    rate_limit: int | None = Field(None, gt=0, le=10000)  # Max 10k req/min
    metadata: dict[str, str] = Field(default_factory=dict)


class ApiKeyResponse(BaseModel):
    """API key information (without the actual key)."""

    id: str
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    is_active: bool
    scopes: list[str]
    metadata: dict[str, str]
    rate_limit: int | None
    archived_at: datetime | None = None

    @classmethod
    def from_model(cls, api_key: ApiKey) -> ApiKeyResponse:
        return cls(
            id=api_key.id,
            name=api_key.name,
            prefix=api_key.prefix,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
            is_active=api_key.is_active,
            scopes=api_key.scopes,
            metadata=api_key.metadata,
            rate_limit=api_key.rate_limit,
            archived_at=api_key.archived_at,
        )


class CreateApiKeyResponse(BaseModel):
    """Response when creating an API key (includes plain key)."""

    api_key: str  # ONLY shown once!
    key_info: ApiKeyResponse


class AvailableScopesResponse(BaseModel):
    """List of available scopes."""

    scopes: list[str]


class InitApiKeyRequest(BaseModel):
    """Request to initialize the first admin API key."""

    name: str = Field("Admin Key", min_length=1, max_length=100)


# Routes
@router.get("/scopes", response_model=AvailableScopesResponse)
async def list_available_scopes() -> AvailableScopesResponse:
    """Get list of all available scopes."""
    return AvailableScopesResponse(scopes=Scopes.all_scopes())


@router.post(
    "/init",
    response_model=CreateApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def init_admin_key(
    request: InitApiKeyRequest,
    auth_service: AuthServiceDep,
) -> CreateApiKeyResponse:
    """
    Initialize authentication by creating the first admin API key.

    This endpoint only works when no admin keys exist.
    """
    existing_keys = await auth_service.list_keys()
    admin_keys = [
        key for key in existing_keys if "*" in key.scopes or "admin:keys" in key.scopes
    ]
    if admin_keys:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin key already exists",
        )

    plain_key, api_key = await auth_service.create_api_key(
        name=request.name,
        scopes=["*"],
        expires_in_days=None,
        rate_limit=None,
        metadata={"type": "admin", "created_by": "api_bootstrap"},
    )

    return CreateApiKeyResponse(
        api_key=plain_key,
        key_info=ApiKeyResponse.from_model(api_key),
    )


@router.post(
    "/keys",
    response_model=CreateApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope("admin:keys"))],
)
async def create_api_key(
    request: CreateApiKeyRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> CreateApiKeyResponse:
    """
    Create a new API key.

    **Requires**: admin:keys scope

    **WARNING**: The plain API key is only shown once! Store it securely.
    """
    plain_key, api_key = await auth_service.create_api_key(
        name=request.name,
        scopes=request.scopes,
        expires_in_days=request.expires_in_days,
        rate_limit=request.rate_limit,
        metadata=request.metadata,
    )

    return CreateApiKeyResponse(
        api_key=plain_key,
        key_info=ApiKeyResponse.from_model(api_key),
    )


@router.get(
    "/keys",
    response_model=list[ApiKeyResponse],
    dependencies=[Depends(require_scope("admin:keys"))],
)
async def list_api_keys(
    include_inactive: bool = False,
    include_archived: bool = False,
    auth_service: AuthService = Depends(get_auth_service),
) -> list[ApiKeyResponse]:
    """
    List all API keys.

    **Requires**: admin:keys scope
    """
    keys = await auth_service.list_keys(
        include_inactive=include_inactive,
        include_archived=include_archived,
    )
    return [ApiKeyResponse.from_model(k) for k in keys]


@router.get(
    "/keys/{key_id}",
    response_model=ApiKeyResponse,
    dependencies=[Depends(require_scope("admin:keys"))],
)
async def get_api_key(
    key_id: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiKeyResponse:
    """
    Get API key by ID.

    **Requires**: admin:keys scope
    """
    api_key = await auth_service.get_key_by_id(key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key not found: {key_id}",
        )
    return ApiKeyResponse.from_model(api_key)


@router.delete(
    "/keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_scope("admin:keys"))],
)
async def delete_api_key(
    key_id: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    """
    Delete an API key permanently.

    **Requires**: admin:keys scope
    """
    api_key = await auth_service.get_key_by_id(key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key not found: {key_id}",
        )

    await auth_service.delete_key(key_id)


@router.post(
    "/keys/{key_id}/restore",
    response_model=ApiKeyResponse,
    dependencies=[Depends(require_scope("admin:keys"))],
)
async def restore_api_key(
    key_id: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiKeyResponse:
    """
    Restore an archived API key or reactivate an inactive one.

    **Requires**: admin:keys scope
    """
    api_key = await auth_service.restore_key(key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key not found: {key_id}",
        )
    return ApiKeyResponse.from_model(api_key)


@router.post(
    "/keys/{key_id}/deactivate",
    response_model=ApiKeyResponse,
    dependencies=[Depends(require_scope("admin:keys"))],
)
async def deactivate_api_key(
    key_id: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> ApiKeyResponse:
    """
    Deactivate an API key (can be reactivated later).

    **Requires**: admin:keys scope
    """
    api_key = await auth_service.get_key_by_id(key_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key not found: {key_id}",
        )

    await auth_service.deactivate_key(key_id)

    # Return updated key
    updated_key = await auth_service.get_key_by_id(key_id)
    if updated_key is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API key state unavailable after deactivation: {key_id}",
        )
    return ApiKeyResponse.from_model(updated_key)
