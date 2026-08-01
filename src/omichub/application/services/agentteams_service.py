"""Authenticated user-facing adapter for the independently deployed AgentTeams Bridge."""

from __future__ import annotations

from typing import Any

import httpx

from omichub.application.services.agentteams_bridge_settings_service import (
    AgentTeamsBridgeRuntimeConfig,
)
from omichub.core.config import Settings
from omichub.core.exceptions import BusinessError


class AgentTeamsService:
    """Uses the Bridge's manager identity internally; browser clients never receive it."""

    def __init__(
        self,
        settings: Settings,
        bridge_config: AgentTeamsBridgeRuntimeConfig | None = None,
    ) -> None:
        self._settings = settings
        self._bridge_config = bridge_config or AgentTeamsBridgeRuntimeConfig.from_settings(settings)

    @property
    def available(self) -> bool:
        return bool(
            self._bridge_config.enabled
            and self._bridge_config.configured
        )

    async def is_connected(self) -> bool:
        """Return whether the configured Bridge is reachable right now."""
        if not self.available:
            return False
        try:
            health = await self._request("/healthz")
        except BusinessError:
            return False
        return health.get("status") == "ok"

    async def list_cases(
        self,
        requester_ref: str,
        *,
        case_status: str | None = None,
        project_id: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        params = {"requester_ref": requester_ref, "limit": limit}
        if case_status:
            params["status"] = case_status
        if project_id:
            params["project_id"] = project_id
        if cursor:
            params["cursor"] = cursor
        response = await self._request("/v1/cases", params=params)
        response["items"] = [self._public_case(case) for case in response.get("items", [])]
        return response

    async def create_case(
        self,
        *,
        case_id: str,
        project_id: str,
        intent: str,
        requester_ref: str,
        flow_id: str,
        sample_sheet: list[dict[str, Any]],
        comparisons: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        case = await self._request(
            "/v1/cases",
            method="POST",
            json={
                "case_id": case_id,
                "project_ref": {"kind": "project", "id": project_id},
                "intent": intent,
                "requester_ref": requester_ref,
            },
        )
        await self._request(
            f"/v1/cases/{case_id}/work-items",
            method="POST",
            json={
                "work_item_id": "preflight-01",
                "target": "data-steward",
                "objective": "核验项目输入、样本表和分组对比，决定是否进入人工审批。",
                "skill_name": "project-preflight",
                "context_refs": [{"kind": "project", "id": project_id}],
                "read_only": True,
            },
        )
        await self._request_as(
            "data-steward",
            self._bridge_config.data_steward_token,
            f"/v1/projects/{project_id}/preflight",
            method="POST",
            json={
                "case_id": case_id,
                "work_item_id": "preflight-01",
                "flow_id": flow_id,
                "sample_sheet": sample_sheet,
                "comparisons": comparisons,
                "context_refs": [{"kind": "project", "id": project_id}],
            },
        )
        return case

    async def approve_and_submit_task(
        self,
        *,
        case_id: str,
        requester_ref: str,
        task_name: str,
    ) -> dict[str, Any]:
        case = await self._get_case_for_requester(case_id, requester_ref)
        if case.get("status") != "approval_pending":
            raise BusinessError("当前协作 Case 尚未满足人工审批和提交条件")
        snapshot = case.get("preflight_input")
        if not isinstance(snapshot, dict):
            raise BusinessError("当前协作 Case 缺少已通过预检的输入快照")
        flow_id = snapshot.get("flow_id")
        sample_sheet = snapshot.get("sample_sheet")
        comparisons = snapshot.get("comparisons")
        if not isinstance(flow_id, str) or not isinstance(sample_sheet, list):
            raise BusinessError("当前协作 Case 的预检输入快照无效")
        approval = await self._request_as(
            "approval-authority",
            self._bridge_config.approval_token,
            "/v1/approvals",
            method="POST",
            json={"case_id": case_id, "action": "submit_task", "flow_id": flow_id},
        )
        if not any(item.get("work_item_id") == "submit-01" for item in case.get("work_items", [])):
            await self._request(
                f"/v1/cases/{case_id}/work-items",
                method="POST",
                json={
                    "work_item_id": "submit-01",
                    "target": "workflow-operator",
                    "objective": "执行已获人工批准的 RNA-seq 流程提交并回写 OmicHub 任务证据。",
                    "skill_name": "workflow-submit",
                    "context_refs": [{"kind": "project", "id": case["project_ref"]["id"]}],
                    "read_only": False,
                    "approval_required": True,
                },
            )
        return await self._request_as(
            "workflow-operator",
            self._bridge_config.workflow_operator_token,
            "/v1/tasks",
            method="POST",
            json={
                "case_id": case_id,
                "work_item_id": "submit-01",
                "idempotency_key": f"{case_id}-submit-v1",
                "approval_token": approval["token"],
                "task": {
                    "flow_id": flow_id,
                    "name": task_name,
                    "sample_sheet": sample_sheet,
                    "comparisons": comparisons,
                    "execution_mode": "local",
                },
            },
        )

    async def get_case(self, case_id: str, requester_ref: str) -> dict[str, Any]:
        return self._public_case(await self._get_case_for_requester(case_id, requester_ref))

    async def refresh_case(self, case_id: str, requester_ref: str) -> dict[str, Any]:
        await self._get_case_for_requester(case_id, requester_ref)
        return self._public_case(
            await self._request(f"/v1/cases/{case_id}/reconcile", method="POST")
        )

    async def _get_case_for_requester(self, case_id: str, requester_ref: str) -> dict[str, Any]:
        case = await self._request(f"/v1/cases/{case_id}")
        if case.get("requester_ref") != requester_ref:
            raise BusinessError("无权查看该协作案例")
        return case

    @staticmethod
    def _public_case(case: dict[str, Any]) -> dict[str, Any]:
        public_case = dict(case)
        public_case.pop("preflight_input", None)
        public_case.pop("task_specs", None)
        return public_case

    async def get_case_events(
        self,
        case_id: str,
        requester_ref: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        await self._get_case_for_requester(case_id, requester_ref)
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return await self._request(f"/v1/cases/{case_id}/events", params=params)

    async def _request(self, path: str, *, method: str = "GET", **kwargs: Any) -> dict[str, Any]:
        return await self._request_as(
            "bioops-manager",
            self._bridge_config.manager_token,
            path,
            method=method,
            **kwargs,
        )

    async def _request_as(
        self, identity: str, token: str, path: str, *, method: str = "GET", **kwargs: Any
    ) -> dict[str, Any]:
        if not self.available:
            raise BusinessError("Agent 协作中心尚未接通")
        headers = {
            "X-Bridge-Identity": identity,
            "X-Bridge-Token": token,
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._bridge_config.bridge_url.rstrip("/"),
                timeout=self._bridge_config.timeout_seconds,
            ) as client:
                response = await client.request(method, path, headers=headers, **kwargs)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise BusinessError("协作案例不存在") from exc
            raise BusinessError("Agent 协作中心暂时不可用") from exc
        except httpx.HTTPError as exc:
            raise BusinessError("Agent 协作中心暂时不可用") from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise BusinessError("Agent 协作中心返回了无效数据")
        return payload
