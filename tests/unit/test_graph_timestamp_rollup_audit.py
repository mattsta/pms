"""Unit coverage for the graph timestamp rollup audit."""

from pathlib import Path

from scripts.audit_graph_timestamp_rollups import audit_source

REQUIRED = (
    "self._plan_service.get_last_activity_map(",
    "self._plan_service.get_last_transition_map(",
)
FORBIDDEN = ('get_last_transition_map("plan_status",',)


def test_audit_flags_missing_required_rollup_call() -> None:
    issues = audit_source(
        """
class Demo:
    async def get_plan_lineage_dashboard(self):
        return await self._plan_service.get_last_activity_map([])
""",
        path=Path("pms/services/lineage_service.py"),
        required_patterns=REQUIRED,
        forbidden_patterns=FORBIDDEN,
    )

    assert len(issues) == 1
    assert "missing required rollup contract snippet" in issues[0].reason


def test_audit_flags_forbidden_shallow_transition_usage() -> None:
    issues = audit_source(
        """
class Demo:
    async def get_plan_lineage_dashboard(self):
        return await transition_repo.get_last_transition_map("plan_status", [])
""",
        path=Path("pms/services/lineage_service.py"),
        required_patterns=REQUIRED,
        forbidden_patterns=FORBIDDEN,
    )

    assert len(issues) == 3
    assert any(
        "forbidden shallow rollup snippet present" in issue.reason for issue in issues
    )


def test_audit_accepts_deep_rollup_backed_surface() -> None:
    issues = audit_source(
        """
class Demo:
    async def get_plan_lineage_dashboard(self):
        await self._plan_service.get_last_activity_map([])
        return await self._plan_service.get_last_transition_map([])
""",
        path=Path("pms/services/lineage_service.py"),
        required_patterns=REQUIRED,
        forbidden_patterns=FORBIDDEN,
    )

    assert issues == ()
