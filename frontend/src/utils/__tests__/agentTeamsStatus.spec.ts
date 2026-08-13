import { describe, expect, it } from 'vitest'
import {
  agentTeamsCaseCategory,
  agentTeamsCaseStageMap,
  agentTeamsFailedStatuses,
  canSendRoomMessage,
} from '@/utils/agentTeamsStatus'
import type { AgentTeamsCaseStatus } from '@/api/agentTeams'

describe('agentTeamsCaseStageMap', () => {
  it('covers every case status exactly once', () => {
    const statuses = Object.keys(agentTeamsCaseStageMap) as AgentTeamsCaseStatus[]
    expect(statuses).toHaveLength(16)
  })

  it('maps statuses onto the five stages of the case lifecycle', () => {
    expect(agentTeamsCaseStageMap.planning_running).toBe('plan')
    expect(agentTeamsCaseStageMap.preflight_blocked).toBe('plan')
    expect(agentTeamsCaseStageMap.approval_pending).toBe('approval')
    expect(agentTeamsCaseStageMap.executing).toBe('execution')
    expect(agentTeamsCaseStageMap.execution_failed).toBe('execution')
    expect(agentTeamsCaseStageMap.quality_running).toBe('quality')
    expect(agentTeamsCaseStageMap.delivery_ready).toBe('delivery')
    expect(agentTeamsCaseStageMap.closed).toBe('delivery')
  })
})

describe('agentTeamsCaseCategory', () => {
  it('groups statuses into sidebar filter chips', () => {
    expect(agentTeamsCaseCategory('approval_pending')).toBe('approval')
    expect(agentTeamsCaseCategory('delivery_ready')).toBe('done')
    expect(agentTeamsCaseCategory('closed')).toBe('done')
    expect(agentTeamsCaseCategory('execution_failed')).toBe('failed')
    expect(agentTeamsCaseCategory('cancelled')).toBe('failed')
    expect(agentTeamsCaseCategory('executing')).toBe('active')
    expect(agentTeamsCaseCategory('queued')).toBe('active')
  })

  it('keeps failed statuses inside the failed category', () => {
    for (const status of agentTeamsFailedStatuses) {
      expect(agentTeamsCaseCategory(status)).toBe('failed')
    }
  })
})

describe('canSendRoomMessage', () => {
  it('allows sending while the case is not terminal', () => {
    expect(canSendRoomMessage('executing')).toBe(true)
    expect(canSendRoomMessage('approval_pending')).toBe(true)
    expect(canSendRoomMessage('delivery_ready')).toBe(true)
  })

  it('allows sending for terminal cases too (post-cancel/close follow-up)', () => {
    expect(canSendRoomMessage('closed')).toBe(true)
    expect(canSendRoomMessage('cancelled')).toBe(true)
  })

  it('blocks sending only when no case is selected', () => {
    expect(canSendRoomMessage('')).toBe(false)
    expect(canSendRoomMessage(null)).toBe(false)
    expect(canSendRoomMessage(undefined)).toBe(false)
  })
})
