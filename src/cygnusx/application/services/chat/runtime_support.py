"""聊天 Runtime 共用的文件、附件、额度、技能和搜索支撑。"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import anyio
import httpx
from loguru import logger
from sqlalchemy import select

from cygnusx.application.services.chat.context_compaction import (
    CompactionCancelled,
    CompactionPolicy,
    compact,
    externalize_large_outputs,
    write_compaction_archive,
)
from cygnusx.application.services.chat.context_estimate import calibration_ratio, estimate_context
from cygnusx.application.services.overdrive_planning_service import build_research_queries
from cygnusx.application.services.research_search_optimizer import ResearchSearchOptimizer
from cygnusx.application.services.search_provider_service import SearchProviderService
from cygnusx.core.config import get_settings
from cygnusx.core.telemetry import get_meter, get_tracer
from cygnusx.domain.skill.services import SKILL_RESOURCE_TOOL_NAME, USE_SKILL_TOOL_NAME
from cygnusx.infrastructure.ai_provider.openai_compatible import (
    normalize_token_usage,
    provider_manager,
)
from cygnusx.infrastructure.database.models.ai_provider import AIProviderConfigModel
from cygnusx.infrastructure.database.models.chat import ChatMessageModel, ChatSessionModel
from cygnusx.infrastructure.database.retry import execute_read_with_retry
from cygnusx.infrastructure.database.session import get_session_factory

_chat_meter = get_meter("cygnusx.chat")
_skill_count = _chat_meter.create_counter("skill.execute.count", description="技能工具执行次数")
_skill_duration = _chat_meter.create_histogram(
    "skill.execute.duration", unit="ms", description="技能工具执行耗时"
)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def extract_docx_text(source: Any) -> str:
    """从 docx（OOXML zip 容器）提取正文纯文本，仅依赖标准库。

    source 可以是本地路径（str/Path）或文件字节（bytes）。
    原理：读取 word/document.xml，把段落结尾/换行/制表符转成文本符号后剥掉其余 XML 标签。
    提取失败（非 zip、缺 document.xml 等）返回空串。
    """
    import io
    import re
    import zipfile
    from html import unescape

    try:
        if isinstance(source, bytes):
            zf_ctx = zipfile.ZipFile(io.BytesIO(source))
        else:
            zf_ctx = zipfile.ZipFile(str(source))
        with zf_ctx as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""
    xml = re.sub(r"<w:tab\b[^>]*/?>", "\t", xml)
    xml = re.sub(r"<w:br\b[^>]*/?>", "\n", xml)
    xml = re.sub(r"</w:p>", "\n", xml)
    text = unescape(re.sub(r"<[^>]+>", "", xml))
    # 收敛空行，避免注入大量空白
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def is_docx_attachment(mime_type: str, filename: str) -> bool:
    """按 MIME 或扩展名识别 docx 附件。"""
    return mime_type == _DOCX_MIME or Path(filename).suffix.lower() == ".docx"


_EXCEL_MIME_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel.sheet.macroenabled.12",
    }
)
_EXCEL_SUFFIXES = frozenset({".xlsx", ".xlsm"})
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_PPTX_SUFFIXES = frozenset({".pptx", ".pptm"})

_IMAGE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tif", ".tiff"}
)
# 视觉模型普遍只接受 png/jpeg/gif/webp；其它位图先转 PNG 再注入。
_IMAGE_CONVERT_SUFFIXES = frozenset({".tif", ".tiff", ".bmp", ".ico"})
_IMAGE_CONVERT_MIME_TYPES = frozenset(
    {"image/tiff", "image/bmp", "image/x-icon", "image/vnd.microsoft.icon"}
)

# 旧版二进制 Office / 压缩包不能在聊天里按 UTF-8 硬读，否则会向模型注入乱码。
_BINARY_ATTACHMENT_SUFFIXES = frozenset(
    {
        ".doc",
        ".ppt",
        ".xls",
        ".xlsb",
        ".bam",
        ".cram",
        ".h5ad",
        ".rds",
        ".qs",
        ".gz",
        ".tar",
        ".bz2",
        ".xz",
        ".zip",
        ".npy",
        ".npz",
        ".pkl",
        ".parquet",
        ".feather",
        ".tif",
        ".tiff",
        ".biom",
        ".h5",
        ".hdf5",
        ".mat",
        ".fcs",
        ".mzml",
        ".mzxml",
        ".mgf",
        ".raw",
        ".bw",
        ".bigwig",
        ".bcf",
        ".maf",
        ".idat",
        ".cel",
        ".qza",
        ".qzv",
    }
)

# 压缩文本（如 counts.csv.gz）可透明解压预览；其余压缩包只回元数据。
_COMPRESSION_SUFFIXES = frozenset({".gz", ".bz2", ".xz"})
_COMPRESSED_TEXT_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".csv",
        ".tsv",
        ".tab",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".htm",
        ".vcf",
        ".gff",
        ".gff3",
        ".gtf",
        ".bed",
        ".sam",
        ".fasta",
        ".fa",
        ".fna",
        ".faa",
        ".ffn",
        ".fastq",
        ".fq",
        ".nwk",
        ".newick",
        ".nhx",
        ".nex",
        ".nxs",
        ".tree",
        ".tre",
        ".trees",
        ".dnd",
        ".aln",
        ".phy",
        ".phylip",
        ".sto",
        ".gmt",
        ".gmx",
        ".rnk",
        ".bib",
        ".ris",
        ".log",
        ".eml",
    }
)
_STRUCTURE_SUFFIXES = frozenset({".pdb", ".cif", ".mmcif"})
_CONTAINER_SUFFIXES = frozenset({".h5", ".hdf5", ".mat"})
_HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"

_ATTACHMENT_TEXT_MAX_BYTES = 256 * 1024
_EML_MAX_PARSE_BYTES = 5 * 1024 * 1024
_BIOM_MAX_PARSE_BYTES = 5 * 1024 * 1024
_STRUCTURE_MAX_PARSE_BYTES = 50 * 1024 * 1024
_IMAGE_MAX_PIXELS = 20_000_000
_IMAGE_MAX_SIDE = 2048


def is_image_attachment(mime_type: str, filename: str) -> bool:
    """按 MIME 或扩展名识别图片附件；MIME 缺失时也能走视觉链路。"""
    return mime_type.startswith("image/") or Path(filename).suffix.lower() in _IMAGE_SUFFIXES


def compressed_text_inner_suffix(filename: str) -> str | None:
    """返回压缩文本的内层扩展名（如 counts.csv.gz → .csv）；非文本压缩返回 None。"""
    suffix = Path(filename).suffix.lower()
    if suffix not in _COMPRESSION_SUFFIXES:
        return None
    inner = Path(filename).with_suffix("").suffix.lower()
    return inner if inner in _COMPRESSED_TEXT_SUFFIXES else None


def is_excel_attachment(mime_type: str, filename: str) -> bool:
    """按 MIME 或扩展名识别可提取文本的 OOXML Excel 附件。"""
    return mime_type in _EXCEL_MIME_TYPES or Path(filename).suffix.lower() in _EXCEL_SUFFIXES


def is_pptx_attachment(mime_type: str, filename: str) -> bool:
    """按 MIME 或扩展名识别可提取文本的 PPTX 附件。"""
    return mime_type == _PPTX_MIME or Path(filename).suffix.lower() in _PPTX_SUFFIXES


def _column_index(cell_ref: str) -> int:
    """把单元格引用（如 BM12）的列字母转成 0 起始列号。"""
    index = 0
    for char in cell_ref:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return max(index - 1, 0)


_OOXML_MAX_XML_BYTES = 10 * 1024 * 1024


def _read_ooxml_entry(zf: Any, name: str) -> bytes:
    """读取 OOXML zip 条目，拒绝超大条目（防 zip bomb）。"""
    try:
        info = zf.getinfo(name)
    except KeyError:
        return b""
    if info.file_size > _OOXML_MAX_XML_BYTES:
        return b""
    try:
        return bytes(zf.read(name))
    except Exception:  # noqa: BLE001
        return b""


def _parse_ooxml_xml(data: bytes) -> Any:
    """解析 OOXML XML，拒绝 DTD/实体声明以规避实体膨胀攻击。"""
    if not data:
        return None
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        return None
    from xml.etree import ElementTree as ET

    try:
        return ET.fromstring(data)
    except Exception:  # noqa: BLE001
        return None


def extract_xlsx_text(
    source: Any,
    *,
    max_rows_per_sheet: int = 200,
    max_cols: int = 50,
    max_chars: int = 30_000,
) -> str:
    """从 xlsx/xlsm（OOXML zip 容器）提取工作表内容，仅依赖标准库。

    source 可以是本地路径（str/Path）或文件字节（bytes）。输出按工作表分段，
    行内以制表符分隔；超出预览上限时追加截断标记。提取失败返回空串。
    """
    import io
    import posixpath
    import zipfile
    from xml.etree import ElementTree as ET

    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"

    def _cell_text(cell: ET.Element, shared: list[str]) -> str:
        cell_type = cell.get("t")
        if cell_type == "inlineStr":
            return "".join(node.text or "" for node in cell.iter(f"{{{main_ns}}}t"))
        value_node = cell.find(f"{{{main_ns}}}v")
        if value_node is None:
            return ""
        raw = value_node.text or ""
        if cell_type == "s":
            try:
                return shared[int(raw)]
            except (ValueError, IndexError):
                return ""
        if cell_type == "b":
            return "TRUE" if raw == "1" else "FALSE"
        return raw

    try:
        if isinstance(source, bytes):
            zf_ctx = zipfile.ZipFile(io.BytesIO(source))
        else:
            zf_ctx = zipfile.ZipFile(str(source))
        with zf_ctx as zf:
            names = set(zf.namelist())
            if "xl/workbook.xml" not in names:
                return ""
            workbook = _parse_ooxml_xml(_read_ooxml_entry(zf, "xl/workbook.xml"))
            if workbook is None:
                return ""

            rels: dict[str, str] = {}
            rel_root = _parse_ooxml_xml(_read_ooxml_entry(zf, "xl/_rels/workbook.xml.rels"))
            if rel_root is not None:
                for rel in rel_root.findall(f"{{{pkg_rel_ns}}}Relationship"):
                    rels[str(rel.get("Id") or "")] = str(rel.get("Target") or "")

            shared: list[str] = []
            shared_root = _parse_ooxml_xml(_read_ooxml_entry(zf, "xl/sharedStrings.xml"))
            if shared_root is not None:
                for item in shared_root.findall(f"{{{main_ns}}}si"):
                    shared.append(
                        "".join(node.text or "" for node in item.iter(f"{{{main_ns}}}t"))
                    )

            sheets: list[tuple[str, str]] = []
            for sheet in workbook.findall(f"{{{main_ns}}}sheets/{{{main_ns}}}sheet"):
                target = rels.get(str(sheet.get(f"{{{rel_ns}}}id") or ""), "")
                if not target:
                    continue
                path = target.lstrip("/")
                if not path.startswith("xl/"):
                    path = posixpath.normpath(posixpath.join("xl", path))
                if path in names:
                    sheets.append((str(sheet.get("name") or ""), path))
            if not sheets:
                fallback = sorted(
                    name
                    for name in names
                    if name.startswith("xl/worksheets/") and name.endswith(".xml")
                )
                sheets = [(Path(name).stem, name) for name in fallback]

            sections: list[str] = []
            total_chars = 0
            for sheet_name, path in sheets[:20]:
                sheet_root = _parse_ooxml_xml(_read_ooxml_entry(zf, path))
                if sheet_root is None:
                    continue
                rows: list[str] = []
                truncated = False
                for row_index, row in enumerate(sheet_root.iter(f"{{{main_ns}}}row")):
                    if row_index >= max_rows_per_sheet:
                        truncated = True
                        break
                    values: dict[int, str] = {}
                    for cell in row.findall(f"{{{main_ns}}}c"):
                        column = _column_index(str(cell.get("r") or "A"))
                        if column >= max_cols:
                            truncated = True
                            continue
                        value = _cell_text(cell, shared)
                        if value:
                            values[column] = value.replace("\t", " ").replace("\n", " ")
                    if not values:
                        continue
                    width = max(values) + 1
                    rows.append("\t".join(values.get(i, "") for i in range(width)))
                if not rows:
                    continue
                section = f"# 工作表: {sheet_name}\n" + "\n".join(rows)
                if truncated:
                    section += "\n...（预览已截断，完整数据请在沙盒中读取）"
                sections.append(section)
                total_chars += len(section)
                if total_chars >= max_chars:
                    break
            return "\n\n".join(sections)[:max_chars].strip()
    except Exception:  # noqa: BLE001
        return ""


def extract_pptx_text(source: Any, *, max_slides: int = 100, max_chars: int = 30_000) -> str:
    """从 pptx（OOXML zip 容器）提取幻灯片文本，仅依赖标准库。"""
    import io
    import re as _re
    import zipfile

    drawing_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    try:
        if isinstance(source, bytes):
            zf_ctx = zipfile.ZipFile(io.BytesIO(source))
        else:
            zf_ctx = zipfile.ZipFile(str(source))
        with zf_ctx as zf:
            slide_items: list[tuple[int, str]] = []
            for name in zf.namelist():
                match = _re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name)
                if match:
                    slide_items.append((int(match.group(1)), name))
            slide_items.sort()

            sections: list[str] = []
            total_chars = 0
            for slide_number, path in slide_items[:max_slides]:
                root = _parse_ooxml_xml(_read_ooxml_entry(zf, path))
                if root is None:
                    continue
                texts = [
                    (node.text or "").strip()
                    for node in root.iter(f"{{{drawing_ns}}}t")
                    if (node.text or "").strip()
                ]
                if not texts:
                    continue
                section = f"# 幻灯片 {slide_number}\n" + "\n".join(texts)
                sections.append(section)
                total_chars += len(section)
                if total_chars >= max_chars:
                    break
            if len(slide_items) > max_slides:
                sections.append("...（幻灯片过多，预览已截断）")
            return "\n\n".join(sections)[:max_chars].strip()
    except Exception:  # noqa: BLE001
        return ""


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f}MB"
    if size >= 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size}B"


def _source_size(source: Any) -> int:
    if isinstance(source, (bytes, bytearray)):
        return len(source)
    try:
        return Path(source).stat().st_size
    except OSError:
        return 0


def _read_source_head(source: Any, max_bytes: int) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source[:max_bytes])
    try:
        with open(source, "rb") as fh:
            return fh.read(max_bytes)
    except OSError:
        return b""


def _decode_text_preview(raw: bytes, *, max_bytes: int = _ATTACHMENT_TEXT_MAX_BYTES) -> str:
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="ignore")
    if truncated:
        text += "\n...（内容预览已截断）"
    return text


def read_text_preview(source: Any, *, max_bytes: int = _ATTACHMENT_TEXT_MAX_BYTES) -> str:
    """读取文本预览，最多读取 max_bytes，避免大文件整体进内存。"""
    return _decode_text_preview(_read_source_head(source, max_bytes + 1), max_bytes=max_bytes)


def decompress_text_preview(
    source: Any,
    compression: str,
    *,
    max_bytes: int = _ATTACHMENT_TEXT_MAX_BYTES,
) -> tuple[str, bool]:
    """有界解压 gz/bz2/xz 文本，返回（预览文本, 是否截断）。"""
    import bz2
    import gzip
    import io
    import lzma

    openers: dict[str, Any] = {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open}
    opener = openers.get(compression)
    if opener is None:
        return "", False
    handle: Any = (
        io.BytesIO(bytes(source))
        if isinstance(source, (bytes, bytearray))
        else str(source)
    )
    try:
        with opener(handle, "rb") as fh:
            raw = fh.read(max_bytes + 1)
    except Exception:  # noqa: BLE001
        return "", False
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="ignore")
    if truncated:
        text += "\n...（压缩文本预览已截断）"
    return text, truncated


def extract_eml_text(source: Any, *, max_chars: int = 30_000) -> str:
    """提取 .eml 邮件的头信息与正文文本，仅依赖标准库。"""
    import email
    from email import policy
    from html import unescape

    raw = _read_source_head(source, _EML_MAX_PARSE_BYTES)
    if not raw:
        return ""
    try:
        message = email.message_from_bytes(raw, policy=policy.default)
    except Exception:  # noqa: BLE001
        return ""

    lines = ["# 邮件"]
    for label, key in (
        ("主题", "Subject"),
        ("发件人", "From"),
        ("收件人", "To"),
        ("日期", "Date"),
    ):
        value = message.get(key)
        if value:
            lines.append(f"- {label}: {value}")

    body_text = ""
    try:
        body = message.get_body(preferencelist=("plain", "html"))
        if body is not None:
            content = body.get_content()
            if isinstance(content, bytes):
                content = content.decode(body.get_content_charset() or "utf-8", errors="ignore")
            body_text = str(content)
            if body.get_content_type() == "text/html":
                body_text = unescape(re.sub(r"<[^>]+>", " ", body_text))
    except Exception:  # noqa: BLE001
        body_text = ""
    body_text = re.sub(r"[ \t]+", " ", body_text)
    body_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()
    if body_text:
        lines.extend(["", body_text])
    return "\n".join(lines)[:max_chars].strip()


def extract_structure_summary(
    source: Any, filename: str, *, max_chars: int = 30_000
) -> str:
    """用 Biopython 生成 PDB/mmCIF 结构摘要；解析失败返回空串。"""
    suffix = Path(filename).suffix.lower()
    if suffix not in _STRUCTURE_SUFFIXES:
        return ""
    size = _source_size(source)
    if size > _STRUCTURE_MAX_PARSE_BYTES:
        return (
            f"# 结构文件: {Path(filename).name}\n"
            f"- 大小: {_format_size(size)}\n"
            "- 超过在线摘要上限（50MB），请在沙盒中读取结构。"
        )

    temp_path: str | None = None
    try:
        import tempfile
        import warnings

        from Bio.PDB.MMCIFParser import MMCIFParser
        from Bio.PDB.PDBParser import PDBParser

        parser_source: Any = source
        if isinstance(source, (bytes, bytearray)):
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(bytes(source))
                temp_path = tmp.name
            parser_source = temp_path

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if suffix == ".pdb":
                structure = PDBParser(QUIET=True).get_structure(  # type: ignore[no-untyped-call]
                    "attachment", parser_source
                )
            else:
                structure = MMCIFParser(QUIET=True).get_structure(  # type: ignore[no-untyped-call]
                    "attachment", parser_source
                )

        models = list(structure.get_models())
        if not models:
            return f"# 结构文件: {Path(filename).name}\n- 未找到可解析的坐标记录。"
        model = models[0]
        chains = list(model.get_chains())
        residues = list(model.get_residues())
        atoms = list(model.get_atoms())
        hetero = sum(1 for residue in residues if residue.id[0].strip())
        chain_ids = ", ".join(str(chain.id) for chain in chains[:10])
        if len(chains) > 10:
            chain_ids += f" 等 {len(chains)} 条"
        return "\n".join(
            [
                f"# 结构文件: {Path(filename).name}",
                f"- 模型数: {len(models)}",
                f"- 链数: {len(chains)}" + (f"（{chain_ids}）" if chain_ids else ""),
                f"- 残基数: {len(residues)}（含配体/水等杂原子残基 {hetero}）",
                f"- 原子数: {len(atoms)}",
            ]
        )[:max_chars]
    except Exception:  # noqa: BLE001
        return ""
    finally:
        if temp_path:
            import contextlib

            with contextlib.suppress(OSError):
                Path(temp_path).unlink(missing_ok=True)


def extract_biom_text(source: Any, *, max_chars: int = 30_000) -> str:
    """生成 BIOM 丰度表摘要；JSON 解析维度，HDF5 容器只回元数据。"""
    import json

    size = _source_size(source)
    head = _read_source_head(source, 8)
    if head == _HDF5_MAGIC:
        return (
            "# BIOM 丰度表（HDF5 容器）\n"
            f"- 大小: {_format_size(size)}\n"
            "- 后端未内置 HDF5 解析器，请在沙盒中用 h5py/biom 读取。"
        )
    if size > _BIOM_MAX_PARSE_BYTES:
        return (
            "# BIOM 丰度表\n"
            f"- 大小: {_format_size(size)}\n"
            "- 超过在线摘要上限（5MB），请在沙盒中读取。"
        )

    try:
        payload = json.loads(_read_source_head(source, _BIOM_MAX_PARSE_BYTES).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    if not isinstance(payload, dict):
        return ""

    def _ids(items: Any) -> list[str]:
        if not isinstance(items, list):
            return []
        values: list[str] = []
        for item in items[:10]:
            value = (item.get("id") or item.get("name") or "") if isinstance(item, dict) else item
            if value:
                values.append(str(value))
        return values

    rows = payload.get("rows") or []
    columns = payload.get("columns") or []
    shape = payload.get("shape")
    try:
        if not isinstance(shape, (list, tuple)) or len(shape) < 2:
            raise ValueError("invalid shape")
        n_features, n_samples = int(shape[0]), int(shape[1])
    except (TypeError, ValueError):
        n_features, n_samples = len(rows), len(columns)

    lines = [
        "# BIOM 丰度表",
        f"- 类型: {payload.get('type') or '未知'}",
        f"- 维度: {n_features} 个特征 × {n_samples} 个样本",
    ]
    data = payload.get("data")
    if isinstance(data, list):
        lines.append(f"- 稀疏非零值: {len(data)}")
    feature_ids = _ids(rows)
    sample_ids = _ids(columns)
    if feature_ids:
        lines.append("- 特征示例: " + ", ".join(feature_ids))
    if sample_ids:
        lines.append("- 样本示例: " + ", ".join(sample_ids))
    return "\n".join(lines)[:max_chars]


def extract_data_container_summary(
    source: Any, filename: str, *, max_chars: int = 30_000
) -> str:
    """生成 HDF5/MAT 容器摘要；HDF5 只回元数据，MAT 用 scipy 枚举变量。"""
    suffix = Path(filename).suffix.lower()
    size = _source_size(source)
    head = _read_source_head(source, 512)
    if suffix in {".h5", ".hdf5"}:
        if head[:8] != _HDF5_MAGIC:
            return ""
        return (
            "# HDF5 数据文件\n"
            f"- 文件: {Path(filename).name}\n"
            f"- 大小: {_format_size(size)}\n"
            "- 后端未内置 h5py，无法枚举数据集；请在沙盒中用 h5py/pandas 读取。"
        )
    if suffix != ".mat":
        return ""
    if head.startswith(b"MATLAB 7.3") or head[:8] == _HDF5_MAGIC:
        return (
            "# MATLAB 数据文件（v7.3 / HDF5）\n"
            f"- 文件: {Path(filename).name}\n"
            f"- 大小: {_format_size(size)}\n"
            "- 该版本为 HDF5 容器，请在沙盒中用 h5py 读取变量。"
        )

    try:
        import io

        from scipy.io import whosmat  # type: ignore[import-untyped]

        handle: Any = (
            io.BytesIO(bytes(source))
            if isinstance(source, (bytes, bytearray))
            else str(source)
        )
        entries = whosmat(handle)
    except Exception:  # noqa: BLE001
        return ""

    lines = [
        "# MATLAB 数据文件",
        f"- 文件: {Path(filename).name}",
        f"- 大小: {_format_size(size)}",
    ]
    if not entries:
        lines.append("- 未发现可读变量。")
        return "\n".join(lines)[:max_chars]
    lines.append(f"- 变量数: {len(entries)}")
    for name, shape, class_name in entries[:30]:
        lines.append(f"- {name}: {class_name} {shape}")
    if len(entries) > 30:
        lines.append(f"- ...（其余 {len(entries) - 30} 个变量已省略）")
    return "\n".join(lines)[:max_chars]


def _convert_image_to_png(data: bytes) -> bytes | None:
    """把 TIFF/BMP/ICO 等视觉模型不支持的位图转成 PNG 预览。"""
    import io

    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > _IMAGE_MAX_PIXELS:
                return None
            image.seek(0)
            preview: Any = image
            if preview.mode.startswith("I") or preview.mode == "F":
                import numpy as np

                array = np.asarray(preview, dtype=np.float32)
                if array.size:
                    low = float(array.min())
                    high = float(array.max())
                    if high > low:
                        array = (array - low) * (255.0 / (high - low))
                    preview = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))
            if preview.mode not in ("RGB", "RGBA"):
                preview = preview.convert("RGBA" if "A" in preview.getbands() else "RGB")
            preview.thumbnail((_IMAGE_MAX_SIDE, _IMAGE_MAX_SIDE))
            output = io.BytesIO()
            preview.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except Exception:  # noqa: BLE001
        return None


class ChatRuntimeSupport:
    """供聊天 Runtime 复用的无状态能力混入。"""

    _context_calibration_ratios: dict[str, float] = {}
    _context_last_estimates: dict[str, int] = {}
    _context_compaction_policies: dict[str, CompactionPolicy] = {}
    _last_context_compaction: dict[str, Any] | None = None

    @classmethod
    def _context_calibration_key(cls, session_id: str | None, model_config: Any) -> str:
        model_id = getattr(model_config, "id", None) or getattr(model_config, "model", "default")
        return f"{session_id or 'unknown'}:{model_id}"

    @classmethod
    def _record_context_usage(
        cls,
        session_id: str | None,
        model_config: Any,
        prompt_tokens: int | None,
    ) -> None:
        key = cls._context_calibration_key(session_id, model_config)
        cls._context_calibration_ratios[key] = calibration_ratio(
            cls._context_calibration_ratios.get(key),
            prompt_tokens,
            cls._context_last_estimates.get(key),
        )

    async def _persist_context_compaction_audit(
        self,
        *,
        tokens: int,
        calibrated_tokens: float,
        estimate: Any | None = None,
    ) -> None:
        """Best-effort session audit; the compacted projection is never persisted."""
        session_id = getattr(self, "_active_context_session_id", None)
        if not session_id or not hasattr(self, "_db"):
            return
        if getattr(self, "_defer_compaction_audit", False):
            # LangGraph 路径在独立 task 中执行 llm_call，图内直接写请求级
            # session 会与消费协程的 update_message_content 并发 flush，
            # 触发 "Session is already flushing" 并打坏 asyncpg 连接。
            # 这里只暂存最后一次结果，由消费协程收尾时统一落库。
            self._deferred_compaction_audit = {
                "tokens": tokens,
                "calibrated_tokens": calibrated_tokens,
                "estimate": estimate,
            }
            return
        await self._write_compaction_audit(
            tokens=tokens, calibrated_tokens=calibrated_tokens, estimate=estimate
        )

    async def _flush_deferred_compaction_audit(self) -> None:
        """消费协程在图执行结束后落库暂存的压缩审计（请求级 session 内串行安全）。"""
        payload = getattr(self, "_deferred_compaction_audit", None)
        if not payload:
            return
        self._deferred_compaction_audit = None
        try:
            await self._write_compaction_audit(**payload)
        except Exception as exc:  # noqa: BLE001 - audit must not affect chat
            logger.warning(f"上下文压缩审计写入失败: {exc}")

    async def _write_compaction_audit(
        self,
        *,
        tokens: int,
        calibrated_tokens: float,
        estimate: Any | None = None,
    ) -> None:
        session_id = getattr(self, "_active_context_session_id", None)
        if not session_id or not hasattr(self, "_db"):
            return
        policy = self._context_compaction_policies.get(
            self._context_calibration_key(session_id, getattr(self, "_active_model_config", None))
        )
        try:
            result = await self._db.execute(
                select(ChatSessionModel).where(ChatSessionModel.session_id == session_id)
            )
            session = result.scalar_one_or_none()
            if session is None:
                return
            metadata = dict(session.sandbox_meta or {})
            metadata["context_compaction"] = {
                "context_estimate_calibrated_total": calibrated_tokens,
                "context_estimate_total": tokens,
                "context_estimate": estimate.as_dict() if estimate is not None else {"total": tokens},
                "compaction_failure_streak": policy.failure_streak if policy else 0,
                "compaction_low_yield_streak": policy.low_yield_streak if policy else 0,
                "compaction_circuit_open": policy.circuit_open if policy else False,
                "compaction_circuit_reason": policy.circuit_reason if policy else None,
                "last_compaction_yield_ratio": (self._last_context_compaction or {}).get("yield_ratio"),
            }
            session.sandbox_meta = metadata
            await self._db.flush()
        except Exception as exc:  # noqa: BLE001 - audit must not affect chat
            logger.warning(f"上下文压缩审计写入失败: {exc}")

    async def _link_session_files_to_workspace(
        self,
        session_id: str,
        user_id: str | None,
        attachment_dicts: list[dict[str, Any]],
    ) -> dict[str, str]:
        """把本轮和历史受控附件幂等引入当前 Session ``/workspace/input/``。

        返回 ``{规范化引用(upload://…、file://… 或 directory://…): 沙盒可读路径}``。
        沙盒内无法解析 file:// / upload:// 引用，只有挂载进工作区的平台软链才能被沙盒
        代码按文件系统路径直接读取；任一文件引入失败仅记录并跳过，不阻断对话。
        """
        if not user_id:
            return {}

        def _normalize_ref(file_id: str) -> str:
            fid = str(file_id or "").strip()
            if not fid:
                return ""
            return fid if "://" in fid else f"upload://{fid}"

        refs: list[str] = [_normalize_ref(att.get("file_id")) for att in attachment_dicts]

        # 历史轮次的上传同样需要挂载才能在沙盒读取（多轮分析场景）
        try:
            result = await execute_read_with_retry(
                self._db,
                select(ChatMessageModel)
                .where(ChatMessageModel.session_id == session_id)
                .order_by(ChatMessageModel.created_at)
            )
            for msg in self._order_messages(result.scalars().all()):
                if msg.role != "user":
                    continue
                for att in (msg.metadata_json or {}).get("attachments") or []:
                    refs.append(_normalize_ref(att.get("file_id")))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Studio 收集历史上传文件引用失败: {}", exc)

        refs = [ref for ref in refs if ref]
        if not refs:
            return {}

        from cygnusx.application.services.studio_context_service import link_session_workspace_refs

        try:
            paths, _manifests, errors = await link_session_workspace_refs(
                str(user_id), session_id, refs, self._db
            )
        except Exception as exc:  # noqa: BLE001 - 挂载失败不能打断对话，模型仍可走 datahub_import
            logger.warning("Studio 批量引入工作区文件失败: {}", exc)
            return {}
        if errors:
            logger.info(f"Session 工作区资源部分引入失败（{len(errors)} 项）: {errors}")
        return paths

    async def _collect_session_file_context(
        self,
        session_id: str,
        exclude_file_ids: set[str] | None = None,
        user_id: str | None = None,
        studio_sandbox_paths: dict[str, str] | None = None,
        studio_mode: bool = False,
    ) -> str:
        """汇总本会话历史消息中的附件引用，供后续轮次继承文件上下文。

        返回空串表示没有可继承的历史文件。附件元数据在消息落库时写入
        metadata_json.attachments，这里只做读取与去重。
        额外兜底：扫描该用户 chat-uploads 目录，按文件名内嵌的会话标记
        （``.s{session_id前8位}``）找回本会话上传过、但未进入消息元数据的文件。
        严格按会话隔离：其它会话的上传不注入，避免跨对话污染。
        ``studio_mode`` 决定未挂载文件的回退措辞：Studio 会话没有
        chat_sandbox_execute，不能再用"执行时自动注入沙盒"的说法。
        """
        exclude = exclude_file_ids or set()
        result = await execute_read_with_retry(
            self._db,
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at)
        )
        lines: list[str] = []
        seen: set[str] = set()
        for msg in self._order_messages(result.scalars().all()):
            if msg.role != "user":
                continue
            for att in (msg.metadata_json or {}).get("attachments") or []:
                file_id = str(att.get("file_id") or "")
                if not file_id or file_id in seen or file_id in exclude:
                    continue
                seen.add(file_id)
                ref = file_id if "://" in file_id else f"upload://{file_id}"
                sandbox_path = (studio_sandbox_paths or {}).get(ref)
                if att.get("type") == "directory":
                    if sandbox_path:
                        lines.append(
                            f"- {att.get('name', '')}/（已只读引入工作区 {sandbox_path}；"
                            "请先用 workspace_list 分页列举，再按需读取文件）"
                        )
                    continue
                if sandbox_path:
                    lines.append(
                        f"- {att.get('name', '')}（已引入工作区 {sandbox_path}，"
                        "沙盒代码请直接按该路径读取，勿用 file:// / upload:// 引用）"
                    )
                else:
                    if studio_mode:
                        lines.append(
                            f"- {att.get('name', '')}（file_id: {ref}，未挂载进沙盒工作区；"
                            f'可用 workspace_read_file(file_id="{ref}") 在宿主侧读取内容，'
                            f"或调用 datahub_import 引入沙盒 /workspace/input/ 后按路径读取）"
                        )
                    else:
                        lines.append(
                            f"- {att.get('name', '')}（file_id: {ref}，"
                            f'可用 workspace_read_file(file_id="{ref}") 读取；'
                            f"chat_sandbox_execute 执行时会自动注入沙盒 /workspace/input/）"
                        )

        sections: list[str] = []
        if lines:
            sections.append(
                "[本会话中用户历史上传过的文件，可直接用 file_id 引用，无需重新搜索。"
                "仅当用户请求涉及这些文件时才使用；与当前请求无关时忽略，不要主动读取或提及]\n"
                + "\n".join(lines)
            )

        if user_id:
            recent_lines = self._collect_recent_upload_lines(
                user_id, seen | exclude, session_id=session_id
            )
            if recent_lines:
                sections.append(
                    "[本会话最近上传的文件，仅供备用：仅当用户请求与这些文件相关"
                    "或用户明确引用时才可使用；与当前请求无关时忽略，不要主动读取、检查或提及。"
                    "纯代码编写/概念问答类请求无需任何数据文件]\n" + "\n".join(recent_lines)
                )

        return "\n\n".join(sections)

    @staticmethod
    def _collect_recent_upload_lines(
        user_id: str, skip_file_ids: set[str], session_id: str = "", limit: int = 5
    ) -> list[str]:
        """扫描用户 chat-uploads 目录，返回本会话最近上传文件的引用行（按修改时间倒序）。

        聊天上传文件名内嵌会话标记（``.s{session_id前8位}``）；给了 session_id 时
        只保留带本会话标记的文件，其它会话的上传一律不注入（会话隔离）。
        """
        from cygnusx.infrastructure.config.storage_config import get_user_chat_upload_dir

        upload_dir = get_user_chat_upload_dir(user_id)
        if not upload_dir.is_dir():
            return []
        session_marker = f".s{session_id[:8]}" if session_id else ""
        try:
            recent = sorted(
                (
                    p
                    for p in upload_dir.iterdir()
                    if p.is_file() and (not session_marker or session_marker in p.name)
                ),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return []
        lines: list[str] = []
        for path in recent:
            fid = path.name.split(".", 1)[0]
            if not fid or fid in skip_file_ids:
                continue
            ref = f"upload://{fid}"
            lines.append(
                f'- {path.name}（file_id: {ref}，可用 workspace_read_file(file_id="{ref}") 读取）'
            )
            if len(lines) >= limit:
                break
        return lines

    @staticmethod
    def _append_context_to_last_user_message(
        messages: list[dict[str, Any]], context_text: str
    ) -> list[dict[str, Any]]:
        """把补充上下文追加到最后一条用户消息（仅影响送 LLM 的视图，不落库）。"""
        if not messages:
            return messages
        target_index = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"),
            default=-1,
        )
        if target_index == -1:
            return messages
        target = messages[target_index]
        content = target.get("content", "")
        new_messages = list(messages)
        if isinstance(content, list):
            new_messages[target_index] = {
                **target,
                "content": content + [{"type": "text", "text": f"\n\n{context_text}"}],
            }
        else:
            new_messages[target_index] = {
                **target,
                "content": f"{content}\n\n{context_text}",
            }
        return new_messages

    # --- 上下文压缩（per-model 窗口保护） ---

    @staticmethod
    def _message_text(message: dict[str, Any]) -> str:
        content = message.get("content", "")
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        return str(content)

    @classmethod
    def _estimate_messages_tokens(
        cls,
        messages: list[dict[str, Any]],
        *,
        tool_schemas: Any = (),
        system_prompt: str | None = None,
    ) -> int:
        """Estimate provider input using CJK-aware accounting."""
        return estimate_context(
            messages, tool_schemas, system_prompt=system_prompt
        ).total

    async def _legacy_compress_context_if_needed(
        self,
        messages: list[dict[str, Any]],
        model_config: Any,
        *,
        keep_recent: int,
    ) -> tuple[list[dict[str, Any]], bool, int]:
        """Exact opt-in rollback path for deployments retaining the old behavior."""
        legacy_threshold = 200_000
        legacy_keep = 10
        original_tokens = sum(len(self._message_text(message)) // 2 + 4 for message in messages)
        if original_tokens <= legacy_threshold or len(messages) <= legacy_keep + 2:
            return messages, False, original_tokens
        old, recent = messages[:-legacy_keep], messages[-legacy_keep:]
        digest_lines: list[str] = []
        for message in old:
            text = self._message_text(message)[:2000]
            if text.strip():
                digest_lines.append(f"[{message.get('role', '?')}] {text}")
        try:
            parts: list[str] = []
            async for chunk in provider_manager.chat_stream(
                config=model_config,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "请将以下对话历史压缩为一份结构化摘要，必须保留：用户的分析目标与需求、"
                            "关键数据文件引用（file_id / 文件名 / 路径）、已完成的分析步骤与结论、"
                            "生成的产物（图表/文件）、以及未完成的待办事项。\n\n"
                            + "\n\n".join(digest_lines)
                        ),
                    }
                ],
                system_prompt="你是对话压缩器，只输出摘要本身，不超过 1500 字。",
                max_tokens=2048,
            ):
                if chunk.type == "text":
                    parts.append(chunk.content)
            summary = "".join(parts).strip()
        except Exception as exc:  # noqa: BLE001 - explicit rollback preserves legacy semantics
            logger.warning(f"上下文压缩摘要生成失败，降级为硬截断: {exc}")

        if summary:
            compressed = [
                {
                    "role": "system",
                    "content": "[早期对话已压缩为摘要，后续请基于摘要与最近对话继续]\n" + summary,
                }
            ] + recent
            logger.info(
                f"上下文已压缩: 估算 {original_tokens} tokens，{len(old)} 条早期消息 → 摘要 + 最近 {len(recent)} 条"
            )
            return compressed, True, original_tokens

        fallback = [message for message in old[:1] if message.get("role") == "user"] + recent
        logger.info(
            f"上下文硬截断: 估算 {original_tokens} tokens，保留 {len(fallback)}/{len(messages)} 条"
        )
        return fallback, True, original_tokens

    async def _compress_context_if_needed(
        self,
        messages: list[dict[str, Any]],
        model_config: Any,
        *,
        tool_schemas: Any = (),
        system_prompt: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool, int]:
        """Prepare a compact request view; failures keep the complete input."""
        original_messages = messages
        self._last_context_compaction = None
        self._last_context_compaction_policy = None
        compaction = get_settings().context_compaction
        keep = max(1, int(compaction.keep_recent_min))
        if getattr(compaction, "legacy_fallback", False):
            return await self._legacy_compress_context_if_needed(
                messages, model_config, keep_recent=keep
            )
        session_part = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            str(getattr(self, "_active_context_session_id", "unknown")),
        ).strip("._-") or "unknown"
        archive_root = Path(get_settings().storage_path) / "context-archive" / session_part
        try:
            messages, archived_count = externalize_large_outputs(
                messages,
                archive_root,
                threshold_chars=int(compaction.large_output_chars),
                preview_chars=int(compaction.preview_chars),
                workspace_dir=getattr(self, "_active_context_workspace_dir", None),
            )
        except Exception as exc:  # noqa: BLE001 - externalization is best effort
            archived_count = 0
            logger.warning(f"上下文大输出外化失败，保留原文: {exc}")
        original_estimate = estimate_context(
            original_messages, tool_schemas, system_prompt=system_prompt
        )
        original_tokens = original_estimate.total
        tokens = self._estimate_messages_tokens(
            messages, tool_schemas=tool_schemas, system_prompt=system_prompt
        )
        context_window = max(1, int(getattr(model_config, "context_window", 262_144) or 262_144))
        key = self._context_calibration_key(
            getattr(self, "_active_context_session_id", None), model_config
        )
        ratio = self._context_calibration_ratios.get(key, 1.0)
        calibrated_tokens = tokens * ratio
        self._context_last_estimates[key] = tokens

        def _set_provider_estimate(value: int) -> None:
            """Keep calibration paired with the view sent to the provider."""
            self._context_last_estimates[key] = max(0, int(value))

        trigger = context_window * float(compaction.trigger_ratio)
        if calibrated_tokens <= trigger or len(messages) <= max(keep + 2, int(compaction.min_messages)):
            if archived_count:
                _set_provider_estimate(tokens)
                self._last_context_compaction = {
                    "tokens_before": original_tokens,
                    "tokens_after": tokens,
                    "yield_ratio": max(0.0, (original_tokens - tokens) / max(1, original_tokens)),
                    "archived_count": archived_count,
                    "note_preview_sha256": "",
                }
                message_id = getattr(self, "_active_context_message_id", None)
                if message_id:
                    try:
                        from cygnusx.application.services.chat_message_event_service import (
                            message_event_service,
                        )

                        await message_event_service.append_compaction_event(
                            message_id,
                            **self._last_context_compaction,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(f"context_compacted 事件排队失败: {exc}")
                await self._persist_context_compaction_audit(
                    tokens=original_tokens,
                    calibrated_tokens=original_tokens * ratio,
                    estimate=original_estimate,
                )
                # The request view is smaller because large outputs were
                # externalized, but the event/UI "before" value must describe
                # the original DB-backed context rather than the projected view.
                return messages, True, original_tokens
            _set_provider_estimate(original_tokens)
            await self._persist_context_compaction_audit(
                tokens=original_tokens,
                calibrated_tokens=original_tokens * ratio,
                estimate=original_estimate,
            )
            return original_messages, False, original_tokens

        async def chat_fn(request: list[dict[str, Any]], *, max_tokens: int, temperature: float) -> dict[str, Any]:
            parts: list[str] = []
            metadata: dict[str, Any] = {}
            async for chunk in provider_manager.chat_stream(
                config=model_config,
                messages=request,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                if chunk.type == "text":
                    parts.append(chunk.content)
                elif chunk.type == "done":
                    metadata.update(chunk.metadata)
            metadata["content"] = "".join(parts)
            return metadata

        policy = self._context_compaction_policies.setdefault(
            key,
            CompactionPolicy(
                min_yield_ratio=float(compaction.min_yield_ratio),
                breaker_attempts=int(compaction.breaker_attempts),
                circuit_retry_growth=float(compaction.circuit_retry_growth),
            ),
        )
        # Settings are reloadable at runtime. Keep existing session policies in
        # sync so a hot reload takes effect without restarting the process.
        policy.min_yield_ratio = float(compaction.min_yield_ratio)
        policy.breaker_attempts = int(compaction.breaker_attempts)
        policy.circuit_retry_growth = float(compaction.circuit_retry_growth)
        circuit_was_open = policy.circuit_open
        try:
            result = await policy.prepare(
                messages,
                compact_fn=lambda: compact(
                    messages,
                    chat_fn=chat_fn,
                    context_window=context_window,
                    model_config=model_config,
                    tool_schemas=tool_schemas,
                    system_prompt=system_prompt,
                    host_state_fact=getattr(self, "_active_context_host_state_fact", None),
                    keep_recent=keep,
                    tail_ratio=float(compaction.tail_ratio),
                    summary_max_tokens=max(8192, int(getattr(model_config, "max_tokens", 0) or 0)),
                    summary_max_chars=int(compaction.summary_max_chars),
                ),
                context_total=tokens,
            )
        except CompactionCancelled:
            _set_provider_estimate(original_tokens)
            logger.info("[compaction cancelled] 用户中断，保留完整上下文且不累计 failure_streak")
            self._last_context_compaction_policy = {
                "failure_streak": policy.failure_streak,
                "low_yield_streak": policy.low_yield_streak,
                "circuit_open": policy.circuit_open,
                "circuit_reason": policy.circuit_reason,
            }
            return original_messages, False, original_tokens
        except Exception as exc:  # noqa: BLE001 - compaction must never kill chat
            _set_provider_estimate(original_tokens)
            logger.warning(f"[compaction fallback] 上下文压缩失败，保留完整上下文继续: {exc}")
            self._last_context_compaction_policy = {
                "failure_streak": policy.failure_streak,
                "low_yield_streak": policy.low_yield_streak,
                "circuit_open": policy.circuit_open,
                "circuit_reason": policy.circuit_reason,
            }
            return original_messages, False, original_tokens
        if result is None or result.tokens_after >= result.tokens_before:
            _set_provider_estimate(original_tokens)
            if circuit_was_open and not policy.circuit_open:
                logger.info("[compaction retry] context grew，熔断自动恢复")
            if policy.circuit_open:
                logger.info("[compaction skipped] circuit open，保留完整上下文")
            else:
                logger.info(f"[compaction low-yield] 保留完整上下文: {tokens} tokens")
            self._last_context_compaction_policy = {
                "failure_streak": policy.failure_streak,
                "low_yield_streak": policy.low_yield_streak,
                "circuit_open": policy.circuit_open,
                "circuit_reason": policy.circuit_reason,
            }
            await self._persist_context_compaction_audit(
                tokens=original_tokens,
                calibrated_tokens=original_tokens * ratio,
                estimate=original_estimate,
            )
            return original_messages, False, original_tokens
        logger.info(
            f"[compacted] 估算 {result.tokens_before}->{result.tokens_after} tokens，"
            f"保留 {len(result.projected)} 条投影消息"
        )
        yield_ratio = max(0.0, (result.tokens_before - result.tokens_after) / max(1, result.tokens_before))
        note = next((m for m in result.projected if m.get("compaction_handoff")), {})
        note_hash = hashlib.sha256(str(note.get("content") or "").encode("utf-8")).hexdigest()
        compaction_metadata = {
            "tokens_before": result.tokens_before,
            "tokens_after": result.tokens_after,
            "yield_ratio": yield_ratio,
            "archived_count": archived_count,
            "note_preview_sha256": note_hash,
        }
        if result.archive_payload:
            try:
                session_part = re.sub(
                    r"[^A-Za-z0-9_.-]+",
                    "_",
                    str(getattr(self, "_active_context_session_id", "session")),
                ).strip("._-") or "session"
                archive_id = f"{session_part}-{time.time_ns()}"
                archive_path = write_compaction_archive(
                    Path(get_settings().storage_path) / "context-archive" / session_part,
                    result.archive_payload,
                    archive_id=archive_id,
                )
                compaction_metadata["archive_ref"] = archive_path
            except Exception as exc:  # noqa: BLE001 - archive is best effort
                _set_provider_estimate(original_tokens)
                policy.failure_streak += 1
                if policy.failure_streak >= policy.breaker_attempts:
                    policy.circuit_open = True
                    policy.circuit_open_total = tokens
                    policy.circuit_reason = "archive failure"
                self._last_context_compaction_policy = {
                    "failure_streak": policy.failure_streak,
                    "low_yield_streak": policy.low_yield_streak,
                    "circuit_open": policy.circuit_open,
                    "circuit_reason": policy.circuit_reason,
                }
                logger.warning(f"[compaction fallback] 上下文压缩归档失败，放弃采用压缩投影: {exc}")
                await self._persist_context_compaction_audit(
                    tokens=original_tokens,
                    calibrated_tokens=original_tokens * ratio,
                    estimate=original_estimate,
                )
                return original_messages, False, original_tokens
        _set_provider_estimate(result.tokens_after)
        self._last_context_compaction = compaction_metadata
        self._last_context_compaction_policy = {
            "failure_streak": policy.failure_streak,
            "low_yield_streak": policy.low_yield_streak,
            "circuit_open": policy.circuit_open,
            "circuit_reason": policy.circuit_reason,
        }
        message_id = getattr(self, "_active_context_message_id", None)
        if message_id:
            try:
                from cygnusx.application.services.chat_message_event_service import (
                    message_event_service,
                )

                await message_event_service.append_compaction_event(
                    message_id,
                    **self._last_context_compaction,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"context_compacted 事件排队失败: {exc}")
        await self._persist_context_compaction_audit(
            tokens=original_tokens,
            calibrated_tokens=original_tokens * ratio,
            estimate=original_estimate,
        )
        return result.projected, True, result.tokens_before

    @staticmethod
    async def _build_multimodal_messages(
        messages: list[dict[str, Any]],
        attachments: list[Any],
        studio_sandbox_paths: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """把附件注入到最后一条用户消息中。

        兼容策略：
        - 只有文本/文件附件时，保持 content 为字符串（对 Qwen 等国产模型兼容性最好）。
        - 包含图片附件时，使用 OpenAI 多模态 list 格式。

        ``studio_sandbox_paths``：Studio 模式下文件引用 → 沙盒可读路径的映射；
        命中时提示模型直接用工作区路径读取（沙盒无法解析 file:// / upload:// 引用）。
        传 ``None`` 表示普通聊天（附件由 chat_sandbox_execute 执行前注入轻量沙盒）。
        """
        if not messages:
            return messages
        target_index = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"),
            default=-1,
        )
        if target_index == -1:
            return messages

        target = messages[target_index]
        base_text = str(target.get("content", ""))

        # attachments 可能是 Pydantic ChatAttachment 对象列表，统一转成 dict
        attachment_dicts: list[dict[str, Any]] = [
            att.model_dump() if hasattr(att, "model_dump") else dict(att)
            for att in (attachments or [])
        ]

        has_image = any(
            att.get("type") == "image"
            or is_image_attachment(
                str(att.get("mime_type", "")), str(att.get("name", ""))
            )
            for att in attachment_dicts
        )

        async def _build_snippets(att: dict[str, Any]) -> list[str]:
            """为单个附件生成文本提示片段。"""
            file_id = att.get("file_id", "")
            if att.get("type") == "directory":
                ref = file_id if "://" in file_id else ""
                sandbox_path = (studio_sandbox_paths or {}).get(ref)
                if sandbox_path:
                    return [
                        f"[目录: {att.get('name', '')}/，已只读引入当前 Session：{sandbox_path}。"
                        "请先用 workspace_list 分页列举，再按需用 workspace_read 读取具体文件；"
                        "不要修改 input/ 或访问目录之外的路径。]"
                    ]
                return [
                    f"[目录 {att.get('name', '')}/ 未获得可读取工作区权限，不能按名称推测或访问路径。]"
                ]
            text = await ChatRuntimeSupport._read_attachment_text(att)
            max_len = 8000
            snippets: list[str] = []
            if file_id:
                # file_id 可能已带 scheme（file://uuid 或 upload://hex）；无 scheme 时按上传文件处理
                ref = file_id if "://" in file_id else f"upload://{file_id}"
                sandbox_path = (studio_sandbox_paths or {}).get(ref)
                if sandbox_path:
                    # Studio：文件已挂载进沙盒工作区，指示模型按文件系统路径读取
                    snippets.append(
                        f"[文件: {att.get('name', '')}，已引入沙盒工作区 {sandbox_path}。"
                        f"在 sandbox_execute 代码或工作区工具中请直接使用该路径读取，"
                        f"不要使用 file:// / upload:// 引用（沙盒内无法解析）]"
                    )
                elif studio_sandbox_paths is None:
                    # 普通聊天：轻量沙盒执行前由 chat_sandbox_execute 注入附件
                    snippets.append(
                        f"[文件: {att.get('name', '')}，file_id: {ref}，"
                        f'可用 workspace_read_file(file_id="{ref}") 读取内容，'
                        f"或在其它工具参数中直接引用该 file_id；"
                        f"调用 chat_sandbox_execute 执行代码时，该文件会自动注入沙盒 "
                        f"/workspace/input/ 目录（真实路径见工具结果的 input_files）]"
                    )
                else:
                    # Studio：文件未挂载进工作区，沙盒代码在文件系统中找不到它，
                    # 不能再提 chat_sandbox_execute 自动注入（Studio 模式该工具不挂载）。
                    snippets.append(
                        f"[文件: {att.get('name', '')}，file_id: {ref}，"
                        f"该文件未挂载进沙盒工作区，沙盒内无法按文件路径访问；"
                        f'请用 workspace_read_file(file_id="{ref}") 在宿主侧读取内容]'
                    )
            if text:
                snippet = text[:max_len] + ("\n...（已截断）" if len(text) > max_len else "")
                snippets.append(f"[文件内容预览: {att.get('name', '')}]\n{snippet}")
            if not snippets:
                snippets.append(f"[文件 {att.get('name', '')} 读取失败或为空]")
            return snippets

        new_messages = list(messages)

        if not has_image:
            # 纯文本附件：拼成字符串，兼容性最好
            parts = [base_text]
            for att in attachment_dicts:
                snippets = await _build_snippets(att)
                parts.append("\n\n".join(snippets))
            new_messages[target_index] = {**target, "content": "\n\n".join(parts)}
            return new_messages

        # 含图片：使用 OpenAI 多模态 list 格式
        content: list[dict[str, Any]] = [{"type": "text", "text": base_text}]
        for att in attachment_dicts:
            att_type = att.get("type", "file")
            mime = att.get("mime_type", "")
            if att_type == "image" or is_image_attachment(mime, str(att.get("name", ""))):
                data_url = await ChatRuntimeSupport._read_attachment_data_url(att)
                if data_url:
                    content.append({"type": "image_url", "image_url": {"url": data_url}})
                else:
                    content.append(
                        {
                            "type": "text",
                            "text": f"\n\n[图片 {att.get('name', '')} 读取失败]",
                        }
                    )
            else:
                snippets = await _build_snippets(att)
                content.append({"type": "text", "text": "\n\n" + "\n\n".join(snippets)})

        new_messages[target_index] = {**target, "content": content}
        return new_messages

    @staticmethod
    def _resolve_attachment_path(att_url: str) -> str | None:
        """把聊天附件 URL 解析为本地路径，非本地上传或越权则返回 None。"""
        prefix = "/api/v1/files/chat-upload/"
        if not att_url.startswith(prefix):
            return None
        rest = att_url[len(prefix) :]
        parts = rest.split("/", 1)
        if len(parts) != 2:
            return None
        user_id, filename = parts
        filename = Path(filename).name
        from cygnusx.infrastructure.config.storage_config import get_user_chat_upload_dir

        path = get_user_chat_upload_dir(user_id) / filename
        if path.is_file():
            return str(path)
        return None

    @staticmethod
    def _is_internal_url(url: str) -> bool:
        """禁止访问内网、回环、链路本地、metadata 等地址，防止 SSRF。"""
        if not url:
            return True
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return True
        host = parsed.hostname
        if not host:
            return True
        if host == "169.254.169.254":
            return True
        try:
            addr = ipaddress.ip_address(host)
            return (
                addr.is_loopback
                or addr.is_private
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_reserved
            )
        except ValueError:
            # 域名：放行；如需更严格可再校验是否解析到内网
            return False

    @staticmethod
    async def _read_attachment_data_url(att: dict[str, Any]) -> str:
        """读取附件并返回 base64 data URL；TIFF/BMP/ICO 先转 PNG 再交给视觉模型。"""
        import base64

        att_url = att.get("url", "")
        mime = str(att.get("mime_type") or "application/octet-stream")
        filename = str(att.get("name", ""))
        suffix = Path(filename).suffix.lower()
        local_path = ChatRuntimeSupport._resolve_attachment_path(att_url)
        try:
            if local_path:
                async with await anyio.open_file(local_path, "rb") as f:
                    data = await f.read()
            else:
                if ChatRuntimeSupport._is_internal_url(att_url):
                    logger.warning(f"拒绝读取内网/非法附件 URL: {att_url}")
                    return ""
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                    resp = await client.get(att_url)
                    resp.raise_for_status()
                    data = resp.content
            if suffix in _IMAGE_CONVERT_SUFFIXES or mime in _IMAGE_CONVERT_MIME_TYPES:
                converted = await anyio.to_thread.run_sync(_convert_image_to_png, data)
                if not converted:
                    logger.warning(f"图片转 PNG 失败，已跳过: {filename}")
                    return ""
                data = converted
                mime = "image/png"
            encoded = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{encoded}"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取附件失败 {att.get('name')}: {e}")
            return ""

    @staticmethod
    async def _read_attachment_text(att: dict[str, Any]) -> str:
        """读取文本类附件；Office/压缩文本/结构文件走专用抽取，避免二进制乱码注入模型。"""
        att_url = att.get("url", "")
        local_path = ChatRuntimeSupport._resolve_attachment_path(att_url)
        mime_type = str(att.get("mime_type", "")).lower()
        filename = str(att.get("name", ""))
        suffix = Path(filename).suffix.lower()
        is_pdf = mime_type == "application/pdf" or suffix == ".pdf"
        is_docx = is_docx_attachment(mime_type, filename)
        is_excel = is_excel_attachment(mime_type, filename)
        is_pptx = is_pptx_attachment(mime_type, filename)
        compression = suffix if suffix in _COMPRESSION_SUFFIXES else ""
        inner_suffix = compressed_text_inner_suffix(filename)

        def _extract_office(source: Any) -> str:
            if is_docx:
                return extract_docx_text(source)
            if is_excel:
                return extract_xlsx_text(source)
            if is_pptx:
                return extract_pptx_text(source)
            return ""

        def _extract_special(source: Any) -> str | None:
            if suffix == ".eml":
                return extract_eml_text(source) or read_text_preview(source)
            if suffix in _STRUCTURE_SUFFIXES:
                return extract_structure_summary(source, filename) or read_text_preview(source)
            if suffix == ".biom":
                return extract_biom_text(source)
            if suffix in _CONTAINER_SUFFIXES:
                return extract_data_container_summary(source, filename)
            if suffix == ".xlsb":
                return (
                    "# Excel 二进制工作簿（.xlsb）\n"
                    "- 该格式无法在线抽取文本；请在沙盒中转换为 .xlsx 后读取。"
                )
            if compression:
                return decompress_text_preview(source, compression)[0] if inner_suffix else ""
            return None

        try:
            if local_path:
                if is_pdf:
                    return await ChatRuntimeSupport._extract_pdf_text(local_path)
                if is_docx or is_excel or is_pptx:
                    return await anyio.to_thread.run_sync(_extract_office, local_path)
                special = await anyio.to_thread.run_sync(_extract_special, local_path)
                if special is not None:
                    return special
                if suffix in _BINARY_ATTACHMENT_SUFFIXES:
                    return ""
                return await anyio.to_thread.run_sync(read_text_preview, local_path)
            if ChatRuntimeSupport._is_internal_url(att_url):
                logger.warning(f"拒绝读取内网/非法附件 URL: {att_url}")
                return ""
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(att_url)
                resp.raise_for_status()
                if is_pdf:
                    import tempfile

                    pdf_suffix = Path(filename).suffix or ".pdf"
                    with tempfile.NamedTemporaryFile(suffix=pdf_suffix, delete=False) as tmp:
                        tmp.write(resp.content)
                        tmp_path = tmp.name
                    try:
                        return await ChatRuntimeSupport._extract_pdf_text(tmp_path)
                    finally:
                        await anyio.Path(tmp_path).unlink(missing_ok=True)
                if is_docx or is_excel or is_pptx:
                    return await anyio.to_thread.run_sync(_extract_office, resp.content)
                special = await anyio.to_thread.run_sync(_extract_special, resp.content)
                if special is not None:
                    return special
                if suffix in _BINARY_ATTACHMENT_SUFFIXES:
                    return ""
                return read_text_preview(resp.content)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取文本附件失败 {att.get('name')}: {e}")
            return ""

    @staticmethod
    async def _extract_pdf_text(file_path: str) -> str:
        """提取聊天 PDF 的分页文本，避免把二进制内容按 UTF-8 注入模型。"""
        from cygnusx.application.services.pdf_processor import (
            CHAT_ATTACHMENT_CONFIG,
            PDFProcessor,
        )

        processor = PDFProcessor(config=CHAT_ATTACHMENT_CONFIG)
        result = await processor.process(file_path)
        return result.content

    async def _resolve_model(self, model_id: uuid.UUID) -> AIProviderConfigModel | None:
        """按 ID 解析已启用的模型配置。"""
        result = await self._db.execute(
            select(AIProviderConfigModel).where(
                AIProviderConfigModel.id == model_id,
                AIProviderConfigModel.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def _apply_usage_to_session(
        self,
        message_id: str,
        usage: dict[str, Any] | None,
    ) -> None:
        """把 LLM 返回的 usage 累加到会话 total_tokens，并写入消息 metadata。"""
        normalized = normalize_token_usage(usage)
        if not normalized:
            return
        try:
            total = int(normalized.get("total_tokens") or 0)
            if total <= 0:
                return
            msg_result = await execute_read_with_retry(
                self._db,
                select(ChatMessageModel).where(ChatMessageModel.message_id == message_id)
            )
            msg = msg_result.scalar_one_or_none()
            if not msg:
                return
            self._record_context_usage(
                str(msg.session_id),
                getattr(self, "_active_model_config", None),
                int(normalized.get("prompt_tokens") or 0),
            )
            # Store the canonical usage shape so historical messages and the
            # statistics endpoint use the same provider-independent counters.
            msg_metadata = dict(msg.metadata_json or {})
            msg_metadata["usage"] = normalized
            msg.metadata_json = msg_metadata
            session_result = await self._db.execute(
                select(ChatSessionModel).where(ChatSessionModel.session_id == msg.session_id)
            )
            session = session_result.scalar_one_or_none()
            if session:
                session.total_tokens += total
                await self._deduct_ai_cookies(session, total, message_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"累加 token 用量失败: {e}")

    async def _ensure_cookie_balance(self, user_id: str) -> str | None:
        """AI 对话准入闸门：饼干余额不足时返回错误文案，放行返回 None。"""
        settings = get_settings()
        if not settings.enable_cookie_system:
            return None
        try:
            from cygnusx.application.services.cookie_service import CookieService

            balance = await CookieService(self._db).check_balance(uuid.UUID(user_id))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"AI 对话饼干余额检查失败，放行: {e}")
            return None
        if balance > 0:
            return None
        rate = settings.ai_token_cookie_rate
        return (
            f"饼干余额不足，无法使用 AI 助手（每 1K tokens 消耗 {rate} 🥫）。"
            "请先通过提交分析任务赚取饼干后再试。"
        )

    async def _deduct_ai_cookies(
        self, session: ChatSessionModel, tokens: int, message_id: str
    ) -> None:
        """按 ai_token_cookie_rate 🥫/1K tokens 从会话属主账户扣减饼干。"""
        settings = get_settings()
        if not settings.enable_cookie_system or tokens <= 0:
            return
        try:
            from cygnusx.application.services.cookie_service import CookieService

            await CookieService(self._db).spend_ai_tokens(
                user_id=uuid.UUID(str(session.user_id)),
                tokens=tokens,
                source_id=message_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"AI 对话饼干扣减失败: {e}")

    async def _record_skill_invocation(
        self,
        *,
        skill_meta: dict[str, Any],
        status: str,
        duration_ms: float,
        summary: str,
        error: str,
        tool_name: str = USE_SKILL_TOOL_NAME,
        session_id: str,
        message_id: Any,
        user_id: str | None,
    ) -> None:
        """落库一条技能调用记录（绝不阻断对话流：任何失败只记日志）。"""
        try:
            from cygnusx.application.services.skill_service import SkillService

            def _to_uuid(value: Any) -> uuid.UUID | None:
                try:
                    return uuid.UUID(str(value)) if value else None
                except (ValueError, AttributeError, TypeError):
                    return None

            await SkillService(self._db).record_invocation(
                skill_id=skill_meta.get("skill_id"),
                skill_name=str(skill_meta.get("name") or ""),
                skill_version=str(skill_meta.get("version") or "") or None,
                source=str(skill_meta.get("source") or ""),
                tool_name=tool_name,
                status=status,
                duration_ms=duration_ms,
                summary=summary,
                error=error,
                session_id=_to_uuid(session_id),
                message_id=_to_uuid(message_id),
                user_id=_to_uuid(user_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("技能调用记录落库失败（忽略）: {}", exc)

    async def _execute_skill_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        skills: list[Any],
        skill_pins: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """技能工具执行入口（带 Trace/Log/Metrics 埋点）。"""
        skill_key = str(args.get("skill_id") or args.get("name") or "").strip()
        tracer = get_tracer("cygnusx.chat")
        with tracer.start_as_current_span(
            "skill.execute",
            attributes={"skill.tool_name": tool_name, "skill.skill_id": skill_key},
        ) as span:
            start = time.perf_counter()
            status = "success"
            try:
                result = await self._execute_skill_tool_inner(
                    tool_name, args, skills, skill_pins=skill_pins
                )
                if not result.get("success"):
                    status = "error"
                return result
            except Exception as exc:  # noqa: BLE001
                status = "error"
                span.record_exception(exc)
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                attrs = {"skill.tool_name": tool_name, "skill.status": status}
                span.set_attribute("skill.status", status)
                span.set_attribute("skill.duration_ms", round(duration_ms, 2))
                try:
                    _skill_count.add(1, attrs)
                    _skill_duration.record(duration_ms, attrs)
                except Exception:  # noqa: BLE001
                    pass
                logger.bind(
                    event="skill.execute",
                    tool_name=tool_name,
                    skill_id=skill_key,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                ).info("skill.execute completed")

    async def _execute_skill_tool_inner(
        self,
        tool_name: str,
        args: dict[str, Any],
        skills: list[Any],
        skill_pins: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """技能渐进式披露内部工具：

        - use_skill（L2）：返回已挂载技能的 SKILL.md 正文。会话 pin 优先（会话启动时
          锁定的版本快照），其次磁盘优先，最后 DB prompt 兜底
        - skill_resource（L3）：按需读取技能 references/assets 文件，代码不进上下文
        """
        from cygnusx.infrastructure.skills import skill_store

        skill_key = str(args.get("skill_id") or args.get("name") or "").strip()
        skill = next((s for s in skills if s.skill_id == skill_key or s.name == skill_key), None)
        if skill is None:
            mounted = "、".join(s.skill_id for s in skills) or "无"
            return {
                "success": False,
                "error": f"技能 '{skill_key}' 未挂载到该助手（已挂载：{mounted}）",
            }

        if tool_name == USE_SKILL_TOOL_NAME:
            body: str | None = None
            pinned_from: str | None = None
            pinned_rev = (skill_pins or {}).get(skill.skill_id)
            if pinned_rev:
                # 会话 pin：读取会话启动时锁定 revision 的快照正文，
                # 会话中途升级/回滚不影响进行中的任务。
                # 工具执行可能在 LangGraph 图 task 内运行，版本快照为已提交
                # 数据，用独立会话读取，避免与消费协程并发使用请求级 session。
                try:
                    from cygnusx.infrastructure.database.models.skill import (
                        SkillVersionModel,
                    )

                    async with get_session_factory()() as pin_db:
                        snap = (
                            await pin_db.execute(
                                select(SkillVersionModel).where(
                                    SkillVersionModel.skill_id == skill.skill_id,
                                    SkillVersionModel.revision == int(pinned_rev),
                                )
                            )
                        ).scalar_one_or_none()
                    if snap and (snap.prompt or "").strip():
                        body = snap.prompt
                        pinned_from = f"r{snap.revision}"
                except Exception as pin_exc:  # noqa: BLE001
                    logger.warning("读取 pin 版本失败（回落当前内容）: {}", pin_exc)
            if body is None:
                body = skill_store.read_skill_body(skill.skill_id) or (skill.prompt or "")
            if not body.strip():
                return {"success": False, "error": f"技能 '{skill.name}' 暂无指令正文"}
            resources = skill_store.list_skill_files(skill.skill_id)
            return {
                "success": True,
                "result": {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "instructions": body,
                    "pinned_revision": pinned_from,
                    "resources": resources or None,
                    "resource_hint": (
                        "正文引用的 references/assets 文件请用 skill_resource 工具读取"
                        if resources
                        else None
                    ),
                },
            }

        if tool_name == SKILL_RESOURCE_TOOL_NAME:
            path = str(args.get("path") or "").strip()
            if not path:
                return {"success": False, "error": "缺少 path 参数"}
            ok, msg, content = skill_store.read_skill_resource(skill.skill_id, path)
            if not ok or content is None:
                return {"success": False, "error": msg}
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                return {
                    "success": True,
                    "result": {
                        "path": path,
                        "note": "该资源为二进制文件，无法作为文本读取",
                    },
                }
            return {"success": True, "result": {"path": path, "content": text}}

        return {"success": False, "error": f"未知技能工具: {tool_name}"}

    async def _web_search(
        self, arguments: dict[str, Any], *, model_config: Any | None = None
    ) -> dict[str, Any]:
        """执行默认联网搜索服务商，并返回统一结果结构。"""
        query = arguments.get("query", "")
        top_n = int(arguments.get("top_n", 5))
        if not query.strip():
            return {"success": False, "error": "缺少搜索关键词"}
        try:
            result = await self._optimized_web_search(query, top_n=top_n, model_config=model_config)
            return {"success": True, "result": result}
        except Exception as exc:  # noqa: BLE001
            logger.warning("联网搜索工具调用失败: %s", exc)
            return {"success": False, "error": "联网搜索失败，已跳过搜索结果"}

    async def _optimized_web_search(
        self,
        query: str,
        *,
        top_n: int = 8,
        model_config: Any | None = None,
    ) -> dict[str, Any]:
        """Run cached query refinement, multi-query retrieval, dedupe and reranking."""
        from cygnusx.application.services.chat_service import _extract_route_json

        optimizer = ResearchSearchOptimizer()
        fallback_queries = build_research_queries(query)["web_queries"]

        async def refine(value: str) -> dict[str, Any]:
            if model_config is None:
                return {"queries": []}
            answer = ""
            async for item in provider_manager.chat_stream(
                config=model_config,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"用户问题：{value}\n\n"
                            "请生成 2-4 条英文联网检索式。每条保留 2-4 个最关键概念或短语，"
                            "用 AND/OR 连接；优先保留实体、主题、任务目标和时效条件。"
                            "不要解释，不添加网站域名。严格返回 JSON："
                            '{"queries":["...","..."]}。'
                        ),
                    }
                ],
                system_prompt="你只负责精炼联网检索式，不回答用户问题。",
                temperature=0.1,
                max_tokens=240,
                tools=None,
                deep_thinking=False,
            ):
                if item.type == "text" and not item.metadata.get("is_reasoning"):
                    answer += item.content
            parsed = _extract_route_json(answer) or {}
            return {"queries": parsed.get("queries") or []}

        refinement = await optimizer.refine_queries(
            query,
            fallback_queries=fallback_queries,
            refiner=refine if model_config is not None else None,
        )
        candidates: list[dict[str, Any]] = []
        errors: list[str] = []
        # 工具执行可能在 LangGraph 图 task 内运行，与消费协程共享请求级
        # session 会并发触发 flush；搜索源配置是已提交数据，用独立会话读取。
        try:
            async with get_session_factory()() as search_db:
                for refined_query in refinement["queries"][:4]:
                    try:
                        candidates.extend(
                            await SearchProviderService(search_db).search_default(
                                refined_query,
                                max(5, min(int(top_n), 12)),
                            )
                        )
                    except Exception as exc:  # noqa: BLE001 - partial query success is useful
                        errors.append(str(exc)[:300])
        except Exception as exc:  # noqa: BLE001 - provider config read failure
            errors.append(str(exc)[:300])
        if not candidates and errors:
            raise RuntimeError(errors[0])
        results = await optimizer.rerank(query, candidates, limit=max(5, min(int(top_n), 8)))
        payload: dict[str, Any] = {
            "query": query,
            "queries": refinement["queries"],
            "query_refinement": refinement,
            "results": results,
            "reranked": True,
        }
        if errors:
            payload["partial_errors"] = errors
        return payload

    async def _knowledge_search_chat(
        self, arguments: dict[str, Any], *, project_id: str | None = None
    ) -> dict[str, Any]:
        """普通聊天的知识库检索：复用 Studio 工具实现（只检索已发布文档的当前修订）。"""
        from cygnusx.application.services.studio_tools import _knowledge_search

        try:
            # 工具执行可能在 LangGraph 图 task 内运行，知识库为已提交数据，
            # 用独立会话读取，避免与消费协程并发使用请求级 session。
            async with get_session_factory()() as kb_db:
                return await _knowledge_search(arguments, kb_db, project_id=project_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识库检索工具调用失败: %s", exc)
            return {"success": False, "error": "知识库检索失败，已跳过"}

    # --- 助手管理 ---
