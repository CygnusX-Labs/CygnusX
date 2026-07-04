/**
 * 多智能体协作平台 — 资产类型定义
 *
 * 后台「AI 资源中心」与前台「AI 助手」共享的资产模型。
 * 当前由 Mock store（agentHub）承载，后续可平滑切换到真实后端 DTO。
 */

export type AgentCategory = 'general' | 'analysis' | 'code' | 'visualization'

/** MCP 服务内置工具 */
export interface McpTool {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

/** MCP 服务（后台可展开表格的单元） */
export interface McpService {
  id: string
  name: string
  description: string
  /** 在线状态：🟢 online / 🔴 offline */
  status: 'online' | 'offline'
  transport: 'stdio' | 'sse' | 'builtin'
  command: string
  args: string[]
  url: string
  env: Record<string, string>
  registry: string
  working_dir: string
  version: string
  is_enabled: boolean
  tools: McpTool[]
  timeout: number
  auto_restart: boolean
  tool_count: number
  is_preset: boolean
}

/** MCP 日志条目 */
export interface McpLogEntry {
  timestamp: string
  level: 'info' | 'stderr' | 'error' | 'warn'
  message: string
  source: string
}

/** 技能（支持 URL 拉取 / JSON 粘贴导入） */
export interface SkillItem {
  id: string
  name: string
  description: string
  icon: string
  category: string
  source: 'url' | 'json' | 'builtin'
  source_url?: string
  /** JSON 模式下原始配置文本 */
  config?: string
  is_active: boolean
}

export interface AgentFeatures {
  enable_web_search?: boolean
  enable_code_execution?: boolean
  enable_file_upload?: boolean
  enable_deep_thinking?: boolean
}

/** Agent 模板 —— 后台编排、前台按需唤醒的「专家角色」 */
export interface AgentTemplate {
  id: string
  name: string
  description: string
  /** emoji 头像 */
  avatar: string
  /** 主题色（头像背景 / 卡片高亮） */
  color: string
  category: AgentCategory
  /** 大模型引擎，如 claude-3-5-sonnet / gpt-4o（展示用 label） */
  model_engine: string
  /** YAML 中写的模型名称（按 name 匹配 ai_provider_configs） */
  model_name?: string
  /** 绑定的真实模型配置 ID（ai_provider_configs.id，UUID） */
  model_id?: string
  /** 系统设定 */
  system_prompt: string
  /** 进入沙盒时自动发送的欢迎语 */
  welcome_message: string
  /** 挂载的 MCP 服务 id 列表 */
  mcp_ids: string[]
  /** 挂载的技能 id 列表 */
  skill_ids: string[]
  /** 功能开关 */
  features: AgentFeatures
  is_active: boolean
  is_builtin: boolean
  is_default: boolean
}

/** 大模型引擎选项（Agent 编排表单下拉用） */
export interface ModelEngineOption {
  label: string
  value: string
}
