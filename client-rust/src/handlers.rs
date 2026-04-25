// Handler implementations for all commands

use anyhow::{bail, Result};
use chrono::Utc;
use serde_json;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::{env, fs};
use tokio::process::Command;

use crate::client::{
    plan_list_query_params, task_list_query_params, CreateEvidenceGateRuleRequest,
    CreatePlanRequest, CreateQueueRequest, DuplicateMergePreviewRequest, DuplicateMergeRequest,
    PlanTestJobCreateRequest, PlanTestJobUpdateRequest, UpdatePlanRequest, UpdateQueueRequest,
    WorkSnapshotReviewRequest,
};

fn python_cli_command() -> Command {
    let mut cmd = Command::new("uv");
    cmd.arg("run").arg("pms");
    cmd
}

pub fn cli_command_prefix(server: &str) -> String {
    for key in ["PMS_INVOKE_ARGV0", "PMS_CLI_ARGV0", "PMS_ARGV0"] {
        if let Ok(value) = env::var(key) {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }
    }
    current_rust_cli_prefix(server)
}

pub fn current_rust_cli_prefix(server: &str) -> String {
    format!(
        "{} --server {}",
        env::args()
            .next()
            .unwrap_or_else(|| "pms-client".to_string()),
        server
    )
}

pub fn cli_command(server: &str, command: &str) -> String {
    let candidate = command.trim();
    if candidate.is_empty() {
        return cli_command_prefix(server);
    }
    format!("{} {}", cli_command_prefix(server), candidate)
}

fn resolve_actor(actor: &str) -> Result<String> {
    if actor != "me" {
        return Ok(actor.to_string());
    }
    if let Ok(value) = env::var("PMS_CURRENT_ACTOR_ID") {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            return Ok(trimmed.to_string());
        }
    }
    bail!("Actor reference 'me' requires PMS_CURRENT_ACTOR_ID to be configured");
}

pub async fn fetch_task_detail(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    api_key: Option<&str>,
) -> Result<serde_json::Value> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/tasks/{}", server, task_id)),
        api_key,
    )
    .send()
    .await?;
    if !resp.status().is_success() {
        return Err(response_error(resp, "Failed to fetch task detail").await);
    }
    Ok(resp.json().await?)
}

pub fn task_mutation_links(
    server: &str,
    task_id: &str,
    include_progress: bool,
) -> serde_json::Value {
    let mut links = serde_json::Map::new();
    links.insert(
        "self".to_string(),
        serde_json::Value::String(cli_command(server, &format!("task show {}", task_id))),
    );
    links.insert(
        "timeline".to_string(),
        serde_json::Value::String(cli_command(server, &format!("task timeline {}", task_id))),
    );
    links.insert(
        "evidence".to_string(),
        serde_json::Value::String(cli_command(
            server,
            &format!("task evidence list {}", task_id),
        )),
    );
    if include_progress {
        links.insert(
            "progress".to_string(),
            serde_json::Value::String(cli_command(
                server,
                &format!("task progress {} <percent> <message> --by <id>", task_id),
            )),
        );
    }
    serde_json::Value::Object(links)
}

async fn run_python_cli(mut cmd: Command, failure_message: &str) -> Result<()> {
    let status = cmd.status().await?;
    if !status.success() {
        bail!("{} with status {}", failure_message, status);
    }
    Ok(())
}

/// Helper to add API key header to request if provided
fn add_auth_header(
    builder: reqwest::RequestBuilder,
    api_key: Option<&str>,
) -> reqwest::RequestBuilder {
    if let Some(key) = api_key {
        builder.header("X-API-Key", key)
    } else {
        builder
    }
}

async fn response_error(resp: reqwest::Response, context: &str) -> anyhow::Error {
    let status = resp.status();
    let body = resp.text().await.unwrap_or_default();
    let detail = serde_json::from_str::<serde_json::Value>(&body)
        .ok()
        .and_then(|payload| {
            payload
                .get("detail")
                .and_then(serde_json::Value::as_str)
                .map(str::to_owned)
        })
        .unwrap_or_else(|| body.trim().to_string());
    if detail.is_empty() {
        anyhow::anyhow!("{} ({})", context, status)
    } else {
        anyhow::anyhow!("{} ({}): {}", context, status, detail)
    }
}

fn task_focus_rank(status: &str) -> i32 {
    match status {
        "in_progress" => 0,
        "in_review" => 1,
        "todo" => 2,
        "blocked" => 3,
        "done" => 4,
        "cancelled" => 5,
        _ => 6,
    }
}

fn task_focus_reason(status: &str) -> &'static str {
    match status {
        "in_progress" => "active execution in progress",
        "in_review" => "review-ready work can be closed",
        "todo" => "next ready work to start",
        "blocked" => "blocked execution needs unblocking",
        "done" => "most actionable task already completed",
        "cancelled" => "remaining task is cancelled",
        _ => "best available task focus",
    }
}

pub async fn resolve_project_id(
    server: &str,
    client: &reqwest::Client,
    project_ref: Option<&str>,
    project_id: Option<&str>,
    api_key: Option<&str>,
) -> Result<Option<String>> {
    if project_ref.is_some() && project_id.is_some() {
        bail!("Use --project or --project-id, not both");
    }
    if let Some(value) = project_id {
        return Ok(Some(value.to_string()));
    }
    let Some(reference) = project_ref else {
        return Ok(None);
    };

    let by_id = add_auth_header(
        client.get(format!("{}/api/v1/projects/{}", server, reference)),
        api_key,
    )
    .send()
    .await?;
    if by_id.status().is_success() {
        let payload: serde_json::Value = by_id.json().await?;
        if let Some(value) = payload["id"].as_str() {
            return Ok(Some(value.to_string()));
        }
    }

    let list_resp = add_auth_header(
        client.get(format!("{}/api/v1/projects?limit=500", server)),
        api_key,
    )
    .send()
    .await?;
    if !list_resp.status().is_success() {
        return Err(response_error(list_resp, "Failed to resolve project").await);
    }
    let payload: serde_json::Value = list_resp.json().await?;
    let Some(items) = payload["items"].as_array() else {
        bail!("Failed to resolve project: response missing items array");
    };
    let matches: Vec<&serde_json::Value> = items
        .iter()
        .filter(|item| item["name"].as_str() == Some(reference))
        .collect();
    if matches.is_empty() {
        bail!("Project '{}' not found", reference);
    }
    if matches.len() > 1 {
        bail!(
            "Multiple projects named '{}' found; use --project-id",
            reference
        );
    }
    let Some(value) = matches[0]["id"].as_str() else {
        bail!("Resolved project '{}' is missing id", reference);
    };
    Ok(Some(value.to_string()))
}

pub async fn handle_project_list(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/projects{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"].as_array().unwrap();
    println!("Projects ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap(),
            item["id"].as_str().unwrap()
        );
    }
    Ok(())
}

pub async fn handle_actor_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/actors", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    if !resp.status().is_success() {
        return Err(response_error(resp, "Failed to create actor").await);
    }
    let actor: serde_json::Value = resp.json().await?;
    if output_format == "json" {
        println!("{}", serde_json::to_string_pretty(&actor)?);
        return Ok(());
    }
    println!("✓ Created actor: {}", actor["name"].as_str().unwrap_or("-"));
    println!("  Handle: {}", actor["handle"].as_str().unwrap_or("-"));
    println!("  ID: {}", actor["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_actor_list(
    server: &str,
    client: &reqwest::Client,
    kind: Option<String>,
    status: Option<String>,
    limit: u32,
    offset: u32,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![("limit", limit.to_string()), ("offset", offset.to_string())];
    if let Some(kind) = kind {
        params.push(("kind", kind));
    }
    if let Some(status) = status {
        params.push(("status", status));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/actors", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    if !resp.status().is_success() {
        return Err(response_error(resp, "Failed to list actors").await);
    }
    let result: serde_json::Value = resp.json().await?;
    if output_format == "json" {
        println!("{}", serde_json::to_string_pretty(&result)?);
        return Ok(());
    }
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Actors ({}):", items.len());
    for item in items {
        println!(
            "  • {} [{}] - {}",
            item["name"].as_str().unwrap_or("-"),
            item["kind"].as_str().unwrap_or("-"),
            item["handle"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_actor_show(
    server: &str,
    client: &reqwest::Client,
    actor: &str,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resolved_actor = resolve_actor(actor)?;
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/actors/{}", server, resolved_actor))
            .query(&[("include_inherited", "true"), ("task_limit", "25")]),
        api_key,
    )
    .send()
    .await?;
    if !resp.status().is_success() {
        return Err(response_error(resp, "Failed to fetch actor").await);
    }
    let payload: serde_json::Value = resp.json().await?;
    if output_format == "json" {
        println!("{}", serde_json::to_string_pretty(&payload)?);
        return Ok(());
    }
    let actor = &payload["actor"];
    println!("Actor: {}", actor["name"].as_str().unwrap_or("-"));
    println!("  Handle: {}", actor["handle"].as_str().unwrap_or("-"));
    println!("  Kind: {}", actor["kind"].as_str().unwrap_or("-"));
    println!("  Status: {}", actor["status"].as_str().unwrap_or("-"));
    println!(
        "  Assigned tasks: {}",
        payload["workload"]["assigned_tasks"].as_u64().unwrap_or(0)
    );
    println!(
        "  Owned items: {}",
        payload["ownership"]["counts"]["total_owned"]
            .as_u64()
            .unwrap_or(0)
    );
    Ok(())
}

pub async fn handle_actor_alias_add(
    server: &str,
    client: &reqwest::Client,
    actor: &str,
    alias_value: &str,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resolved_actor = resolve_actor(actor)?;
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/actors/{}/aliases",
                server, resolved_actor
            ))
            .json(&serde_json::json!({ "alias": alias_value })),
        api_key,
    )
    .send()
    .await?;
    if !resp.status().is_success() {
        return Err(response_error(resp, "Failed to add actor alias").await);
    }
    let payload: serde_json::Value = resp.json().await?;
    if output_format == "json" {
        println!("{}", serde_json::to_string_pretty(&payload)?);
        return Ok(());
    }
    println!(
        "✓ Added alias: {}",
        payload["alias"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_actor_membership_add(
    server: &str,
    client: &reqwest::Client,
    parent: &str,
    member: &str,
    role: &str,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resolved_parent = resolve_actor(parent)?;
    let resolved_member = resolve_actor(member)?;
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/actors/{}/memberships",
                server, resolved_parent
            ))
            .json(&serde_json::json!({
                "member": resolved_member,
                "role": role,
            })),
        api_key,
    )
    .send()
    .await?;
    if !resp.status().is_success() {
        return Err(response_error(resp, "Failed to add actor membership").await);
    }
    let payload: serde_json::Value = resp.json().await?;
    if output_format == "json" {
        println!("{}", serde_json::to_string_pretty(&payload)?);
        return Ok(());
    }
    println!(
        "✓ Added membership: {} -> {} ({})",
        member,
        parent,
        payload["role"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_project_get(
    server: &str,
    client: &reqwest::Client,
    project_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/projects/{}", server, project_id)),
        api_key,
    )
    .send()
    .await?;
    let project: serde_json::Value = resp.json().await?;
    println!("Project: {}", project["name"].as_str().unwrap());
    println!("  ID: {}", project["id"].as_str().unwrap());
    println!("  Status: {}", project["status"].as_str().unwrap());
    Ok(())
}

pub async fn handle_project_create_full(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/projects", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let project: serde_json::Value = resp.json().await?;
    println!("✓ Created project: {}", project["name"].as_str().unwrap());
    println!("  ID: {}", project["id"].as_str().unwrap());
    Ok(())
}

pub async fn handle_project_update(
    server: &str,
    client: &reqwest::Client,
    project_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/projects/{}", server, project_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let project: serde_json::Value = resp.json().await?;
    println!("✓ Updated project: {}", project["name"].as_str().unwrap());
    Ok(())
}

pub async fn handle_project_summary(
    server: &str,
    client: &reqwest::Client,
    project_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/projects/{}/summary", server, project_id)),
        api_key,
    )
    .send()
    .await?;
    let summary: serde_json::Value = resp.json().await?;
    println!("Project Summary:");
    println!(
        "  Project: {}",
        summary["project"]["name"].as_str().unwrap_or("-")
    );
    println!(
        "  Health: {}",
        summary["health_score"].as_f64().unwrap_or(0.0)
    );
    Ok(())
}

pub async fn handle_org_list(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/organizations{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Organizations ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_org_get(
    server: &str,
    client: &reqwest::Client,
    org_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/organizations/{}", server, org_id)),
        api_key,
    )
    .send()
    .await?;
    let org: serde_json::Value = resp.json().await?;
    println!("Organization: {}", org["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", org["id"].as_str().unwrap_or("-"));
    println!("  Status: {}", org["status"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_org_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/organizations", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let org: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created organization: {}",
        org["name"].as_str().unwrap_or("-")
    );
    println!("  ID: {}", org["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_org_update(
    server: &str,
    client: &reqwest::Client,
    org_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/organizations/{}", server, org_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let org: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated organization: {}",
        org["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_org_summary(
    server: &str,
    client: &reqwest::Client,
    org_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/organizations/{}/summary",
            server, org_id
        )),
        api_key,
    )
    .send()
    .await?;
    let summary: serde_json::Value = resp.json().await?;
    println!("Organization Summary:");
    println!(
        "  Org: {}",
        summary["organization"]["name"].as_str().unwrap_or("-")
    );
    println!("  Risk: {}", summary["risk_level"].as_str().unwrap_or("-"));
    println!(
        "  Projects: {}",
        summary["stats"]["total_projects"].as_u64().unwrap_or(0)
    );
    Ok(())
}

pub async fn handle_org_dashboard(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/organizations/dashboard{}",
            server, query
        )),
        api_key,
    )
    .send()
    .await?;
    let payload: serde_json::Value = resp.json().await?;
    let total = payload["total_count"].as_u64().unwrap_or(0);
    let items = payload["items"].as_array().map(|v| v.len()).unwrap_or(0);
    println!("Organization Dashboard:");
    println!("  Total: {}", total);
    println!("  Items: {}", items);
    Ok(())
}

pub async fn handle_team_list(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    org_id: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(org_id) = org_id {
        params.push(format!("org_id={}", org_id));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/teams{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Teams ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_team_get(
    server: &str,
    client: &reqwest::Client,
    team_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/teams/{}", server, team_id)),
        api_key,
    )
    .send()
    .await?;
    let team: serde_json::Value = resp.json().await?;
    println!("Team: {}", team["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", team["id"].as_str().unwrap_or("-"));
    println!("  Status: {}", team["status"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_team_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/teams", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let team: serde_json::Value = resp.json().await?;
    println!("✓ Created team: {}", team["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", team["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_team_update(
    server: &str,
    client: &reqwest::Client,
    team_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/teams/{}", server, team_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let team: serde_json::Value = resp.json().await?;
    println!("✓ Updated team: {}", team["name"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_portfolio_list(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    org_id: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(org_id) = org_id {
        params.push(format!("org_id={}", org_id));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/portfolios{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Portfolios ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_portfolio_get(
    server: &str,
    client: &reqwest::Client,
    portfolio_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/portfolios/{}", server, portfolio_id)),
        api_key,
    )
    .send()
    .await?;
    let portfolio: serde_json::Value = resp.json().await?;
    println!("Portfolio: {}", portfolio["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", portfolio["id"].as_str().unwrap_or("-"));
    println!("  Status: {}", portfolio["status"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_portfolio_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/portfolios", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let portfolio: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created portfolio: {}",
        portfolio["name"].as_str().unwrap_or("-")
    );
    println!("  ID: {}", portfolio["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_portfolio_update(
    server: &str,
    client: &reqwest::Client,
    portfolio_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/portfolios/{}", server, portfolio_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let portfolio: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated portfolio: {}",
        portfolio["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_portfolio_summary(
    server: &str,
    client: &reqwest::Client,
    portfolio_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/portfolios/{}/summary",
            server, portfolio_id
        )),
        api_key,
    )
    .send()
    .await?;
    let summary: serde_json::Value = resp.json().await?;
    println!("Portfolio Summary:");
    println!(
        "  Portfolio: {}",
        summary["portfolio"]["name"].as_str().unwrap_or("-")
    );
    println!(
        "  Projects: {}",
        summary["stats"]["total_projects"].as_u64().unwrap_or(0)
    );
    Ok(())
}

pub async fn handle_portfolio_dashboard(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    org_id: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(org_id) = org_id {
        params.push(format!("org_id={}", org_id));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/portfolios/dashboard{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let payload: serde_json::Value = resp.json().await?;
    let total = payload["total_count"].as_u64().unwrap_or(0);
    let items = payload["items"].as_array().map(|v| v.len()).unwrap_or(0);
    println!("Portfolio Dashboard:");
    println!("  Total: {}", total);
    println!("  Items: {}", items);
    Ok(())
}

pub async fn handle_program_list(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    org_id: Option<String>,
    portfolio_id: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(org_id) = org_id {
        params.push(format!("org_id={}", org_id));
    }
    if let Some(portfolio_id) = portfolio_id {
        params.push(format!("portfolio_id={}", portfolio_id));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/programs{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Programs ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_program_get(
    server: &str,
    client: &reqwest::Client,
    program_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/programs/{}", server, program_id)),
        api_key,
    )
    .send()
    .await?;
    let program: serde_json::Value = resp.json().await?;
    println!("Program: {}", program["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", program["id"].as_str().unwrap_or("-"));
    println!("  Status: {}", program["status"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_program_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/programs", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let program: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created program: {}",
        program["name"].as_str().unwrap_or("-")
    );
    println!("  ID: {}", program["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_program_update(
    server: &str,
    client: &reqwest::Client,
    program_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/programs/{}", server, program_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let program: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated program: {}",
        program["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_program_summary(
    server: &str,
    client: &reqwest::Client,
    program_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/programs/{}/summary", server, program_id)),
        api_key,
    )
    .send()
    .await?;
    let summary: serde_json::Value = resp.json().await?;
    println!("Program Summary:");
    println!(
        "  Program: {}",
        summary["program"]["name"].as_str().unwrap_or("-")
    );
    println!(
        "  Projects: {}",
        summary["stats"]["total_projects"].as_u64().unwrap_or(0)
    );
    Ok(())
}

pub async fn handle_program_dashboard(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    org_id: Option<String>,
    portfolio_id: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(org_id) = org_id {
        params.push(format!("org_id={}", org_id));
    }
    if let Some(portfolio_id) = portfolio_id {
        params.push(format!("portfolio_id={}", portfolio_id));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/programs/dashboard{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let payload: serde_json::Value = resp.json().await?;
    let total = payload["total_count"].as_u64().unwrap_or(0);
    let items = payload["items"].as_array().map(|v| v.len()).unwrap_or(0);
    println!("Program Dashboard:");
    println!("  Total: {}", total);
    println!("  Items: {}", items);
    Ok(())
}

pub async fn handle_workflow_list(
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(client.get(format!("{}/api/v1/workflows", server)), api_key)
        .send()
        .await?;
    let result: serde_json::Value = resp.json().await?;
    let workflows = result["workflows"].as_array().unwrap();
    println!("Workflows ({}):", workflows.len());
    for wf in workflows {
        println!(
            "  • {} ({} states)",
            wf["name"].as_str().unwrap(),
            wf["states_count"]
        );
    }
    Ok(())
}

pub async fn handle_workflow_show(
    server: &str,
    client: &reqwest::Client,
    workflow_ref: &str,
    view: Option<String>,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = view {
        params.push(("view", value));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/workflows/{}", server, workflow_ref))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let workflow: serde_json::Value = resp.json().await?;
    if output_format == "json" {
        println!("{}", serde_json::to_string_pretty(&workflow)?);
        return Ok(());
    }
    println!(
        "{} (id: {})",
        workflow["name"].as_str().unwrap_or("-"),
        workflow["id"].as_str().unwrap_or("-")
    );
    println!(
        "States: {}",
        workflow["states"].as_array().map(|v| v.len()).unwrap_or(0)
    );
    Ok(())
}

pub async fn handle_health_check(
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(client.get(format!("{}/api/v1/health", server)), api_key)
        .send()
        .await?;
    let health: serde_json::Value = resp.json().await?;
    println!("Health: {}", health["status"].as_str().unwrap());
    println!("  Backend: {}", health["backend"].as_str().unwrap());
    println!(
        "  Schema: {} ({})",
        health["schema_version"], health["schema_name"]
    );
    Ok(())
}

pub async fn handle_task_list(
    server: &str,
    client: &reqwest::Client,
    project: Option<String>,
    project_id: Option<String>,
    status: Option<String>,
    limit: u32,
    offset: u32,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resolved_project_id = resolve_project_id(
        server,
        client,
        project.as_deref(),
        project_id.as_deref(),
        api_key,
    )
    .await?;
    let params = task_list_query_params(
        resolved_project_id.as_deref(),
        status.as_deref(),
        Some(limit),
        Some(offset),
    );
    let resp = add_auth_header(client.get(format!("{}/api/v1/tasks", server)), api_key)
        .query(&params)
        .send()
        .await?;
    if !resp.status().is_success() {
        return Err(response_error(resp, "Failed to list tasks").await);
    }
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("Failed to list tasks: response missing items array"))?;
    if output_format == "json" {
        let project_name = if let Some(pid) = resolved_project_id.as_ref() {
            let project_resp = add_auth_header(
                client.get(format!("{}/api/v1/projects/{}", server, pid)),
                api_key,
            )
            .send()
            .await?;
            if project_resp.status().is_success() {
                let project: serde_json::Value = project_resp.json().await?;
                project["name"].as_str().map(str::to_owned)
            } else {
                None
            }
        } else {
            None
        };
        let mut project_hint = project_name
            .as_ref()
            .map(|name| format!("task list --project \"{}\"", name))
            .or_else(|| {
                resolved_project_id
                    .as_ref()
                    .map(|pid| format!("task list --project {}", pid))
            })
            .unwrap_or_else(|| "task list".to_string());
        if let Some(status_value) = status.as_ref() {
            project_hint.push_str(&format!(" --status {}", status_value));
        }
        project_hint.push_str(&format!(" --limit {} --offset {}", limit, offset));
        let enriched_items: Vec<serde_json::Value> = items
            .iter()
            .map(|task| {
                let task_id = task["id"].as_str().unwrap_or("");
                let mut enriched = task.clone();
                if let Some(object) = enriched.as_object_mut() {
                    object.insert(
                        "links".to_string(),
                        serde_json::json!({
                            "self": cli_command(server, &format!("task show {}", task_id)),
                            "timeline": cli_command(server, &format!("task timeline {}", task_id)),
                            "graph": cli_command(server, &format!("task graph {}", task_id)),
                            "evidence": cli_command(server, &format!("task evidence list {}", task_id)),
                        }),
                    );
                }
                enriched
            })
            .collect();
        let total_count = result["total_count"].as_u64().unwrap_or(items.len() as u64);
        let limit_value = result["limit"].as_u64().unwrap_or(limit as u64);
        let offset_value = result["offset"].as_u64().unwrap_or(offset as u64);
        let has_more = offset_value + (items.len() as u64) < total_count;
        let links = serde_json::json!({
            "self": cli_command(server, &format!("{} --format json", project_hint)),
            "guide": cli_command(server, "start --format json"),
        });
        let focus_task = items.iter().min_by_key(|task| {
            let status = task["status"].as_str().unwrap_or("");
            let updated_at = task["updated_at"].as_str().unwrap_or("");
            (
                task_focus_rank(status),
                std::cmp::Reverse(updated_at.to_string()),
            )
        });
        let next_steps = if let Some(task) = focus_task {
            let task_id = task["id"].as_str().unwrap_or("<task-id>");
            let task_title = task["title"].as_str().unwrap_or(task_id);
            let status = task["status"].as_str().unwrap_or("");
            let task_ref = if let Some(project_name) = project_name.as_ref() {
                format!("\"{}\" --project \"{}\"", task_title, project_name)
            } else {
                task_id.to_string()
            };
            let mut steps = match status {
                "in_progress" => vec![
                    cli_command(
                        server,
                        &format!("task progress {} <percent> <message> --by <user>", task_ref),
                    ),
                    cli_command(server, &format!("task show {}", task_ref)),
                ],
                "in_review" => vec![
                    cli_command(server, &format!("task complete {} --by <user>", task_ref)),
                    cli_command(server, &format!("task show {}", task_ref)),
                ],
                "todo" => vec![
                    cli_command(server, &format!("task start {} --by <user>", task_ref)),
                    cli_command(server, &format!("task show {}", task_ref)),
                ],
                "blocked" => vec![
                    cli_command(server, &format!("task unblock {} --by <user>", task_ref)),
                    cli_command(server, &format!("task show {}", task_ref)),
                ],
                _ => vec![cli_command(server, &format!("task show {}", task_ref))],
            };
            steps.push(cli_command(server, "start --format json"));
            steps
        } else {
            vec![cli_command(server, "start --format json")]
        };
        let payload = serde_json::json!({
            "generated_at": Utc::now().to_rfc3339(),
            "purpose": "Machine-readable task list for the installed Rust fast path with actionable focus and next steps.",
            "items": enriched_items,
            "total_count": total_count,
            "page": {
                "total_count": total_count,
                "limit": limit_value,
                "offset": offset_value,
                "has_more": has_more,
                "next_offset": if has_more {
                    Some(offset_value + limit_value)
                } else {
                    None::<u64>
                },
            },
            "focus_task": focus_task.map(|task| serde_json::json!({
                "id": task["id"].as_str().unwrap_or(""),
                "title": task["title"].as_str().unwrap_or(""),
                "status": task["status"].as_str().unwrap_or(""),
                "project_id": task["project_id"].as_str(),
                "project_name": project_name,
                "current_progress_percent": task["current_progress_percent"].as_u64(),
                "reason": task_focus_reason(task["status"].as_str().unwrap_or("")),
            })),
            "links": links,
            "next_steps": next_steps,
            "cli": {
                "canonical_prefix": cli_command_prefix(server),
                "alternate_prefix": current_rust_cli_prefix(server),
            },
        });
        println!("{}", serde_json::to_string_pretty(&payload)?);
        return Ok(());
    }
    println!("Tasks ({}):", items.len());
    for task in items {
        let title = task["title"].as_str().unwrap_or("<unknown-title>");
        let status = task["status"].as_str().unwrap_or("<unknown-status>");
        let id = task["id"].as_str().unwrap_or("<unknown-id>");
        println!("  • {} [{}] - {}", title, status, id);
    }
    Ok(())
}

fn task_action_payload(
    reason: Option<String>,
    updated_by: Option<String>,
) -> Option<serde_json::Value> {
    if reason.is_none() && updated_by.is_none() {
        return None;
    }
    Some(serde_json::json!({
        "reason": reason,
        "updated_by": updated_by,
    }))
}

async fn post_task_action(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    action: &str,
    reason: Option<String>,
    updated_by: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let builder = add_auth_header(
        client.post(format!("{}/api/v1/tasks/{}/{}", server, task_id, action)),
        api_key,
    );
    let resp = if let Some(payload) = task_action_payload(reason, updated_by) {
        builder.json(&payload).send().await?
    } else {
        builder.send().await?
    };
    if !resp.status().is_success() {
        return Err(anyhow::anyhow!("Task action failed"));
    }
    Ok(())
}

pub async fn handle_task_start(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    updated_by: Option<String>,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let builder = add_auth_header(
        client.post(format!("{}/api/v1/tasks/{}/start", server, task_id)),
        api_key,
    );
    let resp = if let Some(payload) = task_action_payload(None, updated_by.clone()) {
        builder.json(&payload).send().await?
    } else {
        builder.send().await?
    };
    if !resp.status().is_success() {
        return Err(anyhow::anyhow!("Failed to start task"));
    }
    if output_format == "json" {
        let task = fetch_task_detail(server, client, task_id, api_key).await?;
        let actor_hint = updated_by.as_deref().unwrap_or("<user>");
        let payload = serde_json::json!({
            "task": task,
            "links": task_mutation_links(server, task_id, true),
            "next_steps": vec![
                cli_command(server, &format!("task show {}", task_id)),
                cli_command(server, &format!("task progress {} <percent> <message> --by {}", task_id, actor_hint)),
                cli_command(server, &format!("task review {} --by {}", task_id, actor_hint)),
            ],
            "cli": {
                "canonical_prefix": cli_command_prefix(server),
                "alternate_prefix": current_rust_cli_prefix(server),
            },
        });
        println!("{}", serde_json::to_string_pretty(&payload)?);
    } else {
        println!("✓ Started task {}", task_id);
    }
    Ok(())
}

pub async fn handle_task_complete(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    notes: Option<String>,
    updated_by: Option<String>,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let builder = add_auth_header(
        client.post(format!("{}/api/v1/tasks/{}/complete", server, task_id)),
        api_key,
    );
    let builder = if let Some(value) = notes.as_ref() {
        builder.query(&[("notes", value)])
    } else {
        builder
    };
    let resp = if let Some(payload) = task_action_payload(None, updated_by.clone()) {
        builder.json(&payload).send().await?
    } else {
        builder.send().await?
    };
    if !resp.status().is_success() {
        return Err(anyhow::anyhow!("Failed to complete task"));
    }
    if output_format == "json" {
        let task = fetch_task_detail(server, client, task_id, api_key).await?;
        let actor_hint = updated_by.as_deref().unwrap_or("<user>");
        let payload = serde_json::json!({
            "task": task,
            "completion": {
                "notes": notes,
                "updated_by": updated_by,
            },
            "links": task_mutation_links(server, task_id, false),
            "next_steps": vec![
                cli_command(server, &format!("task show {}", task_id)),
                cli_command(server, &format!("task reopen {} --by {}", task_id, actor_hint)),
                cli_command(server, &format!("task evidence list {}", task_id)),
            ],
            "cli": {
                "canonical_prefix": cli_command_prefix(server),
                "alternate_prefix": current_rust_cli_prefix(server),
            },
        });
        println!("{}", serde_json::to_string_pretty(&payload)?);
    } else {
        println!("✓ Completed task {}", task_id);
    }
    Ok(())
}

pub async fn handle_task_search(
    server: &str,
    client: &reqwest::Client,
    query: Option<String>,
    project_id: Option<String>,
    status: Vec<String>,
    priority: Vec<String>,
    assignee: Option<String>,
    tags: Vec<String>,
    label_id: Vec<String>,
    label_category_id: Vec<String>,
    created_from: Option<String>,
    created_to: Option<String>,
    updated_from: Option<String>,
    updated_to: Option<String>,
    due_from: Option<String>,
    due_to: Option<String>,
    include_terminal: bool,
    sort_by: Option<String>,
    sort_dir: Option<String>,
    limit: u32,
    offset: u32,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = query {
        params.push(("query", value));
    }
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    for value in status {
        params.push(("status", value));
    }
    for value in priority {
        params.push(("priority", value));
    }
    if let Some(value) = assignee {
        params.push(("assignee", value));
    }
    for value in tags {
        params.push(("tags", value));
    }
    for value in label_id {
        params.push(("label_id", value));
    }
    for value in label_category_id {
        params.push(("label_category_id", value));
    }
    if let Some(value) = created_from {
        params.push(("created_from", value));
    }
    if let Some(value) = created_to {
        params.push(("created_to", value));
    }
    if let Some(value) = updated_from {
        params.push(("updated_from", value));
    }
    if let Some(value) = updated_to {
        params.push(("updated_to", value));
    }
    if let Some(value) = due_from {
        params.push(("due_from", value));
    }
    if let Some(value) = due_to {
        params.push(("due_to", value));
    }
    params.push(("include_terminal", include_terminal.to_string()));
    if let Some(value) = sort_by {
        params.push(("sort_by", value));
    }
    if let Some(value) = sort_dir {
        params.push(("sort_dir", value));
    }
    params.push(("limit", limit.to_string()));
    params.push(("offset", offset.to_string()));

    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/search", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let total = result["total_count"].as_u64().unwrap_or(0);
    println!("Search results: {} task(s)", total);
    Ok(())
}

pub async fn handle_task_ready(
    server: &str,
    client: &reqwest::Client,
    project_id: Option<String>,
    status: Vec<String>,
    exclude_checked_out: bool,
    limit: u32,
    offset: u32,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    for value in status {
        params.push(("status", value));
    }
    params.push(("exclude_checked_out", exclude_checked_out.to_string()));
    params.push(("limit", limit.to_string()));
    params.push(("offset", offset.to_string()));

    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/ready", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let total = result["total_count"].as_u64().unwrap_or(0);
    println!("Ready tasks: {}", total);
    Ok(())
}

pub async fn handle_task_stale(
    server: &str,
    client: &reqwest::Client,
    project_id: Option<String>,
    status: Vec<String>,
    stale_after_days: Option<u32>,
    updated_before: Option<String>,
    include_terminal: bool,
    limit: u32,
    offset: u32,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    for value in status {
        params.push(("status", value));
    }
    if let Some(value) = stale_after_days {
        params.push(("stale_after_days", value.to_string()));
    }
    if let Some(value) = updated_before {
        params.push(("updated_before", value));
    }
    params.push(("include_terminal", include_terminal.to_string()));
    params.push(("limit", limit.to_string()));
    params.push(("offset", offset.to_string()));

    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/stale", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let total = result["total_count"].as_u64().unwrap_or(0);
    println!("Stale tasks: {}", total);
    Ok(())
}

pub async fn handle_task_duplicates(
    server: &str,
    client: &reqwest::Client,
    project_id: Option<String>,
    status: Vec<String>,
    include_terminal: bool,
    min_count: Option<u32>,
    limit: u32,
    offset: u32,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    for value in status {
        params.push(("status", value));
    }
    params.push(("include_terminal", include_terminal.to_string()));
    if let Some(value) = min_count {
        params.push(("min_count", value.to_string()));
    }
    params.push(("limit", limit.to_string()));
    params.push(("offset", offset.to_string()));

    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/duplicates", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let total = result["total_count"].as_u64().unwrap_or(0);
    println!("Duplicate groups: {}", total);
    Ok(())
}

pub async fn handle_task_duplicates_preview(
    server: &str,
    client: &reqwest::Client,
    req: DuplicateMergePreviewRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/tasks/duplicates/preview", server))
            .json(&req),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let can_merge = result["can_merge"].as_bool().unwrap_or(false);
    println!("Merge preview: can_merge={}", can_merge);
    Ok(())
}

pub async fn handle_task_duplicates_merge(
    server: &str,
    client: &reqwest::Client,
    req: DuplicateMergeRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/tasks/duplicates/merge", server))
            .json(&req),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "Merged duplicates: links_added={}",
        result["links_added"].as_u64().unwrap_or(0)
    );
    Ok(())
}

pub async fn handle_task_evidence_add(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    evidence_type: &str,
    reference: &str,
    description: Option<String>,
    metadata: Option<serde_json::Value>,
    created_by: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let payload = serde_json::json!({
        "evidence_type": evidence_type,
        "reference": reference,
        "description": description,
        "metadata": metadata.unwrap_or_else(|| serde_json::json!({})),
        "created_by": created_by,
    });
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/tasks/{}/evidence", server, task_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "✓ Added evidence: {} ({})",
        result["evidence_type"].as_str().unwrap_or("-"),
        result["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_task_evidence(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    include_test_runs: bool,
    include_output: bool,
    limit: u32,
    offset: u32,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/{}/evidence", server, task_id))
            .query(&[
                ("include_test_runs", include_test_runs.to_string()),
                ("include_output", include_output.to_string()),
                ("limit", limit.to_string()),
                ("offset", offset.to_string()),
            ]),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let total = result["total_count"].as_u64().unwrap_or(0);
    println!("Evidence records: {}", total);
    Ok(())
}

pub async fn handle_task_proof_bundle(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    include_output: bool,
    include_logs: bool,
    include_artifacts: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/{}/proof-bundle", server, task_id))
            .query(&[
                ("include_output", include_output.to_string()),
                ("include_logs", include_logs.to_string()),
                ("include_artifacts", include_artifacts.to_string()),
            ]),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let total = result["summary"]["evidence_total"].as_u64().unwrap_or(0);
    println!("Proof bundle: evidence_total={}", total);
    Ok(())
}

pub async fn handle_task_block(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    reason: Option<String>,
    updated_by: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    post_task_action(
        server, client, task_id, "block", reason, updated_by, api_key,
    )
    .await?;
    println!("✓ Blocked task {}", task_id);
    Ok(())
}

pub async fn handle_task_unblock(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    updated_by: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    post_task_action(
        server, client, task_id, "unblock", None, updated_by, api_key,
    )
    .await?;
    println!("✓ Unblocked task {}", task_id);
    Ok(())
}

pub async fn handle_task_review(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    updated_by: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    post_task_action(server, client, task_id, "review", None, updated_by, api_key).await?;
    println!("✓ Sent task {} to review", task_id);
    Ok(())
}

pub async fn handle_task_reopen(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    updated_by: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    post_task_action(server, client, task_id, "reopen", None, updated_by, api_key).await?;
    println!("✓ Reopened task {}", task_id);
    Ok(())
}

pub async fn handle_task_cancel(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    reason: Option<String>,
    updated_by: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    post_task_action(
        server, client, task_id, "cancel", reason, updated_by, api_key,
    )
    .await?;
    println!("✓ Cancelled task {}", task_id);
    Ok(())
}

pub async fn handle_task_dependency_add(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    depends_on_id: &str,
    dependency_type: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let payload = serde_json::json!({
        "depends_on_id": depends_on_id,
        "dependency_type": dependency_type,
    });
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/tasks/{}/dependencies", server, task_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    if !resp.status().is_success() {
        return Err(anyhow::anyhow!("Failed to add dependency"));
    }
    println!("✓ Added dependency: {} -> {}", task_id, depends_on_id);
    Ok(())
}

pub async fn handle_task_dependency_remove(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    depends_on_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.delete(format!(
            "{}/api/v1/tasks/{}/dependencies/{}",
            server, task_id, depends_on_id
        )),
        api_key,
    )
    .send()
    .await?;
    if !resp.status().is_success() {
        return Err(anyhow::anyhow!("Failed to remove dependency"));
    }
    println!("✓ Removed dependency: {} -> {}", task_id, depends_on_id);
    Ok(())
}

pub async fn handle_task_graph(
    server: &str,
    client: &reqwest::Client,
    task_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/tasks/{}/graph", server, task_id)),
        api_key,
    )
    .send()
    .await?;
    let graph: serde_json::Value = resp.json().await?;
    println!("{}", serde_json::to_string_pretty(&graph)?);
    Ok(())
}

fn render_task_tree_node(node: &serde_json::Value, indent: usize, lines: &mut Vec<String>) {
    let task = &node["task"];
    let title = task["title"].as_str().unwrap_or("-");
    let id = task["id"].as_str().unwrap_or("-");
    let prefix = "  ".repeat(indent);
    lines.push(format!("{prefix}- {title} ({id})"));

    if let Some(children) = node["children"].as_array() {
        for child in children {
            render_task_tree_node(child, indent + 1, lines);
        }
    }
}

pub async fn handle_task_tree(
    server: &str,
    client: &reqwest::Client,
    project_id: String,
    root_task_id: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = vec![("project_id", project_id)];
    if let Some(value) = root_task_id {
        params.push(("root_task_id", value));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/tree", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let tree: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let nodes = tree["nodes"].as_array().unwrap_or(&empty);
    if nodes.is_empty() {
        println!("No tasks found.");
        return Ok(());
    }
    let mut lines = Vec::new();
    for node in nodes {
        render_task_tree_node(node, 0, &mut lines);
    }
    println!("{}", lines.join("\n"));
    Ok(())
}

pub async fn handle_task_blocked(
    server: &str,
    client: &reqwest::Client,
    project_id: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = vec![("status", "blocked".to_string())];
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/search", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"].as_array().map(Vec::as_slice).unwrap_or(&[]);
    println!("Blocked tasks ({}):", items.len());
    for task in items {
        println!(
            "  • {} [{}] - {}",
            task["title"].as_str().unwrap_or("-"),
            task["status"].as_str().unwrap_or("-"),
            task["id"].as_str().unwrap_or("-"),
        );
    }
    Ok(())
}

pub async fn handle_task_resolve(
    server: &str,
    client: &reqwest::Client,
    task_ref: &str,
    project_ref: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let direct_resp = add_auth_header(
        client.get(format!("{}/api/v1/tasks/{}", server, task_ref)),
        api_key,
    )
    .send()
    .await?;
    if direct_resp.status().is_success() {
        let task: serde_json::Value = direct_resp.json().await?;
        println!("Task: {}", task["title"].as_str().unwrap_or("-"));
        println!("ID: {}", task["id"].as_str().unwrap_or("-"));
        println!("Project: {}", task["project_id"].as_str().unwrap_or("-"));
        println!("Status: {}", task["status"].as_str().unwrap_or("-"));
        return Ok(());
    }

    let mut project_id = None;
    if let Some(project_ref) = project_ref.clone() {
        let resp = add_auth_header(
            client.get(format!("{}/api/v1/projects/{}", server, project_ref)),
            api_key,
        )
        .send()
        .await?;
        if resp.status().is_success() {
            let project: serde_json::Value = resp.json().await?;
            project_id = project["id"].as_str().map(|id| id.to_string());
        } else {
            let resp = add_auth_header(
                client
                    .get(format!("{}/api/v1/projects", server))
                    .query(&[("limit", "1000")]),
                api_key,
            )
            .send()
            .await?;
            let projects: serde_json::Value = resp.json().await?;
            if let Some(items) = projects["items"].as_array() {
                for project in items {
                    if project["name"].as_str() == Some(project_ref.as_str()) {
                        project_id = project["id"].as_str().map(|id| id.to_string());
                        break;
                    }
                }
            }
        }
    }

    let mut params: Vec<(&str, String)> = vec![("query", task_ref.to_string())];
    if let Some(value) = project_id.clone() {
        params.push(("project_id", value));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/search", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"].as_array().map(Vec::as_slice).unwrap_or(&[]);
    if items.is_empty() {
        println!("No matching tasks found.");
        return Ok(());
    }
    let task = &items[0];
    println!("Task: {}", task["title"].as_str().unwrap_or("-"));
    println!("ID: {}", task["id"].as_str().unwrap_or("-"));
    println!("Project: {}", task["project_id"].as_str().unwrap_or("-"));
    println!("Status: {}", task["status"].as_str().unwrap_or("-"));
    if items.len() > 1 {
        println!("Note: {} additional matches found.", items.len() - 1);
    }
    Ok(())
}

pub async fn handle_auth_scopes(
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/auth/scopes", server)),
        api_key,
    )
    .send()
    .await?;
    let scopes: serde_json::Value = resp.json().await?;
    let items = scopes["scopes"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    println!("Scopes ({}):", items.len());
    for scope in items {
        if let Some(value) = scope.as_str() {
            println!("  - {}", value);
        }
    }
    Ok(())
}

pub async fn handle_auth_init(
    server: &str,
    client: &reqwest::Client,
    name: Option<String>,
    show_key: bool,
) -> Result<()> {
    let payload = serde_json::json!({
        "name": name.unwrap_or_else(|| "Admin Key".to_string()),
    });
    let resp = client
        .post(format!("{}/api/v1/auth/init", server))
        .header("Content-Type", "application/json")
        .json(&payload)
        .send()
        .await?;
    if !resp.status().is_success() {
        return Err(anyhow::anyhow!("Failed to initialize admin key"));
    }
    let created: serde_json::Value = resp.json().await?;
    let key = created["api_key"].as_str().unwrap_or("");
    let key_file = ".pms-admin-key";
    if !key.is_empty() {
        fs::write(key_file, key)?;
        #[cfg(unix)]
        {
            let perms = fs::Permissions::from_mode(0o600);
            fs::set_permissions(key_file, perms)?;
        }
    }
    println!("✓ Admin API key created");
    if let Some(prefix) = created["key_info"]["prefix"].as_str() {
        println!("  Prefix: {}", prefix);
    }
    println!("  Saved: {}", key_file);
    if show_key && !key.is_empty() {
        println!("  Key: {}", key);
    }
    Ok(())
}

pub async fn handle_api_key_create(
    server: &str,
    client: &reqwest::Client,
    name: String,
    scopes: Vec<String>,
    expires_in_days: Option<i32>,
    rate_limit: Option<i32>,
    metadata: std::collections::HashMap<String, String>,
    api_key: Option<&str>,
) -> Result<()> {
    let payload = serde_json::json!({
        "name": name,
        "scopes": scopes,
        "expires_in_days": expires_in_days,
        "rate_limit": rate_limit,
        "metadata": metadata,
    });
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/auth/keys", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let created: serde_json::Value = resp.json().await?;
    println!("✓ Created API key");
    if let Some(prefix) = created["key_info"]["prefix"].as_str() {
        println!("  Prefix: {}", prefix);
    }
    if let Some(key) = created["api_key"].as_str() {
        println!("  Key: {}", key);
    }
    Ok(())
}

pub async fn handle_api_key_list(
    server: &str,
    client: &reqwest::Client,
    include_inactive: bool,
    include_archived: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/auth/keys", server)).query(&[
            ("include_inactive", include_inactive.to_string()),
            ("include_archived", include_archived.to_string()),
        ]),
        api_key,
    )
    .send()
    .await?;
    let items: serde_json::Value = resp.json().await?;
    let keys = items.as_array().map(Vec::as_slice).unwrap_or(&[]);
    println!("API keys ({}):", keys.len());
    for key in keys {
        println!(
            "  • {} - {}",
            key["name"].as_str().unwrap_or("-"),
            key["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_api_key_get(
    server: &str,
    client: &reqwest::Client,
    key_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/auth/keys/{}", server, key_id)),
        api_key,
    )
    .send()
    .await?;
    let key: serde_json::Value = resp.json().await?;
    println!("API key: {}", key["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", key["id"].as_str().unwrap_or("-"));
    println!("  Prefix: {}", key["prefix"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_api_key_deactivate(
    server: &str,
    client: &reqwest::Client,
    key_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!("{}/api/v1/auth/keys/{}/deactivate", server, key_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deactivated API key {}", key_id);
    Ok(())
}

pub async fn handle_api_key_restore(
    server: &str,
    client: &reqwest::Client,
    key_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!("{}/api/v1/auth/keys/{}/restore", server, key_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Restored/reactivated API key {}", key_id);
    Ok(())
}

pub async fn handle_api_key_delete(
    server: &str,
    client: &reqwest::Client,
    key_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!("{}/api/v1/auth/keys/{}", server, key_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted API key {}", key_id);
    Ok(())
}

pub async fn handle_goal_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/goals", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let goal: serde_json::Value = resp.json().await?;
    println!("✓ Created goal: {}", goal["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", goal["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_goal_list(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    horizon: Option<String>,
    product_id: Option<String>,
    project_id: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(horizon) = horizon {
        params.push(format!("horizon={}", horizon));
    }
    if let Some(product_id) = product_id {
        params.push(format!("product_id={}", product_id));
    }
    if let Some(project_id) = project_id {
        params.push(format!("project_id={}", project_id));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/goals{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Goals ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_goal_get(
    server: &str,
    client: &reqwest::Client,
    goal_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/goals/{}", server, goal_id)),
        api_key,
    )
    .send()
    .await?;
    let goal: serde_json::Value = resp.json().await?;
    println!("Goal: {}", goal["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", goal["id"].as_str().unwrap_or("-"));
    println!("  Status: {}", goal["status"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_goal_update(
    server: &str,
    client: &reqwest::Client,
    goal_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/goals/{}", server, goal_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let goal: serde_json::Value = resp.json().await?;
    println!("✓ Updated goal: {}", goal["name"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_goal_complete(
    server: &str,
    client: &reqwest::Client,
    goal_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!("{}/api/v1/goals/{}/complete", server, goal_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Completed goal {}", goal_id);
    Ok(())
}

pub async fn handle_goal_archive(
    server: &str,
    client: &reqwest::Client,
    goal_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!("{}/api/v1/goals/{}/archive", server, goal_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Archived goal {}", goal_id);
    Ok(())
}

pub async fn handle_goal_summary(
    server: &str,
    client: &reqwest::Client,
    goal_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/goals/{}/summary", server, goal_id)),
        api_key,
    )
    .send()
    .await?;
    let summary: serde_json::Value = resp.json().await?;
    println!("Goal Summary:");
    println!(
        "  Goal: {}",
        summary["goal"]["name"].as_str().unwrap_or("-")
    );
    println!(
        "  Progress: {}",
        summary["stats"]["avg_progress"].as_f64().unwrap_or(0.0)
    );
    Ok(())
}

pub async fn handle_goal_workflow_assign(
    server: &str,
    client: &reqwest::Client,
    goal_id: &str,
    workflow_name: &str,
    initial_state: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let payload = serde_json::json!({
        "workflow_name": workflow_name,
        "initial_state": initial_state,
    });
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/goals/{}/workflow/assign",
                server, goal_id
            ))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "✓ Assigned workflow {}",
        result["workflow"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_goal_workflow_transition(
    server: &str,
    client: &reqwest::Client,
    goal_id: &str,
    to_state: &str,
    by: &str,
    reason: Option<String>,
    approved_by: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let payload = serde_json::json!({
        "to_state": to_state,
        "triggered_by": by,
        "reason": reason,
        "approved_by": approved_by,
    });
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/goals/{}/workflow/transition",
                server, goal_id
            ))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "✓ Transitioned to {}",
        result["to_state"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_objective_create(
    server: &str,
    client: &reqwest::Client,
    goal_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/goals/{}/objectives", server, goal_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let objective: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created objective: {}",
        objective["name"].as_str().unwrap_or("-")
    );
    println!("  ID: {}", objective["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_objective_list(
    server: &str,
    client: &reqwest::Client,
    goal_id: &str,
    status: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/goals/{}/objectives{}",
            server, goal_id, query
        )),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Objectives ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_objective_get(
    server: &str,
    client: &reqwest::Client,
    objective_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/objectives/{}", server, objective_id)),
        api_key,
    )
    .send()
    .await?;
    let objective: serde_json::Value = resp.json().await?;
    println!("Objective: {}", objective["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", objective["id"].as_str().unwrap_or("-"));
    println!("  Status: {}", objective["status"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_objective_update(
    server: &str,
    client: &reqwest::Client,
    objective_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/objectives/{}", server, objective_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let objective: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated objective: {}",
        objective["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_objective_complete(
    server: &str,
    client: &reqwest::Client,
    objective_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!(
            "{}/api/v1/objectives/{}/complete",
            server, objective_id
        )),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Completed objective {}", objective_id);
    Ok(())
}

pub async fn handle_objective_archive(
    server: &str,
    client: &reqwest::Client,
    objective_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!(
            "{}/api/v1/objectives/{}/archive",
            server, objective_id
        )),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Archived objective {}", objective_id);
    Ok(())
}

pub async fn handle_objective_workflow_assign(
    server: &str,
    client: &reqwest::Client,
    objective_id: &str,
    workflow_name: &str,
    initial_state: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let payload = serde_json::json!({
        "workflow_name": workflow_name,
        "initial_state": initial_state,
    });
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/objectives/{}/workflow/assign",
                server, objective_id
            ))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "✓ Assigned workflow {}",
        result["workflow"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_objective_workflow_transition(
    server: &str,
    client: &reqwest::Client,
    objective_id: &str,
    to_state: &str,
    by: &str,
    reason: Option<String>,
    approved_by: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let payload = serde_json::json!({
        "to_state": to_state,
        "triggered_by": by,
        "reason": reason,
        "approved_by": approved_by,
    });
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/objectives/{}/workflow/transition",
                server, objective_id
            ))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "✓ Transitioned to {}",
        result["to_state"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_key_result_create(
    server: &str,
    client: &reqwest::Client,
    objective_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/objectives/{}/key-results",
                server, objective_id
            ))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let kr: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created key result: {}",
        kr["name"].as_str().unwrap_or("-")
    );
    println!("  ID: {}", kr["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_key_result_list(
    server: &str,
    client: &reqwest::Client,
    objective_id: &str,
    status: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(status) = status {
        params.push(format!("status={}", status));
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/objectives/{}/key-results{}",
            server, objective_id, query
        )),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Key results ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_key_result_get(
    server: &str,
    client: &reqwest::Client,
    key_result_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/key-results/{}", server, key_result_id)),
        api_key,
    )
    .send()
    .await?;
    let kr: serde_json::Value = resp.json().await?;
    println!("Key result: {}", kr["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", kr["id"].as_str().unwrap_or("-"));
    println!("  Status: {}", kr["status"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_key_result_update(
    server: &str,
    client: &reqwest::Client,
    key_result_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/key-results/{}", server, key_result_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let kr: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated key result: {}",
        kr["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_key_result_complete(
    server: &str,
    client: &reqwest::Client,
    key_result_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!(
            "{}/api/v1/key-results/{}/complete",
            server, key_result_id
        )),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Completed key result {}", key_result_id);
    Ok(())
}

pub async fn handle_key_result_archive(
    server: &str,
    client: &reqwest::Client,
    key_result_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!(
            "{}/api/v1/key-results/{}/archive",
            server, key_result_id
        )),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Archived key result {}", key_result_id);
    Ok(())
}

pub async fn handle_label_category_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/labels/categories", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let category: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created label category: {}",
        category["name"].as_str().unwrap_or("-")
    );
    println!("  ID: {}", category["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_label_category_list(
    server: &str,
    client: &reqwest::Client,
    include_archived: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/labels/categories", server))
            .query(&[("include_archived", include_archived.to_string())]),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Label categories ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_label_category_get(
    server: &str,
    client: &reqwest::Client,
    category_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/labels/categories/{}",
            server, category_id
        )),
        api_key,
    )
    .send()
    .await?;
    let category: serde_json::Value = resp.json().await?;
    println!(
        "Label category: {}",
        category["name"].as_str().unwrap_or("-")
    );
    println!("  ID: {}", category["id"].as_str().unwrap_or("-"));
    println!(
        "  Exclusive: {}",
        category["is_exclusive"].as_bool().unwrap_or(false)
    );
    Ok(())
}

pub async fn handle_label_category_update(
    server: &str,
    client: &reqwest::Client,
    category_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!(
                "{}/api/v1/labels/categories/{}",
                server, category_id
            ))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let category: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated category: {}",
        category["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_label_category_delete(
    server: &str,
    client: &reqwest::Client,
    category_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!(
            "{}/api/v1/labels/categories/{}",
            server, category_id
        )),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted label category {}", category_id);
    Ok(())
}

pub async fn handle_label_category_restore(
    server: &str,
    client: &reqwest::Client,
    category_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!(
            "{}/api/v1/labels/categories/{}/restore",
            server, category_id
        )),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Restored label category {}", category_id);
    Ok(())
}

pub async fn handle_label_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/labels", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let label: serde_json::Value = resp.json().await?;
    println!("✓ Created label: {}", label["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", label["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_label_list(
    server: &str,
    client: &reqwest::Client,
    category_id: Option<String>,
    include_archived: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/labels", server)).query(&[
            ("category_id", category_id.unwrap_or_default()),
            ("include_archived", include_archived.to_string()),
        ]),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Labels ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_label_get(
    server: &str,
    client: &reqwest::Client,
    label_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/labels/{}", server, label_id)),
        api_key,
    )
    .send()
    .await?;
    let label: serde_json::Value = resp.json().await?;
    println!("Label: {}", label["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", label["id"].as_str().unwrap_or("-"));
    println!(
        "  Category: {}",
        label["category_id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_label_update(
    server: &str,
    client: &reqwest::Client,
    label_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/labels/{}", server, label_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let label: serde_json::Value = resp.json().await?;
    println!("✓ Updated label: {}", label["name"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_label_delete(
    server: &str,
    client: &reqwest::Client,
    label_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!("{}/api/v1/labels/{}", server, label_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted label {}", label_id);
    Ok(())
}

pub async fn handle_label_restore(
    server: &str,
    client: &reqwest::Client,
    label_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!("{}/api/v1/labels/{}/restore", server, label_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Restored label {}", label_id);
    Ok(())
}

pub async fn handle_label_assign(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/labels/assignments", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let assignment: serde_json::Value = resp.json().await?;
    println!(
        "✓ Assigned label {}",
        assignment["label_id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_label_assignments(
    server: &str,
    client: &reqwest::Client,
    entity_type: &str,
    entity_id: &str,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![
        format!("entity_type={}", entity_type),
        format!("entity_id={}", entity_id),
    ];
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = format!("?{}", params.join("&"));
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/labels/assignments{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Label assignments ({}):", items.len());
    for item in items {
        println!(
            "  • {} -> {}",
            item["name"].as_str().unwrap_or("-"),
            item["assignment"]["entity_id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_label_assignment_history(
    server: &str,
    client: &reqwest::Client,
    assignment_id: &str,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/labels/assignments/{}/history{}",
            server, assignment_id, query
        )),
        api_key,
    )
    .send()
    .await?;
    let history: serde_json::Value = resp.json().await?;
    let items = history["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Assignment history ({}):", items.len());
    Ok(())
}

pub async fn handle_label_assignment_remove(
    server: &str,
    client: &reqwest::Client,
    entity_type: &str,
    entity_id: &str,
    label_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client
            .delete(format!("{}/api/v1/labels/assignments", server))
            .query(&[
                ("entity_type", entity_type),
                ("entity_id", entity_id),
                ("label_id", label_id),
            ]),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Removed label {}", label_id);
    Ok(())
}

pub async fn handle_label_gate_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/labels/gates", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let rule: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created label gate {}",
        rule["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_label_gate_list(
    server: &str,
    client: &reqwest::Client,
    workflow_id: &str,
    entity_type: &str,
    from_state: &str,
    to_state: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/labels/gates", server))
            .query(&[
                ("workflow_id", workflow_id),
                ("entity_type", entity_type),
                ("from_state", from_state),
                ("to_state", to_state),
            ]),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Label gates ({}):", items.len());
    for item in items {
        println!(
            "  • {} -> {} ({})",
            item["from_state"].as_str().unwrap_or("-"),
            item["to_state"].as_str().unwrap_or("-"),
            item["rule_type"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_label_gate_delete(
    server: &str,
    client: &reqwest::Client,
    rule_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!("{}/api/v1/labels/gates/{}", server, rule_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted label gate {}", rule_id);
    Ok(())
}

pub async fn handle_custom_field_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/custom-fields", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let definition: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created custom field: {} ({})",
        definition["name"].as_str().unwrap_or("-"),
        definition["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_custom_field_list(
    server: &str,
    client: &reqwest::Client,
    entity_type: Option<String>,
    include_archived: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(entity_type) = entity_type {
        params.push(format!("entity_type={}", entity_type));
    }
    if include_archived {
        params.push("include_archived=true".to_string());
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/custom-fields{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Custom fields ({}):", items.len());
    for item in items {
        println!(
            "  • {} ({}) [{}]",
            item["name"].as_str().unwrap_or("-"),
            item["entity_type"].as_str().unwrap_or("-"),
            item["field_type"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_custom_field_show(
    server: &str,
    client: &reqwest::Client,
    field_ref: &str,
    entity_type: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/custom-fields/{}", server, field_ref)),
        api_key,
    )
    .send()
    .await?;
    if resp.status() == reqwest::StatusCode::NOT_FOUND {
        if let Some(entity_type) = entity_type {
            let list_resp = add_auth_header(
                client
                    .get(format!("{}/api/v1/custom-fields", server))
                    .query(&[("entity_type", entity_type)]),
                api_key,
            )
            .send()
            .await?;
            let result: serde_json::Value = list_resp.json().await?;
            let items = result["items"]
                .as_array()
                .map(|items| items.as_slice())
                .unwrap_or(&[]);
            for item in items {
                if item["name"].as_str().unwrap_or("") == field_ref {
                    println!(
                        "Custom field: {} ({})",
                        item["name"].as_str().unwrap_or("-"),
                        item["id"].as_str().unwrap_or("-")
                    );
                    return Ok(());
                }
            }
        }
        bail!("Custom field not found");
    }
    let definition: serde_json::Value = resp.json().await?;
    println!(
        "Custom field: {} ({})",
        definition["name"].as_str().unwrap_or("-"),
        definition["id"].as_str().unwrap_or("-")
    );
    println!(
        "  Entity: {}",
        definition["entity_type"].as_str().unwrap_or("-")
    );
    println!(
        "  Type: {}",
        definition["field_type"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_custom_field_update(
    server: &str,
    client: &reqwest::Client,
    field_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/custom-fields/{}", server, field_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let definition: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated custom field: {}",
        definition["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_custom_field_delete(
    server: &str,
    client: &reqwest::Client,
    field_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!("{}/api/v1/custom-fields/{}", server, field_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted custom field {}", field_id);
    Ok(())
}

pub async fn handle_custom_field_restore(
    server: &str,
    client: &reqwest::Client,
    field_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!(
            "{}/api/v1/custom-fields/{}/restore",
            server, field_id
        )),
        api_key,
    )
    .send()
    .await?;
    let definition: serde_json::Value = resp.json().await?;
    println!(
        "✓ Restored custom field: {}",
        definition["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_custom_field_value_set(
    server: &str,
    client: &reqwest::Client,
    field_ref: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/custom-fields/{}/values",
                server, field_ref
            ))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "✓ Set custom field value: {}",
        result["value"]["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_custom_field_value_list(
    server: &str,
    client: &reqwest::Client,
    entity_type: Option<String>,
    entity_id: Option<String>,
    field_id: Option<String>,
    include_history: bool,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }

    let resp = if let Some(field_id) = field_id {
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!("?{}", params.join("&"))
        };
        add_auth_header(
            client.get(format!(
                "{}/api/v1/custom-fields/{}/values{}",
                server, field_id, query
            )),
            api_key,
        )
        .send()
        .await?
    } else {
        if let Some(entity_type) = entity_type.clone() {
            params.push(format!("entity_type={}", entity_type));
        }
        if let Some(entity_id) = entity_id.clone() {
            params.push(format!("entity_id={}", entity_id));
        }
        if include_history {
            params.push("include_history=true".to_string());
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!("?{}", params.join("&"))
        };
        add_auth_header(
            client.get(format!("{}/api/v1/custom-fields/values{}", server, query)),
            api_key,
        )
        .send()
        .await?
    };

    let result: serde_json::Value = resp.json().await?;
    let items = result["items"]
        .as_array()
        .map(|items| items.as_slice())
        .unwrap_or(&[]);
    println!("Custom field values ({}):", items.len());
    for item in items {
        let definition = &item["definition"];
        let value = &item["value"];
        let field_name = definition["name"].as_str().unwrap_or("-");
        println!("  • {} -> {}", field_name, value["value"].to_string());
    }
    Ok(())
}

pub async fn handle_comment_add(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/comments", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let comment: serde_json::Value = resp.json().await?;
    println!(
        "✓ Added comment {} on {} {}",
        comment["id"].as_str().unwrap_or("-"),
        comment["entity_type"].as_str().unwrap_or("-"),
        comment["entity_id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_comment_list(
    server: &str,
    client: &reqwest::Client,
    entity_type: &str,
    entity_id: &str,
    include_archived: bool,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![
        format!("entity_type={}", entity_type),
        format!("entity_id={}", entity_id),
    ];
    if include_archived {
        params.push("include_archived=true".to_string());
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = format!("?{}", params.join("&"));
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/comments{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"].as_array();
    println!(
        "Comments ({}):",
        items.map(|items| items.len()).unwrap_or(0)
    );
    if let Some(items) = items {
        for item in items {
            let comment_id = item["id"].as_str().unwrap_or("-");
            let created_by = item["created_by"].as_str().unwrap_or("-");
            let body = item["body"].as_str().unwrap_or("");
            println!("  • {} by {} - {}", comment_id, created_by, body);
        }
    }
    Ok(())
}

pub async fn handle_comment_show(
    server: &str,
    client: &reqwest::Client,
    comment_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/comments/{}", server, comment_id)),
        api_key,
    )
    .send()
    .await?;
    let comment: serde_json::Value = resp.json().await?;
    println!("Comment: {}", comment["id"].as_str().unwrap_or("-"));
    println!(
        "  Entity: {} {}",
        comment["entity_type"], comment["entity_id"]
    );
    println!("  By: {}", comment["created_by"]);
    println!("  Body: {}", comment["body"]);
    Ok(())
}

pub async fn handle_comment_delete(
    server: &str,
    client: &reqwest::Client,
    comment_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!("{}/api/v1/comments/{}", server, comment_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted comment {}", comment_id);
    Ok(())
}

pub async fn handle_comment_restore(
    server: &str,
    client: &reqwest::Client,
    comment_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!("{}/api/v1/comments/{}/restore", server, comment_id)),
        api_key,
    )
    .send()
    .await?;
    let comment: serde_json::Value = resp.json().await?;
    println!(
        "✓ Restored comment {} on {} {}",
        comment["id"].as_str().unwrap_or("-"),
        comment["entity_type"].as_str().unwrap_or("-"),
        comment["entity_id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_watcher_add(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/watchers", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let watcher: serde_json::Value = resp.json().await?;
    println!(
        "✓ Added watcher {} ({})",
        watcher["watcher"].as_str().unwrap_or("-"),
        watcher["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_watcher_list(
    server: &str,
    client: &reqwest::Client,
    entity_type: &str,
    entity_id: &str,
    include_archived: bool,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![
        format!("entity_type={}", entity_type),
        format!("entity_id={}", entity_id),
    ];
    if include_archived {
        params.push("include_archived=true".to_string());
    }
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = format!("?{}", params.join("&"));
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/watchers{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"].as_array();
    println!(
        "Watchers ({}):",
        items.map(|items| items.len()).unwrap_or(0)
    );
    if let Some(items) = items {
        for item in items {
            println!(
                "  • {} ({})",
                item["watcher"].as_str().unwrap_or("-"),
                item["id"].as_str().unwrap_or("-")
            );
        }
    }
    Ok(())
}

pub async fn handle_watcher_remove(
    server: &str,
    client: &reqwest::Client,
    entity_type: &str,
    entity_id: &str,
    watcher: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let query = format!(
        "?entity_type={}&entity_id={}&watcher={}",
        entity_type, entity_id, watcher
    );
    add_auth_header(
        client.delete(format!("{}/api/v1/watchers{}", server, query)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Removed watcher {}", watcher);
    Ok(())
}

pub async fn handle_watcher_restore(
    server: &str,
    client: &reqwest::Client,
    watcher_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!("{}/api/v1/watchers/{}/restore", server, watcher_id)),
        api_key,
    )
    .send()
    .await?;
    let watcher: serde_json::Value = resp.json().await?;
    println!(
        "✓ Restored watcher {} ({})",
        watcher["watcher"].as_str().unwrap_or("-"),
        watcher["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_automation_rule_create(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/automation/rules", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let rule: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created automation rule: {} ({})",
        rule["name"].as_str().unwrap_or("-"),
        rule["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_automation_rule_list(
    server: &str,
    client: &reqwest::Client,
    include_archived: bool,
    enabled: Option<bool>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![("include_archived", include_archived.to_string())];
    if let Some(enabled) = enabled {
        params.push(("enabled", enabled.to_string()));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/automation/rules", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"].as_array();
    println!(
        "Automation rules ({}):",
        items.map(|items| items.len()).unwrap_or(0)
    );
    if let Some(items) = items {
        for item in items {
            println!(
                "  • {} [{}]",
                item["name"].as_str().unwrap_or("-"),
                item["action_type"].as_str().unwrap_or("-")
            );
        }
    }
    Ok(())
}

pub async fn handle_automation_rule_show(
    server: &str,
    client: &reqwest::Client,
    rule_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/automation/rules/{}", server, rule_id)),
        api_key,
    )
    .send()
    .await?;
    let rule: serde_json::Value = resp.json().await?;
    println!("Automation rule: {}", rule["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", rule["id"].as_str().unwrap_or("-"));
    println!(
        "  Pattern: {}",
        rule["event_pattern"].as_str().unwrap_or("-")
    );
    println!("  Action: {}", rule["action_type"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_automation_rule_update(
    server: &str,
    client: &reqwest::Client,
    rule_id: &str,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/automation/rules/{}", server, rule_id))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let rule: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated automation rule: {}",
        rule["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_automation_rule_delete(
    server: &str,
    client: &reqwest::Client,
    rule_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!("{}/api/v1/automation/rules/{}", server, rule_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted automation rule {}", rule_id);
    Ok(())
}

pub async fn handle_automation_rule_restore(
    server: &str,
    client: &reqwest::Client,
    rule_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!(
            "{}/api/v1/automation/rules/{}/restore",
            server, rule_id
        )),
        api_key,
    )
    .send()
    .await?;
    let rule: serde_json::Value = resp.json().await?;
    println!(
        "✓ Restored automation rule: {}",
        rule["name"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_automation_rule_runs(
    server: &str,
    client: &reqwest::Client,
    rule_id: &str,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![];
    if let Some(limit) = limit {
        params.push(format!("limit={}", limit));
    }
    if let Some(offset) = offset {
        params.push(format!("offset={}", offset));
    }
    let query = if params.is_empty() {
        "".to_string()
    } else {
        format!("?{}", params.join("&"))
    };
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/automation/rules/{}/runs{}",
            server, rule_id, query
        )),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result["items"].as_array();
    println!(
        "Automation runs ({}):",
        items.map(|items| items.len()).unwrap_or(0)
    );
    if let Some(items) = items {
        for item in items {
            println!(
                "  • {} [{}]",
                item["id"].as_str().unwrap_or("-"),
                item["status"].as_str().unwrap_or("-")
            );
        }
    }
    Ok(())
}

pub async fn handle_automation_run(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/automation/run", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let items = result.as_array();
    println!(
        "Automation run results ({}):",
        items.map(|items| items.len()).unwrap_or(0)
    );
    if let Some(items) = items {
        for item in items {
            println!(
                "  • {} [{}]",
                item["id"].as_str().unwrap_or("-"),
                item["status"].as_str().unwrap_or("-")
            );
        }
    }
    Ok(())
}

pub async fn handle_plan_create(
    server: &str,
    client: &reqwest::Client,
    req: CreatePlanRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!("{}/api/v1/plans", server)).json(&req),
        api_key,
    )
    .send()
    .await?;
    let plan: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created plan: {} ({})",
        plan["name"].as_str().unwrap_or("-"),
        plan["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_plan_list(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    project_id: Option<String>,
    product_id: Option<String>,
    goal_id: Option<String>,
    objective_id: Option<String>,
    task_id: Option<String>,
    format: &str,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let params = plan_list_query_params(
        status.as_deref(),
        project_id.as_deref(),
        product_id.as_deref(),
        goal_id.as_deref(),
        objective_id.as_deref(),
        task_id.as_deref(),
        limit,
        offset,
    );
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/plans", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let items = result["items"].as_array().unwrap_or(&empty);
    if format == "json" {
        let mut project_hint = project_id
            .as_ref()
            .map(|pid| format!("plan list --project-id {}", pid))
            .unwrap_or_else(|| "plan list".to_string());
        if let Some(status_value) = status.as_ref() {
            project_hint.push_str(&format!(" --status {}", status_value));
        }
        if let Some(product_id_value) = product_id.as_ref() {
            project_hint.push_str(&format!(" --product-id {}", product_id_value));
        }
        if let Some(goal_id_value) = goal_id.as_ref() {
            project_hint.push_str(&format!(" --goal-id {}", goal_id_value));
        }
        if let Some(objective_id_value) = objective_id.as_ref() {
            project_hint.push_str(&format!(" --objective-id {}", objective_id_value));
        }
        if let Some(task_id_value) = task_id.as_ref() {
            project_hint.push_str(&format!(" --task-id {}", task_id_value));
        }
        if let Some(limit_value) = limit {
            project_hint.push_str(&format!(" --limit {}", limit_value));
        }
        if let Some(offset_value) = offset {
            project_hint.push_str(&format!(" --offset {}", offset_value));
        }
        let focus_task = result
            .get("focus_task")
            .cloned()
            .unwrap_or(serde_json::Value::Null);
        let enriched_items: Vec<serde_json::Value> = items
            .iter()
            .map(|plan| {
                let plan_id = plan["id"].as_str().unwrap_or("");
                let mut enriched = plan.clone();
                if let Some(object) = enriched.as_object_mut() {
                    object.insert(
                        "links".to_string(),
                        serde_json::json!({
                            "self": cli_command(server, &format!("plan show {}", plan_id)),
                            "lineage": cli_command(server, &format!("plan lineage --plan-id {}", plan_id)),
                        }),
                    );
                }
                enriched
            })
            .collect();
        let mut next_steps: Vec<String> = Vec::new();
        if let Some(task) = focus_task.as_object() {
            if let Some(task_id) = task.get("id").and_then(serde_json::Value::as_str) {
                next_steps.push(cli_command(server, &format!("task show {}", task_id)));
            }
        }
        if let Some(first_plan) = items.first() {
            if let Some(plan_id) = first_plan.get("id").and_then(serde_json::Value::as_str) {
                next_steps.push(cli_command(server, &format!("plan show {}", plan_id)));
                next_steps.push(cli_command(
                    server,
                    &format!("plan lineage --plan-id {}", plan_id),
                ));
            }
        }
        next_steps.push(cli_command(server, "start --format json"));
        let payload = serde_json::json!({
            "generated_at": Utc::now().to_rfc3339(),
            "purpose": "Machine-readable plan list for the installed Rust fast path with runnable plan links and next steps.",
            "items": enriched_items,
            "focus_task": focus_task,
            "page": {
                "total_count": result["page"]["total_count"].as_u64().unwrap_or(items.len() as u64),
                "limit": result["page"]["limit"].as_u64().unwrap_or(limit.unwrap_or(100) as u64),
                "offset": result["page"]["offset"].as_u64().unwrap_or(offset.unwrap_or(0) as u64),
                "has_more": result["page"]["has_more"].as_bool().unwrap_or(false),
                "next_offset": result["page"]["next_offset"].as_u64(),
            },
            "links": {
                "self": cli_command(server, &format!("{} --format json", project_hint)),
                "guide": cli_command(server, "start --format json"),
            },
            "next_steps": next_steps,
            "cli": {
                "canonical_prefix": cli_command_prefix(server),
                "alternate_prefix": current_rust_cli_prefix(server),
            },
        });
        println!("{}", serde_json::to_string_pretty(&payload)?);
        return Ok(());
    }
    println!("Plans ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_plan_get(
    server: &str,
    client: &reqwest::Client,
    plan_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/plans/{}", server, plan_id)),
        api_key,
    )
    .send()
    .await?;
    let plan: serde_json::Value = resp.json().await?;
    println!("Plan: {}", plan["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", plan["id"].as_str().unwrap_or("-"));
    println!("  Status: {}", plan["status"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_plan_update(
    server: &str,
    client: &reqwest::Client,
    plan_id: &str,
    req: UpdatePlanRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!("{}/api/v1/plans/{}", server, plan_id))
            .json(&req),
        api_key,
    )
    .send()
    .await?;
    let plan: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated plan: {} ({})",
        plan["name"].as_str().unwrap_or("-"),
        plan["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_plan_lineage(
    server: &str,
    client: &reqwest::Client,
    status: Option<String>,
    project_id: Option<String>,
    plan_id: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    task_limit: Option<u32>,
    test_limit: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = status {
        params.push(("status", value));
    }
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    if let Some(value) = plan_id {
        params.push(("plan_id", value));
    }
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = offset {
        params.push(("offset", value.to_string()));
    }
    if let Some(value) = task_limit {
        params.push(("task_limit", value.to_string()));
    }
    if let Some(value) = test_limit {
        params.push(("test_limit", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/plans/lineage", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let total_plans = result["total_count"].as_u64().unwrap_or(0);
    println!("Plan lineage items: {}", total_plans);
    Ok(())
}

pub async fn handle_plan_test_job_create(
    server: &str,
    client: &reqwest::Client,
    plan_id: &str,
    req: PlanTestJobCreateRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/plans/{}/test-jobs", server, plan_id))
            .json(&req),
        api_key,
    )
    .send()
    .await?;
    let job: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created plan test job: {} ({})",
        job["name"].as_str().unwrap_or("-"),
        job["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_plan_test_job_list(
    server: &str,
    client: &reqwest::Client,
    plan_id: &str,
    limit: Option<u32>,
    offset: Option<u32>,
    include_archived: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = offset {
        params.push(("offset", value.to_string()));
    }
    params.push(("include_archived", include_archived.to_string()));

    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/plans/{}/test-jobs", server, plan_id))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let items = result["items"].as_array().unwrap_or(&empty);
    println!("Plan test jobs ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_plan_test_job_get(
    server: &str,
    client: &reqwest::Client,
    plan_id: &str,
    job_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/plans/{}/test-jobs/{}",
            server, plan_id, job_id
        )),
        api_key,
    )
    .send()
    .await?;
    let job: serde_json::Value = resp.json().await?;
    println!("Plan test job: {}", job["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", job["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_plan_test_job_update(
    server: &str,
    client: &reqwest::Client,
    plan_id: &str,
    job_id: &str,
    req: PlanTestJobUpdateRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .patch(format!(
                "{}/api/v1/plans/{}/test-jobs/{}",
                server, plan_id, job_id
            ))
            .json(&req),
        api_key,
    )
    .send()
    .await?;
    let job: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated plan test job: {} ({})",
        job["name"].as_str().unwrap_or("-"),
        job["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_plan_test_job_delete(
    server: &str,
    client: &reqwest::Client,
    plan_id: &str,
    job_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!(
            "{}/api/v1/plans/{}/test-jobs/{}",
            server, plan_id, job_id
        )),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted plan test job {}", job_id);
    Ok(())
}

pub async fn handle_plan_test_job_restore(
    server: &str,
    client: &reqwest::Client,
    plan_id: &str,
    job_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!(
            "{}/api/v1/plans/{}/test-jobs/{}/restore",
            server, plan_id, job_id
        )),
        api_key,
    )
    .send()
    .await?;
    let job: serde_json::Value = resp.json().await?;
    println!(
        "✓ Restored plan test job: {} ({})",
        job["name"].as_str().unwrap_or("-"),
        job["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_plan_test_job_run(
    server: &str,
    client: &reqwest::Client,
    plan_id: &str,
    job_id: &str,
    include_output: bool,
    include_logs: bool,
    include_artifacts: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/plans/{}/test-jobs/{}/run",
                server, plan_id, job_id
            ))
            .query(&[
                ("include_output", include_output.to_string()),
                ("include_logs", include_logs.to_string()),
                ("include_artifacts", include_artifacts.to_string()),
            ]),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let job_name = result["job"]["name"].as_str().unwrap_or("-");
    let run_id = result["test_run"]["id"].as_str().unwrap_or("-");
    println!("✓ Ran plan test job: {} (run {})", job_name, run_id);
    Ok(())
}

pub async fn handle_queue_create(
    server: &str,
    client: &reqwest::Client,
    req: CreateQueueRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!("{}/api/v1/queues", server)).json(&req),
        api_key,
    )
    .send()
    .await?;
    let queue: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created queue: {} ({})",
        queue["name"].as_str().unwrap_or("-"),
        queue["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_queue_list(
    server: &str,
    client: &reqwest::Client,
    owner: Option<String>,
    scope_type: Option<String>,
    scope_id: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    include_archived: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = owner {
        params.push(("owner", value));
    }
    if let Some(value) = scope_type {
        params.push(("scope_type", value));
    }
    if let Some(value) = scope_id {
        params.push(("scope_id", value));
    }
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = offset {
        params.push(("offset", value.to_string()));
    }
    params.push(("include_archived", include_archived.to_string()));

    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/queues", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let items = result["items"].as_array().unwrap_or(&empty);
    println!("Queues ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_queue_get(
    server: &str,
    client: &reqwest::Client,
    queue_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/queues/{}", server, queue_id)),
        api_key,
    )
    .send()
    .await?;
    let queue: serde_json::Value = resp.json().await?;
    println!("Queue: {}", queue["name"].as_str().unwrap_or("-"));
    println!("  ID: {}", queue["id"].as_str().unwrap_or("-"));
    Ok(())
}

pub async fn handle_queue_update(
    server: &str,
    client: &reqwest::Client,
    queue_id: &str,
    req: UpdateQueueRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .put(format!("{}/api/v1/queues/{}", server, queue_id))
            .json(&req),
        api_key,
    )
    .send()
    .await?;
    let queue: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated queue: {} ({})",
        queue["name"].as_str().unwrap_or("-"),
        queue["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_queue_delete(
    server: &str,
    client: &reqwest::Client,
    queue_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!("{}/api/v1/queues/{}", server, queue_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted queue {}", queue_id);
    Ok(())
}

pub async fn handle_queue_restore(
    server: &str,
    client: &reqwest::Client,
    queue_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!("{}/api/v1/queues/{}/restore", server, queue_id)),
        api_key,
    )
    .send()
    .await?;
    let queue: serde_json::Value = resp.json().await?;
    println!(
        "✓ Restored queue: {} ({})",
        queue["name"].as_str().unwrap_or("-"),
        queue["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_queue_run(
    server: &str,
    client: &reqwest::Client,
    queue_id: &str,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = offset {
        params.push(("offset", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/queues/{}/run", server, queue_id))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let total = result["total_count"].as_u64().unwrap_or(0);
    println!("Queue results: {} task(s)", total);
    Ok(())
}

pub async fn handle_queue_presets(
    server: &str,
    client: &reqwest::Client,
    project_id: Option<String>,
    limit: Option<u32>,
    stale_days: Option<u32>,
    at_risk_days: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = stale_days {
        params.push(("stale_days", value.to_string()));
    }
    if let Some(value) = at_risk_days {
        params.push(("at_risk_days", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/queues/presets", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let presets: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let items = presets.as_array().unwrap_or(&empty);
    println!("Queue presets ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {}",
            item["name"].as_str().unwrap_or("-"),
            item["description"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_queue_preset(
    server: &str,
    client: &reqwest::Client,
    preset: &str,
    project_id: Option<String>,
    limit: Option<u32>,
    offset: Option<u32>,
    stale_days: Option<u32>,
    at_risk_days: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = offset {
        params.push(("offset", value.to_string()));
    }
    if let Some(value) = stale_days {
        params.push(("stale_days", value.to_string()));
    }
    if let Some(value) = at_risk_days {
        params.push(("at_risk_days", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/queues/presets/{}", server, preset))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let queue: serde_json::Value = resp.json().await?;
    println!(
        "Queue preset: {} ({} tasks)",
        queue["name"].as_str().unwrap_or("-"),
        queue["total_count"].as_u64().unwrap_or(0)
    );
    Ok(())
}

pub async fn handle_test_run_list(
    server: &str,
    client: &reqwest::Client,
    server_id: Option<String>,
    project_id: Option<String>,
    success: Option<bool>,
    include_output: bool,
    include_logs: bool,
    include_artifacts: bool,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = server_id {
        params.push(("server_id", value));
    }
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    if let Some(value) = success {
        params.push(("success", value.to_string()));
    }
    params.push(("include_output", include_output.to_string()));
    params.push(("include_logs", include_logs.to_string()));
    params.push(("include_artifacts", include_artifacts.to_string()));
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = offset {
        params.push(("offset", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/test-runs", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let items = result["items"].as_array().unwrap_or(&empty);
    println!("Test runs ({}):", items.len());
    for item in items {
        println!(
            "  • {} - success={}",
            item["id"].as_str().unwrap_or("-"),
            item["success"].as_bool().unwrap_or(false)
        );
    }
    Ok(())
}

pub async fn handle_test_run_local(
    project_path: &str,
    test_command: String,
    setup_cmd: Option<String>,
    working_dir: Option<String>,
    timeout: f64,
    project_ref: Option<String>,
    project_id: Option<String>,
    plan_ref: Option<String>,
    plan_id: Option<String>,
    task_ids: Vec<String>,
    capture_logs: Vec<String>,
    save_artifacts: Vec<String>,
    env_vars: Vec<String>,
    on_success_state: Option<String>,
    on_failure_state: Option<String>,
    transition_by: Option<String>,
    transition_reason: Option<String>,
    no_output: bool,
) -> Result<()> {
    if project_ref.is_some() && project_id.is_some() {
        bail!("Use --project or --project-id, not both");
    }
    if plan_ref.is_some() && plan_id.is_some() {
        bail!("Use --plan or --plan-id, not both");
    }

    let mut cmd = python_cli_command();
    cmd.arg("test")
        .arg("run")
        .arg(project_path)
        .arg("--command")
        .arg(test_command)
        .arg("--timeout")
        .arg(timeout.to_string());

    if let Some(value) = setup_cmd {
        cmd.arg("--setup").arg(value);
    }
    if let Some(value) = working_dir {
        cmd.arg("--workdir").arg(value);
    }
    if let Some(value) = project_ref {
        cmd.arg("--project").arg(value);
    }
    if let Some(value) = project_id {
        cmd.arg("--project-id").arg(value);
    }
    if let Some(value) = plan_ref {
        cmd.arg("--plan").arg(value);
    }
    if let Some(value) = plan_id {
        cmd.arg("--plan-id").arg(value);
    }
    for item in task_ids {
        cmd.arg("--task-id").arg(item);
    }
    for item in capture_logs {
        cmd.arg("--capture-log").arg(item);
    }
    for item in save_artifacts {
        cmd.arg("--save-artifact").arg(item);
    }
    for item in env_vars {
        cmd.arg("--env").arg(item);
    }
    if let Some(value) = on_success_state {
        cmd.arg("--on-success-state").arg(value);
    }
    if let Some(value) = on_failure_state {
        cmd.arg("--on-failure-state").arg(value);
    }
    if let Some(value) = transition_by {
        cmd.arg("--transition-by").arg(value);
    }
    if let Some(value) = transition_reason {
        cmd.arg("--transition-reason").arg(value);
    }
    if no_output {
        cmd.arg("--no-output");
    }

    run_python_cli(cmd, "Test run failed").await
}

pub async fn handle_test_server_ensure_local(
    project: Option<String>,
    project_id: Option<String>,
    format: String,
) -> Result<()> {
    if project.is_some() && project_id.is_some() {
        bail!("Use --project or --project-id, not both");
    }

    let mut cmd = python_cli_command();
    cmd.arg("test")
        .arg("server")
        .arg("ensure-local")
        .arg("--format")
        .arg(format);

    if let Some(value) = project {
        cmd.arg("--project").arg(value);
    }
    if let Some(value) = project_id {
        cmd.arg("--project-id").arg(value);
    }

    run_python_cli(cmd, "Local test-server ensure-local failed").await
}

pub async fn handle_auth_recover_local_admin(name: Option<String>, show_key: bool) -> Result<()> {
    let mut cmd = python_cli_command();
    cmd.arg("auth").arg("recover-local-admin");
    if let Some(value) = name {
        cmd.arg("--name").arg(value);
    }
    if show_key {
        cmd.arg("--show-key");
    }
    run_python_cli(cmd, "Auth recover-local-admin failed").await
}

pub async fn handle_runtime_prefer_server(
    host: String,
    port: u16,
    install_client: bool,
    sign: bool,
    format: String,
) -> Result<()> {
    let mut cmd = runtime_cli_command("prefer-server");
    cmd.arg("--host")
        .arg(host)
        .arg("--port")
        .arg(port.to_string())
        .arg("--format")
        .arg(format);
    if install_client {
        cmd.arg("--install-client");
    } else {
        cmd.arg("--no-install-client");
    }
    if sign {
        cmd.arg("--sign");
    } else {
        cmd.arg("--no-sign");
    }
    run_python_cli(cmd, "Runtime prefer-server failed").await
}

pub async fn handle_runtime_status(format: String) -> Result<()> {
    let mut cmd = runtime_cli_command("status");
    cmd.arg("--format").arg(format);
    run_python_cli(cmd, "Runtime status failed").await
}

pub async fn handle_runtime_cleanup(format: String) -> Result<()> {
    let mut cmd = runtime_cli_command("cleanup");
    cmd.arg("--format").arg(format);
    run_python_cli(cmd, "Runtime cleanup failed").await
}

pub async fn handle_runtime_stop_local_server(port: u16) -> Result<()> {
    let mut cmd = runtime_cli_command("stop-local-server");
    cmd.arg("--port").arg(port.to_string());
    run_python_cli(cmd, "Runtime stop-local-server failed").await
}

fn runtime_cli_command(action: &str) -> Command {
    let mut cmd = python_cli_command();
    cmd.arg("runtime").arg(action);
    cmd
}

pub async fn handle_test_run_get(
    server: &str,
    client: &reqwest::Client,
    run_id: &str,
    include_output: bool,
    include_logs: bool,
    include_artifacts: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/test-runs/{}", server, run_id))
            .query(&[
                ("include_output", include_output.to_string()),
                ("include_logs", include_logs.to_string()),
                ("include_artifacts", include_artifacts.to_string()),
            ]),
        api_key,
    )
    .send()
    .await?;
    let run: serde_json::Value = resp.json().await?;
    println!("Test run: {}", run["id"].as_str().unwrap_or("-"));
    println!("  Success: {}", run["success"].as_bool().unwrap_or(false));
    Ok(())
}

pub async fn handle_test_run_retention(
    server: &str,
    client: &reqwest::Client,
    limit: Option<u32>,
    sort: Option<String>,
    project_id: Option<String>,
    org_id: Option<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = sort {
        params.push(("sort", value));
    }
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    if let Some(value) = org_id {
        params.push(("org_id", value));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/test-runs/retention", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let retention: serde_json::Value = resp.json().await?;
    println!(
        "Retention: total_runs={} total_bytes={}",
        retention["total_runs"].as_u64().unwrap_or(0),
        retention["total_bytes"].as_u64().unwrap_or(0)
    );
    Ok(())
}

pub async fn handle_test_run_prune(
    server: &str,
    client: &reqwest::Client,
    max_log_bytes: Option<u64>,
    max_artifact_bytes: Option<u64>,
    max_age_days: Option<u32>,
    dry_run: bool,
    project_id: Option<String>,
    org_id: Option<String>,
    use_policies: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = max_log_bytes {
        params.push(("max_log_bytes", value.to_string()));
    }
    if let Some(value) = max_artifact_bytes {
        params.push(("max_artifact_bytes", value.to_string()));
    }
    if let Some(value) = max_age_days {
        params.push(("max_age_days", value.to_string()));
    }
    params.push(("dry_run", dry_run.to_string()));
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    if let Some(value) = org_id {
        params.push(("org_id", value));
    }
    params.push(("use_policies", use_policies.to_string()));
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/test-runs/prune", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "Prune summary: runs_pruned={}",
        result["runs_pruned"].as_u64().unwrap_or(0)
    );
    Ok(())
}

pub async fn handle_retention_policy_list(
    server: &str,
    client: &reqwest::Client,
    scope_type: Option<String>,
    scope_id: Option<String>,
    include_archived: bool,
    limit: Option<u32>,
    offset: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = scope_type {
        params.push(("scope_type", value));
    }
    if let Some(value) = scope_id {
        params.push(("scope_id", value));
    }
    params.push(("include_archived", include_archived.to_string()));
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    if let Some(value) = offset {
        params.push(("offset", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/test-runs/retention/policies", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let items = result["items"].as_array().unwrap_or(&empty);
    println!("Retention policies ({}):", items.len());
    for item in items {
        println!(
            "  • {} ({}/{})",
            item["id"].as_str().unwrap_or("-"),
            item["scope_type"].as_str().unwrap_or("-"),
            item["scope_id"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_retention_policy_get(
    server: &str,
    client: &reqwest::Client,
    policy_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!(
            "{}/api/v1/test-runs/retention/policies/{}",
            server, policy_id
        )),
        api_key,
    )
    .send()
    .await?;
    let policy: serde_json::Value = resp.json().await?;
    println!(
        "Retention policy: {} ({}/{})",
        policy["id"].as_str().unwrap_or("-"),
        policy["scope_type"].as_str().unwrap_or("-"),
        policy["scope_id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_retention_policy_upsert(
    server: &str,
    client: &reqwest::Client,
    scope_type: &str,
    scope_id: &str,
    max_log_bytes: Option<u64>,
    max_artifact_bytes: Option<u64>,
    max_age_days: Option<u32>,
    notes: Option<&str>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    params.push(("scope_type", scope_type.to_string()));
    params.push(("scope_id", scope_id.to_string()));
    if let Some(value) = max_log_bytes {
        params.push(("max_log_bytes", value.to_string()));
    }
    if let Some(value) = max_artifact_bytes {
        params.push(("max_artifact_bytes", value.to_string()));
    }
    if let Some(value) = max_age_days {
        params.push(("max_age_days", value.to_string()));
    }
    if let Some(value) = notes {
        params.push(("notes", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/test-runs/retention/policies", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let policy: serde_json::Value = resp.json().await?;
    println!(
        "✓ Upserted retention policy: {}",
        policy["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_retention_policy_update(
    server: &str,
    client: &reqwest::Client,
    policy_id: &str,
    max_log_bytes: Option<u64>,
    max_artifact_bytes: Option<u64>,
    max_age_days: Option<u32>,
    notes: Option<&str>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = max_log_bytes {
        params.push(("max_log_bytes", value.to_string()));
    }
    if let Some(value) = max_artifact_bytes {
        params.push(("max_artifact_bytes", value.to_string()));
    }
    if let Some(value) = max_age_days {
        params.push(("max_age_days", value.to_string()));
    }
    if let Some(value) = notes {
        params.push(("notes", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .patch(format!(
                "{}/api/v1/test-runs/retention/policies/{}",
                server, policy_id
            ))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let policy: serde_json::Value = resp.json().await?;
    println!(
        "✓ Updated retention policy: {}",
        policy["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_retention_policy_archive(
    server: &str,
    client: &reqwest::Client,
    policy_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.post(format!(
            "{}/api/v1/test-runs/retention/policies/{}/archive",
            server, policy_id
        )),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Archived retention policy {}", policy_id);
    Ok(())
}

pub async fn handle_retention_policy_restore(
    server: &str,
    client: &reqwest::Client,
    policy_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!(
            "{}/api/v1/test-runs/retention/policies/{}/restore",
            server, policy_id
        )),
        api_key,
    )
    .send()
    .await?;
    let policy: serde_json::Value = resp.json().await?;
    println!(
        "✓ Restored retention policy: {}",
        policy["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_workflow_align(
    server: &str,
    client: &reqwest::Client,
    payload: serde_json::Value,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/workflow/align", server))
            .json(&payload),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "Workflow aligned: {} -> {}",
        result["from_state"].as_str().unwrap_or("-"),
        result["target_state"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_evidence_gate_create(
    server: &str,
    client: &reqwest::Client,
    req: CreateEvidenceGateRuleRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!("{}/api/v1/evidence/gates", server))
            .json(&req),
        api_key,
    )
    .send()
    .await?;
    let rule: serde_json::Value = resp.json().await?;
    println!(
        "✓ Created evidence gate rule: {}",
        rule["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_evidence_gate_list(
    server: &str,
    client: &reqwest::Client,
    workflow_id: &str,
    entity_type: &str,
    from_state: &str,
    to_state: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/evidence/gates", server))
            .query(&[
                ("workflow_id", workflow_id),
                ("entity_type", entity_type),
                ("from_state", from_state),
                ("to_state", to_state),
            ]),
        api_key,
    )
    .send()
    .await?;
    let rules: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let items = rules.as_array().unwrap_or(&empty);
    println!("Evidence gate rules ({}):", items.len());
    for item in items {
        println!(
            "  • {} -> {} ({})",
            item["from_state"].as_str().unwrap_or("-"),
            item["to_state"].as_str().unwrap_or("-"),
            item["evidence_type"].as_str().unwrap_or("-")
        );
    }
    Ok(())
}

pub async fn handle_evidence_gate_delete(
    server: &str,
    client: &reqwest::Client,
    rule_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    add_auth_header(
        client.delete(format!("{}/api/v1/evidence/gates/{}", server, rule_id)),
        api_key,
    )
    .send()
    .await?;
    println!("✓ Deleted evidence gate rule {}", rule_id);
    Ok(())
}

pub async fn handle_evidence_bundle_search(
    server: &str,
    client: &reqwest::Client,
    task_ids: Vec<String>,
    plan_id: Option<String>,
    status: Vec<String>,
    evidence_type: Vec<String>,
    created_from: Option<String>,
    created_to: Option<String>,
    include_evidence: bool,
    include_test_runs: bool,
    include_output: bool,
    include_logs: bool,
    include_artifacts: bool,
    limit: u32,
    offset: u32,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    for value in task_ids {
        params.push(("task_id", value));
    }
    if let Some(value) = plan_id {
        params.push(("plan_id", value));
    }
    for value in status {
        params.push(("status", value));
    }
    for value in evidence_type {
        params.push(("evidence_type", value));
    }
    if let Some(value) = created_from {
        params.push(("created_from", value));
    }
    if let Some(value) = created_to {
        params.push(("created_to", value));
    }
    params.push(("include_evidence", include_evidence.to_string()));
    params.push(("include_test_runs", include_test_runs.to_string()));
    params.push(("include_output", include_output.to_string()));
    params.push(("include_logs", include_logs.to_string()));
    params.push(("include_artifacts", include_artifacts.to_string()));
    params.push(("limit", limit.to_string()));
    params.push(("offset", offset.to_string()));

    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/evidence/bundles", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let total = result["total_count"].as_u64().unwrap_or(0);
    println!("Proof bundles: {}", total);
    Ok(())
}

pub async fn handle_transition_timeline(
    server: &str,
    client: &reqwest::Client,
    kind: &str,
    entity_type: &str,
    entity_id: &str,
    triggered_by: Option<String>,
    from_state: Option<String>,
    to_state: Option<String>,
    start_time: Option<String>,
    end_time: Option<String>,
    transition_type: Option<String>,
    labels: Vec<String>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = triggered_by {
        params.push(("triggered_by", value));
    }
    if let Some(value) = from_state {
        params.push(("from_state", value));
    }
    if let Some(value) = to_state {
        params.push(("to_state", value));
    }
    if let Some(value) = start_time {
        params.push(("start_time", value));
    }
    if let Some(value) = end_time {
        params.push(("end_time", value));
    }
    if let Some(value) = transition_type {
        params.push(("transition_type", value));
    }
    for value in labels {
        params.push(("label", value));
    }

    let url = match kind {
        "workflow" => format!(
            "{}/api/v1/transitions/workflow/{}/{}",
            server, entity_type, entity_id
        ),
        "status" => format!(
            "{}/api/v1/transitions/status/{}/{}",
            server, entity_type, entity_id
        ),
        _ => format!(
            "{}/api/v1/transitions/status/{}/{}",
            server, entity_type, entity_id
        ),
    };
    let resp = add_auth_header(client.get(url).query(&params), api_key)
        .send()
        .await?;
    let result: serde_json::Value = resp.json().await?;
    let transitions = result["transitions"]
        .as_array()
        .map(|items| items.len())
        .unwrap_or(0);
    println!("Transitions ({}): {}", kind, transitions);
    Ok(())
}

pub async fn handle_revision_diff(
    server: &str,
    client: &reqwest::Client,
    entity_type: &str,
    entity_id: &str,
    from_revision: u32,
    to_revision: u32,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .get(format!(
                "{}/api/v1/revisions/{}/{}/diff",
                server, entity_type, entity_id
            ))
            .query(&[
                ("from_revision", from_revision.to_string()),
                ("to_revision", to_revision.to_string()),
            ]),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let changes = result["changes"]
        .as_array()
        .map(|items| items.len())
        .unwrap_or(0);
    println!("Revision diff changes: {}", changes);
    Ok(())
}

pub async fn handle_revision_bundle(
    server: &str,
    client: &reqwest::Client,
    entity_type: &str,
    entity_id: &str,
    include_linked: bool,
    include_linked_history: bool,
    history_limit: u32,
    history_offset: u32,
    linked_limit: u32,
    linked_history_limit: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    params.push(("include_linked", include_linked.to_string()));
    params.push(("include_linked_history", include_linked_history.to_string()));
    params.push(("history_limit", history_limit.to_string()));
    params.push(("history_offset", history_offset.to_string()));
    params.push(("linked_limit", linked_limit.to_string()));
    if let Some(value) = linked_history_limit {
        params.push(("linked_history_limit", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .get(format!(
                "{}/api/v1/revisions/{}/{}/bundle",
                server, entity_type, entity_id
            ))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "Revision bundle: {} {}",
        result["entity_type"].as_str().unwrap_or("-"),
        result["entity_id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_work_snapshot(
    server: &str,
    client: &reqwest::Client,
    scope_type: &str,
    scope_id: &str,
    task_limit: u32,
    test_limit: u32,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .get(format!(
                "{}/api/v1/work-snapshots/{}/{}",
                server, scope_type, scope_id
            ))
            .query(&[
                ("task_limit", task_limit.to_string()),
                ("test_limit", test_limit.to_string()),
            ]),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "Work snapshot: {} {}",
        result["scope_type"].as_str().unwrap_or("-"),
        result["scope_id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_work_daily(
    server: &str,
    client: &reqwest::Client,
    scope_type: &str,
    scope_id: &str,
    task_limit: u32,
    test_limit: u32,
    queue_limit: u32,
    stale_days: u32,
    at_risk_days: u32,
    include_timeline: bool,
    timeline_limit: u32,
    include_history: bool,
    history_limit: u32,
    view: Option<String>,
    output_format: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params = vec![
        ("task_limit", task_limit.to_string()),
        ("test_limit", test_limit.to_string()),
        ("queue_limit", queue_limit.to_string()),
        ("stale_days", stale_days.to_string()),
        ("at_risk_days", at_risk_days.to_string()),
        ("include_timeline", include_timeline.to_string()),
        ("timeline_limit", timeline_limit.to_string()),
        ("include_history", include_history.to_string()),
        ("history_limit", history_limit.to_string()),
    ];
    if let Some(value) = view {
        params.push(("view", value));
    }
    let resp = add_auth_header(
        client
            .get(format!(
                "{}/api/v1/work-snapshots/{}/{}/daily",
                server, scope_type, scope_id
            ))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    if output_format == "json" {
        println!("{}", serde_json::to_string_pretty(&result)?);
        return Ok(());
    }
    let snapshot = &result["snapshot"];
    println!(
        "Daily Review ({})",
        snapshot["scope_type"].as_str().unwrap_or("-")
    );
    println!(
        "Scope: {} (ID: {})",
        snapshot["scope_name"].as_str().unwrap_or("unknown"),
        snapshot["scope_id"].as_str().unwrap_or("-")
    );
    let totals = &snapshot["totals"];
    println!(
        "Totals: projects {} | goals {} | objectives {} | tasks {} | blocked {}",
        totals["total_projects"].as_i64().unwrap_or(0),
        totals["total_goals"].as_i64().unwrap_or(0),
        totals["total_objectives"].as_i64().unwrap_or(0),
        totals["total_tasks"].as_i64().unwrap_or(0),
        totals["blocked_tasks"].as_i64().unwrap_or(0)
    );
    let next_actions = result["next_actions"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    println!("Next Actions: {}", next_actions.len());
    Ok(())
}

pub async fn handle_work_graph_report(
    server: &str,
    scope_type: String,
    scope: Option<String>,
    scope_id: Option<String>,
    task_limit: u32,
    goal_limit: u32,
    objective_limit: u32,
    plan_limit: u32,
    output_format: String,
    api_key: Option<&str>,
) -> Result<()> {
    if scope.is_some() && scope_id.is_some() {
        bail!("Use --scope or --scope-id, not both");
    }

    let mut cmd = python_cli_command();
    cmd.arg("work")
        .arg("graph-report")
        .arg("--scope-type")
        .arg(scope_type)
        .arg("--task-limit")
        .arg(task_limit.to_string())
        .arg("--goal-limit")
        .arg(goal_limit.to_string())
        .arg("--objective-limit")
        .arg(objective_limit.to_string())
        .arg("--plan-limit")
        .arg(plan_limit.to_string())
        .arg("--format")
        .arg(output_format)
        .env("PMS_SERVER_BASE_URL", server);
    if let Some(value) = scope {
        cmd.arg("--scope").arg(value);
    }
    if let Some(value) = scope_id {
        cmd.arg("--scope-id").arg(value);
    }
    if let Some(value) = api_key {
        cmd.env("PMS_API_KEY", value);
    }

    run_python_cli(cmd, "Work graph-report failed").await
}

pub async fn handle_work_snapshot_review(
    server: &str,
    client: &reqwest::Client,
    scope_type: &str,
    scope_id: &str,
    req: WorkSnapshotReviewRequest,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client
            .post(format!(
                "{}/api/v1/work-snapshots/{}/{}/review",
                server, scope_type, scope_id
            ))
            .json(&req),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    println!(
        "✓ Reviewed snapshot: {}",
        result["id"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_loop_list(
    server: &str,
    client: &reqwest::Client,
    project_id: Option<String>,
    include_ended: bool,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    params.push(("include_ended", include_ended.to_string()));
    if let Some(value) = project_id {
        params.push(("project_id", value));
    }
    let resp = add_auth_header(
        client
            .get(format!("{}/api/v1/agent-loops", server))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let items = result["items"].as_array().unwrap_or(&empty);
    println!("Agent loops ({}):", items.len());
    for item in items {
        println!(
            "  • {} - {} ({}/{})",
            item["id"].as_str().unwrap_or("-"),
            item["status"].as_str().unwrap_or("-"),
            item["iterations"].as_u64().unwrap_or(0),
            item["max_iterations"].as_u64().unwrap_or(0),
        );
    }
    Ok(())
}

pub async fn handle_loop_show(
    server: &str,
    client: &reqwest::Client,
    loop_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.get(format!("{}/api/v1/agent-loops/{}", server, loop_id)),
        api_key,
    )
    .send()
    .await?;
    let item: serde_json::Value = resp.json().await?;
    println!(
        "Loop: {} ({})",
        item["id"].as_str().unwrap_or("-"),
        item["status"].as_str().unwrap_or("-")
    );
    println!(
        "  Iterations: {}/{}",
        item["iterations"].as_u64().unwrap_or(0),
        item["max_iterations"].as_u64().unwrap_or(0)
    );
    println!(
        "  Stop reason: {}",
        item["stop_reason"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_loop_messages(
    server: &str,
    client: &reqwest::Client,
    loop_id: &str,
    limit: Option<u32>,
    api_key: Option<&str>,
) -> Result<()> {
    let mut params: Vec<(&str, String)> = Vec::new();
    if let Some(value) = limit {
        params.push(("limit", value.to_string()));
    }
    let resp = add_auth_header(
        client
            .get(format!(
                "{}/api/v1/agent-loops/{}/messages",
                server, loop_id
            ))
            .query(&params),
        api_key,
    )
    .send()
    .await?;
    let result: serde_json::Value = resp.json().await?;
    let empty: Vec<serde_json::Value> = Vec::new();
    let items = result["items"].as_array().unwrap_or(&empty);
    println!("Messages ({}):", items.len());
    for item in items {
        println!(
            "  • {}: {}",
            item["role"].as_str().unwrap_or("-"),
            item["content"].as_str().unwrap_or("")
        );
    }
    Ok(())
}

pub async fn handle_loop_cancel(
    server: &str,
    client: &reqwest::Client,
    loop_id: &str,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(
        client.post(format!("{}/api/v1/agent-loops/{}/cancel", server, loop_id)),
        api_key,
    )
    .send()
    .await?;
    let item: serde_json::Value = resp.json().await?;
    println!(
        "Cancelled loop: {} ({})",
        item["id"].as_str().unwrap_or("-"),
        item["status"].as_str().unwrap_or("-")
    );
    Ok(())
}

pub async fn handle_loop_run(
    prompt: Vec<String>,
    config: Option<String>,
    prompt_file: Option<String>,
    project: Option<String>,
    project_id: Option<String>,
    agent: Option<String>,
    agent_command: Option<String>,
    agent_args: Vec<String>,
    prompt_mode: String,
    max_iterations: Option<u32>,
    max_runtime: Option<u32>,
    completion_promise: Option<String>,
    completion_marker: Option<String>,
    retry_delay: Option<f64>,
    dry_run: bool,
) -> Result<()> {
    let mut cmd = python_cli_command();
    cmd.arg("loop").arg("run");

    if !prompt.is_empty() {
        cmd.args(prompt);
    }
    if let Some(value) = config {
        cmd.arg("--config").arg(value);
    }
    if let Some(value) = prompt_file {
        cmd.arg("--prompt-file").arg(value);
    }
    if let Some(value) = project {
        cmd.arg("--project").arg(value);
    }
    if let Some(value) = project_id {
        cmd.arg("--project-id").arg(value);
    }
    if let Some(value) = agent {
        cmd.arg("--agent").arg(value);
    }
    if let Some(value) = agent_command {
        cmd.arg("--agent-command").arg(value);
    }
    for arg in agent_args {
        cmd.arg("--agent-arg").arg(arg);
    }
    if !prompt_mode.is_empty() {
        cmd.arg("--prompt-mode").arg(prompt_mode);
    }
    if let Some(value) = max_iterations {
        cmd.arg("--max-iterations").arg(value.to_string());
    }
    if let Some(value) = max_runtime {
        cmd.arg("--max-runtime").arg(value.to_string());
    }
    if let Some(value) = completion_promise {
        cmd.arg("--completion-promise").arg(value);
    }
    if let Some(value) = completion_marker {
        cmd.arg("--completion-marker").arg(value);
    }
    if let Some(value) = retry_delay {
        cmd.arg("--retry-delay").arg(value.to_string());
    }
    if dry_run {
        cmd.arg("--dry-run");
    }

    run_python_cli(cmd, "Loop run failed").await
}

pub async fn handle_loop_init(config: String, prompt_file: String, force: bool) -> Result<()> {
    let mut cmd = python_cli_command();
    cmd.arg("loop")
        .arg("init")
        .arg("--config")
        .arg(config)
        .arg("--prompt-file")
        .arg(prompt_file);
    if force {
        cmd.arg("--force");
    }
    run_python_cli(cmd, "Loop init failed").await
}

pub async fn handle_loop_setup(
    defaults: bool,
    org: Option<String>,
    product: Option<String>,
    project: Option<String>,
    project_id: Option<String>,
    goal: Option<String>,
    goal_horizon: String,
    objective: Option<String>,
    criteria: Vec<String>,
    tasks: Vec<String>,
    config: String,
    prompt_file: String,
    force: bool,
    agent: String,
    completion_promise: String,
    run: bool,
    no_run: bool,
    assign_workflow: bool,
    no_assign_workflow: bool,
    workflow: String,
    initial_state: String,
) -> Result<()> {
    let mut cmd = python_cli_command();
    cmd.arg("loop").arg("setup");
    if defaults {
        cmd.arg("--defaults");
    }
    if let Some(value) = org {
        cmd.arg("--org").arg(value);
    }
    if let Some(value) = product {
        cmd.arg("--product").arg(value);
    }
    if let Some(value) = project {
        cmd.arg("--project").arg(value);
    }
    if let Some(value) = project_id {
        cmd.arg("--project-id").arg(value);
    }
    if let Some(value) = goal {
        cmd.arg("--goal").arg(value);
    }
    if !goal_horizon.is_empty() {
        cmd.arg("--goal-horizon").arg(goal_horizon);
    }
    if let Some(value) = objective {
        cmd.arg("--objective").arg(value);
    }
    for criterion in criteria {
        cmd.arg("--criterion").arg(criterion);
    }
    for task in tasks {
        cmd.arg("--task").arg(task);
    }
    cmd.arg("--config").arg(config);
    cmd.arg("--prompt-file").arg(prompt_file);
    if force {
        cmd.arg("--force");
    }
    if !agent.is_empty() {
        cmd.arg("--agent").arg(agent);
    }
    if !completion_promise.is_empty() {
        cmd.arg("--completion-promise").arg(completion_promise);
    }
    let should_run = if no_run { false } else { run };
    if should_run {
        cmd.arg("--run");
    }
    let should_assign = if no_assign_workflow {
        false
    } else {
        assign_workflow
    };
    if !should_assign {
        cmd.arg("--no-assign-workflow");
    }
    if !workflow.is_empty() {
        cmd.arg("--workflow").arg(workflow);
    }
    if !initial_state.is_empty() {
        cmd.arg("--initial-state").arg(initial_state);
    }

    run_python_cli(cmd, "Loop setup failed").await
}

pub async fn handle_loop_guard(
    project: Option<String>,
    project_id: Option<String>,
    goals: Vec<String>,
    goal_ids: Vec<String>,
    include_archived: bool,
    allow_no_goals: bool,
    hook: bool,
    format: Option<String>,
) -> Result<()> {
    let mut cmd = python_cli_command();
    cmd.arg("loop").arg("guard");
    if let Some(value) = project {
        cmd.arg("--project").arg(value);
    }
    if let Some(value) = project_id {
        cmd.arg("--project-id").arg(value);
    }
    for goal in goals {
        cmd.arg("--goal").arg(goal);
    }
    for goal_id in goal_ids {
        cmd.arg("--goal-id").arg(goal_id);
    }
    if include_archived {
        cmd.arg("--include-archived");
    }
    if allow_no_goals {
        cmd.arg("--allow-no-goals");
    }
    if hook {
        cmd.arg("--hook");
    }
    if let Some(value) = format {
        cmd.arg("--format").arg(value);
    }
    run_python_cli(cmd, "Loop guard failed").await
}

pub async fn handle_loop_prompt_template(
    project: Option<String>,
    project_id: Option<String>,
    goal: Option<String>,
    goal_id: Option<String>,
    objective: Option<String>,
    objective_id: Option<String>,
    plan: Option<String>,
    plan_id: Option<String>,
    prompt_file: String,
    force: bool,
    stdout: bool,
    no_write: bool,
    task_limit: Option<u32>,
    keyresult_limit: Option<u32>,
    pick: bool,
) -> Result<()> {
    let mut cmd = python_cli_command();
    cmd.arg("loop")
        .arg("prompt-template")
        .arg("--prompt-file")
        .arg(prompt_file);
    if let Some(value) = project {
        cmd.arg("--project").arg(value);
    }
    if let Some(value) = project_id {
        cmd.arg("--project-id").arg(value);
    }
    if let Some(value) = goal {
        cmd.arg("--goal").arg(value);
    }
    if let Some(value) = goal_id {
        cmd.arg("--goal-id").arg(value);
    }
    if let Some(value) = objective {
        cmd.arg("--objective").arg(value);
    }
    if let Some(value) = objective_id {
        cmd.arg("--objective-id").arg(value);
    }
    if let Some(value) = plan {
        cmd.arg("--plan").arg(value);
    }
    if let Some(value) = plan_id {
        cmd.arg("--plan-id").arg(value);
    }
    if force {
        cmd.arg("--force");
    }
    if stdout {
        cmd.arg("--stdout");
    }
    if no_write {
        cmd.arg("--no-write");
    }
    if let Some(value) = task_limit {
        cmd.arg("--task-limit").arg(value.to_string());
    }
    if let Some(value) = keyresult_limit {
        cmd.arg("--keyresult-limit").arg(value.to_string());
    }
    if pick {
        cmd.arg("--pick");
    }

    run_python_cli(cmd, "Loop prompt-template failed").await
}

pub async fn handle_dashboard(
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    let resp = add_auth_header(client.get(format!("{}/dashboard", server)), api_key)
        .send()
        .await?;
    let body = resp.text().await.unwrap_or_default();
    println!("Dashboard HTML bytes: {}", body.len());
    Ok(())
}
