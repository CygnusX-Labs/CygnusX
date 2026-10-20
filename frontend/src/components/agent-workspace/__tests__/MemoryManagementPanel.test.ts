// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MemoryManagementPanel from '../MemoryManagementPanel.vue'
import type { MemoryBlock } from '@/types/memory'

const { get, patch, post, warning } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), post: vi.fn(), warning: vi.fn() }))
vi.mock('@/api/client', () => ({ default: { get, patch, post } }))
vi.mock('naive-ui', async (importOriginal) => ({
  ...await importOriginal<typeof import('naive-ui')>(),
  useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
  useDialog: () => ({ warning }),
}))

const project = 'ecfcd069-e139-4a09-8782-c999d014b7b7'
const block: MemoryBlock = {
  id: 2, agent_id: 'a', block_name: 'current_focus', project_id: project,
  content: '项目独有目标', char_limit: 2000, version: 7, status: 'active',
}
async function settle() {
  for (let index = 0; index < 8; index++) { await Promise.resolve(); await nextTick() }
}
async function mount(enabled: boolean, facts: unknown[] = []) {
  get.mockResolvedValue({ data: {
    mode: 'v2', focus_per_project_enabled: enabled, agent_ids: ['a'], facts, legacy_memories: [],
    blocks: [
      { ...block, id: 1, project_id: null, content: '通用目标', version: 3 }, block,
      { ...block, id: 3, agent_id: '', project_id: null, block_name: 'profile', content: '个人背景' },
    ],
  } })
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({ render: () => h(MemoryManagementPanel, { agentId: 'a' }) })
  app.mount(host)
  await settle()
  return { host, close() { app.unmount(); host.remove() } }
}

describe('project focus management', () => {
  beforeEach(() => vi.clearAllMocks())

  it('groups project/general/shared blocks and edits the selected project using its version', async () => {
    patch.mockResolvedValue({ data: { ...block, content: '', version: 8 } })
    const panel = await mount(true)
    try {
      const groups = [...panel.host.querySelectorAll('.memory-block-group')]
      const projectGroup = groups.find((node) => node.querySelector('h5')?.textContent?.includes(project))!
      expect(projectGroup.textContent).toContain('项目独有目标')
      expect(projectGroup.textContent).not.toContain('通用目标')
      expect(groups.some((node) => node.textContent?.includes('共享个人记忆'))).toBe(true)
      projectGroup.querySelector('button')!.click()
      await settle()
      const input = document.querySelector<HTMLTextAreaElement>('.n-modal textarea')!
      expect(input).toBeTruthy()
      input.value = ''
      input.dispatchEvent(new Event('input', { bubbles: true }))
      await settle()
      const save = [...document.querySelectorAll<HTMLButtonElement>('.n-modal button')].find((button) => button.textContent?.includes('保存记忆块'))!
      expect(save.disabled).toBe(false)
      save.click()
      await settle()
      expect(patch).toHaveBeenCalledWith('/users/me/memory-blocks/current_focus', {
        content: '', expected_version: 7,
      }, { params: { agent_id: 'a', project_id: project } })
    } finally { panel.close() }
  })

  it('retains project focus as readonly when the feature is off', async () => {
    const panel = await mount(false)
    try {
      const groups = [...panel.host.querySelectorAll('.memory-block-group')]
      const projectGroup = groups.find((node) => node.querySelector('h5')?.textContent?.includes(project))!
      expect(projectGroup.querySelector('button')!.disabled).toBe(true)
      expect(projectGroup.textContent).toContain('只读')
      const general = groups.find((node) => node.querySelector('h5')?.textContent?.includes('无项目'))!
      expect(general.querySelector('button')!.disabled).toBe(false)
      expect(patch).not.toHaveBeenCalled()
    } finally { panel.close() }
  })

  it('shows residuals after confirmation and never cleans them automatically', async () => {
    const source = { id: 10, agent_id: 'a', project_id: project, scope: 'summary', content: 'GRCh38 来源', keywords: [], confidence: 1, status: 'active', created_at: null, last_recalled_at: null }
    const hints = [
      { kind: 'block', id: 3, excerpt: '<img src=x onerror=alert(1)>', block_name: 'profile', agent_id: '', project_id: null },
      { kind: 'episode', id: 80, excerpt: 'GRCh38 会话进展', block_name: null, agent_id: 'a', project_id: project },
    ]
    let relatedArchived = false
    post.mockImplementation((url: string) => {
      if (url.includes('/80/')) relatedArchived = true
      return Promise.resolve({ data: url.endsWith('/forget') ? {
        memory_id: url.includes('/80/') ? '80' : '10', forgotten: true, scan_status: 'complete',
        residual_hints: url.includes('/80/') ? [] : relatedArchived ? hints.filter((hint) => hint.kind === 'block') : hints,
      } : undefined })
    })
    const panel = await mount(true, [source])
    try {
      const archive = [...panel.host.querySelectorAll<HTMLButtonElement>('button')].find((button) => button.textContent?.trim() === '归档')!
      archive.click(); await settle()
      expect(post).not.toHaveBeenCalled()
      await warning.mock.calls[0][0].onPositiveClick(); await settle()
      expect(post).toHaveBeenCalledWith('/users/me/memories/10/forget', null, { params: { agent_id: 'a', project_id: project } })
      expect(panel.host.querySelector('.memory-residual-list img')).toBeNull()
      expect(panel.host.querySelector('.memory-residuals')?.textContent).toContain('可能')
      expect(patch).not.toHaveBeenCalled()
      const edit = [...panel.host.querySelectorAll<HTMLButtonElement>('.memory-residuals button')].find((button) => button.textContent?.includes('编辑相关块'))!
      edit.click(); await settle()
      expect(document.querySelector<HTMLTextAreaElement>('.n-modal textarea')!.value).toBe('个人背景')
      expect(patch).not.toHaveBeenCalled()
      const related = [...panel.host.querySelectorAll<HTMLButtonElement>('.memory-residuals button')].find((button) => button.textContent?.includes('一并归档'))!
      related.click(); await settle()
      expect(post.mock.calls.some(([url]) => url === '/users/me/memories/80/forget')).toBe(false)
      await warning.mock.calls[1][0].onPositiveClick(); await settle()
      expect(post).toHaveBeenCalledWith('/users/me/memories/80/forget', null, { params: { agent_id: 'a', project_id: project } })
      expect(panel.host.querySelector('.memory-residual-list')?.textContent).not.toContain('GRCh38 会话进展')
      expect(panel.host.querySelector('.memory-residual-list')?.textContent).toContain('<img src=x onerror=alert(1)>')
    } finally { panel.close() }
  })

  it('distinguishes an incomplete scan from successful complete erasure', async () => {
    post.mockResolvedValue({ data: { memory_id: '10', forgotten: true, scan_status: 'failed', residual_hints: [] } })
    const panel = await mount(true, [{ id: 10, scope: 'summary', content: 'source', confidence: 1, status: 'active' }])
    try {
      const archive = [...panel.host.querySelectorAll<HTMLButtonElement>('button')].find((button) => button.textContent?.trim() === '归档')!
      archive.click(); await settle()
      await warning.mock.calls[0][0].onPositiveClick(); await settle()
      expect(panel.host.querySelector('.memory-residuals')?.textContent).toContain('检查失败')
      expect(panel.host.querySelector('.memory-residuals')?.textContent).not.toContain('已彻底清除')
    } finally { panel.close() }
  })

})
