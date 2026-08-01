"""应用配置 - 基于 Pydantic Settings，从环境变量读取"""

from functools import lru_cache
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 应用配置 =====
    app_name: str = "OmicHub"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_secret_key: str = "change-me-in-production"
    service_name: str = "web"

    # ===== 数据库配置 =====
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "omichub"
    postgres_password: str = "omichub"
    postgres_db: str = "omichub"
    database_url: str = ""

    # ===== Redis 配置 =====
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # ===== JWT 配置 =====
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ===== CORS 配置 =====
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ===== AI 配置 =====
    llm_provider: str = "kimi"
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "moonshot-v1-8k"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    # ===== 文件存储 =====
    storage_type: str = "local"
    storage_path: str = "/data/omichub"
    # ===== 多智能体编排（MAS，默认关闭，待灰度启用）=====
    mas_enabled: bool = False
    mas_workspace_root: str = "/data/omichub"
    mas_tool_policies_yaml: str = "data/ai/mas/tool_policies.yaml"
    mas_agent_capabilities_yaml: str = "data/ai/mas/agent_capabilities.yaml"
    mas_artifact_schemas_yaml: str = "data/ai/mas/artifact_schemas.yaml"
    mas_apptainer_binary: str = "apptainer"
    mas_apptainer_image: str = ""
    mas_apptainer_pipeline_root: str = "/opt/omichub/pipelines/RNAFlow"
    mas_scrna_docker_image: str = "omichub-analysis:scrna-2026.07"
    mas_scrna_timeout_seconds: int = 7200
    # ===== P4 记忆语义召回（默认关闭；失败时回退关键词召回） =====
    agent_memory_semantic_retrieval_enabled: bool = False
    agent_memory_embedding_model: str = ""
    agent_memory_semantic_candidate_limit: int = 100
    agent_memory_auto_summary_enabled: bool = False
    agent_memory_auto_summary_min_messages: int = 6
    agent_memory_summary_model: str = ""
    agent_memory_conflict_adjudication_enabled: bool = False
    agent_memory_conflict_adjudication_model: str = ""
    multi_expert_consultation_enabled: bool = False
    multi_expert_consultation_max_experts: int = 3
    # ===== 对话内子 Agent 并行 fan-out（默认关闭，按 Agent 白名单灰度）=====
    # 设计见 ARCHITECTURE_DESIN/multi-agent.md §4
    subagent_fanout_enabled: bool = False
    subagent_max_parallel: int = 4  # 单次 fan-out 最大子任务数
    subagent_max_concurrent: int = 3  # 实际并发信号量（给主链路 LLM 调用留余量）
    subagent_child_timeout_seconds: int = 180  # 单个子任务墙钟上限
    subagent_max_rounds_per_child: int = 6  # 子循环工具轮数上限
    subagent_max_children_per_message: int = 1  # 父单轮工具回合内允许的 fan-out 调用次数
    upload_dir: str = "uploads"
    results_dir: str = "results"
    # 文件生命周期：临时分片会话超 24h 视为僵尸；中间文件保留期；冷数据归档期
    file_upload_session_timeout_hours: int = 24
    file_temp_retention_days: int = 30  # 超期临时/中间文件清理
    file_archive_retention_days: int = 90  # 超期未活跃结果归档或删除
    file_archive_mode: str = "archive"  # archive（压缩归档）/ delete（彻底删除）

    # ===== 数据下载 (EBIDownload Rust 二进制 + 云存储 CLI) =====
    enable_ebi_download: bool = False  # 装好二进制 + sra-tools 后再开
    enable_direct_download: bool = False  # 装好 aria2c 后再开
    download_config_yaml: str = "tool_configs/download/download_config.yaml"
    ebi_download_binary: str = "/data/omichub/bin/EBIDownload"
    ebi_download_yaml: str = "/data/omichub/bin/EBIDownload.yaml"
    enable_cloud_storage_download: bool = False  # 装好 ossutil/tosutil/obsutil 并配置凭据后再开
    cloud_ossutil_binary: str = "/data/omichub/bin/ossutil"
    cloud_tosutil_binary: str = "/data/omichub/bin/tosutil"
    cloud_obsutil_binary: str = "/data/omichub/bin/obsutil"
    direct_download_binary: str = "/usr/bin/aria2c"

    # ===== 流程 YAML 配置 =====
    flow_yaml_dir: str = "flows"

    # ===== Snakemake 配置 =====
    snakemake_cores: int = 4
    snakemake_use_conda: bool = True
    # --use-conda 时环境创建目录（须可写，避免只读挂载冲突）
    snakemake_conda_prefix: str = "/data/omichub/.conda_envs"

    # ===== 任务日志保护 =====
    task_log_message_max_chars: int = 8192  # DB 中单条任务日志 message 最大字符数
    task_log_max_entries: int = 1000  # DB 中单任务最多保留最近 N 条日志

    # ===== 饼干积分系统 =====
    enable_cookie_system: bool = True
    initial_cookie_balance: float = 100.0
    cookie_sandbox_base_cost: float = 0.5
    ai_token_cookie_rate: float = 10.0  # AI 对话每 1K tokens 折算消耗的饼干数

    # ===== 仪表板统计缓存 =====
    enable_stats_cache: bool = True  # Redis 不可用时自动降级为直查 DB

    # ===== AI Copilot =====
    ai_system_prompt: str = ""  # 已迁移到 data/ai/prompts/copilot/system.md；仅保留环境变量兼容覆盖
    ai_max_context_messages: int = 20
    ai_temperature: float = 0.7
    ai_default_provider_id: str = ""  # 默认 AI provider 配置 UUID，空则使用环境变量兜底
    ai_provider_key_encryption_key: str = ""  # Fernet 密钥，为空则 API key 明文存储
    ai_provider_config_yaml: str = "data/ai/providers.yaml"  # 外置 AI Provider YAML 配置路径
    site_content_yaml: str = "data/OmicHub.yaml"  # 首页文案外置 YAML 路径（改文件即生效）
    prompts_registry_yaml: str = "data/ai/prompts/registry.yaml"
    skills_dir: str = "data/ai/skills"  # SKILL.md 标准技能库目录（每个技能一个文件夹）
    skill_marketplace_dir: str = (
        "data/ai/skill_marketplace"  # 内置技能市场：随仓库发布的可安装技能文件夹
    )
    runtime_images_yaml: str = "data/ai/runtime_images.yaml"
    # JBrowse 2 基因组浏览器外置配置：参考基因组 / 预设轨道 / 扫描与上传策略。
    # 改文件后调用 POST /api/v1/jbrowse/config/reload 即时生效（或等配置加载器 mtime 热重载）。
    # 集中配置：与富集分析同放 tool_configs/<工具名>/，仓库内源码管控；容器内经 tool_configs/ 挂载(:ro) 可读。
    jbrowse_config_yaml: str = "tool_configs/jbrowse/jbrowse_config.yaml"

    # ===== 工具箱前端注册表（哪些工具加载到前端 + 展示元数据）=====
    # tool_configs/tools_setting.yaml 列出全部工具卡片（title/description/icon/gradient/route/enabled），
    # 前端 GET /api/v1/tools 拉取 enabled 项渲染 ToolsHub；改文件由加载器 mtime 热重载。
    # 仅「展示元数据」集中于此；各工具的「功能配置」放 tool_configs/<工具名>/（如 jbrowse/、enrichments/）。
    tools_setting_yaml: str = "tool_configs/tools_setting.yaml"

    # ===== FASTQ 极速质控工具配置 =====
    # API 与 QC Worker 共用；任务创建时将其默认参数快照写入任务目录。
    fastq_qc_config_yaml: str = "tool_configs/fastq_qc/config.yaml"

    # ===== AI 助手可调用的工具 Schema 注册表 =====
    # tool_configs/tools_schema.yaml 描述 LLM 可见的参数 schema、执行方式、结果字段白名单等。
    # 与 tools_setting.yaml 解耦：前者供 LLM/MCP 消费，后者供前端工具箱展示。
    tools_schema_yaml: str = "tool_configs/tools_schema.yaml"

    # ===== 系统发育树构建工具配置 =====
    phylogenetic_tree_config_yaml: str = "tool_configs/phylogenetic-tree/config.yaml"
    phylogenetic_tree_defaults_yaml: str = "tool_configs/phylogenetic-tree/defaults.yaml"

    # ===== BLAST 序列比对工具配置 =====
    blast_config_yaml: str = "tool_configs/blast/blast_config.yaml"
    blast_db_root: str = "/data/omichub/blast/db"
    blast_uploads_dir: str = "blast/uploads"
    blast_results_dir: str = "blast/results"
    blast_default_evalue: float = 1e-5
    blast_default_max_target_seqs: int = 10
    blast_docker_image: str = "ncbi/blast:latest"
    blast_use_docker: bool = False
    blast_num_threads: int = 4
    blast_search_timeout: int = 3000  # 50 分钟软超时
    blast_build_timeout: int = 3600  # 1 小时

    # ===== Snakemake 流程监控 =====
    workflow_monitor_enabled: bool = True
    workflow_monitor_template_dir: str = "tool_configs/workflow_monitor/templates"
    workflow_monitor_default_template: str = "default"
    workflow_monitor_ingest_token: str = ""
    # Alias used by the Snakemake logger plugin; if set, it also satisfies backend ingest auth.
    omichub_workflow_monitor_token: str = ""
    workflow_monitor_internal_url: str = "http://web:8000/api/v1/workflow-monitor"
    workflow_monitor_plugin_token_env: str = "OMICHUB_WORKFLOW_MONITOR_TOKEN"
    workflow_monitor_signature_max_skew_seconds: int = 300
    # Entry point from snakemake-logger-plugin-rich-loguru >= 0.2.1.
    snakemake_monitor_logger: str = "rich_loguru"
    snakemake_monitor_plugin_min_version: str = "0.2.1"
    workflow_monitor_event_ttl_seconds: int = 86400
    workflow_monitor_recent_event_limit: int = 1000
    workflow_monitor_stale_after_seconds: int = 600

    # ===== AgentTeams 协作控制面（独立 Bridge 的受控用户代理） =====
    # 浏览器不接触 Bridge 身份凭证；Data Steward 仅可执行只读预检。
    agentteams_bridge_enabled: bool = False
    agentteams_bridge_url: str = ""
    agentteams_bridge_manager_token: str = ""
    agentteams_bridge_data_steward_token: str = ""
    agentteams_bridge_approval_token: str = ""
    agentteams_bridge_workflow_operator_token: str = ""
    agentteams_bridge_timeout_seconds: float = 10.0

    # ===== 节日彩蛋系统 =====
    festival_config_yaml: str = "data/festival_config.yaml"  # 节日彩蛋外置 YAML 配置路径

    # ===== 富集分析（KEGG / GO，R Docker 容器）=====
    # 物种配置 YAML（仓库内源码管控，仿 flows/）；改文件后由加载器 mtime 热重载。
    enrichment_config_yaml: str = "tool_configs/enrichments/species_config.yaml"
    # R 计算容器镜像（用户自行构建，契约见 tool_configs/enrichments/KEGG_Docker_契约.md）
    enrichment_docker_image: str = "omichub-r-enrichment:v1"
    # 容器加入的 Docker 网络；默认使用开发/生产主栈已创建的 app 网络。
    enrichment_docker_network: str = "omichub_app_net"
    # 可选出站代理地址；为空时 KEGG REST 通过 Docker bridge 直接出网。
    enrichment_proxy_url: str = ""
    # 宿主→容器挂载源（容器内固定为 /data/omichub，基因列表与结果 CSV 经此交换）
    enrichment_data_mount: str = "/data/omichub"
    enrichment_exec_timeout: int = 120  # 单次富集分析超时（秒）
    enrichment_memory: str = "2g"  # 容器内存上限
    enrichment_cpus: float = 2.0  # 容器 CPU 核数

    # ===== DEG 差异表达分析（DESeq2 / edgeR 双引擎，R Docker 容器）=====
    # 运行配置 YAML（镜像资源、默认参数、输入限制）；改文件后由加载器 mtime 热重载。
    deg_config_yaml: str = "tool_configs/deg/deg_config.yaml"
    # R 计算容器镜像（make docker-build-deg 构建，契约见 tool_configs/deg/README.md）
    deg_docker_image: str = "omichub-r-deg:v1"
    # 容器加入的 Docker 网络（与主栈 app 网络一致）
    deg_docker_network: str = "omichub_app_net"
    # 宿主→容器挂载源（容器内固定为 /data/omichub，输入与结果经此交换）
    deg_data_mount: str = "/data/omichub"
    deg_exec_timeout: int = 7200  # 单次 DEG 分析超时（秒）；0 回退 YAML execution.timeout

    # ===== 管理员欢迎彩蛋（预生成 + 顺序轮询）=====
    # 启动时若 welcome.yaml 条数 < threshold，调用默认 AI provider 补齐到 threshold 条；
    # 运行时登录仅读盘 + 游标前进，零延迟、不调 AI。两文件均缺失时回退内置兜底文案。
    # 注意：必须放在可写目录。data/ 目录在容器中为只读挂载（docker-compose :ro），
    # 故改用 storage_path（/data/omichub，容器与宿主共享且可写）下的
    # omichub_data/welcome/ 子目录，避免与任务数据混放。
    welcome_yaml: str = (
        "/data/omichub/omichub_data/welcome/welcome.yaml"  # 预生成欢迎词（纯字符串数组）
    )
    welcome_state_yaml: str = "/data/omichub/omichub_data/welcome/welcome_state.yaml"  # 轮询游标
    welcome_seed_threshold: int = 20  # 启动补齐目标条数

    # ===== 代码执行沙盒 =====
    sandbox_enabled: bool = True
    sandbox_image: str = "omichub/sandbox-base:latest"
    sandbox_docker_network: str = "omichub_default"
    # 是否将沙盒容器置于无网络模式（默认 True），防止用户代码扫描/访问内网
    sandbox_network_isolated: bool = True
    sandbox_warm_pool_size: int = 2
    sandbox_max_pool_size: int = 10
    sandbox_session_timeout: int = 1800  # 30 分钟无活动回收
    sandbox_exec_timeout: int = 300  # 单次代码执行超时（秒）
    sandbox_data_dir: str = "/data/omichub"
    sandbox_default_cpu: float = 2.0
    sandbox_default_memory: str = "4g"

    # ===== 云端沙盒终端 =====
    # 功能配置 YAML（仓库内源码管控）；改文件后由加载器 mtime 热重载。
    terminal_config_yaml: str = "tool_configs/terminal/terminal_config.yaml"
    # 终端镜像配置 YAML（仓库内源码管控）；改文件后由加载器 mtime 热重载。
    terminal_images_config_yaml: str = "tool_configs/terminal/terminal_images.yaml"

    # ===== MCP 集成 =====
    mcp_enabled: bool = True
    mcp_default_timeout: int = 30

    # ===== MCP Builder（AI 自生成 MCP）=====
    mcp_builder_enabled: bool = True  # 是否启用 MCP Builder 功能
    mcp_builder_requires_review: bool = True  # 发布是否需要管理员审核
    mcp_builder_max_per_user: int = 5  # 每用户最大实验 MCP 数量
    mcp_builder_default_ttl_hours: int = 24  # 实验 MCP 默认 TTL
    mcp_builder_default_model: str = "qwen3.7-plus"  # 代码生成默认模型（与平台 agent 标准一致）

    # ===== 限流（全局每 IP 滑动窗口，Redis 不可用时降级放行）=====
    rate_limit_enabled: bool = True
    rate_limit_max: int = 100  # 窗口内最大请求数
    rate_limit_window: int = 60  # 窗口秒数

    # ===== OmicStudio AI 分析工作台 =====
    # 功能配置 YAML（仓库内源码管控）；改文件后由加载器 mtime 热重载。
    studio_config_yaml: str = "data/ai/studio.yaml"
    # Celery worker 无 Docker socket；通过 web 的受认证内部控制面执行/回收沙盒。
    studio_control_internal_url: str = "http://web:8000/api/v1/studio/internal"
    studio_control_token: str = ""

    # ===== 敏感信息脱敏 =====
    # 逗号分隔的敏感词列表，AI 对话送 LLM 前 / 落库前替换为 [REDACTED]（不可逆）
    sensitive_keywords: list[str] = []

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_database_url(cls, v: str, info: Any) -> str:
        if v:
            return v
        values = info.data
        return (
            f"postgresql+asyncpg://{values['postgres_user']}:"
            f"{values['postgres_password']}@{values['postgres_host']}:"
            f"{values['postgres_port']}/{values['postgres_db']}"
        )

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def assemble_celery_broker(cls, v: str, info: Any) -> str:
        values = info.data
        redis_password = values.get("redis_password", "")
        if v:
            # 已配置 URL 但未带密码时，自动注入密码（兼容 .env 中硬编码的旧写法）
            if redis_password and "://" in v and "@" not in v:
                scheme, rest = v.split("://", 1)
                return f"{scheme}://:{redis_password}@{rest}"
            return v
        password_part = f":{redis_password}@" if redis_password else ""
        return f"redis://{password_part}{values['redis_host']}:{values['redis_port']}/1"

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def assemble_celery_backend(cls, v: str, info: Any) -> str:
        values = info.data
        redis_password = values.get("redis_password", "")
        if v:
            if redis_password and "://" in v and "@" not in v:
                scheme, rest = v.split("://", 1)
                return f"{scheme}://:{redis_password}@{rest}"
            return v
        password_part = f":{redis_password}@" if redis_password else ""
        return f"redis://{password_part}{values['redis_host']}:{values['redis_port']}/2"

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """生产环境强制校验关键密钥，避免使用默认值或空值上线。"""
        if not self.workflow_monitor_ingest_token and self.omichub_workflow_monitor_token:
            self.workflow_monitor_ingest_token = self.omichub_workflow_monitor_token
        if not self.is_production:
            return self

        default_secret = "change-me-in-production"
        if self.app_secret_key == default_secret:
            raise ValueError("生产环境必须设置 APP_SECRET_KEY，不能使用默认值")
        if self.jwt_secret_key == default_secret:
            raise ValueError("生产环境必须设置 JWT_SECRET_KEY，不能使用默认值")
        if not self.redis_password:
            raise ValueError("生产环境必须设置 REDIS_PASSWORD")
        if not self.ai_provider_key_encryption_key:
            raise ValueError("生产环境必须设置 AI_PROVIDER_KEY_ENCRYPTION_KEY")
        if self.workflow_monitor_enabled and not self.workflow_monitor_ingest_token:
            raise ValueError("生产环境启用流程监控时必须设置 WORKFLOW_MONITOR_INGEST_TOKEN")
        if self.agentteams_bridge_enabled and (
            not self.agentteams_bridge_url
            or self._is_placeholder(self.agentteams_bridge_manager_token)
            or self._is_placeholder(self.agentteams_bridge_data_steward_token)
            or self._is_placeholder(self.agentteams_bridge_approval_token)
            or self._is_placeholder(self.agentteams_bridge_workflow_operator_token)
        ):
            raise ValueError(
                "生产环境启用 AgentTeams Bridge 时必须设置地址、Manager、Data Steward、审批和 Workflow Operator 凭证"
            )
        return self

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        normalized = value.strip().lower()
        return (
            not normalized
            or normalized.startswith("replace-")
            or normalized.startswith("change-me")
        )

    @property
    def redis_url(self) -> str:
        password_part = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
