"""Controlled BioReport integration.

BioReport is an external renderer. This adapter never runs a pipeline, never
passes platform credentials, and disables its optional AI module explicitly.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from cygnusx.application.schemas.report_delivery import BioReportRenderRequest


@dataclass(frozen=True)
class BioReportRenderResult:
    output: Path
    renderer_version: str
    template_version: str
    reused: bool


class BioReportAdapter:
    """Invoke a pinned BioReport executable with a sanitized configuration."""

    def __init__(
        self,
        *,
        executable: str = "bioreport",
        renderer_version: str = "unknown",
        template_version: str = "unknown",
        timeout_seconds: int = 600,
    ) -> None:
        self.executable = executable
        self.renderer_version = renderer_version
        self.template_version = template_version
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def validate_html_dependencies(source: Path) -> tuple[Path, ...]:
        """Return local HTML dependencies and reject remote or missing assets."""
        import re

        if source.is_symlink():
            raise ValueError("科学报告 HTML 不可用")
        source = source.resolve()
        if not source.is_file():
            raise ValueError("科学报告 HTML 不可用")
        html = source.read_text(encoding="utf-8")
        references = re.findall(r"<(?:script|link|img|source)[^>]+(?:src|href)=['\"]([^'\"]+)", html, re.I)
        dependencies: list[Path] = []
        for reference in references:
            parsed = urlparse(reference)
            if parsed.scheme in {"http", "https", "blob"} or reference.startswith("//"):
                raise ValueError("科学报告包含未授权的外部资源")
            if parsed.scheme == "data":
                continue
            if "${" in reference or reference.startswith(("+", "'", '"')):
                continue
            if reference.startswith("#"):
                continue
            target = (source.parent / reference).resolve()
            if not target.is_relative_to(source.parent.resolve()) or not target.is_file():
                raise ValueError("科学报告存在缺失的静态资源")
            dependencies.append(target)
        return tuple(dict.fromkeys(dependencies))

    @staticmethod
    def _safe_config(config: str, output_format: str) -> dict[str, Any]:
        candidate = Path(config)
        if candidate.is_symlink():
            raise ValueError("BioReport 配置不可用")
        path = candidate.resolve()
        if not path.is_file():
            raise ValueError("BioReport 配置不可用")
        content = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(content) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(content)
        if not isinstance(raw, dict):
            raise ValueError("BioReport 配置必须是对象")
        report = raw.setdefault("report", {})
        if not isinstance(report, dict):
            raise ValueError("BioReport report 配置无效")
        if output_format not in {"html", "pdf"}:
            raise ValueError("BioReport 输出格式不受支持")
        report["output_format"] = output_format
        report["layout"] = "single"
        modules = report.get("modules")
        if isinstance(modules, list):
            report["modules"] = [item for item in modules if item != "ai"]
        ai = raw.setdefault("ai", {})
        if not isinstance(ai, dict):
            raw["ai"] = {}
        raw["ai"]["enabled"] = False
        return raw

    def render(self, request: BioReportRenderRequest, output_dir: Path) -> BioReportRenderResult:
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        source_candidate = Path(request.scientific_report_source)
        if source_candidate.is_symlink():
            raise ValueError("科学报告 HTML 不可用")
        source = source_candidate.resolve()
        if request.output_format == "html" and source.is_file():
            self.validate_html_dependencies(source)
            return BioReportRenderResult(
                output=source,
                renderer_version=request.renderer_version,
                template_version=request.template_version,
                reused=True,
            )
        config = self._safe_config(request.report_config, request.output_format)
        with tempfile.TemporaryDirectory(prefix="cygnusx-bioreport-") as temp:
            config_path = Path(temp) / "report.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": temp,
                "NO_PROXY": "*",
                "BIOREPORT_AI_ENABLED": "false",
            }
            command = [
                self.executable,
                "run",
                "-c",
                str(config_path),
                "-o",
                str(output_dir),
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError("BioReport 渲染工具不可用或超时") from exc
            if completed.returncode != 0:
                raise RuntimeError("BioReport 渲染失败")
        output = output_dir / f"report.{request.output_format}"
        if not output.is_file() or output.is_symlink() or output.stat().st_size == 0:
            raise RuntimeError("BioReport 未生成有效报告文件")
        return BioReportRenderResult(
            output=output,
            renderer_version=request.renderer_version,
            template_version=request.template_version,
            reused=False,
        )
