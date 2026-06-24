<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NGrid, NGridItem, NStatistic, NButton, NSpace } from 'naive-ui'
import apiClient from '@/api/client'

const healthStatus = ref<string>('检测中...')

onMounted(async () => {
  try {
    const res = await apiClient.get('/../health')
    healthStatus.value = res.data.status === 'ok' ? '正常运行' : '异常'
  } catch {
    healthStatus.value = '后端未连接'
  }
})
</script>

<template>
  <NSpace vertical :size="24">
    <NCard title="平台概览">
      <NGrid :cols="4" :x-gap="16" :y-gap="16" responsive="screen">
        <NGridItem>
          <NStatistic label="运行状态" :value="healthStatus" />
        </NGridItem>
        <NGridItem>
          <NStatistic label="分析流程" :value="6" />
        </NGridItem>
        <NGridItem>
          <NStatistic label="运行中任务" :value="0" />
        </NGridItem>
        <NGridItem>
          <NStatistic label="数据样本" :value="0" />
        </NGridItem>
      </NGrid>
    </NCard>

    <NCard title="快速开始">
      <NSpace>
        <NButton type="primary">提交分析任务</NButton>
        <NButton>上传样本数据</NButton>
        <NButton>浏览分析流程</NButton>
      </NSpace>
    </NCard>

    <NCard title="最近任务">
      <div style="color: #999; padding: 24px; text-align: center">
        暂无任务，点击上方按钮提交
      </div>
    </NCard>
  </NSpace>
</template>
