# 可复现报告 Phase 2 实施记录

## 结论

本轮实现了科研交付包的数据契约、构建器、ZIP 安全验证、报告中心 API 和前端入口。交付过程是离线整理：不重跑 RNA、不替换冻结快照、不把哈希完整性描述成科学结论正确性。真实 RNA/PostgreSQL/Celery/对象存储现场验收仍未完成。

## 实施内容

| 区域 | 实际实现 |
|---|---|
| BioReport adapter | `application/services/bioreport_adapter.py`；受控 CLI、HTML 复用、PDF/HTML 输出约束、AI 明确关闭；交付构建仅在存在 owner 已登记 BioReport 配置时尝试科学 PDF |
| 审计 PDF | `application/services/report_audit_pdf_renderer.py`；冻结 HTML 经 Pandoc/Typst 转换并按 SHA-256 登记为 `ReportFile(type=pdf)` |
| 交付契约 | `application/schemas/report_delivery.py`；版本化 `cygnusx.evidence_manifest.v1` |
| 交付构建 | `application/services/research_delivery_service.py`；README、Manifest、checksums、ZIP、缺失文件状态 |
| 完整性 | owner 文件授权、源文件 SHA/size 回读、ZIP 路径/符号链接/解压大小检查、Manifest 文件校验、文件数和大小上限 |
| 报告服务 | `ReportService.build_delivery_package`；科学报告与最新执行证据报告合并，生成 `report_kind=delivery` 版本 |
| HTTP/UI | `POST /reports/{id}/delivery`、报告预览入口、delivery 类型展示、统一鉴权下载 |

## BioReport 核验

本地 BioReport 仓库的核验信息为版本 `2.0.0`、源码提交 `cb2911a`。CLI 支持 HTML/PDF；PDF 使用 single layout。当前没有可安全引用的 CygnusX 生产镜像 digest，也没有启动真实 BioReport 容器执行 RNA 科学报告，因此科学 PDF 生产环境仍未验收。审计 PDF 已在当前环境以 Pandoc/Typst 生成有效 PDF 字节，不能将该本地 smoke test 等同部署验收。

## 交付语义

包状态只有 `complete` 和 `partial`。`partial` 表示某些登记文件不可用，并不表示分析失败。README 明确区分 Scientific Report、Reproducibility Record、Snapshot 和复现限制。快照 digest 是内容一致性校验，不是签名；`validation_status=validated` 只表示本地构建器完成结构/字节校验。

## 测试与限制

新增单测覆盖缺失文件、中文内容、ZIP slip、机器可读 Manifest、篡改拒绝、审计 PDF 字节、外部资源/符号链接拒绝和 fake BioReport CLI。报告域 Phase 0/1/2 单元与隔离集成测试：78 passed；定向 Ruff、6 个变更 Python 文件的 mypy、迁移链检查通过。前端 `vue-tsc --noEmit`、报告相关 Vitest（8 passed）和 `npm run build` 通过。全仓 mypy 当前报 1028 个存量错误，分布于 230 个文件；未据此声称全仓类型门禁通过。完整仓库 pytest、生产组件和真实浏览器操作仍需在授权环境执行。

未发现 `docs/audits/reproducible-report-phase1-live-validation.md`；Phase 1.5 现场验收因此保持未接受状态。后续必须使用授权的独立 PostgreSQL、broker、对象存储、真实已结束 RNA Task 和固定 BioReport 镜像，完成 Task → 证据 → PDF/HTML → ZIP → 下载校验闭环。

## 验收状态

- `CODE COMPLETE`：Phase 2 代码、隔离测试、前端入口和所需设计/实施文档已完成；科学 PDF 仅在可用的已登记 BioReport 配置和渲染器条件下生成，缺失时诚实产出 partial 包。
- `LIVE VALIDATED`: **NO**。未执行真实 RNA Task、授权 PostgreSQL 并发/迁移、现场 Celery、对象存储或浏览器下载闭环。
- `PRODUCTION READY`: **NO**。生产 BioReport 镜像 digest、输入配置/资源映射和以上 live 验收均未确认。
