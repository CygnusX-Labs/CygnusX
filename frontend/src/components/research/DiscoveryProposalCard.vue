<script setup lang="ts">
import type { DiscoveryProposal } from '@/api/researchAgent'
import { NButton } from 'naive-ui'

defineProps<{ proposal: DiscoveryProposal }>()
defineEmits<{ inspect: [accession: string]; prepareImport: [accession: string] }>()
</script>

<template>
  <article class="proposal-card">
    <div class="proposal-heading">
      <div>
        <p class="proposal-source">{{ proposal.source }}</p>
        <h3>{{ proposal.title || '未命名发现' }}</h3>
      </div>
      <code v-if="proposal.accession">{{ proposal.accession }}</code>
    </div>
    <p v-if="proposal.summary" class="proposal-summary">{{ proposal.summary }}</p>
    <dl class="proposal-meta">
      <template v-if="proposal.organism"><dt>物种</dt><dd>{{ proposal.organism }}</dd></template>
      <template v-if="proposal.assay_type"><dt>实验</dt><dd>{{ proposal.assay_type }}</dd></template>
      <template v-if="proposal.sample_count !== null"><dt>样本</dt><dd>{{ proposal.sample_count }}</dd></template>
      <template v-if="proposal.evidence_refs.length"><dt>证据</dt><dd>{{ proposal.evidence_refs.join(', ') }}</dd></template>
    </dl>
    <div class="proposal-footer">
      <span>未将此发现登记为数据集或任务</span>
      <NButton v-if="proposal.accession" size="small" @click="$emit('inspect', proposal.accession)">检查获取方式</NButton>
      <NButton v-if="proposal.accession" size="small" @click="$emit('prepareImport', proposal.accession)">查看数据与导入预案</NButton>
      <a v-for="link in proposal.source_links" :key="link" :href="link" target="_blank" rel="noopener noreferrer">查看来源</a>
    </div>
  </article>
</template>

<style scoped>
.proposal-card { border: 1px solid var(--neutral-border); border-radius: 8px; padding: 14px; background: var(--neutral-card); }
.proposal-heading { display: flex; gap: 12px; align-items: flex-start; justify-content: space-between; }
.proposal-heading h3 { margin: 2px 0 0; font-size: 15px; overflow-wrap: anywhere; }
.proposal-source { margin: 0; color: var(--primary-color); font-size: 12px; font-weight: 600; }
.proposal-heading code { flex: none; max-width: 42%; overflow-wrap: anywhere; color: var(--neutral-text-secondary); }
.proposal-summary { margin: 10px 0; color: var(--neutral-text-secondary); white-space: pre-wrap; overflow-wrap: anywhere; }
.proposal-meta { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 5px 10px; margin: 0; font-size: 12px; }
.proposal-meta dt { color: var(--neutral-text-secondary); }
.proposal-meta dd { margin: 0; overflow-wrap: anywhere; }
.proposal-footer { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; color: var(--neutral-text-secondary); font-size: 12px; }
.proposal-footer a { color: var(--primary-color); }
</style>
