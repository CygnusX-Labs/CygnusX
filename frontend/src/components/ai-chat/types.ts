// ===== Token 统计 =====
export interface TokenInfo {
  input?: number
  output?: number
  total?: number
}

// ===== 聊天消息 =====
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

// ===== 工具调用 =====
export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: unknown
  status: 'pending' | 'running' | 'success' | 'error'
}

// ===== 图表数据 =====
export interface ChartData {
  id: string
  type: 'echarts'
  option: Record<string, unknown>
}

// ===== 文件附件 =====
export interface FileAttachment {
  name: string
  size: number
  type: string
  url?: string
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
