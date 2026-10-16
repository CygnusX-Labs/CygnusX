"""首页文案服务 —— 加载 data/CygnusX.yaml，每次请求从磁盘读取，改文件即生效。

仿 docs_service 的磁盘读取风格：不落库、不走 lifespan 同步。
文件缺失 / 解析失败 / 字段缺失时回退到内置默认文案，保证首页永远不崩。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cygnusx.application.schemas.site_content import SiteContentDTO
from cygnusx.core.config import get_settings

# 内置默认文案：yaml 缺失或损坏时的兜底，保持首页可用
DEFAULT_CONTENT: dict[str, Any] = {
    "hero": {
        "title": "CygnusX BioOps · 天鹅座智能科研平台",
        "description": (
            "从公共数据发现或已有数据导入出发，以科研 Agent 组织研究任务，以标准化 Flow "
            "承载计算分析，以可信证据连接科研过程与成果交付。"
        ),
        "slogan": "让科学问题，抵达可验证的发现。",
        "tags": ["数据与文献发现", "受控计算分析", "可追溯交付", "科研资产积累"],
        "vision": {
            "title_en": "FROM STARDUST, TO DISCOVERY",
            "text": "让每一次科研探索，都留下可以继续前行的证据。",
            "label": "平台愿景",
        },
    },
    "quick_entries": [
        {"key": "treasure-mouse", "title": "科研寻宝鼠", "desc": "公共组学数据与文献探索"},
        {"key": "files", "title": "科研数据管理", "desc": "数据导入与科研资产组织"},
        {"key": "flows", "title": "多组学分析", "desc": "标准化、版本化分析流程"},
        {"key": "ai", "title": "星尘 AI 助手", "desc": "科研需求理解与智能协作"},
        {"key": "tasks", "title": "计算任务中心", "desc": "执行状态、日志与质量检查"},
        {"key": "reports", "title": "报告与证据", "desc": "分析报告、产物和来源记录"},
    ],
    "guide_steps": [
        {"title": "上传样本数据", "desc": "将 FASTQ / BAM 等原始数据上传至数据管理"},
        {"title": "选择分析流程", "desc": "在分析中心选择 RNA-seq 或 ATAC-seq 流程"},
        {"title": "查看分析结果", "desc": "任务完成后在任务中心查看与下载结果"},
    ],
    "registration": {
        "disabled_message": "当前平台暂停自助注册，需由管理员创建账号。",
        "admin_contact": "",
    },
    "activation": {
        "message": "喵喵！检测到账号还在沉睡中，快找管理员大大帮忙激活一下吧！开通后就能开心逛平台啦～",
        "admin_contact": "",
        "title": "账号还在星尘中沉睡 ✨",
        "button_text": "收到喵！",
        "title_urgent": "喵～ 你好像很着急呢 ⏳",
        "message_urgent": "(｡•́︿•̀｡) 再戳管理员一下嘛！开通后就能开心逛平台啦～ ✨",
        "button_text_urgent": "我这就去！",
    },
    "easter_egg": {
        "message": "🎉 恭喜你发现了 CygnusX 的隐藏星际守护者！",
        "button_text": "🐾 召唤星际猫咪",
        "toast": "🎉 星际守护者已响应召唤！快看看屏幕上留下的足迹吧～ ✨",
    },
    "ai_assistant": {
        "input_hint": "内容由 AI 生成，请仔细甄别",
    },
}


class SiteContentService:
    """首页文案服务"""

    def __init__(self, yaml_path: str | Path | None = None) -> None:
        self._path = Path(yaml_path) if yaml_path else Path(get_settings().site_content_yaml)

    def get_content(self) -> SiteContentDTO:
        """读取首页文案。yaml 缺失 / 解析失败 / 字段缺失时回退默认。"""
        data = _deep_merge(DEFAULT_CONTENT, self._load_yaml())
        try:
            dto = SiteContentDTO.model_validate(data)
        except Exception:
            # yaml 结构不合法时整体兜底，避免首页 500
            dto = SiteContentDTO.model_validate(DEFAULT_CONTENT)

        # activation.admin_contact 缺省时回退到 registration.admin_contact，
        # 避免管理员需在两处重复填写同一邮箱
        if not dto.activation.admin_contact:
            dto.activation.admin_contact = dto.registration.admin_contact
        return dto

    def _load_yaml(self) -> dict[str, Any]:
        """读盘；文件不存在 / 解析失败 / 非字典时返回空 dict（由默认值兜底）。"""
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            return {}
        return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深度合并：override 覆盖 base 同名字段，list 整体替换。"""
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
