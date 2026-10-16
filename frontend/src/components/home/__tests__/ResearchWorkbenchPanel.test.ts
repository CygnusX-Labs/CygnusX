// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProjectItem } from '@/api/projects'
import type { Report } from '@/types/report'
import type { Task } from '@/types'
import ResearchWorkbenchPanel from '../ResearchWorkbenchPanel.vue'

const apiMocks = vi.hoisted(() => ({
  getTasks: vi.fn(),
  listProjects: vi.fn(),
  getReports: vi.fn(),
}))

vi.mock('@/api/client', () => ({ default: { get: apiMocks.getTasks } }))
vi.mock('@/api/projects', () => ({ projectsApi: { listProjects: apiMocks.listProjects } }))
vi.mock('@/api/report', () => ({ reportApi: { getReports: apiMocks.getReports } }))

const project: ProjectItem = {
  id: 'project-1',
  name: '番茄耐盐转录组',
  slug: 'tomato-salt-rna',
  description: '盐胁迫响应分析',
  created_at: '2026-10-10T08:00:00Z',
  updated_at: '2026-10-12T08:00:00Z',
}

const task = (id: string, status: Task['status']): Task => ({
  id,
  flow_id: 'rna_seq',
  user_id: 'user-1',
  name: `任务 ${id}`,
  status,
  execution_mode: 'celery',
  parameters: {},
  work_dir: '',
  result_path: '',
  error_message: '',
  progress: status === 'running' ? 45 : 0,
  logs: [],
  created_at: '2026-10-13T08:00:00Z',
  started_at: null,
  finished_at: null,
})

const report: Report = {
  id: 'report-1',
  task_id: 'task-running',
  user_id: 'user-1',
  flow_id: 'rna_seq',
  flow_name: 'RNA-seq',
  flow_version: '2.3.0',
  flow_icon: '',
  title: '盐胁迫差异表达结果',
  description: '',
  status: 'completed',
  sample_count: 4,
  duration: 0,
  created_at: '2026-10-14T08:00:00Z',
  completed_at: '2026-10-14T08:10:00Z',
  is_read: false,
  is_starred: false,
  files: [],
}

let app: ReturnType<typeof createApp> | null = null
let host: HTMLDivElement | null = null

async function mountPanel() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: ResearchWorkbenchPanel },
      { path: '/projects', name: 'projects', component: { render: () => h('div') } },
      { path: '/projects/:projectId', name: 'project-detail', component: { render: () => h('div') } },
      { path: '/tasks', name: 'tasks', component: { render: () => h('div') } },
      { path: '/tasks/:taskId', name: 'task-detail', component: { render: () => h('div') } },
      { path: '/flows', name: 'flows', component: { render: () => h('div') } },
      { path: '/reports', name: 'reports', component: { render: () => h('div') } },
    ],
  })
  await router.push('/')
  await router.isReady()
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(RouterView) })
  app.use(router)
  app.mount(host)
  for (let index = 0; index < 8; index++) {
    await Promise.resolve()
    await nextTick()
  }
  return host
}

afterEach(() => {
  app?.unmount()
  host?.remove()
  app = null
  host = null
  vi.clearAllMocks()
})

describe('ResearchWorkbenchPanel', () => {
  it('shows real project, queued/running task and report data with valid destinations', async () => {
    apiMocks.listProjects.mockResolvedValue([project])
    apiMocks.getTasks.mockImplementation((_path: string, config: { params: { status: string } }) =>
      Promise.resolve({ data: { items: [task(config.params.status === 'running' ? 'running' : 'queued', config.params.status === 'running' ? 'running' : 'queued')] } }),
    )
    apiMocks.getReports.mockResolvedValue({ data: { items: [report], total: 1 } })

    const page = await mountPanel()

    expect(page.textContent).toContain('番茄耐盐转录组')
    expect(page.textContent).toContain('任务 running')
    expect(page.textContent).toContain('任务 queued')
    expect(page.textContent).toContain('运行中')
    expect(page.textContent).toContain('排队中')
    expect(page.textContent).toContain('盐胁迫差异表达结果')
    expect(page.querySelector('a[href="/projects/project-1"]')).not.toBeNull()
    expect(apiMocks.getTasks).toHaveBeenCalledWith('/tasks', { params: { status: 'running', limit: 5 } })
  })

  it('shows empty and unavailable states without substituting sample content', async () => {
    apiMocks.listProjects.mockRejectedValue(new Error('unavailable'))
    apiMocks.getTasks.mockRejectedValue(new Error('unavailable'))
    apiMocks.getReports.mockRejectedValue(new Error('unavailable'))

    const page = await mountPanel()

    expect(page.textContent).toContain('项目暂时无法加载')
    expect(page.textContent).toContain('任务暂时无法加载')
    expect(page.textContent).toContain('报告暂时无法加载')
    expect(page.textContent).not.toContain('示例项目')
    expect(page.textContent).not.toContain('示例报告')
  })
})
