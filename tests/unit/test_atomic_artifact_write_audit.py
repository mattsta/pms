"""Unit coverage for the artifact-write audit."""

from pathlib import Path

from scripts.audit_atomic_artifact_writes import audit_source


def test_audit_flags_raw_write_text_usage() -> None:
    issues = audit_source(
        """
from pms.utils.atomic_files import write_json_atomic
Path(\"out.json\").write_text(\"{}\")
write_json_atomic(Path(\"audit.json\"), {\"ok\": True})
""",
        path=Path("scripts/demo_writer.py"),
        required_helper="write_json_atomic",
    )

    assert len(issues) == 1
    assert issues[0].reason == "raw .write_text() artifact write"


def test_audit_flags_missing_helper_call() -> None:
    issues = audit_source(
        """
from pms.utils.atomic_files import write_json_atomic
payload = {\"ok\": True}
""",
        path=Path("scripts/demo_writer.py"),
        required_helper="write_json_atomic",
    )

    assert len(issues) == 1
    assert issues[0].reason == "missing required helper call write_json_atomic()"


def test_audit_accepts_helper_backed_writer() -> None:
    issues = audit_source(
        """
from pms.utils.atomic_files import write_json_atomic
write_json_atomic(Path(\"out.json\"), {\"ok\": True})
""",
        path=Path("scripts/demo_writer.py"),
        required_helper="write_json_atomic",
    )

    assert issues == ()


def test_audit_accepts_text_helper_backed_writer() -> None:
    issues = audit_source(
        """
from pms.utils.atomic_files import write_text_atomic
write_text_atomic(Path(\"out.md\"), \"hello\\n\")
""",
        path=Path("scripts/demo_writer.py"),
        required_helper="write_text_atomic",
    )

    assert issues == ()
