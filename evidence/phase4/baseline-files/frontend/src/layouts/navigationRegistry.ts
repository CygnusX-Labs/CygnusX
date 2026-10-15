import {
  HomeOutline, GridOutline, FlaskOutline, FitnessOutline,
  DocumentTextOutline, CloudUploadOutline, DownloadOutline, BarChartOutline,
  SettingsOutline, InformationCircleOutline, PersonOutline, WalletOutline,
  SparklesOutline, ConstructOutline, LayersOutline, TerminalOutline,
  SearchOutline, DesktopOutline, BulbOutline, BriefcaseOutline,
  ServerOutline, ArchiveOutline, ChatbubblesOutline, NotificationsOutline,
} from '@vicons/ionicons5'

export interface NavItem {
  key: string
  label: string
  to: string
  icon: typeof HomeOutline
  children?: NavItem[]
}

type SidebarGroup = 'main' | 'system' | 'admin'
interface NavigationEntry extends NavItem {
  sidebarGroup?: SidebarGroup
  topOrder?: number
  topLabel?: string
  topIcon?: typeof HomeOutline
}

// An entry owns its destination; projections only choose its placement and presentation.
const navigationRegistry: NavigationEntry[] = [
  { key: 'home', label: '首页', to: '/', icon: HomeOutline, sidebarGroup: 'main' },
  { key: 'dashboard', label: '仪表板', to: '/dashboard', icon: GridOutline,
    sidebarGroup: 'main', topOrder: 1, topLabel: '控制台', topIcon: HomeOutline },
  { key: 'analysis-center', label: '分析中心', to: '/flows', icon: FlaskOutline,
    sidebarGroup: 'main', topOrder: 2, children: [
      { key: 'rna-seq', label: 'RNA-seq 分析', to: '/flows?type=rna-seq', icon: FlaskOutline },
      { key: 'atac-seq', label: 'ATAC-seq 分析', to: '/flows?type=atac-seq', icon: FitnessOutline },
    ] },
  { key: 'treasure-mouse', label: '寻宝鼠', to: '/treasure-mouse', icon: SearchOutline, sidebarGroup: 'main' },
  { key: 'files', label: '数据管理', to: '/files', icon: CloudUploadOutline, sidebarGroup: 'main' },
  { key: 'database', label: '数据库', to: '/database', icon: LayersOutline, sidebarGroup: 'main' },
  { key: 'downloads', label: '数据下载', to: '/downloads', icon: DownloadOutline, sidebarGroup: 'main' },
  { key: 'tasks', label: '任务中心', to: '/tasks', icon: DocumentTextOutline, sidebarGroup: 'main' },
  { key: 'workflow-monitor', label: '流程监控', to: '/workflow-monitor', icon: BarChartOutline,
    sidebarGroup: 'main' },
  { key: 'reports', label: '结果报告中心', to: '/reports', icon: DocumentTextOutline, sidebarGroup: 'main' },
  { key: 'projects', label: '项目管理', to: '/projects', icon: BriefcaseOutline, sidebarGroup: 'main' },
  { key: 'ai', label: 'AI 助手', to: '/ai', icon: ChatbubblesOutline, sidebarGroup: 'main' },
  { key: 'studio', label: 'AI 工作台', to: '/studio', icon: DesktopOutline, sidebarGroup: 'main' },
  { key: 'tools', label: '生信工具箱', to: '/tools', icon: ConstructOutline, sidebarGroup: 'main' },
  { key: 'cookies', label: '用量统计', to: '/cookies', icon: BarChartOutline, sidebarGroup: 'system' },
  { key: 'agent-capabilities', label: '我的 Agent 能力', to: '/agent-capabilities',
    icon: SparklesOutline, sidebarGroup: 'system' },
  { key: 'settings', label: '系统设置', to: '/settings', icon: SettingsOutline,
    sidebarGroup: 'system' },
  { key: 'about', label: '关于 CygnusX', to: '/about', icon: InformationCircleOutline,
    sidebarGroup: 'system', topOrder: 4, topLabel: '关于' },
  { key: 'knowledge', label: '实验室知识库', to: '/knowledge', icon: DocumentTextOutline,
    topOrder: 3 },
  { key: 'admin-center', label: '系统管理', to: '/admin/users', icon: SettingsOutline,
    sidebarGroup: 'admin', children: [
      { key: 'admin-users', label: '用户管理', to: '/admin/users', icon: PersonOutline },
      { key: 'admin-memory', label: '记忆审计', to: '/admin/memory', icon: BulbOutline },
      { key: 'admin-session-logs', label: '会话日志排查', to: '/admin/session-logs', icon: DocumentTextOutline },
      { key: 'admin-database-health', label: '数据库健康', to: '/admin/database-health', icon: ServerOutline },
      { key: 'admin-ai-metrics', label: 'AI 指标仪表盘', to: '/admin/ai-metrics', icon: BarChartOutline },
      { key: 'admin-ai-config', label: 'AI 配置中心', to: '/admin/ai-config/providers', icon: SparklesOutline },
      { key: 'admin-home-quick-entries', label: '首页入口管理', to: '/admin/home-quick-entries', icon: GridOutline },
      { key: 'admin-biscuits', label: '饼干中心', to: '/admin/biscuits/accounts', icon: WalletOutline },
      { key: 'admin-announcements', label: '通知公告', to: '/admin/announcements', icon: NotificationsOutline },
      { key: 'admin-terminals', label: '沙盒终端管理', to: '/admin/terminals', icon: TerminalOutline },
      { key: 'admin-blast-databases', label: 'BLAST 数据库管理', to: '/admin/blast-databases', icon: SearchOutline },
      { key: 'admin-workspace-archive', label: '工作区归档管理', to: '/admin/workspace-archive', icon: ArchiveOutline },
    ] },
]

export function navigationForTop(): NavItem[] {
  return navigationRegistry.filter((entry) => entry.topOrder !== undefined)
    .sort((a, b) => (a.topOrder ?? 0) - (b.topOrder ?? 0))
    .map((entry) => ({
      key: entry.key === 'analysis-center' ? 'flows' : entry.key,
      label: entry.topLabel ?? entry.label,
      to: entry.to,
      icon: entry.topIcon ?? entry.icon,
    }))
}

export function navigationForSidebar(group: SidebarGroup): NavItem[] {
  return navigationRegistry.filter((entry) => entry.sidebarGroup === group)
    .map(({ key, label, to, icon, children }) => ({ key, label, to, icon, children }))
}
