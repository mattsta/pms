"""Repository layer for data access."""

from pms.repositories.actor_alias_repository import ActorAliasRepository
from pms.repositories.actor_membership_repository import ActorMembershipRepository
from pms.repositories.actor_repository import ActorRepository
from pms.repositories.automation_rule_repository import AutomationRuleRepository
from pms.repositories.automation_rule_run_repository import AutomationRuleRunRepository
from pms.repositories.base import EventSourcedRepository, RepositoryContext
from pms.repositories.comment_mention_repository import CommentMentionRepository
from pms.repositories.comment_repository import CommentRepository
from pms.repositories.custom_field_repository import CustomFieldRepository
from pms.repositories.custom_field_value_repository import CustomFieldValueRepository
from pms.repositories.entity_watcher_repository import EntityWatcherRepository
from pms.repositories.evidence_gate_rule_repository import EvidenceGateRuleRepository
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.key_result_repository import KeyResultRepository
from pms.repositories.label_assignment_repository import LabelAssignmentRepository
from pms.repositories.label_category_repository import LabelCategoryRepository
from pms.repositories.label_gate_rule_repository import LabelGateRuleRepository
from pms.repositories.label_repository import LabelRepository
from pms.repositories.milestone_repository import MilestoneRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.organization_repository import OrganizationRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.portfolio_repository import PortfolioRepository
from pms.repositories.product_repository import ProductRepository
from pms.repositories.program_repository import ProgramRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.saved_search_repository import SavedSearchRepository
from pms.repositories.session_repository import SessionRepository
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.repositories.task_evidence_repository import TaskEvidenceRepository
from pms.repositories.task_repository import TaskRepository
from pms.repositories.team_repository import TeamRepository
from pms.repositories.test_run_repository import TestRunRepository
from pms.repositories.test_run_retention_policy_repository import (
    TestRunRetentionPolicyRepository,
)
from pms.repositories.work_snapshot_review_repository import (
    WorkSnapshotReviewRepository,
)

__all__ = [
    "EventSourcedRepository",
    "RepositoryContext",
    "ActorRepository",
    "ActorAliasRepository",
    "ActorMembershipRepository",
    "AutomationRuleRepository",
    "AutomationRuleRunRepository",
    "CustomFieldRepository",
    "CustomFieldValueRepository",
    "CommentRepository",
    "CommentMentionRepository",
    "EntityWatcherRepository",
    "GoalRepository",
    "LabelAssignmentRepository",
    "LabelCategoryRepository",
    "LabelGateRuleRepository",
    "EvidenceGateRuleRepository",
    "LabelRepository",
    "ObjectiveRepository",
    "KeyResultRepository",
    "PlanRepository",
    "MilestoneRepository",
    "OrganizationRepository",
    "TeamRepository",
    "PortfolioRepository",
    "ProgramRepository",
    "ProductRepository",
    "ProjectRepository",
    "SavedSearchRepository",
    "SessionRepository",
    "StateTransitionRepository",
    "TaskRepository",
    "TaskEvidenceRepository",
    "TestRunRepository",
    "TestRunRetentionPolicyRepository",
    "WorkSnapshotReviewRepository",
]
