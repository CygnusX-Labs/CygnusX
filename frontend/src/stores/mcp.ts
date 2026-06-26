import { defineStore } from 'pinia'
import { ref } from 'vue'
import apiClient from '@/api/client'
import type { MCPServer, MCPTool } from '@/types'

export const useMCPStore = defineStore('mcp', () => {
  const servers = ref<MCPServer[]>([])
  const toolsCache = ref<Record<string, MCPTool[]>>({})
  const loading = ref(false)

  async function fetchServers() {
    loading.value = true
    try {
      const res = await apiClient.get<MCPServer[]>('/mcp/servers')
      servers.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function fetchTools(serverId: string): Promise<MCPTool[]> {
    const res = await apiClient.get<MCPTool[]>(`/mcp/servers/${serverId}/tools`)
    toolsCache.value[serverId] = res.data
    return res.data
  }

  async function invokeTool(
    serverId: string,
    toolName: string,
    args: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    const res = await apiClient.post(`/mcp/servers/${serverId}/tools/${toolName}/invoke`, {
      tool_name: toolName,
      arguments: args,
    })
    return res.data
  }

  return {
    servers,
    toolsCache,
    loading,
    fetchServers,
    fetchTools,
    invokeTool,
  }
})
