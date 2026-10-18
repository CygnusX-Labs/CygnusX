"""llm_payload 独立限额与目录分页测试（架构审查 §5 防膨胀）。"""

from __future__ import annotations

import json

from cygnusx.application.services.flow_service import FlowService
from cygnusx.application.services.tool_bridge_service import ToolBridgeService

# ============ llm_payload 预算 ============


def _make_bridge() -> ToolBridgeService:
    from tests.unit.tools.test_tool_bridge import _FakeLoader

    return ToolBridgeService(_FakeLoader([]))


def test_fit_llm_payload_under_budget_passes_through() -> None:
    bridge = _make_bridge()
    payload = {"valid": True, "confirmation_id": "c-1", "summary": "ok"}
    assert bridge._fit_llm_payload(payload) == payload


def test_fit_llm_payload_drops_parameter_preview_first() -> None:
    bridge = _make_bridge()
    payload = {
        "valid": True,
        "confirmation_id": "c-1",
        "parameter_preview": {"p" + str(i): "v" * 200 for i in range(50)},
        "resource_hint": {"cores": 8, "memory": "32G", "time": "4h"},
        "summary": "x" * 100,
    }
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > ToolBridgeService._MAX_LLM_PAYLOAD_BYTES
    fitted = bridge._fit_llm_payload(payload)
    assert "parameter_preview" not in fitted
    assert "parameter_preview_note" in fitted
    assert fitted["resource_hint"] == payload["resource_hint"]
    assert (
        len(json.dumps(fitted, ensure_ascii=False, default=str).encode("utf-8"))
        <= ToolBridgeService._MAX_LLM_PAYLOAD_BYTES + 200  # note 本身计入，允许少量余量
    )


def test_fit_llm_payload_falls_back_to_minimal() -> None:
    bridge = _make_bridge()
    payload = {
        "valid": True,
        "confirmation_id": "c-1",
        "flow_name": "f" * 5000,
        "parameter_preview": {"p": "v" * 100},
        "resource_hint": {"cores": 8},
        "summary": "s" * 5000,
    }
    fitted = bridge._fit_llm_payload(payload)
    assert set(fitted) <= {"valid", "confirmation_id", "summary"}


def test_package_analysis_flow_result_clamps_oversized_errors() -> None:
    bridge = _make_bridge()
    raw = {
        "valid": False,
        "errors": [
            {"field": f"p{i}", "code": "X", "message": "m" * 50} for i in range(30)
        ],
        "warnings": [],
    }
    packaged = bridge._package_analysis_flow_result(raw)
    errors = packaged["llm_payload"]["errors"]
    assert len(errors) == 11  # 前 10 条 + TRUNCATED 计数条目
    assert errors[-1]["code"] == "TRUNCATED"
    # ui_payload 保留完整错误清单
    assert len(packaged["ui_payload"]["errors"]) == 30


def test_package_analysis_flow_result_small_errors_unchanged() -> None:
    bridge = _make_bridge()
    raw = {"valid": False, "errors": [{"field": "a", "code": "X", "message": "m"}], "warnings": []}
    packaged = bridge._package_analysis_flow_result(raw)
    assert packaged["llm_payload"]["errors"] == raw["errors"]


# ============ 目录分页 ============


def test_flow_service_pagination_slices_and_keeps_total() -> None:
    service = FlowService()
    all_items = service.list_flows()
    total = all_items.total
    assert total >= 2  # rna_seq + atac_seq（counts_deg 默认门控关闭）

    page = service.list_flows(limit=1, offset=0)
    assert len(page.items) == 1
    assert page.total == total

    page2 = service.list_flows(limit=1, offset=1)
    assert len(page2.items) == 1
    assert page.items[0].id != page2.items[0].id

    beyond = service.list_flows(limit=10, offset=total)
    assert beyond.items == []
    assert beyond.total == total


def test_flow_service_no_pagination_backwards_compatible() -> None:
    service = FlowService()
    assert service.list_flows().total == len(service.list_flows().items)
