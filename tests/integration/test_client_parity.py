from __future__ import annotations

import json
from pathlib import Path

from scripts.client_parity_audit import audit_parity


def test_client_parity_allowlist() -> None:
    audit = audit_parity()
    allowlist_path = Path("scripts/client_parity_allowlist.json")
    allowlist = json.loads(allowlist_path.read_text())

    assert set(audit["missing_python"]) == set(allowlist.get("python", []))
    assert set(audit["missing_rust"]) == set(allowlist.get("rust", []))
    assert audit["extra_python"] == []
    assert audit["extra_rust"] == []
