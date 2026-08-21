"""pdf-inspector 主路径适配器。

Phase 2 启用：取消注释所有被标记为 "Phase 2" 的代码块，
并确保 `pdf-inspector` 已安装且 Rust 编译环境就绪。
"""

from __future__ import annotations

import logging
from typing import Any

from .exceptions import PDFInspectorError

logger = logging.getLogger(__name__)


class PDFInspectorAdapter:
    """pdf-inspector 主路径适配器。

    当前为 **占位实现**（Phase 1），内部直接返回空结果触发降级。
    待 pdf-inspector 安装并验证后，取消注释 Phase 2 代码即可激活。
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self._inspector: Any | None = None

    # ── Phase 2: 激活 pdf-inspector 时取消注释 ─────────────
    # def _ensure_loaded(self) -> None:
    #     if self._inspector is not None:
    #         return
    #     try:
    #         import pdf_inspector
    #         self._inspector = pdf_inspector
    #     except ImportError as exc:
    #         raise PDFInspectorError(
    #             "pdf-inspector is not installed. "
    #             "Run: pip install pdf-inspector"
    #         ) from exc

    def extract(self, file_path: str) -> dict:
        """使用 pdf-inspector 提取 PDF 内容。

        Returns:
            {
                "success": True,
                "markdown": str,
                "pages": [
                    {
                        "page_number": int,
                        "markdown": str,
                        "text": str,
                        "needs_ocr": bool,
                    }
                ],
                "metadata": {
                    "pdf_type": str,
                    "confidence": float,
                    "has_encoding_issues": bool,
                    "pages_needing_ocr": list[int],
                    "total_pages": int,
                }
            }
        """
        # ── Phase 1: 占位 ────────────────────────────────────
        logger.info("pdf-inspector adapter is in placeholder mode (Phase 1)")
        raise PDFInspectorError("pdf-inspector not yet activated (Phase 1)")

        # ── Phase 2: 激活时取消注释以下代码 ──────────────────
        # self._ensure_loaded()
        #
        # try:
        #     detection = self._inspector.detect_pdf(file_path)
        #     result = self._inspector.process_pdf(
        #         file_path,
        #         options={
        #             "extract_markdown": True,
        #             "extract_metadata": True,
        #             "enable_ocr": self.config.get("enable_ocr", False),
        #         },
        #     )
        #
        #     return {
        #         "success": True,
        #         "markdown": result.markdown,
        #         "pages": [
        #             {
        #                 "page_number": p.page_number,
        #                 "markdown": p.markdown,
        #                 "text": getattr(p, "text", p.markdown),
        #                 "needs_ocr": getattr(p, "needs_ocr", False),
        #             }
        #             for p in result.pages
        #         ],
        #         "metadata": {
        #             "pdf_type": getattr(detection, "pdf_type", "unknown"),
        #             "confidence": getattr(detection, "confidence", 1.0),
        #             "has_encoding_issues": getattr(
        #                 detection, "has_encoding_issues", False
        #             ),
        #             "pages_needing_ocr": getattr(
        #                 result, "pages_needing_ocr", []
        #             ),
        #             "total_pages": getattr(result, "total_pages", 0),
        #         },
        #     }
        # except Exception as exc:
        #     raise PDFInspectorError(f"pdf-inspector failed: {exc}") from exc
