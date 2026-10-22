<script setup lang="ts">
import { NAlert, NCard, NSkeleton } from 'naive-ui'
import type { ProjectCapability } from '@/api/projects'
defineProps<{ title: string; capability?: ProjectCapability; error?: string }>()
</script>

<template>
  <slot v-if="capability?.allowed" />
  <NCard v-else :title="title" size="small">
    <NAlert v-if="error" type="warning">{{ error }}</NAlert>
    <NAlert v-else-if="capability && !capability.enabled" type="info">服务未启用：{{ title }}尚未开放。</NAlert>
    <NAlert v-else-if="capability" type="warning">当前用户无权限：无法访问{{ title }}，请联系管理员核对授权。</NAlert>
    <NSkeleton v-else text :repeat="2" />
  </NCard>
</template>
