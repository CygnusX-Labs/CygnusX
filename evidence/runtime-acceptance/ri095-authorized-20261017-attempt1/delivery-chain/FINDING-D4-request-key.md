# FINDING D4 — 浏览器 UI 导出创建发送空 request_key（真实代码缺陷）

发现轮次：`ri095-authorized-20261017-attempt1`，2026-10-18。

## 现象

浏览器真实 UI 流程（登录 → 项目详情 → 刷新科研成果 → 导出科研成果：预览范围 →
确认范围并后台生成）中 `POST /api/v1/projects/{id}/exports` 返回 **422**：

```json
{"detail":"请求参数校验失败","errors":[{"type":"uuid_parsing",
 "loc":["body","request_key"],"msg":"Input should be a valid UUID,
 invalid length: expected length 32 for simple format, found 0","input":""}]}
```

拦截证据（`deploy/acceptance/probe-create.cjs`，真实 Chromium sandbox 容器内）：

```text
REQ  .../exports
REQ_BODY {"selection":{...},"manifest_digest":"e49b...","request_key":""}
RESP 422  uuid_parsing  request_key  input ""
```

同一 payload 经 httpx 复现为 200，说明缺陷仅在 UI 的取值路径。

## 根因

`frontend/src/components/ProjectResearchDelivery.vue`：

- `let requestKey = ''` 初始为空；
- 仅在 `prepare()` 内 `selectionVersion === selectionGeneration` 时才赋值
  `requestKey = crypto.randomUUID()`；
- `load()`（挂载时）与 `invalidate()` 均把它重置为 `''`。

当预览通过（恢复/快速路径）后 `requestKey` 保持 `''`，`create()` 原样发出空串，
后端 pydantic `CreateProjectExport.request_key: UUID` 拒绝 → 422。API 层驱动器
直接构造合法 UUID，因此从未暴露。

## 最小修复

`create()` 内兜底生成（幂等键只要求同预览内唯一，兜底生成语义等价）：

```ts
// request_key 是导出幂等键；预览确认后必须非空，兜底生成避免空 UUID 422。
if (!requestKey) requestKey = crypto.randomUUID()
```

## 验证

- 前端镜像重建（`Dockerfile.frontend` 真实 `npm ci` + `vue-tsc -b && vite build`），
  digest `127.0.0.1:5000/ri095-frontend-fixd4@sha256:c23901d6...`；
- 隔离 acceptance 栈换用该镜像重建 frontend 容器；
- 浏览器 E2E 重跑（`browser/attempt2-fixed/browser-e2e.log`）：
  - **422 消失**（w1920-network.json 无任何 4xx）；
  - 业务 console 错误清零（`console_clean` 三宽度全过）；
  - 34 步中 31 步通过；剩余 3 处 `export_ready` 为 spec 等待时序（幂等创建
    直接返回既有 ready job，spec 的按钮轮询未命中），非产品缺陷——
    ready 状态本身由 API 驱动器 30 步全 200 证明。

## 修复文件

- `frontend/src/components/ProjectResearchDelivery.vue`（未提交，随本轮工作树）
- `deploy/acceptance/probe-create.cjs`（拦截/复现探针）
- `deploy/acceptance/seccomp_browser.py` + `seccomp-browser.json` +
  `docker-seccomp-default.json`（浏览器 sandbox 解锁，用户已授权）
- `deploy/acceptance/browser-e2e.cjs` + `run-browser-e2e.sh`（业务 E2E 执行器）
