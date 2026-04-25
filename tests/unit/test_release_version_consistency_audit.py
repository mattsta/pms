from __future__ import annotations

from pathlib import Path

from scripts.audit_release_version_consistency import run_audit


def _write_release_fixture(
    root: Path,
    *,
    cargo_version: str,
    changelog_label: str | None,
) -> None:
    (root / "client-rust").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "pms").mkdir(parents=True, exist_ok=True)

    (root / "pyproject.toml").write_text(
        '[project]\nname = "pms"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "client-rust" / "Cargo.toml").write_text(
        f'[package]\nname = "pms-client"\nversion = "{cargo_version}"\n',
        encoding="utf-8",
    )
    (root / "pms" / "__init__.py").write_text(
        '__version__ = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "docs" / "CAPABILITIES_REFERENCE.md").write_text(
        "**Version:** 0.1.0\n",
        encoding="utf-8",
    )
    (root / "docs" / "SERVER_DEPLOYMENT.md").write_text(
        "**Version**: 0.1.0\n",
        encoding="utf-8",
    )
    if changelog_label is not None:
        (root / "CHANGELOG.md").write_text(
            f"# Changelog\n\n## [0.1.0] - {changelog_label}\n",
            encoding="utf-8",
        )


def test_release_version_consistency_audit_accepts_aligned_surfaces(
    tmp_path: Path,
) -> None:
    _write_release_fixture(
        tmp_path,
        cargo_version="0.1.0",
        changelog_label="Pending public release cut",
    )

    assert run_audit(root_dir=tmp_path) == ()


def test_release_version_consistency_audit_flags_mismatched_rust_version(
    tmp_path: Path,
) -> None:
    _write_release_fixture(
        tmp_path,
        cargo_version="2.0.0",
        changelog_label="Pending public release cut",
    )

    issues = run_audit(root_dir=tmp_path)
    assert len(issues) == 1
    assert issues[0].file == "client-rust/Cargo.toml"
    assert "does not match project version" in issues[0].reason


def test_release_version_consistency_audit_flags_placeholder_changelog_label(
    tmp_path: Path,
) -> None:
    _write_release_fixture(
        tmp_path,
        cargo_version="0.1.0",
        changelog_label="2025-01-XX",
    )

    issues = run_audit(root_dir=tmp_path)
    assert len(issues) == 1
    assert issues[0].file == "CHANGELOG.md"
    assert "changelog release label" in issues[0].reason


def test_release_version_consistency_audit_accepts_missing_changelog(
    tmp_path: Path,
) -> None:
    _write_release_fixture(
        tmp_path,
        cargo_version="0.1.0",
        changelog_label=None,
    )

    assert run_audit(root_dir=tmp_path) == ()
