# Treasure E2E Release Gates

2026-10-16；本轮仅静态、SQLite/fixture、Vue/React DOM 隔离验证，**没有 PASS_RUNTIME 或 PASS_E2E**。源码门禁 WRITE_RUNTIME_ACCEPTED=False、worker_paths_verified=false 及所有现有默认关闭配置未更改。

| Gate | 本轮结果 | 证据/缺口与后果 |
|---|---|---|
| RG-01 | BLOCKED | w0 源码/子仓/Compose清单已保存；runtime/docker.txt 连接 socket 被拒；运行镜像tag/digest未知，不开放写工具 |
| RG-02 | BLOCKED | 无下载 Worker 二进制/hash/help与命令实证；只准备 SRR，ERR/DRR展示而不可选 |
| RG-03 | BLOCKED | 无真实 RNAFlow/Counts Worker软件、挂载及输入路径验收；分析仅 Prepare |
| RG-04 | BLOCKED | SQLite迁移/所有权测试非PG；runtime/tcp.json PG socket操作被拒；不进行生产迁移 |
| RG-05 | BLOCKED | MemoryStore/Redis mock CAS测试仅隔离；真实Redis端口socket拒绝；不允许内存生产回退 |
| RG-06 | BLOCKED | 委托/重放/schema与ToolBridge隔离测试通过；无真实Node↔Gateway/MCP transport证据 |
| RG-07 | BLOCKED | 双owner/project ASGI与服务隔离测试通过；非真实双用户全栈 |
| RG-08 | BLOCKED | 来源白名单/重定向/预算/符号链接隔离负例通过；无真实下载Worker传输 |
| RG-09 | BLOCKED | 实际临时文件SHA与FileRecord/Version/Handoff隔离测试通过；非真实下载链 |
| RG-10 | BLOCKED | 既有统一validator及合成文件Prepare/拒绝态通过；未创建真实分析Task或执行Flow |
| RG-11 | BLOCKED | 缺报告/双报告索引/失败仅重试交付的隔离测试通过；未真实生成与下载科研报告 |
| RG-12 | BLOCKED | 原展示树DOM通过；runtime/browser.txt Chromium启动退出，无4视口×2主题×2语言截图/键盘验收 |

运行探测只进行无凭证的本地连接/版本查询；没有启动服务、部署、迁移、下载、分析或报告生成。后续需具备权限的非生产隔离环境，逐 Gate 留实际 ID、hash、镜像 digest、耗时与双用户负例；不能因环境变量或人工批准而跳过门禁。
