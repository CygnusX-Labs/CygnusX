# CygnusX 真实运行验收环境

2026-10-17：配置交付 PARTIAL，实际运行 BLOCKED。没有启动服务、读取生产 .env、连接生产数据库或使用生产凭据。

详细拓扑与操作入口见 [验收 README](../../deploy/acceptance/README.md)。独立 internal 网络：Playwright → frontend:8080 → api:8000 → PostgreSQL；API → Redis DB1/ri095_acceptance → Worker；Beat 仅调度项目 report/export reconcile；Worker → private-storage。所有服务无宿主发布端口。

现有 Worker Compose 继承根 .env、external 网络、共享数据和 Docker socket，不能安全直接继承，因此新增最小拓扑，复用现有应用/Worker/前端镜像和业务入口。最小 Dockerfile 仅补齐 data 及 UID10001 私有卷目录，不安装依赖。镜像必须审查并固定 digest，构建 tag 带源码短 SHA。

| 组件 | 专用配置 | 实际运行身份/版本 |
|---|---|---|
| Docker | 本机 unix socket | 权限拒绝，UNKNOWN |
| Compose CLI | 离线 config | v2.39.1 |
| PostgreSQL | postgres / project_export_test_ri095 / ri095_acceptance | NOT_OBSERVED |
| Redis | 独占 Broker DB1/backend DB2 | NOT_OBSERVED |
| API/Worker/Beat | UID10001，队列 ri095_acceptance | NOT_OBSERVED |
| StorageBackend | local /acceptance-storage，独占命名卷 | 未初始化 |
| JWT | 独立密钥，现有注册/登录 | 未创建身份 |
| Pandoc/Typst/字体 | 必须同一 Worker 镜像探测 | NOT_OBSERVED |
| 模板/renderer | 源码 project-summary.v1 / project-summary-adapter.v1 | Worker 未核实 |
| Linux Playwright/Chromium | 匹配包与浏览器镜像，不用 Snap | 未运行 |

控制器不继承宿主 DATABASE_URL、DOCKER_HOST 或云密钥，环境文件 600，四个独立随机秘密；进程禁用 Pydantic .env；实际 PG 身份校验先于迁移/API/Worker/Beat。入口处理 YAML storage 优先级，有效根必须私有卷。对象存储已有 S3 backend，但无授权测试 Bucket，单独 BLOCKED。

本配置未获真实启动认证：镜像、卷权限、应用依赖及 Chromium sandbox 仍需验证。原始 [Docker 拒绝](../../evidence/runtime-acceptance/docker-probe.log)、[静态日志](../../evidence/runtime-acceptance/static-checks.log) 保留。当前所有示例写 flag false，生产默认值未变。
