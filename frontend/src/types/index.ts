/** 通用 API 响应类型 */

export interface ApiResponse<T = unknown> {
  data: T
  message?: string
}

export interface User {
  id: string
  username: string
  email: string
  role: 'admin' | 'user'
  status: 'active' | 'inactive'
}

export interface FlowDefinition {
  id: string
  name: string
  description: string
  category: string
  version: string
}

export interface Task {
  id: string
  flow_id: string
  user_id: string
  name: string
  status: 'pending' | 'queued' | 'running' | 'success' | 'failed' | 'cancelled'
  progress: number
  created_at: string
}

export interface ChatMessage {
  id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  timestamp: string
}
