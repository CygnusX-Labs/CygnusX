// ===== 聊天消息 =====
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  thought?: string
  toolCalls?: ToolCall[]
  charts?: ChartData[]
  attachments?: FileAttachment[]
  feedback?: 'like' | 'dislike'
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

// ===== 模型选项 =====
export interface ModelOption {
  id: string
  name: string
  description: string
  provider: string
}

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
