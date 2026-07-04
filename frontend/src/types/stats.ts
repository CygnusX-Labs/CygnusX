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

/** 全局磁盘容量（data_root 所在挂载盘） */
export interface StorageGlobalUsage {
  /** 总容量（字节） */
  total: number
  /** 已用空间（字节） */
  used: number
  /** 剩余空间（字节） */
  free: number
  /** 已用百分比（0-100） */
  used_percent: number
}

/** 单个用户的空间占用 */
export interface UserStorageUsage {
  /** 用户 ID（users/ 下的目录名） */
  user_id: string
  /** 用户名（库中查不到时回退为目录名） */
  username: string
  /** 占用磁盘空间（字节） */
  size: number
  /** 占所有用户占用总和的百分比（0-100） */
  percent: number
}

/** 存储监控聚合响应 */
export interface StorageUsage {
  /** 本次统计的数据根目录 */
  data_root: string
  /** 全局磁盘容量 */
  global_usage: StorageGlobalUsage
  /** 占用最多的前 N 个用户（降序） */
  users: UserStorageUsage[]
  /** 扫描到的用户目录总数 */
  users_total: number
}
