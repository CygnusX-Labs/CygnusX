"""Write an offline download provenance manifest; never starts downloads or containers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cygnusx.core.config import get_settings
from cygnusx.infrastructure.download.provenance import WorkerObservation, build_source_manifest
from cygnusx.infrastructure.storage import get_path_factory
from cygnusx.tools.download.config import get_download_config
from pydantic import ValidationError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker-observation", type=Path)
    args = parser.parse_args()
    try:
        if args.worker_observation and args.worker_observation.stat().st_size > 1024 * 1024:
            raise ValueError("observation too large")
        observation = (
            WorkerObservation.model_validate_json(args.worker_observation.read_text())
            if args.worker_observation
            else None
        )
        manifest = build_source_manifest(
            Path(__file__).resolve().parents[1],
            get_download_config(),
            get_settings(),
            get_path_factory().data_root,
            observation,
        )
    except (ValueError, OSError, ValidationError):
        parser.exit(2, "DOWNLOAD_MANIFEST_INVALID: 请检查受信运行证据与路径配置\n")
    # Refuse overwrite of prior provenance evidence.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
