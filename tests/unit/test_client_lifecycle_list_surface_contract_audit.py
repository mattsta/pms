"""Unit coverage for the maintained client lifecycle-list surface audit."""

from pathlib import Path

from scripts.audit_client_lifecycle_list_surface_contracts import (
    CLIENT_LIFECYCLE_LIST_SURFACE_CONTRACTS,
    audit_source,
    run_audit,
)


def test_audit_source_accepts_consistent_python_lifecycle_list_contract() -> None:
    issues = audit_source(
        """
class PMSClient:
    async def list_tasks(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        response = await client.get(
            "/api/v1/tasks",
            params={
                "project_id": project_id,
                "status": status,
                "limit": limit,
                "offset": offset,
            },
        )

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
""",
        path=Path("pms/client/http_client.py"),
        block_contracts=CLIENT_LIFECYCLE_LIST_SURFACE_CONTRACTS[
            "pms/client/http_client.py"
        ],
    )

    assert issues == ()


def test_audit_source_flags_missing_rust_plan_task_filter_contract() -> None:
    issues = audit_source(
        """
pub(crate) fn plan_list_query_params(
    status: Option<&str>,
    project_id: Option<&str>,
    product_id: Option<&str>,
    goal_id: Option<&str>,
    objective_id: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Vec<(&'static str, String)> {
    let mut params = Vec::new();
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    params
}

pub async fn list_plans(
    &self,
    status: Option<&str>,
    project_id: Option<&str>,
    product_id: Option<&str>,
    goal_id: Option<&str>,
    objective_id: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Result<Value> {
    let params = plan_list_query_params(
        status,
        project_id,
        product_id,
        goal_id,
        objective_id,
        limit,
        offset,
    );
    Ok(resp.json().await?)
}
""",
        path=Path("client-rust/src/client.rs"),
        block_contracts=CLIENT_LIFECYCLE_LIST_SURFACE_CONTRACTS[
            "client-rust/src/client.rs"
        ],
    )

    assert any("task_id: Option<&str>" in issue.reason for issue in issues)
    assert any('("task_id", value.to_string())' in issue.reason for issue in issues)


def test_audit_source_scopes_required_snippets_to_the_right_rust_block() -> None:
    issues = audit_source(
        """
pub(crate) fn unrelated_query_params(status: Option<&str>) -> Vec<(&'static str, String)> {
    let mut params = Vec::new();
    if let Some(status) = status {
        params.push(("status", status.to_string()));
    }
    params
}

pub(crate) fn task_list_query_params(
    project_id: Option<&str>,
    status: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Vec<(&'static str, String)> {
    let mut params = Vec::new();
    if let Some(value) = project_id {
        params.push(("project_id", value.to_string()));
    }
    params
}

pub async fn list_tasks(
    &self,
    project_id: Option<&str>,
    status: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Result<TaskList> {
    let params = task_list_query_params(project_id, status, limit, offset);
    let resp = self
        .client
        .get(format!("{}/api/v1/tasks", self.base_url))
        .headers(self.headers())
        .query(&params)
        .send()
        .await?;
    Ok(resp.json().await?)
}
""",
        path=Path("client-rust/src/client.rs"),
        block_contracts=(
            CLIENT_LIFECYCLE_LIST_SURFACE_CONTRACTS["client-rust/src/client.rs"][0],
            CLIENT_LIFECYCLE_LIST_SURFACE_CONTRACTS["client-rust/src/client.rs"][1],
        ),
    )

    assert any(
        'params.push(("status", value.to_string()));' in issue.reason
        for issue in issues
    )
    assert any(
        'params.push(("limit", value.to_string()));' in issue.reason for issue in issues
    )
    assert any(
        'params.push(("offset", value.to_string()));' in issue.reason
        for issue in issues
    )


def test_run_audit_accepts_consistent_client_tree(tmp_path: Path) -> None:
    python_path = tmp_path / "pms" / "client"
    python_path.mkdir(parents=True)
    (python_path / "http_client.py").write_text(
        """
from typing import Any

class PMSClient:
    async def list_tasks(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        response = await client.get(
            "/api/v1/tasks",
            params={
                "project_id": project_id,
                "status": status,
                "limit": limit,
                "offset": offset,
            },
        )

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
""",
        encoding="utf-8",
    )

    rust_src = tmp_path / "client-rust" / "src"
    rust_src.mkdir(parents=True)
    (rust_src / "client.rs").write_text(
        """
pub(crate) fn task_list_query_params(
    project_id: Option<&str>,
    status: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Vec<(&'static str, String)> {
    let mut params = Vec::new();
    if let Some(value) = project_id {
        params.push(("project_id", value.to_string()));
    }
    if let Some(value) = status {
        params.push(("status", value.to_string()));
    }
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = offset {
        params.push(("offset", value.to_string()));
    }
    params
}

pub async fn list_tasks(
    &self,
    project_id: Option<&str>,
    status: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Result<TaskList> {
    let params = task_list_query_params(project_id, status, limit, offset);
    let resp = self
        .client
        .get(format!("{}/api/v1/tasks", self.base_url))
        .headers(self.headers())
        .query(&params)
        .send()
        .await?;
    Ok(resp.json().await?)
}

pub(crate) fn plan_list_query_params(
    status: Option<&str>,
    project_id: Option<&str>,
    product_id: Option<&str>,
    goal_id: Option<&str>,
    objective_id: Option<&str>,
    task_id: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Vec<(&'static str, String)> {
    let mut params = Vec::new();
    if let Some(value) = task_id {
        params.push(("task_id", value.to_string()));
    }
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = offset {
        params.push(("offset", value.to_string()));
    }
    params
}

pub async fn list_plans(
    &self,
    status: Option<&str>,
    project_id: Option<&str>,
    product_id: Option<&str>,
    goal_id: Option<&str>,
    objective_id: Option<&str>,
    task_id: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Result<Value> {
    let params = plan_list_query_params(
        status,
        project_id,
        product_id,
        goal_id,
        objective_id,
        task_id,
        limit,
        offset,
    );

    let resp = self
        .client
        .get(format!("{}/api/v1/plans", self.base_url))
        .headers(self.headers())
        .query(&params)
        .send()
        .await?;

    Ok(resp.json().await?)
}
""",
        encoding="utf-8",
    )

    (rust_src / "main.rs").write_text(
        """
enum TaskCommands {
    /// List tasks
    List {
        #[arg(long)]
        status: Option<String>,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    }
}

async fn handle_task(action: TaskCommands) -> Result<()> {
    match action {
        TaskCommands::List {
            project,
            project_id,
            status,
            limit,
            offset,
            format,
        } => {
            handle_task_list(
                server, client, project, project_id, status, limit, offset, &format, api_key,
            )
            .await?;
        }
    }
}

enum PlanCommands {
    /// List plans
    List {
        #[arg(long)]
        task_id: Option<String>,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    }
}

async fn handle_plan(action: PlanCommands) -> Result<()> {
    match action {
        PlanCommands::List {
            status,
            project_id,
            product_id,
            goal_id,
            objective_id,
            task_id,
            format,
            limit,
            offset,
        } => {
            handle_plan_list(
                server,
                client,
                status,
                project_id,
                product_id,
                goal_id,
                objective_id,
                task_id,
                &format,
                Some(limit),
                Some(offset),
                api_key,
            )
            .await
        }
    }
}
""",
        encoding="utf-8",
    )

    assert run_audit(tmp_path) == ()
