import { describe, expect, it } from 'vitest'
import { navigationForSidebar, navigationForTop } from '../navigationRegistry'

describe('navigation registry projections', () => {
  it('keeps the existing top destinations, order, and labels', () => {
    expect(navigationForTop().map(({ key, label, to }) => [key, label, to])).toEqual([
      ['dashboard', '控制台', '/dashboard'],
      ['flows', '分析中心', '/flows'],
      ['knowledge', '实验室知识库', '/knowledge'],
      ['about', '关于', '/about'],
    ])
  })

  it('keeps the main, system, and admin destinations', () => {
    expect(navigationForSidebar('main').map(({ key }) => key)).toEqual([
      'home', 'dashboard', 'analysis-center', 'treasure-mouse', 'files', 'database',
      'downloads', 'tasks', 'workflow-monitor', 'reports', 'projects', 'ai', 'studio', 'tools',
    ])
    expect(navigationForSidebar('system').map(({ key }) => key)).toEqual([
      'cookies', 'agent-capabilities', 'settings', 'about',
    ])
    expect(navigationForSidebar('admin')[0]?.children?.map(({ key }) => key)).toEqual([
      'admin-users', 'admin-memory', 'admin-session-logs', 'admin-database-health',
      'admin-ai-metrics', 'admin-ai-config', 'admin-home-quick-entries', 'admin-biscuits',
      'admin-announcements', 'admin-terminals', 'admin-blast-databases',
      'admin-workspace-archive',
    ])
  })
})
