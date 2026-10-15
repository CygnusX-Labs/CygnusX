// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentToolProposalCard from '../AgentToolProposalCard.vue'
import { agentToolsApi, type ToolProposal } from '@/api/agentTools'

async function flushPromises() { for (let i = 0; i < 4; i++) { await Promise.resolve(); await nextTick() } }
function mountCard(proposal: ToolProposal) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp({ render: () => h(AgentToolProposalCard, { proposal }) })
  app.mount(host)
  return { host, destroy: () => { app.unmount(); host.remove() } }
}

vi.mock('@/api/agentTools', () => ({ agentToolsApi: { decide: vi.fn() } }))
const proposal: ToolProposal = {
  proposal_id: 'proposal-a', conversation_id: 'session-a', operation: 'downloads.submit',
  project_id: 'project-a', parameters_hash: 'immutable-digest',
  normalized_parameters: { accession: 'SRR123', target_directory: 'projects/a/downloads' },
  preview: { bytes_estimate: null }, confirmation_id: 'confirmation-a',
  expires_at: '2099-01-01T00:00:00Z', state: 'PENDING', write_enabled: false,
  gate: 'WRITE_GATE_BLOCKED',
}

describe('shared proposal card', () => {
  beforeEach(() => vi.clearAllMocks())
  it('shows exact immutable params, records human approval without submitting', async () => {
    vi.mocked(agentToolsApi.decide).mockResolvedValue({ state: 'APPROVED', write_enabled: false })
    const wrapper = mountCard(proposal)
    expect(wrapper.host.textContent).toContain('SRR123')
    expect(wrapper.host.textContent).toContain('immutable-digest')
    const buttons = wrapper.host.querySelectorAll('button')
    expect(buttons[2].getAttribute('disabled')).not.toBeNull()
    buttons[0].click()
    await flushPromises()
    expect(agentToolsApi.decide).toHaveBeenCalledWith('session-a', 'proposal-a', true)
    expect(wrapper.host.textContent).toContain('APPROVED')
    expect(wrapper.host.textContent).toContain('不会创建下载或分析任务')
    wrapper.destroy()
  })
  it('failure remains visible and does not silently retry', async () => {
    vi.mocked(agentToolsApi.decide).mockRejectedValue(new Error('offline'))
    const wrapper = mountCard(proposal)
    wrapper.host.querySelector('button')!.click()
    await flushPromises()
    expect(wrapper.host.querySelector('[role="alert"]')?.textContent).toContain('未提交任务')
    expect(agentToolsApi.decide).toHaveBeenCalledTimes(1)
    wrapper.destroy()
  })
  it('expired or rejected proposal cannot approve', () => {
    for (const value of [{ ...proposal, expires_at: '2000-01-01T00:00:00Z' }, { ...proposal, state: 'REJECTED' }]) {
      const wrapper = mountCard(value)
      expect(wrapper.host.querySelector('button')!.getAttribute('disabled')).not.toBeNull()
      wrapper.destroy()
    }
  })
})
