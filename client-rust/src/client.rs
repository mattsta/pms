// Complete PMS HTTP client implementation

use anyhow::Result;
pub use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::time::Duration;

pub struct PMSClient {
    client: reqwest::Client,
    base_url: String,
    api_key: Option<String>,
}

pub(crate) fn task_list_query_params(
    project_id: Option<&str>,
    status: Option<&str>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Vec<(&'static str, String)> {
    let mut params: Vec<(&'static str, String)> = Vec::new();
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
    let mut params: Vec<(&'static str, String)> = Vec::new();
    if let Some(value) = status {
        params.push(("status", value.to_string()));
    }
    if let Some(value) = project_id {
        params.push(("project_id", value.to_string()));
    }
    if let Some(value) = product_id {
        params.push(("product_id", value.to_string()));
    }
    if let Some(value) = goal_id {
        params.push(("goal_id", value.to_string()));
    }
    if let Some(value) = objective_id {
        params.push(("objective_id", value.to_string()));
    }
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

impl PMSClient {
    pub fn new(base_url: String, api_key: Option<String>) -> Self {
        let client = reqwest::Client::builder()
            .no_proxy()
            .timeout(Duration::from_secs(30))
            .pool_max_idle_per_host(100)
            .build()
            .unwrap();

        Self {
            client,
            base_url,
            api_key,
        }
    }

    fn headers(&self) -> reqwest::header::HeaderMap {
        let mut headers = reqwest::header::HeaderMap::new();
        if let Some(key) = &self.api_key {
            headers.insert("X-API-Key", key.parse().unwrap());
        }
        headers.insert("Content-Type", "application/json".parse().unwrap());
        headers
    }

    // ============================================================
    // Actors (5 endpoints)
    // ============================================================

    pub async fn create_actor(&self, req: CreateActorRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/actors", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_actors(
        &self,
        kind: Option<&str>,
        status: Option<&str>,
        limit: u32,
        offset: u32,
    ) -> Result<Value> {
        let mut params = vec![("limit", limit.to_string()), ("offset", offset.to_string())];
        if let Some(kind) = kind {
            params.push(("kind", kind.to_string()));
        }
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/actors", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_actor(
        &self,
        actor: &str,
        include_inherited: bool,
        task_limit: u32,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/actors/{}", self.base_url, actor))
            .headers(self.headers())
            .query(&[
                ("include_inherited", include_inherited.to_string()),
                ("task_limit", task_limit.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn add_actor_alias(
        &self,
        actor: &str,
        req: CreateActorAliasRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/actors/{}/aliases", self.base_url, actor))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn add_actor_membership(
        &self,
        actor: &str,
        req: CreateActorMembershipRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/actors/{}/memberships",
                self.base_url, actor
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Auth and API Keys (7 endpoints)
    // ============================================================

    pub async fn list_scopes(&self) -> Result<ScopesResponse> {
        let resp = self
            .client
            .get(format!("{}/api/v1/auth/scopes", self.base_url))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_discoverability_graph(
        &self,
        include_entry_points: bool,
        include_observability: bool,
        include_scenarios: bool,
        max_next_steps: u32,
        path_contains: Option<&str>,
    ) -> Result<Value> {
        let mut params = vec![
            ("include_entry_points", include_entry_points.to_string()),
            ("include_observability", include_observability.to_string()),
            ("include_scenarios", include_scenarios.to_string()),
            ("max_next_steps", max_next_steps.to_string()),
        ];
        if let Some(path_contains) = path_contains {
            params.push(("path_contains", path_contains.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/discoverability/graph", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_observability_overview(
        &self,
        include_rollups: bool,
        include_queues: bool,
        include_lineage: bool,
        include_retention: bool,
        include_event_timeline: bool,
        queue_limit: u32,
        lineage_limit: u32,
        retention_limit: u32,
        timeline_days: u32,
    ) -> Result<Value> {
        let params = vec![
            ("include_rollups", include_rollups.to_string()),
            ("include_queues", include_queues.to_string()),
            ("include_lineage", include_lineage.to_string()),
            ("include_retention", include_retention.to_string()),
            ("include_event_timeline", include_event_timeline.to_string()),
            ("queue_limit", queue_limit.to_string()),
            ("lineage_limit", lineage_limit.to_string()),
            ("retention_limit", retention_limit.to_string()),
            ("timeline_days", timeline_days.to_string()),
        ];

        let resp = self
            .client
            .get(format!("{}/api/v1/observability/overview", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_project_operator_overview(
        &self,
        project_id: &str,
        task_limit: u32,
        test_limit: u32,
        queue_limit: u32,
        lineage_limit: u32,
        history_limit: u32,
        include_timeline: bool,
        include_history: bool,
        include_linked_history: bool,
        view: &str,
    ) -> Result<Value> {
        let params = vec![
            ("task_limit", task_limit.to_string()),
            ("test_limit", test_limit.to_string()),
            ("queue_limit", queue_limit.to_string()),
            ("lineage_limit", lineage_limit.to_string()),
            ("history_limit", history_limit.to_string()),
            ("include_timeline", include_timeline.to_string()),
            ("include_history", include_history.to_string()),
            ("include_linked_history", include_linked_history.to_string()),
            ("view", view.to_string()),
        ];

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/projects/{}/operator-overview",
                self.base_url, project_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn init_admin_key(&self, req: InitApiKeyRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/auth/init", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn create_api_key(&self, req: CreateApiKeyRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/auth/keys", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_api_keys(
        &self,
        include_inactive: bool,
        include_archived: bool,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/auth/keys", self.base_url))
            .headers(self.headers())
            .query(&[
                ("include_inactive", include_inactive.to_string()),
                ("include_archived", include_archived.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_api_key(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/auth/keys/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn deactivate_api_key(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/auth/keys/{}/deactivate",
                self.base_url, id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_api_key(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/auth/keys/{}/restore", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_api_key(&self, id: &str) -> Result<()> {
        self.client
            .delete(format!("{}/api/v1/auth/keys/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;
        Ok(())
    }

    // ============================================================
    // Products (6 endpoints)
    // ============================================================

    pub async fn create_product(&self, req: CreateProductRequest) -> Result<Product> {
        let resp = self
            .client
            .post(format!("{}/api/v1/products", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_products(&self) -> Result<ProductList> {
        let resp = self
            .client
            .get(format!("{}/api/v1/products", self.base_url))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_product(&self, id: &str) -> Result<Product> {
        let resp = self
            .client
            .get(format!("{}/api/v1/products/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_product_summary(&self, id: &str) -> Result<ProductSummary> {
        let resp = self
            .client
            .get(format!("{}/api/v1/products/{}/summary", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_product(
        &self,
        product_id: &str,
        req: UpdateProductRequest,
    ) -> Result<Product> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/products/{}", self.base_url, product_id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Organizations (6 endpoints)
    // ============================================================

    pub async fn create_organization(
        &self,
        req: CreateOrganizationRequest,
    ) -> Result<Organization> {
        let resp = self
            .client
            .post(format!("{}/api/v1/organizations", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_organizations(
        &self,
        status: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<OrganizationList> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
        let resp = self
            .client
            .get(format!("{}/api/v1/organizations{}", self.base_url, query))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_organization(&self, id: &str) -> Result<Organization> {
        let resp = self
            .client
            .get(format!("{}/api/v1/organizations/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_organization(
        &self,
        id: &str,
        req: UpdateOrganizationRequest,
    ) -> Result<Organization> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/organizations/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_organization_summary(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/organizations/{}/summary",
                self.base_url, id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_organization_dashboard(
        &self,
        status: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
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

    // ============================================================
    // Teams (4 endpoints)
    // ============================================================

    pub async fn create_team(&self, req: CreateTeamRequest) -> Result<Team> {
        let resp = self
            .client
            .post(format!("{}/api/v1/teams", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_teams(
        &self,
        status: Option<&str>,
        org_id: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<TeamList> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(org_id) = org_id {
            params.push(("org_id", org_id.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
        let resp = self
            .client
            .get(format!("{}/api/v1/teams{}", self.base_url, query))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_team(&self, id: &str) -> Result<Team> {
        let resp = self
            .client
            .get(format!("{}/api/v1/teams/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_team(&self, id: &str, req: UpdateTeamRequest) -> Result<Team> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/teams/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Portfolios (6 endpoints)
    // ============================================================

    pub async fn create_portfolio(&self, req: CreatePortfolioRequest) -> Result<Portfolio> {
        let resp = self
            .client
            .post(format!("{}/api/v1/portfolios", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_portfolios(
        &self,
        status: Option<&str>,
        org_id: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<PortfolioList> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(org_id) = org_id {
            params.push(("org_id", org_id.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
        let resp = self
            .client
            .get(format!("{}/api/v1/portfolios{}", self.base_url, query))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_portfolio(&self, id: &str) -> Result<Portfolio> {
        let resp = self
            .client
            .get(format!("{}/api/v1/portfolios/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_portfolio(
        &self,
        id: &str,
        req: UpdatePortfolioRequest,
    ) -> Result<Portfolio> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/portfolios/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_portfolio_summary(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/portfolios/{}/summary",
                self.base_url, id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_portfolio_dashboard(
        &self,
        status: Option<&str>,
        org_id: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(org_id) = org_id {
            params.push(("org_id", org_id.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
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

    // ============================================================
    // Programs (6 endpoints)
    // ============================================================

    pub async fn create_program(&self, req: CreateProgramRequest) -> Result<Program> {
        let resp = self
            .client
            .post(format!("{}/api/v1/programs", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_programs(
        &self,
        status: Option<&str>,
        org_id: Option<&str>,
        portfolio_id: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<ProgramList> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(org_id) = org_id {
            params.push(("org_id", org_id.to_string()));
        }
        if let Some(portfolio_id) = portfolio_id {
            params.push(("portfolio_id", portfolio_id.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
        let resp = self
            .client
            .get(format!("{}/api/v1/programs{}", self.base_url, query))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_program(&self, id: &str) -> Result<Program> {
        let resp = self
            .client
            .get(format!("{}/api/v1/programs/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_program(&self, id: &str, req: UpdateProgramRequest) -> Result<Program> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/programs/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_program_summary(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/programs/{}/summary", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_program_dashboard(
        &self,
        status: Option<&str>,
        org_id: Option<&str>,
        portfolio_id: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(org_id) = org_id {
            params.push(("org_id", org_id.to_string()));
        }
        if let Some(portfolio_id) = portfolio_id {
            params.push(("portfolio_id", portfolio_id.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
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

    // ============================================================
    // Projects (5 endpoints)
    // ============================================================

    pub async fn create_project(&self, req: CreateProjectRequest) -> Result<Project> {
        let resp = self
            .client
            .post(format!("{}/api/v1/projects", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_projects(
        &self,
        status: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<ProjectList> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
        let resp = self
            .client
            .get(format!("{}/api/v1/projects{}", self.base_url, query))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_project(&self, id: &str) -> Result<Project> {
        let resp = self
            .client
            .get(format!("{}/api/v1/projects/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_project_summary(&self, id: &str) -> Result<ProjectSummary> {
        let resp = self
            .client
            .get(format!("{}/api/v1/projects/{}/summary", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_project(&self, id: &str, req: UpdateProjectRequest) -> Result<Project> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/projects/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Goals (9 endpoints)
    // ============================================================

    pub async fn create_goal(&self, req: CreateGoalRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/goals", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_goals(
        &self,
        status: Option<&str>,
        horizon: Option<&str>,
        product_id: Option<&str>,
        project_id: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(horizon) = horizon {
            params.push(("horizon", horizon.to_string()));
        }
        if let Some(product_id) = product_id {
            params.push(("product_id", product_id.to_string()));
        }
        if let Some(project_id) = project_id {
            params.push(("project_id", project_id.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
        let resp = self
            .client
            .get(format!("{}/api/v1/goals{}", self.base_url, query))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_goal(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/goals/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_goal(&self, id: &str, req: UpdateGoalRequest) -> Result<Value> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/goals/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn complete_goal(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/goals/{}/complete", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn archive_goal(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/goals/{}/archive", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_goal_summary(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/goals/{}/summary", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn assign_goal_workflow(
        &self,
        goal_id: &str,
        workflow_name: &str,
        initial_state: &str,
    ) -> Result<Value> {
        let body = serde_json::json!({
            "workflow_name": workflow_name,
            "initial_state": initial_state
        });
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/goals/{}/workflow/assign",
                self.base_url, goal_id
            ))
            .headers(self.headers())
            .json(&body)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn transition_goal_workflow(
        &self,
        goal_id: &str,
        to_state: &str,
        by: &str,
        reason: Option<&str>,
        approved_by: Option<&str>,
    ) -> Result<Value> {
        let body = serde_json::json!({
            "to_state": to_state,
            "triggered_by": by,
            "reason": reason,
            "approved_by": approved_by
        });
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/goals/{}/workflow/transition",
                self.base_url, goal_id
            ))
            .headers(self.headers())
            .json(&body)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Objectives (9 endpoints)
    // ============================================================

    pub async fn create_objective(
        &self,
        goal_id: &str,
        req: CreateObjectiveRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/goals/{}/objectives",
                self.base_url, goal_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_objectives(
        &self,
        goal_id: &str,
        status: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/goals/{}/objectives{}",
                self.base_url, goal_id, query
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_objective(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/objectives/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_objective(&self, id: &str, req: UpdateObjectiveRequest) -> Result<Value> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/objectives/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn complete_objective(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/objectives/{}/complete",
                self.base_url, id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn archive_objective(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/objectives/{}/archive",
                self.base_url, id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn assign_objective_workflow(
        &self,
        objective_id: &str,
        workflow_name: &str,
        initial_state: &str,
    ) -> Result<Value> {
        let body = serde_json::json!({
            "workflow_name": workflow_name,
            "initial_state": initial_state
        });
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/objectives/{}/workflow/assign",
                self.base_url, objective_id
            ))
            .headers(self.headers())
            .json(&body)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn transition_objective_workflow(
        &self,
        objective_id: &str,
        to_state: &str,
        by: &str,
        reason: Option<&str>,
        approved_by: Option<&str>,
    ) -> Result<Value> {
        let body = serde_json::json!({
            "to_state": to_state,
            "triggered_by": by,
            "reason": reason,
            "approved_by": approved_by
        });
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/objectives/{}/workflow/transition",
                self.base_url, objective_id
            ))
            .headers(self.headers())
            .json(&body)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Key Results (6 endpoints)
    // ============================================================

    pub async fn create_key_result(
        &self,
        objective_id: &str,
        req: CreateKeyResultRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/objectives/{}/key-results",
                self.base_url, objective_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_key_results(
        &self,
        objective_id: &str,
        status: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params = vec![];
        if let Some(status) = status {
            params.push(("status", status.to_string()));
        }
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/objectives/{}/key-results{}",
                self.base_url, objective_id, query
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_key_result(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/key-results/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_key_result(&self, id: &str, req: UpdateKeyResultRequest) -> Result<Value> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/key-results/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn complete_key_result(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/key-results/{}/complete",
                self.base_url, id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn archive_key_result(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/key-results/{}/archive",
                self.base_url, id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Labels (13 endpoints)
    // ============================================================

    pub async fn create_label_category(&self, req: CreateLabelCategoryRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/labels/categories", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_label_categories(&self, include_archived: bool) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/labels/categories", self.base_url))
            .headers(self.headers())
            .query(&[("include_archived", include_archived.to_string())])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_label_category(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/labels/categories/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_label_category(
        &self,
        id: &str,
        req: UpdateLabelCategoryRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/labels/categories/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_label_category(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .delete(format!("{}/api/v1/labels/categories/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_label_category(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/labels/categories/{}/restore",
                self.base_url, id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn create_label(&self, req: CreateLabelRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/labels", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_labels(
        &self,
        category_id: Option<&str>,
        include_archived: bool,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/labels", self.base_url))
            .headers(self.headers())
            .query(&[
                ("category_id", category_id.unwrap_or("").to_string()),
                ("include_archived", include_archived.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_label(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/labels/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_label(&self, id: &str, req: UpdateLabelRequest) -> Result<Value> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/labels/{}", self.base_url, id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_label(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .delete(format!("{}/api/v1/labels/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_label(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/labels/{}/restore", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn assign_label(&self, req: CreateLabelAssignmentRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/labels/assignments", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_label_assignments(
        &self,
        entity_type: &str,
        entity_id: &str,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params = vec![
            ("entity_type", entity_type.to_string()),
            ("entity_id", entity_id.to_string()),
        ];
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let resp = self
            .client
            .get(format!("{}/api/v1/labels/assignments", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_label_assignment_history(
        &self,
        assignment_id: &str,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params = vec![];
        if let Some(limit) = limit {
            params.push(("limit", limit.to_string()));
        }
        if let Some(offset) = offset {
            params.push(("offset", offset.to_string()));
        }
        let query = if params.is_empty() {
            "".to_string()
        } else {
            format!(
                "?{}",
                params
                    .iter()
                    .map(|(k, v)| format!("{}={}", k, v))
                    .collect::<Vec<String>>()
                    .join("&")
            )
        };
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/labels/assignments/{}/history{}",
                self.base_url, assignment_id, query
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn remove_label_assignment(
        &self,
        entity_type: &str,
        entity_id: &str,
        label_id: &str,
    ) -> Result<Value> {
        let resp = self
            .client
            .delete(format!("{}/api/v1/labels/assignments", self.base_url))
            .headers(self.headers())
            .query(&[
                ("entity_type", entity_type),
                ("entity_id", entity_id),
                ("label_id", label_id),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn create_label_gate(&self, req: CreateLabelGateRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/labels/gates", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_label_gates(
        &self,
        workflow_id: &str,
        entity_type: &str,
        from_state: &str,
        to_state: &str,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/labels/gates", self.base_url))
            .headers(self.headers())
            .query(&[
                ("workflow_id", workflow_id),
                ("entity_type", entity_type),
                ("from_state", from_state),
                ("to_state", to_state),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_label_gate(&self, id: &str) -> Result<Value> {
        let resp = self
            .client
            .delete(format!("{}/api/v1/labels/gates/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Custom Fields (9 endpoints)
    // ============================================================

    pub async fn create_custom_field(&self, req: CreateCustomFieldRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/custom-fields", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_custom_fields(
        &self,
        entity_type: Option<&str>,
        include_archived: bool,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/custom-fields", self.base_url))
            .headers(self.headers())
            .query(&[
                ("entity_type", entity_type.unwrap_or("").to_string()),
                ("include_archived", include_archived.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_custom_field(&self, field_id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/custom-fields/{}",
                self.base_url, field_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_custom_field(
        &self,
        field_id: &str,
        req: UpdateCustomFieldRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .patch(format!(
                "{}/api/v1/custom-fields/{}",
                self.base_url, field_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_custom_field(&self, field_id: &str) -> Result<Value> {
        let resp = self
            .client
            .delete(format!(
                "{}/api/v1/custom-fields/{}",
                self.base_url, field_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_custom_field(&self, field_id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/custom-fields/{}/restore",
                self.base_url, field_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn set_custom_field_value(
        &self,
        field_id: &str,
        req: SetCustomFieldValueRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/custom-fields/{}/values",
                self.base_url, field_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_custom_field_values(
        &self,
        entity_type: &str,
        entity_id: &str,
        include_history: bool,
        limit: i32,
        offset: i32,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/custom-fields/values", self.base_url))
            .headers(self.headers())
            .query(&[
                ("entity_type", entity_type),
                ("entity_id", entity_id),
                ("include_history", &include_history.to_string()),
                ("limit", &limit.to_string()),
                ("offset", &offset.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_custom_field_values_for_field(
        &self,
        field_id: &str,
        limit: i32,
        offset: i32,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/custom-fields/{}/values",
                self.base_url, field_id
            ))
            .headers(self.headers())
            .query(&[
                ("limit", &limit.to_string()),
                ("offset", &offset.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Comments and Watchers (9 endpoints)
    // ============================================================

    pub async fn add_comment(&self, req: CreateCommentRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/comments", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_comments(
        &self,
        entity_type: &str,
        entity_id: &str,
        include_archived: bool,
        limit: i32,
        offset: i32,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/comments", self.base_url))
            .headers(self.headers())
            .query(&[
                ("entity_type", entity_type),
                ("entity_id", entity_id),
                ("include_archived", &include_archived.to_string()),
                ("limit", &limit.to_string()),
                ("offset", &offset.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_comment(&self, comment_id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/comments/{}", self.base_url, comment_id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_comment(&self, comment_id: &str) -> Result<Value> {
        let resp = self
            .client
            .delete(format!("{}/api/v1/comments/{}", self.base_url, comment_id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_comment(&self, comment_id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/comments/{}/restore",
                self.base_url, comment_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn add_watcher(&self, req: AddWatcherRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/watchers", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_watchers(
        &self,
        entity_type: &str,
        entity_id: &str,
        include_archived: bool,
        limit: i32,
        offset: i32,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/watchers", self.base_url))
            .headers(self.headers())
            .query(&[
                ("entity_type", entity_type),
                ("entity_id", entity_id),
                ("include_archived", &include_archived.to_string()),
                ("limit", &limit.to_string()),
                ("offset", &offset.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn remove_watcher(
        &self,
        entity_type: &str,
        entity_id: &str,
        watcher: &str,
    ) -> Result<Value> {
        let resp = self
            .client
            .delete(format!("{}/api/v1/watchers", self.base_url))
            .headers(self.headers())
            .query(&[
                ("entity_type", entity_type),
                ("entity_id", entity_id),
                ("watcher", watcher),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_watcher(&self, watcher_id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/watchers/{}/restore",
                self.base_url, watcher_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Automation rules (8 endpoints)
    // ============================================================

    pub async fn create_automation_rule(&self, req: CreateAutomationRuleRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/automation/rules", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_automation_rules(
        &self,
        include_archived: bool,
        enabled: Option<bool>,
    ) -> Result<Value> {
        let mut params = vec![("include_archived", include_archived.to_string())];
        if let Some(enabled) = enabled {
            params.push(("enabled", enabled.to_string()));
        }
        let resp = self
            .client
            .get(format!("{}/api/v1/automation/rules", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_automation_rule(&self, rule_id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/automation/rules/{}",
                self.base_url, rule_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_automation_rule(&self, rule_id: &str, payload: Value) -> Result<Value> {
        let resp = self
            .client
            .patch(format!(
                "{}/api/v1/automation/rules/{}",
                self.base_url, rule_id
            ))
            .headers(self.headers())
            .json(&payload)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_automation_rule(&self, rule_id: &str) -> Result<Value> {
        let resp = self
            .client
            .delete(format!(
                "{}/api/v1/automation/rules/{}",
                self.base_url, rule_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_automation_rule(&self, rule_id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/automation/rules/{}/restore",
                self.base_url, rule_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn run_automation_rules(&self, req: AutomationRuleRunRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/automation/run", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_automation_rule_runs(
        &self,
        rule_id: &str,
        limit: i32,
        offset: i32,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/automation/rules/{}/runs",
                self.base_url, rule_id
            ))
            .headers(self.headers())
            .query(&[
                ("limit", &limit.to_string()),
                ("offset", &offset.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Tasks (8 endpoints)
    // ============================================================

    pub async fn create_task(&self, req: CreateTaskRequest) -> Result<Task> {
        let resp = self
            .client
            .post(format!("{}/api/v1/tasks", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
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

    pub async fn get_task(&self, id: &str) -> Result<Task> {
        let resp = self
            .client
            .get(format!("{}/api/v1/tasks/{}", self.base_url, id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn start_task(
        &self,
        id: &str,
        req: Option<TaskActionRequest>,
    ) -> Result<StatusResponse> {
        let builder = self
            .client
            .post(format!("{}/api/v1/tasks/{}/start", self.base_url, id))
            .headers(self.headers());
        let resp = match req {
            Some(payload) => builder.json(&payload).send().await?,
            None => builder.send().await?,
        };

        Ok(resp.json().await?)
    }

    pub async fn complete_task(
        &self,
        id: &str,
        notes: Option<String>,
        req: Option<TaskActionRequest>,
    ) -> Result<StatusResponse> {
        let builder = self
            .client
            .post(format!("{}/api/v1/tasks/{}/complete", self.base_url, id))
            .headers(self.headers());
        let builder = if let Some(value) = notes.as_ref() {
            builder.query(&[("notes", value)])
        } else {
            builder
        };
        let resp = match req {
            Some(payload) => builder.json(&payload).send().await?,
            None => builder.send().await?,
        };

        Ok(resp.json().await?)
    }

    pub async fn block_task(
        &self,
        id: &str,
        req: Option<TaskActionRequest>,
    ) -> Result<StatusResponse> {
        let builder = self
            .client
            .post(format!("{}/api/v1/tasks/{}/block", self.base_url, id))
            .headers(self.headers());
        let resp = match req {
            Some(payload) => builder.json(&payload).send().await?,
            None => builder.send().await?,
        };

        Ok(resp.json().await?)
    }

    pub async fn unblock_task(
        &self,
        id: &str,
        req: Option<TaskActionRequest>,
    ) -> Result<StatusResponse> {
        let builder = self
            .client
            .post(format!("{}/api/v1/tasks/{}/unblock", self.base_url, id))
            .headers(self.headers());
        let resp = match req {
            Some(payload) => builder.json(&payload).send().await?,
            None => builder.send().await?,
        };

        Ok(resp.json().await?)
    }

    pub async fn review_task(
        &self,
        id: &str,
        req: Option<TaskActionRequest>,
    ) -> Result<StatusResponse> {
        let builder = self
            .client
            .post(format!("{}/api/v1/tasks/{}/review", self.base_url, id))
            .headers(self.headers());
        let resp = match req {
            Some(payload) => builder.json(&payload).send().await?,
            None => builder.send().await?,
        };

        Ok(resp.json().await?)
    }

    pub async fn reopen_task(
        &self,
        id: &str,
        req: Option<TaskActionRequest>,
    ) -> Result<StatusResponse> {
        let builder = self
            .client
            .post(format!("{}/api/v1/tasks/{}/reopen", self.base_url, id))
            .headers(self.headers());
        let resp = match req {
            Some(payload) => builder.json(&payload).send().await?,
            None => builder.send().await?,
        };

        Ok(resp.json().await?)
    }

    pub async fn cancel_task(
        &self,
        id: &str,
        req: Option<TaskActionRequest>,
    ) -> Result<StatusResponse> {
        let builder = self
            .client
            .post(format!("{}/api/v1/tasks/{}/cancel", self.base_url, id))
            .headers(self.headers());
        let resp = match req {
            Some(payload) => builder.json(&payload).send().await?,
            None => builder.send().await?,
        };

        Ok(resp.json().await?)
    }

    pub async fn update_task(&self, task_id: &str, req: UpdateTaskRequest) -> Result<Value> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/tasks/{}", self.base_url, task_id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn add_task_dependency(
        &self,
        task_id: &str,
        req: TaskDependencyCreateRequest,
    ) -> Result<TaskDependency> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/dependencies",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn remove_task_dependency(
        &self,
        task_id: &str,
        depends_on_id: &str,
    ) -> Result<StatusResponse> {
        let resp = self
            .client
            .delete(format!(
                "{}/api/v1/tasks/{}/dependencies/{}",
                self.base_url, task_id, depends_on_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_task_dependency_graph(&self, task_id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/tasks/{}/graph", self.base_url, task_id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_task_tree(
        &self,
        project_id: &str,
        root_task_id: Option<&str>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = vec![("project_id", project_id.to_string())];
        if let Some(value) = root_task_id {
            params.push(("root_task_id", value.to_string()));
        }
        let resp = self
            .client
            .get(format!("{}/api/v1/tasks/tree", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn search_tasks(
        &self,
        query: Option<&str>,
        project_id: Option<&str>,
        status: Option<Vec<String>>,
        priority: Option<Vec<String>>,
        assignee: Option<&str>,
        tags: Option<Vec<String>>,
        label_id: Option<Vec<String>>,
        label_category_id: Option<Vec<String>>,
        created_from: Option<&str>,
        created_to: Option<&str>,
        updated_from: Option<&str>,
        updated_to: Option<&str>,
        due_from: Option<&str>,
        due_to: Option<&str>,
        include_terminal: bool,
        sort_by: Option<&str>,
        sort_dir: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = query {
            params.push(("query", value.to_string()));
        }
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
        }
        if let Some(values) = status {
            for value in values {
                params.push(("status", value));
            }
        }
        if let Some(values) = priority {
            for value in values {
                params.push(("priority", value));
            }
        }
        if let Some(value) = assignee {
            params.push(("assignee", value.to_string()));
        }
        if let Some(values) = tags {
            for value in values {
                params.push(("tags", value));
            }
        }
        if let Some(values) = label_id {
            for value in values {
                params.push(("label_id", value));
            }
        }
        if let Some(values) = label_category_id {
            for value in values {
                params.push(("label_category_id", value));
            }
        }
        if let Some(value) = created_from {
            params.push(("created_from", value.to_string()));
        }
        if let Some(value) = created_to {
            params.push(("created_to", value.to_string()));
        }
        if let Some(value) = updated_from {
            params.push(("updated_from", value.to_string()));
        }
        if let Some(value) = updated_to {
            params.push(("updated_to", value.to_string()));
        }
        if let Some(value) = due_from {
            params.push(("due_from", value.to_string()));
        }
        if let Some(value) = due_to {
            params.push(("due_to", value.to_string()));
        }
        params.push(("include_terminal", include_terminal.to_string()));
        if let Some(value) = sort_by {
            params.push(("sort_by", value.to_string()));
        }
        if let Some(value) = sort_dir {
            params.push(("sort_dir", value.to_string()));
        }
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/tasks/search", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_ready_tasks(
        &self,
        project_id: Option<&str>,
        status: Option<Vec<String>>,
        exclude_checked_out: bool,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
        }
        if let Some(values) = status {
            for value in values {
                params.push(("status", value));
            }
        }
        params.push(("exclude_checked_out", exclude_checked_out.to_string()));
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/tasks/ready", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_stale_tasks(
        &self,
        project_id: Option<&str>,
        status: Option<Vec<String>>,
        stale_after_days: Option<u32>,
        updated_before: Option<&str>,
        include_terminal: bool,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
        }
        if let Some(values) = status {
            for value in values {
                params.push(("status", value));
            }
        }
        if let Some(value) = stale_after_days {
            params.push(("stale_after_days", value.to_string()));
        }
        if let Some(value) = updated_before {
            params.push(("updated_before", value.to_string()));
        }
        params.push(("include_terminal", include_terminal.to_string()));
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/tasks/stale", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_duplicate_tasks(
        &self,
        project_id: Option<&str>,
        status: Option<Vec<String>>,
        include_terminal: bool,
        min_count: Option<u32>,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
        }
        if let Some(values) = status {
            for value in values {
                params.push(("status", value));
            }
        }
        params.push(("include_terminal", include_terminal.to_string()));
        if let Some(value) = min_count {
            params.push(("min_count", value.to_string()));
        }
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/tasks/duplicates", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn preview_duplicate_merge(
        &self,
        req: DuplicateMergePreviewRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/tasks/duplicates/preview", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn merge_duplicate_tasks(&self, req: DuplicateMergeRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/tasks/duplicates/merge", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Checkout (4 endpoints)
    // ============================================================

    pub async fn checkout_task(
        &self,
        task_id: &str,
        agent_id: &str,
        lease: u32,
    ) -> Result<CheckoutResponse> {
        let body = serde_json::json!({
            "agent_session_id": agent_id,
            "lease_seconds": lease
        });

        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/checkout",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .json(&body)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn renew_checkout(&self, task_id: &str, agent_id: &str) -> Result<StatusResponse> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/checkout/renew?agent_session_id={}",
                self.base_url, task_id, agent_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn release_checkout(&self, task_id: &str, agent_id: &str) -> Result<StatusResponse> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/checkout/release?agent_session_id={}",
                self.base_url, task_id, agent_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_available_tasks(
        &self,
        project_id: Option<&str>,
    ) -> Result<AvailableTasksResponse> {
        let mut url = format!("{}/api/v1/checkout/available", self.base_url);
        if let Some(pid) = project_id {
            url = format!("{}?project_id={}", url, pid);
        }

        let resp = self.client.get(&url).headers(self.headers()).send().await?;
        Ok(resp.json().await?)
    }

    pub async fn get_checkout_status(
        &self,
        agent_session_id: &str,
        include_expired: bool,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/checkout/status", self.base_url))
            .headers(self.headers())
            .query(&[
                ("agent_session_id", agent_session_id.to_string()),
                ("include_expired", include_expired.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn add_task_evidence(
        &self,
        task_id: &str,
        req: TaskEvidenceCreateRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/evidence",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_task_evidence(
        &self,
        task_id: &str,
        include_test_runs: bool,
        include_output: bool,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        params.push(("include_test_runs", include_test_runs.to_string()));
        params.push(("include_output", include_output.to_string()));
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/tasks/{}/evidence",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_task_proof_bundle(
        &self,
        task_id: &str,
        include_output: bool,
        include_logs: bool,
        include_artifacts: bool,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/tasks/{}/proof-bundle",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .query(&[
                ("include_output", include_output.to_string()),
                ("include_logs", include_logs.to_string()),
                ("include_artifacts", include_artifacts.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn search_proof_bundles(
        &self,
        task_id: Option<Vec<String>>,
        plan_id: Option<&str>,
        status: Option<Vec<String>>,
        evidence_type: Option<Vec<String>>,
        created_from: Option<&str>,
        created_to: Option<&str>,
        include_evidence: bool,
        include_test_runs: bool,
        include_output: bool,
        include_logs: bool,
        include_artifacts: bool,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(values) = task_id {
            for value in values {
                params.push(("task_id", value));
            }
        }
        if let Some(value) = plan_id {
            params.push(("plan_id", value.to_string()));
        }
        if let Some(values) = status {
            for value in values {
                params.push(("status", value));
            }
        }
        if let Some(values) = evidence_type {
            for value in values {
                params.push(("evidence_type", value));
            }
        }
        if let Some(value) = created_from {
            params.push(("created_from", value.to_string()));
        }
        if let Some(value) = created_to {
            params.push(("created_to", value.to_string()));
        }
        params.push(("include_evidence", include_evidence.to_string()));
        params.push(("include_test_runs", include_test_runs.to_string()));
        params.push(("include_output", include_output.to_string()));
        params.push(("include_logs", include_logs.to_string()));
        params.push(("include_artifacts", include_artifacts.to_string()));
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/evidence/bundles", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn create_evidence_gate_rule(
        &self,
        req: CreateEvidenceGateRuleRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/evidence/gates", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_evidence_gate_rules(
        &self,
        workflow_id: &str,
        entity_type: &str,
        from_state: &str,
        to_state: &str,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/evidence/gates", self.base_url))
            .headers(self.headers())
            .query(&[
                ("workflow_id", workflow_id.to_string()),
                ("entity_type", entity_type.to_string()),
                ("from_state", from_state.to_string()),
                ("to_state", to_state.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_evidence_gate_rule(&self, rule_id: &str) -> Result<Value> {
        let resp = self
            .client
            .delete(format!(
                "{}/api/v1/evidence/gates/{}",
                self.base_url, rule_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_checkout_log(
        &self,
        task_id: Option<&str>,
        agent_session_id: Option<&str>,
        action: Option<&str>,
        success: Option<bool>,
        limit: Option<u32>,
        offset: Option<u32>,
        include_metadata: bool,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = task_id {
            params.push(("task_id", value.to_string()));
        }
        if let Some(value) = agent_session_id {
            params.push(("agent_session_id", value.to_string()));
        }
        if let Some(value) = action {
            params.push(("action", value.to_string()));
        }
        if let Some(value) = success {
            params.push(("success", value.to_string()));
        }
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }
        params.push(("include_metadata", include_metadata.to_string()));

        let resp = self
            .client
            .get(format!("{}/api/v1/checkout/log", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn cleanup_checkouts(&self, dry_run: bool) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/checkout/cleanup", self.base_url))
            .headers(self.headers())
            .query(&[("dry_run", dry_run.to_string())])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn force_release_checkout(
        &self,
        task_id: &str,
        released_by: Option<&str>,
        reason: Option<&str>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = released_by {
            params.push(("released_by", value.to_string()));
        }
        if let Some(value) = reason {
            params.push(("reason", value.to_string()));
        }

        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/checkout/force-release",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Progress (2 endpoints)
    // ============================================================

    pub async fn update_progress(
        &self,
        task_id: &str,
        percent: u8,
        message: &str,
        by: &str,
    ) -> Result<ProgressResponse> {
        let body = serde_json::json!({
            "percent_complete": percent,
            "status_message": message,
            "updated_by": by
        });

        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/progress",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .json(&body)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_progress_timeline(&self, task_id: &str) -> Result<ProgressTimeline> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/tasks/{}/progress/timeline",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Workflows (4 endpoints)
    // ============================================================

    pub async fn list_workflows(&self) -> Result<WorkflowList> {
        let resp = self
            .client
            .get(format!("{}/api/v1/workflows", self.base_url))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_workflow_detail(
        &self,
        workflow_ref: &str,
        view: Option<&str>,
    ) -> Result<Value> {
        let builder = self
            .client
            .get(format!(
                "{}/api/v1/workflows/{}",
                self.base_url, workflow_ref
            ))
            .headers(self.headers());
        let builder = if let Some(value) = view {
            builder.query(&[("view", value)])
        } else {
            builder
        };
        let resp = builder.send().await?;
        Ok(resp.json().await?)
    }

    pub async fn assign_workflow(
        &self,
        task_id: &str,
        workflow_name: &str,
        initial_state: &str,
    ) -> Result<StatusResponse> {
        let body = serde_json::json!({
            "workflow_name": workflow_name,
            "initial_state": initial_state
        });

        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/workflow/assign",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .json(&body)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn transition_workflow(
        &self,
        task_id: &str,
        to_state: &str,
        by: &str,
        reason: Option<&str>,
    ) -> Result<TransitionResponse> {
        let body = serde_json::json!({
            "to_state": to_state,
            "triggered_by": by,
            "reason": reason
        });

        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/workflow/transition",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .json(&body)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn align_workflow(&self, req: WorkflowAlignRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/workflow/align", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn align_task_workflow(
        &self,
        task_id: &str,
        req: WorkflowAlignRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/tasks/{}/workflow/align",
                self.base_url, task_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Transitions (2 endpoints)
    // ============================================================

    pub async fn get_workflow_timeline(
        &self,
        entity_type: &str,
        entity_id: &str,
        triggered_by: Option<&str>,
        from_state: Option<&str>,
        to_state: Option<&str>,
        start_time: Option<&str>,
        end_time: Option<&str>,
        transition_type: Option<&str>,
        label: Option<Vec<String>>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = triggered_by {
            params.push(("triggered_by", value.to_string()));
        }
        if let Some(value) = from_state {
            params.push(("from_state", value.to_string()));
        }
        if let Some(value) = to_state {
            params.push(("to_state", value.to_string()));
        }
        if let Some(value) = start_time {
            params.push(("start_time", value.to_string()));
        }
        if let Some(value) = end_time {
            params.push(("end_time", value.to_string()));
        }
        if let Some(value) = transition_type {
            params.push(("transition_type", value.to_string()));
        }
        if let Some(values) = label {
            for value in values {
                params.push(("label", value));
            }
        }

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/transitions/workflow/{}/{}",
                self.base_url, entity_type, entity_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_status_timeline(
        &self,
        entity_type: &str,
        entity_id: &str,
        triggered_by: Option<&str>,
        from_state: Option<&str>,
        to_state: Option<&str>,
        start_time: Option<&str>,
        end_time: Option<&str>,
        transition_type: Option<&str>,
        label: Option<Vec<String>>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = triggered_by {
            params.push(("triggered_by", value.to_string()));
        }
        if let Some(value) = from_state {
            params.push(("from_state", value.to_string()));
        }
        if let Some(value) = to_state {
            params.push(("to_state", value.to_string()));
        }
        if let Some(value) = start_time {
            params.push(("start_time", value.to_string()));
        }
        if let Some(value) = end_time {
            params.push(("end_time", value.to_string()));
        }
        if let Some(value) = transition_type {
            params.push(("transition_type", value.to_string()));
        }
        if let Some(values) = label {
            for value in values {
                params.push(("label", value));
            }
        }

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/transitions/status/{}/{}",
                self.base_url, entity_type, entity_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Revisions (2 endpoints)
    // ============================================================

    pub async fn diff_revisions(
        &self,
        entity_type: &str,
        entity_id: &str,
        from_revision: u32,
        to_revision: u32,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/revisions/{}/{}/diff",
                self.base_url, entity_type, entity_id
            ))
            .headers(self.headers())
            .query(&[
                ("from_revision", from_revision.to_string()),
                ("to_revision", to_revision.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_revision_bundle(
        &self,
        entity_type: &str,
        entity_id: &str,
        include_linked: bool,
        include_linked_history: bool,
        history_limit: Option<u32>,
        history_offset: Option<u32>,
        linked_limit: Option<u32>,
        linked_history_limit: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        params.push(("include_linked", include_linked.to_string()));
        params.push(("include_linked_history", include_linked_history.to_string()));
        if let Some(value) = history_limit {
            params.push(("history_limit", value.to_string()));
        }
        if let Some(value) = history_offset {
            params.push(("history_offset", value.to_string()));
        }
        if let Some(value) = linked_limit {
            params.push(("linked_limit", value.to_string()));
        }
        if let Some(value) = linked_history_limit {
            params.push(("linked_history_limit", value.to_string()));
        }

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/revisions/{}/{}/bundle",
                self.base_url, entity_type, entity_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Work Snapshots (3 endpoints)
    // ============================================================

    pub async fn get_work_snapshot(
        &self,
        scope_type: &str,
        scope_id: &str,
        task_limit: Option<u32>,
        test_limit: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = task_limit {
            params.push(("task_limit", value.to_string()));
        }
        if let Some(value) = test_limit {
            params.push(("test_limit", value.to_string()));
        }

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/work-snapshots/{}/{}",
                self.base_url, scope_type, scope_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Agent Loops (4 endpoints)
    // ============================================================

    pub async fn list_agent_loops(
        &self,
        project_id: Option<&str>,
        include_ended: bool,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        params.push(("include_ended", include_ended.to_string()));
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/agent-loops", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_agent_loop(&self, loop_id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/agent-loops/{}", self.base_url, loop_id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_agent_loop_messages(
        &self,
        loop_id: &str,
        limit: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/agent-loops/{}/messages",
                self.base_url, loop_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn cancel_agent_loop(&self, loop_id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/agent-loops/{}/cancel",
                self.base_url, loop_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_work_daily(
        &self,
        scope_type: &str,
        scope_id: &str,
        task_limit: Option<u32>,
        test_limit: Option<u32>,
        queue_limit: Option<u32>,
        stale_days: Option<u32>,
        at_risk_days: Option<u32>,
        include_timeline: Option<bool>,
        timeline_limit: Option<u32>,
        include_history: Option<bool>,
        history_limit: Option<u32>,
        view: Option<&str>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = task_limit {
            params.push(("task_limit", value.to_string()));
        }
        if let Some(value) = test_limit {
            params.push(("test_limit", value.to_string()));
        }
        if let Some(value) = queue_limit {
            params.push(("queue_limit", value.to_string()));
        }
        if let Some(value) = stale_days {
            params.push(("stale_days", value.to_string()));
        }
        if let Some(value) = at_risk_days {
            params.push(("at_risk_days", value.to_string()));
        }
        if let Some(value) = include_timeline {
            params.push(("include_timeline", value.to_string()));
        }
        if let Some(value) = timeline_limit {
            params.push(("timeline_limit", value.to_string()));
        }
        if let Some(value) = include_history {
            params.push(("include_history", value.to_string()));
        }
        if let Some(value) = history_limit {
            params.push(("history_limit", value.to_string()));
        }
        if let Some(value) = view {
            params.push(("view", value.to_string()));
        }

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/work-snapshots/{}/{}/daily",
                self.base_url, scope_type, scope_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn review_work_snapshot(
        &self,
        scope_type: &str,
        scope_id: &str,
        req: WorkSnapshotReviewRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/work-snapshots/{}/{}/review",
                self.base_url, scope_type, scope_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Dashboard (2 endpoints)
    // ============================================================

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

    // ============================================================
    // Plans (5 endpoints)
    // ============================================================

    pub async fn create_plan(&self, req: CreatePlanRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/plans", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
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

    pub async fn get_plan(&self, plan_id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/plans/{}", self.base_url, plan_id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_plan(&self, plan_id: &str, req: UpdatePlanRequest) -> Result<Value> {
        let resp = self
            .client
            .patch(format!("{}/api/v1/plans/{}", self.base_url, plan_id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_plan_lineage(
        &self,
        status: Option<&str>,
        project_id: Option<&str>,
        plan_id: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
        task_limit: Option<u32>,
        test_limit: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = status {
            params.push(("status", value.to_string()));
        }
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
        }
        if let Some(value) = plan_id {
            params.push(("plan_id", value.to_string()));
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

        let resp = self
            .client
            .get(format!("{}/api/v1/plans/lineage", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Plan Test Jobs (7 endpoints)
    // ============================================================

    pub async fn create_plan_test_job(
        &self,
        plan_id: &str,
        req: PlanTestJobCreateRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/plans/{}/test-jobs",
                self.base_url, plan_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_plan_test_jobs(
        &self,
        plan_id: &str,
        limit: Option<u32>,
        offset: Option<u32>,
        include_archived: bool,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }
        params.push(("include_archived", include_archived.to_string()));

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/plans/{}/test-jobs",
                self.base_url, plan_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_plan_test_job(&self, plan_id: &str, job_id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/plans/{}/test-jobs/{}",
                self.base_url, plan_id, job_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_plan_test_job(
        &self,
        plan_id: &str,
        job_id: &str,
        req: PlanTestJobUpdateRequest,
    ) -> Result<Value> {
        let resp = self
            .client
            .patch(format!(
                "{}/api/v1/plans/{}/test-jobs/{}",
                self.base_url, plan_id, job_id
            ))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_plan_test_job(&self, plan_id: &str, job_id: &str) -> Result<Value> {
        let resp = self
            .client
            .delete(format!(
                "{}/api/v1/plans/{}/test-jobs/{}",
                self.base_url, plan_id, job_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_plan_test_job(&self, plan_id: &str, job_id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/plans/{}/test-jobs/{}/restore",
                self.base_url, plan_id, job_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn run_plan_test_job(
        &self,
        plan_id: &str,
        job_id: &str,
        include_output: bool,
        include_logs: bool,
        include_artifacts: bool,
    ) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/plans/{}/test-jobs/{}/run",
                self.base_url, plan_id, job_id
            ))
            .headers(self.headers())
            .query(&[
                ("include_output", include_output.to_string()),
                ("include_logs", include_logs.to_string()),
                ("include_artifacts", include_artifacts.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Queues (8 endpoints)
    // ============================================================

    pub async fn create_queue(&self, req: CreateQueueRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/queues", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_queues(
        &self,
        owner: Option<&str>,
        scope_type: Option<&str>,
        scope_id: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
        include_archived: bool,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = owner {
            params.push(("owner", value.to_string()));
        }
        if let Some(value) = scope_type {
            params.push(("scope_type", value.to_string()));
        }
        if let Some(value) = scope_id {
            params.push(("scope_id", value.to_string()));
        }
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }
        params.push(("include_archived", include_archived.to_string()));

        let resp = self
            .client
            .get(format!("{}/api/v1/queues", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_queue_presets(
        &self,
        project_id: Option<&str>,
        limit: Option<u32>,
        stale_days: Option<u32>,
        at_risk_days: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
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

        let resp = self
            .client
            .get(format!("{}/api/v1/queues/presets", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_queue_preset(
        &self,
        preset: &str,
        project_id: Option<&str>,
        limit: Option<u32>,
        offset: Option<u32>,
        stale_days: Option<u32>,
        at_risk_days: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
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

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/queues/presets/{}",
                self.base_url, preset
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_queue(&self, queue_id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/queues/{}", self.base_url, queue_id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_queue(&self, queue_id: &str, req: UpdateQueueRequest) -> Result<Value> {
        let resp = self
            .client
            .put(format!("{}/api/v1/queues/{}", self.base_url, queue_id))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn delete_queue(&self, queue_id: &str) -> Result<Value> {
        let resp = self
            .client
            .delete(format!("{}/api/v1/queues/{}", self.base_url, queue_id))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_queue(&self, queue_id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/queues/{}/restore",
                self.base_url, queue_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn run_queue(
        &self,
        queue_id: &str,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/queues/{}/run", self.base_url, queue_id))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Test Runs (11 endpoints)
    // ============================================================

    pub async fn create_test_run(&self, req: CreateTestRunRequest) -> Result<Value> {
        let resp = self
            .client
            .post(format!("{}/api/v1/test-runs", self.base_url))
            .headers(self.headers())
            .json(&req)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_test_runs(
        &self,
        server_id: Option<&str>,
        project_id: Option<&str>,
        success: Option<bool>,
        include_output: bool,
        include_logs: bool,
        include_artifacts: bool,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = server_id {
            params.push(("server_id", value.to_string()));
        }
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
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

        let resp = self
            .client
            .get(format!("{}/api/v1/test-runs", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_test_run(
        &self,
        run_id: &str,
        include_output: bool,
        include_logs: bool,
        include_artifacts: bool,
    ) -> Result<Value> {
        let resp = self
            .client
            .get(format!("{}/api/v1/test-runs/{}", self.base_url, run_id))
            .headers(self.headers())
            .query(&[
                ("include_output", include_output.to_string()),
                ("include_logs", include_logs.to_string()),
                ("include_artifacts", include_artifacts.to_string()),
            ])
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_test_run_retention(
        &self,
        limit: Option<u32>,
        sort: Option<&str>,
        project_id: Option<&str>,
        org_id: Option<&str>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = sort {
            params.push(("sort", value.to_string()));
        }
        if let Some(value) = project_id {
            params.push(("project_id", value.to_string()));
        }
        if let Some(value) = org_id {
            params.push(("org_id", value.to_string()));
        }

        let resp = self
            .client
            .get(format!("{}/api/v1/test-runs/retention", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn prune_test_runs(
        &self,
        max_log_bytes: Option<u64>,
        max_artifact_bytes: Option<u64>,
        max_age_days: Option<u32>,
        dry_run: bool,
        project_id: Option<&str>,
        org_id: Option<&str>,
        use_policies: bool,
    ) -> Result<Value> {
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
            params.push(("project_id", value.to_string()));
        }
        if let Some(value) = org_id {
            params.push(("org_id", value.to_string()));
        }
        params.push(("use_policies", use_policies.to_string()));

        let resp = self
            .client
            .post(format!("{}/api/v1/test-runs/prune", self.base_url))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn list_retention_policies(
        &self,
        scope_type: Option<&str>,
        scope_id: Option<&str>,
        include_archived: bool,
        limit: Option<u32>,
        offset: Option<u32>,
    ) -> Result<Value> {
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(value) = scope_type {
            params.push(("scope_type", value.to_string()));
        }
        if let Some(value) = scope_id {
            params.push(("scope_id", value.to_string()));
        }
        params.push(("include_archived", include_archived.to_string()));
        if let Some(value) = limit {
            params.push(("limit", value.to_string()));
        }
        if let Some(value) = offset {
            params.push(("offset", value.to_string()));
        }

        let resp = self
            .client
            .get(format!(
                "{}/api/v1/test-runs/retention/policies",
                self.base_url
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn upsert_retention_policy(
        &self,
        scope_type: &str,
        scope_id: &str,
        max_log_bytes: Option<u64>,
        max_artifact_bytes: Option<u64>,
        max_age_days: Option<u32>,
        notes: Option<&str>,
    ) -> Result<Value> {
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

        let resp = self
            .client
            .post(format!(
                "{}/api/v1/test-runs/retention/policies",
                self.base_url
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn get_retention_policy(&self, policy_id: &str) -> Result<Value> {
        let resp = self
            .client
            .get(format!(
                "{}/api/v1/test-runs/retention/policies/{}",
                self.base_url, policy_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn update_retention_policy(
        &self,
        policy_id: &str,
        max_log_bytes: Option<u64>,
        max_artifact_bytes: Option<u64>,
        max_age_days: Option<u32>,
        notes: Option<&str>,
    ) -> Result<Value> {
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

        let resp = self
            .client
            .patch(format!(
                "{}/api/v1/test-runs/retention/policies/{}",
                self.base_url, policy_id
            ))
            .headers(self.headers())
            .query(&params)
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn archive_retention_policy(&self, policy_id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/test-runs/retention/policies/{}/archive",
                self.base_url, policy_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    pub async fn restore_retention_policy(&self, policy_id: &str) -> Result<Value> {
        let resp = self
            .client
            .post(format!(
                "{}/api/v1/test-runs/retention/policies/{}/restore",
                self.base_url, policy_id
            ))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }

    // ============================================================
    // Health (1 endpoint)
    // ============================================================

    pub async fn health_check(&self) -> Result<HealthResponse> {
        let resp = self
            .client
            .get(format!("{}/api/v1/health", self.base_url))
            .headers(self.headers())
            .send()
            .await?;

        Ok(resp.json().await?)
    }
}

// ============================================================
// Request Types
// ============================================================

#[derive(Serialize)]
pub struct CreateActorRequest {
    pub name: String,
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub handle: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub metadata: std::collections::HashMap<String, String>,
}

#[derive(Serialize)]
pub struct CreateActorAliasRequest {
    pub alias: String,
}

#[derive(Serialize)]
pub struct CreateActorMembershipRequest {
    pub member: String,
    pub role: String,
}

#[derive(Serialize)]
pub struct CreateProductRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub vision: Option<String>,
}

#[derive(Serialize)]
pub struct UpdateProductRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub vision: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub repository_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub product_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
}

#[derive(Serialize)]
pub struct CreateApiKeyRequest {
    pub name: String,
    pub scopes: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub expires_in_days: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rate_limit: Option<i32>,
    #[serde(default)]
    pub metadata: std::collections::HashMap<String, String>,
}

#[derive(Serialize)]
pub struct InitApiKeyRequest {
    pub name: String,
}

#[derive(Serialize)]
pub struct CreateOrganizationRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(default)]
    pub members: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
}

#[derive(Serialize)]
pub struct UpdateOrganizationRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub members: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
}

#[derive(Serialize)]
pub struct CreateTeamRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub org_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(default)]
    pub members: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
}

#[derive(Serialize)]
pub struct UpdateTeamRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub members: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
}

#[derive(Serialize)]
pub struct CreatePortfolioRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub org_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(default)]
    pub project_ids: Vec<String>,
    #[serde(default)]
    pub goal_ids: Vec<String>,
    #[serde(default)]
    pub objective_ids: Vec<String>,
    #[serde(default)]
    pub effective_goal_ids: Vec<String>,
    #[serde(default)]
    pub effective_objective_ids: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
}

#[derive(Serialize)]
pub struct UpdatePortfolioRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_ids: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub goal_ids: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub objective_ids: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
}

#[derive(Serialize)]
pub struct CreateProgramRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub org_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub portfolio_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(default)]
    pub project_ids: Vec<String>,
    #[serde(default)]
    pub goal_ids: Vec<String>,
    #[serde(default)]
    pub objective_ids: Vec<String>,
    #[serde(default)]
    pub effective_goal_ids: Vec<String>,
    #[serde(default)]
    pub effective_objective_ids: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
}

#[derive(Serialize)]
pub struct UpdateProgramRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_ids: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub goal_ids: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub objective_ids: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
}

#[derive(Serialize)]
pub struct CreateGoalRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    pub horizon: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_date: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub product_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_id: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub progress_percent: Option<i32>,
}

#[derive(Serialize)]
pub struct UpdateGoalRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub horizon: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_date: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub product_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub progress_percent: Option<i32>,
}

#[derive(Serialize)]
pub struct CreateObjectiveRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_date: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub progress_percent: Option<i32>,
}

#[derive(Serialize)]
pub struct UpdateObjectiveRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_date: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub progress_percent: Option<i32>,
}

#[derive(Serialize)]
pub struct CreateKeyResultRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_value: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_value: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub unit: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub progress_percent: Option<i32>,
}

#[derive(Serialize)]
pub struct UpdateKeyResultRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_value: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target_value: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub unit: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub progress_percent: Option<i32>,
}

#[derive(Serialize)]
pub struct CreateLabelCategoryRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_exclusive: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sort_order: Option<i32>,
}

#[derive(Serialize)]
pub struct UpdateLabelCategoryRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_exclusive: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sort_order: Option<i32>,
}

#[derive(Serialize)]
pub struct CreateLabelRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub category_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub color: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_system: Option<bool>,
}

#[derive(Serialize)]
pub struct UpdateLabelRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub category_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub color: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_system: Option<bool>,
}

#[derive(Serialize)]
pub struct CreateLabelAssignmentRequest {
    pub entity_type: String,
    pub entity_id: String,
    pub label_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub applied_by: Option<String>,
}

#[derive(Serialize)]
pub struct CreateLabelGateRequest {
    pub workflow_id: String,
    pub entity_type: String,
    pub from_state: String,
    pub to_state: String,
    pub rule_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub label_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub category_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

#[derive(Serialize)]
pub struct CreateCustomFieldRequest {
    pub name: String,
    pub entity_type: String,
    pub field_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub options: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_required: Option<bool>,
}

#[derive(Serialize)]
pub struct UpdateCustomFieldRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub field_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub options: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_required: Option<bool>,
}

#[derive(Serialize)]
pub struct SetCustomFieldValueRequest {
    pub entity_type: String,
    pub entity_id: String,
    pub value: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub created_by: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
}

#[derive(Serialize)]
pub struct CreateCommentRequest {
    pub entity_type: String,
    pub entity_id: String,
    pub body: String,
    pub created_by: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mentions: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub watch: Option<bool>,
}

#[derive(Serialize)]
pub struct AddWatcherRequest {
    pub entity_type: String,
    pub entity_id: String,
    pub watcher: String,
}

#[derive(Serialize)]
pub struct CreateAutomationRuleRequest {
    pub name: String,
    pub event_pattern: String,
    pub action_type: String,
    pub action_payload: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub aggregate_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub aggregate_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub enabled: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cooldown_seconds: Option<f64>,
}

#[derive(Serialize)]
pub struct AutomationRuleRunRequest {
    pub event_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rule_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dry_run: Option<bool>,
}

#[derive(Serialize)]
pub struct CreateProjectRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub org_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub portfolio_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub program_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub product_id: Option<String>,
}

#[derive(Serialize)]
pub struct UpdateProjectRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub org_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub portfolio_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub program_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub product_id: Option<String>,
}

#[derive(Serialize)]
pub struct CreateTaskRequest {
    pub project_id: String,
    pub title: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub complexity_points: Option<u8>,
    pub priority: String,
}

#[derive(Serialize)]
pub struct UpdateTaskRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub clear_parent: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub priority: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub complexity_points: Option<u8>,
}

#[derive(Serialize)]
pub struct TaskActionRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub updated_by: Option<String>,
}

#[derive(Serialize)]
pub struct TaskDependencyCreateRequest {
    pub depends_on_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dependency_type: Option<String>,
}

#[derive(Serialize)]
pub struct TaskEvidenceCreateRequest {
    pub evidence_type: String,
    pub reference: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub created_by: Option<String>,
}

#[derive(Serialize)]
pub struct WorkflowAlignRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub entity_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub entity_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub to_state: Option<String>,
    pub triggered_by: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub approved_by: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auto: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dry_run: Option<bool>,
}

#[derive(Serialize)]
pub struct CreatePlanRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub format: Option<String>,
    pub content: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub product_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub goal_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub objective_id: Option<String>,
    #[serde(default)]
    pub task_ids: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
}

#[derive(Serialize)]
pub struct UpdatePlanRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub format: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub product_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub goal_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub objective_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub task_ids: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
}

#[derive(Serialize)]
pub struct EnvVarPair {
    pub key: String,
    pub value: String,
}

#[derive(Serialize)]
pub struct PlanTestJobCreateRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mode: Option<String>,
    pub project_path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub test_command: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub setup_command: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub working_dir: Option<String>,
    #[serde(default)]
    pub env_vars: Vec<EnvVarPair>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeout: Option<f64>,
    #[serde(default)]
    pub capture_logs: Vec<String>,
    #[serde(default)]
    pub save_artifacts: Vec<String>,
    #[serde(default)]
    pub task_ids: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transition_on_success: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transition_on_failure: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transition_by: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transition_reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub server_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub server_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub remote_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exclude_patterns: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stream_output: Option<bool>,
}

#[derive(Serialize)]
pub struct PlanTestJobUpdateRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mode: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub test_command: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub setup_command: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub working_dir: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub env_vars: Option<Vec<EnvVarPair>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeout: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub capture_logs: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub save_artifacts: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub task_ids: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transition_on_success: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transition_on_failure: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transition_by: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub transition_reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub server_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub server_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub remote_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exclude_patterns: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stream_output: Option<bool>,
}

#[derive(Serialize)]
pub struct CreateTestRunRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub run_id: Option<String>,
    pub server_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_id: Option<String>,
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exit_code: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration_seconds: Option<f64>,
    pub started_at: String,
    pub finished_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stdout: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stderr: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub logs: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub artifacts: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub config: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub command: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub runner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub plan_id: Option<String>,
    #[serde(default)]
    pub task_ids: Vec<String>,
}

#[derive(Serialize)]
pub struct CreateQueueRequest {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub filters: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sort_by: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sort_dir: Option<String>,
}

#[derive(Serialize)]
pub struct UpdateQueueRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub filters: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sort_by: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sort_dir: Option<String>,
}

#[derive(Serialize)]
pub struct CreateEvidenceGateRuleRequest {
    pub workflow_id: String,
    pub entity_type: String,
    pub from_state: String,
    pub to_state: String,
    pub evidence_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub min_count: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub require_success: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

#[derive(Serialize)]
pub struct DuplicateMergePreviewRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub primary_task_id: Option<String>,
    pub duplicate_task_ids: Vec<String>,
}

#[derive(Serialize)]
pub struct DuplicateMergeRequest {
    pub primary_task_id: String,
    pub duplicate_task_ids: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cancel_duplicates: Option<bool>,
}

#[derive(Serialize)]
pub struct WorkSnapshotReviewRequest {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reviewed_by: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<Value>,
}

// ============================================================
// Response Types
// ============================================================

#[derive(Deserialize)]
pub struct Product {
    pub id: String,
    pub name: String,
    pub status: String,
}

#[derive(Deserialize)]
pub struct ProductList {
    pub items: Vec<Product>,
    pub total_count: usize,
}

#[derive(Deserialize)]
pub struct ProductSummary {
    pub product: Product,
    pub stats: ProductStats,
}

#[derive(Deserialize)]
pub struct ProductStats {
    pub total_projects: usize,
    pub total_tasks: usize,
    pub completed_tasks: usize,
}

#[derive(Deserialize)]
pub struct ScopesResponse {
    pub scopes: Vec<String>,
}

#[derive(Deserialize)]
pub struct Organization {
    pub id: String,
    pub name: String,
    pub status: String,
    pub description: Option<String>,
    pub owner: Option<String>,
    #[serde(default)]
    pub members: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Deserialize)]
pub struct OrganizationList {
    pub items: Vec<Organization>,
    #[serde(default)]
    pub total_count: usize,
    #[serde(default)]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
}

#[derive(Deserialize)]
pub struct Team {
    pub id: String,
    pub org_id: Option<String>,
    pub name: String,
    pub status: String,
    pub description: Option<String>,
    pub owner: Option<String>,
    #[serde(default)]
    pub members: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Deserialize)]
pub struct TeamList {
    pub items: Vec<Team>,
    #[serde(default)]
    pub total_count: usize,
    #[serde(default)]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
}

#[derive(Deserialize)]
pub struct Portfolio {
    pub id: String,
    pub org_id: Option<String>,
    pub name: String,
    pub status: String,
    pub description: Option<String>,
    pub owner: Option<String>,
    #[serde(default)]
    pub project_ids: Vec<String>,
    #[serde(default)]
    pub goal_ids: Vec<String>,
    #[serde(default)]
    pub objective_ids: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Deserialize)]
pub struct PortfolioList {
    pub items: Vec<Portfolio>,
    #[serde(default)]
    pub total_count: usize,
    #[serde(default)]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
}

#[derive(Deserialize)]
pub struct Program {
    pub id: String,
    pub org_id: Option<String>,
    pub portfolio_id: Option<String>,
    pub name: String,
    pub status: String,
    pub description: Option<String>,
    pub owner: Option<String>,
    #[serde(default)]
    pub project_ids: Vec<String>,
    #[serde(default)]
    pub goal_ids: Vec<String>,
    #[serde(default)]
    pub objective_ids: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Deserialize)]
pub struct ProgramList {
    pub items: Vec<Program>,
    #[serde(default)]
    pub total_count: usize,
    #[serde(default)]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
}

#[derive(Deserialize)]
pub struct Project {
    pub id: String,
    pub name: String,
    pub status: Option<String>,
    pub description: Option<String>,
    pub tags: Option<Vec<String>>,
    pub org_id: Option<String>,
    pub portfolio_id: Option<String>,
    pub program_id: Option<String>,
    pub product_id: Option<String>,
}

#[derive(Deserialize)]
pub struct ProjectList {
    pub items: Vec<Project>,
    #[serde(default)]
    pub total_count: usize,
    #[serde(default)]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
}

#[derive(Deserialize)]
pub struct ProjectSummary {
    pub project: Project,
    pub stats: Option<ProjectStats>,
    pub health_score: f64,
}

#[derive(Deserialize)]
pub struct ProjectStats {
    pub total_tasks: usize,
    pub completed_tasks: usize,
    pub in_progress_tasks: usize,
    pub blocked_tasks: usize,
    pub total_milestones: usize,
    pub completed_milestones: usize,
    pub total_complexity_points: usize,
    pub avg_complexity_per_task: f64,
    pub total_duration_hours: f64,
    pub avg_duration_per_task: f64,
    pub avg_efficiency_score: f64,
    pub overdue_tasks: usize,
    pub total_goals: usize,
    pub completed_goals: usize,
    pub avg_goal_progress: f64,
}

#[derive(Deserialize)]
pub struct Task {
    pub id: String,
    pub title: String,
    pub status: String,
    pub complexity_points: Option<u8>,
    pub parent_id: Option<String>,
}

#[derive(Deserialize)]
pub struct TaskList {
    pub items: Vec<Task>,
    #[serde(default)]
    pub total_count: usize,
    #[serde(default)]
    pub offset: usize,
    #[serde(default)]
    pub limit: usize,
}

#[derive(Deserialize)]
pub struct TaskDependency {
    pub id: String,
    pub task_id: String,
    pub depends_on_id: String,
    pub dependency_type: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Deserialize)]
pub struct CheckoutResponse {
    pub task_id: String,
    pub checkout: serde_json::Value,
}

#[derive(Deserialize)]
pub struct ProgressResponse {
    pub task_id: String,
    pub percent_complete: u8,
}

#[derive(Deserialize)]
pub struct ProgressTimeline {
    pub current_percent: u8,
    pub velocity_percent_per_hour: f64,
    pub estimated_completion: Option<String>,
}

#[derive(Deserialize)]
pub struct WorkflowList {
    pub workflows: Vec<WorkflowInfo>,
}

#[derive(Deserialize)]
pub struct WorkflowInfo {
    pub id: String,
    pub name: String,
    pub states_count: usize,
}

#[derive(Deserialize)]
pub struct TransitionResponse {
    pub entity_id: String,
    pub to_state: String,
}

#[derive(Deserialize)]
pub struct HealthResponse {
    pub status: String,
    pub backend: String,
    pub schema_version: usize,
    pub schema_name: String,
}

#[derive(Deserialize)]
pub struct StatusResponse {
    pub status: String,
}

#[derive(Deserialize)]
pub struct AvailableTasksResponse {
    pub available_tasks: Vec<Task>,
    pub count: usize,
}

#[cfg(test)]
mod tests {
    use super::{plan_list_query_params, task_list_query_params, PMSClient};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;
    use tokio::task::JoinHandle;

    async fn spawn_single_response_server(
        content_type: &'static str,
        body: &'static str,
    ) -> (String, JoinHandle<String>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let handle = tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut buffer = vec![0_u8; 4096];
            let bytes_read = stream.read(&mut buffer).await.unwrap();
            let request = String::from_utf8_lossy(&buffer[..bytes_read]).into_owned();
            let response = format!(
                "HTTP/1.1 200 OK\r\ncontent-type: {content_type}\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}",
                body.len()
            );
            stream.write_all(response.as_bytes()).await.unwrap();
            request
        });
        (format!("http://{}", address), handle)
    }

    #[tokio::test]
    async fn get_dashboard_hits_api_dashboard_route() {
        let (base_url, server) = spawn_single_response_server(
            "application/json",
            r#"{"scope":{"kind":"instance_dashboard"}}"#,
        )
        .await;
        let client = PMSClient::new(base_url, None);

        let payload = client.get_dashboard().await.unwrap();
        let request = server.await.unwrap();
        let request_line = request.lines().next().unwrap();
        let request_parts: Vec<&str> = request_line.split_whitespace().collect();

        assert_eq!(payload["scope"]["kind"], "instance_dashboard");
        assert_eq!(request_parts[..2], ["GET", "/api/v1/dashboard"]);
    }

    #[tokio::test]
    async fn get_dashboard_html_hits_dashboard_page_route() {
        let (base_url, server) =
            spawn_single_response_server("text/html", "<html>dashboard</html>").await;
        let client = PMSClient::new(base_url, None);

        let payload = client.get_dashboard_html().await.unwrap();
        let request = server.await.unwrap();
        let request_line = request.lines().next().unwrap();
        let request_parts: Vec<&str> = request_line.split_whitespace().collect();

        assert_eq!(payload, "<html>dashboard</html>");
        assert_eq!(request_parts[..2], ["GET", "/dashboard"]);
    }

    #[test]
    fn task_list_query_params_preserve_python_filter_semantics() {
        let params = task_list_query_params(Some("project-123"), Some("todo"), Some(25), Some(50));

        assert_eq!(
            params,
            vec![
                ("project_id", "project-123".to_string()),
                ("status", "todo".to_string()),
                ("limit", "25".to_string()),
                ("offset", "50".to_string()),
            ]
        );
    }

    #[tokio::test]
    async fn list_tasks_includes_filters_and_pagination_query_params() {
        let (base_url, server) = spawn_single_response_server(
            "application/json",
            r#"{"items":[],"total_count":17,"limit":25,"offset":50}"#,
        )
        .await;
        let client = PMSClient::new(base_url, None);

        let payload = client
            .list_tasks(Some("project-123"), Some("todo"), Some(25), Some(50))
            .await
            .unwrap();
        let request = server.await.unwrap();
        let request_line = request.lines().next().unwrap();
        let request_parts: Vec<&str> = request_line.split_whitespace().collect();

        assert_eq!(payload.total_count, 17);
        assert_eq!(payload.limit, 25);
        assert_eq!(payload.offset, 50);
        assert_eq!(
            request_parts[..2],
            [
                "GET",
                "/api/v1/tasks?project_id=project-123&status=todo&limit=25&offset=50"
            ]
        );
    }

    #[test]
    fn plan_list_query_params_preserve_python_filter_semantics() {
        let params = plan_list_query_params(
            Some("draft"),
            Some("project-123"),
            None,
            None,
            None,
            Some("task-456"),
            Some(25),
            Some(50),
        );

        assert_eq!(
            params,
            vec![
                ("status", "draft".to_string()),
                ("project_id", "project-123".to_string()),
                ("task_id", "task-456".to_string()),
                ("limit", "25".to_string()),
                ("offset", "50".to_string()),
            ]
        );
    }

    #[tokio::test]
    async fn list_plans_includes_task_id_filter_query_param() {
        let (base_url, server) =
            spawn_single_response_server("application/json", r#"{"items":[]}"#).await;
        let client = PMSClient::new(base_url, None);

        client
            .list_plans(
                Some("draft"),
                Some("project-123"),
                None,
                None,
                None,
                Some("task-456"),
                Some(25),
                Some(50),
            )
            .await
            .unwrap();
        let request = server.await.unwrap();
        let request_line = request.lines().next().unwrap();
        let request_parts: Vec<&str> = request_line.split_whitespace().collect();

        assert_eq!(
            request_parts[..2],
            [
                "GET",
                "/api/v1/plans?status=draft&project_id=project-123&task_id=task-456&limit=25&offset=50"
            ]
        );
    }
}
