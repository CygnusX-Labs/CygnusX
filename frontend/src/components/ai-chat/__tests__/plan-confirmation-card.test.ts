// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { NMessageProvider } from 'naive-ui'
import PlanConfirmationCard from '@/components/ai-chat/PlanConfirmationCard.vue'
import type { PlanConfirmation } from '@/components/ai-chat/types'

let cleanup: (() => void) | undefined
afterEach(() => cleanup?.())

function mountCard(plan: PlanConfirmation) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const root = document.createElement('div')
  document.body.appendChild(root)
  const app = createApp({
    render: () => h(NMessageProvider, null, {
      default: () => h(PlanConfirmationCard, { plan, sessionId: 'session-1' }),
    }),
  })
  app.use(pinia)
  app.mount(root)
  cleanup = () => { app.unmount(); root.remove() }
  return root
}

const plan: PlanConfirmation = {
  runId: 'run-1',
  title: '转录组分析执行计划',
  summary: '先完成输入核验，再进入两个执行波次。',
  planPath: 'output/overdrive/session-1/run-1/plan.md',
  planVersion: 1,
  planHash: 'sha256:test',
  waveCount: 2,
  agents: [{ agentId: 'agent-data', name: '数据管家', reason: '核验输入' }],
  serialPreflight: ['检查样本表与 FASTQ 配对'],
  risks: ['分组元数据可能不完整'],
  approvalPoints: ['安装缺失的分析依赖'],
  deliverables: ['质控报告', '差异表达结果'],
  actions: ['approve', 'revise', 'cancel'],
  status: 'pending',
}

describe('PlanConfirmationCard', () => {
  it('呈现摘要、风险、Agent、波次、交付物和三个决策入口', () => {
    const root = mountCard({ ...plan })
    expect(root.textContent).toContain('转录组分析执行计划')
    expect(root.textContent).toContain('预计波次')
    expect(root.textContent).toContain('数据管家')
    expect(root.textContent).toContain('分组元数据可能不完整')
    expect(root.textContent).toContain('差异表达结果')
    expect(root.textContent).toContain('预览 plan.md')
    expect(root.textContent).toContain('确认并执行')
    expect(root.textContent).toContain('提出修改')
    expect(root.textContent).toContain('取消任务')
  })

  it('提出修改后显示具有可访问名称的意见输入框', async () => {
    const root = mountCard({ ...plan })
    const revise = [...root.querySelectorAll('button')].find((button) => button.textContent?.includes('提出修改'))
    revise?.click()
    await nextTick()
    expect(root.querySelector('textarea[aria-label="计划修改意见"]')).not.toBeNull()
    expect(root.textContent).toContain('提交修改意见')
  })
})
