from __future__ import annotations

from pathlib import Path

from pms.runtime.defaults import LOCAL_SERVER_DEFAULT_BASE_URL
from scripts.audit_local_server_surface_truth import run_audit


def _write_fixture(
    root: Path,
    *,
    web_api_body: str,
    api_reference_body: str,
) -> None:
    for relative_path, body in (
        ("docs/WEB_API.md", web_api_body),
        ("docs/API_REFERENCE.md", api_reference_body),
        ("docs/DASHBOARD_USAGE.md", f"{LOCAL_SERVER_DEFAULT_BASE_URL}/dashboard\n"),
        (
            "docs/CLIENT_GUIDE.md",
            f'base_url="{LOCAL_SERVER_DEFAULT_BASE_URL}"\n',
        ),
        (
            "docs/WRITE_COORDINATION_ARCHITECTURE.md",
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}\n",
        ),
        (
            "examples/real_world/README.md",
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/api/v1/observability/overview\n",
        ),
        (
            "docs/END_TO_END_WORKFLOWS.md",
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/api/v1/tasks\n",
        ),
        (
            "client-rust/README.md",
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}\n",
        ),
        ("pms/config/settings.py", "LOCAL_SERVER_DEFAULT_BASE_URL\n"),
        ("pms/client/cli.py", "LOCAL_SERVER_DEFAULT_BASE_URL\n"),
        ("pms/client/http_client.py", "LOCAL_SERVER_DEFAULT_BASE_URL\n"),
        ("pms/api/app.py", 'print("📚 API docs: /docs")\n'),
    ):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def test_local_server_surface_truth_audit_accepts_consistent_surfaces(
    tmp_path: Path,
) -> None:
    _write_fixture(
        tmp_path,
        web_api_body=(
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/docs\n"
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/api/v1/health\n"
            "PMS_DATABASE_PATH=postgresql://user:pass@host/db\n"
            "PMS_SERVER_BASE_URL\n"
        ),
        api_reference_body=(
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}\n"
            "PMS_DATABASE_PATH=postgresql://user:pass@host/db\n"
            "PMS_SERVER_BASE_URL\n"
        ),
    )

    assert run_audit(root_dir=tmp_path) == ()


def test_local_server_surface_truth_audit_flags_stale_default_url(
    tmp_path: Path,
) -> None:
    _write_fixture(
        tmp_path,
        web_api_body=(
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/docs\n"
            "http://127.0.0.1:8000/docs\n"
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/api/v1/health\n"
            "PMS_DATABASE_PATH=postgresql://user:pass@host/db\n"
            "PMS_SERVER_BASE_URL\n"
        ),
        api_reference_body=(
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}\n"
            "PMS_DATABASE_PATH=postgresql://user:pass@host/db\n"
            "PMS_SERVER_BASE_URL\n"
        ),
    )

    issues = run_audit(root_dir=tmp_path)
    assert len(issues) == 1
    assert issues[0].file == "docs/WEB_API.md"
    assert "stale 127.0.0.1:8000 default URL remains" in issues[0].reason


def test_local_server_surface_truth_audit_flags_database_url_drift(
    tmp_path: Path,
) -> None:
    _write_fixture(
        tmp_path,
        web_api_body=(
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/docs\n"
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/api/v1/health\n"
            "PMS_DATABASE_PATH=postgresql://user:pass@host/db\n"
            "PMS_SERVER_BASE_URL\n"
            "DATABASE_URL=postgresql://user:pass@host/db\n"
        ),
        api_reference_body=(
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}\n"
            "PMS_DATABASE_PATH=postgresql://user:pass@host/db\n"
            "PMS_SERVER_BASE_URL\n"
        ),
    )

    issues = run_audit(root_dir=tmp_path)
    assert len(issues) == 1
    assert issues[0].file == "docs/WEB_API.md"
    assert "use PMS_DATABASE_PATH" in issues[0].reason
