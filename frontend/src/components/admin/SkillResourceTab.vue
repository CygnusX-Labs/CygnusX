<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  NButton, NIcon, NTag, NSwitch, NGrid, NGridItem, NModal, NTabs, NTabPane,
  NInput, NSpace, NPopconfirm, useMessage,
} from 'naive-ui'
import { AddOutline, TrashOutline, LinkOutline, CodeSlashOutline } from '@vicons/ionicons5'
import { useAgentHubStore } from '@/stores/agentHub'
import type { SkillItem } from '@/types/agent'

const message = useMessage()
const store = useAgentHubStore()

const showImport = ref(false)
const importMode = ref<'url' | 'json'>('url')
const urlInput = ref('')
const jsonInput = ref('')
const pulling = ref(false)

const sampleJson = `{
  "name": "差异表达分析",
  "description": "基于 DESeq2 的差异表达分析技能",
  "icon": "🧬",
  "category": "数据处理",
  "prompt": "你擅长使用 DESeq2 进行差异表达分析..."
}`

onMounted(() => {
  store.fetchSkills(true)
})

function openImport() {
  urlInput.value = ''
  jsonInput.value = sampleJson
  importMode.value = 'url'
  showImport.value = true
}

async function handlePullFromUrl() {
  if (!urlInput.value.trim()) {
    message.warning('请填写 GitHub / 公共库 URL')
    return
  }
  pulling.value = true
  try {
    await store.importSkillFromUrl(urlInput.value.trim())
    message.success('已从 URL 拉取并导入技能')
    showImport.value = false
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    pulling.value = false
  }
}

async function handleImportJson() {
  try {
    await store.importSkillFromJson(jsonInput.value)
    message.success('JSON 配置已导入')
    showImport.value = false
  } catch (e) {
    message.error((e as Error).message)
  }
}

function handleToggle(skill: SkillItem) {
  store.toggleSkill(skill.id)
}

function handleDelete(skill: SkillItem) {
  store.deleteSkill(skill.id)
  message.success('已删除')
}
</script>

<template>
  <div class="resource-tab">
    <div class="tab-header">
      <span class="tab-hint">管理可挂载到 Agent 的技能，支持 URL 拉取或 JSON 粘贴导入。</span>
      <NButton type="primary" size="small" @click="openImport">
        <template #icon><NIcon :component="AddOutline" /></template>
        导入技能
      </NButton>
    </div>

    <NGrid :cols="2" :x-gap="14" :y-gap="14" responsive="screen" item-responsive>
      <NGridItem v-for="skill in store.skills" :key="skill.id" span="2 m:1">
        <div class="skill-card">
          <div class="skill-icon">{{ skill.icon }}</div>
          <div class="skill-body">
            <div class="skill-head">
              <span class="skill-name">{{ skill.name }}</span>
              <NTag size="tiny" round :bordered="false">{{ skill.category }}</NTag>
              <NTag size="tiny" :type="skill.source === 'builtin' ? 'default' : 'info'" :bordered="false">
                {{ skill.source === 'url' ? 'URL' : skill.source === 'json' ? 'JSON' : '内置' }}
              </NTag>
            </div>
            <div class="skill-desc">{{ skill.description }}</div>
            <div v-if="skill.source_url" class="skill-url">
              <NIcon :component="LinkOutline" size="12" /> {{ skill.source_url }}
            </div>
          </div>
          <div class="skill-actions">
            <NSwitch size="small" :value="skill.is_active" @update:value="handleToggle(skill)" />
            <NPopconfirm @positive-click="handleDelete(skill)">
              <template #trigger>
                <NButton size="tiny" quaternary type="error">
                  <template #icon><NIcon :component="TrashOutline" /></template>
                </NButton>
              </template>
              确定删除该技能？
            </NPopconfirm>
          </div>
        </div>
      </NGridItem>
    </NGrid>

    <NModal v-model:show="showImport" preset="card" title="导入技能" style="width: 600px">
      <NTabs v-model:value="importMode" type="line">
        <NTabPane name="url">
          <template #tab>
            <NIcon :component="LinkOutline" /> &nbsp;URL 拉取
          </template>
          <div class="import-pane">
            <p class="pane-hint">填入 GitHub 仓库或公共库的技能配置 URL，系统会拉取并解析。</p>
            <NInput v-model:value="urlInput" placeholder="https://github.com/your-org/omichub-skills/raw/main/dataprep.json" clearable />
            <NSpace justify="end">
              <NButton size="small" @click="showImport = false">取消</NButton>
              <NButton size="small" type="primary" :loading="pulling" @click="handlePullFromUrl">拉取并导入</NButton>
            </NSpace>
          </div>
        </NTabPane>
        <NTabPane name="json">
          <template #tab>
            <NIcon :component="CodeSlashOutline" /> &nbsp;JSON 粘贴
          </template>
          <div class="import-pane">
            <p class="pane-hint">直接粘贴 JSON 格式的技能配置（必填 name，可选 description/icon/category/prompt）。</p>
            <NInput v-model:value="jsonInput" type="textarea" :autosize="{ minRows: 8, maxRows: 16 }" />
            <NSpace justify="end">
              <NButton size="small" @click="showImport = false">取消</NButton>
              <NButton size="small" type="primary" @click="handleImportJson">解析导入</NButton>
            </NSpace>
          </div>
        </NTabPane>
      </NTabs>
    </NModal>
  </div>
</template>

<style scoped>
.tab-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 14px; }
.tab-hint { font-size: 12px; color: var(--n-text-color-3, #999); }
.skill-card { display: flex; gap: 12px; padding: 14px; border: 1px solid var(--n-border-color, #eee); border-radius: 10px; transition: border-color .2s, box-shadow .2s; }
.skill-card:hover { border-color: var(--n-color-primary, #4f8ef7); box-shadow: 0 2px 12px rgba(79,142,247,.08); }
.skill-icon { font-size: 28px; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; background: rgba(79,142,247,.08); border-radius: 10px; flex-shrink: 0; }
.skill-body { flex: 1; min-width: 0; }
.skill-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.skill-name { font-weight: 600; font-size: 14px; }
.skill-desc { font-size: 12px; color: var(--neutral-text-3, #888); line-height: 1.5; }
.skill-url { font-size: 11px; color: var(--neutral-text-3, #aaa); margin-top: 6px; display: flex; align-items: center; gap: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; flex-shrink: 0; }
.import-pane { display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
.pane-hint { font-size: 12px; color: var(--neutral-text-3, #888); margin: 0; }
</style>
