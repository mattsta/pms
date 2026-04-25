"""FastAPI dependency injection for PMS services."""

from __future__ import annotations

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.repositories.api_key_repository import ApiKeyRepository
from pms.services.actor_service import ActorService
from pms.services.agent_loop_service import AgentLoopService
from pms.services.auth_service import AuthService
from pms.services.automation_rule_service import AutomationRuleService
from pms.services.comment_service import CommentService
from pms.services.custom_field_service import CustomFieldService
from pms.services.evidence_gate_service import EvidenceGateService
from pms.services.goal_service import GoalService
from pms.services.history_bundle_service import HistoryBundleService
from pms.services.label_service import LabelService
from pms.services.lineage_service import LineageService
from pms.services.organization_service import OrganizationService
from pms.services.plan_service import PlanService
from pms.services.plan_test_job_service import PlanTestJobService
from pms.services.portfolio_service import PortfolioService
from pms.services.product_service import ProductService
from pms.services.program_service import ProgramService
from pms.services.project_service import ProjectService
from pms.services.proof_bundle_service import ProofBundleService
from pms.services.queue_service import QueueService
from pms.services.saved_search_service import SavedSearchService
from pms.services.task_evidence_service import TaskEvidenceService
from pms.services.task_service import TaskService
from pms.services.team_service import TeamService
from pms.services.test_run_retention_policy_service import (
    TestRunRetentionPolicyService,
)
from pms.services.test_run_retention_service import TestRunRetentionService
from pms.services.test_run_service import TestRunService
from pms.services.work_snapshot_service import WorkSnapshotService

# Global service instances (initialized on startup)
_db: Database | None = None
_auth_service: AuthService | None = None
_actor_service: ActorService | None = None
_goal_service: GoalService | None = None
_lineage_service: LineageService | None = None
_organization_service: OrganizationService | None = None
_plan_service: PlanService | None = None
_plan_test_job_service: PlanTestJobService | None = None
_portfolio_service: PortfolioService | None = None
_product_service: ProductService | None = None
_program_service: ProgramService | None = None
_project_service: ProjectService | None = None
_task_service: TaskService | None = None
_task_evidence_service: TaskEvidenceService | None = None
_test_run_service: TestRunService | None = None
_test_run_retention_service: TestRunRetentionService | None = None
_test_run_retention_policy_service: TestRunRetentionPolicyService | None = None
_label_service: LabelService | None = None
_team_service: TeamService | None = None
_saved_search_service: SavedSearchService | None = None
_queue_service: QueueService | None = None
_work_snapshot_service: WorkSnapshotService | None = None
_evidence_gate_service: EvidenceGateService | None = None
_proof_bundle_service: ProofBundleService | None = None
_history_bundle_service: HistoryBundleService | None = None
_agent_loop_service: AgentLoopService | None = None
_custom_field_service: CustomFieldService | None = None
_comment_service: CommentService | None = None
_automation_rule_service: AutomationRuleService | None = None


async def init_services(database: Database) -> None:
    """Initialize all services with database."""
    global \
        _db, \
        _auth_service, \
        _actor_service, \
        _goal_service, \
        _lineage_service, \
        _organization_service, \
        _plan_service, \
        _plan_test_job_service, \
        _portfolio_service, \
        _product_service, \
        _program_service, \
        _project_service, \
        _task_service, \
        _task_evidence_service, \
        _test_run_service, \
        _test_run_retention_service, \
        _test_run_retention_policy_service, \
        _label_service, \
        _team_service, \
        _saved_search_service, \
        _queue_service, \
        _work_snapshot_service, \
        _evidence_gate_service, \
        _proof_bundle_service, \
        _history_bundle_service, \
        _agent_loop_service, \
        _custom_field_service, \
        _comment_service, \
        _automation_rule_service

    _db = database
    event_store = EventStore(database)
    revision_store = RevisionStore(database)
    metrics = MetricsCollector(database)

    # Initialize auth service
    api_key_repo = ApiKeyRepository(database)
    _auth_service = AuthService(api_key_repo)

    _actor_service = ActorService(database, event_store, revision_store, metrics)
    _goal_service = GoalService(database, event_store, revision_store, metrics)
    _lineage_service = LineageService(database, event_store, revision_store, metrics)
    _organization_service = OrganizationService(
        database, event_store, revision_store, metrics
    )
    _plan_service = PlanService(database, event_store, revision_store, metrics)
    _plan_test_job_service = PlanTestJobService(
        database, event_store, revision_store, metrics
    )
    _portfolio_service = PortfolioService(
        database, event_store, revision_store, metrics
    )
    _product_service = ProductService(database, event_store, revision_store, metrics)
    _program_service = ProgramService(database, event_store, revision_store, metrics)
    _project_service = ProjectService(database, event_store, revision_store, metrics)
    _task_service = TaskService(database, event_store, revision_store, metrics)
    _task_evidence_service = TaskEvidenceService(database, metrics)
    _test_run_service = TestRunService(database, metrics)
    _test_run_retention_service = TestRunRetentionService(database, metrics)
    from pms.repositories.test_run_retention_policy_repository import (
        TestRunRetentionPolicyRepository,
    )

    policy_repo = TestRunRetentionPolicyRepository(database)
    _test_run_retention_policy_service = TestRunRetentionPolicyService(
        policy_repo,
        metrics,
    )
    _label_service = LabelService(database, metrics)
    _evidence_gate_service = EvidenceGateService(database, metrics)
    _team_service = TeamService(database, event_store, revision_store, metrics)
    from pms.repositories.saved_search_repository import SavedSearchRepository

    saved_search_repo = SavedSearchRepository(database)
    _saved_search_service = SavedSearchService(
        saved_search_repo, _task_service, metrics, database
    )
    _queue_service = QueueService(_task_service)
    _work_snapshot_service = WorkSnapshotService(
        database,
        metrics,
        project_service=_project_service,
        organization_service=_organization_service,
        program_service=_program_service,
        portfolio_service=_portfolio_service,
        lineage_service=_lineage_service,
        retention_service=_test_run_retention_service,
    )
    _proof_bundle_service = ProofBundleService(
        task_service=_task_service,
        evidence_service=_task_evidence_service,
        test_run_service=_test_run_service,
    )
    _history_bundle_service = HistoryBundleService(database)
    _agent_loop_service = AgentLoopService(
        database,
        event_store,
        revision_store,
        metrics,
        goal_service=_goal_service,
    )
    _custom_field_service = CustomFieldService(database, metrics)
    _comment_service = CommentService(database, metrics)
    _automation_rule_service = AutomationRuleService(
        database,
        metrics,
        task_service=_task_service,
        comment_service=_comment_service,
        custom_field_service=_custom_field_service,
    )


async def get_db() -> Database:
    """Get database instance."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_services() first.")
    return _db


async def get_agent_loop_service() -> AgentLoopService:
    """Get AgentLoopService instance."""
    if _agent_loop_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _agent_loop_service


async def get_custom_field_service() -> CustomFieldService:
    """Get CustomFieldService instance."""
    if _custom_field_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _custom_field_service


async def get_comment_service() -> CommentService:
    """Get CommentService instance."""
    if _comment_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _comment_service


async def get_automation_rule_service() -> AutomationRuleService:
    """Get AutomationRuleService instance."""
    if _automation_rule_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _automation_rule_service


async def get_auth_service() -> AuthService:
    """Get AuthService instance."""
    if _auth_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _auth_service


async def get_actor_service() -> ActorService:
    """Get ActorService instance."""
    if _actor_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _actor_service


async def get_goal_service() -> GoalService:
    """Get GoalService instance."""
    if _goal_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _goal_service


async def get_lineage_service() -> LineageService:
    """Get LineageService instance."""
    if _lineage_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _lineage_service


async def get_plan_service() -> PlanService:
    """Get PlanService instance."""
    if _plan_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _plan_service


async def get_plan_test_job_service() -> PlanTestJobService:
    """Get PlanTestJobService instance."""
    if _plan_test_job_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _plan_test_job_service


async def get_organization_service() -> OrganizationService:
    """Get OrganizationService instance."""
    if _organization_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _organization_service


async def get_team_service() -> TeamService:
    """Get TeamService instance."""
    if _team_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _team_service


async def get_saved_search_service() -> SavedSearchService:
    """Get SavedSearchService instance."""
    if _saved_search_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _saved_search_service


async def get_queue_service() -> QueueService:
    """Get QueueService instance."""
    if _queue_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _queue_service


async def get_history_bundle_service() -> HistoryBundleService:
    """Get HistoryBundleService instance."""
    if _history_bundle_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _history_bundle_service


async def get_work_snapshot_service() -> WorkSnapshotService:
    """Get WorkSnapshotService instance."""
    if _work_snapshot_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _work_snapshot_service


async def get_evidence_gate_service() -> EvidenceGateService:
    """Get EvidenceGateService instance."""
    if _evidence_gate_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _evidence_gate_service


async def get_proof_bundle_service() -> ProofBundleService:
    """Get ProofBundleService instance."""
    if _proof_bundle_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _proof_bundle_service


async def get_portfolio_service() -> PortfolioService:
    """Get PortfolioService instance."""
    if _portfolio_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _portfolio_service


async def get_program_service() -> ProgramService:
    """Get ProgramService instance."""
    if _program_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _program_service


async def get_product_service() -> ProductService:
    """Get ProductService instance."""
    if _product_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _product_service


async def get_project_service() -> ProjectService:
    """Get ProjectService instance."""
    if _project_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _project_service


async def get_task_service() -> TaskService:
    """Get TaskService instance."""
    if _task_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _task_service


async def get_task_evidence_service() -> TaskEvidenceService:
    """Get TaskEvidenceService instance."""
    if _task_evidence_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _task_evidence_service


async def get_test_run_service() -> TestRunService:
    """Get TestRunService instance."""
    if _test_run_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _test_run_service


async def get_test_run_retention_service() -> TestRunRetentionService:
    """Get TestRunRetentionService instance."""
    if _test_run_retention_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _test_run_retention_service


async def get_test_run_retention_policy_service() -> TestRunRetentionPolicyService:
    """Get TestRunRetentionPolicyService instance."""
    if _test_run_retention_policy_service is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _test_run_retention_policy_service


async def get_label_service() -> LabelService:
    """Get LabelService instance."""
    if _label_service is None:
        raise RuntimeError("Services not initialized")
    return _label_service
