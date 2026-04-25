"""Unit coverage for the service transaction boundary audit."""

from pathlib import Path

from scripts.audit_service_transaction_boundaries import audit_service_source


def test_audit_flags_multi_write_method_without_outer_transaction() -> None:
    issues = audit_service_source(
        """
class DemoService:
    async def _run_rule_for_event(self):
        await self._execute_action_in_transaction()
        await self._run_repo.record({})
""",
        path=Path("demo_service.py"),
    )

    assert len(issues) == 1
    assert issues[0].method == "_run_rule_for_event"
    assert issues[0].mutation_calls == (
        "self._execute_action_in_transaction",
        "self._run_repo.record",
    )


def test_audit_accepts_multi_write_method_with_outer_transaction() -> None:
    issues = audit_service_source(
        """
class DemoService:
    async def _run_rule_for_event(self):
        async with self.db.transaction():
            await self._execute_action_in_transaction()
            await self._run_repo.record({})
""",
        path=Path("demo_service.py"),
    )

    assert issues == ()


def test_audit_ignores_single_write_method_without_outer_transaction() -> None:
    issues = audit_service_source(
        """
class DemoService:
    async def create_item(self):
        await self._repo.create({})
""",
        path=Path("demo_service.py"),
    )

    assert issues == ()


def test_audit_ignores_multi_repo_read_method_without_outer_transaction() -> None:
    issues = audit_service_source(
        """
class DemoService:
    async def run_lookup(self):
        await self._repo.get_by_id("123")
        await self._other_repo.list_all()
""",
        path=Path("demo_service.py"),
    )

    assert issues == ()
