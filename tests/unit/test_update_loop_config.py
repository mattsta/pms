from __future__ import annotations

import sys
from pathlib import Path

import yaml

from scripts import update_loop_config


def test_update_loop_config_updates_yaml_file(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "loop.yaml"
    config_path.write_text("enabled: false\nmax_turns: 2\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_loop_config.py",
            "--file",
            str(config_path),
            "--set",
            "enabled=true",
            "--set",
            "max_turns=5",
        ],
    )

    assert update_loop_config.main() == 0
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == {
        "enabled": True,
        "max_turns": 5,
    }
