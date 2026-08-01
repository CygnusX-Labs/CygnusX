import { describe, expect, it } from 'vitest'
import type { AgentTeamsEvent } from '@/api/agentTeams'
import { mergeAgentTeamsEvents, shouldPollAgentTeamsCase } from './agentTeamsState'

const event = (eventId: string): AgentTeamsEvent => ({
  event_id: eventId,
  recorded_at: '2026-07-31T12:00:00Z',
  case_id: 'bioops_case',
  actor: 'data-steward',
  event_type: 'skill.finished',
  payload: {},
})

describe('agentTeamsState', () => {
  it('preserves prior events and ignores cursor replay duplicates', () => {
    expect(mergeAgentTeamsEvents([event('one'), event('two')], [event('two'), event('three')]))
      .toEqual([event('one'), event('two'), event('three')])
  })

  it('polls only while the browser page is visible', () => {
    expect(shouldPollAgentTeamsCase('visible')).toBe(true)
    expect(shouldPollAgentTeamsCase('hidden')).toBe(false)
  })
})
