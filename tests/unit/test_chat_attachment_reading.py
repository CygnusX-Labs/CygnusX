from pathlib import Path
from types import SimpleNamespace

import pytest

from cygnusx.application.services.chat.runtime_support import ChatRuntimeSupport
from cygnusx.application.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_read_attachment_text_extracts_local_pdf(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF fake")
    # 方法体内部按 ChatRuntimeSupport 显式引用解析，补丁必须打在定义类上
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(pdf_path)),
    )
    async def fake_extract_pdf_text(source: str) -> str:
        return f"parsed:{Path(source).name}"

    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_extract_pdf_text",
        staticmethod(fake_extract_pdf_text),
    )

    text = await ChatService._read_attachment_text(
        {
            "name": "paper.pdf",
            "mime_type": "application/pdf",
            "url": "/api/v1/files/chat-upload/user/paper.pdf",
        }
    )

    assert text == "parsed:paper.pdf"


@pytest.mark.asyncio
async def test_extract_pdf_text_delegates_to_pdf_processor(monkeypatch, tmp_path: Path) -> None:
    """验证 _extract_pdf_text 已迁移至 PDFProcessor。"""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF fake")

    async def fake_process(self, file_path: str):
        return SimpleNamespace(
            content=f"processed:{Path(file_path).name}",
            metadata=SimpleNamespace(total_pages=2),
        )

    monkeypatch.setattr(
        "cygnusx.application.services.pdf_processor.PDFProcessor.process",
        fake_process,
    )

    text = await ChatService._extract_pdf_text(str(pdf_path))

    assert text == "processed:paper.pdf"


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    """构造最小可解析的 docx（OOXML zip），正文为若干段落。"""
    import io
    import zipfile

    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document><w:body>{body}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_extract_docx_text_reads_paragraphs_and_entities(tmp_path: Path) -> None:
    from cygnusx.application.services.chat.runtime_support import extract_docx_text

    raw = _make_docx_bytes([">sp1", "ATGCGT", "A&amp;B 混合"])
    docx_path = tmp_path / "MDH2序列.docx"
    docx_path.write_bytes(raw)

    assert extract_docx_text(str(docx_path)) == ">sp1\nATGCGT\nA&B 混合"
    # bytes 形态（远程附件场景）同样可解析
    assert extract_docx_text(raw) == ">sp1\nATGCGT\nA&B 混合"
    # 非 zip 内容返回空串而不是抛异常
    assert extract_docx_text(b"not a zip") == ""


@pytest.mark.asyncio
async def test_read_attachment_text_extracts_local_docx(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docx_path = tmp_path / "MDH2序列.docx"
    docx_path.write_bytes(_make_docx_bytes([">MDH2_human", "MABC..."]))
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(docx_path)),
    )

    async def run_sync_inline(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("anyio.to_thread.run_sync", run_sync_inline)

    text = await ChatService._read_attachment_text(
        {
            "name": "MDH2序列.docx",
            "mime_type": (
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            "url": "/api/v1/files/chat-upload/user/MDH2序列.docx",
        }
    )

    assert text == ">MDH2_human\nMABC..."


def _make_xlsx_bytes() -> bytes:
    """构造最小可解析的 xlsx（OOXML zip），含共享字符串与数值/内联字符串。"""
    import io
    import zipfile

    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<workbook xmlns="{main_ns}" xmlns:r="{rel_ns}">'
        '<sheets><sheet name="差异基因" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Relationships xmlns="{pkg_ns}">'
        '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    shared = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<sst xmlns="{main_ns}">'
        "<si><t>gene</t></si><si><t>log2FC</t></si><si><t>TP53</t></si>"
        "</sst>"
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="{main_ns}"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>2.5</v></c>'
        '<c r="C2" t="inlineStr"><is><t>up</t></is></c></row>'
        "</sheetData></worksheet>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", rels)
        zf.writestr("xl/sharedStrings.xml", shared)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def _make_pptx_bytes() -> bytes:
    """构造最小可解析的 pptx（OOXML zip），含一张幻灯片。"""
    import io
    import zipfile

    drawing_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    slide = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        f'xmlns:a="{drawing_ns}"><p:cSld><p:spTree>'
        f"<a:t>分析结果</a:t><a:t>差异基因 128 个</a:t>"
        "</p:spTree></p:cSld></p:sld>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", slide)
    return buf.getvalue()


def test_extract_xlsx_text_reads_sheets_and_cells(tmp_path: Path) -> None:
    from cygnusx.application.services.chat.runtime_support import extract_xlsx_text

    raw = _make_xlsx_bytes()
    xlsx_path = tmp_path / "deg.xlsx"
    xlsx_path.write_bytes(raw)

    expected = "# 工作表: 差异基因\ngene\tlog2FC\nTP53\t2.5\tup"
    assert extract_xlsx_text(str(xlsx_path)) == expected
    assert extract_xlsx_text(raw) == expected
    assert extract_xlsx_text(b"not a zip") == ""


def test_extract_xlsx_text_rejects_dtd_entities() -> None:
    import io
    import zipfile

    from cygnusx.application.services.chat.runtime_support import extract_xlsx_text

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            '<!DOCTYPE x [<!ENTITY a "b">]><workbook/>',
        )
    assert extract_xlsx_text(buf.getvalue()) == ""


def test_extract_pptx_text_reads_slides(tmp_path: Path) -> None:
    from cygnusx.application.services.chat.runtime_support import extract_pptx_text

    raw = _make_pptx_bytes()
    pptx_path = tmp_path / "report.pptx"
    pptx_path.write_bytes(raw)

    assert extract_pptx_text(str(pptx_path)) == "# 幻灯片 1\n分析结果\n差异基因 128 个"
    assert extract_pptx_text(raw) == "# 幻灯片 1\n分析结果\n差异基因 128 个"


@pytest.mark.asyncio
async def test_read_attachment_text_extracts_local_xlsx(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xlsx_path = tmp_path / "deg.xlsx"
    xlsx_path.write_bytes(_make_xlsx_bytes())
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(xlsx_path)),
    )

    async def run_sync_inline(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("anyio.to_thread.run_sync", run_sync_inline)

    text = await ChatService._read_attachment_text(
        {
            "name": "deg.xlsx",
            "mime_type": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            "url": "/api/v1/files/chat-upload/user/deg.xlsx",
        }
    )

    assert "gene\tlog2FC" in text
    assert "TP53\t2.5\tup" in text


@pytest.mark.asyncio
async def test_workspace_read_file_extracts_xlsx(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """@ 引用的 Excel 走 workspace_read_file 时也应返回可读表格文本。"""
    from cygnusx.infrastructure.mcp import presets

    xlsx_path = tmp_path / "deg.xlsx"
    xlsx_path.write_bytes(_make_xlsx_bytes())
    meta = {
        "file_id": "abc123",
        "ref": "upload://abc123",
        "name": "deg.xlsx",
        "size": xlsx_path.stat().st_size,
        "size_human": "1KB",
        "file_type": "chat_upload",
        "directory": "workspace/chat-uploads",
        "created_at": None,
    }

    async def fake_resolve(_user_id: str, _file_id: str, _db: object):
        return xlsx_path, meta

    class _DummySession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr(presets, "_resolve_workspace_file", fake_resolve)
    monkeypatch.setattr(
        "cygnusx.infrastructure.database.session.get_session_factory",
        lambda: _DummySession,
    )

    result = await presets._workspace_read_file({"file_id": "upload://abc123"}, user_id="u")
    assert "gene\tlog2FC" in result["content"]
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_read_attachment_text_does_not_decode_legacy_xls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xls_path = tmp_path / "legacy.xls"
    xls_path.write_bytes(b"\xd0\xcf\x11\xe0not-a-text-file")
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(xls_path)),
    )

    text = await ChatService._read_attachment_text(
        {
            "name": "legacy.xls",
            "mime_type": "application/vnd.ms-excel",
            "url": "/api/v1/files/chat-upload/user/legacy.xls",
        }
    )

    assert text == ""


def _patch_inline_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_sync_inline(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("anyio.to_thread.run_sync", run_sync_inline)


@pytest.mark.asyncio
async def test_read_attachment_text_decompresses_gzip_csv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import gzip

    gz_path = tmp_path / "counts.csv.gz"
    gz_path.write_bytes(gzip.compress(b"gene,count\nTP53,10\n"))
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(gz_path)),
    )
    _patch_inline_threads(monkeypatch)

    text = await ChatService._read_attachment_text(
        {
            "name": "counts.csv.gz",
            "mime_type": "application/gzip",
            "url": "/api/v1/files/chat-upload/user/counts.csv.gz",
        }
    )

    assert text == "gene,count\nTP53,10\n"


@pytest.mark.asyncio
async def test_read_attachment_text_extracts_eml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    eml_path = tmp_path / "mail.eml"
    eml_path.write_bytes(
        b"Subject: RNA result\r\nFrom: lab@example.org\r\n"
        b"MIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
        b"Hello RNA"
    )
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(eml_path)),
    )
    _patch_inline_threads(monkeypatch)

    text = await ChatService._read_attachment_text(
        {
            "name": "mail.eml",
            "mime_type": "message/rfc822",
            "url": "/api/v1/files/chat-upload/user/mail.eml",
        }
    )

    assert "RNA result" in text
    assert "Hello RNA" in text


@pytest.mark.asyncio
async def test_read_attachment_text_summarizes_pdb(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pdb_path = tmp_path / "protein.pdb"
    pdb_path.write_bytes(
        b"ATOM      1  CA  ALA A   1      11.104   6.134  -6.504  1.00  0.00           C\n"
        b"END\n"
    )
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(pdb_path)),
    )
    _patch_inline_threads(monkeypatch)

    text = await ChatService._read_attachment_text(
        {
            "name": "protein.pdb",
            "mime_type": "chemical/x-pdb",
            "url": "/api/v1/files/chat-upload/user/protein.pdb",
        }
    )

    assert "结构文件" in text
    assert "链数: 1" in text
    assert "原子数: 1" in text


@pytest.mark.asyncio
async def test_read_attachment_text_summarizes_biom(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    biom_path = tmp_path / "table.biom"
    biom_path.write_text(
        '{"type":"OTU table","shape":[2,3],'
        '"rows":[{"id":"f1"}],"columns":[{"id":"s1"}],"data":[[0,1,2]]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(biom_path)),
    )
    _patch_inline_threads(monkeypatch)

    text = await ChatService._read_attachment_text(
        {
            "name": "table.biom",
            "mime_type": "application/octet-stream",
            "url": "/api/v1/files/chat-upload/user/table.biom",
        }
    )

    assert "BIOM 丰度表" in text
    assert "2 个特征 × 3 个样本" in text


@pytest.mark.asyncio
async def test_read_attachment_text_reports_hdf5_without_h5py(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h5_path = tmp_path / "data.h5"
    h5_path.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 64)
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(h5_path)),
    )
    _patch_inline_threads(monkeypatch)

    text = await ChatService._read_attachment_text(
        {
            "name": "data.h5",
            "mime_type": "application/x-hdf5",
            "url": "/api/v1/files/chat-upload/user/data.h5",
        }
    )

    assert "HDF5 数据文件" in text
    assert "h5py" in text


@pytest.mark.asyncio
async def test_read_attachment_text_notes_xlsb(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    xlsb_path = tmp_path / "legacy.xlsb"
    xlsb_path.write_bytes(b"not-a-workbook")
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(xlsb_path)),
    )
    _patch_inline_threads(monkeypatch)

    text = await ChatService._read_attachment_text(
        {
            "name": "legacy.xlsb",
            "mime_type": "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
            "url": "/api/v1/files/chat-upload/user/legacy.xlsb",
        }
    )

    assert "Excel 二进制工作簿" in text


@pytest.mark.asyncio
async def test_read_attachment_data_url_converts_tiff_to_png(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from PIL import Image

    tiff_path = tmp_path / "figure.tif"
    Image.new("I;16", (10, 10), 500).save(tiff_path, format="TIFF")
    monkeypatch.setattr(
        ChatRuntimeSupport,
        "_resolve_attachment_path",
        staticmethod(lambda _url: str(tiff_path)),
    )

    data_url = await ChatRuntimeSupport._read_attachment_data_url(
        {
            "name": "figure.tif",
            "mime_type": "image/tiff",
            "url": "/api/v1/files/chat-upload/user/figure.tif",
        }
    )

    assert data_url.startswith("data:image/png;base64,")


def test_extract_mat_summary_lists_variables(tmp_path: Path) -> None:
    from scipy.io import savemat

    from cygnusx.application.services.chat.runtime_support import (
        extract_data_container_summary,
    )

    mat_path = tmp_path / "data.mat"
    savemat(mat_path, {"matrix": [[1, 2], [3, 4]]})

    text = extract_data_container_summary(str(mat_path), "data.mat")

    assert "变量数: 1" in text
    assert "matrix" in text


@pytest.mark.asyncio
async def test_workspace_read_file_decompresses_gzip_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import gzip

    from cygnusx.infrastructure.mcp import presets

    gz_path = tmp_path / "counts.csv.gz"
    gz_path.write_bytes(gzip.compress(b"gene,count\nTP53,10\n"))
    meta = {
        "file_id": "abc123",
        "ref": "upload://abc123",
        "name": "counts.csv.gz",
        "size": gz_path.stat().st_size,
        "size_human": "1KB",
        "file_type": "chat_upload",
        "directory": "workspace/chat-uploads",
        "created_at": None,
    }

    async def fake_resolve(_user_id: str, _file_id: str, _db: object):
        return gz_path, meta

    class _DummySession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr(presets, "_resolve_workspace_file", fake_resolve)
    monkeypatch.setattr(
        "cygnusx.infrastructure.database.session.get_session_factory",
        lambda: _DummySession,
    )

    result = await presets._workspace_read_file({"file_id": "upload://abc123"}, user_id="u")
    assert result["content"] == "gene,count\nTP53,10\n"
    assert result["truncated"] is False
