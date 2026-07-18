<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NResult, NSpin, NTag } from 'naive-ui'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { studioApi, type SharedStudioSession } from '@/api/studio'

const route = useRoute()
const token = computed(() => String(route.params.token || ''))
const loading = ref(true)
const snapshot = ref<SharedStudioSession | null>(null)
const failed = ref(false)

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

function printPage() {
  window.print()
}

onMounted(async () => {
  try {
    snapshot.value = await studioApi.getSharedSession(token.value)
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="shared-studio">
    <div v-if="loading" class="center-state" role="status" aria-live="polite" aria-busy="true">
      <n-spin size="large" />
      <p>正在加载只读工作台…</p>
    </div>

    <n-result
      v-else-if="failed || !snapshot"
      status="404"
      title="分享链接不存在或已失效"
      description="链接可能已过期、被撤销或输入不完整。"
      class="result"
    />

    <template v-else>
      <header class="page-header">
        <div>
          <div class="brand">OmicStudio · 只读分享</div>
          <h1>{{ snapshot.title }}</h1>
          <div class="meta">
            <n-tag size="small" :bordered="false">{{ snapshot.agent_id || '未标注 Agent' }}</n-tag>
            <span>创建于 {{ formatTime(snapshot.created_at) }}</span>
            <span>链接有效至 {{ formatTime(snapshot.expires_at) }}</span>
          </div>
        </div>
        <n-button class="no-print" @click="printPage">打印 / 保存为 PDF</n-button>
      </header>

      <section class="section">
        <h2>对话记录</h2>
        <div v-if="snapshot.messages.length" class="messages">
          <article
            v-for="(item, index) in snapshot.messages"
            :key="`${item.created_at}-${index}`"
            class="message-card"
            :class="item.role"
          >
            <header>
              <strong>{{ item.role === 'user' ? '用户' : 'AI 助手' }}</strong>
              <time>{{ formatTime(item.created_at) }}</time>
            </header>
            <MarkdownRenderer :content="item.content" />
          </article>
        </div>
        <p v-else class="empty">暂无可分享的对话内容</p>
      </section>

      <section class="section">
        <h2>工作区产物</h2>
        <div v-if="snapshot.artifacts.length" class="artifacts">
          <a
            v-for="artifact in snapshot.artifacts"
            :key="artifact.path"
            :href="studioApi.sharedArtifactUrl(token, artifact.path)"
            class="artifact"
            target="_blank"
            rel="noopener noreferrer"
          >
            <code>{{ artifact.path }}</code>
            <span>{{ artifact.size.toLocaleString() }} bytes</span>
          </a>
        </div>
        <p v-else class="empty">暂无 output 产物</p>
      </section>

      <footer>该页面为只读快照，不提供代码执行、文件写入或能力加载入口。</footer>
    </template>
  </main>
</template>

<style scoped>
.shared-studio {
  min-height: 100vh;
  padding: 36px clamp(20px, 5vw, 72px) 64px;
  color: var(--neutral-text-1, #172033);
  background: var(--neutral-bg-1, #f7f8fa);
}
.center-state,
.result {
  min-height: 70vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--neutral-text-3, #667085);
}
.page-header,
.section,
footer {
  max-width: 980px;
  margin-inline: auto;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
}
.brand {
  color: var(--primary-color, #3b82f6);
  font-weight: 700;
  letter-spacing: .04em;
}
h1 {
  margin: 8px 0 10px;
  font-size: clamp(26px, 4vw, 42px);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  color: var(--neutral-text-3, #667085);
  font-size: 13px;
}
.section {
  margin-top: 26px;
}
.section h2 {
  margin-bottom: 12px;
  font-size: 18px;
}
.messages,
.artifacts {
  display: grid;
  gap: 12px;
}
.message-card,
.artifact {
  border: 1px solid var(--neutral-border, #e4e7ec);
  border-radius: 12px;
  background: var(--neutral-bg-2, #fff);
}
.message-card {
  padding: 14px 16px;
  break-inside: avoid;
}
.message-card.assistant {
  border-left: 3px solid var(--primary-color, #3b82f6);
}
.message-card > header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}
time,
.artifact span,
.empty,
footer {
  color: var(--neutral-text-3, #667085);
  font-size: 12px;
}
.artifact {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  color: inherit;
  text-decoration: none;
}
.artifact:hover {
  border-color: var(--primary-color, #3b82f6);
}
footer {
  margin-top: 36px;
  text-align: center;
}
@media print {
  .shared-studio {
    padding: 0;
    background: white;
  }
  .no-print,
  footer {
    display: none;
  }
  .message-card,
  .artifact {
    box-shadow: none;
  }
}
</style>
