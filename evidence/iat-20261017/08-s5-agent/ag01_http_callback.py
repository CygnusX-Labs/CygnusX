"""AG-01: REAL HTTP fixed callback against the isolated acceptance FastAPI.

Issues a real delegation via the original agent_tool_delegation code, then POSTs to the
real /api/v1/agent-tools/delegated/invoke route over TCP with the Bearer token. Verifies
server-side processing (real HTTP request/response), delegation verification (Redis NX),
and the Gateway audit row persisted in real PG.

Run: .venv/bin/python <this> <PG_URL> <REDIS_URL> <API_BASE>
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.error
import urllib.request
from uuid import UUID, uuid4

sys.path.insert(0, "evidence/iat-20261017/08-s5-agent")
import p3_s5_harness as H  # noqa: E402

from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

PG_URL, REDIS_URL, API_BASE = sys.argv[1], sys.argv[2], sys.argv[3]


async def main():
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.application.services.agent_tool_delegation import issue_delegation
    from cygnusx.infrastructure.database.models.agent_tool_invocation import (
        AgentToolInvocationModel,
    )

    H.enable_gateway()
    engine = create_async_engine(PG_URL)
    env = await H.seed(engine)
    db = env.maker()
    gw = AgentToolGateway(db)
    ctx = await gw.context(str(env.owner), env.s_a1)
    token = await issue_delegation(ctx)
    call_id = str(uuid4())
    await db.close()

    body = json.dumps({
        "capability_id": "downloads.describe_capabilities",
        "call_id": call_id,
        "arguments": {},
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/agent-tools/delegated/invoke",
        data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    status, payload = None, None
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = exc.read().decode()[:400]

    # replay via HTTP must be refused
    req2 = urllib.request.Request(
        f"{API_BASE}/api/v1/agent-tools/delegated/invoke",
        data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    replay_status = None
    try:
        with urllib.request.urlopen(req2, timeout=30) as resp:
            replay_status = resp.status
    except urllib.error.HTTPError as exc:
        replay_status = exc.code

    # audit row in real PG (verify via the invocation returned by the first call)
    audit_owner = None
    inv_id = (payload or {}).get("invocation_id") if isinstance(payload, dict) else None
    if inv_id:
        db2 = env.maker()
        row = await db2.get(AgentToolInvocationModel, UUID(inv_id))
        audit_owner = row.owner_id if row else None
        await db2.close()

    ok = (status == 200 and replay_status in (401, 403, 409, 422)
          and audit_owner == str(env.owner))
    H.rec("AG-01", ok, http_status=status, replay_status=replay_status,
          invocation_id=inv_id, audit_owner=audit_owner,
          note="real HTTP callback + real delegation + Redis NX replay refusal")
    await engine.dispose()


asyncio.run(main())
