// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { createApp, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { agentTeamsStatusLabel } from '@/utils/agentTeamsStatus'
import AgentTeamsCaseCard from '../AgentTeamsCaseCard.vue'

vi.mock('@/api/agentTeams', () => ({
  agentTeamsApi: { getCase: vi.fn() },
}))

describe('AgentTeamsCaseCard', () => {
  it('renders the shared stage label and approval action rail', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/agent-teams/cases/:id', component: { template: '<div />' } }],
    })
    const host = document.createElement('div')
    const app = createApp({
      render: () => h(AgentTeamsCaseCard, {
        caseInfo: {
          case_id: 'case-1',
          title: 'RNA-seq 全流程交付',
          status: 'approval_pending',
          next_actor: '审批人',
          case_url: '/agent-teams/cases/case-1',
        },
      }),
    })
    app.use(pinia)
    app.use(router)
    app.mount(host)

    expect(host.textContent).toContain(agentTeamsStatusLabel.approval_pending)
    expect(host.textContent).toContain('审批待处理')
    expect(host.textContent).toContain('打开 Case')

    app.unmount()
  })
})
