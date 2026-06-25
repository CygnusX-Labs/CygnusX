<script setup lang="ts">
import type { FlowDefinition } from '@/types'
import { apiClient } from '@/api'
import { NButton, NCard, NEmpty, NGrid, NGridItem, NSpace, NSpin, NTag } from 'naive-ui'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const flows = ref<FlowDefinition[]>([])
const loading = ref(false)

async function fetchFlows() {
  loading.value = true
  try {
    const res = await apiClient.get<{ items: FlowDefinition[]; total: number }>('/flows')
    flows.value = res.data.items
  } finally {
    loading.value = false
  }
}

function goToSubmit(flowId: string) {
  router.push({ name: 'flow-submit', params: { flowId } })
}

onMounted(fetchFlows)
</script>

<template>
  <div class="flows-view">
    <h2>分析流程</h2>
    <NSpin :show="loading">
      <NGrid v-if="flows.length" :cols="3" :x-gap="16" :y-gap="16">
        <NGridItem v-for="flow in flows" :key="flow.id">
          <NCard :title="flow.name" hoverable>
            <p>{{ flow.description }}</p>
            <NSpace>
              <NTag type="info">{{ flow.category }}</NTag>
              <NTag type="success">v{{ flow.version }}</NTag>
            </NSpace>
            <template #action>
              <NButton type="primary" @click="goToSubmit(flow.id)">提交任务</NButton>
            </template>
          </NCard>
        </NGridItem>
      </NGrid>
      <NEmpty v-else description="暂无可用流程" />
    </NSpin>
  </div>
</template>

<style scoped>
.flows-view {
  padding: 24px;
}
</style>
