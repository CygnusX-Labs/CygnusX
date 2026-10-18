"""Hash actual collected artifacts; never infer acceptance from exit-zero alone."""

import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2] / "evidence/runtime-acceptance"
artifacts = []
for path in sorted(root.rglob("*")):
    if path.is_file() and path.name != "artifact-index.json":
        artifacts.append(
            {
                "path": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
(root / "artifact-index.json").write_text(
    json.dumps(
        {
            "artifacts": artifacts,
            "note": "Hashes identify evidence only; see results.json for acceptance status.",
        },
        indent=2,
    )
    + "\n"
)
print(f"Indexed {len(artifacts)} evidence files; no acceptance status promoted")
