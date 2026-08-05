import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import preflight


def test_gateway_env_requires_matrix_credentials_and_required_identities() -> None:
    errors = preflight.validate_gateway_env({})

    assert "GATEWAY_MATRIX_SERVICE_TOKEN is missing or still a template placeholder" in errors
    assert "GATEWAY_IDENTITIES is missing bioops-manager" in errors
    assert "GATEWAY_MATRIX_IDENTITIES is missing omichub-user" in errors


def test_gateway_env_accepts_complete_isolated_gateway_configuration() -> None:
    errors = preflight.validate_gateway_env({
        "GATEWAY_IDENTITIES": "bioops-manager:manager-secret",
        "GATEWAY_MATRIX_HOMESERVER_URL": "https://matrix.example.internal",
        "GATEWAY_MATRIX_SERVICE_TOKEN": "matrix-service-secret",
        "GATEWAY_MATRIX_IDENTITIES": "bioops-manager=@manager:example.internal,omichub-user=@user:example.internal",
        "GATEWAY_ELEMENT_BASE_URL": "https://element.example.internal",
    })

    assert errors == []
