// ===== Token 统计 =====
export interface TokenInfo {
  input?: number
  output?: number
  total?: number
}

// ===== 聊天消息 =====
/** 智能路由：目标专家信息（route 事件） */
export interface RoutedAgentInfo {
  agentId: string
  name: string
  avatar: string
  color: string
  reason: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  thought?: string
  /** 思考过程用时（秒），AI 消息专属 */
  thinkingDuration?: number
  /** 实际使用的模型名，AI 消息专属 */
  modelName?: string
  toolCalls?: ToolCall[]
  charts?: ChartData[]
  /** Studio ask_user 澄清卡片（AI 消息专属，回答后标记 answered） */
  askRequest?: AskRequest
  /** 智能路由：本条 AI 消息实际由哪位专家回答（路由器会话专属） */
  routedAgent?: RoutedAgentInfo
  attachments?: FileAttachment[]
  feedback?: 'like' | 'dislike'
  /** 是否被编辑过，用户消息专属 */
  edited?: boolean
  /** 编辑历史，用户消息专属 */
  editHistory?: string[]
  /** Token 统计 */
  tokens?: TokenInfo
  /** 消息状态，用于流式错误/空内容识别 */
  status?: 'complete' | 'streaming' | 'error' | 'empty'
  createdAt: string
}

// ===== 图表数据 =====
export interface ChartData {
  id: string
  type: 'echarts' | 'plotly'
  option: Record<string, unknown>
}

// ===== 工具调用 =====
export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: unknown
  uiPayload?: Record<string, unknown>
  mcpServer?: string
  status: 'pending' | 'running' | 'awaiting_approval' | 'success' | 'error'
  /** Studio 工具执行过程中累计的 stdout/stderr 输出（流式填充） */
  output?: string
  /** Studio 代码卡片的语言（python / r / bash） */
  language?: string
  /** Studio HITL 审批状态（仅内存态，刷新后丢失） */
  approval?: ToolApproval
}

/** Studio 工具审批（supervised 模式下受控工具挂起等待用户决议） */
export interface ToolApproval {
  approval_id: string
  status: 'pending' | 'approved' | 'edited' | 'rejected' | 'timeout'
  risk_hint?: string
  timeout_seconds?: number
}

/** Studio ask_user 澄清请求（附着在 AI 消息上，用户下一条消息回答） */
export interface AskRequest {
  question: string
  options?: string[]
  answered?: boolean
}

// ===== 文件附件 =====
export interface FileAttachment {
  name: string
  size: number
  type: string
  url?: string
  file_id?: string
}

// ===== 会话 =====
export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: string
  updatedAt: string
  model: string
  shared?: boolean
  settings?: SessionSettings
}

// ===== 会话设置 =====
export interface SessionSettings {
  temperature?: number
  maxTokens?: number
  topP?: number
  systemPrompt?: string
}

// ===== 用户信息 =====
export interface UserInfo {
  id: string
  name: string
  avatar: string
  role: string
  roleTag?: string
}

// ===== 快捷提示 =====
export interface QuickPrompt {
  icon: string
  text: string
  category: string
}

// ===== 模型能力 =====
export type Capability = 'longContext' | 'code' | 'multimodal' | 'bio'

// ===== 模型类型 =====
export type ModelType = 'general' | 'bio'

// ===== 模型选项 =====
export interface ModelOption {
  id: string
  name: string
  description: string
  provider: string
  /** 推断出的能力标签 */
  capabilities?: Capability[]
  /** 通用 / 生信专用 */
  modelType?: ModelType
  /** 上下文窗口大小（k） */
  contextWindow?: number
}

// ===== 消息操作类型 =====
export type MessageAction = 'copy' | 'regenerate' | 'retry' | 'translate' | 'delete'

// ===== 复制模式 =====
export type CopyMode = 'plain' | 'markdown' | 'citation'

// ===== 生信提示词模板 =====
export interface BioPromptTemplate {
  id: string
  title: string
  description: string
  category: string
  /** Markdown 内容，可含 {{param}} 占位符 */
  content: string
}

// ===== 对话级设置 =====
export interface ConversationSettings {
  temperature: number
  maxTokens: number
  contextLength: number
}

// ===== 系统状态 =====
export type SystemStatus = 'ready' | 'thinking' | 'toolCalling' | 'webSearching'

// ===== 插件选项 =====
export interface PluginOption {
  id: string
  name: string
  description: string
  icon: string
}

// ===== Slash 命令 =====
export interface SlashCommand {
  id: string
  name: string
  description: string
  icon: string
  category: string
  shortcut?: string
}

// ===== 发送选项 =====
export interface SendOptions {
  agentMode: boolean
  model: string
  plugins: string[]
  attachments?: File[]
}
