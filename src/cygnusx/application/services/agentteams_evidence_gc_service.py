"""Lifecycle cleanup for closed AgentTeams case evidence."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cygnusx.application.services.agentteams_service import AgentTeamsService
from cygnusx.core.config import Settings, get_settings
from cygnusx.infrastructure.config.storage_config import get_storage_config
from cygnusx.infrastructure.storage.minio_store import MinioStore


class AgentTeamsEvidenceGcService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        case_service: AgentTeamsService | None = None,
        minio_store: MinioStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.case_service = case_service or AgentTeamsService(self.settings)
        self.minio_store = minio_store or MinioStore(self.settings)
        # 启动自检：数据根不可写/不存在即显式失败，绝不静默跳过清理
        # （历史教训：硬编码旧根导致 GC 从未真正生效）。
        self._data_root = Path(get_storage_config().data_root)
        if not self._data_root.is_dir():
            raise RuntimeError(
                f"AgentTeams 证据 GC 数据根不存在: {self._data_root}，拒绝执行清理"
            )

    async def cleanup(self, *, now: datetime | None = None) -> dict[str, Any]:
        cutoff = (now or datetime.now(UTC)) - timedelta(
            days=self.settings.agentteams_evidence_retention_days
        )
        snapshot = await self.case_service.admin_resource_snapshot()
        removed: list[str] = []
        for case in snapshot.get("cases") or []:
            if case.get("status") != "closed":
                continue
            updated_at = datetime.fromisoformat(str(case.get("updated_at")).replace("Z", "+00:00"))
            if updated_at > cutoff:
                continue
            case_id = str(case["case_id"])
            self.minio_store.delete_case_prefix(case_id, preserve_delivery=True)
            self._clean_local_workdir(case_id)
            removed.append(case_id)
        return {"status": "ok", "removed_cases": removed, "count": len(removed)}

    def _clean_local_workdir(self, case_id: str) -> None:
        # 数据根由存储配置链解析（YAML storage.data_root → STORAGE_PATH），
        # 与 agentteams_data_tool_service 的产物落盘路径保持同一根。
        root = self._data_root / "output" / "agentteams" / case_id
        if not root.is_dir():
            return
        for child in root.iterdir():
            if child.name == "delivery":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)


__all__ = ["AgentTeamsEvidenceGcService"]
