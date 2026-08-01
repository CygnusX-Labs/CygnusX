"""REST application for the read-only scientific-interpretation Skill."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request

from .audit import AuditStore
from .client import OmicHubConsultationClient
from .config import GatewaySettings
from .models import ConsultationRequest, ScientificInterpretationResponse
from .security import require_manager
from .service import GatewayService


async def get_service(request: Request) -> GatewayService:
    return request.app.state.gateway_service


async def authenticate_manager(
    request: Request,
    x_gateway_identity: str | None = Header(default=None),
    x_gateway_token: str | None = Header(default=None),
) -> str:
    return require_manager(request.app.state.gateway_settings, x_gateway_identity, x_gateway_token)


def create_app(
    settings: GatewaySettings | None = None,
    client: OmicHubConsultationClient | None = None,
) -> FastAPI:
    runtime_settings = settings or GatewaySettings()
    runtime_client = client or OmicHubConsultationClient(runtime_settings)
    service = GatewayService(
        runtime_settings, runtime_client, AuditStore(runtime_settings.audit_log_path)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await runtime_client.close()

    app = FastAPI(
        title="OmicHub Controlled Agent Gateway",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.gateway_settings = runtime_settings
    app.state.gateway_service = service

    @app.get("/healthz", tags=["Health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/v1/scientific-interpretation",
        response_model=ScientificInterpretationResponse,
        tags=["Skills"],
    )
    async def scientific_interpretation(
        payload: ConsultationRequest,
        actor: Annotated[str, Depends(authenticate_manager)],
        gateway_service: Annotated[GatewayService, Depends(get_service)],
    ) -> ScientificInterpretationResponse:
        return await gateway_service.consult(payload, actor)

    return app


app = create_app()
