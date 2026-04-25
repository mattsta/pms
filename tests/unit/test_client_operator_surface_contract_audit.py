"""Unit coverage for the maintained client operator-surface audit."""

from pathlib import Path

from scripts.audit_client_operator_surface_contracts import (
    CLIENT_OPERATOR_SURFACE_CONTRACTS,
    audit_source,
    run_audit,
)


def test_audit_source_accepts_consistent_python_contract() -> None:
    issues = audit_source(
        """
async def get_dashboard(self) -> dict[str, Any]:
    response = await client.get("/api/v1/dashboard")

async def get_dashboard_html(self) -> str:
    response = await client.get("/dashboard")

async def get_organization_dashboard(self):
    response = await client.get("/api/v1/organizations/dashboard", params={})

async def get_portfolio_dashboard(self):
    response = await client.get("/api/v1/portfolios/dashboard", params={})

async def get_program_dashboard(self):
    response = await client.get("/api/v1/programs/dashboard", params={})
""",
        path=Path("pms/client/http_client.py"),
        required_patterns=CLIENT_OPERATOR_SURFACE_CONTRACTS[
            "pms/client/http_client.py"
        ]["required"],
        forbidden_patterns=CLIENT_OPERATOR_SURFACE_CONTRACTS[
            "pms/client/http_client.py"
        ]["forbidden"],
    )

    assert issues == ()


def test_audit_source_flags_rust_dashboard_signature_regression() -> None:
    issues = audit_source(
        """
pub async fn get_dashboard(&self) -> Result<String> {
    let resp = self
        .client
        .get(format!("{}/dashboard", self.base_url))
        .headers(self.headers())
        .send()
        .await?;
    Ok(resp.text().await?)
}
""",
        path=Path("client-rust/src/client.rs"),
        required_patterns=CLIENT_OPERATOR_SURFACE_CONTRACTS[
            "client-rust/src/client.rs"
        ]["required"],
        forbidden_patterns=CLIENT_OPERATOR_SURFACE_CONTRACTS[
            "client-rust/src/client.rs"
        ]["forbidden"],
    )

    assert any(
        "forbidden client contract snippet present" in issue.reason for issue in issues
    )
    assert any("/api/v1/dashboard" in issue.reason for issue in issues)


def test_run_audit_accepts_consistent_client_tree(tmp_path: Path) -> None:
    python_path = tmp_path / "pms" / "client"
    python_path.mkdir(parents=True)
    (python_path / "http_client.py").write_text(
        """
from typing import Any

async def get_dashboard(self) -> dict[str, Any]:
    response = await client.get("/api/v1/dashboard")

async def get_dashboard_html(self) -> str:
    response = await client.get("/dashboard")

async def get_organization_dashboard(self):
    response = await client.get("/api/v1/organizations/dashboard", params={})

async def get_portfolio_dashboard(self):
    response = await client.get("/api/v1/portfolios/dashboard", params={})

async def get_program_dashboard(self):
    response = await client.get("/api/v1/programs/dashboard", params={})
""",
        encoding="utf-8",
    )

    rust_path = tmp_path / "client-rust" / "src"
    rust_path.mkdir(parents=True)
    (rust_path / "client.rs").write_text(
        """
use anyhow::Result;
use serde_json::Value;

pub async fn get_organization_dashboard(
    &self,
    status: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Result<Value> {
    let resp = self
        .client
        .get(format!(
            "{}/api/v1/organizations/dashboard{}",
            self.base_url, query
        ))
        .headers(self.headers())
        .send()
        .await?;
    Ok(resp.json().await?)
}

pub async fn get_portfolio_dashboard(
    &self,
    status: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Result<Value> {
    let resp = self
        .client
        .get(format!(
            "{}/api/v1/portfolios/dashboard{}",
            self.base_url, query
        ))
        .headers(self.headers())
        .send()
        .await?;
    Ok(resp.json().await?)
}

pub async fn get_program_dashboard(
    &self,
    status: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Result<Value> {
    let resp = self
        .client
        .get(format!(
            "{}/api/v1/programs/dashboard{}",
            self.base_url, query
        ))
        .headers(self.headers())
        .send()
        .await?;
    Ok(resp.json().await?)
}

pub async fn get_dashboard(&self) -> Result<Value> {
    let resp = self
        .client
        .get(format!("{}/api/v1/dashboard", self.base_url))
        .headers(self.headers())
        .send()
        .await?;
    Ok(resp.json().await?)
}

pub async fn get_dashboard_html(&self) -> Result<String> {
    let resp = self
        .client
        .get(format!("{}/dashboard", self.base_url))
        .headers(self.headers())
        .send()
        .await?;
    Ok(resp.text().await?)
}
""",
        encoding="utf-8",
    )

    assert run_audit(tmp_path) == ()
