# RI095 RC02 PDF 与 Browser Runtime Enablement

Run ID: `rc01-rc02-20261017-attempt1`  
Commit: `d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33`

结论：**BLOCKED**。源码路径已核实，PDF 工具链和浏览器合规环境尚未形成可通过的真实证据。

## PDF 路径

当前项目报告通过 `BioReportAdapter` 调用 `report_audit_pdf_renderer.render_audit_pdf`，实际命令是 Pandoc HTML→Typst，指定 `Droid Sans Fallback` 为主、无衬线和等宽字体。该路径不要求 LaTeX 或 Quarto；它只转换已冻结的 HTML，不运行科研分析。证据来自 `src/cygnx/application/services/bioreport_adapter.py` 与 `report_audit_pdf_renderer.py`。

历史 Worker 版本探针显示同一验收镜像中 `pandoc`、`typst`、`fc-list` 均缺失，故 PDF 为 BLOCKED；本轮没有把宿主工具版本冒充 Worker 版本，也没有下载未授权工具。补齐时必须在受控 Worker 镜像中固定 Pandoc、Typst 和中文字体版本，记录镜像 digest、工具输出、模板/renderer 版本，并真实生成中文 PDF，逐页检查字体/分页、数据库 FileRecord SHA、磁盘 SHA 和 JWT 下载 SHA。PDF 失败必须证明 HTML 保留及 Job 恢复，HTML 成功不能替代 PDF 成功。

## Browser 环境

历史 runner 使用 Chromium sandbox 启动失败，证据明确为 `No usable sandbox`，宿主 AppArmor `apparmor_restrict_unprivileged_userns=1`；未使用 `--no-sandbox`。本轮当前 Docker daemon 也不可访问，不能重新启动合规 runner。解除条件是提供允许 Chromium 正常 user namespace/seccomp sandbox 的隔离 runner，并核实 Playwright npm 包与浏览器版本匹配。不得修改生产宿主权限或增加 `--no-sandbox`。

完整业务浏览器链路仍未执行：真实登录、ProjectDetail、Claim、报告 Job、HTML/PDF、M1、ZIP、SHA、刷新/离页/撤权/失败重试、键盘和窄屏检查均无本轮证据。`browser-preflight.cjs` 只是三宽度首页/启动探针，不是 PASS_E2E。

## RC02 状态

| 项目 | 状态 |
|---|---|
| 渲染器调用链核实 | PASS_STATIC |
| Worker Pandoc/Typst/字体 | BLOCKED：历史镜像缺失，当前 Docker 不可用 |
| 中文 PDF/分页/完整性 | BLOCKED |
| PDF 失败保留 HTML/恢复 | BLOCKED |
| Chromium sandbox 合规启动 | BLOCKED |
| Browser 业务 E2E | BLOCKED |

本轮没有生成 PDF、截图、trace、下载制品或伪造通过状态。生产默认门禁和旧报告/ZIP 不变。
