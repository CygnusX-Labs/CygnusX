"""Render the frozen audit HTML to a static PDF without running analysis code."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


class AuditPdfRenderError(RuntimeError):
    """Raised when the controlled PDF toolchain cannot produce a PDF."""


def render_audit_pdf(
    html: bytes,
    *,
    executable: str = "pandoc",
    timeout_seconds: int = 300,
) -> bytes:
    """Convert already-rendered audit HTML with Pandoc and the Typst engine.

    The input is a frozen HTML byte stream. No project files, database settings,
    shell commands, or network credentials are made available to the renderer.
    """
    with tempfile.TemporaryDirectory(prefix="cygnusx-audit-pdf-") as temp:
        root = Path(temp)
        source = root / "audit.html"
        target = root / "audit.pdf"
        source.write_bytes(html)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": temp,
            "NO_PROXY": "*",
        }
        command = [
            executable,
            str(source),
            "-o",
            str(target),
            "--pdf-engine=typst",
            "-V",
            "mainfont=Droid Sans Fallback",
            "-V",
            "sansfont=Droid Sans Fallback",
            "-V",
            "monofont=Droid Sans Fallback",
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AuditPdfRenderError("审计 PDF 渲染工具不可用或超时") from exc
        if completed.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
            raise AuditPdfRenderError("审计 PDF 渲染失败")
        return target.read_bytes()
