import { defineStore } from 'pinia'
import { ref } from 'vue'
import { agentTeamsApi, type AgentTeamsCase } from '@/api/agentTeams'

export const useAgentTeamsStore = defineStore('agentTeams', () => {
  const cases = ref<Record<string, AgentTeamsCase>>({})

  async function refreshCase(caseId: string): Promise<AgentTeamsCase> {
    const value = await agentTeamsApi.getCase(caseId)
    cases.value = { ...cases.value, [caseId]: value }
    return value
  }

  return { cases, refreshCase }
})
