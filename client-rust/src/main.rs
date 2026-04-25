//! PMS Client - Zero-latency compiled binary for PMS API server
//!
//! Fast native client with no interpreter overhead

use anyhow::{bail, Result};
use chrono::Utc;
use clap::{Parser, Subcommand};
use pms_client::{client::*, handlers::*};
use std::fs;

#[derive(Parser)]
#[command(name = "pms-client")]
#[command(about = "Fast compiled client for PMS API server", long_about = None)]
struct Cli {
    #[arg(
        long,
        env = "PMS_SERVER_BASE_URL",
        default_value = "http://127.0.0.1:27541"
    )]
    server: String,

    #[arg(long, env = "PMS_API_KEY")]
    api_key: Option<String>,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Auth operations
    Auth {
        #[command(subcommand)]
        action: AuthCommands,
    },
    /// Actor identity graph operations
    Actor {
        #[command(subcommand)]
        action: ActorCommands,
    },
    /// Task operations
    Task {
        #[command(subcommand)]
        action: TaskCommands,
    },
    /// Organization operations
    Org {
        #[command(subcommand)]
        action: OrgCommands,
    },
    /// Team operations
    Team {
        #[command(subcommand)]
        action: TeamCommands,
    },
    /// Portfolio operations
    Portfolio {
        #[command(subcommand)]
        action: PortfolioCommands,
    },
    /// Program operations
    Program {
        #[command(subcommand)]
        action: ProgramCommands,
    },
    /// Product operations
    Product {
        #[command(subcommand)]
        action: ProductCommands,
    },
    /// Project operations
    Project {
        #[command(subcommand)]
        action: ProjectCommands,
    },
    /// Plan operations
    Plan {
        #[command(subcommand)]
        action: PlanCommands,
    },
    /// Queue operations
    Queue {
        #[command(subcommand)]
        action: QueueCommands,
    },
    /// Test run operations
    #[command(name = "test-run")]
    TestRun {
        #[command(subcommand)]
        action: TestRunCommands,
    },
    /// Test operations
    #[command(name = "test")]
    Test {
        #[command(subcommand)]
        action: TestRunCommands,
    },
    /// Workflow operations
    Workflow {
        #[command(subcommand)]
        action: WorkflowCommands,
    },
    /// Goal operations
    Goal {
        #[command(subcommand)]
        action: GoalCommands,
    },
    /// Objective operations
    Objective {
        #[command(subcommand)]
        action: ObjectiveCommands,
    },
    /// Key result operations
    #[command(name = "keyresult")]
    KeyResult {
        #[command(subcommand)]
        action: KeyResultCommands,
    },
    /// Label operations
    Label {
        #[command(subcommand)]
        action: LabelCommands,
    },
    /// Custom field operations
    #[command(name = "custom-field")]
    CustomField {
        #[command(subcommand)]
        action: CustomFieldCommands,
    },
    /// Comment operations
    Comment {
        #[command(subcommand)]
        action: CommentCommands,
    },
    /// Watcher operations
    Watcher {
        #[command(subcommand)]
        action: WatcherCommands,
    },
    /// Automation operations
    Automation {
        #[command(subcommand)]
        action: AutomationCommands,
    },
    /// Evidence operations
    Evidence {
        #[command(subcommand)]
        action: EvidenceCommands,
    },
    /// Transition timeline operations
    Timeline {
        #[command(subcommand)]
        action: TimelineCommands,
    },
    /// Revision history operations
    Revision {
        #[command(subcommand)]
        action: RevisionCommands,
    },
    /// Work snapshot operations
    Work {
        #[command(subcommand)]
        action: WorkCommands,
    },
    /// Agent loop operations
    Loop {
        #[command(subcommand)]
        action: LoopCommands,
    },
    /// Practical start -> go guidance with live API state
    Start {
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Dashboard HTML
    Dashboard,
    /// Preferred local runtime operations
    Runtime {
        #[command(subcommand)]
        action: RuntimeCommands,
    },
    /// Health check
    Health,
}

#[derive(Subcommand)]
enum ActorCommands {
    /// Create a canonical actor
    Create {
        name: String,
        #[arg(
            long,
            value_parser = ["human", "persona", "team", "service_account", "runtime_agent"]
        )]
        kind: String,
        #[arg(long)]
        handle: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(short = 't', long)]
        tag: Vec<String>,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// List actors
    List {
        #[arg(
            long,
            value_parser = ["human", "persona", "team", "service_account", "runtime_agent"]
        )]
        kind: Option<String>,
        #[arg(long, value_parser = ["active", "archived"])]
        status: Option<String>,
        #[arg(long, default_value = "table", value_parser = ["table", "json"])]
        format: String,
        #[arg(long, default_value_t = 100)]
        limit: u32,
        #[arg(long, default_value_t = 0)]
        offset: u32,
    },
    /// Show actor details and linked workload
    Show {
        actor: String,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Manage actor aliases
    Alias {
        #[command(subcommand)]
        action: ActorAliasCommands,
    },
    /// Manage actor memberships
    Membership {
        #[command(subcommand)]
        action: ActorMembershipCommands,
    },
}

#[derive(Subcommand)]
enum ActorAliasCommands {
    /// Add an alias to an actor
    Add {
        actor: String,
        alias_value: String,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
}

#[derive(Subcommand)]
enum ActorMembershipCommands {
    /// Add a membership edge between actors
    Add {
        parent: String,
        member: String,
        #[arg(long, default_value = "member", value_parser = ["member", "lead", "representative"])]
        role: String,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
}

#[derive(Subcommand)]
enum TaskCommands {
    /// Create a task
    Create {
        project_id: String,
        title: String,
        #[arg(long)]
        parent_id: Option<String>,
        #[arg(short, long)]
        complexity: Option<u8>,
        #[arg(short, long, default_value = "medium")]
        priority: String,
    },
    /// List tasks
    List {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Get task by ID
    Get { task_id: String },
    /// Resolve a task reference
    Resolve {
        task_ref: String,
        #[arg(long)]
        project: Option<String>,
    },
    /// Start a task
    Start {
        task_id: String,
        #[arg(long)]
        by: Option<String>,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Complete a task
    Complete {
        task_id: String,
        #[arg(long)]
        notes: Option<String>,
        #[arg(long)]
        by: Option<String>,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Block a task
    Block {
        task_id: String,
        #[arg(long)]
        reason: Option<String>,
        #[arg(long)]
        by: Option<String>,
    },
    /// Unblock a task
    Unblock {
        task_id: String,
        #[arg(long)]
        by: Option<String>,
    },
    /// Submit a task for review
    Review {
        task_id: String,
        #[arg(long)]
        by: Option<String>,
    },
    /// Reopen a task
    Reopen {
        task_id: String,
        #[arg(long)]
        by: Option<String>,
    },
    /// Delete (cancel) a task
    Delete {
        task_id: String,
        #[arg(long)]
        reason: Option<String>,
        #[arg(long)]
        by: Option<String>,
    },
    /// Checkout a task
    Checkout {
        task_id: String,
        #[arg(long)]
        agent_id: String,
        #[arg(long, default_value = "300")]
        lease: u32,
    },
    /// Release checkout
    Release {
        task_id: String,
        #[arg(long)]
        agent_id: String,
    },
    /// Renew checkout lease
    Renew {
        task_id: String,
        #[arg(long)]
        agent_id: String,
    },
    /// Get available tasks for checkout
    Available {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
    },
    /// Update progress
    Progress {
        task_id: String,
        percent: u8,
        message: String,
        #[arg(long)]
        by: String,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Get progress timeline
    Timeline { task_id: String },
    /// Search tasks with filters
    Search {
        #[arg(long)]
        query: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        status: Vec<String>,
        #[arg(long)]
        priority: Vec<String>,
        #[arg(long)]
        assignee: Option<String>,
        #[arg(long)]
        tag: Vec<String>,
        #[arg(long)]
        label_id: Vec<String>,
        #[arg(long)]
        label_category_id: Vec<String>,
        #[arg(long)]
        created_from: Option<String>,
        #[arg(long)]
        created_to: Option<String>,
        #[arg(long)]
        updated_from: Option<String>,
        #[arg(long)]
        updated_to: Option<String>,
        #[arg(long)]
        due_from: Option<String>,
        #[arg(long)]
        due_to: Option<String>,
        #[arg(long)]
        include_terminal: bool,
        #[arg(long)]
        sort_by: Option<String>,
        #[arg(long)]
        sort_dir: Option<String>,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
    /// List ready tasks
    Ready {
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        status: Vec<String>,
        #[arg(long, default_value_t = true)]
        exclude_checked_out: bool,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
    /// List stale tasks
    Stale {
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        status: Vec<String>,
        #[arg(long)]
        stale_after_days: Option<u32>,
        #[arg(long)]
        updated_before: Option<String>,
        #[arg(long)]
        include_terminal: bool,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
    /// List blocked tasks
    Blocked {
        #[arg(long)]
        project_id: Option<String>,
    },
    /// List duplicate task groups
    Duplicates {
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        status: Vec<String>,
        #[arg(long)]
        include_terminal: bool,
        #[arg(long)]
        min_count: Option<u32>,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
    /// Preview duplicate task merge
    DuplicatesPreview {
        #[arg(long)]
        primary_task_id: Option<String>,
        #[arg(long, required = true)]
        duplicate_task_id: Vec<String>,
    },
    /// Merge duplicate tasks
    DuplicatesMerge {
        #[arg(long)]
        primary_task_id: String,
        #[arg(long, required = true)]
        duplicate_task_id: Vec<String>,
        #[arg(long)]
        cancel_duplicates: bool,
    },
    /// Manage task evidence
    Evidence {
        #[command(subcommand)]
        action: TaskEvidenceCommands,
    },
    /// Get a task proof bundle
    ProofBundle {
        task_id: String,
        #[arg(long)]
        include_output: bool,
        #[arg(long)]
        include_logs: bool,
        #[arg(long)]
        include_artifacts: bool,
    },
    /// Search task proof bundles
    ProofBundleSearch {
        #[arg(long)]
        task_id: Vec<String>,
        #[arg(long)]
        plan_id: Option<String>,
        #[arg(long)]
        status: Vec<String>,
        #[arg(long)]
        evidence_type: Vec<String>,
        #[arg(long)]
        created_from: Option<String>,
        #[arg(long)]
        created_to: Option<String>,
        #[arg(long)]
        include_evidence: bool,
        #[arg(long)]
        include_test_runs: bool,
        #[arg(long)]
        include_output: bool,
        #[arg(long)]
        include_logs: bool,
        #[arg(long)]
        include_artifacts: bool,
        #[arg(long, default_value = "50")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
    /// Manage task dependencies
    Dep {
        #[command(subcommand)]
        action: TaskDependencyCommands,
    },
    /// Show dependency graph for a task
    Graph { task_id: String },
    /// Show task hierarchy tree for a project
    Tree {
        #[arg(long)]
        project_id: String,
        #[arg(long)]
        root_task_id: Option<String>,
    },
    /// Update a task
    Update {
        task_id: String,
        #[arg(long)]
        title: Option<String>,
        #[arg(long)]
        description: Option<String>,
        #[arg(long)]
        parent_id: Option<String>,
        #[arg(long)]
        clear_parent: bool,
        #[arg(long)]
        priority: Option<String>,
        #[arg(long)]
        complexity_points: Option<u8>,
    },
    /// Show checkout status for an agent
    CheckoutStatus {
        #[arg(long)]
        agent_id: String,
        #[arg(long)]
        include_expired: bool,
    },
    /// Show checkout audit log
    CheckoutLog {
        #[arg(long)]
        task_id: Option<String>,
        #[arg(long)]
        agent_id: Option<String>,
        #[arg(long)]
        action: Option<String>,
        #[arg(long)]
        success: Option<bool>,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
        #[arg(long)]
        include_metadata: bool,
    },
    /// Cleanup expired checkouts
    CheckoutCleanup {
        #[arg(long)]
        dry_run: bool,
    },
    /// Force release a checkout
    ForceRelease {
        task_id: String,
        #[arg(long)]
        released_by: Option<String>,
        #[arg(long)]
        reason: Option<String>,
    },
}

#[derive(Subcommand)]
enum TaskEvidenceCommands {
    /// Add evidence to a task
    Add {
        task_id: String,
        evidence_type: String,
        reference: String,
        #[arg(long)]
        description: Option<String>,
        #[arg(long)]
        metadata: Option<String>,
        #[arg(long)]
        metadata_file: Option<String>,
        #[arg(long)]
        created_by: Option<String>,
    },
    /// List evidence for a task
    List {
        task_id: String,
        #[arg(long)]
        include_test_runs: bool,
        #[arg(long)]
        include_output: bool,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
}

#[derive(Subcommand)]
enum TaskDependencyCommands {
    /// Add a task dependency
    Add {
        task_id: String,
        depends_on_id: String,
        #[arg(long)]
        dependency_type: Option<String>,
    },
    /// Remove a task dependency
    Remove {
        task_id: String,
        depends_on_id: String,
    },
}

#[derive(Subcommand)]
enum AuthCommands {
    /// List available auth scopes
    Scopes,
    /// Initialize the first admin API key
    Init {
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        show_key: bool,
    },
    /// Recover a local admin API key and refresh .pms-admin-key
    #[command(name = "recover-local-admin")]
    RecoverLocalAdmin {
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        show_key: bool,
    },
    /// Manage API keys
    Keys {
        #[command(subcommand)]
        action: KeyCommands,
    },
}

#[derive(Subcommand)]
enum KeyCommands {
    /// Create an API key
    Create {
        #[arg(long)]
        name: String,
        #[arg(long, required = true)]
        scope: Vec<String>,
        #[arg(long)]
        expires_in_days: Option<i32>,
        #[arg(long)]
        rate_limit: Option<i32>,
        #[arg(long = "meta")]
        metadata: Vec<String>,
    },
    /// List API keys
    List {
        #[arg(long)]
        include_inactive: bool,
        #[arg(long)]
        include_archived: bool,
    },
    /// Get API key by ID
    Get { key_id: String },
    /// Deactivate an API key
    Deactivate { key_id: String },
    /// Restore an API key
    Restore { key_id: String },
    /// Delete an API key
    Delete { key_id: String },
}

#[derive(Subcommand)]
enum GoalCommands {
    /// Create a goal
    Create {
        name: String,
        #[arg(long)]
        horizon: String,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        target_date: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        product_id: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(short = 't', long)]
        tag: Vec<String>,
        #[arg(long)]
        progress: Option<i32>,
    },
    /// List goals
    List {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        horizon: Option<String>,
        #[arg(long)]
        product_id: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Get goal by ID
    Get { goal_id: String },
    /// Update goal
    Update {
        goal_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        horizon: Option<String>,
        #[arg(long)]
        target_date: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        product_id: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
        #[arg(long)]
        progress: Option<i32>,
    },
    /// Complete goal
    Complete { goal_id: String },
    /// Archive goal
    Archive { goal_id: String },
    /// Goal summary
    Summary { goal_id: String },
    /// Assign workflow
    WorkflowAssign {
        goal_id: String,
        workflow_name: String,
        initial_state: String,
    },
    /// Transition workflow
    WorkflowTransition {
        goal_id: String,
        to_state: String,
        #[arg(long)]
        by: String,
        #[arg(long)]
        reason: Option<String>,
        #[arg(long)]
        approved_by: Option<String>,
    },
}

#[derive(Subcommand)]
enum ObjectiveCommands {
    /// Create an objective
    Create {
        goal_id: String,
        name: String,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        target_date: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(short = 't', long)]
        tag: Vec<String>,
        #[arg(long)]
        progress: Option<i32>,
    },
    /// List objectives for a goal
    List {
        goal_id: String,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Get objective by ID
    Get { objective_id: String },
    /// Update objective
    Update {
        objective_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        target_date: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
        #[arg(long)]
        progress: Option<i32>,
    },
    /// Complete objective
    Complete { objective_id: String },
    /// Archive objective
    Archive { objective_id: String },
    /// Assign workflow
    WorkflowAssign {
        objective_id: String,
        workflow_name: String,
        initial_state: String,
    },
    /// Transition workflow
    WorkflowTransition {
        objective_id: String,
        to_state: String,
        #[arg(long)]
        by: String,
        #[arg(long)]
        reason: Option<String>,
        #[arg(long)]
        approved_by: Option<String>,
    },
}

#[derive(Subcommand)]
enum KeyResultCommands {
    /// Create a key result
    Create {
        objective_id: String,
        name: String,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        current_value: Option<f64>,
        #[arg(long)]
        target_value: Option<f64>,
        #[arg(long)]
        unit: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(short = 't', long)]
        tag: Vec<String>,
        #[arg(long)]
        progress: Option<i32>,
    },
    /// List key results for an objective
    List {
        objective_id: String,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Get key result by ID
    Get { key_result_id: String },
    /// Update key result
    Update {
        key_result_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        current_value: Option<f64>,
        #[arg(long)]
        target_value: Option<f64>,
        #[arg(long)]
        unit: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
        #[arg(long)]
        progress: Option<i32>,
    },
    /// Complete key result
    Complete { key_result_id: String },
    /// Archive key result
    Archive { key_result_id: String },
}

#[derive(Subcommand)]
enum LabelCommands {
    /// Create a label
    Create {
        name: String,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        category_id: Option<String>,
        #[arg(long)]
        color: Option<String>,
        #[arg(long)]
        system: Option<bool>,
    },
    /// List labels
    List {
        #[arg(long)]
        category_id: Option<String>,
        #[arg(long)]
        include_archived: bool,
    },
    /// Get label by ID
    Get { label_id: String },
    /// Update label
    Update {
        label_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        category_id: Option<String>,
        #[arg(long)]
        color: Option<String>,
        #[arg(long)]
        system: Option<bool>,
    },
    /// Delete label
    Delete { label_id: String },
    /// Restore label
    Restore { label_id: String },
    /// Manage label categories
    Category {
        #[command(subcommand)]
        action: LabelCategoryCommands,
    },
    /// Manage label assignments
    Assignment {
        #[command(subcommand)]
        action: LabelAssignmentCommands,
    },
    /// Manage label gate rules
    Gate {
        #[command(subcommand)]
        action: LabelGateCommands,
    },
}

#[derive(Subcommand)]
enum LabelCategoryCommands {
    /// Create a label category
    Create {
        name: String,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        exclusive: Option<bool>,
        #[arg(long)]
        sort_order: Option<i32>,
    },
    /// List label categories
    List {
        #[arg(long)]
        include_archived: bool,
    },
    /// Get category by ID
    Get { category_id: String },
    /// Update category
    Update {
        category_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        exclusive: Option<bool>,
        #[arg(long)]
        sort_order: Option<i32>,
    },
    /// Delete category
    Delete { category_id: String },
    /// Restore category
    Restore { category_id: String },
}

#[derive(Subcommand)]
enum LabelAssignmentCommands {
    /// Assign a label
    Create {
        entity_type: String,
        entity_id: String,
        label_id: String,
        #[arg(long)]
        applied_by: Option<String>,
    },
    /// List assignments for an entity
    List {
        entity_type: String,
        entity_id: String,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Assignment history
    History {
        assignment_id: String,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Remove assignment
    Remove {
        entity_type: String,
        entity_id: String,
        label_id: String,
    },
}

#[derive(Subcommand)]
enum LabelGateCommands {
    /// Create a label gate rule
    Create {
        workflow_id: String,
        entity_type: String,
        from_state: String,
        to_state: String,
        rule_type: String,
        #[arg(long)]
        label_id: Option<String>,
        #[arg(long)]
        category_id: Option<String>,
        #[arg(long)]
        message: Option<String>,
    },
    /// List label gate rules
    List {
        workflow_id: String,
        entity_type: String,
        from_state: String,
        to_state: String,
    },
    /// Delete a label gate rule
    Delete { rule_id: String },
}

#[derive(Subcommand)]
enum CustomFieldCommands {
    /// Create a custom field definition
    Create {
        name: String,
        #[arg(long)]
        entity_type: String,
        #[arg(long)]
        field_type: String,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        option: Vec<String>,
        #[arg(long)]
        required: bool,
    },
    /// List custom field definitions
    List {
        #[arg(long)]
        entity_type: Option<String>,
        #[arg(long)]
        include_archived: bool,
    },
    /// Show custom field definition
    #[command(name = "show")]
    Show {
        field_ref: String,
        #[arg(long)]
        entity_type: Option<String>,
    },
    /// Update custom field definition
    Update {
        field_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        field_type: Option<String>,
        #[arg(long)]
        option: Vec<String>,
        #[arg(long)]
        required: Option<bool>,
    },
    /// Delete custom field definition
    Delete { field_id: String },
    /// Restore custom field definition
    Restore { field_id: String },
    /// Manage custom field values
    Value {
        #[command(subcommand)]
        action: CustomFieldValueCommands,
    },
}

#[derive(Subcommand)]
enum CommentCommands {
    /// Add a comment to an entity
    Add {
        entity_type: String,
        entity_id: String,
        body: String,
        #[arg(long = "by")]
        created_by: String,
        #[arg(long)]
        mention: Vec<String>,
        #[arg(long)]
        metadata_json: Option<String>,
        #[arg(long)]
        watch: bool,
    },
    /// List comments for an entity
    List {
        entity_type: String,
        entity_id: String,
        #[arg(long)]
        include_archived: bool,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Show a comment by ID
    Show { comment_id: String },
    /// Delete a comment by ID
    Delete { comment_id: String },
    /// Restore a comment by ID
    Restore { comment_id: String },
}

#[derive(Subcommand)]
enum WatcherCommands {
    /// Add a watcher for an entity
    Add {
        entity_type: String,
        entity_id: String,
        watcher: String,
    },
    /// List watchers for an entity
    List {
        entity_type: String,
        entity_id: String,
        #[arg(long)]
        include_archived: bool,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Remove a watcher from an entity
    Remove {
        entity_type: String,
        entity_id: String,
        watcher: String,
    },
    /// Restore a watcher by ID
    Restore { watcher_id: String },
}

#[derive(Subcommand)]
enum AutomationCommands {
    /// Manage automation rules
    Rule {
        #[command(subcommand)]
        action: AutomationRuleCommands,
    },
    /// Run automation rules for an event
    Run {
        #[arg(long)]
        event_id: String,
        #[arg(long)]
        rule_id: Option<String>,
        #[arg(long)]
        dry_run: bool,
    },
}

#[derive(Subcommand)]
enum AutomationRuleCommands {
    /// Create an automation rule
    Create {
        name: String,
        event_pattern: String,
        action_type: String,
        #[arg(long)]
        action_payload_json: String,
        #[arg(long)]
        description: Option<String>,
        #[arg(long)]
        aggregate_type: Option<String>,
        #[arg(long)]
        aggregate_id: Option<String>,
        #[arg(long)]
        enabled: Option<bool>,
        #[arg(long)]
        cooldown_seconds: Option<f64>,
    },
    /// List automation rules
    List {
        #[arg(long)]
        include_archived: bool,
        #[arg(long)]
        enabled: Option<bool>,
    },
    /// Show automation rule details
    Show { rule_id: String },
    /// Update an automation rule
    Update {
        rule_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        event_pattern: Option<String>,
        #[arg(long)]
        action_type: Option<String>,
        #[arg(long)]
        action_payload_json: Option<String>,
        #[arg(long)]
        description: Option<String>,
        #[arg(long)]
        aggregate_type: Option<String>,
        #[arg(long)]
        aggregate_id: Option<String>,
        #[arg(long)]
        enabled: Option<bool>,
        #[arg(long)]
        cooldown_seconds: Option<f64>,
    },
    /// Delete an automation rule
    Delete { rule_id: String },
    /// Restore an automation rule
    Restore { rule_id: String },
    /// List automation rule runs
    Runs {
        rule_id: String,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
}

#[derive(Subcommand)]
enum CustomFieldValueCommands {
    /// Set a custom field value
    Set {
        field_ref: String,
        #[arg(long)]
        entity_type: String,
        #[arg(long)]
        entity_id: String,
        #[arg(long)]
        value: Option<String>,
        #[arg(long)]
        value_json: Option<String>,
        #[arg(long)]
        created_by: Option<String>,
        #[arg(long)]
        source: Option<String>,
        #[arg(long)]
        metadata_json: Option<String>,
    },
    /// List custom field values
    List {
        #[arg(long)]
        entity_type: Option<String>,
        #[arg(long)]
        entity_id: Option<String>,
        #[arg(long)]
        field_id: Option<String>,
        #[arg(long)]
        include_history: bool,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
}

#[derive(Subcommand)]
enum EvidenceCommands {
    /// Evidence gate rules
    Gate {
        #[command(subcommand)]
        action: EvidenceGateCommands,
    },
    /// Search proof bundles
    BundleSearch {
        #[arg(long)]
        task_id: Vec<String>,
        #[arg(long)]
        plan_id: Option<String>,
        #[arg(long)]
        status: Vec<String>,
        #[arg(long)]
        evidence_type: Vec<String>,
        #[arg(long)]
        created_from: Option<String>,
        #[arg(long)]
        created_to: Option<String>,
        #[arg(long)]
        include_evidence: bool,
        #[arg(long)]
        include_test_runs: bool,
        #[arg(long)]
        include_output: bool,
        #[arg(long)]
        include_logs: bool,
        #[arg(long)]
        include_artifacts: bool,
        #[arg(long, default_value = "50")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
}

#[derive(Subcommand)]
enum EvidenceGateCommands {
    /// Create an evidence gate rule
    Create {
        workflow_id: String,
        entity_type: String,
        from_state: String,
        to_state: String,
        evidence_type: String,
        #[arg(long)]
        min_count: Option<u32>,
        #[arg(long)]
        require_success: bool,
        #[arg(long)]
        message: Option<String>,
    },
    /// List evidence gate rules
    List {
        workflow_id: String,
        entity_type: String,
        from_state: String,
        to_state: String,
    },
    /// Delete evidence gate rule
    Delete { rule_id: String },
}

#[derive(Subcommand)]
enum TimelineCommands {
    /// Workflow transition timeline
    Workflow {
        entity_type: String,
        entity_id: String,
        #[arg(long)]
        triggered_by: Option<String>,
        #[arg(long)]
        from_state: Option<String>,
        #[arg(long)]
        to_state: Option<String>,
        #[arg(long)]
        start_time: Option<String>,
        #[arg(long)]
        end_time: Option<String>,
        #[arg(long)]
        transition_type: Option<String>,
        #[arg(long)]
        label: Vec<String>,
    },
    /// Status transition timeline
    Status {
        entity_type: String,
        entity_id: String,
        #[arg(long)]
        triggered_by: Option<String>,
        #[arg(long)]
        from_state: Option<String>,
        #[arg(long)]
        to_state: Option<String>,
        #[arg(long)]
        start_time: Option<String>,
        #[arg(long)]
        end_time: Option<String>,
        #[arg(long)]
        transition_type: Option<String>,
        #[arg(long)]
        label: Vec<String>,
    },
}

#[derive(Subcommand)]
enum RevisionCommands {
    /// Diff two revisions
    Diff {
        entity_type: String,
        entity_id: String,
        from_revision: u32,
        to_revision: u32,
    },
    /// Get revision history bundle
    Bundle {
        entity_type: String,
        entity_id: String,
        #[arg(long)]
        include_linked: bool,
        #[arg(long)]
        include_linked_history: bool,
        #[arg(long, default_value = "20")]
        history_limit: u32,
        #[arg(long, default_value = "0")]
        history_offset: u32,
        #[arg(long, default_value = "20")]
        linked_limit: u32,
        #[arg(long)]
        linked_history_limit: Option<u32>,
    },
}

#[derive(Subcommand)]
enum WorkCommands {
    /// Get a work snapshot
    Snapshot {
        scope_type: String,
        scope_id: String,
        #[arg(long, default_value = "5")]
        task_limit: u32,
        #[arg(long, default_value = "5")]
        test_limit: u32,
    },
    /// Get a daily work summary
    Daily {
        scope_type: String,
        scope_id: String,
        #[arg(long, default_value = "5")]
        task_limit: u32,
        #[arg(long, default_value = "5")]
        test_limit: u32,
        #[arg(long, default_value = "3")]
        queue_limit: u32,
        #[arg(long, default_value = "14")]
        stale_days: u32,
        #[arg(long, default_value = "7")]
        at_risk_days: u32,
        #[arg(long)]
        include_timeline: bool,
        #[arg(long, default_value = "5")]
        timeline_limit: u32,
        #[arg(long)]
        include_history: bool,
        #[arg(long, default_value = "3")]
        history_limit: u32,
        #[arg(long)]
        view: Option<String>,
        #[arg(long, default_value = "text")]
        format: String,
    },
    /// Show a unified graph report across scope, plans, tasks, actors, and evidence
    #[command(name = "graph-report")]
    GraphReport {
        #[arg(long = "scope-type")]
        scope_type: String,
        #[arg(long)]
        scope: Option<String>,
        #[arg(long = "scope-id")]
        scope_id: Option<String>,
        #[arg(long, default_value = "20")]
        task_limit: u32,
        #[arg(long, default_value = "20")]
        goal_limit: u32,
        #[arg(long, default_value = "20")]
        objective_limit: u32,
        #[arg(long, default_value = "20")]
        plan_limit: u32,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Mark a work snapshot reviewed
    Review {
        scope_type: String,
        scope_id: String,
        #[arg(long)]
        reviewed_by: Option<String>,
        #[arg(long)]
        note: Option<String>,
        #[arg(long)]
        metadata: Option<String>,
        #[arg(long)]
        metadata_file: Option<String>,
    },
}

#[derive(Subcommand)]
enum LoopCommands {
    /// Initialize loop config and prompt
    Init {
        #[arg(long, default_value = "pms-loop.yml")]
        config: String,
        #[arg(long, default_value = "PROMPT.md")]
        prompt_file: String,
        #[arg(long)]
        force: bool,
    },
    /// Interactive prompt-to-loop setup
    Setup {
        #[arg(long)]
        defaults: bool,
        #[arg(long)]
        org: Option<String>,
        #[arg(long)]
        product: Option<String>,
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        goal: Option<String>,
        #[arg(long, default_value = "short_term")]
        goal_horizon: String,
        #[arg(long)]
        objective: Option<String>,
        #[arg(long = "criterion")]
        criteria: Vec<String>,
        #[arg(long = "task")]
        tasks: Vec<String>,
        #[arg(long, default_value = "pms-loop.yml")]
        config: String,
        #[arg(long, default_value = "PROMPT.md")]
        prompt_file: String,
        #[arg(long)]
        force: bool,
        #[arg(long, default_value = "claude")]
        agent: String,
        #[arg(long, default_value = "DONE")]
        completion_promise: String,
        #[arg(long)]
        run: bool,
        #[arg(long)]
        no_run: bool,
        #[arg(long, default_value_t = true)]
        assign_workflow: bool,
        #[arg(long)]
        no_assign_workflow: bool,
        #[arg(long, default_value = "sdlc")]
        workflow: String,
        #[arg(long, default_value = "concept")]
        initial_state: String,
    },
    /// Render a prompt template with IDs prefilled
    PromptTemplate {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        goal: Option<String>,
        #[arg(long)]
        goal_id: Option<String>,
        #[arg(long)]
        objective: Option<String>,
        #[arg(long)]
        objective_id: Option<String>,
        #[arg(long)]
        plan: Option<String>,
        #[arg(long)]
        plan_id: Option<String>,
        #[arg(long, default_value = "PROMPT.md")]
        prompt_file: String,
        #[arg(long)]
        force: bool,
        #[arg(long)]
        stdout: bool,
        #[arg(long)]
        no_write: bool,
        #[arg(long)]
        task_limit: Option<u32>,
        #[arg(long)]
        keyresult_limit: Option<u32>,
        #[arg(long)]
        pick: bool,
    },
    /// Run a local loop (delegates to the Python CLI loop runner)
    Run {
        prompt: Vec<String>,
        #[arg(long)]
        config: Option<String>,
        #[arg(long)]
        prompt_file: Option<String>,
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        agent: Option<String>,
        #[arg(long)]
        agent_command: Option<String>,
        #[arg(long = "agent-arg")]
        agent_args: Vec<String>,
        #[arg(long, default_value = "stdin")]
        prompt_mode: String,
        #[arg(long)]
        max_iterations: Option<u32>,
        #[arg(long)]
        max_runtime: Option<u32>,
        #[arg(long)]
        completion_promise: Option<String>,
        #[arg(long)]
        completion_marker: Option<String>,
        #[arg(long)]
        retry_delay: Option<f64>,
        #[arg(long)]
        dry_run: bool,
    },
    /// List agent loops
    List {
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        include_ended: bool,
    },
    /// Show agent loop summary
    Show { loop_id: String },
    /// Show agent loop messages
    Messages {
        loop_id: String,
        #[arg(long)]
        limit: Option<u32>,
    },
    /// Cancel an agent loop
    Cancel { loop_id: String },
    /// Guard loop stop until goals are complete
    Guard {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        goal: Vec<String>,
        #[arg(long = "goal-id")]
        goal_id: Vec<String>,
        #[arg(long)]
        include_archived: bool,
        #[arg(long)]
        allow_no_goals: bool,
        #[arg(long)]
        hook: bool,
        #[arg(long)]
        format: Option<String>,
    },
}

#[derive(Subcommand)]
enum OrgCommands {
    /// Create an organization
    Create {
        name: String,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        member: Vec<String>,
        #[arg(short = 't', long)]
        tag: Vec<String>,
    },
    /// List organizations
    List {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Get organization by ID
    Get { org_id: String },
    /// Update organization
    Update {
        org_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        member: Option<Vec<String>>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
    },
    /// Organization summary
    Summary { org_id: String },
    /// Organization dashboard rollups
    Dashboard {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
}

#[derive(Subcommand)]
enum TeamCommands {
    /// Create a team
    Create {
        name: String,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        member: Vec<String>,
        #[arg(short = 't', long)]
        tag: Vec<String>,
    },
    /// List teams
    List {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Get team by ID
    Get { team_id: String },
    /// Update team
    Update {
        team_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        member: Option<Vec<String>>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
    },
}

#[derive(Subcommand)]
enum PortfolioCommands {
    /// Create a portfolio
    Create {
        name: String,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long = "project-id")]
        project_ids: Vec<String>,
        #[arg(long = "goal-id")]
        goal_ids: Vec<String>,
        #[arg(long = "objective-id")]
        objective_ids: Vec<String>,
        #[arg(short = 't', long)]
        tag: Vec<String>,
    },
    /// List portfolios
    List {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Get portfolio by ID
    Get { portfolio_id: String },
    /// Update portfolio
    Update {
        portfolio_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long = "project-id")]
        project_ids: Option<Vec<String>>,
        #[arg(long = "goal-id")]
        goal_ids: Option<Vec<String>>,
        #[arg(long = "objective-id")]
        objective_ids: Option<Vec<String>>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
    },
    /// Portfolio summary
    Summary { portfolio_id: String },
    /// Portfolio dashboard rollups
    Dashboard {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
}

#[derive(Subcommand)]
enum ProgramCommands {
    /// Create a program
    Create {
        name: String,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(long)]
        portfolio_id: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long = "project-id")]
        project_ids: Vec<String>,
        #[arg(long = "goal-id")]
        goal_ids: Vec<String>,
        #[arg(long = "objective-id")]
        objective_ids: Vec<String>,
        #[arg(short = 't', long)]
        tag: Vec<String>,
    },
    /// List programs
    List {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(long)]
        portfolio_id: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Get program by ID
    Get { program_id: String },
    /// Update program
    Update {
        program_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long = "project-id")]
        project_ids: Option<Vec<String>>,
        #[arg(long = "goal-id")]
        goal_ids: Option<Vec<String>>,
        #[arg(long = "objective-id")]
        objective_ids: Option<Vec<String>>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
    },
    /// Program summary
    Summary { program_id: String },
    /// Program dashboard rollups
    Dashboard {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(long)]
        portfolio_id: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
}

#[derive(Subcommand)]
enum ProductCommands {
    /// Create a product
    Create {
        name: String,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(short, long)]
        vision: Option<String>,
    },
    /// List products
    List,
    /// Get product by ID
    Get { product_id: String },
    /// Get product summary with stats
    Summary { product_id: String },
    /// Update a product
    Update {
        product_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        description: Option<String>,
        #[arg(long)]
        vision: Option<String>,
        #[arg(long)]
        repo: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        product_type: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
    },
    /// Archive a product
    Archive { product_id: String },
}

#[derive(Subcommand)]
enum ProjectCommands {
    /// Create a project
    Create {
        name: String,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(long)]
        portfolio_id: Option<String>,
        #[arg(long)]
        program_id: Option<String>,
        #[arg(long)]
        product_id: Option<String>,
    },
    /// List projects
    List {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        limit: Option<u32>,
        #[arg(long)]
        offset: Option<u32>,
    },
    /// Get project by ID
    Get { project_id: String },
    /// Get project summary with stats
    Summary { project_id: String },
    /// Update project
    Update {
        project_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(short, long)]
        description: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(short = 't', long)]
        tag: Option<Vec<String>>,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(long)]
        portfolio_id: Option<String>,
        #[arg(long)]
        program_id: Option<String>,
        #[arg(long)]
        product_id: Option<String>,
    },
    /// Archive a project
    Archive { project_id: String },
    /// Complete a project
    Complete { project_id: String },
    /// Delete (archive) a project
    Delete { project_id: String },
    /// Project revision history
    History {
        project_id: String,
        #[arg(long, default_value = "10")]
        limit: u32,
    },
}

#[derive(Subcommand)]
enum PlanCommands {
    /// Create a plan
    Create {
        name: String,
        #[arg(long)]
        description: Option<String>,
        #[arg(long, default_value = "draft")]
        status: String,
        #[arg(long, default_value = "json")]
        format: String,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        content_file: Option<String>,
        #[arg(long)]
        product_id: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        goal_id: Option<String>,
        #[arg(long)]
        objective_id: Option<String>,
        #[arg(long = "task-id")]
        task_ids: Vec<String>,
        #[arg(long = "tag")]
        tags: Vec<String>,
    },
    /// List plans
    List {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        product_id: Option<String>,
        #[arg(long)]
        goal_id: Option<String>,
        #[arg(long)]
        objective_id: Option<String>,
        #[arg(long)]
        task_id: Option<String>,
        #[arg(long, default_value = "text")]
        format: String,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
    /// Get plan by ID
    Get { plan_id: String },
    /// Update a plan
    Update {
        plan_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        description: Option<String>,
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        format: Option<String>,
        #[arg(long)]
        content: Option<String>,
        #[arg(long)]
        content_file: Option<String>,
        #[arg(long)]
        product_id: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        goal_id: Option<String>,
        #[arg(long)]
        objective_id: Option<String>,
        #[arg(long = "task-id")]
        task_ids: Vec<String>,
        #[arg(long = "tag")]
        tags: Vec<String>,
    },
    /// Plan lineage dashboard
    Lineage {
        #[arg(long)]
        status: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        plan_id: Option<String>,
        #[arg(long, default_value = "50")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
        #[arg(long, default_value = "10")]
        task_limit: u32,
        #[arg(long, default_value = "5")]
        test_limit: u32,
    },
    /// Plan test jobs
    TestJob {
        #[command(subcommand)]
        action: PlanTestJobCommands,
    },
}

#[derive(Subcommand)]
enum PlanTestJobCommands {
    /// Create a plan test job
    Create {
        plan_id: String,
        name: String,
        project_path: String,
        #[arg(long)]
        description: Option<String>,
        #[arg(long, default_value = "local")]
        mode: String,
        #[arg(long)]
        test_command: Option<String>,
        #[arg(long)]
        setup_command: Option<String>,
        #[arg(long)]
        working_dir: Option<String>,
        #[arg(long = "env")]
        env_vars: Vec<String>,
        #[arg(long)]
        timeout: Option<f64>,
        #[arg(long = "capture-log")]
        capture_logs: Vec<String>,
        #[arg(long = "save-artifact")]
        save_artifacts: Vec<String>,
        #[arg(long = "task-id")]
        task_ids: Vec<String>,
        #[arg(long)]
        transition_on_success: Option<String>,
        #[arg(long)]
        transition_on_failure: Option<String>,
        #[arg(long)]
        transition_by: Option<String>,
        #[arg(long)]
        transition_reason: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        server_id: Option<String>,
        #[arg(long)]
        server_name: Option<String>,
        #[arg(long)]
        remote_path: Option<String>,
        #[arg(long = "exclude")]
        exclude_patterns: Vec<String>,
        #[arg(long)]
        stream_output: bool,
    },
    /// List plan test jobs
    List {
        plan_id: String,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
        #[arg(long)]
        include_archived: bool,
    },
    /// Get plan test job by ID
    Get { plan_id: String, job_id: String },
    /// Update a plan test job
    Update {
        plan_id: String,
        job_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        description: Option<String>,
        #[arg(long)]
        mode: Option<String>,
        #[arg(long)]
        project_path: Option<String>,
        #[arg(long)]
        test_command: Option<String>,
        #[arg(long)]
        setup_command: Option<String>,
        #[arg(long)]
        working_dir: Option<String>,
        #[arg(long = "env")]
        env_vars: Vec<String>,
        #[arg(long)]
        timeout: Option<f64>,
        #[arg(long = "capture-log")]
        capture_logs: Vec<String>,
        #[arg(long = "save-artifact")]
        save_artifacts: Vec<String>,
        #[arg(long = "task-id")]
        task_ids: Vec<String>,
        #[arg(long)]
        transition_on_success: Option<String>,
        #[arg(long)]
        transition_on_failure: Option<String>,
        #[arg(long)]
        transition_by: Option<String>,
        #[arg(long)]
        transition_reason: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        server_id: Option<String>,
        #[arg(long)]
        server_name: Option<String>,
        #[arg(long)]
        remote_path: Option<String>,
        #[arg(long = "exclude")]
        exclude_patterns: Vec<String>,
        #[arg(long)]
        stream_output: Option<bool>,
    },
    /// Delete a plan test job
    Delete { plan_id: String, job_id: String },
    /// Restore a plan test job
    Restore { plan_id: String, job_id: String },
    /// Run a plan test job
    Run {
        plan_id: String,
        job_id: String,
        #[arg(long)]
        include_output: bool,
        #[arg(long)]
        include_logs: bool,
        #[arg(long)]
        include_artifacts: bool,
    },
}

#[derive(Subcommand)]
enum QueueCommands {
    /// Create a saved queue
    Create {
        name: String,
        #[arg(long)]
        description: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        scope_type: Option<String>,
        #[arg(long)]
        scope_id: Option<String>,
        #[arg(long)]
        filters: Option<String>,
        #[arg(long)]
        filters_file: Option<String>,
        #[arg(long)]
        sort_by: Option<String>,
        #[arg(long)]
        sort_dir: Option<String>,
    },
    /// List saved queues
    List {
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        scope_type: Option<String>,
        #[arg(long)]
        scope_id: Option<String>,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
        #[arg(long)]
        include_archived: bool,
    },
    /// Get queue by ID
    Get { queue_id: String },
    /// Update a saved queue
    Update {
        queue_id: String,
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        description: Option<String>,
        #[arg(long)]
        owner: Option<String>,
        #[arg(long)]
        scope_type: Option<String>,
        #[arg(long)]
        scope_id: Option<String>,
        #[arg(long)]
        filters: Option<String>,
        #[arg(long)]
        filters_file: Option<String>,
        #[arg(long)]
        sort_by: Option<String>,
        #[arg(long)]
        sort_dir: Option<String>,
    },
    /// Delete a saved queue
    Delete { queue_id: String },
    /// Restore a saved queue
    Restore { queue_id: String },
    /// Run a saved queue
    Run {
        queue_id: String,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
    /// List queue presets
    Presets {
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long, default_value = "5")]
        limit: u32,
        #[arg(long, default_value = "14")]
        stale_days: u32,
        #[arg(long, default_value = "7")]
        at_risk_days: u32,
    },
    /// Get queue preset
    Preset {
        preset: String,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long, default_value = "10")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
        #[arg(long, default_value = "14")]
        stale_days: u32,
        #[arg(long, default_value = "7")]
        at_risk_days: u32,
    },
}

#[derive(Subcommand)]
enum TestRunCommands {
    /// Run local tests and record results
    Run {
        #[arg(default_value = ".")]
        project_path: String,
        #[arg(short = 'c', long = "command", default_value = "pytest")]
        test_command: String,
        #[arg(short = 's', long = "setup")]
        setup_cmd: Option<String>,
        #[arg(short = 'w', long = "workdir")]
        working_dir: Option<String>,
        #[arg(short = 't', long = "timeout", default_value = "600")]
        timeout: f64,
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        plan: Option<String>,
        #[arg(long)]
        plan_id: Option<String>,
        #[arg(long = "task-id")]
        task_ids: Vec<String>,
        #[arg(long = "capture-log")]
        capture_logs: Vec<String>,
        #[arg(long = "save-artifact")]
        save_artifacts: Vec<String>,
        #[arg(long = "env")]
        env_vars: Vec<String>,
        #[arg(long)]
        on_success_state: Option<String>,
        #[arg(long)]
        on_failure_state: Option<String>,
        #[arg(long)]
        transition_by: Option<String>,
        #[arg(long)]
        transition_reason: Option<String>,
        #[arg(long)]
        no_output: bool,
    },
    /// Record a test run without executing tests
    Record {
        #[arg(long)]
        server_id: String,
        #[arg(long, value_parser = ["passed", "failed"])]
        status: String,
        #[arg(long)]
        started_at: String,
        #[arg(long)]
        finished_at: String,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        run_id: Option<String>,
        #[arg(long)]
        exit_code: Option<i32>,
        #[arg(long)]
        duration_seconds: Option<f64>,
        #[arg(long)]
        stdout: Option<String>,
        #[arg(long)]
        stderr: Option<String>,
        #[arg(long)]
        command: Option<String>,
        #[arg(long)]
        runner: Option<String>,
        #[arg(long)]
        plan_id: Option<String>,
        #[arg(long = "task-id")]
        task_ids: Vec<String>,
        #[arg(long)]
        config: Option<String>,
        #[arg(long)]
        config_file: Option<String>,
        #[arg(long)]
        logs: Option<String>,
        #[arg(long)]
        logs_file: Option<String>,
        #[arg(long)]
        artifacts: Option<String>,
        #[arg(long)]
        artifacts_file: Option<String>,
    },
    /// List test runs
    List {
        #[arg(long)]
        server_id: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        success: Option<bool>,
        #[arg(long)]
        include_output: bool,
        #[arg(long)]
        include_logs: bool,
        #[arg(long)]
        include_artifacts: bool,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
    /// Get test run by ID
    #[command(name = "show", alias = "get")]
    Get {
        run_id: String,
        #[arg(long, default_value = "true")]
        include_output: bool,
        #[arg(long, default_value = "true")]
        include_logs: bool,
        #[arg(long, default_value = "true")]
        include_artifacts: bool,
    },
    /// Test run retention summary
    Retention {
        #[arg(long, default_value = "20")]
        limit: u32,
        #[arg(long)]
        sort: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        org_id: Option<String>,
    },
    /// Prune test runs
    Prune {
        #[arg(long)]
        max_log_bytes: Option<u64>,
        #[arg(long)]
        max_artifact_bytes: Option<u64>,
        #[arg(long)]
        max_age_days: Option<u32>,
        #[arg(long)]
        dry_run: bool,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long)]
        org_id: Option<String>,
        #[arg(long, default_value = "true")]
        use_policies: bool,
    },
    /// Retention policy management
    #[command(name = "retention-policy", alias = "policy")]
    Policy {
        #[command(subcommand)]
        action: RetentionPolicyCommands,
    },
    /// Local test-server registration helpers
    Server {
        #[command(subcommand)]
        action: TestServerCommands,
    },
}

#[derive(Subcommand)]
enum TestServerCommands {
    /// Ensure the reusable local test server exists
    #[command(name = "ensure-local")]
    EnsureLocal {
        #[arg(long)]
        project: Option<String>,
        #[arg(long)]
        project_id: Option<String>,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
}

#[derive(Subcommand)]
enum RetentionPolicyCommands {
    /// List retention policies
    List {
        #[arg(long)]
        scope_type: Option<String>,
        #[arg(long)]
        scope_id: Option<String>,
        #[arg(long)]
        include_archived: bool,
        #[arg(long, default_value = "100")]
        limit: u32,
        #[arg(long, default_value = "0")]
        offset: u32,
    },
    /// Get retention policy by ID
    #[command(name = "show", alias = "get")]
    Get { policy_id: String },
    /// Create or update retention policy
    #[command(name = "set", alias = "upsert")]
    Upsert {
        scope_type: String,
        scope_id: String,
        #[arg(long)]
        max_log_bytes: Option<u64>,
        #[arg(long)]
        max_artifact_bytes: Option<u64>,
        #[arg(long)]
        max_age_days: Option<u32>,
        #[arg(long)]
        notes: Option<String>,
    },
    /// Update retention policy by ID
    Update {
        policy_id: String,
        #[arg(long)]
        max_log_bytes: Option<u64>,
        #[arg(long)]
        max_artifact_bytes: Option<u64>,
        #[arg(long)]
        max_age_days: Option<u32>,
        #[arg(long)]
        notes: Option<String>,
    },
    /// Archive retention policy
    Archive { policy_id: String },
    /// Restore retention policy
    Restore { policy_id: String },
}

#[derive(Subcommand)]
enum WorkflowCommands {
    /// List available workflows
    List,
    /// Show workflow details
    Show {
        workflow_ref: String,
        #[arg(long)]
        view: Option<String>,
        #[arg(long, default_value = "text")]
        format: String,
    },
    /// Assign workflow to task
    Assign {
        task_id: String,
        workflow_name: String,
        initial_state: String,
    },
    /// Transition workflow state
    Transition {
        task_id: String,
        to_state: String,
        #[arg(long)]
        by: String,
        #[arg(long)]
        reason: Option<String>,
    },
    /// Align workflow state with entity status
    Align {
        entity_id: String,
        #[arg(long)]
        to_state: Option<String>,
        #[arg(long)]
        by: String,
        #[arg(long)]
        reason: Option<String>,
        #[arg(long)]
        approved_by: Option<String>,
        #[arg(long, default_value = "task")]
        entity_type: String,
        #[arg(long, default_value_t = true)]
        auto: bool,
        #[arg(long)]
        dry_run: bool,
    },
}

#[derive(Subcommand)]
enum RuntimeCommands {
    /// Bootstrap the preferred local server-backed runtime
    #[command(name = "prefer-server")]
    PreferServer {
        #[arg(long, default_value = "127.0.0.1")]
        host: String,
        #[arg(long, default_value_t = 27541)]
        port: u16,
        #[arg(long, default_value_t = true)]
        install_client: bool,
        #[arg(long, default_value_t = true)]
        sign: bool,
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Show managed local PMS server state and runtime coordination status
    #[command(name = "status")]
    Status {
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Clean up tracked managed local PMS servers
    #[command(name = "cleanup")]
    Cleanup {
        #[arg(long, default_value = "text", value_parser = ["text", "json"])]
        format: String,
    },
    /// Stop a managed local PMS server started for the preferred runtime
    #[command(name = "stop-local-server")]
    StopLocalServer {
        #[arg(long, default_value_t = 27541)]
        port: u16,
    },
}

#[derive(Serialize)]
struct CreateTaskRequest {
    project_id: String,
    title: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    parent_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    complexity_points: Option<u8>,
    priority: String,
}

#[derive(Deserialize)]
struct TaskResponse {
    id: String,
    title: String,
    complexity_points: Option<u8>,
    parent_id: Option<String>,
}

#[derive(Serialize)]
struct CheckoutRequest {
    agent_session_id: String,
    lease_seconds: u32,
}

#[derive(Deserialize, Default)]
struct StartOrganizationDashboardTotals {
    #[serde(default)]
    blocked_tasks: u64,
}

#[derive(Deserialize, Default)]
struct StartOrganizationDashboardResponse {
    #[serde(default)]
    totals: StartOrganizationDashboardTotals,
}

#[derive(Deserialize, Default)]
struct StartPageResponse<T> {
    #[serde(default)]
    total_count: u64,
    #[serde(default)]
    items: Vec<T>,
}

#[derive(Deserialize, Default)]
struct StartNamedItem {
    #[serde(default)]
    name: String,
}

#[derive(Deserialize)]
struct StartReadyTaskItem {
    id: String,
    title: String,
    #[serde(default)]
    project_id: Option<String>,
}

#[derive(Deserialize, Default)]
struct StartReadyTaskResponse {
    #[serde(default)]
    total_count: u64,
    #[serde(default)]
    items: Vec<StartReadyTaskItem>,
}

#[derive(Deserialize, Default)]
struct StartTaskSearchItem {
    id: String,
    title: String,
    #[serde(default)]
    project_id: Option<String>,
    #[serde(default)]
    current_progress_percent: Option<u8>,
}

#[derive(Serialize)]
struct StartLiveState {
    organizations: u64,
    portfolios: u64,
    programs: u64,
    projects: u64,
    tasks: u64,
    ready_tasks: u64,
    in_progress_tasks: u64,
    blocked_tasks: u64,
    queue_presets: usize,
    blocked_projects: u64,
    overdue_tasks: u64,
}

#[derive(Serialize)]
struct StartDocs {
    readme: &'static str,
    getting_started: &'static str,
    immediate_start: &'static str,
    capabilities: &'static str,
    workflows: &'static str,
}

#[derive(Serialize)]
struct StartObservabilityPath {
    name: &'static str,
    command: String,
    why: &'static str,
    continue_with: String,
}

#[derive(Serialize)]
struct StartScenarioPath {
    name: &'static str,
    command: &'static str,
    contract: &'static str,
    docs: &'static str,
}

#[derive(Serialize)]
struct StartLinks {
    dashboard: String,
    guide: String,
    quickstart: String,
}

#[derive(Serialize)]
struct StartCliPrefixes {
    canonical_prefix: String,
    alternate_prefix: String,
}

#[derive(Serialize)]
struct StartFocusTask {
    id: String,
    title: String,
    status: String,
    project_id: Option<String>,
    project_name: Option<String>,
    current_progress_percent: Option<u8>,
    reason: String,
}

#[derive(Serialize)]
struct StartGuidePayload {
    generated_at: String,
    purpose: String,
    artifacts_created: Vec<String>,
    live_state: StartLiveState,
    docs: StartDocs,
    observability_paths: Vec<StartObservabilityPath>,
    scenario_paths: Vec<StartScenarioPath>,
    focus_task: Option<StartFocusTask>,
    next_steps: Vec<String>,
    links: StartLinks,
    cli: StartCliPrefixes,
}

fn format_cli_error(server: &str, error: &anyhow::Error) -> String {
    let detail = error.to_string();
    if detail.contains("error sending request for url")
        || detail.contains("tcp connect error")
        || detail.contains("Connection refused")
    {
        return format!(
            "Error: could not reach PMS server at {server}.\n\
Try:\n\
  1. {}\n\
  2. {}\n\
  3. {}",
            cli_command(server, "config show --format json"),
            cli_command(server, "runtime status --format json"),
            cli_command(server, "runtime prefer-server --host 127.0.0.1 --port 27541")
        );
    }
    format!("Error: {}", detail)
}

async fn run_cli(cli: Cli) -> Result<()> {
    let client = reqwest::Client::builder().no_proxy().build()?;

    match cli.command {
        Commands::Auth { action } => {
            handle_auth(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Actor { action } => {
            handle_actor(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Task { action } => {
            handle_task(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Org { action } => {
            handle_org(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Team { action } => {
            handle_team(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Portfolio { action } => {
            handle_portfolio(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Program { action } => {
            handle_program(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Product { action } => {
            handle_product(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Project { action } => {
            handle_project(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Plan { action } => {
            handle_plan(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Queue { action } => {
            handle_queue(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::TestRun { action } => {
            handle_test_run(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Test { action } => {
            handle_test_run(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Workflow { action } => {
            handle_workflow(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Goal { action } => {
            handle_goal(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Objective { action } => {
            handle_objective(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::KeyResult { action } => {
            handle_key_result(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Label { action } => {
            handle_label(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::CustomField { action } => {
            handle_custom_field(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Comment { action } => {
            handle_comment(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Watcher { action } => {
            handle_watcher(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Automation { action } => {
            handle_automation(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Evidence { action } => {
            handle_evidence(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Timeline { action } => {
            handle_timeline(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Revision { action } => {
            handle_revision(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Work { action } => {
            handle_work(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Loop { action } => {
            handle_loop(action, &cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Start { format } => {
            handle_start_cmd(&cli.server, &client, cli.api_key.as_deref(), &format).await?
        }
        Commands::Dashboard => {
            handle_dashboard_cmd(&cli.server, &client, cli.api_key.as_deref()).await?
        }
        Commands::Runtime { action } => handle_runtime(action).await?,
        Commands::Health => handle_health(&cli.server, &client, cli.api_key.as_deref()).await?,
    }

    Ok(())
}

#[tokio::main]
async fn main() {
    let cli = Cli::parse();
    let server = cli.server.clone();
    let exit_code = match run_cli(cli).await {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("{}", format_cli_error(&server, &error));
            1
        }
    };
    std::process::exit(exit_code);
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

async fn handle_task(
    action: TaskCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
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
        TaskCommands::Get { task_id } => {
            let resp = add_auth_header(
                client.get(format!("{}/api/v1/tasks/{}", server, task_id)),
                api_key,
            )
            .send()
            .await?;
            let task: serde_json::Value = resp.json().await?;
            println!("Task: {}", task["title"].as_str().unwrap());
        }
        TaskCommands::Resolve { task_ref, project } => {
            handle_task_resolve(server, client, &task_ref, project, api_key).await?;
        }
        TaskCommands::Start {
            task_id,
            by,
            format,
        } => {
            handle_task_start(server, client, &task_id, by, &format, api_key).await?;
        }
        TaskCommands::Complete {
            task_id,
            notes,
            by,
            format,
        } => {
            handle_task_complete(server, client, &task_id, notes, by, &format, api_key).await?;
        }
        TaskCommands::Block {
            task_id,
            reason,
            by,
        } => {
            handle_task_block(server, client, &task_id, reason, by, api_key).await?;
        }
        TaskCommands::Unblock { task_id, by } => {
            handle_task_unblock(server, client, &task_id, by, api_key).await?;
        }
        TaskCommands::Review { task_id, by } => {
            handle_task_review(server, client, &task_id, by, api_key).await?;
        }
        TaskCommands::Reopen { task_id, by } => {
            handle_task_reopen(server, client, &task_id, by, api_key).await?;
        }
        TaskCommands::Delete {
            task_id,
            reason,
            by,
        } => {
            handle_task_cancel(server, client, &task_id, reason, by, api_key).await?;
        }
        TaskCommands::Release { task_id, agent_id } => {
            add_auth_header(
                client.post(format!(
                    "{}/api/v1/tasks/{}/checkout/release?agent_session_id={}",
                    server, task_id, agent_id
                )),
                api_key,
            )
            .send()
            .await?;
            println!("✓ Released checkout");
        }
        TaskCommands::Renew { task_id, agent_id } => {
            add_auth_header(
                client.post(format!(
                    "{}/api/v1/tasks/{}/checkout/renew?agent_session_id={}",
                    server, task_id, agent_id
                )),
                api_key,
            )
            .send()
            .await?;
            println!("✓ Renewed checkout");
        }
        TaskCommands::Available {
            project,
            project_id,
        } => {
            let resolved_project_id = resolve_project_id(
                server,
                client,
                project.as_deref(),
                project_id.as_deref(),
                api_key,
            )
            .await?;
            let url = if let Some(pid) = resolved_project_id {
                format!("{}/api/v1/checkout/available?project_id={}", server, pid)
            } else {
                format!("{}/api/v1/checkout/available", server)
            };
            let resp = add_auth_header(client.get(&url), api_key).send().await?;
            let result: serde_json::Value = resp.json().await?;
            let tasks = result["available_tasks"].as_array().unwrap();
            println!("Available tasks ({}):", tasks.len());
            for task in tasks {
                println!(
                    "  • {} - {}",
                    task["title"].as_str().unwrap(),
                    task["id"].as_str().unwrap()
                );
            }
        }
        TaskCommands::Timeline { task_id } => {
            let resp = add_auth_header(
                client.get(format!(
                    "{}/api/v1/tasks/{}/progress/timeline",
                    server, task_id
                )),
                api_key,
            )
            .send()
            .await?;
            let timeline: serde_json::Value = resp.json().await?;
            println!("Timeline: {}% complete", timeline["current_percent"]);
        }
        TaskCommands::Search {
            query,
            project_id,
            status,
            priority,
            assignee,
            tag,
            label_id,
            label_category_id,
            created_from,
            created_to,
            updated_from,
            updated_to,
            due_from,
            due_to,
            include_terminal,
            sort_by,
            sort_dir,
            limit,
            offset,
        } => {
            handle_task_search(
                server,
                client,
                query,
                project_id,
                status,
                priority,
                assignee,
                tag,
                label_id,
                label_category_id,
                created_from,
                created_to,
                updated_from,
                updated_to,
                due_from,
                due_to,
                include_terminal,
                sort_by,
                sort_dir,
                limit,
                offset,
                api_key,
            )
            .await?;
        }
        TaskCommands::Ready {
            project_id,
            status,
            exclude_checked_out,
            limit,
            offset,
        } => {
            handle_task_ready(
                server,
                client,
                project_id,
                status,
                exclude_checked_out,
                limit,
                offset,
                api_key,
            )
            .await?;
        }
        TaskCommands::Stale {
            project_id,
            status,
            stale_after_days,
            updated_before,
            include_terminal,
            limit,
            offset,
        } => {
            handle_task_stale(
                server,
                client,
                project_id,
                status,
                stale_after_days,
                updated_before,
                include_terminal,
                limit,
                offset,
                api_key,
            )
            .await?;
        }
        TaskCommands::Blocked { project_id } => {
            handle_task_blocked(server, client, project_id, api_key).await?;
        }
        TaskCommands::Duplicates {
            project_id,
            status,
            include_terminal,
            min_count,
            limit,
            offset,
        } => {
            handle_task_duplicates(
                server,
                client,
                project_id,
                status,
                include_terminal,
                min_count,
                limit,
                offset,
                api_key,
            )
            .await?;
        }
        TaskCommands::DuplicatesPreview {
            primary_task_id,
            duplicate_task_id,
        } => {
            let req = DuplicateMergePreviewRequest {
                primary_task_id,
                duplicate_task_ids: duplicate_task_id,
            };
            handle_task_duplicates_preview(server, client, req, api_key).await?;
        }
        TaskCommands::DuplicatesMerge {
            primary_task_id,
            duplicate_task_id,
            cancel_duplicates,
        } => {
            let req = DuplicateMergeRequest {
                primary_task_id,
                duplicate_task_ids: duplicate_task_id,
                cancel_duplicates: Some(cancel_duplicates),
            };
            handle_task_duplicates_merge(server, client, req, api_key).await?;
        }
        TaskCommands::Evidence { action } => {
            handle_task_evidence_cmd(action, server, client, api_key).await?;
        }
        TaskCommands::ProofBundle {
            task_id,
            include_output,
            include_logs,
            include_artifacts,
        } => {
            handle_task_proof_bundle(
                server,
                client,
                &task_id,
                include_output,
                include_logs,
                include_artifacts,
                api_key,
            )
            .await?;
        }
        TaskCommands::ProofBundleSearch {
            task_id,
            plan_id,
            status,
            evidence_type,
            created_from,
            created_to,
            include_evidence,
            include_test_runs,
            include_output,
            include_logs,
            include_artifacts,
            limit,
            offset,
        } => {
            handle_evidence_bundle_search(
                server,
                client,
                task_id,
                plan_id,
                status,
                evidence_type,
                created_from,
                created_to,
                include_evidence,
                include_test_runs,
                include_output,
                include_logs,
                include_artifacts,
                limit,
                offset,
                api_key,
            )
            .await?;
        }
        TaskCommands::Dep { action } => match action {
            TaskDependencyCommands::Add {
                task_id,
                depends_on_id,
                dependency_type,
            } => {
                handle_task_dependency_add(
                    server,
                    client,
                    &task_id,
                    &depends_on_id,
                    dependency_type,
                    api_key,
                )
                .await?;
            }
            TaskDependencyCommands::Remove {
                task_id,
                depends_on_id,
            } => {
                handle_task_dependency_remove(server, client, &task_id, &depends_on_id, api_key)
                    .await?;
            }
        },
        TaskCommands::Graph { task_id } => {
            handle_task_graph(server, client, &task_id, api_key).await?;
        }
        TaskCommands::Tree {
            project_id,
            root_task_id,
        } => {
            handle_task_tree(server, client, project_id, root_task_id, api_key).await?;
        }
        TaskCommands::Update {
            task_id,
            title,
            description,
            parent_id,
            clear_parent,
            priority,
            complexity_points,
        } => {
            if clear_parent && parent_id.is_some() {
                bail!("Use --parent-id or --clear-parent, not both");
            }
            let mut payload = serde_json::Map::new();
            if let Some(value) = title {
                payload.insert("title".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = parent_id {
                payload.insert("parent_id".to_string(), serde_json::json!(value));
            }
            if clear_parent {
                payload.insert("clear_parent".to_string(), serde_json::json!(true));
            }
            if let Some(value) = priority {
                payload.insert("priority".to_string(), serde_json::json!(value));
            }
            if let Some(value) = complexity_points {
                payload.insert("complexity_points".to_string(), serde_json::json!(value));
            }
            let resp = add_auth_header(
                client
                    .patch(format!("{}/api/v1/tasks/{}", server, task_id))
                    .json(&serde_json::Value::Object(payload)),
                api_key,
            )
            .send()
            .await?;
            let task: serde_json::Value = resp.json().await?;
            println!(
                "✓ Updated task: {} ({})",
                task["title"].as_str().unwrap_or("-"),
                task["id"].as_str().unwrap_or("-")
            );
        }
        TaskCommands::CheckoutStatus {
            agent_id,
            include_expired,
        } => {
            let resp = add_auth_header(
                client
                    .get(format!("{}/api/v1/checkout/status", server))
                    .query(&[
                        ("agent_session_id", agent_id.as_str()),
                        (
                            "include_expired",
                            if include_expired { "true" } else { "false" },
                        ),
                    ]),
                api_key,
            )
            .send()
            .await?;
            let result: serde_json::Value = resp.json().await?;
            let empty: Vec<serde_json::Value> = Vec::new();
            let checkouts = result["checkouts"].as_array().unwrap_or(&empty);
            println!("Checkouts for {} ({}):", agent_id, checkouts.len());
            for item in checkouts {
                println!(
                    "  • {} - {}",
                    item["title"].as_str().unwrap_or("-"),
                    item["id"].as_str().unwrap_or("-")
                );
            }
        }
        TaskCommands::CheckoutLog {
            task_id,
            agent_id,
            action,
            success,
            limit,
            offset,
            include_metadata,
        } => {
            let mut params: Vec<(&str, String)> = Vec::new();
            if let Some(value) = task_id {
                params.push(("task_id", value));
            }
            if let Some(value) = agent_id {
                params.push(("agent_session_id", value));
            }
            if let Some(value) = action {
                params.push(("action", value));
            }
            if let Some(value) = success {
                params.push(("success", value.to_string()));
            }
            params.push(("limit", limit.to_string()));
            params.push(("offset", offset.to_string()));
            params.push(("include_metadata", include_metadata.to_string()));

            let resp = add_auth_header(
                client
                    .get(format!("{}/api/v1/checkout/log", server))
                    .query(&params),
                api_key,
            )
            .send()
            .await?;
            let result: serde_json::Value = resp.json().await?;
            let empty: Vec<serde_json::Value> = Vec::new();
            let entries = result["entries"].as_array().unwrap_or(&empty);
            println!("Checkout log entries ({}):", entries.len());
            for entry in entries {
                println!(
                    "  • {} {} {}",
                    entry["timestamp"].as_str().unwrap_or("-"),
                    entry["action"].as_str().unwrap_or("-"),
                    entry["task_id"].as_str().unwrap_or("-")
                );
            }
        }
        TaskCommands::CheckoutCleanup { dry_run } => {
            let resp = add_auth_header(
                client
                    .post(format!("{}/api/v1/checkout/cleanup", server))
                    .query(&[("dry_run", if dry_run { "true" } else { "false" })]),
                api_key,
            )
            .send()
            .await?;
            let result: serde_json::Value = resp.json().await?;
            let count = result["count"].as_u64().unwrap_or(0);
            if dry_run {
                println!("Would clean up {} expired checkout(s).", count);
            } else {
                println!("Cleaned up {} expired checkout(s).", count);
            }
        }
        TaskCommands::ForceRelease {
            task_id,
            released_by,
            reason,
        } => {
            let mut params: Vec<(&str, String)> = Vec::new();
            if let Some(value) = released_by {
                params.push(("released_by", value));
            }
            if let Some(value) = reason {
                params.push(("reason", value));
            }
            let resp = add_auth_header(
                client
                    .post(format!(
                        "{}/api/v1/tasks/{}/checkout/force-release",
                        server, task_id
                    ))
                    .query(&params),
                api_key,
            )
            .send()
            .await?;
            let result: serde_json::Value = resp.json().await?;
            println!(
                "✓ Force released checkout: {} ({})",
                result["task_id"].as_str().unwrap_or(&task_id),
                result["released_by"].as_str().unwrap_or("system")
            );
        }
        TaskCommands::Create {
            project_id,
            title,
            parent_id,
            complexity,
            priority,
        } => {
            let req = CreateTaskRequest {
                project_id: project_id.clone(),
                title: title.clone(),
                parent_id,
                complexity_points: complexity,
                priority,
            };

            let resp = add_auth_header(
                client.post(format!("{}/api/v1/tasks", server)).json(&req),
                api_key,
            )
            .send()
            .await?;

            let task: TaskResponse = resp.json().await?;

            println!("✓ Created task: {}", task.title);
            println!("  ID: {}", task.id);
            if let Some(c) = task.complexity_points {
                println!("  Complexity: {} points", c);
            }
            if let Some(parent) = task.parent_id {
                println!("  Parent: {}", parent);
            }
        }

        TaskCommands::Checkout {
            task_id,
            agent_id,
            lease,
        } => {
            let req = CheckoutRequest {
                agent_session_id: agent_id.clone(),
                lease_seconds: lease,
            };

            let resp = add_auth_header(
                client
                    .post(format!("{}/api/v1/tasks/{}/checkout", server, task_id))
                    .json(&req),
                api_key,
            )
            .send()
            .await?;
            if !resp.status().is_success() {
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
                let mut message = if detail.is_empty() {
                    format!("Failed to checkout task {} ({})", task_id, status)
                } else {
                    format!(
                        "Failed to checkout task {} ({}): {}",
                        task_id, status, detail
                    )
                };
                if status.as_u16() == 409 {
                    message.push_str(&format!(
                        "\nNext:\n- {}\n- {}\n- {}",
                        cli_command(
                            server,
                            &format!("task checkout-status --agent-id {}", agent_id)
                        ),
                        cli_command(server, &format!("task show {}", task_id)),
                        cli_command(
                            server,
                            &format!(
                                "task force-release {} --released-by <user> --reason <reason>",
                                task_id
                            ),
                        )
                    ));
                } else if status.as_u16() == 423 {
                    message.push_str(&format!(
                        "\nNext:\n- {}\n- {}\n- {}",
                        cli_command(server, &format!("task graph {}", task_id)),
                        cli_command(server, &format!("task show {}", task_id)),
                        cli_command(server, "task blocked --format json")
                    ));
                }
                bail!(message);
            }

            let result: serde_json::Value = resp.json().await?;

            println!("✓ Checked out task {}", task_id);
            println!("  Agent: {}", agent_id);
            println!(
                "  Until: {}",
                result["checkout"]["lease_until"].as_str().unwrap_or("?")
            );
        }

        TaskCommands::Progress {
            task_id,
            percent,
            message,
            by,
            format,
        } => {
            let req = serde_json::json!({
                "percent_complete": percent,
                "status_message": message,
                "updated_by": by,
            });

            let resp = add_auth_header(
                client
                    .post(format!("{}/api/v1/tasks/{}/progress", server, task_id))
                    .json(&req),
                api_key,
            )
            .send()
            .await?;
            if !resp.status().is_success() {
                return Err(anyhow::anyhow!(
                    "Failed to update task progress ({})",
                    resp.status()
                ));
            }

            if format == "json" {
                let task = fetch_task_detail(server, client, &task_id, api_key).await?;
                let payload = serde_json::json!({
                    "task": task,
                    "progress": {
                        "percent": percent,
                        "message": message,
                        "updated_by": by,
                    },
                    "links": task_mutation_links(server, &task_id, true),
                    "next_steps": vec![
                        cli_command(server, &format!("task show {}", task_id)),
                        cli_command(server, &format!("task review {} --by {}", task_id, by)),
                        cli_command(server, &format!("task complete {} --by {}", task_id, by)),
                    ],
                    "cli": {
                        "canonical_prefix": cli_command_prefix(server),
                        "alternate_prefix": current_rust_cli_prefix(server),
                    },
                });
                println!("{}", serde_json::to_string_pretty(&payload)?);
            } else {
                println!("✓ Updated progress: {}%", percent);
                println!("  {}", message);
            }
        }
    }

    Ok(())
}

fn parse_kv_pairs(pairs: Vec<String>) -> Result<std::collections::HashMap<String, String>> {
    let mut map = std::collections::HashMap::new();
    for pair in pairs {
        let mut parts = pair.splitn(2, '=');
        let key = parts.next().unwrap_or("").trim();
        let value = parts.next().unwrap_or("").trim();
        if key.is_empty() {
            return Err(anyhow::anyhow!("Metadata must use key=value format"));
        }
        map.insert(key.to_string(), value.to_string());
    }
    Ok(map)
}

fn parse_json_input(
    value: Option<String>,
    file: Option<String>,
    label: &str,
) -> Result<Option<serde_json::Value>> {
    if value.is_some() && file.is_some() {
        bail!("Use --{} or --{}-file, not both", label, label);
    }
    let raw = if let Some(path) = file {
        fs::read_to_string(path)?
    } else if let Some(text) = value {
        text
    } else {
        return Ok(None);
    };
    let parsed: serde_json::Value = serde_json::from_str(&raw)
        .map_err(|err| anyhow::anyhow!("Invalid {} JSON: {}", label, err))?;
    if !parsed.is_object() {
        bail!("{} must be a JSON object", label);
    }
    Ok(Some(parsed))
}

fn parse_env_pairs(pairs: Vec<String>) -> Result<Vec<EnvVarPair>> {
    let mut result = Vec::new();
    for pair in pairs {
        let mut parts = pair.splitn(2, '=');
        let key = parts.next().unwrap_or("").trim();
        if key.is_empty() {
            return Err(anyhow::anyhow!("Env vars must use KEY=VALUE format"));
        }
        let value = parts.next().unwrap_or("").to_string();
        result.push(EnvVarPair {
            key: key.to_string(),
            value,
        });
    }
    Ok(result)
}

fn parse_json_value(raw: &str, label: &str) -> Result<serde_json::Value> {
    serde_json::from_str(raw).map_err(|err| anyhow::anyhow!("Invalid {} JSON: {}", label, err))
}

fn load_text_arg(
    value: Option<String>,
    file: Option<String>,
    label: &str,
) -> Result<Option<String>> {
    if value.is_some() && file.is_some() {
        return Err(anyhow::anyhow!(
            "Use --{} or --{}-file, not both",
            label,
            label
        ));
    }
    if let Some(path) = file {
        let data = std::fs::read_to_string(path)?;
        return Ok(Some(data));
    }
    Ok(value)
}

fn parse_content_value(raw: &str) -> serde_json::Value {
    serde_json::from_str(raw).unwrap_or_else(|_| serde_json::Value::String(raw.to_string()))
}

async fn handle_task_evidence_cmd(
    action: TaskEvidenceCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        TaskEvidenceCommands::Add {
            task_id,
            evidence_type,
            reference,
            description,
            metadata,
            metadata_file,
            created_by,
        } => {
            let metadata_text = load_text_arg(metadata, metadata_file, "metadata")?;
            let metadata_value = match metadata_text {
                Some(text) => Some(parse_json_value(&text, "metadata")?),
                None => None,
            };
            handle_task_evidence_add(
                server,
                client,
                &task_id,
                &evidence_type,
                &reference,
                description,
                metadata_value,
                created_by,
                api_key,
            )
            .await
        }
        TaskEvidenceCommands::List {
            task_id,
            include_test_runs,
            include_output,
            limit,
            offset,
        } => {
            handle_task_evidence(
                server,
                client,
                &task_id,
                include_test_runs,
                include_output,
                limit,
                offset,
                api_key,
            )
            .await
        }
    }
}

async fn handle_auth(
    action: AuthCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        AuthCommands::Scopes => handle_auth_scopes(server, client, api_key).await,
        AuthCommands::Init { name, show_key } => {
            handle_auth_init(server, client, name, show_key).await
        }
        AuthCommands::RecoverLocalAdmin { name, show_key } => {
            handle_auth_recover_local_admin(name, show_key).await
        }
        AuthCommands::Keys { action } => match action {
            KeyCommands::Create {
                name,
                scope,
                expires_in_days,
                rate_limit,
                metadata,
            } => {
                let metadata_map = parse_kv_pairs(metadata)?;
                handle_api_key_create(
                    server,
                    client,
                    name,
                    scope,
                    expires_in_days,
                    rate_limit,
                    metadata_map,
                    api_key,
                )
                .await
            }
            KeyCommands::List {
                include_inactive,
                include_archived,
            } => {
                handle_api_key_list(server, client, include_inactive, include_archived, api_key)
                    .await
            }
            KeyCommands::Get { key_id } => {
                handle_api_key_get(server, client, &key_id, api_key).await
            }
            KeyCommands::Deactivate { key_id } => {
                handle_api_key_deactivate(server, client, &key_id, api_key).await
            }
            KeyCommands::Restore { key_id } => {
                handle_api_key_restore(server, client, &key_id, api_key).await
            }
            KeyCommands::Delete { key_id } => {
                handle_api_key_delete(server, client, &key_id, api_key).await
            }
        },
    }
}

async fn handle_actor(
    action: ActorCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        ActorCommands::Create {
            name,
            kind,
            handle,
            description,
            tag,
            format,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "kind": kind,
                "handle": handle,
                "description": description,
                "tags": tag,
                "metadata": {},
            });
            handle_actor_create(server, client, payload, &format, api_key).await
        }
        ActorCommands::List {
            kind,
            status,
            format,
            limit,
            offset,
        } => {
            handle_actor_list(
                server, client, kind, status, limit, offset, &format, api_key,
            )
            .await
        }
        ActorCommands::Show { actor, format } => {
            handle_actor_show(server, client, &actor, &format, api_key).await
        }
        ActorCommands::Alias { action } => match action {
            ActorAliasCommands::Add {
                actor,
                alias_value,
                format,
            } => {
                handle_actor_alias_add(server, client, &actor, &alias_value, &format, api_key).await
            }
        },
        ActorCommands::Membership { action } => match action {
            ActorMembershipCommands::Add {
                parent,
                member,
                role,
                format,
            } => {
                handle_actor_membership_add(
                    server, client, &parent, &member, &role, &format, api_key,
                )
                .await
            }
        },
    }
}

async fn handle_runtime(action: RuntimeCommands) -> Result<()> {
    match action {
        RuntimeCommands::PreferServer {
            host,
            port,
            install_client,
            sign,
            format,
        } => handle_runtime_prefer_server(host, port, install_client, sign, format).await,
        RuntimeCommands::Status { format } => handle_runtime_status(format).await,
        RuntimeCommands::Cleanup { format } => handle_runtime_cleanup(format).await,
        RuntimeCommands::StopLocalServer { port } => handle_runtime_stop_local_server(port).await,
    }
}

async fn handle_goal(
    action: GoalCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        GoalCommands::Create {
            name,
            horizon,
            description,
            target_date,
            owner,
            product_id,
            project_id,
            tag,
            progress,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "horizon": horizon,
                "description": description,
                "target_date": target_date,
                "owner": owner,
                "product_id": product_id,
                "project_id": project_id,
                "tags": tag,
                "progress_percent": progress,
            });
            handle_goal_create(server, client, payload, api_key).await
        }
        GoalCommands::List {
            status,
            horizon,
            product_id,
            project_id,
            limit,
            offset,
        } => {
            handle_goal_list(
                server, client, status, horizon, product_id, project_id, limit, offset, api_key,
            )
            .await
        }
        GoalCommands::Get { goal_id } => handle_goal_get(server, client, &goal_id, api_key).await,
        GoalCommands::Update {
            goal_id,
            name,
            description,
            status,
            horizon,
            target_date,
            owner,
            product_id,
            project_id,
            tag,
            progress,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = status {
                payload.insert("status".to_string(), serde_json::json!(value));
            }
            if let Some(value) = horizon {
                payload.insert("horizon".to_string(), serde_json::json!(value));
            }
            if let Some(value) = target_date {
                payload.insert("target_date".to_string(), serde_json::json!(value));
            }
            if let Some(value) = owner {
                payload.insert("owner".to_string(), serde_json::json!(value));
            }
            if let Some(value) = product_id {
                payload.insert("product_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = project_id {
                payload.insert("project_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = tag {
                payload.insert("tags".to_string(), serde_json::json!(value));
            }
            if let Some(value) = progress {
                payload.insert("progress_percent".to_string(), serde_json::json!(value));
            }
            handle_goal_update(
                server,
                client,
                &goal_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
        GoalCommands::Complete { goal_id } => {
            handle_goal_complete(server, client, &goal_id, api_key).await
        }
        GoalCommands::Archive { goal_id } => {
            handle_goal_archive(server, client, &goal_id, api_key).await
        }
        GoalCommands::Summary { goal_id } => {
            handle_goal_summary(server, client, &goal_id, api_key).await
        }
        GoalCommands::WorkflowAssign {
            goal_id,
            workflow_name,
            initial_state,
        } => {
            handle_goal_workflow_assign(
                server,
                client,
                &goal_id,
                &workflow_name,
                &initial_state,
                api_key,
            )
            .await
        }
        GoalCommands::WorkflowTransition {
            goal_id,
            to_state,
            by,
            reason,
            approved_by,
        } => {
            handle_goal_workflow_transition(
                server,
                client,
                &goal_id,
                &to_state,
                &by,
                reason,
                approved_by,
                api_key,
            )
            .await
        }
    }
}

async fn handle_objective(
    action: ObjectiveCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        ObjectiveCommands::Create {
            goal_id,
            name,
            description,
            target_date,
            owner,
            tag,
            progress,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "description": description,
                "target_date": target_date,
                "owner": owner,
                "tags": tag,
                "progress_percent": progress,
            });
            handle_objective_create(server, client, &goal_id, payload, api_key).await
        }
        ObjectiveCommands::List {
            goal_id,
            status,
            limit,
            offset,
        } => handle_objective_list(server, client, &goal_id, status, limit, offset, api_key).await,
        ObjectiveCommands::Get { objective_id } => {
            handle_objective_get(server, client, &objective_id, api_key).await
        }
        ObjectiveCommands::Update {
            objective_id,
            name,
            description,
            status,
            target_date,
            owner,
            tag,
            progress,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = status {
                payload.insert("status".to_string(), serde_json::json!(value));
            }
            if let Some(value) = target_date {
                payload.insert("target_date".to_string(), serde_json::json!(value));
            }
            if let Some(value) = owner {
                payload.insert("owner".to_string(), serde_json::json!(value));
            }
            if let Some(value) = tag {
                payload.insert("tags".to_string(), serde_json::json!(value));
            }
            if let Some(value) = progress {
                payload.insert("progress_percent".to_string(), serde_json::json!(value));
            }
            handle_objective_update(
                server,
                client,
                &objective_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
        ObjectiveCommands::Complete { objective_id } => {
            handle_objective_complete(server, client, &objective_id, api_key).await
        }
        ObjectiveCommands::Archive { objective_id } => {
            handle_objective_archive(server, client, &objective_id, api_key).await
        }
        ObjectiveCommands::WorkflowAssign {
            objective_id,
            workflow_name,
            initial_state,
        } => {
            handle_objective_workflow_assign(
                server,
                client,
                &objective_id,
                &workflow_name,
                &initial_state,
                api_key,
            )
            .await
        }
        ObjectiveCommands::WorkflowTransition {
            objective_id,
            to_state,
            by,
            reason,
            approved_by,
        } => {
            handle_objective_workflow_transition(
                server,
                client,
                &objective_id,
                &to_state,
                &by,
                reason,
                approved_by,
                api_key,
            )
            .await
        }
    }
}

async fn handle_key_result(
    action: KeyResultCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        KeyResultCommands::Create {
            objective_id,
            name,
            description,
            current_value,
            target_value,
            unit,
            owner,
            tag,
            progress,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "description": description,
                "current_value": current_value,
                "target_value": target_value,
                "unit": unit,
                "owner": owner,
                "tags": tag,
                "progress_percent": progress,
            });
            handle_key_result_create(server, client, &objective_id, payload, api_key).await
        }
        KeyResultCommands::List {
            objective_id,
            status,
            limit,
            offset,
        } => {
            handle_key_result_list(
                server,
                client,
                &objective_id,
                status,
                limit,
                offset,
                api_key,
            )
            .await
        }
        KeyResultCommands::Get { key_result_id } => {
            handle_key_result_get(server, client, &key_result_id, api_key).await
        }
        KeyResultCommands::Update {
            key_result_id,
            name,
            description,
            status,
            current_value,
            target_value,
            unit,
            owner,
            tag,
            progress,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = status {
                payload.insert("status".to_string(), serde_json::json!(value));
            }
            if let Some(value) = current_value {
                payload.insert("current_value".to_string(), serde_json::json!(value));
            }
            if let Some(value) = target_value {
                payload.insert("target_value".to_string(), serde_json::json!(value));
            }
            if let Some(value) = unit {
                payload.insert("unit".to_string(), serde_json::json!(value));
            }
            if let Some(value) = owner {
                payload.insert("owner".to_string(), serde_json::json!(value));
            }
            if let Some(value) = tag {
                payload.insert("tags".to_string(), serde_json::json!(value));
            }
            if let Some(value) = progress {
                payload.insert("progress_percent".to_string(), serde_json::json!(value));
            }
            handle_key_result_update(
                server,
                client,
                &key_result_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
        KeyResultCommands::Complete { key_result_id } => {
            handle_key_result_complete(server, client, &key_result_id, api_key).await
        }
        KeyResultCommands::Archive { key_result_id } => {
            handle_key_result_archive(server, client, &key_result_id, api_key).await
        }
    }
}

async fn handle_label(
    action: LabelCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        LabelCommands::Create {
            name,
            description,
            category_id,
            color,
            system,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "description": description,
                "category_id": category_id,
                "color": color,
                "is_system": system,
            });
            handle_label_create(server, client, payload, api_key).await
        }
        LabelCommands::List {
            category_id,
            include_archived,
        } => handle_label_list(server, client, category_id, include_archived, api_key).await,
        LabelCommands::Get { label_id } => {
            handle_label_get(server, client, &label_id, api_key).await
        }
        LabelCommands::Update {
            label_id,
            name,
            description,
            category_id,
            color,
            system,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = category_id {
                payload.insert("category_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = color {
                payload.insert("color".to_string(), serde_json::json!(value));
            }
            if let Some(value) = system {
                payload.insert("is_system".to_string(), serde_json::json!(value));
            }
            handle_label_update(
                server,
                client,
                &label_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
        LabelCommands::Delete { label_id } => {
            handle_label_delete(server, client, &label_id, api_key).await
        }
        LabelCommands::Restore { label_id } => {
            handle_label_restore(server, client, &label_id, api_key).await
        }
        LabelCommands::Category { action } => match action {
            LabelCategoryCommands::Create {
                name,
                description,
                exclusive,
                sort_order,
            } => {
                let payload = serde_json::json!({
                    "name": name,
                    "description": description,
                    "is_exclusive": exclusive,
                    "sort_order": sort_order,
                });
                handle_label_category_create(server, client, payload, api_key).await
            }
            LabelCategoryCommands::List { include_archived } => {
                handle_label_category_list(server, client, include_archived, api_key).await
            }
            LabelCategoryCommands::Get { category_id } => {
                handle_label_category_get(server, client, &category_id, api_key).await
            }
            LabelCategoryCommands::Update {
                category_id,
                name,
                description,
                exclusive,
                sort_order,
            } => {
                let mut payload = serde_json::Map::new();
                if let Some(value) = name {
                    payload.insert("name".to_string(), serde_json::json!(value));
                }
                if let Some(value) = description {
                    payload.insert("description".to_string(), serde_json::json!(value));
                }
                if let Some(value) = exclusive {
                    payload.insert("is_exclusive".to_string(), serde_json::json!(value));
                }
                if let Some(value) = sort_order {
                    payload.insert("sort_order".to_string(), serde_json::json!(value));
                }
                handle_label_category_update(
                    server,
                    client,
                    &category_id,
                    serde_json::Value::Object(payload),
                    api_key,
                )
                .await
            }
            LabelCategoryCommands::Delete { category_id } => {
                handle_label_category_delete(server, client, &category_id, api_key).await
            }
            LabelCategoryCommands::Restore { category_id } => {
                handle_label_category_restore(server, client, &category_id, api_key).await
            }
        },
        LabelCommands::Assignment { action } => match action {
            LabelAssignmentCommands::Create {
                entity_type,
                entity_id,
                label_id,
                applied_by,
            } => {
                let payload = serde_json::json!({
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "label_id": label_id,
                    "applied_by": applied_by,
                });
                handle_label_assign(server, client, payload, api_key).await
            }
            LabelAssignmentCommands::List {
                entity_type,
                entity_id,
                limit,
                offset,
            } => {
                handle_label_assignments(
                    server,
                    client,
                    &entity_type,
                    &entity_id,
                    limit,
                    offset,
                    api_key,
                )
                .await
            }
            LabelAssignmentCommands::History {
                assignment_id,
                limit,
                offset,
            } => {
                handle_label_assignment_history(
                    server,
                    client,
                    &assignment_id,
                    limit,
                    offset,
                    api_key,
                )
                .await
            }
            LabelAssignmentCommands::Remove {
                entity_type,
                entity_id,
                label_id,
            } => {
                handle_label_assignment_remove(
                    server,
                    client,
                    &entity_type,
                    &entity_id,
                    &label_id,
                    api_key,
                )
                .await
            }
        },
        LabelCommands::Gate { action } => match action {
            LabelGateCommands::Create {
                workflow_id,
                entity_type,
                from_state,
                to_state,
                rule_type,
                label_id,
                category_id,
                message,
            } => {
                let payload = serde_json::json!({
                    "workflow_id": workflow_id,
                    "entity_type": entity_type,
                    "from_state": from_state,
                    "to_state": to_state,
                    "rule_type": rule_type,
                    "label_id": label_id,
                    "category_id": category_id,
                    "message": message,
                });
                handle_label_gate_create(server, client, payload, api_key).await
            }
            LabelGateCommands::List {
                workflow_id,
                entity_type,
                from_state,
                to_state,
            } => {
                handle_label_gate_list(
                    server,
                    client,
                    &workflow_id,
                    &entity_type,
                    &from_state,
                    &to_state,
                    api_key,
                )
                .await
            }
            LabelGateCommands::Delete { rule_id } => {
                handle_label_gate_delete(server, client, &rule_id, api_key).await
            }
        },
    }
}

async fn handle_custom_field(
    action: CustomFieldCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        CustomFieldCommands::Create {
            name,
            entity_type,
            field_type,
            description,
            option,
            required,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "entity_type": entity_type,
                "field_type": field_type,
                "description": description,
                "options": option,
                "is_required": required,
            });
            handle_custom_field_create(server, client, payload, api_key).await
        }
        CustomFieldCommands::List {
            entity_type,
            include_archived,
        } => handle_custom_field_list(server, client, entity_type, include_archived, api_key).await,
        CustomFieldCommands::Show {
            field_ref,
            entity_type,
        } => handle_custom_field_show(server, client, &field_ref, entity_type, api_key).await,
        CustomFieldCommands::Update {
            field_id,
            name,
            description,
            field_type,
            option,
            required,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = field_type {
                payload.insert("field_type".to_string(), serde_json::json!(value));
            }
            if !option.is_empty() {
                payload.insert("options".to_string(), serde_json::json!(option));
            }
            if let Some(value) = required {
                payload.insert("is_required".to_string(), serde_json::json!(value));
            }
            handle_custom_field_update(
                server,
                client,
                &field_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
        CustomFieldCommands::Delete { field_id } => {
            handle_custom_field_delete(server, client, &field_id, api_key).await
        }
        CustomFieldCommands::Restore { field_id } => {
            handle_custom_field_restore(server, client, &field_id, api_key).await
        }
        CustomFieldCommands::Value { action } => match action {
            CustomFieldValueCommands::Set {
                field_ref,
                entity_type,
                entity_id,
                value,
                value_json,
                created_by,
                source,
                metadata_json,
            } => {
                if value.is_some() && value_json.is_some() {
                    bail!("Use --value or --value-json, not both.");
                }

                let mut payload = serde_json::Map::new();
                payload.insert("entity_type".to_string(), serde_json::json!(entity_type));
                payload.insert("entity_id".to_string(), serde_json::json!(entity_id));
                if let Some(raw) = value {
                    payload.insert("value".to_string(), serde_json::json!(raw));
                } else if let Some(raw) = value_json {
                    let parsed: serde_json::Value = serde_json::from_str(&raw)?;
                    payload.insert("value".to_string(), parsed);
                }
                if let Some(value) = created_by {
                    payload.insert("created_by".to_string(), serde_json::json!(value));
                }
                if let Some(value) = source {
                    payload.insert("source".to_string(), serde_json::json!(value));
                }
                if let Some(raw) = metadata_json {
                    let parsed: serde_json::Value = serde_json::from_str(&raw)?;
                    payload.insert("metadata".to_string(), parsed);
                }

                handle_custom_field_value_set(
                    server,
                    client,
                    &field_ref,
                    serde_json::Value::Object(payload),
                    api_key,
                )
                .await
            }
            CustomFieldValueCommands::List {
                entity_type,
                entity_id,
                field_id,
                include_history,
                limit,
                offset,
            } => {
                handle_custom_field_value_list(
                    server,
                    client,
                    entity_type,
                    entity_id,
                    field_id,
                    include_history,
                    limit,
                    offset,
                    api_key,
                )
                .await
            }
        },
    }
}

async fn handle_comment(
    action: CommentCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        CommentCommands::Add {
            entity_type,
            entity_id,
            body,
            created_by,
            mention,
            metadata_json,
            watch,
        } => {
            let mut payload = serde_json::Map::new();
            payload.insert("entity_type".to_string(), serde_json::json!(entity_type));
            payload.insert("entity_id".to_string(), serde_json::json!(entity_id));
            payload.insert("body".to_string(), serde_json::json!(body));
            payload.insert("created_by".to_string(), serde_json::json!(created_by));
            if !mention.is_empty() {
                payload.insert("mentions".to_string(), serde_json::json!(mention));
            }
            if let Some(raw) = metadata_json {
                let parsed: serde_json::Value = serde_json::from_str(&raw)?;
                payload.insert("metadata".to_string(), parsed);
            }
            if watch {
                payload.insert("watch".to_string(), serde_json::json!(true));
            }
            handle_comment_add(server, client, serde_json::Value::Object(payload), api_key).await
        }
        CommentCommands::List {
            entity_type,
            entity_id,
            include_archived,
            limit,
            offset,
        } => {
            handle_comment_list(
                server,
                client,
                &entity_type,
                &entity_id,
                include_archived,
                limit,
                offset,
                api_key,
            )
            .await
        }
        CommentCommands::Show { comment_id } => {
            handle_comment_show(server, client, &comment_id, api_key).await
        }
        CommentCommands::Delete { comment_id } => {
            handle_comment_delete(server, client, &comment_id, api_key).await
        }
        CommentCommands::Restore { comment_id } => {
            handle_comment_restore(server, client, &comment_id, api_key).await
        }
    }
}

async fn handle_watcher(
    action: WatcherCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        WatcherCommands::Add {
            entity_type,
            entity_id,
            watcher,
        } => {
            let payload = serde_json::json!({
                "entity_type": entity_type,
                "entity_id": entity_id,
                "watcher": watcher,
            });
            handle_watcher_add(server, client, payload, api_key).await
        }
        WatcherCommands::List {
            entity_type,
            entity_id,
            include_archived,
            limit,
            offset,
        } => {
            handle_watcher_list(
                server,
                client,
                &entity_type,
                &entity_id,
                include_archived,
                limit,
                offset,
                api_key,
            )
            .await
        }
        WatcherCommands::Remove {
            entity_type,
            entity_id,
            watcher,
        } => {
            handle_watcher_remove(server, client, &entity_type, &entity_id, &watcher, api_key).await
        }
        WatcherCommands::Restore { watcher_id } => {
            handle_watcher_restore(server, client, &watcher_id, api_key).await
        }
    }
}

async fn handle_automation(
    action: AutomationCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        AutomationCommands::Rule { action } => match action {
            AutomationRuleCommands::Create {
                name,
                event_pattern,
                action_type,
                action_payload_json,
                description,
                aggregate_type,
                aggregate_id,
                enabled,
                cooldown_seconds,
            } => {
                let payload: serde_json::Value = serde_json::from_str(&action_payload_json)?;
                let req = serde_json::json!({
                    "name": name,
                    "event_pattern": event_pattern,
                    "action_type": action_type,
                    "action_payload": payload,
                    "description": description,
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "enabled": enabled,
                    "cooldown_seconds": cooldown_seconds,
                });
                handle_automation_rule_create(server, client, req, api_key).await
            }
            AutomationRuleCommands::List {
                include_archived,
                enabled,
            } => {
                handle_automation_rule_list(server, client, include_archived, enabled, api_key)
                    .await
            }
            AutomationRuleCommands::Show { rule_id } => {
                handle_automation_rule_show(server, client, &rule_id, api_key).await
            }
            AutomationRuleCommands::Update {
                rule_id,
                name,
                event_pattern,
                action_type,
                action_payload_json,
                description,
                aggregate_type,
                aggregate_id,
                enabled,
                cooldown_seconds,
            } => {
                let mut payload = serde_json::Map::new();
                if let Some(value) = name {
                    payload.insert("name".to_string(), serde_json::json!(value));
                }
                if let Some(value) = event_pattern {
                    payload.insert("event_pattern".to_string(), serde_json::json!(value));
                }
                if let Some(value) = action_type {
                    payload.insert("action_type".to_string(), serde_json::json!(value));
                }
                if let Some(raw) = action_payload_json {
                    let parsed: serde_json::Value = serde_json::from_str(&raw)?;
                    payload.insert("action_payload".to_string(), parsed);
                }
                if let Some(value) = description {
                    payload.insert("description".to_string(), serde_json::json!(value));
                }
                if let Some(value) = aggregate_type {
                    payload.insert("aggregate_type".to_string(), serde_json::json!(value));
                }
                if let Some(value) = aggregate_id {
                    payload.insert("aggregate_id".to_string(), serde_json::json!(value));
                }
                if let Some(value) = enabled {
                    payload.insert("enabled".to_string(), serde_json::json!(value));
                }
                if let Some(value) = cooldown_seconds {
                    payload.insert("cooldown_seconds".to_string(), serde_json::json!(value));
                }
                handle_automation_rule_update(
                    server,
                    client,
                    &rule_id,
                    serde_json::Value::Object(payload),
                    api_key,
                )
                .await
            }
            AutomationRuleCommands::Delete { rule_id } => {
                handle_automation_rule_delete(server, client, &rule_id, api_key).await
            }
            AutomationRuleCommands::Restore { rule_id } => {
                handle_automation_rule_restore(server, client, &rule_id, api_key).await
            }
            AutomationRuleCommands::Runs {
                rule_id,
                limit,
                offset,
            } => {
                handle_automation_rule_runs(server, client, &rule_id, limit, offset, api_key).await
            }
        },
        AutomationCommands::Run {
            event_id,
            rule_id,
            dry_run,
        } => {
            let payload = serde_json::json!({
                "event_id": event_id,
                "rule_id": rule_id,
                "dry_run": dry_run,
            });
            handle_automation_run(server, client, payload, api_key).await
        }
    }
}

async fn handle_org(
    action: OrgCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        OrgCommands::Create {
            name,
            description,
            owner,
            member,
            tag,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "description": description,
                "owner": owner,
                "members": member,
                "tags": tag,
            });
            handle_org_create(server, client, payload, api_key).await
        }
        OrgCommands::List {
            status,
            limit,
            offset,
        } => handle_org_list(server, client, status, limit, offset, api_key).await,
        OrgCommands::Get { org_id } => handle_org_get(server, client, &org_id, api_key).await,
        OrgCommands::Update {
            org_id,
            name,
            description,
            status,
            owner,
            member,
            tag,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = status {
                payload.insert("status".to_string(), serde_json::json!(value));
            }
            if let Some(value) = owner {
                payload.insert("owner".to_string(), serde_json::json!(value));
            }
            if let Some(value) = member {
                payload.insert("members".to_string(), serde_json::json!(value));
            }
            if let Some(value) = tag {
                payload.insert("tags".to_string(), serde_json::json!(value));
            }
            handle_org_update(
                server,
                client,
                &org_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
        OrgCommands::Summary { org_id } => {
            handle_org_summary(server, client, &org_id, api_key).await
        }
        OrgCommands::Dashboard {
            status,
            limit,
            offset,
        } => handle_org_dashboard(server, client, status, limit, offset, api_key).await,
    }
}

async fn handle_team(
    action: TeamCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        TeamCommands::Create {
            name,
            org_id,
            description,
            owner,
            member,
            tag,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "org_id": org_id,
                "description": description,
                "owner": owner,
                "members": member,
                "tags": tag,
            });
            handle_team_create(server, client, payload, api_key).await
        }
        TeamCommands::List {
            status,
            org_id,
            limit,
            offset,
        } => handle_team_list(server, client, status, org_id, limit, offset, api_key).await,
        TeamCommands::Get { team_id } => handle_team_get(server, client, &team_id, api_key).await,
        TeamCommands::Update {
            team_id,
            name,
            description,
            status,
            owner,
            member,
            tag,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = status {
                payload.insert("status".to_string(), serde_json::json!(value));
            }
            if let Some(value) = owner {
                payload.insert("owner".to_string(), serde_json::json!(value));
            }
            if let Some(value) = member {
                payload.insert("members".to_string(), serde_json::json!(value));
            }
            if let Some(value) = tag {
                payload.insert("tags".to_string(), serde_json::json!(value));
            }
            handle_team_update(
                server,
                client,
                &team_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
    }
}

async fn handle_portfolio(
    action: PortfolioCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        PortfolioCommands::Create {
            name,
            org_id,
            description,
            owner,
            project_ids,
            goal_ids,
            objective_ids,
            tag,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "org_id": org_id,
                "description": description,
                "owner": owner,
                "project_ids": project_ids,
                "goal_ids": goal_ids,
                "objective_ids": objective_ids,
                "tags": tag,
            });
            handle_portfolio_create(server, client, payload, api_key).await
        }
        PortfolioCommands::List {
            status,
            org_id,
            limit,
            offset,
        } => handle_portfolio_list(server, client, status, org_id, limit, offset, api_key).await,
        PortfolioCommands::Get { portfolio_id } => {
            handle_portfolio_get(server, client, &portfolio_id, api_key).await
        }
        PortfolioCommands::Update {
            portfolio_id,
            name,
            description,
            status,
            owner,
            project_ids,
            goal_ids,
            objective_ids,
            tag,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = status {
                payload.insert("status".to_string(), serde_json::json!(value));
            }
            if let Some(value) = owner {
                payload.insert("owner".to_string(), serde_json::json!(value));
            }
            if let Some(value) = project_ids {
                payload.insert("project_ids".to_string(), serde_json::json!(value));
            }
            if let Some(value) = goal_ids {
                payload.insert("goal_ids".to_string(), serde_json::json!(value));
            }
            if let Some(value) = objective_ids {
                payload.insert("objective_ids".to_string(), serde_json::json!(value));
            }
            if let Some(value) = tag {
                payload.insert("tags".to_string(), serde_json::json!(value));
            }
            handle_portfolio_update(
                server,
                client,
                &portfolio_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
        PortfolioCommands::Summary { portfolio_id } => {
            handle_portfolio_summary(server, client, &portfolio_id, api_key).await
        }
        PortfolioCommands::Dashboard {
            status,
            org_id,
            limit,
            offset,
        } => {
            handle_portfolio_dashboard(server, client, status, org_id, limit, offset, api_key).await
        }
    }
}

async fn handle_program(
    action: ProgramCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        ProgramCommands::Create {
            name,
            org_id,
            portfolio_id,
            description,
            owner,
            project_ids,
            goal_ids,
            objective_ids,
            tag,
        } => {
            let payload = serde_json::json!({
                "name": name,
                "org_id": org_id,
                "portfolio_id": portfolio_id,
                "description": description,
                "owner": owner,
                "project_ids": project_ids,
                "goal_ids": goal_ids,
                "objective_ids": objective_ids,
                "tags": tag,
            });
            handle_program_create(server, client, payload, api_key).await
        }
        ProgramCommands::List {
            status,
            org_id,
            portfolio_id,
            limit,
            offset,
        } => {
            handle_program_list(
                server,
                client,
                status,
                org_id,
                portfolio_id,
                limit,
                offset,
                api_key,
            )
            .await
        }
        ProgramCommands::Get { program_id } => {
            handle_program_get(server, client, &program_id, api_key).await
        }
        ProgramCommands::Update {
            program_id,
            name,
            description,
            status,
            owner,
            project_ids,
            goal_ids,
            objective_ids,
            tag,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = status {
                payload.insert("status".to_string(), serde_json::json!(value));
            }
            if let Some(value) = owner {
                payload.insert("owner".to_string(), serde_json::json!(value));
            }
            if let Some(value) = project_ids {
                payload.insert("project_ids".to_string(), serde_json::json!(value));
            }
            if let Some(value) = goal_ids {
                payload.insert("goal_ids".to_string(), serde_json::json!(value));
            }
            if let Some(value) = objective_ids {
                payload.insert("objective_ids".to_string(), serde_json::json!(value));
            }
            if let Some(value) = tag {
                payload.insert("tags".to_string(), serde_json::json!(value));
            }
            handle_program_update(
                server,
                client,
                &program_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
        ProgramCommands::Summary { program_id } => {
            handle_program_summary(server, client, &program_id, api_key).await
        }
        ProgramCommands::Dashboard {
            status,
            org_id,
            portfolio_id,
            limit,
            offset,
        } => {
            handle_program_dashboard(
                server,
                client,
                status,
                org_id,
                portfolio_id,
                limit,
                offset,
                api_key,
            )
            .await
        }
    }
}

async fn handle_product(
    action: ProductCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        ProductCommands::Get { product_id } => {
            let resp = add_auth_header(
                client.get(format!("{}/api/v1/products/{}", server, product_id)),
                api_key,
            )
            .send()
            .await?;
            let product: serde_json::Value = resp.json().await?;
            println!("Product: {}", product["name"].as_str().unwrap());
        }
        ProductCommands::Summary { product_id } => {
            let resp = add_auth_header(
                client.get(format!("{}/api/v1/products/{}/summary", server, product_id)),
                api_key,
            )
            .send()
            .await?;
            let summary: serde_json::Value = resp.json().await?;
            println!("Product Summary:");
            println!("  Health: {}%", summary["health_score"]);
        }
        ProductCommands::Update {
            product_id,
            name,
            description,
            vision,
            repo,
            owner,
            product_type,
            status,
            tag,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = vision {
                payload.insert("vision".to_string(), serde_json::json!(value));
            }
            if let Some(value) = repo {
                payload.insert("repository_url".to_string(), serde_json::json!(value));
            }
            if let Some(value) = owner {
                payload.insert("owner".to_string(), serde_json::json!(value));
            }
            if let Some(value) = product_type {
                payload.insert("product_type".to_string(), serde_json::json!(value));
            }
            if let Some(value) = status {
                payload.insert("status".to_string(), serde_json::json!(value));
            }
            if let Some(value) = tag {
                payload.insert("tags".to_string(), serde_json::json!(value));
            }
            let resp = add_auth_header(
                client
                    .patch(format!("{}/api/v1/products/{}", server, product_id))
                    .json(&serde_json::Value::Object(payload)),
                api_key,
            )
            .send()
            .await?;
            let product: serde_json::Value = resp.json().await?;
            println!(
                "✓ Updated product: {} ({})",
                product["name"].as_str().unwrap_or("-"),
                product["id"].as_str().unwrap_or("-")
            );
        }
        ProductCommands::Archive { product_id } => {
            add_auth_header(
                client.post(format!("{}/api/v1/products/{}/archive", server, product_id)),
                api_key,
            )
            .send()
            .await?;
            println!("✓ Archived product");
        }
        ProductCommands::Create {
            name,
            description,
            vision,
        } => {
            let req = serde_json::json!({
                "name": name,
                "description": description,
                "vision": vision,
            });

            let resp = add_auth_header(
                client
                    .post(format!("{}/api/v1/products", server))
                    .json(&req),
                api_key,
            )
            .send()
            .await?;

            let product: serde_json::Value = resp.json().await?;

            println!("✓ Created product: {}", product["name"].as_str().unwrap());
            println!("  ID: {}", product["id"].as_str().unwrap());
        }

        ProductCommands::List => {
            let resp = add_auth_header(client.get(format!("{}/api/v1/products", server)), api_key)
                .send()
                .await?;

            let result: serde_json::Value = resp.json().await?;
            let items = result["items"].as_array().unwrap();

            println!("Products ({}):", items.len());
            for item in items {
                println!(
                    "  • {} ({}) - {}",
                    item["name"].as_str().unwrap(),
                    item["status"].as_str().unwrap(),
                    item["id"].as_str().unwrap()
                );
            }
        }
    }

    Ok(())
}

async fn handle_project(
    action: ProjectCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        ProjectCommands::Create {
            name,
            description,
            tag,
            org_id,
            portfolio_id,
            program_id,
            product_id,
        } => {
            let mut payload = serde_json::Map::new();
            payload.insert("name".to_string(), serde_json::json!(name));
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(tags) = tag {
                payload.insert("tags".to_string(), serde_json::json!(tags));
            }
            if let Some(value) = org_id {
                payload.insert("org_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = portfolio_id {
                payload.insert("portfolio_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = program_id {
                payload.insert("program_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = product_id {
                payload.insert("product_id".to_string(), serde_json::json!(value));
            }
            handle_project_create_full(server, client, serde_json::Value::Object(payload), api_key)
                .await
        }
        ProjectCommands::List {
            status,
            limit,
            offset,
        } => handle_project_list(server, client, status, limit, offset, api_key).await,
        ProjectCommands::Get { project_id } => {
            handle_project_get(server, client, &project_id, api_key).await
        }
        ProjectCommands::Summary { project_id } => {
            handle_project_summary(server, client, &project_id, api_key).await
        }
        ProjectCommands::Update {
            project_id,
            name,
            description,
            status,
            tag,
            org_id,
            portfolio_id,
            program_id,
            product_id,
        } => {
            let mut payload = serde_json::Map::new();
            if let Some(value) = name {
                payload.insert("name".to_string(), serde_json::json!(value));
            }
            if let Some(value) = description {
                payload.insert("description".to_string(), serde_json::json!(value));
            }
            if let Some(value) = status {
                payload.insert("status".to_string(), serde_json::json!(value));
            }
            if let Some(tags) = tag {
                payload.insert("tags".to_string(), serde_json::json!(tags));
            }
            if let Some(value) = org_id {
                payload.insert("org_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = portfolio_id {
                payload.insert("portfolio_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = program_id {
                payload.insert("program_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = product_id {
                payload.insert("product_id".to_string(), serde_json::json!(value));
            }
            handle_project_update(
                server,
                client,
                &project_id,
                serde_json::Value::Object(payload),
                api_key,
            )
            .await
        }
        ProjectCommands::Archive { project_id } => {
            let payload = serde_json::json!({ "status": "archived" });
            handle_project_update(server, client, &project_id, payload, api_key).await
        }
        ProjectCommands::Complete { project_id } => {
            let payload = serde_json::json!({ "status": "completed" });
            handle_project_update(server, client, &project_id, payload, api_key).await
        }
        ProjectCommands::Delete { project_id } => {
            let payload = serde_json::json!({ "status": "archived" });
            handle_project_update(server, client, &project_id, payload, api_key).await
        }
        ProjectCommands::History { project_id, limit } => {
            handle_revision_bundle(
                server,
                client,
                "project",
                &project_id,
                false,
                false,
                limit,
                0,
                20,
                None,
                api_key,
            )
            .await
        }
    }
}

async fn handle_plan(
    action: PlanCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        PlanCommands::Create {
            name,
            description,
            status,
            format,
            content,
            content_file,
            product_id,
            project_id,
            goal_id,
            objective_id,
            task_ids,
            tags,
        } => {
            let content_text = load_text_arg(content, content_file, "content")?;
            let content_value = match content_text {
                Some(text) => parse_content_value(&text),
                None => serde_json::json!({}),
            };
            let req = CreatePlanRequest {
                name,
                description,
                status: Some(status),
                format: Some(format),
                content: content_value,
                product_id,
                project_id,
                goal_id,
                objective_id,
                task_ids,
                tags,
            };
            handle_plan_create(server, client, req, api_key).await
        }
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
        PlanCommands::Get { plan_id } => handle_plan_get(server, client, &plan_id, api_key).await,
        PlanCommands::Update {
            plan_id,
            name,
            description,
            status,
            format,
            content,
            content_file,
            product_id,
            project_id,
            goal_id,
            objective_id,
            task_ids,
            tags,
        } => {
            let content_text = load_text_arg(content, content_file, "content")?;
            let content_value = content_text.map(|text| parse_content_value(&text));
            let req = UpdatePlanRequest {
                name,
                description,
                status,
                format,
                content: content_value,
                product_id,
                project_id,
                goal_id,
                objective_id,
                task_ids: if task_ids.is_empty() {
                    None
                } else {
                    Some(task_ids)
                },
                tags: if tags.is_empty() { None } else { Some(tags) },
            };
            handle_plan_update(server, client, &plan_id, req, api_key).await
        }
        PlanCommands::Lineage {
            status,
            project_id,
            plan_id,
            limit,
            offset,
            task_limit,
            test_limit,
        } => {
            handle_plan_lineage(
                server,
                client,
                status,
                project_id,
                plan_id,
                Some(limit),
                Some(offset),
                Some(task_limit),
                Some(test_limit),
                api_key,
            )
            .await
        }
        PlanCommands::TestJob { action } => {
            handle_plan_test_job(action, server, client, api_key).await
        }
    }
}

async fn handle_plan_test_job(
    action: PlanTestJobCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        PlanTestJobCommands::Create {
            plan_id,
            name,
            project_path,
            description,
            mode,
            test_command,
            setup_command,
            working_dir,
            env_vars,
            timeout,
            capture_logs,
            save_artifacts,
            task_ids,
            transition_on_success,
            transition_on_failure,
            transition_by,
            transition_reason,
            project_id,
            server_id,
            server_name,
            remote_path,
            exclude_patterns,
            stream_output,
        } => {
            let env_pairs = parse_env_pairs(env_vars)?;
            let req = PlanTestJobCreateRequest {
                name,
                description,
                mode: Some(mode),
                project_path,
                test_command,
                setup_command,
                working_dir,
                env_vars: env_pairs,
                timeout,
                capture_logs,
                save_artifacts,
                task_ids,
                transition_on_success,
                transition_on_failure,
                transition_by,
                transition_reason,
                project_id,
                server_id,
                server_name,
                remote_path,
                exclude_patterns: if exclude_patterns.is_empty() {
                    None
                } else {
                    Some(exclude_patterns)
                },
                stream_output: Some(stream_output),
            };
            handle_plan_test_job_create(server, client, &plan_id, req, api_key).await
        }
        PlanTestJobCommands::List {
            plan_id,
            limit,
            offset,
            include_archived,
        } => {
            handle_plan_test_job_list(
                server,
                client,
                &plan_id,
                Some(limit),
                Some(offset),
                include_archived,
                api_key,
            )
            .await
        }
        PlanTestJobCommands::Get { plan_id, job_id } => {
            handle_plan_test_job_get(server, client, &plan_id, &job_id, api_key).await
        }
        PlanTestJobCommands::Update {
            plan_id,
            job_id,
            name,
            description,
            mode,
            project_path,
            test_command,
            setup_command,
            working_dir,
            env_vars,
            timeout,
            capture_logs,
            save_artifacts,
            task_ids,
            transition_on_success,
            transition_on_failure,
            transition_by,
            transition_reason,
            project_id,
            server_id,
            server_name,
            remote_path,
            exclude_patterns,
            stream_output,
        } => {
            let env_pairs = if env_vars.is_empty() {
                None
            } else {
                Some(parse_env_pairs(env_vars)?)
            };
            let req = PlanTestJobUpdateRequest {
                name,
                description,
                mode,
                project_path,
                test_command,
                setup_command,
                working_dir,
                env_vars: env_pairs,
                timeout,
                capture_logs: if capture_logs.is_empty() {
                    None
                } else {
                    Some(capture_logs)
                },
                save_artifacts: if save_artifacts.is_empty() {
                    None
                } else {
                    Some(save_artifacts)
                },
                task_ids: if task_ids.is_empty() {
                    None
                } else {
                    Some(task_ids)
                },
                transition_on_success,
                transition_on_failure,
                transition_by,
                transition_reason,
                project_id,
                server_id,
                server_name,
                remote_path,
                exclude_patterns: if exclude_patterns.is_empty() {
                    None
                } else {
                    Some(exclude_patterns)
                },
                stream_output,
            };
            handle_plan_test_job_update(server, client, &plan_id, &job_id, req, api_key).await
        }
        PlanTestJobCommands::Delete { plan_id, job_id } => {
            handle_plan_test_job_delete(server, client, &plan_id, &job_id, api_key).await
        }
        PlanTestJobCommands::Restore { plan_id, job_id } => {
            handle_plan_test_job_restore(server, client, &plan_id, &job_id, api_key).await
        }
        PlanTestJobCommands::Run {
            plan_id,
            job_id,
            include_output,
            include_logs,
            include_artifacts,
        } => {
            handle_plan_test_job_run(
                server,
                client,
                &plan_id,
                &job_id,
                include_output,
                include_logs,
                include_artifacts,
                api_key,
            )
            .await
        }
    }
}

async fn handle_queue(
    action: QueueCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        QueueCommands::Create {
            name,
            description,
            owner,
            scope_type,
            scope_id,
            filters,
            filters_file,
            sort_by,
            sort_dir,
        } => {
            let filters_text = load_text_arg(filters, filters_file, "filters")?;
            let filters_value = match filters_text {
                Some(text) => Some(parse_json_value(&text, "filters")?),
                None => None,
            };
            let req = CreateQueueRequest {
                name,
                description,
                owner,
                scope_type,
                scope_id,
                filters: filters_value,
                sort_by,
                sort_dir,
            };
            handle_queue_create(server, client, req, api_key).await
        }
        QueueCommands::List {
            owner,
            scope_type,
            scope_id,
            limit,
            offset,
            include_archived,
        } => {
            handle_queue_list(
                server,
                client,
                owner,
                scope_type,
                scope_id,
                Some(limit),
                Some(offset),
                include_archived,
                api_key,
            )
            .await
        }
        QueueCommands::Get { queue_id } => {
            handle_queue_get(server, client, &queue_id, api_key).await
        }
        QueueCommands::Update {
            queue_id,
            name,
            description,
            owner,
            scope_type,
            scope_id,
            filters,
            filters_file,
            sort_by,
            sort_dir,
        } => {
            let filters_text = load_text_arg(filters, filters_file, "filters")?;
            let filters_value = match filters_text {
                Some(text) => Some(parse_json_value(&text, "filters")?),
                None => None,
            };
            let req = UpdateQueueRequest {
                name,
                description,
                owner,
                scope_type,
                scope_id,
                filters: filters_value,
                sort_by,
                sort_dir,
            };
            handle_queue_update(server, client, &queue_id, req, api_key).await
        }
        QueueCommands::Delete { queue_id } => {
            handle_queue_delete(server, client, &queue_id, api_key).await
        }
        QueueCommands::Restore { queue_id } => {
            handle_queue_restore(server, client, &queue_id, api_key).await
        }
        QueueCommands::Run {
            queue_id,
            limit,
            offset,
        } => {
            handle_queue_run(
                server,
                client,
                &queue_id,
                Some(limit),
                Some(offset),
                api_key,
            )
            .await
        }
        QueueCommands::Presets {
            project_id,
            limit,
            stale_days,
            at_risk_days,
        } => {
            handle_queue_presets(
                server,
                client,
                project_id,
                Some(limit),
                Some(stale_days),
                Some(at_risk_days),
                api_key,
            )
            .await
        }
        QueueCommands::Preset {
            preset,
            project_id,
            limit,
            offset,
            stale_days,
            at_risk_days,
        } => {
            handle_queue_preset(
                server,
                client,
                &preset,
                project_id,
                Some(limit),
                Some(offset),
                Some(stale_days),
                Some(at_risk_days),
                api_key,
            )
            .await
        }
    }
}

async fn handle_test_run(
    action: TestRunCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        TestRunCommands::Run {
            project_path,
            test_command,
            setup_cmd,
            working_dir,
            timeout,
            project,
            project_id,
            plan,
            plan_id,
            task_ids,
            capture_logs,
            save_artifacts,
            env_vars,
            on_success_state,
            on_failure_state,
            transition_by,
            transition_reason,
            no_output,
        } => {
            handle_test_run_local(
                &project_path,
                test_command,
                setup_cmd,
                working_dir,
                timeout,
                project,
                project_id,
                plan,
                plan_id,
                task_ids,
                capture_logs,
                save_artifacts,
                env_vars,
                on_success_state,
                on_failure_state,
                transition_by,
                transition_reason,
                no_output,
            )
            .await
        }
        TestRunCommands::Record {
            server_id,
            status,
            started_at,
            finished_at,
            project_id,
            run_id,
            exit_code,
            duration_seconds,
            stdout,
            stderr,
            command,
            runner,
            plan_id,
            task_ids,
            config,
            config_file,
            logs,
            logs_file,
            artifacts,
            artifacts_file,
        } => {
            let config_value = parse_json_input(config, config_file, "config")?;
            let logs_value = parse_json_input(logs, logs_file, "logs")?;
            let artifacts_value = parse_json_input(artifacts, artifacts_file, "artifacts")?;

            let mut payload = serde_json::Map::new();
            payload.insert("server_id".to_string(), serde_json::json!(server_id));
            payload.insert("success".to_string(), serde_json::json!(status == "passed"));
            payload.insert("started_at".to_string(), serde_json::json!(started_at));
            payload.insert("finished_at".to_string(), serde_json::json!(finished_at));

            if let Some(value) = project_id {
                payload.insert("project_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = run_id {
                payload.insert("run_id".to_string(), serde_json::json!(value));
            }
            if let Some(value) = exit_code {
                payload.insert("exit_code".to_string(), serde_json::json!(value));
            }
            if let Some(value) = duration_seconds {
                payload.insert("duration_seconds".to_string(), serde_json::json!(value));
            }
            if let Some(value) = stdout {
                payload.insert("stdout".to_string(), serde_json::json!(value));
            }
            if let Some(value) = stderr {
                payload.insert("stderr".to_string(), serde_json::json!(value));
            }
            if let Some(value) = command {
                payload.insert("command".to_string(), serde_json::json!(value));
            }
            if let Some(value) = runner {
                payload.insert("runner".to_string(), serde_json::json!(value));
            }
            if let Some(value) = plan_id {
                payload.insert("plan_id".to_string(), serde_json::json!(value));
            }
            if !task_ids.is_empty() {
                payload.insert("task_ids".to_string(), serde_json::json!(task_ids));
            }
            if let Some(value) = config_value {
                payload.insert("config".to_string(), value);
            }
            if let Some(value) = logs_value {
                payload.insert("logs".to_string(), value);
            }
            if let Some(value) = artifacts_value {
                payload.insert("artifacts".to_string(), value);
            }

            let resp = add_auth_header(
                client
                    .post(format!("{}/api/v1/test-runs", server))
                    .json(&serde_json::Value::Object(payload)),
                api_key,
            )
            .send()
            .await?;
            let result: serde_json::Value = resp.json().await?;
            println!(
                "✓ Recorded test run: {} (success={})",
                result["id"].as_str().unwrap_or("-"),
                result["success"].as_bool().unwrap_or(false)
            );
            Ok(())
        }
        TestRunCommands::List {
            server_id,
            project_id,
            success,
            include_output,
            include_logs,
            include_artifacts,
            limit,
            offset,
        } => {
            handle_test_run_list(
                server,
                client,
                server_id,
                project_id,
                success,
                include_output,
                include_logs,
                include_artifacts,
                Some(limit),
                Some(offset),
                api_key,
            )
            .await
        }
        TestRunCommands::Get {
            run_id,
            include_output,
            include_logs,
            include_artifacts,
        } => {
            handle_test_run_get(
                server,
                client,
                &run_id,
                include_output,
                include_logs,
                include_artifacts,
                api_key,
            )
            .await
        }
        TestRunCommands::Retention {
            limit,
            sort,
            project_id,
            org_id,
        } => {
            handle_test_run_retention(
                server,
                client,
                Some(limit),
                sort,
                project_id,
                org_id,
                api_key,
            )
            .await
        }
        TestRunCommands::Prune {
            max_log_bytes,
            max_artifact_bytes,
            max_age_days,
            dry_run,
            project_id,
            org_id,
            use_policies,
        } => {
            handle_test_run_prune(
                server,
                client,
                max_log_bytes,
                max_artifact_bytes,
                max_age_days,
                dry_run,
                project_id,
                org_id,
                use_policies,
                api_key,
            )
            .await
        }
        TestRunCommands::Policy { action } => {
            handle_retention_policy(action, server, client, api_key).await
        }
        TestRunCommands::Server { action } => match action {
            TestServerCommands::EnsureLocal {
                project,
                project_id,
                format,
            } => handle_test_server_ensure_local(project, project_id, format).await,
        },
    }
}

async fn handle_retention_policy(
    action: RetentionPolicyCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        RetentionPolicyCommands::List {
            scope_type,
            scope_id,
            include_archived,
            limit,
            offset,
        } => {
            handle_retention_policy_list(
                server,
                client,
                scope_type,
                scope_id,
                include_archived,
                Some(limit),
                Some(offset),
                api_key,
            )
            .await
        }
        RetentionPolicyCommands::Get { policy_id } => {
            handle_retention_policy_get(server, client, &policy_id, api_key).await
        }
        RetentionPolicyCommands::Upsert {
            scope_type,
            scope_id,
            max_log_bytes,
            max_artifact_bytes,
            max_age_days,
            notes,
        } => {
            handle_retention_policy_upsert(
                server,
                client,
                &scope_type,
                &scope_id,
                max_log_bytes,
                max_artifact_bytes,
                max_age_days,
                notes.as_deref(),
                api_key,
            )
            .await
        }
        RetentionPolicyCommands::Update {
            policy_id,
            max_log_bytes,
            max_artifact_bytes,
            max_age_days,
            notes,
        } => {
            handle_retention_policy_update(
                server,
                client,
                &policy_id,
                max_log_bytes,
                max_artifact_bytes,
                max_age_days,
                notes.as_deref(),
                api_key,
            )
            .await
        }
        RetentionPolicyCommands::Archive { policy_id } => {
            handle_retention_policy_archive(server, client, &policy_id, api_key).await
        }
        RetentionPolicyCommands::Restore { policy_id } => {
            handle_retention_policy_restore(server, client, &policy_id, api_key).await
        }
    }
}

async fn handle_evidence(
    action: EvidenceCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        EvidenceCommands::Gate { action } => match action {
            EvidenceGateCommands::Create {
                workflow_id,
                entity_type,
                from_state,
                to_state,
                evidence_type,
                min_count,
                require_success,
                message,
            } => {
                let req = CreateEvidenceGateRuleRequest {
                    workflow_id,
                    entity_type,
                    from_state,
                    to_state,
                    evidence_type,
                    min_count,
                    require_success: Some(require_success),
                    message,
                };
                handle_evidence_gate_create(server, client, req, api_key).await
            }
            EvidenceGateCommands::List {
                workflow_id,
                entity_type,
                from_state,
                to_state,
            } => {
                handle_evidence_gate_list(
                    server,
                    client,
                    &workflow_id,
                    &entity_type,
                    &from_state,
                    &to_state,
                    api_key,
                )
                .await
            }
            EvidenceGateCommands::Delete { rule_id } => {
                handle_evidence_gate_delete(server, client, &rule_id, api_key).await
            }
        },
        EvidenceCommands::BundleSearch {
            task_id,
            plan_id,
            status,
            evidence_type,
            created_from,
            created_to,
            include_evidence,
            include_test_runs,
            include_output,
            include_logs,
            include_artifacts,
            limit,
            offset,
        } => {
            handle_evidence_bundle_search(
                server,
                client,
                task_id,
                plan_id,
                status,
                evidence_type,
                created_from,
                created_to,
                include_evidence,
                include_test_runs,
                include_output,
                include_logs,
                include_artifacts,
                limit,
                offset,
                api_key,
            )
            .await
        }
    }
}

async fn handle_timeline(
    action: TimelineCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        TimelineCommands::Workflow {
            entity_type,
            entity_id,
            triggered_by,
            from_state,
            to_state,
            start_time,
            end_time,
            transition_type,
            label,
        } => {
            handle_transition_timeline(
                server,
                client,
                "workflow",
                &entity_type,
                &entity_id,
                triggered_by,
                from_state,
                to_state,
                start_time,
                end_time,
                transition_type,
                label,
                api_key,
            )
            .await
        }
        TimelineCommands::Status {
            entity_type,
            entity_id,
            triggered_by,
            from_state,
            to_state,
            start_time,
            end_time,
            transition_type,
            label,
        } => {
            handle_transition_timeline(
                server,
                client,
                "status",
                &entity_type,
                &entity_id,
                triggered_by,
                from_state,
                to_state,
                start_time,
                end_time,
                transition_type,
                label,
                api_key,
            )
            .await
        }
    }
}

async fn handle_revision(
    action: RevisionCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        RevisionCommands::Diff {
            entity_type,
            entity_id,
            from_revision,
            to_revision,
        } => {
            handle_revision_diff(
                server,
                client,
                &entity_type,
                &entity_id,
                from_revision,
                to_revision,
                api_key,
            )
            .await
        }
        RevisionCommands::Bundle {
            entity_type,
            entity_id,
            include_linked,
            include_linked_history,
            history_limit,
            history_offset,
            linked_limit,
            linked_history_limit,
        } => {
            handle_revision_bundle(
                server,
                client,
                &entity_type,
                &entity_id,
                include_linked,
                include_linked_history,
                history_limit,
                history_offset,
                linked_limit,
                linked_history_limit,
                api_key,
            )
            .await
        }
    }
}

async fn handle_work(
    action: WorkCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        WorkCommands::Snapshot {
            scope_type,
            scope_id,
            task_limit,
            test_limit,
        } => {
            handle_work_snapshot(
                server,
                client,
                &scope_type,
                &scope_id,
                task_limit,
                test_limit,
                api_key,
            )
            .await
        }
        WorkCommands::Daily {
            scope_type,
            scope_id,
            task_limit,
            test_limit,
            queue_limit,
            stale_days,
            at_risk_days,
            include_timeline,
            timeline_limit,
            include_history,
            history_limit,
            view,
            format,
        } => {
            handle_work_daily(
                server,
                client,
                &scope_type,
                &scope_id,
                task_limit,
                test_limit,
                queue_limit,
                stale_days,
                at_risk_days,
                include_timeline,
                timeline_limit,
                include_history,
                history_limit,
                view,
                &format,
                api_key,
            )
            .await
        }
        WorkCommands::GraphReport {
            scope_type,
            scope,
            scope_id,
            task_limit,
            goal_limit,
            objective_limit,
            plan_limit,
            format,
        } => {
            handle_work_graph_report(
                server,
                scope_type,
                scope,
                scope_id,
                task_limit,
                goal_limit,
                objective_limit,
                plan_limit,
                format,
                api_key,
            )
            .await
        }
        WorkCommands::Review {
            scope_type,
            scope_id,
            reviewed_by,
            note,
            metadata,
            metadata_file,
        } => {
            let metadata_text = load_text_arg(metadata, metadata_file, "metadata")?;
            let metadata_value = match metadata_text {
                Some(text) => Some(parse_json_value(&text, "metadata")?),
                None => None,
            };
            let req = WorkSnapshotReviewRequest {
                reviewed_by,
                note,
                metadata: metadata_value,
            };
            handle_work_snapshot_review(server, client, &scope_type, &scope_id, req, api_key).await
        }
    }
}

async fn handle_loop(
    action: LoopCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        LoopCommands::Init {
            config,
            prompt_file,
            force,
        } => handle_loop_init(config, prompt_file, force).await,
        LoopCommands::Setup {
            defaults,
            org,
            product,
            project,
            project_id,
            goal,
            goal_horizon,
            objective,
            criteria,
            tasks,
            config,
            prompt_file,
            force,
            agent,
            completion_promise,
            run,
            no_run,
            assign_workflow,
            no_assign_workflow,
            workflow,
            initial_state,
        } => {
            handle_loop_setup(
                defaults,
                org,
                product,
                project,
                project_id,
                goal,
                goal_horizon,
                objective,
                criteria,
                tasks,
                config,
                prompt_file,
                force,
                agent,
                completion_promise,
                run,
                no_run,
                assign_workflow,
                no_assign_workflow,
                workflow,
                initial_state,
            )
            .await
        }
        LoopCommands::PromptTemplate {
            project,
            project_id,
            goal,
            goal_id,
            objective,
            objective_id,
            plan,
            plan_id,
            prompt_file,
            force,
            stdout,
            no_write,
            task_limit,
            keyresult_limit,
            pick,
        } => {
            handle_loop_prompt_template(
                project,
                project_id,
                goal,
                goal_id,
                objective,
                objective_id,
                plan,
                plan_id,
                prompt_file,
                force,
                stdout,
                no_write,
                task_limit,
                keyresult_limit,
                pick,
            )
            .await
        }
        LoopCommands::Run {
            prompt,
            config,
            prompt_file,
            project,
            project_id,
            agent,
            agent_command,
            agent_args,
            prompt_mode,
            max_iterations,
            max_runtime,
            completion_promise,
            completion_marker,
            retry_delay,
            dry_run,
        } => {
            handle_loop_run(
                prompt,
                config,
                prompt_file,
                project,
                project_id,
                agent,
                agent_command,
                agent_args,
                prompt_mode,
                max_iterations,
                max_runtime,
                completion_promise,
                completion_marker,
                retry_delay,
                dry_run,
            )
            .await
        }
        LoopCommands::List {
            project_id,
            include_ended,
        } => handle_loop_list(server, client, project_id, include_ended, api_key).await,
        LoopCommands::Show { loop_id } => handle_loop_show(server, client, &loop_id, api_key).await,
        LoopCommands::Messages { loop_id, limit } => {
            handle_loop_messages(server, client, &loop_id, limit, api_key).await
        }
        LoopCommands::Cancel { loop_id } => {
            handle_loop_cancel(server, client, &loop_id, api_key).await
        }
        LoopCommands::Guard {
            project,
            project_id,
            goal,
            goal_id,
            include_archived,
            allow_no_goals,
            hook,
            format,
        } => {
            handle_loop_guard(
                project,
                project_id,
                goal,
                goal_id,
                include_archived,
                allow_no_goals,
                hook,
                format,
            )
            .await
        }
    }
}

async fn handle_dashboard_cmd(
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    handle_dashboard(server, client, api_key).await
}

async fn handle_start_cmd(
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
    output_format: &str,
) -> Result<()> {
    let canonical_prefix = cli_command_prefix(server);
    let alternate_prefix = current_rust_cli_prefix(server);
    let canonical_command = |command: &str| cli_command(server, command);

    let organizations_response = add_auth_header(
        client
            .get(format!("{}/api/v1/organizations", server))
            .query(&[("limit", "1"), ("offset", "0")]),
        api_key,
    )
    .send()
    .await?;
    if !organizations_response.status().is_success() {
        bail!(
            "Failed to fetch organizations: {}",
            organizations_response.status()
        );
    }
    let organizations: StartPageResponse<StartNamedItem> = organizations_response.json().await?;

    let portfolios_response = add_auth_header(
        client
            .get(format!("{}/api/v1/portfolios", server))
            .query(&[("limit", "1"), ("offset", "0")]),
        api_key,
    )
    .send()
    .await?;
    if !portfolios_response.status().is_success() {
        bail!(
            "Failed to fetch portfolios: {}",
            portfolios_response.status()
        );
    }
    let portfolios: StartPageResponse<StartNamedItem> = portfolios_response.json().await?;

    let programs_response = add_auth_header(
        client
            .get(format!("{}/api/v1/programs", server))
            .query(&[("limit", "1"), ("offset", "0")]),
        api_key,
    )
    .send()
    .await?;
    if !programs_response.status().is_success() {
        bail!("Failed to fetch programs: {}", programs_response.status());
    }
    let programs: StartPageResponse<StartNamedItem> = programs_response.json().await?;

    let projects_response = add_auth_header(
        client
            .get(format!("{}/api/v1/projects", server))
            .query(&[("limit", "1"), ("offset", "0")]),
        api_key,
    )
    .send()
    .await?;
    if !projects_response.status().is_success() {
        bail!("Failed to fetch projects: {}", projects_response.status());
    }
    let projects: StartPageResponse<StartNamedItem> = projects_response.json().await?;

    let task_totals_response = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/search", server))
            .query(&[
                ("include_terminal", "true"),
                ("limit", "1"),
                ("offset", "0"),
            ]),
        api_key,
    )
    .send()
    .await?;
    if !task_totals_response.status().is_success() {
        bail!(
            "Failed to fetch task totals: {}",
            task_totals_response.status()
        );
    }
    let task_totals: StartPageResponse<StartTaskSearchItem> = task_totals_response.json().await?;

    let dashboard_response = add_auth_header(
        client
            .get(format!("{}/api/v1/organizations/dashboard", server))
            .query(&[("limit", "1"), ("offset", "0")]),
        api_key,
    )
    .send()
    .await?;
    if !dashboard_response.status().is_success() {
        bail!(
            "Failed to fetch organization dashboard: {}",
            dashboard_response.status()
        );
    }
    let dashboard: StartOrganizationDashboardResponse = dashboard_response.json().await?;

    let ready_response = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/ready", server))
            .query(&[
                ("exclude_checked_out", "true"),
                ("limit", "5"),
                ("offset", "0"),
            ]),
        api_key,
    )
    .send()
    .await?;
    if !ready_response.status().is_success() {
        bail!("Failed to fetch ready tasks: {}", ready_response.status());
    }
    let ready: StartReadyTaskResponse = ready_response.json().await?;

    let in_progress_response = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/search", server))
            .query(&[
                ("status", "in_progress"),
                ("include_terminal", "true"),
                ("limit", "5"),
                ("offset", "0"),
            ]),
        api_key,
    )
    .send()
    .await?;
    if !in_progress_response.status().is_success() {
        bail!(
            "Failed to fetch in-progress tasks: {}",
            in_progress_response.status()
        );
    }
    let in_progress: StartPageResponse<StartTaskSearchItem> = in_progress_response.json().await?;

    let blocked_response = add_auth_header(
        client
            .get(format!("{}/api/v1/tasks/search", server))
            .query(&[
                ("status", "blocked"),
                ("include_terminal", "true"),
                ("limit", "5"),
                ("offset", "0"),
            ]),
        api_key,
    )
    .send()
    .await?;
    if !blocked_response.status().is_success() {
        bail!(
            "Failed to fetch blocked tasks: {}",
            blocked_response.status()
        );
    }
    let blocked: StartPageResponse<StartTaskSearchItem> = blocked_response.json().await?;

    let queue_presets_response = add_auth_header(
        client
            .get(format!("{}/api/v1/queues/presets", server))
            .query(&[("limit", "3"), ("offset", "0")]),
        api_key,
    )
    .send()
    .await?;
    if !queue_presets_response.status().is_success() {
        bail!(
            "Failed to fetch queue presets: {}",
            queue_presets_response.status()
        );
    }
    let queue_presets: Vec<serde_json::Value> = queue_presets_response.json().await?;

    let focus_task = in_progress
        .items
        .first()
        .map(|task| {
            (
                task.id.clone(),
                task.title.clone(),
                "in_progress".to_string(),
                task.project_id.clone(),
                task.current_progress_percent,
                "active execution in progress".to_string(),
            )
        })
        .or_else(|| {
            ready.items.first().map(|task| {
                (
                    task.id.clone(),
                    task.title.clone(),
                    "todo".to_string(),
                    task.project_id.clone(),
                    None,
                    "next ready work to start".to_string(),
                )
            })
        });

    let focus_project_name = if let Some((_, _, _, Some(project_id), _, _)) = &focus_task {
        let project_response = add_auth_header(
            client.get(format!("{}/api/v1/projects/{}", server, project_id)),
            api_key,
        )
        .send()
        .await?;
        if project_response.status().is_success() {
            let project: StartNamedItem = project_response.json().await?;
            if project.name.is_empty() {
                None
            } else {
                Some(project.name)
            }
        } else {
            None
        }
    } else {
        None
    };

    let dashboard_command = canonical_command("dashboard --format json");
    let guide_command = canonical_command("start --format json");
    let quickstart_command = canonical_command("quickstart --defaults");
    let queue_presets_command = canonical_command("queue presets --format json");
    let work_daily_command = match focus_project_name.as_deref() {
        Some(project_name) => canonical_command(&format!(
            "work daily --scope-type project --scope \"{}\" --format json",
            project_name
        )),
        None => canonical_command("dashboard --format json"),
    };

    let focus_next_steps = match (&focus_task, focus_project_name.as_deref()) {
        (Some((_, title, status, _, _, _)), Some(project_name)) if status == "in_progress" => vec![
            canonical_command(&format!(
                "task progress \"{}\" --project \"{}\" <percent> <message> --by <user>",
                title, project_name
            )),
            canonical_command(&format!(
                "task show \"{}\" --project \"{}\"",
                title, project_name
            )),
        ],
        (Some((_, title, _, _, _, _)), Some(project_name)) => vec![
            canonical_command(&format!(
                "task start \"{}\" --project \"{}\" --by <user>",
                title, project_name
            )),
            canonical_command(&format!(
                "task show \"{}\" --project \"{}\"",
                title, project_name
            )),
        ],
        (Some((task_id, _, status, _, _, _)), None) if status == "in_progress" => vec![
            format!(
                "{} task progress {} <percent> <message> --by <user>",
                alternate_prefix, task_id
            ),
            format!("{} task get {}", alternate_prefix, task_id),
        ],
        (Some((task_id, _, _, _, _, _)), None) => vec![
            format!("{} task start {} --by <user>", alternate_prefix, task_id),
            format!("{} task get {}", alternate_prefix, task_id),
        ],
        (None, _) => vec![],
    };

    let mut next_steps = Vec::new();
    if projects.total_count == 0 {
        next_steps.push(quickstart_command.clone());
    }
    next_steps.extend(focus_next_steps);
    next_steps.push(work_daily_command.clone());
    next_steps.push(dashboard_command.clone());
    next_steps.push(queue_presets_command.clone());
    next_steps.push("./scripts/run_dropin_start_go_extend_grow.sh".to_string());

    let payload = StartGuidePayload {
        generated_at: Utc::now().to_rfc3339(),
        purpose: "Practical start -> go entry point for discovering live state, fastest first action, and where to extend next.".to_string(),
        artifacts_created: Vec::new(),
        live_state: StartLiveState {
            organizations: organizations.total_count,
            portfolios: portfolios.total_count,
            programs: programs.total_count,
            projects: projects.total_count,
            tasks: task_totals.total_count,
            ready_tasks: ready.total_count,
            in_progress_tasks: in_progress.total_count,
            blocked_tasks: blocked.total_count,
            queue_presets: queue_presets.len(),
            blocked_projects: dashboard.totals.blocked_tasks,
            overdue_tasks: 0,
        },
        docs: StartDocs {
            readme: "README.md",
            getting_started: "GETTING_STARTED.md",
            immediate_start: "docs/IMMEDIATE_START_GO.md",
            capabilities: "docs/CAPABILITIES_REFERENCE.md",
            workflows: "docs/END_TO_END_WORKFLOWS.md",
        },
        observability_paths: vec![
            StartObservabilityPath {
                name: "Global Dashboard",
                command: dashboard_command.clone(),
                why: "Project/task rollup with ready and in-progress focus.",
                continue_with: canonical_command(
                    "work daily --scope-type project --scope <name>",
                ),
            },
            StartObservabilityPath {
                name: "Scoped Daily Digest",
                command: canonical_command(
                    "work daily --scope-type project --scope <name> --format json",
                ),
                why: "Accumulated snapshot + queues + transitions + review history.",
                continue_with: canonical_command(
                    "work review --scope-type project --scope <name> --reviewed-by <you>",
                ),
            },
            StartObservabilityPath {
                name: "Queue Presets",
                command: queue_presets_command.clone(),
                why: "Instant ready/blocker/at-risk action lists.",
                continue_with: canonical_command("queue create <name> --filters '{...}'"),
            },
            StartObservabilityPath {
                name: "Org/Portfolio/Program Rollups",
                command: canonical_command("org dashboard --format json"),
                why: "Cross-project health and next actions for handoffs.",
                continue_with: canonical_command(
                    "portfolio dashboard --org <name> --format json",
                ),
            },
        ],
        scenario_paths: vec![
            StartScenarioPath {
                name: "Drop-in Start Go Extend Grow",
                command: "./scripts/run_dropin_start_go_extend_grow.sh",
                contract: "./scripts/run_dropin_contract_smoke.sh",
                docs: "examples/real_world/README.md#scenario-dropin",
            },
            StartScenarioPath {
                name: "Team Handoff",
                command: "./scripts/run_team_handoff_flow.sh",
                contract: "./scripts/run_team_handoff_contract_smoke.sh",
                docs: "examples/real_world/README.md#scenario-team-handoff",
            },
            StartScenarioPath {
                name: "Incident Response",
                command: "./scripts/run_incident_response_flow.sh",
                contract: "./scripts/run_incident_response_contract_smoke.sh",
                docs: "examples/real_world/README.md#scenario-incident-response",
            },
        ],
        focus_task: focus_task.map(
            |(id, title, status, project_id, current_progress_percent, reason)| StartFocusTask {
                id,
                title,
                status,
                project_id,
                project_name: focus_project_name,
                current_progress_percent,
                reason,
            },
        ),
        next_steps,
        links: StartLinks {
            dashboard: dashboard_command,
            guide: guide_command,
            quickstart: quickstart_command,
        },
        cli: StartCliPrefixes {
            canonical_prefix,
            alternate_prefix,
        },
    };

    match output_format {
        "json" => println!("{}", serde_json::to_string_pretty(&payload)?),
        "text" => {
            println!("Start -> Go Guide");
            println!("Purpose: {}", payload.purpose);
            println!("Creates: no new state; this command maps the current workspace and tells you where to jump next.");
            println!("Live State:");
            println!(
                "  orgs {} | portfolios {} | programs {}",
                payload.live_state.organizations,
                payload.live_state.portfolios,
                payload.live_state.programs
            );
            println!(
                "  projects {} | tasks {} | ready {} | in-progress {} | blocked {}",
                payload.live_state.projects,
                payload.live_state.tasks,
                payload.live_state.ready_tasks,
                payload.live_state.in_progress_tasks,
                payload.live_state.blocked_tasks
            );
            if let Some(task) = &payload.focus_task {
                println!("Focus Task: {} [{}]", task.title, task.status);
                if let Some(project_name) = &task.project_name {
                    println!("Project: {}", project_name);
                }
                println!("Why: {}", task.reason);
            }
            println!();
            println!("Observability Paths:");
            for path in &payload.observability_paths {
                println!("  - {}: {}", path.name, path.command);
                println!("    why: {}", path.why);
                println!("    continue: {}", path.continue_with);
            }
            println!();
            println!("Scenario Paths:");
            for path in &payload.scenario_paths {
                println!("  - {}: {}", path.name, path.command);
                println!("    contract: {}", path.contract);
                println!("    docs: {}", path.docs);
            }
            println!();
            println!("Next Steps:");
            for (idx, step) in payload.next_steps.iter().enumerate() {
                println!("  {}. {}", idx + 1, step);
            }
        }
        _ => bail!("Unsupported format '{}'", output_format),
    }

    Ok(())
}

async fn handle_workflow(
    action: WorkflowCommands,
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    match action {
        WorkflowCommands::List => handle_workflow_list(server, client, api_key).await,
        WorkflowCommands::Show {
            workflow_ref,
            view,
            format,
        } => handle_workflow_show(server, client, &workflow_ref, view, &format, api_key).await,
        WorkflowCommands::Assign {
            task_id,
            workflow_name,
            initial_state,
        } => {
            let req =
                serde_json::json!({"workflow_name": workflow_name, "initial_state": initial_state});
            add_auth_header(
                client
                    .post(format!(
                        "{}/api/v1/tasks/{}/workflow/assign",
                        server, task_id
                    ))
                    .json(&req),
                api_key,
            )
            .send()
            .await?;
            println!("✓ Assigned workflow");
            Ok(())
        }
        WorkflowCommands::Transition {
            task_id,
            to_state,
            by,
            reason,
        } => {
            let req =
                serde_json::json!({"to_state": to_state, "triggered_by": by, "reason": reason});
            add_auth_header(
                client
                    .post(format!(
                        "{}/api/v1/tasks/{}/workflow/transition",
                        server, task_id
                    ))
                    .json(&req),
                api_key,
            )
            .send()
            .await?;
            println!("✓ Transitioned");
            Ok(())
        }
        WorkflowCommands::Align {
            entity_id,
            to_state,
            by,
            reason,
            approved_by,
            entity_type,
            auto,
            dry_run,
        } => {
            let payload = serde_json::json!({
                "entity_id": entity_id,
                "entity_type": entity_type,
                "to_state": to_state,
                "triggered_by": by,
                "reason": reason,
                "approved_by": approved_by,
                "auto": auto,
                "dry_run": dry_run,
            });
            handle_workflow_align(server, client, payload, api_key).await
        }
    }
}

async fn handle_health(
    server: &str,
    client: &reqwest::Client,
    api_key: Option<&str>,
) -> Result<()> {
    handle_health_check(server, client, api_key).await
}
