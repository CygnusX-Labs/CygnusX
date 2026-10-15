<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NEmpty, NSpace, NTag } from 'naive-ui'
import { researchDeliveryApi, type ProjectDelivery } from '@/api/researchDelivery'
const props = defineProps<{ projectId: string }>()
const delivery = ref<ProjectDelivery | null>(null)
const error = ref('')
const loading = ref(false)
let generation = 0
let pending: AbortController | null = null
async function load() {
  const current = ++generation
  pending?.abort()
  pending = new AbortController()
  delivery.value = null
  error.value = ''
  loading.value = true
  try {
    const result = await researchDeliveryApi.project(props.projectId, pending.signal)
    if (current === generation && result.project_id === props.projectId) delivery.value = result
  } catch {
    if (current === generation) error.value = '科研交付记录暂不可用；可能尚未启用或授权已变更。'
  } finally { if (current === generation) loading.value = false }
}
async function downloadArtifact(fileId: string) {
  const current = generation
  const project = props.projectId
  try {
    const blob = await researchDeliveryApi.downloadArtifact(fileId)
    if (current !== generation || project !== props.projectId) return
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `artifact-${fileId}`
    link.click()
    URL.revokeObjectURL(url)
  } catch { if (current === generation) error.value = '产物不可下载，请刷新核验当前权限与文件状态。' }
}
watch(() => props.projectId, load, { immediate: true })
onBeforeUnmount(() => { generation++; pending?.abort() })
</script>
<template>
  <NCard title="科研执行与交付链" size="small">
    <NSpace vertical>
      <NButton size="small" :loading="loading" @click="load">刷新交付记录</NButton>
      <NAlert v-if="error" type="info">{{ error }}</NAlert>
      <template v-if="delivery">
        <NAlert type="warning">运行准入：{{ delivery.runtime_admission }}。分析、产物、证据及报告状态分别核验。</NAlert>
        <NEmpty v-if="!delivery.datasets.length" description="尚无 Dataset 交付记录" />
        <NCard v-for="dataset in delivery.datasets" :key="dataset.dataset_version_id" size="small" title="Dataset → 冻结输入 → 分析 → 产物 → 双报告">
          <p>数据版本 {{ dataset.dataset_version_id }}</p>
          <p>冻结输入 SHA-256：{{ dataset.handoff_hash || '尚未冻结' }}</p>
          <p v-for="gap in dataset.gaps" :key="gap">{{ gap }}</p>
          <div v-for="(analysis, index) in dataset.analyses" :key="analysis.task_id || index">
            <template v-if="analysis.task_id !== null">
              <RouterLink :to="`/tasks/${analysis.task_id}`">分析任务 {{ analysis.task_id }}</RouterLink>
              <p>来源：{{ analysis.source.filter(source => source.accession).map(source => `${source.repository || 'UNKNOWN'} ${source.accession}`).join('、') || 'UNKNOWN' }}</p>
              <p>流程 {{ analysis.flow.id }} · 声明版本 {{ analysis.flow.version || 'UNKNOWN' }} · 参数摘要 {{ analysis.parameters_sha256 || 'UNKNOWN' }}</p>
              <p>已记录分析参数：{{ JSON.stringify(analysis.analysis_parameters) }}</p>
              <p>人工分组：{{ analysis.samples.map(sample => `${sample.sample_key || 'UNKNOWN'}: ${sample.group || 'UNKNOWN'} (${sample.group_confirmed ? '已确认' : '待确认'})`).join('、') || 'UNKNOWN' }}</p>
              <NSpace>
                <NTag>分析 {{ analysis.compute_state }}</NTag><NTag>输入 {{ analysis.input_integrity }}</NTag>
                <NTag>产物 {{ analysis.result_integrity }}</NTag><NTag>证据 {{ analysis.evidence_state }}</NTag><NTag>交付 {{ analysis.delivery_state }}</NTag>
              </NSpace>
              <p v-for="artifact in analysis.artifacts" :key="artifact.logical_name">
                {{ artifact.logical_name }} · {{ artifact.integrity }} · SHA-256 {{ artifact.sha256 || '未知' }}
                <NButton v-if="artifact.file_record_id" size="tiny" :disabled="artifact.integrity !== 'VERIFIED'" @click="downloadArtifact(artifact.file_record_id)">下载产物</NButton>
              </p>
              <p v-for="report in analysis.reports" :key="report.report_id">
                <RouterLink :to="{path: '/reports', query: {reportId: report.report_id}}">{{ report.kind === 'scientific' ? '科学报告' : report.kind === 'reproducibility' ? '可复现执行证据报告' : '交付包' }}</RouterLink>
                · {{ report.state }} · {{ report.integrity }}
              </p>
              <p v-for="job in analysis.report_jobs" :key="String(job.job_id)">报告生成：{{ job.kind }} · {{ job.state }} · {{ job.error_code || '—' }}</p>
              <p v-if="analysis.gaps.length">证据缺口：{{ analysis.gaps.join('、') }}</p>
            </template>
            <p v-else>分析尚未提交：{{ analysis.state }}</p>
          </div>
        </NCard>
        <p v-if="delivery.truncated">当前仅展示部分记录，请进入具体数据版本查询。</p>
      </template>
    </NSpace>
  </NCard>
</template>
