"""Offline revision planning audit. Never connects to a database or stamps revisions."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
CREATE = "h6i7j8k9l1m3"
ALTER = "c1d2e3f4b5a6"


def audit() -> dict:
    config = Config()
    config.set_main_option("script_location", str(ROOT / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    assert len(heads) == 1, heads
    revisions = list(scripts.walk_revisions())
    assert scripts.get_revision(ALTER).down_revision == CREATE
    upgrade = scripts._upgrade_revs("heads", "base")
    order = [item.revision.revision for item in upgrade]
    assert order.index(CREATE) < order.index(ALTER)
    assert len(order) == len(set(order)) == len(revisions)
    plans = []
    for revision in revisions:
        pending = [
            item.revision.revision for item in scripts._upgrade_revs("heads", revision.revision)
        ]
        assert len(pending) == len(set(pending))
        assert revision.revision not in pending
        plans.append(
            {
                "from": revision.revision,
                "pending": pending,
                "create_pending": CREATE in pending,
                "alter_pending": ALTER in pending,
            }
        )
    # Explicit historical branch stamp is retained; planning cannot prove physical schema.
    return {
        "scope": "PASS_STATIC planning only; no SQL executed",
        "heads": heads,
        "bases": scripts.get_bases(),
        "revision_count": len(revisions),
        "base_upgrade_order": order,
        "mergepoints": [
            {"revision": r.revision, "down_revision": r.down_revision}
            for r in revisions
            if r.is_merge_point
        ],
        "branchpoints": [r.revision for r in revisions if r.is_branch_point],
        "all_revision_upgrade_plans": plans,
        "duplicate_base_steps": [r for r, count in Counter(order).items() if count > 1],
        "historical_warning": "Changing c1 parent changes ancestor interpretation. A stored c1 stamp alone does not prove mcp_builder tables physically exist. Obtain trusted pre-upgrade revision rows plus schema/data backup. Do not stamp, reset or replay CREATE/ALTER blindly.",
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
