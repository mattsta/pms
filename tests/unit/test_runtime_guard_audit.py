from scripts.audit_runtime_guards import _uses_runtime_guard_wrapper


def test_runtime_guard_audit_accepts_direct_bounded_wrapper() -> None:
    assert _uses_runtime_guard_wrapper('pms_run_bounded_script "$timeout" "$cwd"')


def test_runtime_guard_audit_accepts_contract_flow_wrapper() -> None:
    assert _uses_runtime_guard_wrapper('pms_run_contract_flow "$label" "$timeout"')


def test_runtime_guard_audit_rejects_missing_wrapper() -> None:
    assert not _uses_runtime_guard_wrapper("echo missing wrapper")
