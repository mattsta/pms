use anyhow::Result;
use clap::Parser;
use pms_client::client::PMSClient;
use serde_json::json;

#[derive(Parser, Debug)]
struct Args {
    #[arg(long)]
    server: String,
    #[arg(long)]
    api_key: Option<String>,
    #[arg(long)]
    org_id: String,
    #[arg(long)]
    portfolio_id: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();
    let client = PMSClient::new(args.server, args.api_key);

    let payload = json!({
        "dashboard": client.get_dashboard().await?,
        "dashboard_html": client.get_dashboard_html().await?,
        "organization_dashboard": client
            .get_organization_dashboard(None, Some(100), Some(0))
            .await?,
        "portfolio_dashboard": client
            .get_portfolio_dashboard(None, Some(args.org_id.as_str()), Some(100), Some(0))
            .await?,
        "program_dashboard": client
            .get_program_dashboard(
                None,
                Some(args.org_id.as_str()),
                Some(args.portfolio_id.as_str()),
                Some(100),
                Some(0),
            )
            .await?,
    });

    println!("{}", serde_json::to_string(&payload)?);
    Ok(())
}
