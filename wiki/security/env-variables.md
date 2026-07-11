# 环境变量与密钥

OmicHub 的运行时差异与敏感信息通过环境变量管理。`.env` 文件已加入 `.gitignore`，请勿将真实密钥提交到仓库。

## 首次部署必填

以下变量必须设置为强随机值，生产环境若缺失或仍为默认值应用将**启动失败**。

```bash
# JWT / Cookie 签名密钥（任意长随机字符串，建议 ≥32 字节）
JWT_SECRET_KEY=your-random-secret-here
APP_SECRET_KEY=your-random-secret-here

# Redis 认证密码
REDIS_PASSWORD=your-redis-password-here

# AI Provider key / TOTP secret 加密密钥（Fernet 32 字节 URL-safe base64）
# 生成方式：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AI_PROVIDER_KEY_ENCRYPTION_KEY=your-fernet-key-here

# 生产环境首位管理员强密码
OMICHBUB_INIT_ADMIN_PASSWORD=your-strong-password

# 开发环境 Flower 基本认证（用户名:密码）
FLOWER_BASIC_AUTH=admin:your-strong-password
```

> ⚠️ `AI_PROVIDER_KEY_ENCRYPTION_KEY` 一旦设置并写入数据后**不可更改**，否则已加密的字段将无法解密。

## AI Provider 配置

支持两种方式（可共存，方式 1 优先）：

### 方式 1（推荐）：外置 YAML

编辑 `data/ai_providers.yaml`，支持 `${ENV_VAR}` 插值：

```yaml
providers:
  - name: aliyun
    provider_type: openai_compatible
    model: qwen3.7-max
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: ${AL_API_KEY}
    is_default: true
```

### 方式 2：环境变量兜底

仅在数据库无 Provider 时生效：

```bash
KIMI_API_KEY=your-kimi-key
OPENAI_API_KEY=your-openai-key
```

## 日志相关

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `SERVICE_NAME` | 服务标识（web/beat/worker） | `app` |
| `OMICHUB_LOG_LEVEL` | stdout 日志级别 | `INFO`（开发 `DEBUG`） |
| `OMICHUB_LOG_DIR` | 应用日志根目录 | `/app/logs` |
| `OMICHUB_LOG_ROTATION` | 应用日志轮转阈值 | `50 MB` |
| `OMICHUB_LOG_RETENTION` | 应用日志保留期 | `30 days` |
| `OMICHUB_LOG_COMPRESSION` | 应用日志压缩格式 | `zip` |
| `OMICHUB_CELERY_LOG_DIR` | Celery 单任务日志目录 | `${OMICHUB_LOG_DIR}/celery/tasks` |
| `OMICHUB_CELERY_LOG_ROTATION` | 单任务日志轮转阈值 | `20 MB` |
| `OMICHUB_CELERY_LOG_RETENTION` | 单任务日志保留期 | `7 days` |
| `TASK_LOG_MESSAGE_MAX_CHARS` | DB 单条任务日志最大字符数 | `8192` |
| `TASK_LOG_MAX_ENTRIES` | 单任务最多保留日志条数 | `1000` |

## 下载相关

| 环境变量 | 说明 |
|---|---|
| `ENABLE_EBI_DOWNLOAD` | 是否启用 EBI/NCBI 公共数据库下载 |
| `EBI_DOWNLOAD_BINARY` | EBIDownload 二进制路径 |
| `EBI_DOWNLOAD_YAML` | EBIDownload 配置文件路径 |
| `ENABLE_CLOUD_STORAGE_DOWNLOAD` | 是否启用云存储直拉 |
| `CLOUD_OSSUTIL_BINARY` | 阿里云 ossutil 路径 |
| `CLOUD_TOSUTIL_BINARY` | 火山引擎 tosutil 路径 |
| `CLOUD_OBSUTIL_BINARY` | 华为云 obsutil 路径 |

## 沙盒终端

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `SANDBOX_NETWORK_ISOLATED` | 沙盒容器是否使用 `network_mode=none` | `true` |

## 安全提示

- 生产环境务必修改所有默认值。
- 不要把 `.env` 或含密钥的 YAML 提交到仓库。
- 定期轮换 `JWT_SECRET_KEY`、`APP_SECRET_KEY`、`REDIS_PASSWORD`；注意 `AI_PROVIDER_KEY_ENCRYPTION_KEY` 不可改。
- 使用 `pip-audit` 定期扫描依赖漏洞。
