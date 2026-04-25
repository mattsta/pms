"""Custom field API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_custom_field_service
from pms.api.models import (
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionResponse,
    CustomFieldDefinitionUpdate,
    CustomFieldValueCreate,
    CustomFieldValueItemResponse,
    CustomFieldValueResponse,
    CustomFieldValuesResponse,
)
from pms.models.api_key import ApiKey
from pms.models.custom_field import (
    CustomFieldDefinition,
    CustomFieldType,
    CustomFieldValue,
)
from pms.services.custom_field_service import CustomFieldService

router = APIRouter()


def _field_type(value: str | None) -> CustomFieldType | None:
    if value is None:
        return None
    try:
        return CustomFieldType(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid field_type") from exc


def _definition_response(
    definition: CustomFieldDefinition,
) -> CustomFieldDefinitionResponse:
    return CustomFieldDefinitionResponse(
        id=definition.id,
        name=definition.name,
        entity_type=definition.entity_type,
        field_type=definition.field_type.value,
        description=definition.description,
        options=list(definition.options),
        is_required=definition.is_required,
        created_at=definition.created_at,
        updated_at=definition.updated_at,
        archived_at=definition.archived_at,
    )


def _value_response(value: CustomFieldValue) -> CustomFieldValueResponse:
    return CustomFieldValueResponse(
        id=value.id,
        field_id=value.field_id,
        entity_type=value.entity_type,
        entity_id=value.entity_id,
        value=value.value,
        created_by=value.created_by,
        source=value.source,
        metadata=value.metadata,
        created_at=value.created_at,
    )


@router.post(
    "/custom-fields", response_model=CustomFieldDefinitionResponse, status_code=201
)
async def create_custom_field(
    data: CustomFieldDefinitionCreate,
    service: CustomFieldService = Depends(get_custom_field_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.CUSTOM_FIELDS_WRITE)),
) -> CustomFieldDefinitionResponse:
    """Create a custom field definition."""
    try:
        definition = await service.create_definition(
            name=data.name,
            entity_type=data.entity_type,
            field_type=_field_type(data.field_type) or CustomFieldType.TEXT,
            description=data.description,
            options=data.options,
            is_required=data.is_required,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _definition_response(definition)


@router.get("/custom-fields")
async def list_custom_fields(
    entity_type: str | None = None,
    include_archived: bool = False,
    service: CustomFieldService = Depends(get_custom_field_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.CUSTOM_FIELDS_READ)),
) -> dict[str, list[CustomFieldDefinitionResponse]]:
    """List custom field definitions."""
    try:
        definitions = await service.list_definitions(
            entity_type=entity_type, include_archived=include_archived
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": [_definition_response(defn) for defn in definitions]}


@router.get("/custom-fields/values", response_model=CustomFieldValuesResponse)
async def list_custom_field_values(
    entity_type: str,
    entity_id: str,
    include_history: bool = False,
    limit: int = 100,
    offset: int = 0,
    service: CustomFieldService = Depends(get_custom_field_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.CUSTOM_FIELDS_READ)),
) -> CustomFieldValuesResponse:
    """List custom field values for an entity."""
    try:
        page = await service.list_values_for_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            include_history=include_history,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CustomFieldValuesResponse(
        items=[
            CustomFieldValueItemResponse(
                definition=_definition_response(item.definition)
                if item.definition
                else None,
                value=_value_response(item.value),
            )
            for item in page.items
        ],
        total_count=page.total_count,
        offset=page.offset,
        limit=page.limit,
    )


@router.get("/custom-fields/{field_id}", response_model=CustomFieldDefinitionResponse)
async def get_custom_field(
    field_id: str,
    service: CustomFieldService = Depends(get_custom_field_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.CUSTOM_FIELDS_READ)),
) -> CustomFieldDefinitionResponse:
    """Get a custom field definition."""
    definition = await service.get_definition(field_id, include_archived=True)
    if definition is None:
        raise HTTPException(status_code=404, detail="Custom field not found")
    return _definition_response(definition)


@router.patch("/custom-fields/{field_id}", response_model=CustomFieldDefinitionResponse)
async def update_custom_field(
    field_id: str,
    data: CustomFieldDefinitionUpdate,
    service: CustomFieldService = Depends(get_custom_field_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.CUSTOM_FIELDS_WRITE)),
) -> CustomFieldDefinitionResponse:
    """Update a custom field definition."""
    try:
        definition = await service.update_definition(
            field_id,
            name=data.name,
            description=data.description,
            field_type=_field_type(data.field_type),
            options=data.options,
            is_required=data.is_required,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if definition is None:
        raise HTTPException(status_code=404, detail="Custom field not found")
    return _definition_response(definition)


@router.delete("/custom-fields/{field_id}")
async def delete_custom_field(
    field_id: str,
    service: CustomFieldService = Depends(get_custom_field_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.CUSTOM_FIELDS_DELETE)),
) -> dict[str, str]:
    """Archive a custom field definition."""
    await service.delete_definition(field_id)
    return {"status": "deleted", "field_id": field_id}


@router.post("/custom-fields/{field_id}/restore")
async def restore_custom_field(
    field_id: str,
    service: CustomFieldService = Depends(get_custom_field_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.CUSTOM_FIELDS_WRITE)),
) -> CustomFieldDefinitionResponse:
    """Restore a custom field definition."""
    definition = await service.restore_definition(field_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Custom field not found")
    return _definition_response(definition)


@router.post(
    "/custom-fields/{field_id}/values",
    response_model=CustomFieldValueItemResponse,
    status_code=201,
)
async def set_custom_field_value(
    field_id: str,
    data: CustomFieldValueCreate,
    service: CustomFieldService = Depends(get_custom_field_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.CUSTOM_FIELDS_WRITE)),
) -> CustomFieldValueItemResponse:
    """Set a custom field value for an entity."""
    try:
        item = await service.set_value(
            field_id,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            value=data.value,
            created_by=data.created_by,
            source=data.source,
            metadata=data.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CustomFieldValueItemResponse(
        definition=_definition_response(item.definition) if item.definition else None,
        value=_value_response(item.value),
    )


@router.get(
    "/custom-fields/{field_id}/values", response_model=CustomFieldValuesResponse
)
async def list_custom_field_values_for_field(
    field_id: str,
    limit: int = 100,
    offset: int = 0,
    service: CustomFieldService = Depends(get_custom_field_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.CUSTOM_FIELDS_READ)),
) -> CustomFieldValuesResponse:
    """List custom field values for a field definition."""
    page = await service.list_values_for_field(field_id, limit=limit, offset=offset)
    return CustomFieldValuesResponse(
        items=[
            CustomFieldValueItemResponse(
                definition=_definition_response(item.definition)
                if item.definition
                else None,
                value=_value_response(item.value),
            )
            for item in page.items
        ],
        total_count=page.total_count,
        offset=page.offset,
        limit=page.limit,
    )
