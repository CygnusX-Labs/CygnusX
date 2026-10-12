# CygnusX Frontend v2.0 - W08 变更报告

- 状态：部分完成。下载进度、模拟下载按钮和参考数据库版本提示已修正；完整输入/深链/资源状态及浏览器验收待补。
- 基线与保护：沿用 W00 基线，保留起点五个脏子模块、原规范及 W01–W07 改动。
- 采用规范：实施规范 §5.5–§5.6、§19 W08；活动 `CygnusX_frontend.md` 页面约束。
- 实际修改：DownloadsView 的进度复用 `normalizeProgress()`，兼容 0–1 与 0–100；SRA 的“模拟下载验证”按钮实际提交既有 `dry_run: true` 字段，成功后进入真实任务详情。ReferenceGenomesView 的版本选择提示从“设为默认”改为“当前页面已选择”，展示区标明“当前查看版本”。
- 数据依据：后端 `DownloadRequest.dry_run` 仅支持 SRA，`DownloadService` 将其写入任务参数，worker 消费该字段；参考数据库版本选择当前只写本地 ref，没有服务端持久化。
- 兼容：下载来源、accession、目标目录、task id 深链、参考数据库 versionId/gene/go/kegg 深链均沿用现有协议。
- 自动验证：`npm run type-check`、`npm run build`、`git diff --check` 通过。未执行真实下载任务，模拟下载需要有后端的手工 E2E。
- 视觉证据：未取得；浏览器限制见 W00。需检查表单、状态、版本资源和移动视口。
- 风险与可逆性：Dry Run 现在会创建一条真实任务记录，但 worker 不下载文件；这是后端现有语义。回滚本批只需恢复 DownloadsView 和 ReferenceGenomesView 本批差异。
- 下一推荐包：W09；W00–W08 浏览器证据与 S1–S10 仍待补。
