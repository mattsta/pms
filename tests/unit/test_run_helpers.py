from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_pms_copy_file_atomic_replaces_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text('{"status":"new"}\n', encoding="utf-8")
    target.write_text('{"status":"old"}\n', encoding="utf-8")

    subprocess.run(
        [
            "bash",
            "-lc",
            f'source "{ROOT / "scripts/lib/run_helpers.sh"}"; '
            f'pms_copy_file_atomic "{source}" "{target}"',
        ],
        cwd=ROOT,
        check=True,
    )

    assert target.read_text(encoding="utf-8") == '{"status":"new"}\n'
    assert list(tmp_path.glob("*.tmp")) == []


def test_pms_copy_file_atomic_cleans_temp_file_on_copy_failure(tmp_path: Path) -> None:
    missing_source = tmp_path / "missing.json"
    target = tmp_path / "target.json"

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(
            [
                "bash",
                "-lc",
                f'source "{ROOT / "scripts/lib/run_helpers.sh"}"; '
                f'pms_copy_file_atomic "{missing_source}" "{target}"',
            ],
            cwd=ROOT,
            check=True,
        )

    assert not target.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_pms_publish_symlink_atomic_points_latest_at_bundle(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "20260422-000000"
    bundle_dir.mkdir()
    (bundle_dir / "benchmark-bundle.summary.json").write_text(
        '{"status":"ok"}\n', encoding="utf-8"
    )
    latest = tmp_path / "latest"

    subprocess.run(
        [
            "bash",
            "-lc",
            f'source "{ROOT / "scripts/lib/run_helpers.sh"}"; '
            f'pms_publish_symlink_atomic "{bundle_dir}" "{latest}"',
        ],
        cwd=ROOT,
        check=True,
    )

    assert latest.is_symlink()
    assert latest.resolve() == bundle_dir.resolve()
    assert (latest / "benchmark-bundle.summary.json").read_text(encoding="utf-8") == (
        '{"status":"ok"}\n'
    )


def test_pms_publish_symlink_atomic_migrates_legacy_directory(tmp_path: Path) -> None:
    legacy_latest = tmp_path / "latest"
    legacy_latest.mkdir()
    (legacy_latest / "stale.txt").write_text("stale\n", encoding="utf-8")

    bundle_dir = tmp_path / "20260422-010000"
    bundle_dir.mkdir()
    (bundle_dir / "benchmark-bundle.summary.json").write_text(
        '{"status":"fresh"}\n', encoding="utf-8"
    )

    subprocess.run(
        [
            "bash",
            "-lc",
            f'source "{ROOT / "scripts/lib/run_helpers.sh"}"; '
            f'pms_publish_symlink_atomic "{bundle_dir}" "{legacy_latest}"',
        ],
        cwd=ROOT,
        check=True,
    )

    assert legacy_latest.is_symlink()
    assert legacy_latest.resolve() == bundle_dir.resolve()
    assert not any(tmp_path.glob(".latest.legacy.*"))
