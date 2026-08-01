import type { AgentTeamsEvent } from '@/api/agentTeams'

/** Merge Bridge event pages without losing history or duplicating cursor replays. */
export function mergeAgentTeamsEvents(
  current: AgentTeamsEvent[],
  incoming: AgentTeamsEvent[],
): AgentTeamsEvent[] {
  const knownIds = new Set(current.map((event) => event.event_id))
  return [...current, ...incoming.filter((event) => !knownIds.has(event.event_id))]
}

/** Background polling must not refresh a hidden browser tab. */
export function shouldPollAgentTeamsCase(visibilityState: DocumentVisibilityState): boolean {
  return visibilityState === 'visible'
}
