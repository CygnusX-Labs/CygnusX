export interface MemoryBlock {
  id: number
  agent_id: string
  project_id: string | null
  block_name: string
  content: string
  char_limit: number
  version: number
  status?: string
  superseded_by?: number | null
}

export interface MemoryResidualHint {
  kind: 'block' | 'fact' | 'episode'
  id: number
  excerpt: string
  agent_id: string
  project_id: string | null
  block_name: string | null
}

export interface MemoryForgetResponse {
  memory_id: string
  forgotten: boolean
  scan_status: 'disabled' | 'complete' | 'partial' | 'failed'
  residual_hints: MemoryResidualHint[]
}

export interface MemoryForgetContext {
  agent_id?: string
  project_id?: string
}
