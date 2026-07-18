<script setup lang="ts">
import { NButton, NIcon, NTooltip } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'

const router = useRouter()

withDefaults(defineProps<{
  title: string
  subtitle?: string
  backTo?: string
  backLabel?: string
}>(), {
  subtitle: '',
  backTo: '',
  backLabel: '返回上一页',
})
</script>

<template>
  <header class="page-header">
    <div class="page-header-main">
      <NTooltip v-if="backTo" placement="bottom" :delay="300">
        <template #trigger>
          <NButton
            circle
            secondary
            size="large"
            class="page-header-back"
            :aria-label="backLabel"
            @click="router.push(backTo)"
          >
            <template #icon><NIcon :size="22"><ArrowBackOutline /></NIcon></template>
          </NButton>
        </template>
        {{ backLabel }}
      </NTooltip>
      <div v-if="$slots.leading" class="page-header-leading">
        <slot name="leading" />
      </div>
      <div class="page-header-copy">
        <h1>{{ title }}</h1>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
    </div>
    <div v-if="$slots.actions" class="page-header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.page-header-main {
  display: flex;
  align-items: flex-start;
  min-width: 0;
  gap: 8px;
}

.page-header-back {
  flex: 0 0 auto;
}

.page-header-leading {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  padding-top: 2px;
}

.page-header-copy h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.33;
}

.page-header-copy p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.57;
}

.page-header-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 10px;
}

@media (max-width: 640px) {
  .page-header {
    flex-direction: column;
    gap: 12px;
  }

  .page-header-actions {
    width: 100%;
  }
}
</style>
