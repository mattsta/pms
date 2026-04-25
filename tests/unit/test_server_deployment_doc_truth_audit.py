from __future__ import annotations

from pathlib import Path

from scripts.audit_server_deployment_doc_truth import run_audit


def _write_fixture(root: Path, doc_body: str) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "pms" / "cli").mkdir(parents=True, exist_ok=True)

    (root / "pyproject.toml").write_text(
        '[project]\nname = "pms"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "pms" / "cli" / "app.py").write_text(
        "LOCAL_RUNTIME_DEFAULT_PORT = 27541\n",
        encoding="utf-8",
    )
    (root / "docs" / "SERVER_DEPLOYMENT.md").write_text(doc_body, encoding="utf-8")


def test_server_deployment_doc_truth_audit_accepts_grounded_doc(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        """# Guide

**Version**: 0.1.0

http://127.0.0.1:27541/docs
http://127.0.0.1:27541/openapi.json
http://127.0.0.1:27541/dashboard
http://127.0.0.1:27541/api/v1/health
PMS_DATA_DIR
PMS_DATABASE_PATH
PMS_WRITE_MODE
PMS_SERVER_BASE_URL
uv run pms auth init --show-key
X-API-Key
docs/API_ENDPOINT_CATALOG.md
docs/WRITE_COORDINATION_ARCHITECTURE.md
PMS_DATABASE_PATH=postgresql://user:pass@host/db
""",
    )

    assert run_audit(root_dir=tmp_path) == ()


def test_server_deployment_doc_truth_audit_flags_hardcoded_endpoint_counts(
    tmp_path: Path,
) -> None:
    _write_fixture(
        tmp_path,
        """# Guide

**Version**: 0.1.0

http://127.0.0.1:27541/docs
http://127.0.0.1:27541/openapi.json
http://127.0.0.1:27541/dashboard
http://127.0.0.1:27541/api/v1/health
PMS_DATA_DIR
PMS_DATABASE_PATH
PMS_WRITE_MODE
PMS_SERVER_BASE_URL
uv run pms auth init --show-key
X-API-Key
docs/API_ENDPOINT_CATALOG.md
docs/WRITE_COORDINATION_ARCHITECTURE.md
PMS_DATABASE_PATH=postgresql://user:pass@host/db
24 API Endpoints
""",
    )

    issues = run_audit(root_dir=tmp_path)
    assert len(issues) == 1
    assert issues[0].file == "docs/SERVER_DEPLOYMENT.md"
    assert "must not hardcode endpoint counts" in issues[0].reason


def test_server_deployment_doc_truth_audit_flags_database_url_drift(
    tmp_path: Path,
) -> None:
    _write_fixture(
        tmp_path,
        """# Guide

**Version**: 0.1.0

http://127.0.0.1:27541/docs
http://127.0.0.1:27541/openapi.json
http://127.0.0.1:27541/dashboard
http://127.0.0.1:27541/api/v1/health
PMS_DATA_DIR
PMS_DATABASE_PATH
PMS_WRITE_MODE
PMS_SERVER_BASE_URL
uv run pms auth init --show-key
X-API-Key
docs/API_ENDPOINT_CATALOG.md
docs/WRITE_COORDINATION_ARCHITECTURE.md
PMS_DATABASE_PATH=postgresql://user:pass@host/db
DATABASE_URL=postgresql://user:pass@host/db
""",
    )

    issues = run_audit(root_dir=tmp_path)
    assert len(issues) == 1
    assert issues[0].file == "docs/SERVER_DEPLOYMENT.md"
    assert "PMS_DATABASE_PATH rather than DATABASE_URL" in issues[0].reason
