-- PMS schema.sql
--
-- This file defines the initial schema for a brand new database.
-- Design goals:
-- - Immutable history via append-only logs (events, revisions, transitions, evidence).
-- - Fast read models for interactive UI/CLI/API queries.
-- - Every entity has created_at; projections update updated_at and/or emit logs.
-- - All timestamps stored as ISO-8601 UTC strings.
-- - Logs are never mutated; deletions are represented as new events or archive state.

-- =============================================================================
-- Schema metadata and event sourcing primitives
-- =============================================================================

-- schema_info records the schema version loaded into this database.
-- Only one row should exist; init/verify uses this to ensure compatibility.
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- events is the canonical append-only event store.
-- Each aggregate receives a monotonically increasing sequence_number.
-- created_at is insertion time; timestamp is the event time from the emitter.
CREATE TABLE IF NOT EXISTS events (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload TEXT NOT NULL,   -- JSON payload data
    metadata TEXT NOT NULL,  -- JSON metadata (source, actor, correlation, etc.)
    sequence_number INTEGER NOT NULL,
    timestamp TEXT NOT NULL,

    UNIQUE(aggregate_type, aggregate_id, sequence_number)
);

-- Indexes for common event store access patterns.
CREATE INDEX IF NOT EXISTS idx_events_aggregate
    ON events(aggregate_type, aggregate_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_events_type
    ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp
    ON events(timestamp);

-- revisions stores full entity snapshots per revision.
-- This is the immutable audit trail for "what did we change" and "why".
CREATE TABLE IF NOT EXISTS revisions (
    revision_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    revision_number INTEGER NOT NULL,
    parent_revision_id TEXT,
    content TEXT NOT NULL,       -- JSON: full state at this revision
    content_hash TEXT NOT NULL,  -- SHA-256 for integrity checks
    changes TEXT NOT NULL,       -- JSON: list of field changes
    change_type TEXT NOT NULL,   -- create, update, delete, restore
    created_at TEXT NOT NULL,
    created_by TEXT,
    message TEXT,                -- human description of the change
    metadata TEXT NOT NULL DEFAULT '{}',

    UNIQUE(entity_type, entity_id, revision_number),
    FOREIGN KEY(parent_revision_id) REFERENCES revisions(revision_id),
    CHECK(json_valid(content)),
    CHECK(json_valid(changes)),
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_revisions_entity
    ON revisions(entity_type, entity_id, revision_number DESC);
CREATE INDEX IF NOT EXISTS idx_revisions_parent
    ON revisions(parent_revision_id);

-- snapshots cache computed state to accelerate rehydration.
-- Safe to rebuild from events/revisions; not an authoritative history source.
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    state TEXT NOT NULL,  -- JSON: computed state
    state_hash TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL,
    last_revision_number INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',

    CHECK(json_valid(state)),
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_snapshots_entity
    ON snapshots(entity_type, entity_id, created_at DESC);

-- metrics stores operational telemetry for the PMS runtime.
-- Not part of entity history; used for dashboards and health reporting.
CREATE TABLE IF NOT EXISTS metrics (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    metric_id TEXT PRIMARY KEY,
    metric_type TEXT NOT NULL,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    labels TEXT NOT NULL DEFAULT '{}',  -- JSON
    metadata TEXT NOT NULL DEFAULT '{}', -- JSON

    CHECK(json_valid(labels)),
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_metrics_name_time
    ON metrics(name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_type
    ON metrics(metric_type);

-- =============================================================================
-- Core work model (projects, tasks, dependencies)
-- =============================================================================

-- actors is the canonical identity graph root for humans, personas, teams,
-- service accounts, and runtime agents.
CREATE TABLE IF NOT EXISTS actors (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    handle TEXT NOT NULL,
    normalized_handle TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    tags TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    CHECK(kind IN ('human', 'persona', 'team', 'service_account', 'runtime_agent')),
    CHECK(status IN ('active', 'archived')),
    CHECK(json_valid(tags)),
    CHECK(json_valid(metadata))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_actors_normalized_handle_active
    ON actors(normalized_handle)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_actors_kind
    ON actors(kind);
CREATE INDEX IF NOT EXISTS idx_actors_status
    ON actors(status);

-- actor_aliases lets prior names and alternate handles resolve to one actor.
CREATE TABLE IF NOT EXISTS actor_aliases (
    id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(actor_id) REFERENCES actors(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_actor_aliases_normalized_active
    ON actor_aliases(normalized_alias)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_actor_aliases_actor
    ON actor_aliases(actor_id);

-- actor_memberships defines graph edges such as a human belonging to a team or
-- representing a persona.
CREATE TABLE IF NOT EXISTS actor_memberships (
    id TEXT PRIMARY KEY,
    parent_actor_id TEXT NOT NULL,
    member_actor_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(parent_actor_id) REFERENCES actors(id) ON DELETE CASCADE,
    FOREIGN KEY(member_actor_id) REFERENCES actors(id) ON DELETE CASCADE,
    CHECK(role IN ('member', 'lead', 'representative'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_actor_memberships_unique_active
    ON actor_memberships(parent_actor_id, member_actor_id, role)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_actor_memberships_parent
    ON actor_memberships(parent_actor_id);
CREATE INDEX IF NOT EXISTS idx_actor_memberships_member
    ON actor_memberships(member_actor_id);

-- projects is the current-state projection for project-level execution.
-- History lives in events/revisions; tasks and milestones attach here.
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    -- Optional organizational scoping for rollups and dashboards.
    org_id TEXT,
    portfolio_id TEXT,
    program_id TEXT,
    -- Optional product linkage for delivery grouping.
    product_id TEXT,
    -- Workflow binding: which workflow definition governs this project.
    workflow_id TEXT,
    -- Denormalized current state for fast queries; history is in state_transition_log.
    current_state TEXT,
    -- JSON: workflow-specific metadata (state payloads, guard context, UI hints).
    workflow_metadata TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE SET NULL,
    FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE SET NULL,
    FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE SET NULL,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL,

    CHECK(status IN ('active', 'archived', 'completed', 'on_hold')),
    CHECK(json_valid(tags)),
    CHECK(json_valid(workflow_metadata))
);

CREATE INDEX IF NOT EXISTS idx_projects_status
    ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_name
    ON projects(name);
CREATE INDEX IF NOT EXISTS idx_projects_product
    ON projects(product_id);
CREATE INDEX IF NOT EXISTS idx_projects_org
    ON projects(org_id);
CREATE INDEX IF NOT EXISTS idx_projects_portfolio
    ON projects(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_projects_program
    ON projects(program_id);

-- milestones define project-level schedule anchors.
-- Names are unique per project to avoid ambiguity in CLI/UI.
CREATE TABLE IF NOT EXISTS milestones (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,

    UNIQUE(project_id, name),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CHECK(status IN ('pending', 'in_progress', 'completed', 'missed')),
    CHECK(sort_order >= 0)
);

CREATE INDEX IF NOT EXISTS idx_milestones_project
    ON milestones(project_id);

-- task_dependencies defines edges in the task graph (blocks/relates/etc).
-- This is the source for readiness, critical path, and ordering analysis.
CREATE TABLE IF NOT EXISTS task_dependencies (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    depends_on_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL DEFAULT 'blocks',
    created_at TEXT NOT NULL,

    UNIQUE(task_id, depends_on_id),
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY(depends_on_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CHECK(dependency_type IN ('blocks', 'relates_to', 'duplicates'))
);

CREATE INDEX IF NOT EXISTS idx_deps_task
    ON task_dependencies(task_id);
CREATE INDEX IF NOT EXISTS idx_deps_depends_on
    ON task_dependencies(depends_on_id);

-- tasks is the current-state projection for task execution.
-- The full history is preserved in events/revisions/transition logs.
CREATE TABLE IF NOT EXISTS "tasks" (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    milestone_id TEXT,
    parent_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'todo',
    priority TEXT NOT NULL DEFAULT 'medium',
    complexity_points INTEGER,
    actual_hours REAL,
    due_date TEXT,
    assignee TEXT,
    assignee_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    -- Agent/user currently holding the lease for edits (NULL when unlocked).
    checkout_agent_session_id TEXT,
    -- Canonical actor identity backing the current checkout lease.
    checkout_actor_id TEXT,
    -- Timestamp when the current checkout lease began.
    checked_out_at TEXT,
    -- Lease expiration timestamp; checkout is invalid after this time.
    checkout_lease_until TEXT,
    -- Total attempts to acquire a checkout lease (used for backoff).
    checkout_attempts INTEGER NOT NULL DEFAULT 0,
    -- Incremented on each checkout/renew to prevent stale updates.
    checkout_version INTEGER NOT NULL DEFAULT 0,
    current_progress_percent INTEGER NOT NULL DEFAULT 0,
    last_progress_update_at TEXT,
    -- Workflow binding: which workflow definition governs this task.
    workflow_id TEXT,
    -- Denormalized current workflow state; transition history is append-only.
    current_state TEXT,
    -- JSON: workflow metadata captured at the current state (guards, UI hints).
    workflow_metadata TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(milestone_id) REFERENCES milestones(id) ON DELETE SET NULL,
    FOREIGN KEY(parent_id) REFERENCES "tasks"(id) ON DELETE CASCADE,
    FOREIGN KEY(assignee_id) REFERENCES actors(id) ON DELETE SET NULL,
    FOREIGN KEY(checkout_actor_id) REFERENCES actors(id) ON DELETE SET NULL,

    CHECK(status IN ('todo', 'in_progress', 'blocked', 'in_review', 'done', 'cancelled')),
    CHECK(priority IN ('low', 'medium', 'high', 'critical')),
    CHECK(json_valid(tags)),
    CHECK(json_valid(workflow_metadata)),
    CHECK(sort_order >= 0),
    CHECK(checkout_attempts >= 0),
    CHECK(checkout_version >= 0),
    CHECK(current_progress_percent >= 0 AND current_progress_percent <= 100),
    CHECK(
        (checkout_agent_session_id IS NULL AND checked_out_at IS NULL AND checkout_lease_until IS NULL)
        OR checkout_agent_session_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_tasks_project
    ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_milestone
    ON tasks(milestone_id);
CREATE INDEX IF NOT EXISTS idx_tasks_parent
    ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee_id
    ON tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_tasks_normalized_title
    ON tasks(LOWER(TRIM(title)));
CREATE INDEX IF NOT EXISTS idx_tasks_project_status_normalized_title
    ON tasks(project_id, status, LOWER(TRIM(title)));
CREATE INDEX IF NOT EXISTS idx_tasks_checkout_lease
    ON tasks(checkout_lease_until)
    WHERE checkout_agent_session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_checked_out_by
    ON tasks(checkout_agent_session_id)
    WHERE checkout_agent_session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_checkout_actor
    ON tasks(checkout_actor_id)
    WHERE checkout_actor_id IS NOT NULL;

-- task_state_transitions captures task-specific status history.
-- This is separate from workflow transitions to preserve direct status updates.
CREATE TABLE IF NOT EXISTS task_state_transitions (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    reason TEXT,
    triggered_by TEXT NOT NULL,  -- agent_id or user_id
    duration_in_state_seconds INTEGER,
    metadata TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_state_transitions_task
    ON task_state_transitions(task_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_state_transitions_timestamp
    ON task_state_transitions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_state_transitions_to_state
    ON task_state_transitions(to_state, timestamp DESC);

-- task_checkout_log records concurrency control actions.
-- Used to diagnose lock conflicts, lease expirations, and automation retries.
CREATE TABLE IF NOT EXISTS task_checkout_log (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_session_id TEXT NOT NULL,
    -- Checkout action verb for audit: checkout, renew, release, expire, conflict.
    action TEXT NOT NULL,  -- checkout, renew, release, expire, conflict
    -- Lease duration requested/recorded for the action (seconds).
    lease_seconds INTEGER,
    success INTEGER NOT NULL,
    conflict_with TEXT,     -- agent session ID that held the lock
    error_message TEXT,
    timestamp TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CHECK(success IN (0, 1)),
    CHECK(metadata IS NOT NULL AND json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_checkout_log_task
    ON task_checkout_log(task_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_checkout_log_agent
    ON task_checkout_log(agent_session_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_checkout_log_action
    ON task_checkout_log(action, timestamp DESC);

-- task_progress_updates stores incremental progress updates.
-- Enables activity rollups and progress audit trails.
CREATE TABLE IF NOT EXISTS task_progress_updates (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    percent_complete INTEGER NOT NULL,  -- 0-100
    status_message TEXT,
    updated_by TEXT NOT NULL,           -- agent_id or user_id
    timestamp TEXT NOT NULL,
    duration_since_last_update_seconds INTEGER,
    percent_delta INTEGER,              -- change since previous update
    metadata TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,

    CHECK(percent_complete >= 0 AND percent_complete <= 100),
    CHECK(metadata IS NOT NULL AND json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_progress_updates_task
    ON task_progress_updates(task_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_progress_updates_time
    ON task_progress_updates(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_progress_updates_by
    ON task_progress_updates(updated_by, timestamp DESC);

-- task_evidence records proof artifacts tied to tasks.
-- This is the enforcement point for evidence gate rules.
CREATE TABLE IF NOT EXISTS task_evidence (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    -- Evidence category used by gate rules (e.g., test_run, artifact, note).
    evidence_type TEXT NOT NULL,
    -- Locator for the evidence (URL, file path, run ID, or opaque reference).
    reference TEXT NOT NULL,
    description TEXT,
    -- JSON: evidence metadata (size_bytes, created_at, modified_at, pruned_at, tags).
    metadata TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),

    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_task_evidence_task
    ON task_evidence(task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_task_evidence_type
    ON task_evidence(evidence_type, created_at DESC);

-- =============================================================================
-- Comments, mentions, and watchers
-- =============================================================================

-- comments capture append-only discussion for any entity.
-- Use archived_at for soft deletes while preserving full history.
CREATE TABLE IF NOT EXISTS comments (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    body TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',

    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_comments_entity
    ON comments(entity_type, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comments_created_by
    ON comments(created_by, created_at DESC);

-- comment_mentions store parsed @mentions or explicit mention list.
-- Mentions are append-only and tied to the comment record.
CREATE TABLE IF NOT EXISTS comment_mentions (
    id TEXT PRIMARY KEY,
    comment_id TEXT NOT NULL,
    mention TEXT NOT NULL,
    created_at TEXT NOT NULL,

    FOREIGN KEY(comment_id) REFERENCES comments(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_comment_mentions_comment
    ON comment_mentions(comment_id);
CREATE INDEX IF NOT EXISTS idx_comment_mentions_mention
    ON comment_mentions(mention);

-- entity_watchers record subscriptions for changes on any entity.
-- Use archived_at for soft-unsubscribe to preserve history.
CREATE TABLE IF NOT EXISTS entity_watchers (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    watcher TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_watchers_active
    ON entity_watchers(entity_type, entity_id, watcher)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_entity_watchers_entity
    ON entity_watchers(entity_type, entity_id, created_at DESC);

-- =============================================================================
-- Workflow engine and gating
-- =============================================================================

-- workflow_definitions defines reusable state machines per entity type.
-- Entities link to these definitions via workflow_id/current_state.
CREATE TABLE IF NOT EXISTS workflow_definitions (
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    entity_type TEXT NOT NULL,  -- task, project, product, etc.
    initial_state TEXT NOT NULL,
    terminal_states TEXT NOT NULL,  -- JSON array
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',

    CHECK(json_valid(terminal_states)),
    CHECK(is_default IN (0, 1)),
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_workflow_defs_entity_type
    ON workflow_definitions(entity_type);

-- workflow_states enumerates the valid states for each workflow.
-- UI metadata lives here for consistent rendering across CLI/UI.
CREATE TABLE IF NOT EXISTS workflow_states (
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    state_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    color TEXT,
    icon TEXT,
    is_terminal INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata_schema TEXT,  -- JSON schema for state-specific metadata

    FOREIGN KEY(workflow_id) REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    UNIQUE(workflow_id, state_name),
    CHECK(is_terminal IN (0, 1)),
    CHECK(sort_order >= 0),
    CHECK(metadata_schema IS NULL OR json_valid(metadata_schema))
);

CREATE INDEX IF NOT EXISTS idx_workflow_states_workflow
    ON workflow_states(workflow_id, sort_order);

-- workflow_transitions enumerates valid edges plus policy checks.
-- Validation rules and approvals enforce safe transitions.
CREATE TABLE IF NOT EXISTS workflow_transitions (
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    requires_approval INTEGER NOT NULL DEFAULT 0,
    approval_roles TEXT,       -- JSON array of roles
    validation_rules TEXT,     -- JSON validation rules
    auto_transition INTEGER NOT NULL DEFAULT 0,
    condition_expr TEXT,       -- expression for auto-transition
    metadata TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(workflow_id) REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    UNIQUE(workflow_id, from_state, to_state),
    CHECK(requires_approval IN (0, 1)),
    CHECK(auto_transition IN (0, 1)),
    CHECK(approval_roles IS NULL OR json_valid(approval_roles)),
    CHECK(validation_rules IS NULL OR json_valid(validation_rules)),
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_workflow_transitions_workflow
    ON workflow_transitions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_transitions_from
    ON workflow_transitions(workflow_id, from_state);

-- state_transition_log is the canonical workflow transition history.
-- Provides auditability, timing, and actor attribution.
CREATE TABLE IF NOT EXISTS state_transition_log (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    workflow_id TEXT,
    from_state TEXT,
    to_state TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    reason TEXT,
    triggered_by TEXT NOT NULL,
    duration_in_state_seconds INTEGER,
    requires_approval INTEGER DEFAULT 0,
    approved_by TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',

    CHECK(requires_approval IS NULL OR requires_approval IN (0, 1)),
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_state_log_entity
    ON state_transition_log(entity_type, entity_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_state_log_workflow
    ON state_transition_log(workflow_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_state_log_to_state
    ON state_transition_log(to_state, timestamp DESC);

-- label_categories define taxonomy groupings and exclusivity rules.
-- These enforce structured labeling rather than free-form tags.
CREATE TABLE IF NOT EXISTS label_categories (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    is_exclusive INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- Soft archive timestamp; hidden from default queries when set.
    archived_at TEXT,

    CHECK(is_exclusive IN (0, 1)),
    CHECK(sort_order >= 0)
);

-- labels are the canonical label definitions.
-- Use category_id to attach to a taxonomy group; is_system locks reserved labels.
CREATE TABLE IF NOT EXISTS labels (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    category_id TEXT,
    color TEXT,
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- Soft archive timestamp; used instead of deletes for immutability.
    archived_at TEXT,
    FOREIGN KEY(category_id) REFERENCES label_categories(id)
        ON DELETE SET NULL,
    CHECK(is_system IN (0, 1))
);

-- label_assignments maps labels to entities (current view).
-- History is preserved via events/revisions; this supports fast queries.
CREATE TABLE IF NOT EXISTS label_assignments (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    label_id TEXT NOT NULL,
    applied_by TEXT,
    applied_at TEXT NOT NULL,
    -- Soft archive timestamp; enables re-assigning a label after removal.
    archived_at TEXT,
    FOREIGN KEY(label_id) REFERENCES labels(id) ON DELETE CASCADE
);

-- label_gate_rules enforce label-based gating for workflow transitions.
-- Example: require label "release:ready" before moving to "ship".
CREATE TABLE IF NOT EXISTS label_gate_rules (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    label_id TEXT,
    category_id TEXT,
    message TEXT,
    created_at TEXT NOT NULL,
    -- Soft archive timestamp to preserve gate history.
    archived_at TEXT,
    FOREIGN KEY(label_id) REFERENCES labels(id) ON DELETE CASCADE,
    FOREIGN KEY(category_id) REFERENCES label_categories(id)
        ON DELETE CASCADE,
    CHECK(rule_type IN ('require_label', 'forbid_label', 'require_category', 'forbid_category'))
);

CREATE INDEX IF NOT EXISTS idx_label_categories_name
    ON label_categories(name);
CREATE INDEX IF NOT EXISTS idx_labels_category
    ON labels(category_id);
CREATE INDEX IF NOT EXISTS idx_label_assignments_entity
    ON label_assignments(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_label_assignments_label
    ON label_assignments(label_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_label_assignments_unique_active
    ON label_assignments(entity_type, entity_id, label_id)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_label_gate_rules_transition
    ON label_gate_rules(workflow_id, entity_type, from_state, to_state);

-- =============================================================================
-- Custom fields and structured metadata
-- =============================================================================

-- custom_field_definitions declare reusable fields per entity type.
-- Fields act like schema extensions without changing core tables.
-- options_json holds enum choices or structured config for special types.
CREATE TABLE IF NOT EXISTS custom_field_definitions (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL, -- e.g., task, project, goal
    field_type TEXT NOT NULL,  -- text, number, boolean, date, datetime, enum, json, url
    description TEXT,
    options_json TEXT NOT NULL DEFAULT '[]',
    is_required INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    UNIQUE(entity_type, name),
    CHECK(field_type IN ('text', 'number', 'boolean', 'date', 'datetime', 'enum', 'json', 'url')),
    CHECK(json_valid(options_json)),
    CHECK(is_required IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_custom_field_defs_entity
    ON custom_field_definitions(entity_type, name);
CREATE INDEX IF NOT EXISTS idx_custom_field_defs_archived
    ON custom_field_definitions(archived_at);

-- custom_field_values are append-only entries for each field assignment.
-- The "current" value for a field/entity is the latest created_at entry.
CREATE TABLE IF NOT EXISTS custom_field_values (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    field_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    value_json TEXT NOT NULL,
    created_by TEXT,
    source TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY(field_id) REFERENCES custom_field_definitions(id) ON DELETE CASCADE,
    CHECK(json_valid(value_json)),
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_custom_field_values_entity
    ON custom_field_values(entity_type, entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_custom_field_values_field
    ON custom_field_values(field_id, created_at DESC);

-- evidence_gate_rules enforce proof requirements on transitions.
-- Evaluation checks task_evidence and test_runs for required evidence.
CREATE TABLE IF NOT EXISTS evidence_gate_rules (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    -- Evidence type to match against task_evidence/test_runs.
    evidence_type TEXT NOT NULL,
    -- Minimum number of matching evidence records required to pass.
    min_count INTEGER NOT NULL DEFAULT 1,
    -- If true, evidence must indicate success (e.g., test run passed).
    require_success INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- Soft archive timestamp to preserve rule history.
    archived_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_evidence_gate_rules_transition
    ON evidence_gate_rules(workflow_id, entity_type, from_state, to_state);

-- =============================================================================
-- Automation rules and execution history
-- =============================================================================

-- automation_rules define event-driven actions (comment, task creation, etc).
-- Rules are append-only via revisions/events; archived_at disables without loss.
CREATE TABLE IF NOT EXISTS automation_rules (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    -- Event pattern matcher (exact or wildcard, e.g., task.completed or task.*).
    event_pattern TEXT NOT NULL,
    -- Optional filter for the aggregate that emitted the event.
    aggregate_type TEXT,
    aggregate_id TEXT,
    -- Action to execute when rule matches.
    action_type TEXT NOT NULL,
    -- JSON payload for action configuration.
    action_payload TEXT NOT NULL DEFAULT '{}',
    -- Rule enable/disable flag.
    enabled INTEGER NOT NULL DEFAULT 1,
    -- Cooldown to prevent repeated triggers for noisy events.
    cooldown_seconds REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,

    CHECK(json_valid(action_payload)),
    CHECK(action_type IN (
        'add_comment',
        'create_task',
        'update_task_status',
        'set_custom_field_value'
    )),
    CHECK(enabled IN (0, 1)),
    CHECK(cooldown_seconds >= 0)
);

CREATE INDEX IF NOT EXISTS idx_automation_rules_pattern
    ON automation_rules(event_pattern);
CREATE INDEX IF NOT EXISTS idx_automation_rules_enabled
    ON automation_rules(enabled, archived_at);

-- automation_rule_runs record each execution for auditability.
CREATE TABLE IF NOT EXISTS automation_rule_runs (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    event_id TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT,
    output TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(rule_id) REFERENCES automation_rules(id) ON DELETE CASCADE,
    CHECK(status IN ('running', 'skipped', 'dry_run', 'success', 'failed')),
    CHECK(json_valid(output))
);

CREATE INDEX IF NOT EXISTS idx_automation_rule_runs_rule
    ON automation_rule_runs(rule_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_automation_rule_runs_event
    ON automation_rule_runs(event_id);

-- =============================================================================
-- Orgs, products, portfolios, programs
-- =============================================================================

-- organizations define top-level ownership and governance.
CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    owner TEXT,
    owner_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(owner_id) REFERENCES actors(id) ON DELETE SET NULL,
    CHECK(status IN ('active', 'archived')),
    CHECK(json_valid(tags))
);

CREATE INDEX IF NOT EXISTS idx_organizations_status
    ON organizations(status);
CREATE INDEX IF NOT EXISTS idx_organizations_owner
    ON organizations(owner);
CREATE INDEX IF NOT EXISTS idx_organizations_owner_id
    ON organizations(owner_id);

-- teams define membership and staffing within organizations.
CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    org_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    owner TEXT,
    owner_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE SET NULL,
    FOREIGN KEY(owner_id) REFERENCES actors(id) ON DELETE SET NULL,
    CHECK(status IN ('active', 'archived')),
    CHECK(json_valid(tags))
);

CREATE INDEX IF NOT EXISTS idx_teams_org
    ON teams(org_id);
CREATE INDEX IF NOT EXISTS idx_teams_status
    ON teams(status);
CREATE INDEX IF NOT EXISTS idx_teams_owner_id
    ON teams(owner_id);

-- organization_members are the authoritative org-to-actor membership edges.
CREATE TABLE IF NOT EXISTS organization_members (
    organization_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (organization_id, actor_id),
    FOREIGN KEY(organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY(actor_id) REFERENCES actors(id) ON DELETE CASCADE,
    CHECK(position >= 0)
);

CREATE INDEX IF NOT EXISTS idx_organization_members_org
    ON organization_members(organization_id, position);
CREATE INDEX IF NOT EXISTS idx_organization_members_actor
    ON organization_members(actor_id, organization_id);

-- team_members are the authoritative team-to-actor membership edges.
CREATE TABLE IF NOT EXISTS team_members (
    team_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (team_id, actor_id),
    FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
    FOREIGN KEY(actor_id) REFERENCES actors(id) ON DELETE CASCADE,
    CHECK(position >= 0)
);

CREATE INDEX IF NOT EXISTS idx_team_members_team
    ON team_members(team_id, position);
CREATE INDEX IF NOT EXISTS idx_team_members_actor
    ON team_members(actor_id, team_id);

-- portfolios group initiatives for rollups and prioritization.
CREATE TABLE IF NOT EXISTS portfolios (
    id TEXT PRIMARY KEY,
    org_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    owner TEXT,
    owner_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE SET NULL,
    FOREIGN KEY(owner_id) REFERENCES actors(id) ON DELETE SET NULL,
    CHECK(status IN ('active', 'archived')),
    CHECK(json_valid(tags))
);

CREATE INDEX IF NOT EXISTS idx_portfolios_org
    ON portfolios(org_id);
CREATE INDEX IF NOT EXISTS idx_portfolios_status
    ON portfolios(status);
CREATE INDEX IF NOT EXISTS idx_portfolios_owner_id
    ON portfolios(owner_id);

-- portfolio_goals are authoritative direct portfolio-to-goal links.
CREATE TABLE IF NOT EXISTS portfolio_goals (
    portfolio_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (portfolio_id, goal_id),
    FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE,
    CHECK(position >= 0)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_goals_portfolio
    ON portfolio_goals(portfolio_id, position);
CREATE INDEX IF NOT EXISTS idx_portfolio_goals_goal
    ON portfolio_goals(goal_id, portfolio_id);

-- portfolio_objectives are authoritative direct portfolio-to-objective links.
CREATE TABLE IF NOT EXISTS portfolio_objectives (
    portfolio_id TEXT NOT NULL,
    objective_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (portfolio_id, objective_id),
    FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
    FOREIGN KEY(objective_id) REFERENCES objectives(id) ON DELETE CASCADE,
    CHECK(position >= 0)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_objectives_portfolio
    ON portfolio_objectives(portfolio_id, position);
CREATE INDEX IF NOT EXISTS idx_portfolio_objectives_objective
    ON portfolio_objectives(objective_id, portfolio_id);

-- programs group related projects, optionally under portfolios.
CREATE TABLE IF NOT EXISTS programs (
    id TEXT PRIMARY KEY,
    org_id TEXT,
    portfolio_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    owner TEXT,
    owner_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE SET NULL,
    FOREIGN KEY(portfolio_id) REFERENCES portfolios(id) ON DELETE SET NULL,
    FOREIGN KEY(owner_id) REFERENCES actors(id) ON DELETE SET NULL,
    CHECK(status IN ('active', 'archived')),
    CHECK(json_valid(tags))
);

CREATE INDEX IF NOT EXISTS idx_programs_org
    ON programs(org_id);
CREATE INDEX IF NOT EXISTS idx_programs_portfolio
    ON programs(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_programs_status
    ON programs(status);
CREATE INDEX IF NOT EXISTS idx_programs_owner_id
    ON programs(owner_id);

-- program_goals are authoritative direct program-to-goal links.
CREATE TABLE IF NOT EXISTS program_goals (
    program_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (program_id, goal_id),
    FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE,
    CHECK(position >= 0)
);

CREATE INDEX IF NOT EXISTS idx_program_goals_program
    ON program_goals(program_id, position);
CREATE INDEX IF NOT EXISTS idx_program_goals_goal
    ON program_goals(goal_id, program_id);

-- program_objectives are authoritative direct program-to-objective links.
CREATE TABLE IF NOT EXISTS program_objectives (
    program_id TEXT NOT NULL,
    objective_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (program_id, objective_id),
    FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE CASCADE,
    FOREIGN KEY(objective_id) REFERENCES objectives(id) ON DELETE CASCADE,
    CHECK(position >= 0)
);

CREATE INDEX IF NOT EXISTS idx_program_objectives_program
    ON program_objectives(program_id, position);
CREATE INDEX IF NOT EXISTS idx_program_objectives_objective
    ON program_objectives(objective_id, program_id);

-- products track strategic ownership and product-level metadata.
-- Projects, goals, and plans may reference products for governance.
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    vision TEXT,
    repository_url TEXT,
    service_urls TEXT NOT NULL DEFAULT '[]',
    owner TEXT,
    owner_id TEXT,
    team TEXT NOT NULL DEFAULT '[]',  -- Descriptive team labels, not Team entity IDs.
    tags TEXT NOT NULL DEFAULT '[]',
    product_type TEXT NOT NULL DEFAULT 'service',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    -- Workflow binding for product lifecycle governance.
    workflow_id TEXT,
    -- Denormalized workflow state for dashboards; history in state_transition_log.
    current_state TEXT DEFAULT 'planning',
    -- JSON: workflow metadata captured for the current product state.
    workflow_metadata TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(owner_id) REFERENCES actors(id) ON DELETE SET NULL,
    CHECK(status IN ('planning', 'active', 'mature', 'sunset', 'archived')),
    CHECK(json_valid(service_urls)),
    CHECK(json_valid(team)),
    CHECK(json_valid(tags)),
    CHECK(json_valid(workflow_metadata))
);

CREATE INDEX IF NOT EXISTS idx_products_status
    ON products(status);
CREATE INDEX IF NOT EXISTS idx_products_name
    ON products(name);
CREATE INDEX IF NOT EXISTS idx_products_owner
    ON products(owner);
CREATE INDEX IF NOT EXISTS idx_products_owner_id
    ON products(owner_id);
CREATE INDEX IF NOT EXISTS idx_products_type
    ON products(product_type);

-- =============================================================================
-- Planning, goals, objectives
-- =============================================================================

-- goals represent long/medium/short-term outcomes.
-- Projects and products can attach to goals for rollups.
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    horizon TEXT NOT NULL DEFAULT 'short_term',
    target_date TEXT,
    owner TEXT,
    owner_id TEXT,
    product_id TEXT,
    project_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    progress_percent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    -- Workflow binding for goal lifecycle (e.g., draft -> active -> achieved).
    workflow_id TEXT,
    -- Denormalized workflow state for rapid rollups/filters.
    current_state TEXT,
    -- JSON: workflow metadata (guards, reviewer notes, automation hints).
    workflow_metadata TEXT DEFAULT '{}',

    FOREIGN KEY(owner_id) REFERENCES actors(id) ON DELETE SET NULL,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
    CHECK(status IN ('active', 'completed', 'on_hold', 'archived')),
    CHECK(horizon IN ('short_term', 'medium_term', 'long_term')),
    CHECK(progress_percent >= 0 AND progress_percent <= 100),
    CHECK(json_valid(tags)),
    CHECK(json_valid(workflow_metadata))
);

CREATE INDEX IF NOT EXISTS idx_goals_status
    ON goals(status);
CREATE INDEX IF NOT EXISTS idx_goals_horizon
    ON goals(horizon);
CREATE INDEX IF NOT EXISTS idx_goals_product
    ON goals(product_id);
CREATE INDEX IF NOT EXISTS idx_goals_project
    ON goals(project_id);
CREATE INDEX IF NOT EXISTS idx_goals_owner_id
    ON goals(owner_id);

-- objectives are intermediate goals under a goal.
CREATE TABLE IF NOT EXISTS objectives (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    target_date TEXT,
    owner TEXT,
    owner_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    progress_percent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    -- Workflow binding for objective lifecycle tracking.
    workflow_id TEXT,
    -- Denormalized workflow state to avoid replaying transitions.
    current_state TEXT,
    -- JSON: workflow metadata captured at the current objective state.
    workflow_metadata TEXT DEFAULT '{}',

    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE CASCADE,
    FOREIGN KEY(owner_id) REFERENCES actors(id) ON DELETE SET NULL,
    CHECK(status IN ('active', 'completed', 'on_hold', 'archived')),
    CHECK(progress_percent >= 0 AND progress_percent <= 100),
    CHECK(json_valid(tags)),
    CHECK(json_valid(workflow_metadata))
);

CREATE INDEX IF NOT EXISTS idx_objectives_goal
    ON objectives(goal_id);
CREATE INDEX IF NOT EXISTS idx_objectives_status
    ON objectives(status);
CREATE INDEX IF NOT EXISTS idx_objectives_owner_id
    ON objectives(owner_id);

-- key_results capture measurable outcomes for objectives.
CREATE TABLE IF NOT EXISTS key_results (
    id TEXT PRIMARY KEY,
    objective_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    current_value REAL,
    target_value REAL,
    unit TEXT,
    owner TEXT,
    owner_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    progress_percent INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(objective_id) REFERENCES objectives(id) ON DELETE CASCADE,
    FOREIGN KEY(owner_id) REFERENCES actors(id) ON DELETE SET NULL,
    CHECK(status IN ('active', 'completed', 'on_hold', 'archived')),
    CHECK(progress_percent >= 0 AND progress_percent <= 100),
    CHECK(json_valid(tags))
);

CREATE INDEX IF NOT EXISTS idx_key_results_objective
    ON key_results(objective_id);
CREATE INDEX IF NOT EXISTS idx_key_results_status
    ON key_results(status);
CREATE INDEX IF NOT EXISTS idx_key_results_owner_id
    ON key_results(owner_id);

-- plans are structured planning documents tied to execution.
-- Linkages to tasks/goals/objectives enable traceability.
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    format TEXT NOT NULL DEFAULT 'json',
    content TEXT NOT NULL,
    product_id TEXT,
    project_id TEXT,
    goal_id TEXT,
    objective_id TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY(goal_id) REFERENCES goals(id) ON DELETE SET NULL,
    FOREIGN KEY(objective_id) REFERENCES objectives(id) ON DELETE SET NULL,
    CHECK(status IN ('draft', 'active', 'completed', 'archived')),
    CHECK(format IN ('json', 'yaml')),
    CHECK(json_valid(tags))
);

CREATE INDEX IF NOT EXISTS idx_plans_status
    ON plans(status);
CREATE INDEX IF NOT EXISTS idx_plans_project
    ON plans(project_id);
CREATE INDEX IF NOT EXISTS idx_plans_goal
    ON plans(goal_id);
CREATE INDEX IF NOT EXISTS idx_plans_objective
    ON plans(objective_id);

-- plan_tasks are the authoritative plan-to-task execution links.
CREATE TABLE IF NOT EXISTS plan_tasks (
    plan_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (plan_id, task_id),
    FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CHECK(position >= 0)
);

CREATE INDEX IF NOT EXISTS idx_plan_tasks_plan
    ON plan_tasks(plan_id, position);
CREATE INDEX IF NOT EXISTS idx_plan_tasks_task
    ON plan_tasks(task_id, plan_id);

-- plan_test_jobs define repeatable test execution pipelines.
-- Results are captured in test_runs and linked back to plans/tasks.
CREATE TABLE IF NOT EXISTS plan_test_jobs (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    mode TEXT NOT NULL,
    project_path TEXT NOT NULL,
    test_command TEXT NOT NULL,
    setup_command TEXT,
    working_dir TEXT,
    env_vars TEXT NOT NULL,
    timeout REAL NOT NULL,
    -- JSON array: log capture patterns; retained in test_runs.logs payloads.
    capture_logs TEXT NOT NULL,
    -- JSON array: artifact paths to collect; tracked with size/timestamps.
    save_artifacts TEXT NOT NULL,
    transition_on_success TEXT,
    transition_on_failure TEXT,
    transition_by TEXT,
    transition_reason TEXT,
    project_id TEXT,
    server_id TEXT,
    server_name TEXT,
    remote_path TEXT,
    exclude_patterns TEXT,
    stream_output INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- Soft archive timestamp; plans keep test job history intact.
    archived_at TEXT,

    FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY(server_id) REFERENCES test_servers(id) ON DELETE SET NULL,
    CHECK(mode IN ('local', 'aws')),
    CHECK(json_valid(env_vars)),
    CHECK(json_valid(capture_logs)),
    CHECK(json_valid(save_artifacts)),
    CHECK(exclude_patterns IS NULL OR json_valid(exclude_patterns)),
    CHECK(timeout >= 0),
    CHECK(stream_output IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_plan_test_jobs_plan_id
    ON plan_test_jobs(plan_id);

-- plan_test_job_tasks are the authoritative task links for a plan test job.
CREATE TABLE IF NOT EXISTS plan_test_job_tasks (
    plan_test_job_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (plan_test_job_id, task_id),
    FOREIGN KEY(plan_test_job_id) REFERENCES plan_test_jobs(id) ON DELETE CASCADE,
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CHECK(position >= 0)
);

CREATE INDEX IF NOT EXISTS idx_plan_test_job_tasks_job
    ON plan_test_job_tasks(plan_test_job_id, position);
CREATE INDEX IF NOT EXISTS idx_plan_test_job_tasks_task
    ON plan_test_job_tasks(task_id, plan_test_job_id);

-- =============================================================================
-- Sessions, activity, and documentation
-- =============================================================================

-- sessions track agent runs, cost, and summary context.
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    claude_session_id TEXT,
    context_summary TEXT,
    last_prompt TEXT,
    last_response_summary TEXT,
    state TEXT NOT NULL DEFAULT '{}',
    cost_usd REAL NOT NULL DEFAULT 0,
    token_count INTEGER NOT NULL DEFAULT 0,
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    ended_at TEXT,

    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
    CHECK(json_valid(state)),
    CHECK(cost_usd >= 0),
    CHECK(token_count >= 0),
    CHECK(message_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_sessions_project
    ON sessions(project_id);

-- session_messages is the immutable transcript for each session.
CREATE TABLE IF NOT EXISTS session_messages (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- preferred built-ins: system, user, assistant, tool; custom roles remain valid
    content TEXT NOT NULL,
    tokens INTEGER,
    cost_usd REAL,
    timestamp TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',

    FOREIGN KEY(session_id) REFERENCES sessions(id),
    CHECK(metadata IS NOT NULL AND json_valid(metadata)),
    CHECK(tokens IS NULL OR tokens >= 0),
    CHECK(cost_usd IS NULL OR cost_usd >= 0)
);

CREATE INDEX IF NOT EXISTS idx_session_messages
    ON session_messages(session_id, timestamp);

-- activity_log is a coarse, append-only audit log.
-- Useful for timelines and "what changed" digest views.
CREATE TABLE IF NOT EXISTS activity_log (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    session_id TEXT,
    project_id TEXT,
    entity_type TEXT NOT NULL,  -- intentionally open coarse-audit family; may include plugin or derived types
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,  -- intentionally open coarse-audit verb/event label
    details TEXT NOT NULL DEFAULT '{}',
    user_id TEXT,
    timestamp TEXT NOT NULL,

    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
    CHECK(json_valid(details))
);

CREATE INDEX IF NOT EXISTS idx_activity_project
    ON activity_log(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_activity_entity
    ON activity_log(entity_type, entity_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_activity_time
    ON activity_log(timestamp DESC);

-- documents indexes authored/generated docs tied to projects.
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    doc_type TEXT NOT NULL,  -- readme, api_doc, changelog, etc.
    file_path TEXT NOT NULL,
    title TEXT,
    auto_generated INTEGER NOT NULL DEFAULT 0,
    last_generated_at TEXT,
    generation_prompt TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
    CHECK(doc_type IN ('readme', 'api_doc', 'changelog', 'architecture', 'contributing', 'license', 'custom')),
    CHECK(auto_generated IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_documents_project
    ON documents(project_id);

-- work_snapshot_reviews records review checkpoints.
-- Used to compute "what changed since last review".
CREATE TABLE IF NOT EXISTS work_snapshot_reviews (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    reviewed_by TEXT,
    note TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',

    CHECK(scope_type IN ('organization', 'portfolio', 'program', 'project')),
    CHECK(json_valid(metadata))
);

CREATE INDEX IF NOT EXISTS idx_work_snapshot_reviews_scope
    ON work_snapshot_reviews(scope_type, scope_id, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_work_snapshot_reviews_reviewed_at
    ON work_snapshot_reviews(reviewed_at);

-- saved_searches persist reusable filters for queues/dashboards.
CREATE TABLE IF NOT EXISTS saved_searches (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner TEXT,
    owner_id TEXT,
    scope_type TEXT NOT NULL DEFAULT 'global',
    scope_id TEXT,
    filters TEXT NOT NULL,
    sort_by TEXT,
    sort_dir TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- Soft archive timestamp; saved views are hidden but remain queryable.
    archived_at TEXT,

    FOREIGN KEY(owner_id) REFERENCES actors(id) ON DELETE SET NULL,
    CHECK(scope_type IN ('global', 'organization', 'program', 'project')),
    CHECK(json_valid(filters)),
    CHECK(sort_dir IS NULL OR sort_dir IN ('asc', 'desc'))
);

CREATE INDEX IF NOT EXISTS idx_saved_searches_owner
    ON saved_searches(owner);
CREATE INDEX IF NOT EXISTS idx_saved_searches_owner_id
    ON saved_searches(owner_id);
CREATE INDEX IF NOT EXISTS idx_saved_searches_scope
    ON saved_searches(scope_type, scope_id);
CREATE INDEX IF NOT EXISTS idx_saved_searches_name
    ON saved_searches(name);

-- =============================================================================
-- Remote operations and test infrastructure
-- =============================================================================

-- remote_hosts defines external execution targets (SSH, cloud, etc.).
CREATE TABLE IF NOT EXISTS remote_hosts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 22,
    username TEXT NOT NULL,
    key_path TEXT,
    host_type TEXT NOT NULL DEFAULT 'ssh',
    aws_instance_id TEXT,
    aws_region TEXT,
    default_remote_path TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,

    CHECK(host_type IN ('ssh', 'aws_ec2')),
    CHECK(json_valid(tags)),
    CHECK(port > 0 AND port <= 65535)
);

-- sync_configs describe project sync plans for a host.
CREATE TABLE IF NOT EXISTS sync_configs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    remote_host_id TEXT NOT NULL,
    local_path TEXT NOT NULL,
    remote_path TEXT NOT NULL,
    exclude_patterns TEXT NOT NULL DEFAULT '[]',
    sync_mode TEXT NOT NULL DEFAULT 'mirror',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE(project_id, remote_host_id),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(remote_host_id) REFERENCES remote_hosts(id) ON DELETE CASCADE,
    CHECK(json_valid(exclude_patterns)),
    CHECK(sync_mode IN ('mirror', 'update', 'backup'))
);

-- sync_history is the append-only log of sync executions.
CREATE TABLE IF NOT EXISTS sync_history (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    sync_config_id TEXT NOT NULL,
    direction TEXT NOT NULL,  -- push or pull
    status TEXT NOT NULL,     -- started, completed, failed
    files_transferred INTEGER DEFAULT 0,
    bytes_transferred INTEGER DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_message TEXT,
    output TEXT,              -- full rsync output

    FOREIGN KEY(sync_config_id) REFERENCES sync_configs(id),
    CHECK(direction IN ('push', 'pull')),
    CHECK(status IN ('started', 'in_progress', 'completed', 'failed')),
    CHECK(files_transferred IS NULL OR files_transferred >= 0),
    CHECK(bytes_transferred IS NULL OR bytes_transferred >= 0)
);

CREATE INDEX IF NOT EXISTS idx_sync_history_config
    ON sync_history(sync_config_id, started_at DESC);

-- test_servers track ephemeral compute for test execution.
CREATE TABLE IF NOT EXISTS test_servers (
    id TEXT PRIMARY KEY,
    instance_id TEXT UNIQUE,
    name TEXT NOT NULL,
    project_id TEXT,
    config TEXT NOT NULL DEFAULT '{}',  -- JSON: TestServerConfig
    public_ip TEXT,
    private_ip TEXT,
    state TEXT NOT NULL DEFAULT 'pending',
    region TEXT NOT NULL,
    availability_zone TEXT NOT NULL,
    hourly_price REAL NOT NULL DEFAULT 0,
    estimated_cost REAL NOT NULL DEFAULT 0,
    launched_at TEXT NOT NULL,
    terminated_at TEXT,
    last_activity TEXT,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),

    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
    CHECK(state IN ('pending', 'running', 'stopping', 'terminated', 'interrupted')),
    CHECK(json_valid(config)),
    CHECK(hourly_price >= 0),
    CHECK(estimated_cost >= 0)
);

CREATE INDEX IF NOT EXISTS idx_test_servers_state
    ON test_servers(state);
CREATE INDEX IF NOT EXISTS idx_test_servers_project
    ON test_servers(project_id);
CREATE INDEX IF NOT EXISTS idx_test_servers_instance
    ON test_servers(instance_id);

-- test_runs is the immutable record of executed tests.
-- Includes stdout/stderr, artifacts, and structured logs.
CREATE TABLE IF NOT EXISTS test_runs (
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    project_id TEXT,
    config TEXT NOT NULL DEFAULT '{}',  -- JSON: TestRunConfig
    success INTEGER NOT NULL DEFAULT 0,
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    duration_seconds REAL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    -- JSON: captured log contents with size_bytes/created_at/modified_at/pruned_at.
    logs TEXT DEFAULT '{}',
    -- JSON: artifact entries with local_path + size/timestamps for retention/LRU.
    artifacts TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),

    FOREIGN KEY(server_id) REFERENCES test_servers(id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
    CHECK(json_valid(config)),
    CHECK(success IN (0, 1)),
    CHECK(duration_seconds IS NULL OR duration_seconds >= 0),
    CHECK(logs IS NULL OR json_valid(logs)),
    CHECK(artifacts IS NULL OR json_valid(artifacts))
);

CREATE INDEX IF NOT EXISTS idx_test_runs_server
    ON test_runs(server_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_runs_project
    ON test_runs(project_id, started_at DESC);

-- test_run_retention_policies capture scoped storage budgets for test outputs.
-- scope_type is "project" or "organization" (orgs are resolved via portfolio/program).
-- Budgets are evaluated by TestRunRetentionService for alerts and LRU pruning.
CREATE TABLE IF NOT EXISTS test_run_retention_policies (
    id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    -- Max bytes for stdout/stderr/logs combined (0 = no limit).
    max_log_bytes INTEGER NOT NULL DEFAULT 0,
    -- Max bytes for artifacts (0 = no limit).
    max_artifact_bytes INTEGER NOT NULL DEFAULT 0,
    -- Max age in days for outputs (0 = no age-based pruning).
    max_age_days INTEGER NOT NULL DEFAULT 0,
    -- Operator notes for why this budget exists (owner intent, risk).
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    last_revision_number INTEGER NOT NULL DEFAULT 0,

    UNIQUE(scope_type, scope_id),
    CHECK(scope_type IN ('project', 'organization')),
    CHECK(max_log_bytes >= 0),
    CHECK(max_artifact_bytes >= 0),
    CHECK(max_age_days >= 0)
);

CREATE INDEX IF NOT EXISTS idx_test_run_retention_scope
    ON test_run_retention_policies(scope_type, scope_id);

-- network_environments group servers for network test scenarios.
CREATE TABLE IF NOT EXISTS network_environments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    config TEXT NOT NULL DEFAULT '{}',  -- JSON: NetworkTestConfig
    state TEXT NOT NULL DEFAULT 'pending',
    security_group_id TEXT,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    destroyed_at TEXT,

    CHECK(state IN ('pending', 'running', 'stopping', 'terminated', 'interrupted')),
    CHECK(json_valid(config))
);

CREATE INDEX IF NOT EXISTS idx_network_env_state
    ON network_environments(state);

-- network_environment_servers are the authoritative environment-to-server edges.
-- server_role preserves role -> server mappings when available.
CREATE TABLE IF NOT EXISTS network_environment_servers (
    network_environment_id TEXT NOT NULL,
    server_id TEXT NOT NULL,
    server_role TEXT,
    position INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (network_environment_id, server_id),
    UNIQUE (network_environment_id, server_role),
    FOREIGN KEY(network_environment_id) REFERENCES network_environments(id) ON DELETE CASCADE,
    FOREIGN KEY(server_id) REFERENCES test_servers(id) ON DELETE CASCADE,
    CHECK(position >= 0)
);

CREATE INDEX IF NOT EXISTS idx_network_environment_servers_environment
    ON network_environment_servers(network_environment_id, position);
CREATE INDEX IF NOT EXISTS idx_network_environment_servers_server
    ON network_environment_servers(server_id, network_environment_id);

-- aws_costs is append-only cost history for test servers.
CREATE TABLE IF NOT EXISTS aws_costs (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    instance_type TEXT NOT NULL,
    hours REAL NOT NULL,
    cost_usd REAL NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),

    FOREIGN KEY(server_id) REFERENCES test_servers(id) ON DELETE CASCADE,
    CHECK(hours >= 0),
    CHECK(cost_usd >= 0)
);

CREATE INDEX IF NOT EXISTS idx_aws_costs_server
    ON aws_costs(server_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_aws_costs_time
    ON aws_costs(recorded_at DESC);

-- spot_price_cache avoids repeated AWS spot price lookups.
CREATE TABLE IF NOT EXISTS spot_price_cache (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    id TEXT PRIMARY KEY,
    instance_type TEXT NOT NULL,
    availability_zone TEXT NOT NULL,
    price REAL NOT NULL,
    timestamp TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),

    UNIQUE(instance_type, availability_zone, timestamp),
    CHECK(price >= 0)
);

CREATE INDEX IF NOT EXISTS idx_spot_price_type_az
    ON spot_price_cache(instance_type, availability_zone, timestamp DESC);

-- =============================================================================
-- API auth and rate limiting
-- =============================================================================

-- api_keys stores auth credentials and metadata for the API.
CREATE TABLE IF NOT EXISTS api_keys (
    last_revision_number INTEGER NOT NULL DEFAULT 0,
    last_event_sequence INTEGER NOT NULL DEFAULT 0,
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    expires_at TEXT,
    last_used_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    scopes TEXT NOT NULL,
    metadata TEXT,
    rate_limit INTEGER,
    -- Soft archive timestamp; remove keys without losing audit history.
    archived_at TEXT,

    CHECK (is_active IN (0, 1)),
    CHECK (scopes IS NOT NULL AND json_valid(scopes)),
    CHECK (metadata IS NULL OR json_valid(metadata)),
    CHECK (rate_limit IS NULL OR rate_limit >= 0)
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(prefix);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);

-- rate_limit_usage stores per-key request counters for throttling.
CREATE TABLE IF NOT EXISTS rate_limit_usage (
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    api_key_id TEXT NOT NULL,
    window_start TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (api_key_id, window_start),
    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE,
    CHECK(request_count >= 0)
);
