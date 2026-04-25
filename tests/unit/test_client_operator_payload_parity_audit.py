from __future__ import annotations

from pathlib import Path

from scripts.audit_client_operator_payload_parity import (
    _normalize_payload,
    _parse_env_file,
)


def test_normalize_payload_strips_generated_at_recursively() -> None:
    payload = {
        "generated_at": "2026-04-24T19:00:00Z",
        "scope": {"kind": "instance_dashboard"},
        "items": [
            {
                "id": "project-1",
                "generated_at": "2026-04-24T19:00:01Z",
                "links": {"self": "uv run pms project show project-1"},
            }
        ],
    }

    normalized = _normalize_payload(payload)

    assert normalized == {
        "scope": {"kind": "instance_dashboard"},
        "items": [
            {
                "id": "project-1",
                "links": {"self": "uv run pms project show project-1"},
            }
        ],
    }


def test_parse_env_file_reads_simple_key_value_lines(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# comment\n"
        "PMS_SERVER_BASE_URL=http://127.0.0.1:27541\n"
        "PMS_API_KEY_PATH='/tmp/admin.key'\n"
    )

    parsed = _parse_env_file(env_path)

    assert parsed == {
        "PMS_SERVER_BASE_URL": "http://127.0.0.1:27541",
        "PMS_API_KEY_PATH": "/tmp/admin.key",
    }
