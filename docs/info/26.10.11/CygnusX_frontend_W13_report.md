# CygnusX Frontend v2.0 - W13 变更报告

- 状态：部分完成。文件预览补齐 PDF 和图片/PDF 打印，消息产物画廊现有媒体预览保留；真实 Blob/PDF/历史恢复浏览器验收待补。
- 基线与保护：沿用 W00 基线，保留起点五个脏子模块、原规范及 W01–W12 改动。
- 采用规范：实施规范 §5.11–§5.12、§19 W13；活动 `CygnusX_frontend.md` 的产物和文件协议。
- 核实的现状：MessageArtifactGallery 已支持图片/PDF 的 Blob 预览、放大、打印、下载，并处理产物 URL 来源更新；FilePreviewModal 仅支持图片和文本，未支持 PDF。
- 实际修改：FilePreviewModal 使用既有受鉴权 `/files/{id}/download` Blob 加载 PDF 到 iframe，图片/PDF 显示打印按钮并复用 `printBlobUrl()`；切换文件或关闭弹窗时用请求代次阻止旧响应覆盖当前预览并回收对象 URL。
- 兼容：file id、下载事件、文本 Monaco 预览、25MB 限额和不支持格式的下载引导均保留。
- 自动验证：`npm run type-check`、`npm run build` 通过；真实 PDF 渲染/打印需浏览器和受控文件验证。
- 视觉证据：未取得；浏览器限制见 W00。需检查图/PDF 长文件、快速切换、关闭恢复、打印和历史会话产物。
- 风险与可逆性：浏览器 PDF 插件支持度不同，加载失败时仍可通过下载查看；可撤销本批 FilePreviewModal 差异。
- 下一推荐包：W14；W00–W13 视觉和业务 E2E 仍待补。
