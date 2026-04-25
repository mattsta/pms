"""Helpers for API response discoverability and continuation hints."""

from __future__ import annotations

from urllib.parse import urlencode

from pms.api.types import JsonObject

type QueryParamValue = str | int | bool | list[str] | None
type QueryParamMap = dict[str, QueryParamValue]
CLI_INVOKE_PREFIX_TEMPLATE = "<invoke-prefix>"


def build_query_path(path: str, params: QueryParamMap) -> str:
    """Build a URL path with deterministic query parameters."""
    query_items: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, list):
            query_items.extend((key, item) for item in value)
            continue
        if isinstance(value, bool):
            query_items.append((key, "true" if value else "false"))
            continue
        query_items.append((key, str(value)))
    if not query_items:
        return path
    return f"{path}?{urlencode(query_items, doseq=True)}"


def next_page_path(
    *,
    path: str,
    params: QueryParamMap,
    total_count: int,
    offset: int,
    limit: int,
) -> str | None:
    """Build a next-page URL path when more results are available."""
    if limit <= 0:
        return None
    if offset + limit >= total_count:
        return None
    return build_query_path(path, {**params, "offset": offset + limit})


def paginated_links(*, self_path: str, next_path: str | None) -> JsonObject:
    """Standard discoverability links for paginated API responses."""
    return {
        "self": self_path,
        "next": next_path,
        "guide": "/api/v1/",
    }


def normalize_next_steps(*steps: str) -> list[str]:
    """Normalize and de-duplicate continuation hints while preserving order."""
    normalized: list[str] = []
    for step in steps:
        step_value = step.strip()
        if not step_value or step_value in normalized:
            continue
        normalized.append(step_value)
    return normalized


def cli_command_template(command: str) -> str:
    """Render an invocation-agnostic CLI command template for API guidance."""
    candidate = command.strip()
    if not candidate:
        return candidate
    if candidate == CLI_INVOKE_PREFIX_TEMPLATE or candidate.startswith(
        f"{CLI_INVOKE_PREFIX_TEMPLATE} "
    ):
        return candidate
    if candidate == "pms":
        return CLI_INVOKE_PREFIX_TEMPLATE
    if candidate.startswith("pms "):
        return f"{CLI_INVOKE_PREFIX_TEMPLATE} {candidate[4:]}"
    return f"{CLI_INVOKE_PREFIX_TEMPLATE} {candidate}"


def detail_links(self_path: str, **extra_links: JsonValue) -> JsonObject:
    """Build a standard detail-response link map."""
    links: JsonObject = {
        "self": self_path,
        "guide": "/api/v1/",
    }
    for key, value in extra_links.items():
        links[key] = value
    return links
