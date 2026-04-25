"""HTTP client for PMS API server."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import TracebackType
from typing import Any, Self

import httpx

from pms.models.automation_rule import AutomationActionType
from pms.models.json_types import JsonObject
from pms.models.value_contracts import RetentionUsageSort, SortDirection
from pms.runtime.defaults import LOCAL_SERVER_DEFAULT_BASE_URL


class PMSClient:
    """Fast HTTP client for PMS API server."""

    def __init__(
        self, base_url: str = LOCAL_SERVER_DEFAULT_BASE_URL, api_key: str | None = None
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            headers=headers or None,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client:
            await self._client.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with'.")
        return self._client

    @staticmethod
    def _json_dict(response: httpx.Response) -> dict[str, Any]:
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError(f"Expected JSON object, got {type(payload).__name__}")
        return payload

    @staticmethod
    def _json_list(response: httpx.Response) -> list[dict[str, Any]]:
        payload = response.json()
        if not isinstance(payload, list):
            raise TypeError(f"Expected JSON array, got {type(payload).__name__}")
        if not all(isinstance(item, dict) for item in payload):
            raise TypeError("Expected JSON array of objects")
        return payload

    @staticmethod
    def _query_params(**params: Any) -> dict[str, Any]:
        return {key: value for key, value in params.items() if value is not None}

    @staticmethod
    def _task_action_payload(
        reason: str | None, updated_by: str | None
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        if updated_by is not None:
            payload["updated_by"] = updated_by
        return payload or None

    async def create_product(
        self,
        name: str,
        description: str | None = None,
        vision: str | None = None,
        repository_url: str | None = None,
        owner: str | None = None,
        product_type: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/products",
            json={
                "name": name,
                "description": description,
                "vision": vision,
                "repository_url": repository_url,
                "owner": owner,
                "product_type": product_type,
                "tags": tags or [],
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_product(self, product_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/products/{product_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_product_summary(self, product_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/products/{product_id}/summary")
        response.raise_for_status()
        return self._json_dict(response)

    async def archive_product(self, product_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/products/{product_id}/archive")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_product(
        self,
        product_id: str,
        name: str | None = None,
        description: str | None = None,
        vision: str | None = None,
        repository_url: str | None = None,
        owner: str | None = None,
        product_type: str | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if vision is not None:
            payload["vision"] = vision
        if repository_url is not None:
            payload["repository_url"] = repository_url
        if owner is not None:
            payload["owner"] = owner
        if product_type is not None:
            payload["product_type"] = product_type
        if status is not None:
            payload["status"] = status
        if tags is not None:
            payload["tags"] = tags
        response = await client.patch(f"/api/v1/products/{product_id}", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def list_products(
        self, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/products",
            params={"status": status, "limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_project(
        self,
        name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        product_id: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/projects",
            json={
                "name": name,
                "description": description,
                "tags": tags or [],
                "org_id": org_id,
                "portfolio_id": portfolio_id,
                "program_id": program_id,
                "product_id": product_id,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_projects(
        self, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/projects",
            params={"status": status, "limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_project(self, project_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/projects/{project_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_project_summary(self, project_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/projects/{project_id}/summary")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_dashboard(self) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get("/api/v1/dashboard")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_project(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        product_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if tags is not None:
            payload["tags"] = tags
        if org_id is not None:
            payload["org_id"] = org_id
        if portfolio_id is not None:
            payload["portfolio_id"] = portfolio_id
        if program_id is not None:
            payload["program_id"] = program_id
        if product_id is not None:
            payload["product_id"] = product_id

        client = self._get_client()
        response = await client.patch(f"/api/v1/projects/{project_id}", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def create_organization(
        self,
        name: str,
        description: str | None = None,
        owner: str | None = None,
        members: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/organizations",
            json={
                "name": name,
                "description": description,
                "owner": owner,
                "members": members or [],
                "tags": tags or [],
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_organization(self, org_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/organizations/{org_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def list_organizations(
        self, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/organizations",
            params={"status": status, "limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def update_organization(
        self,
        org_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        members: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if owner is not None:
            payload["owner"] = owner
        if members is not None:
            payload["members"] = members
        if tags is not None:
            payload["tags"] = tags

        client = self._get_client()
        response = await client.patch(f"/api/v1/organizations/{org_id}", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def get_organization_summary(self, org_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/organizations/{org_id}/summary")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_organization_dashboard(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
        include_digest: bool = True,
        include_next_actions: bool = True,
        include_evidence: bool = True,
        include_retention: bool = True,
        next_limit: int = 3,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/organizations/dashboard",
            params=self._query_params(
                status=status,
                limit=limit,
                offset=offset,
                include_digest=include_digest,
                include_next_actions=include_next_actions,
                include_evidence=include_evidence,
                include_retention=include_retention,
                next_limit=next_limit,
            ),
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_team(
        self,
        name: str,
        org_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        members: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/teams",
            json={
                "name": name,
                "org_id": org_id,
                "description": description,
                "owner": owner,
                "members": members or [],
                "tags": tags or [],
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_team(self, team_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/teams/{team_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def list_teams(
        self,
        status: str | None = None,
        org_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/teams",
            params={
                "status": status,
                "org_id": org_id,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def update_team(
        self,
        team_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        members: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if owner is not None:
            payload["owner"] = owner
        if members is not None:
            payload["members"] = members
        if tags is not None:
            payload["tags"] = tags

        client = self._get_client()
        response = await client.patch(f"/api/v1/teams/{team_id}", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def add_task_evidence(
        self,
        task_id: str,
        evidence_type: str,
        reference: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/evidence",
            json={
                "evidence_type": evidence_type,
                "reference": reference,
                "description": description,
                "metadata": metadata or {},
                "created_by": created_by,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_task_evidence(
        self,
        task_id: str,
        include_test_runs: bool = False,
        include_output: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/tasks/{task_id}/evidence",
            params={
                "include_test_runs": include_test_runs,
                "include_output": include_output,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_task_proof_bundle(
        self,
        task_id: str,
        include_output: bool = False,
        include_logs: bool = False,
        include_artifacts: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/tasks/{task_id}/proof-bundle",
            params={
                "include_output": include_output,
                "include_logs": include_logs,
                "include_artifacts": include_artifacts,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_revision_diff(
        self,
        entity_type: str,
        entity_id: str,
        from_revision: int,
        to_revision: int,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/revisions/{entity_type}/{entity_id}/diff",
            params={
                "from_revision": from_revision,
                "to_revision": to_revision,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_revision_history_bundle(
        self,
        entity_type: str,
        entity_id: str,
        include_linked: bool = False,
        include_linked_history: bool = False,
        history_limit: int = 20,
        history_offset: int = 0,
        linked_limit: int = 20,
        linked_history_limit: int | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        params: dict[str, Any] = {
            "include_linked": include_linked or include_linked_history,
            "include_linked_history": include_linked_history,
            "history_limit": history_limit,
            "history_offset": history_offset,
            "linked_limit": linked_limit,
        }
        if linked_history_limit is not None:
            params["linked_history_limit"] = linked_history_limit
        response = await client.get(
            f"/api/v1/revisions/{entity_type}/{entity_id}/bundle",
            params=params,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def search_evidence_bundles(
        self,
        task_id: list[str] | None = None,
        plan_id: str | None = None,
        status: list[str] | None = None,
        evidence_type: list[str] | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        include_evidence: bool = False,
        include_test_runs: bool = False,
        include_output: bool = False,
        include_logs: bool = False,
        include_artifacts: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "include_evidence": include_evidence,
            "include_test_runs": include_test_runs or include_output,
            "include_output": include_output,
            "include_logs": include_logs,
            "include_artifacts": include_artifacts,
            "limit": limit,
            "offset": offset,
        }
        if task_id:
            params["task_id"] = task_id
        if plan_id:
            params["plan_id"] = plan_id
        if status:
            params["status"] = status
        if evidence_type:
            params["evidence_type"] = evidence_type
        if created_from:
            params["created_from"] = created_from
        if created_to:
            params["created_to"] = created_to

        client = self._get_client()
        response = await client.get("/api/v1/evidence/bundles", params=params)
        response.raise_for_status()
        return self._json_dict(response)

    async def create_test_run(
        self,
        server_id: str,
        success: bool,
        started_at: str,
        finished_at: str,
        project_id: str | None = None,
        run_id: str | None = None,
        exit_code: int | None = None,
        duration_seconds: float | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
        logs: dict[str, Any] | None = None,
        artifacts: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        command: str | None = None,
        runner: str | None = None,
        plan_id: str | None = None,
        task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "server_id": server_id,
            "success": success,
            "started_at": started_at,
            "finished_at": finished_at,
            "logs": logs or {},
            "artifacts": artifacts or {},
            "config": config or {},
            "task_ids": task_ids or [],
        }
        if project_id:
            payload["project_id"] = project_id
        if run_id:
            payload["run_id"] = run_id
        if exit_code is not None:
            payload["exit_code"] = exit_code
        if duration_seconds is not None:
            payload["duration_seconds"] = duration_seconds
        if stdout is not None:
            payload["stdout"] = stdout
        if stderr is not None:
            payload["stderr"] = stderr
        if command is not None:
            payload["command"] = command
        if runner is not None:
            payload["runner"] = runner
        if plan_id is not None:
            payload["plan_id"] = plan_id

        client = self._get_client()
        response = await client.post("/api/v1/test-runs", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def list_test_runs(
        self,
        project_id: str | None = None,
        server_id: str | None = None,
        success: bool | None = None,
        include_output: bool = False,
        include_logs: bool = False,
        include_artifacts: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "include_output": include_output,
            "include_logs": include_logs,
            "include_artifacts": include_artifacts,
            "limit": limit,
            "offset": offset,
        }
        if project_id:
            params["project_id"] = project_id
        if server_id:
            params["server_id"] = server_id
        if success is not None:
            params["success"] = success

        client = self._get_client()
        response = await client.get("/api/v1/test-runs", params=params)
        response.raise_for_status()
        return self._json_dict(response)

    async def get_test_run(
        self,
        run_id: str,
        include_output: bool = True,
        include_logs: bool = True,
        include_artifacts: bool = True,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/test-runs/{run_id}",
            params={
                "include_output": include_output,
                "include_logs": include_logs,
                "include_artifacts": include_artifacts,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def prune_test_runs(
        self,
        max_log_bytes: int | None = None,
        max_artifact_bytes: int | None = None,
        max_age_days: int | None = None,
        dry_run: bool = False,
        project_id: str | None = None,
        org_id: str | None = None,
        use_policies: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"dry_run": dry_run}
        if max_log_bytes is not None:
            params["max_log_bytes"] = max_log_bytes
        if max_artifact_bytes is not None:
            params["max_artifact_bytes"] = max_artifact_bytes
        if max_age_days is not None:
            params["max_age_days"] = max_age_days
        if project_id is not None:
            params["project_id"] = project_id
        if org_id is not None:
            params["org_id"] = org_id
        if not use_policies:
            params["use_policies"] = False

        client = self._get_client()
        response = await client.post("/api/v1/test-runs/prune", params=params)
        response.raise_for_status()
        return self._json_dict(response)

    async def get_test_run_retention(
        self,
        limit: int = 20,
        sort: RetentionUsageSort = "largest",
        project_id: str | None = None,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        params: dict[str, Any] = {"limit": limit, "sort": sort}
        if project_id is not None:
            params["project_id"] = project_id
        if org_id is not None:
            params["org_id"] = org_id
        response = await client.get("/api/v1/test-runs/retention", params=params)
        response.raise_for_status()
        return self._json_dict(response)

    async def list_test_run_retention_policies(
        self,
        scope_type: str | None = None,
        scope_id: str | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "include_archived": include_archived,
            "limit": limit,
            "offset": offset,
        }
        if scope_type is not None:
            params["scope_type"] = scope_type
        if scope_id is not None:
            params["scope_id"] = scope_id
        client = self._get_client()
        response = await client.get(
            "/api/v1/test-runs/retention/policies",
            params=params,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def upsert_test_run_retention_policy(
        self,
        scope_type: str,
        scope_id: str,
        max_log_bytes: int = 0,
        max_artifact_bytes: int = 0,
        max_age_days: int = 0,
        notes: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "max_log_bytes": max_log_bytes,
            "max_artifact_bytes": max_artifact_bytes,
            "max_age_days": max_age_days,
        }
        if notes is not None:
            params["notes"] = notes
        client = self._get_client()
        response = await client.post(
            "/api/v1/test-runs/retention/policies",
            params=params,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_test_run_retention_policy(self, policy_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/test-runs/retention/policies/{policy_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_test_run_retention_policy(
        self,
        policy_id: str,
        max_log_bytes: int | None = None,
        max_artifact_bytes: int | None = None,
        max_age_days: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if max_log_bytes is not None:
            params["max_log_bytes"] = max_log_bytes
        if max_artifact_bytes is not None:
            params["max_artifact_bytes"] = max_artifact_bytes
        if max_age_days is not None:
            params["max_age_days"] = max_age_days
        if notes is not None:
            params["notes"] = notes
        client = self._get_client()
        response = await client.patch(
            f"/api/v1/test-runs/retention/policies/{policy_id}",
            params=params,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def archive_test_run_retention_policy(self, policy_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/test-runs/retention/policies/{policy_id}/archive"
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_test_run_retention_policy(self, policy_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/test-runs/retention/policies/{policy_id}/restore"
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_work_snapshot(
        self,
        scope_type: str,
        scope_id: str,
        task_limit: int = 5,
        test_limit: int = 5,
        include_history: bool = True,
        history_limit: int = 3,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/work-snapshots/{scope_type}/{scope_id}",
            params={
                "task_limit": task_limit,
                "test_limit": test_limit,
                "include_history": include_history,
                "history_limit": history_limit,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_work_daily(
        self,
        scope_type: str,
        scope_id: str,
        task_limit: int = 5,
        test_limit: int = 5,
        queue_limit: int = 3,
        stale_days: int = 14,
        at_risk_days: int = 7,
        include_timeline: bool = False,
        timeline_limit: int = 5,
        include_history: bool = False,
        history_limit: int = 3,
        view: str = "detail",
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/work-snapshots/{scope_type}/{scope_id}/daily",
            params={
                "task_limit": task_limit,
                "test_limit": test_limit,
                "queue_limit": queue_limit,
                "stale_days": stale_days,
                "at_risk_days": at_risk_days,
                "include_timeline": include_timeline,
                "timeline_limit": timeline_limit,
                "include_history": include_history,
                "history_limit": history_limit,
                "view": view,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def mark_work_snapshot_reviewed(
        self,
        scope_type: str,
        scope_id: str,
        reviewed_by: str | None = None,
        note: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/work-snapshots/{scope_type}/{scope_id}/review",
            json={
                "reviewed_by": reviewed_by,
                "note": note,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_label_category(
        self,
        name: str,
        description: str | None = None,
        is_exclusive: bool = False,
        sort_order: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/labels/categories",
            json={
                "name": name,
                "description": description,
                "is_exclusive": is_exclusive,
                "sort_order": sort_order,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_label_categories(
        self, include_archived: bool = False
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/labels/categories",
            params={"include_archived": include_archived} if include_archived else None,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_label_category(self, category_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/labels/categories/{category_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_label_category(
        self,
        category_id: str,
        name: str | None = None,
        description: str | None = None,
        is_exclusive: bool | None = None,
        sort_order: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if is_exclusive is not None:
            payload["is_exclusive"] = is_exclusive
        if sort_order is not None:
            payload["sort_order"] = sort_order

        client = self._get_client()
        response = await client.patch(
            f"/api/v1/labels/categories/{category_id}", json=payload
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_label_category(self, category_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/labels/categories/{category_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_label_category(self, category_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/labels/categories/{category_id}/restore")
        response.raise_for_status()
        return self._json_dict(response)

    async def create_label(
        self,
        name: str,
        description: str | None = None,
        category_id: str | None = None,
        color: str | None = None,
        is_system: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/labels",
            json={
                "name": name,
                "description": description,
                "category_id": category_id,
                "color": color,
                "is_system": is_system,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_labels(
        self, category_id: str | None = None, include_archived: bool = False
    ) -> dict[str, Any]:
        client = self._get_client()
        params: dict[str, Any] = {}
        if category_id:
            params["category_id"] = category_id
        if include_archived:
            params["include_archived"] = include_archived
        response = await client.get("/api/v1/labels", params=params or None)
        response.raise_for_status()
        return self._json_dict(response)

    async def get_label(self, label_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/labels/{label_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_label(
        self,
        label_id: str,
        name: str | None = None,
        description: str | None = None,
        category_id: str | None = None,
        color: str | None = None,
        is_system: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if category_id is not None:
            payload["category_id"] = category_id
        if color is not None:
            payload["color"] = color
        if is_system is not None:
            payload["is_system"] = is_system

        client = self._get_client()
        response = await client.patch(f"/api/v1/labels/{label_id}", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_label(self, label_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/labels/{label_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_label(self, label_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/labels/{label_id}/restore")
        response.raise_for_status()
        return self._json_dict(response)

    async def assign_label(
        self,
        entity_type: str,
        entity_id: str,
        label_id: str,
        applied_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/labels/assignments",
            json={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "label_id": label_id,
                "applied_by": applied_by,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_label_assignments(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/labels/assignments",
            params={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_label_assignment_history(
        self,
        assignment_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/labels/assignments/{assignment_id}/history",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def remove_label_assignment(
        self, entity_type: str, entity_id: str, label_id: str
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(
            "/api/v1/labels/assignments",
            params={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "label_id": label_id,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_label_gate_rule(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
        rule_type: str,
        label_id: str | None = None,
        category_id: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/labels/gates",
            json={
                "workflow_id": workflow_id,
                "entity_type": entity_type,
                "from_state": from_state,
                "to_state": to_state,
                "rule_type": rule_type,
                "label_id": label_id,
                "category_id": category_id,
                "message": message,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_label_gate_rules(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/labels/gates",
            params={
                "workflow_id": workflow_id,
                "entity_type": entity_type,
                "from_state": from_state,
                "to_state": to_state,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_label_gate_rule(self, rule_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/labels/gates/{rule_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def create_evidence_gate_rule(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
        evidence_type: str,
        min_count: int = 1,
        require_success: bool = False,
        message: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/evidence/gates",
            json={
                "workflow_id": workflow_id,
                "entity_type": entity_type,
                "from_state": from_state,
                "to_state": to_state,
                "evidence_type": evidence_type,
                "min_count": min_count,
                "require_success": require_success,
                "message": message,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_evidence_gate_rules(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/evidence/gates",
            params={
                "workflow_id": workflow_id,
                "entity_type": entity_type,
                "from_state": from_state,
                "to_state": to_state,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_evidence_gate_rule(self, rule_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/evidence/gates/{rule_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def create_portfolio(
        self,
        name: str,
        org_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        project_ids: list[str] | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/portfolios",
            json={
                "name": name,
                "org_id": org_id,
                "description": description,
                "owner": owner,
                "project_ids": project_ids or [],
                "goal_ids": goal_ids or [],
                "objective_ids": objective_ids or [],
                "tags": tags or [],
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_portfolio(self, portfolio_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/portfolios/{portfolio_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def list_portfolios(
        self,
        status: str | None = None,
        org_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/portfolios",
            params={
                "status": status,
                "org_id": org_id,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def update_portfolio(
        self,
        portfolio_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        project_ids: list[str] | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if owner is not None:
            payload["owner"] = owner
        if project_ids is not None:
            payload["project_ids"] = project_ids
        if goal_ids is not None:
            payload["goal_ids"] = goal_ids
        if objective_ids is not None:
            payload["objective_ids"] = objective_ids
        if tags is not None:
            payload["tags"] = tags

        client = self._get_client()
        response = await client.patch(
            f"/api/v1/portfolios/{portfolio_id}", json=payload
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_portfolio_summary(self, portfolio_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/portfolios/{portfolio_id}/summary")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_portfolio_dashboard(
        self,
        status: str | None = None,
        org_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        include_digest: bool = True,
        include_next_actions: bool = True,
        include_evidence: bool = True,
        include_retention: bool = True,
        next_limit: int = 3,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/portfolios/dashboard",
            params=self._query_params(
                status=status,
                org_id=org_id,
                limit=limit,
                offset=offset,
                include_digest=include_digest,
                include_next_actions=include_next_actions,
                include_evidence=include_evidence,
                include_retention=include_retention,
                next_limit=next_limit,
            ),
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_program(
        self,
        name: str,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        project_ids: list[str] | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/programs",
            json={
                "name": name,
                "org_id": org_id,
                "portfolio_id": portfolio_id,
                "description": description,
                "owner": owner,
                "project_ids": project_ids or [],
                "goal_ids": goal_ids or [],
                "objective_ids": objective_ids or [],
                "tags": tags or [],
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_program(self, program_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/programs/{program_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def list_programs(
        self,
        status: str | None = None,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/programs",
            params={
                "status": status,
                "org_id": org_id,
                "portfolio_id": portfolio_id,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def update_program(
        self,
        program_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        project_ids: list[str] | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if owner is not None:
            payload["owner"] = owner
        if project_ids is not None:
            payload["project_ids"] = project_ids
        if goal_ids is not None:
            payload["goal_ids"] = goal_ids
        if objective_ids is not None:
            payload["objective_ids"] = objective_ids
        if tags is not None:
            payload["tags"] = tags

        client = self._get_client()
        response = await client.patch(f"/api/v1/programs/{program_id}", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def get_program_summary(self, program_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/programs/{program_id}/summary")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_program_dashboard(
        self,
        status: str | None = None,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        include_digest: bool = True,
        include_next_actions: bool = True,
        include_evidence: bool = True,
        include_retention: bool = True,
        next_limit: int = 3,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/programs/dashboard",
            params=self._query_params(
                status=status,
                org_id=org_id,
                portfolio_id=portfolio_id,
                limit=limit,
                offset=offset,
                include_digest=include_digest,
                include_next_actions=include_next_actions,
                include_evidence=include_evidence,
                include_retention=include_retention,
                next_limit=next_limit,
            ),
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_actor(
        self,
        name: str,
        kind: str = "human",
        handle: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/actors",
            json={
                "name": name,
                "kind": kind,
                "handle": handle,
                "description": description,
                "tags": tags or [],
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_actors(
        self,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/actors",
            params={
                "kind": kind,
                "status": status,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_actor(
        self,
        actor: str,
        include_inherited: bool = True,
        task_limit: int = 25,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/actors/{actor}",
            params={
                "include_inherited": include_inherited,
                "task_limit": task_limit,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def add_actor_alias(
        self,
        actor: str,
        alias: str,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/actors/{actor}/aliases",
            json={"alias": alias},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def add_actor_membership(
        self,
        actor: str,
        member: str,
        role: str = "member",
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/actors/{actor}/memberships",
            json={
                "member": member,
                "role": role,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_goal(
        self,
        name: str,
        description: str | None = None,
        horizon: str = "short_term",
        target_date: str | None = None,
        owner: str | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/goals",
            json={
                "name": name,
                "description": description,
                "horizon": horizon,
                "target_date": target_date,
                "owner": owner,
                "product_id": product_id,
                "project_id": project_id,
                "tags": tags or [],
                "progress_percent": progress_percent,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_goals(
        self,
        status: str | None = None,
        horizon: str | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/goals",
            params={
                "status": status,
                "horizon": horizon,
                "product_id": product_id,
                "project_id": project_id,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_goal(self, goal_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/goals/{goal_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_goal(
        self,
        goal_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        horizon: str | None = None,
        target_date: str | None = None,
        owner: str | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if horizon is not None:
            payload["horizon"] = horizon
        if target_date is not None:
            payload["target_date"] = target_date
        if owner is not None:
            payload["owner"] = owner
        if product_id is not None:
            payload["product_id"] = product_id
        if project_id is not None:
            payload["project_id"] = project_id
        if tags is not None:
            payload["tags"] = tags
        if progress_percent is not None:
            payload["progress_percent"] = progress_percent

        client = self._get_client()
        response = await client.patch(f"/api/v1/goals/{goal_id}", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def complete_goal(self, goal_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/goals/{goal_id}/complete")
        response.raise_for_status()
        return self._json_dict(response)

    async def archive_goal(self, goal_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/goals/{goal_id}/archive")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_goal_summary(self, goal_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/goals/{goal_id}/summary")
        response.raise_for_status()
        return self._json_dict(response)

    async def assign_goal_workflow(
        self,
        goal_id: str,
        workflow_name: str,
        initial_state: str,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/goals/{goal_id}/workflow/assign",
            json={
                "workflow_name": workflow_name,
                "initial_state": initial_state,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def transition_goal_workflow(
        self,
        goal_id: str,
        to_state: str,
        triggered_by: str,
        reason: str | None = None,
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/goals/{goal_id}/workflow/transition",
            json={
                "to_state": to_state,
                "triggered_by": triggered_by,
                "reason": reason,
                "approved_by": approved_by,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_plan(
        self,
        name: str,
        description: str | None = None,
        status: str = "draft",
        format: str = "json",
        content: Any = None,
        product_id: str | None = None,
        project_id: str | None = None,
        goal_id: str | None = None,
        objective_id: str | None = None,
        task_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/plans",
            json={
                "name": name,
                "description": description,
                "status": status,
                "format": format,
                "content": content,
                "product_id": product_id,
                "project_id": project_id,
                "goal_id": goal_id,
                "objective_id": objective_id,
                "task_ids": task_ids or [],
                "tags": tags or [],
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_plans(
        self,
        status: str | None = None,
        project_id: str | None = None,
        product_id: str | None = None,
        goal_id: str | None = None,
        objective_id: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/plans",
            params={
                "status": status,
                "project_id": project_id,
                "product_id": product_id,
                "goal_id": goal_id,
                "objective_id": objective_id,
                "task_id": task_id,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_plan_lineage(
        self,
        status: str | None = None,
        project_id: str | None = None,
        plan_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        task_limit: int = 10,
        test_limit: int = 5,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/plans/lineage",
            params={
                "status": status,
                "project_id": project_id,
                "plan_id": plan_id,
                "limit": limit,
                "offset": offset,
                "task_limit": task_limit,
                "test_limit": test_limit,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_plan(self, plan_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/plans/{plan_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_plan(
        self,
        plan_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        format: str | None = None,
        content: Any | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        goal_id: str | None = None,
        objective_id: str | None = None,
        task_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if format is not None:
            payload["format"] = format
        if content is not None:
            payload["content"] = content
        if product_id is not None:
            payload["product_id"] = product_id
        if project_id is not None:
            payload["project_id"] = project_id
        if goal_id is not None:
            payload["goal_id"] = goal_id
        if objective_id is not None:
            payload["objective_id"] = objective_id
        if task_ids is not None:
            payload["task_ids"] = task_ids
        if tags is not None:
            payload["tags"] = tags

        client = self._get_client()
        response = await client.patch(f"/api/v1/plans/{plan_id}", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    def _env_vars_payload(
        self, env_vars: dict[str, str] | list[tuple[str, str]] | None
    ) -> list[dict[str, str]]:
        if not env_vars:
            return []
        if isinstance(env_vars, dict):
            return [{"key": key, "value": value} for key, value in env_vars.items()]
        return [{"key": key, "value": value} for key, value in env_vars]

    async def create_plan_test_job(
        self,
        plan_id: str,
        name: str,
        project_path: str,
        description: str | None = None,
        mode: str = "local",
        test_command: str = "pytest",
        setup_command: str | None = None,
        working_dir: str | None = None,
        env_vars: dict[str, str] | list[tuple[str, str]] | None = None,
        timeout: float = 600.0,
        capture_logs: list[str] | None = None,
        save_artifacts: list[str] | None = None,
        task_ids: list[str] | None = None,
        transition_on_success: str | None = None,
        transition_on_failure: str | None = None,
        transition_by: str | None = None,
        transition_reason: str | None = None,
        project_id: str | None = None,
        server_id: str | None = None,
        server_name: str | None = None,
        remote_path: str = "/home/ec2-user/project",
        exclude_patterns: list[str] | None = None,
        stream_output: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/plans/{plan_id}/test-jobs",
            json={
                "name": name,
                "description": description,
                "mode": mode,
                "project_path": project_path,
                "test_command": test_command,
                "setup_command": setup_command,
                "working_dir": working_dir,
                "env_vars": self._env_vars_payload(env_vars),
                "timeout": timeout,
                "capture_logs": capture_logs or [],
                "save_artifacts": save_artifacts or [],
                "task_ids": task_ids or [],
                "transition_on_success": transition_on_success,
                "transition_on_failure": transition_on_failure,
                "transition_by": transition_by,
                "transition_reason": transition_reason,
                "project_id": project_id,
                "server_id": server_id,
                "server_name": server_name,
                "remote_path": remote_path,
                "exclude_patterns": exclude_patterns,
                "stream_output": stream_output,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_plan_test_jobs(
        self,
        plan_id: str,
        limit: int = 100,
        offset: int = 0,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/plans/{plan_id}/test-jobs",
            params={
                "limit": limit,
                "offset": offset,
                "include_archived": include_archived,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_plan_test_job(self, plan_id: str, job_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/plans/{plan_id}/test-jobs/{job_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_plan_test_job(self, plan_id: str, job_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/plans/{plan_id}/test-jobs/{job_id}/restore"
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def update_plan_test_job(
        self,
        plan_id: str,
        job_id: str,
        name: str | None = None,
        description: str | None = None,
        mode: str | None = None,
        project_path: str | None = None,
        test_command: str | None = None,
        setup_command: str | None = None,
        working_dir: str | None = None,
        env_vars: dict[str, str] | list[tuple[str, str]] | None = None,
        timeout: float | None = None,
        capture_logs: list[str] | None = None,
        save_artifacts: list[str] | None = None,
        task_ids: list[str] | None = None,
        transition_on_success: str | None = None,
        transition_on_failure: str | None = None,
        transition_by: str | None = None,
        transition_reason: str | None = None,
        project_id: str | None = None,
        server_id: str | None = None,
        server_name: str | None = None,
        remote_path: str | None = None,
        exclude_patterns: list[str] | None = None,
        stream_output: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if mode is not None:
            payload["mode"] = mode
        if project_path is not None:
            payload["project_path"] = project_path
        if test_command is not None:
            payload["test_command"] = test_command
        if setup_command is not None:
            payload["setup_command"] = setup_command
        if working_dir is not None:
            payload["working_dir"] = working_dir
        if env_vars is not None:
            payload["env_vars"] = self._env_vars_payload(env_vars)
        if timeout is not None:
            payload["timeout"] = timeout
        if capture_logs is not None:
            payload["capture_logs"] = capture_logs
        if save_artifacts is not None:
            payload["save_artifacts"] = save_artifacts
        if task_ids is not None:
            payload["task_ids"] = task_ids
        if transition_on_success is not None:
            payload["transition_on_success"] = transition_on_success
        if transition_on_failure is not None:
            payload["transition_on_failure"] = transition_on_failure
        if transition_by is not None:
            payload["transition_by"] = transition_by
        if transition_reason is not None:
            payload["transition_reason"] = transition_reason
        if project_id is not None:
            payload["project_id"] = project_id
        if server_id is not None:
            payload["server_id"] = server_id
        if server_name is not None:
            payload["server_name"] = server_name
        if remote_path is not None:
            payload["remote_path"] = remote_path
        if exclude_patterns is not None:
            payload["exclude_patterns"] = exclude_patterns
        if stream_output is not None:
            payload["stream_output"] = stream_output

        client = self._get_client()
        response = await client.patch(
            f"/api/v1/plans/{plan_id}/test-jobs/{job_id}",
            json=payload,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_plan_test_job(self, plan_id: str, job_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/plans/{plan_id}/test-jobs/{job_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def run_plan_test_job(
        self,
        plan_id: str,
        job_id: str,
        include_output: bool = False,
        include_logs: bool = False,
        include_artifacts: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/plans/{plan_id}/test-jobs/{job_id}/run",
            params={
                "include_output": include_output,
                "include_logs": include_logs,
                "include_artifacts": include_artifacts,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_objective(
        self,
        goal_id: str,
        name: str,
        description: str | None = None,
        target_date: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/goals/{goal_id}/objectives",
            json={
                "name": name,
                "description": description,
                "target_date": target_date,
                "owner": owner,
                "tags": tags or [],
                "progress_percent": progress_percent,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_objectives(
        self,
        goal_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/goals/{goal_id}/objectives",
            params={"status": status, "limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_objective(self, objective_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/objectives/{objective_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_objective(
        self,
        objective_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        target_date: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if target_date is not None:
            payload["target_date"] = target_date
        if owner is not None:
            payload["owner"] = owner
        if tags is not None:
            payload["tags"] = tags
        if progress_percent is not None:
            payload["progress_percent"] = progress_percent

        client = self._get_client()
        response = await client.patch(
            f"/api/v1/objectives/{objective_id}", json=payload
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def complete_objective(self, objective_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/objectives/{objective_id}/complete")
        response.raise_for_status()
        return self._json_dict(response)

    async def archive_objective(self, objective_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/objectives/{objective_id}/archive")
        response.raise_for_status()
        return self._json_dict(response)

    async def assign_objective_workflow(
        self,
        objective_id: str,
        workflow_name: str,
        initial_state: str,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/objectives/{objective_id}/workflow/assign",
            json={
                "workflow_name": workflow_name,
                "initial_state": initial_state,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def transition_objective_workflow(
        self,
        objective_id: str,
        to_state: str,
        triggered_by: str,
        reason: str | None = None,
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/objectives/{objective_id}/workflow/transition",
            json={
                "to_state": to_state,
                "triggered_by": triggered_by,
                "reason": reason,
                "approved_by": approved_by,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_key_result(
        self,
        objective_id: str,
        name: str,
        description: str | None = None,
        current_value: float | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/objectives/{objective_id}/key-results",
            json={
                "name": name,
                "description": description,
                "current_value": current_value,
                "target_value": target_value,
                "unit": unit,
                "owner": owner,
                "tags": tags or [],
                "progress_percent": progress_percent,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_key_results(
        self,
        objective_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/objectives/{objective_id}/key-results",
            params={"status": status, "limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_key_result(self, key_result_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/key-results/{key_result_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_key_result(
        self,
        key_result_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        current_value: float | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if status is not None:
            payload["status"] = status
        if current_value is not None:
            payload["current_value"] = current_value
        if target_value is not None:
            payload["target_value"] = target_value
        if unit is not None:
            payload["unit"] = unit
        if owner is not None:
            payload["owner"] = owner
        if tags is not None:
            payload["tags"] = tags
        if progress_percent is not None:
            payload["progress_percent"] = progress_percent

        client = self._get_client()
        response = await client.patch(
            f"/api/v1/key-results/{key_result_id}", json=payload
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def complete_key_result(self, key_result_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/key-results/{key_result_id}/complete")
        response.raise_for_status()
        return self._json_dict(response)

    async def archive_key_result(self, key_result_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/key-results/{key_result_id}/archive")
        response.raise_for_status()
        return self._json_dict(response)

    async def checkout_task(
        self,
        task_id: str,
        agent_session_id: str,
        lease_seconds: int = 300,
        actor: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/checkout",
            json={
                "agent_session_id": agent_session_id,
                "lease_seconds": lease_seconds,
                "actor": actor,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def renew_checkout(
        self,
        task_id: str,
        agent_session_id: str,
        lease_seconds: int = 300,
        actor: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/checkout/renew",
            params={
                "agent_session_id": agent_session_id,
                "lease_seconds": lease_seconds,
                "actor": actor,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def release_checkout(
        self, task_id: str, agent_session_id: str
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/checkout/release",
            params={"agent_session_id": agent_session_id},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def force_release_checkout(
        self, task_id: str, released_by: str | None = None, reason: str | None = None
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/checkout/force-release",
            params={"released_by": released_by, "reason": reason},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_available_tasks(
        self,
        project_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/checkout/available",
            params={"project_id": project_id, "limit": limit},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_agent_checkouts(
        self, agent_session_id: str, include_expired: bool = False
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/checkout/status",
            params={
                "agent_session_id": agent_session_id,
                "include_expired": include_expired,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def cleanup_expired_checkouts(self, dry_run: bool = False) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/checkout/cleanup",
            params={"dry_run": dry_run},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_checkout_log(
        self,
        task_id: str | None = None,
        agent_session_id: str | None = None,
        action: str | None = None,
        success: bool | None = None,
        limit: int = 100,
        offset: int = 0,
        include_metadata: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/checkout/log",
            params={
                "task_id": task_id,
                "agent_session_id": agent_session_id,
                "action": action,
                "success": success,
                "limit": limit,
                "offset": offset,
                "include_metadata": include_metadata,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def iter_checkout_log(
        self,
        task_id: str | None = None,
        agent_session_id: str | None = None,
        action: str | None = None,
        success: bool | None = None,
        page_size: int = 100,
        include_metadata: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield checkout log entries across pages."""
        offset = 0
        while True:
            payload = await self.get_checkout_log(
                task_id=task_id,
                agent_session_id=agent_session_id,
                action=action,
                success=success,
                limit=page_size,
                offset=offset,
                include_metadata=include_metadata,
            )
            entries = payload.get("entries", [])
            if not entries:
                break
            for entry in entries:
                yield entry
            offset += len(entries)

    async def update_progress(
        self, task_id: str, percent_complete: int, status_message: str, updated_by: str
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/progress",
            json={
                "percent_complete": percent_complete,
                "status_message": status_message,
                "updated_by": updated_by,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_task(
        self,
        project_id: str,
        title: str,
        description: str | None = None,
        parent_id: str | None = None,
        complexity_points: int | None = None,
        priority: str = "medium",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/tasks",
            json={
                "project_id": project_id,
                "title": title,
                "description": description,
                "parent_id": parent_id,
                "complexity_points": complexity_points,
                "priority": priority,
                "tags": tags or [],
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_tasks(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/tasks",
            params={
                "project_id": project_id,
                "status": status,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_task_tree(
        self,
        project_id: str,
        root_task_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"project_id": project_id}
        if root_task_id:
            params["root_task_id"] = root_task_id
        client = self._get_client()
        response = await client.get("/api/v1/tasks/tree", params=params)
        response.raise_for_status()
        return self._json_dict(response)

    async def search_tasks(
        self,
        query: str | None = None,
        project_id: str | None = None,
        status: list[str] | None = None,
        priority: list[str] | None = None,
        assignee: str | None = None,
        tags: list[str] | None = None,
        label_id: list[str] | None = None,
        label_category_id: list[str] | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        updated_from: str | None = None,
        updated_to: str | None = None,
        due_from: str | None = None,
        due_to: str | None = None,
        include_terminal: bool = False,
        sort_by: str | None = None,
        sort_dir: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/tasks/search",
            params={
                "query": query,
                "project_id": project_id,
                "status": status,
                "priority": priority,
                "assignee": assignee,
                "tags": tags,
                "label_id": label_id,
                "label_category_id": label_category_id,
                "created_from": created_from,
                "created_to": created_to,
                "updated_from": updated_from,
                "updated_to": updated_to,
                "due_from": due_from,
                "due_to": due_to,
                "include_terminal": include_terminal,
                "sort_by": sort_by,
                "sort_dir": sort_dir,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_duplicate_tasks(
        self,
        project_id: str | None = None,
        status: list[str] | None = None,
        include_terminal: bool = False,
        min_count: int = 2,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/tasks/duplicates",
            params={
                "project_id": project_id,
                "status": status,
                "include_terminal": include_terminal,
                "min_count": min_count,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def preview_duplicate_merge(
        self,
        primary_task_id: str,
        duplicate_task_ids: list[str],
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/tasks/duplicates/preview",
            json={
                "primary_task_id": primary_task_id,
                "duplicate_task_ids": duplicate_task_ids,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def merge_duplicate_tasks(
        self,
        primary_task_id: str,
        duplicate_task_ids: list[str],
        cancel_duplicates: bool = True,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/tasks/duplicates/merge",
            json={
                "primary_task_id": primary_task_id,
                "duplicate_task_ids": duplicate_task_ids,
                "cancel_duplicates": cancel_duplicates,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_saved_search(
        self,
        name: str,
        description: str | None = None,
        owner: str | None = None,
        scope_type: str = "global",
        scope_id: str | None = None,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_dir: SortDirection | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/queues",
            json={
                "name": name,
                "description": description,
                "owner": owner,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "filters": filters or {},
                "sort_by": sort_by,
                "sort_dir": sort_dir,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_saved_searches(
        self,
        owner: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/queues",
            params={
                "owner": owner,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "limit": limit,
                "offset": offset,
                "include_archived": include_archived,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_saved_search(self, queue_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/queues/{queue_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_saved_search(
        self,
        queue_id: str,
        name: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_dir: SortDirection | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.put(
            f"/api/v1/queues/{queue_id}",
            json={
                "name": name,
                "description": description,
                "owner": owner,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "filters": filters,
                "sort_by": sort_by,
                "sort_dir": sort_dir,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_saved_search(self, queue_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/queues/{queue_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_saved_search(self, queue_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/queues/{queue_id}/restore")
        response.raise_for_status()
        return self._json_dict(response)

    async def run_saved_search(
        self, queue_id: str, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/queues/{queue_id}/run",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_queue_presets(
        self,
        project_id: str | None = None,
        limit: int = 5,
        stale_days: int = 14,
        at_risk_days: int = 7,
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/queues/presets",
            params={
                "project_id": project_id,
                "limit": limit,
                "stale_days": stale_days,
                "at_risk_days": at_risk_days,
            },
        )
        response.raise_for_status()
        return self._json_list(response)

    async def get_queue_preset(
        self,
        preset: str,
        project_id: str | None = None,
        limit: int = 10,
        offset: int = 0,
        stale_days: int = 14,
        at_risk_days: int = 7,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/queues/presets/{preset}",
            params={
                "project_id": project_id,
                "limit": limit,
                "offset": offset,
                "stale_days": stale_days,
                "at_risk_days": at_risk_days,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_ready_tasks(
        self,
        project_id: str | None = None,
        status: list[str] | None = None,
        exclude_checked_out: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/tasks/ready",
            params={
                "project_id": project_id,
                "status": status,
                "exclude_checked_out": exclude_checked_out,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_stale_tasks(
        self,
        project_id: str | None = None,
        status: list[str] | None = None,
        stale_after_days: int = 14,
        updated_before: str | None = None,
        include_terminal: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/tasks/stale",
            params={
                "project_id": project_id,
                "status": status,
                "stale_after_days": stale_after_days,
                "updated_before": updated_before,
                "include_terminal": include_terminal,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def start_task(
        self, task_id: str, updated_by: str | None = None
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/start",
            json=self._task_action_payload(None, updated_by),
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def complete_task(
        self,
        task_id: str,
        notes: str | None = None,
        updated_by: str | None = None,
        actual_hours: float | None = None,
    ) -> dict[str, Any]:
        payload = self._task_action_payload(None, updated_by) or {}
        if actual_hours is not None:
            payload["actual_hours"] = actual_hours
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/complete",
            params={"notes": notes} if notes else None,
            json=payload or None,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def update_task(
        self,
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        parent_id: str | None = None,
        clear_parent: bool = False,
        priority: str | None = None,
        complexity_points: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if parent_id is not None:
            payload["parent_id"] = parent_id
        if clear_parent:
            payload["clear_parent"] = True
        if priority is not None:
            payload["priority"] = priority
        if complexity_points is not None:
            payload["complexity_points"] = complexity_points

        client = self._get_client()
        response = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json=payload,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def block_task(
        self,
        task_id: str,
        reason: str | None = None,
        updated_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/block",
            json=self._task_action_payload(reason, updated_by),
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def unblock_task(
        self,
        task_id: str,
        updated_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/unblock",
            json=self._task_action_payload(None, updated_by),
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def review_task(
        self,
        task_id: str,
        updated_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/review",
            json=self._task_action_payload(None, updated_by),
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def reopen_task(
        self,
        task_id: str,
        updated_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/reopen",
            json=self._task_action_payload(None, updated_by),
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def cancel_task(
        self,
        task_id: str,
        reason: str | None = None,
        updated_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/cancel",
            json=self._task_action_payload(reason, updated_by),
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def add_task_dependency(
        self,
        task_id: str,
        depends_on_id: str,
        dependency_type: str = "blocks",
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/dependencies",
            json={
                "depends_on_id": depends_on_id,
                "dependency_type": dependency_type,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def remove_task_dependency(
        self, task_id: str, depends_on_id: str
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(
            f"/api/v1/tasks/{task_id}/dependencies/{depends_on_id}"
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_task_dependency_graph(self, task_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/tasks/{task_id}/graph")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_progress_timeline(self, task_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/tasks/{task_id}/progress/timeline")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_workflow_timeline(
        self, entity_type: str, entity_id: str
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/transitions/workflow/{entity_type}/{entity_id}"
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_status_timeline(
        self, entity_type: str, entity_id: str
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/transitions/status/{entity_type}/{entity_id}"
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_workflows(self) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get("/api/v1/workflows")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_workflow(
        self, workflow_ref: str, view: str | None = None
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/workflows/{workflow_ref}",
            params={"view": view} if view else None,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def assign_workflow(
        self, task_id: str, workflow_name: str, initial_state: str
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/workflow/assign",
            json={
                "workflow_name": workflow_name,
                "initial_state": initial_state,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def transition_task_workflow(
        self,
        task_id: str,
        to_state: str,
        triggered_by: str,
        reason: str | None = None,
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/workflow/transition",
            json={
                "to_state": to_state,
                "triggered_by": triggered_by,
                "reason": reason,
                "approved_by": approved_by,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def align_workflow(
        self,
        entity_id: str | None,
        entity_type: str,
        triggered_by: str,
        to_state: str | None = None,
        reason: str | None = None,
        approved_by: str | None = None,
        auto: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/workflow/align",
            json={
                "entity_id": entity_id,
                "entity_type": entity_type,
                "to_state": to_state,
                "triggered_by": triggered_by,
                "reason": reason,
                "approved_by": approved_by,
                "auto": auto,
                "dry_run": dry_run,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def align_task_workflow(
        self,
        task_id: str,
        triggered_by: str,
        to_state: str | None = None,
        reason: str | None = None,
        approved_by: str | None = None,
        auto: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/tasks/{task_id}/workflow/align",
            json={
                "triggered_by": triggered_by,
                "to_state": to_state,
                "reason": reason,
                "approved_by": approved_by,
                "auto": auto,
                "dry_run": dry_run,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_agent_loops(
        self,
        project_id: str | None = None,
        include_ended: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        params: dict[str, Any] = {
            "include_ended": include_ended,
            "limit": limit,
            "offset": offset,
        }
        if project_id:
            params["project_id"] = project_id
        response = await client.get("/api/v1/agent-loops", params=params)
        response.raise_for_status()
        return self._json_dict(response)

    async def get_agent_loop(self, loop_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/agent-loops/{loop_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_agent_loop_messages(
        self, loop_id: str, limit: int | None = None, offset: int = 0
    ) -> dict[str, Any]:
        client = self._get_client()
        params: dict[str, Any] = {"offset": offset}
        if limit is not None:
            params["limit"] = limit
        response = await client.get(
            f"/api/v1/agent-loops/{loop_id}/messages",
            params=params,
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def cancel_agent_loop(self, loop_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/agent-loops/{loop_id}/cancel")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_available_scopes(self) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get("/api/v1/auth/scopes")
        response.raise_for_status()
        return self._json_dict(response)

    async def get_discoverability_graph(
        self,
        include_entry_points: bool = True,
        include_observability: bool = True,
        include_scenarios: bool = True,
        max_next_steps: int = 8,
        path_contains: str | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/discoverability/graph",
            params={
                "include_entry_points": include_entry_points,
                "include_observability": include_observability,
                "include_scenarios": include_scenarios,
                "max_next_steps": max_next_steps,
                "path_contains": path_contains,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_observability_overview(
        self,
        include_rollups: bool = True,
        include_queues: bool = True,
        include_lineage: bool = True,
        include_retention: bool = True,
        include_event_timeline: bool = True,
        queue_limit: int = 5,
        lineage_limit: int = 20,
        retention_limit: int = 10,
        timeline_days: int = 14,
    ) -> JsonObject:
        client = self._get_client()
        response = await client.get(
            "/api/v1/observability/overview",
            params={
                "include_rollups": include_rollups,
                "include_queues": include_queues,
                "include_lineage": include_lineage,
                "include_retention": include_retention,
                "include_event_timeline": include_event_timeline,
                "queue_limit": queue_limit,
                "lineage_limit": lineage_limit,
                "retention_limit": retention_limit,
                "timeline_days": timeline_days,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_project_operator_overview(
        self,
        project_id: str,
        task_limit: int = 5,
        test_limit: int = 5,
        queue_limit: int = 3,
        lineage_limit: int = 3,
        history_limit: int = 5,
        include_timeline: bool = True,
        include_history: bool = False,
        include_linked_history: bool = False,
        view: str = "overview",
    ) -> JsonObject:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/projects/{project_id}/operator-overview",
            params={
                "task_limit": task_limit,
                "test_limit": test_limit,
                "queue_limit": queue_limit,
                "lineage_limit": lineage_limit,
                "history_limit": history_limit,
                "include_timeline": include_timeline,
                "include_history": include_history,
                "include_linked_history": include_linked_history,
                "view": view,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def init_admin_key(self, name: str = "Admin Key") -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/auth/init",
            json={"name": name},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def create_api_key(
        self,
        name: str,
        scopes: list[str],
        expires_in_days: int | None = None,
        rate_limit: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/auth/keys",
            json={
                "name": name,
                "scopes": scopes,
                "expires_in_days": expires_in_days,
                "rate_limit": rate_limit,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_api_keys(
        self, include_inactive: bool = False, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/auth/keys",
            params={
                "include_inactive": include_inactive,
                "include_archived": include_archived,
            },
        )
        response.raise_for_status()
        return self._json_list(response)

    async def get_api_key(self, key_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/auth/keys/{key_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def deactivate_api_key(self, key_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/auth/keys/{key_id}/deactivate")
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_api_key(self, key_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/auth/keys/{key_id}/restore")
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_api_key(self, key_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/auth/keys/{key_id}")
        response.raise_for_status()
        return {"status": "deleted", "key_id": key_id}

    async def create_custom_field(
        self,
        name: str,
        entity_type: str,
        field_type: str,
        description: str | None = None,
        options: list[str] | None = None,
        is_required: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/custom-fields",
            json={
                "name": name,
                "entity_type": entity_type,
                "field_type": field_type,
                "description": description,
                "options": options or [],
                "is_required": is_required,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_custom_fields(
        self,
        entity_type: str | None = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/custom-fields",
            params={
                "entity_type": entity_type,
                "include_archived": include_archived,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_custom_field(self, field_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/custom-fields/{field_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_custom_field(
        self,
        field_id: str,
        name: str | None = None,
        field_type: str | None = None,
        description: str | None = None,
        options: list[str] | None = None,
        is_required: bool | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if field_type is not None:
            payload["field_type"] = field_type
        if description is not None:
            payload["description"] = description
        if options is not None:
            payload["options"] = options
        if is_required is not None:
            payload["is_required"] = is_required
        response = await client.patch(f"/api/v1/custom-fields/{field_id}", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_custom_field(self, field_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/custom-fields/{field_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_custom_field(self, field_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/custom-fields/{field_id}/restore")
        response.raise_for_status()
        return self._json_dict(response)

    async def set_custom_field_value(
        self,
        field_id: str,
        entity_type: str,
        entity_id: str,
        value: Any,
        created_by: str | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            f"/api/v1/custom-fields/{field_id}/values",
            json={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "value": value,
                "created_by": created_by,
                "source": source,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_custom_field_values(
        self,
        entity_type: str,
        entity_id: str,
        include_history: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/custom-fields/values",
            params={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "include_history": include_history,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_custom_field_values_for_field(
        self,
        field_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/custom-fields/{field_id}/values",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def add_comment(
        self,
        entity_type: str,
        entity_id: str,
        body: str,
        created_by: str,
        mentions: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        watch: bool = False,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/comments",
            json={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "body": body,
                "created_by": created_by,
                "mentions": mentions or [],
                "metadata": metadata or {},
                "watch": watch,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_comments(
        self,
        entity_type: str,
        entity_id: str,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/comments",
            params={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_comment(self, comment_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/comments/{comment_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_comment(self, comment_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/comments/{comment_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_comment(self, comment_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/comments/{comment_id}/restore")
        response.raise_for_status()
        return self._json_dict(response)

    async def add_watcher(
        self,
        entity_type: str,
        entity_id: str,
        watcher: str,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(
            "/api/v1/watchers",
            json={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "watcher": watcher,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def list_watchers(
        self,
        entity_type: str,
        entity_id: str,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            "/api/v1/watchers",
            params={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "include_archived": include_archived,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def remove_watcher(
        self,
        entity_type: str,
        entity_id: str,
        watcher: str,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(
            "/api/v1/watchers",
            params={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "watcher": watcher,
            },
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_watcher(self, watcher_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/watchers/{watcher_id}/restore")
        response.raise_for_status()
        return self._json_dict(response)

    async def create_automation_rule(
        self,
        name: str,
        event_pattern: str,
        action_type: str | AutomationActionType,
        action_payload: dict[str, Any],
        *,
        description: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        enabled: bool = True,
        cooldown_seconds: float = 0.0,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "event_pattern": event_pattern,
            "action_type": (
                action_type.value
                if isinstance(action_type, AutomationActionType)
                else action_type
            ),
            "action_payload": action_payload,
            "description": description,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "enabled": enabled,
            "cooldown_seconds": cooldown_seconds,
        }
        client = self._get_client()
        response = await client.post("/api/v1/automation/rules", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def list_automation_rules(
        self,
        *,
        include_archived: bool = False,
        enabled: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        params = {
            "include_archived": include_archived,
            "limit": limit,
            "offset": offset,
        }
        if enabled is not None:
            params["enabled"] = enabled
        client = self._get_client()
        response = await client.get("/api/v1/automation/rules", params=params)
        response.raise_for_status()
        return self._json_dict(response)

    async def get_automation_rule(self, rule_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(f"/api/v1/automation/rules/{rule_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def update_automation_rule(
        self, rule_id: str, **updates: Any
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.patch(
            f"/api/v1/automation/rules/{rule_id}", json=updates
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def delete_automation_rule(self, rule_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.delete(f"/api/v1/automation/rules/{rule_id}")
        response.raise_for_status()
        return self._json_dict(response)

    async def restore_automation_rule(self, rule_id: str) -> dict[str, Any]:
        client = self._get_client()
        response = await client.post(f"/api/v1/automation/rules/{rule_id}/restore")
        response.raise_for_status()
        return self._json_dict(response)

    async def run_automation_rules(
        self,
        event_id: str,
        *,
        rule_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        payload = {"event_id": event_id, "dry_run": dry_run, "rule_id": rule_id}
        client = self._get_client()
        response = await client.post("/api/v1/automation/run", json=payload)
        response.raise_for_status()
        return self._json_dict(response)

    async def list_automation_rule_runs(
        self,
        rule_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get(
            f"/api/v1/automation/rules/{rule_id}/runs",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return self._json_dict(response)

    async def get_dashboard_html(self) -> str:
        client = self._get_client()
        response = await client.get("/dashboard")
        response.raise_for_status()
        return response.text

    async def health_check(self) -> dict[str, Any]:
        client = self._get_client()
        response = await client.get("/api/v1/health")
        response.raise_for_status()
        return self._json_dict(response)
