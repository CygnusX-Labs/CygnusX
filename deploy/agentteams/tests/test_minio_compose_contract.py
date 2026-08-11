from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[3]
AGENTTEAMS_COMPOSE = ROOT / "deploy/agentteams/docker-compose.agentteams.yml"
MAIN_COMPOSE = ROOT / "deploy/docker/docker-compose.yml"


def test_main_compose_exposes_private_agentteams_bucket() -> None:
    payload = yaml.safe_load(MAIN_COMPOSE.read_text(encoding="utf-8"))
    services = payload["services"]

    assert set(services["minio"]["networks"]) == {"data_net", "omichub_net"}
    assert services["minio"]["ports"] == [
        "${OMICHUB_MINIO_BIND_HOST:-127.0.0.1}:${OMICHUB_MINIO_PORT:-9000}:9000",
        "${OMICHUB_MINIO_BIND_HOST:-127.0.0.1}:${OMICHUB_MINIO_CONSOLE_PORT:-9001}:9001",
    ]
    init_command = " ".join(services["minio-init"]["command"])
    assert "mc mb --ignore-existing" in init_command
    assert "mc anonymous set none" in init_command


def test_bridge_joins_minio_network_with_server_side_credentials() -> None:
    payload = yaml.safe_load(AGENTTEAMS_COMPOSE.read_text(encoding="utf-8"))
    bridge = payload["services"]["omichub-agentteams-bridge"]

    assert "omichub_net" in bridge["networks"]
    assert bridge["environment"] == {
        "AGENTTEAMS_MINIO_ENDPOINT": "http://minio:9000",
        "AGENTTEAMS_MINIO_BUCKET": "${MINIO_AGENTTEAMS_BUCKET:-agentteams-evidence}",
        "AGENTTEAMS_MINIO_ACCESS_KEY": "${MINIO_ROOT_USER:?missing MINIO_ROOT_USER}",
        "AGENTTEAMS_MINIO_SECRET_KEY": "${MINIO_ROOT_PASSWORD:?missing MINIO_ROOT_PASSWORD}",
    }
    assert payload["networks"]["omichub_net"] == {
        "name": "omichub_net",
        "external": True,
    }
