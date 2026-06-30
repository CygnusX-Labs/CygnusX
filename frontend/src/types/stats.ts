/** 仪表板统计相关响应类型 */

export interface StatsOverview {
  /** 运行中任务数 */
  running: number
  /** 总任务数 */
  total: number
  /** 累计样本数 */
  samples: number
}

export interface TrendPoint {
  /** 日期 MM/DD */
  date: string
  /** 当日任务数 */
  tasks: number
  /** 当日样本数 */
  samples: number
}

export interface GuideStep {
  number: number
  title: string
  done: boolean
}

export interface UserProgress {
  steps: GuideStep[]
  /** 当前应完成的步骤编号（全部完成则为 null） */
  current: number | null
}

/** 全平台各状态任务数：{ running: n, success: n, ... } */
export type AdminStatus = Record<string, number>

export interface FlowUsage {
  flow_id: string
  name: string
  count: number
}

export interface AdminUserStats {
  total_users: number
  active_users_7d: number
}

export interface FailedTask {
  id: string
  name: string
  flow_id: string
  user_id: string
  error_message: string
  created_at: string | null
}
