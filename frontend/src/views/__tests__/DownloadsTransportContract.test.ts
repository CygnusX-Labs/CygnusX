// @vitest-environment jsdom
import { createApp, defineComponent, h, inject, nextTick, provide, toRef, type Ref } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import DownloadsView from '@/views/DownloadsView.vue'
import apiClient from '@/api/client'

const messages = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }))
const push = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('@/components/PageHeader.vue', () => ({ default: { render: () => null } }))
vi.mock('naive-ui', () => {
  const passthrough = defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    useMessage: () => messages,
    NAlert: passthrough, NIcon: passthrough, NSpin: passthrough, NPopconfirm: passthrough,
    NButton: defineComponent({ setup: (_, { slots, attrs }) => () => h('button', { ...attrs, type: 'button' }, slots.default?.()) }),
    NSelect: defineComponent({
      props: ['value', 'options'], emits: ['update:value'],
      setup: (props, { emit }) => () => h('select', {
        value: props.value,
        onChange: (event: Event) => emit('update:value', (event.target as HTMLSelectElement).value),
      }, props.options.map((option: { label: string; value: string }) => h('option', { value: option.value }, option.label))),
    }),
    NTabs: defineComponent({
      props: ['value'], emits: ['update:value'],
      setup(props, { slots, emit }) {
        provide('download-active-tab', toRef(props, 'value'))
        return () => {
          const panes = slots.default?.() ?? []
          return h('div', [
            h('nav', panes.filter(pane => pane.props?.name).map(pane => h('button', {
              role: 'tab', onClick: () => emit('update:value', pane.props?.name),
            }, pane.props?.name))),
            ...panes,
          ])
        }
      },
    }),
    NTabPane: defineComponent({
      props: ['name'],
      setup(props, { slots }) {
        const selected = inject<Ref<string>>('download-active-tab')!
        return () => selected.value === props.name ? h('section', slots.default?.()) : null
      },
    }),
  }
})

async function settle() {
  for (let i = 0; i < 6; i++) { await Promise.resolve(); await nextTick() }
}
function mount() {
  const host = document.createElement('div')
  const app = createApp(DownloadsView)
  app.directive('animate-list', {})
  app.mount(host)
  return { host, close: () => app.unmount() }
}
function tab(host: HTMLElement, value: string) {
  const button = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(el => el.textContent === value)!
  button.click()
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(apiClient.get).mockImplementation(async (path) => ({ data: path === '/downloads/capabilities'
    ? { write_enabled: true, sources: [{ source_type: 'sra', supported_methods: ['aws', 'ftp'] }] }
    : { items: [], total: 0 } }))
  vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 'real-response-task-id' } })
})
it('submits only the platform AWS/FTP contract, with no inactive filters', async () => {
  const card = mount()
  try {
    await settle()
    const method = card.host.querySelector<HTMLSelectElement>('select')!
    expect([...method.options].map(option => option.value)).toEqual(['aws', 'ftp'])
    expect(card.host.textContent).toContain('样本与 Run 筛选暂不可用')
    expect(card.host.querySelector('input[placeholder*="SAMN"]')).toBeNull()
    const accession = card.host.querySelector<HTMLTextAreaElement>('textarea')!
    accession.value = 'SRR123'
    accession.dispatchEvent(new Event('input', { bubbles: true }))
    method.value = 'ftp'
    method.dispatchEvent(new Event('change', { bubbles: true }))
    await settle()
    const submit = [...card.host.querySelectorAll<HTMLButtonElement>('button')].find(button => button.textContent?.includes('提交拉取任务'))!
    submit.click(); await settle()
    expect(apiClient.post).toHaveBeenCalledWith('/downloads', {
      source: 'sra', accession: 'SRR123', download_method: 'ftp', target_directory: '',
    })
    expect(push).toHaveBeenCalledWith('/tasks/real-response-task-id')
  } finally { card.close() }
})
it('keeps all four entries but prevents cloud-drive extraction from being submitted', async () => {
  const card = mount()
  try {
    await settle()
    expect(card.host.querySelectorAll('[role="tab"]')).toHaveLength(4)
    tab(card.host, 'cloud-drive'); await settle()
    expect(card.host.textContent).toContain('提取尚未接入')
    const unavailable = [...card.host.querySelectorAll<HTMLButtonElement>('section button')].find(button => button.textContent?.includes('暂未接入'))!
    expect(unavailable.disabled).toBe(true)
    unavailable.click(); await settle()
    expect(apiClient.post).not.toHaveBeenCalled()
    tab(card.host, 'direct-link'); await settle()
    expect(card.host.textContent).toContain('暂不支持 FTPS')
  } finally { card.close() }
})
it('does not turn a declared method into permission when runtime admission is closed', async () => {
  vi.mocked(apiClient.get).mockImplementation(async path => ({ data: path === '/downloads/capabilities'
    ? { write_enabled: false, sources: [{ source_type: 'sra', supported_methods: ['aws', 'ftp'] }] }
    : { items: [], total: 0 } }))
  const card = mount()
  try {
    await settle()
    const submit = [...card.host.querySelectorAll<HTMLButtonElement>('button')].find(button => button.textContent?.includes('提交拉取任务'))!
    expect(submit.disabled).toBe(true)
    submit.click(); await settle()
    expect(apiClient.post).not.toHaveBeenCalled()
    expect(card.host.textContent).toContain('暂不开放执行')
  } finally { card.close() }
})
