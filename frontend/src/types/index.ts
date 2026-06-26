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

// ===== AI Copilot =====
export interface Conversation {
  id: string
  user_id: string
  title: string
  model: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface AIMessage {
  id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  tool_calls?: Array<Record<string, unknown>>
  tool_call_id?: string | null
  timestamp: string
}

export interface ConversationDetail extends Conversation {
  messages: AIMessage[]
}

// AI WebSocket 事件
export type AIEvent =
  | { type: 'user_message'; message: AIMessage }
  | { type: 'token'; content: string }
  | { type: 'assistant_message'; message: AIMessage }
  | { type: 'tool_call'; tool: string; arguments: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; result: Record<string, unknown> }
  | { type: 'done' }
  | { type: 'error'; detail: string }
  | { type: 'pong' }

// ===== 代码执行沙盒 =====
export interface SandboxSession {
  id: string
  user_id: string
  container_id: string | null
  status: 'creating' | 'ready' | 'executing' | 'idle' | 'paused' | 'error' | 'destroyed'
  language: string
  last_activity: string
  created_at: string
  expires_at: string | null
}

export type SandboxEvent =
  | { type: 'stdout'; data: string }
  | { type: 'stderr'; data: string }
  | { type: 'echarts'; option: Record<string, unknown> }
  | { type: 'image'; data: string }
  | { type: 'done'; exit_code: number; duration_ms: number }
  | { type: 'error'; detail: string }

// ===== MCP =====
export interface MCPServer {
  id: string
  name: string
  description: string
  transport: 'stdio' | 'sse' | 'builtin'
  command: string
  url: string
  status: 'online' | 'offline' | 'error' | 'starting'
  timeout: number
  auto_restart: boolean
  is_preset: boolean
  tool_count: number
  created_at: string | null
}

export interface MCPTool {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

// ===== AI Provider 配置 =====
export interface AIProviderConfig {
  id: string
  name: string
  provider_type: string
  model: string
  base_url: string
  temperature: number
  max_tokens: number
  top_p: number
  timeout: number
  is_active: boolean
  is_default: boolean
  extra_params: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

// ===== 饼干积分系统 =====
export interface CookieAccount {
  id: number | null
  user_id: string
  balance: number
  frozen_balance: number
  available_balance: number
  total_earned: number
  total_spent: number
  total_adjusted: number
  status: 'active' | 'frozen' | 'suspended'
  created_at: string | null
}

export interface CookieTransaction {
  id: number | null
  user_id: string
  txn_type: 'earn' | 'spend' | 'adjust' | 'refund' | 'freeze' | 'unfreeze'
  amount: number
  balance_after: number
  source_type: string
  source_id: string
  task_type: string
  description: string
  created_at: string | null
}

export interface CookiePricing {
  id: number | null
  pricing_type: 'task_type' | 'resource' | 'sandbox' | 'bonus'
  resource_type: string
  flow_category: string
  base_cost: number
  unit: 'per_task' | 'per_hour' | 'per_core_hour' | 'per_gb_hour' | 'per_session' | 'per_user'
  is_active: boolean
  priority: number
  description: string
  effective_from: string | null
  effective_until: string | null
}

export interface CostEstimate {
  flow_id: string
  estimated_cost: number
  breakdown: Array<{ item: string; cost: string }>
  affordable: boolean
  current_balance: number
}

export interface CookieStats {
  total_accounts: number
  active_accounts: number
  total_balance: number
  total_frozen: number
  total_earned: number
  total_spent: number
}

// ===== 通知提醒 =====
export type NotificationLevel = 'info' | 'warning' | 'error'

export interface Notification {
  id: string
  title: string
  content: string
  level: NotificationLevel
  created_by: string
  is_global: boolean
  target_user_id: string | null
  read_by: string[]
  expires_at: string | null
  created_at: string
  updated_at: string
}
