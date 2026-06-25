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
  status: 'active' | 'inactive' | 'locked'
  avatar_url?: string | null
  preferences?: Record<string, unknown>
  last_login_at?: string | null
  created_at: string
  updated_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
}

export interface FlowDefinition {
  id: string
  name: string
  description: string
  category: string
  version: string
}

export interface TaskLog {
  timestamp: string
  level: 'debug' | 'info' | 'warning' | 'error' | 'critical'
  message: string
  source: string
}

export interface Task {
  id: string
  flow_id: string
  user_id: string
  name: string
  status: 'pending' | 'queued' | 'running' | 'success' | 'failed' | 'cancelled'
  execution_mode: string
  parameters: Record<string, unknown>
  work_dir: string
  result_path: string
  error_message: string
  progress: number
  logs: TaskLog[]
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ChatMessage {
  id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  timestamp: string
}
