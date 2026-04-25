use anyhow::{anyhow, Result};
use clap::Parser;
use pms_client::client::{PMSClient, TaskList};
use serde_json::{json, Value};

#[derive(Parser, Debug)]
struct Args {
    #[arg(long)]
    server: String,
    #[arg(long)]
    api_key: Option<String>,
    #[arg(long)]
    project_id: String,
    #[arg(long)]
    active_task_id: String,
}

fn normalize_task_list(list: TaskList) -> Value {
    json!({
        "items": list.items.into_iter().map(|task| {
            json!({
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "parent_id": task.parent_id,
                "complexity_points": task.complexity_points,
            })
        }).collect::<Vec<_>>(),
        "total_count": list.total_count,
        "limit": list.limit,
        "offset": list.offset,
    })
}

fn normalize_plan_list(value: Value) -> Result<Value> {
    let items = value
        .get("items")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("plan list probe payload missing items array"))?;
    Ok(json!({
        "items": items.iter().map(|plan| {
            let task_ids = plan
                .get("task_ids")
                .and_then(Value::as_array)
                .map(|raw_ids| {
                    raw_ids
                        .iter()
                        .filter_map(Value::as_str)
                        .map(str::to_owned)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            json!({
                "id": plan.get("id").and_then(Value::as_str).unwrap_or_default(),
                "name": plan.get("name").and_then(Value::as_str).unwrap_or_default(),
                "status": plan.get("status").and_then(Value::as_str).unwrap_or_default(),
                "task_ids": task_ids,
            })
        }).collect::<Vec<_>>(),
        "total_count": value.get("total_count").and_then(Value::as_u64).unwrap_or(items.len() as u64),
        "limit": value.get("limit").and_then(Value::as_u64).unwrap_or(0),
        "offset": value.get("offset").and_then(Value::as_u64).unwrap_or(0),
    }))
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();
    let client = PMSClient::new(args.server, args.api_key);

    let payload = json!({
        "task_project_page": normalize_task_list(
            client
                .list_tasks(Some(args.project_id.as_str()), None, Some(2), Some(1))
                .await?,
        ),
        "task_status_in_progress": normalize_task_list(
            client
                .list_tasks(
                    Some(args.project_id.as_str()),
                    Some("in_progress"),
                    Some(10),
                    Some(0),
                )
                .await?,
        ),
        "plan_project_page": normalize_plan_list(
            client
                .list_plans(
                    None,
                    Some(args.project_id.as_str()),
                    None,
                    None,
                    None,
                    None,
                    Some(1),
                    Some(1),
                )
                .await?,
        )?,
        "plan_task_filter": normalize_plan_list(
            client
                .list_plans(
                    None,
                    None,
                    None,
                    None,
                    None,
                    Some(args.active_task_id.as_str()),
                    Some(10),
                    Some(0),
                )
                .await?,
        )?,
    });

    println!("{}", serde_json::to_string(&payload)?);
    Ok(())
}
