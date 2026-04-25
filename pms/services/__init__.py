"""Service layer for business logic."""

from pms.services.actor_service import ActorGraphSnapshot, ActorService
from pms.services.agent_loop_service import AgentLoopService
from pms.services.automation_rule_service import (
    AutomationRuleService,
    AutomationRunResult,
)
from pms.services.checkout_manager import CheckoutManager
from pms.services.comment_service import (
    CommentItem,
    CommentPage,
    CommentService,
    WatcherPage,
)
from pms.services.custom_field_service import (
    CustomFieldService,
    CustomFieldValueItem,
    CustomFieldValuePage,
)
from pms.services.evidence_gate_service import EvidenceGateResult, EvidenceGateService
from pms.services.goal_service import GoalService, GoalSummary
from pms.services.history_bundle_service import HistoryBundleService
from pms.services.label_service import LabelGateResult, LabelService
from pms.services.lineage_service import LineageService
from pms.services.organization_service import (
    OrganizationDashboard,
    OrganizationDashboardItem,
    OrganizationService,
    OrganizationSummary,
)
from pms.services.plan_service import PlanService
from pms.services.plan_test_job_service import PlanTestJobRun, PlanTestJobService
from pms.services.portfolio_service import (
    PortfolioDashboard,
    PortfolioDashboardItem,
    PortfolioService,
    PortfolioSummary,
)
from pms.services.program_service import (
    ProgramDashboard,
    ProgramDashboardItem,
    ProgramService,
    ProgramSummary,
)
from pms.services.project_service import (
    ProjectDashboard,
    ProjectService,
    ProjectSummary,
)
from pms.services.proof_bundle_service import ProofBundleService
from pms.services.queue_service import QueueService, QueueSummary
from pms.services.remote_service import (
    RemoteHostInfo,
    RemoteService,
    SyncOperation,
)
from pms.services.saved_search_service import SavedSearchRun, SavedSearchService
from pms.services.task_evidence_service import (
    TaskEvidenceItem,
    TaskEvidencePage,
    TaskEvidenceService,
    TestRunSummary,
)
from pms.services.task_service import (
    DependencyGraph,
    TaskBatch,
    TaskService,
    TaskTree,
)
from pms.services.team_service import TeamService
from pms.services.test_execution_service import (
    TestExecutionConfig,
    TestExecutionService,
)
from pms.services.test_run_retention_policy_service import (
    TestRunRetentionPolicyService,
)
from pms.services.test_run_retention_service import (
    TestRunPruneSummary,
    TestRunRetentionService,
)
from pms.services.test_run_service import TestRunService
from pms.services.test_run_workflow_service import (
    TestRunWorkflowService,
    TestRunWorkflowTransition,
)
from pms.services.test_server_service import TestServerRegistration, TestServerService
from pms.services.work_snapshot_service import (
    WorkSnapshot,
    WorkSnapshotDigest,
    WorkSnapshotEvidence,
    WorkSnapshotRunHighlight,
    WorkSnapshotService,
    WorkSnapshotTaskHighlight,
    WorkSnapshotTotals,
)

__all__ = [
    # Project service
    "ProjectService",
    "ProjectSummary",
    "ActorService",
    "ActorGraphSnapshot",
    "QueueService",
    "QueueSummary",
    "ProjectDashboard",
    # Custom fields
    "CustomFieldService",
    "CustomFieldValueItem",
    "CustomFieldValuePage",
    "CommentService",
    "CommentItem",
    "CommentPage",
    "WatcherPage",
    "AutomationRuleService",
    "AutomationRunResult",
    # Goal service
    "GoalService",
    "GoalSummary",
    "HistoryBundleService",
    "LabelService",
    "LabelGateResult",
    "EvidenceGateService",
    "EvidenceGateResult",
    # Organization service
    "OrganizationService",
    "OrganizationSummary",
    "OrganizationDashboard",
    "OrganizationDashboardItem",
    # Team service
    "TeamService",
    # Portfolio service
    "PortfolioService",
    "PortfolioSummary",
    "PortfolioDashboard",
    "PortfolioDashboardItem",
    # Program service
    "ProgramService",
    "ProgramSummary",
    "ProgramDashboard",
    "ProgramDashboardItem",
    # Plan service
    "PlanService",
    "PlanTestJobService",
    "PlanTestJobRun",
    "ProofBundleService",
    # Lineage service
    "LineageService",
    # Saved searches / queues
    "SavedSearchService",
    "SavedSearchRun",
    # Task service
    "TaskService",
    "TaskTree",
    "DependencyGraph",
    "TaskBatch",
    # Task evidence service
    "TaskEvidenceService",
    "TaskEvidenceItem",
    "TaskEvidencePage",
    "TestRunSummary",
    "TestRunService",
    "TestServerRegistration",
    "TestServerService",
    "TestRunWorkflowService",
    "TestRunWorkflowTransition",
    "TestExecutionConfig",
    "TestExecutionService",
    "TestRunPruneSummary",
    "TestRunRetentionService",
    "TestRunRetentionPolicyService",
    "WorkSnapshotService",
    "WorkSnapshot",
    "WorkSnapshotDigest",
    "WorkSnapshotTotals",
    "WorkSnapshotEvidence",
    "WorkSnapshotTaskHighlight",
    "WorkSnapshotRunHighlight",
    # Checkout manager
    "CheckoutManager",
    # Remote service
    "RemoteService",
    "RemoteHostInfo",
    "SyncOperation",
    # Agent loop service
    "AgentLoopService",
]
