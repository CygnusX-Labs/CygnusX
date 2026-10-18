import apiClient from '@/api/client'

export interface DownloadCapabilities {
  schema_version: string
  write_enabled: boolean
  runtime_status: string
  sources: {
    source_type: string
    supported_methods: string[]
    binary_name: string | null
    binary_version: string | null
    runtime_readiness: string
    limitations: string[]
  }[]
}

export async function getDownloadCapabilities(): Promise<DownloadCapabilities> {
  return (await apiClient.get<DownloadCapabilities>('/downloads/capabilities')).data
}
