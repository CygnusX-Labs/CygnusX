<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NButton, NIcon, NTag, NSwitch, NGrid, NGridItem, NModal, NTabs, NTabPane,
  NInput, NSpace, NPopconfirm, NUpload, NAlert, NEmpty, NScrollbar, NTooltip,
  NCheckbox, useMessage, type UploadFileInfo,
} from 'naive-ui'
import {
  AddOutline, TrashOutline, LinkOutline, CodeSlashOutline, StorefrontOutline,
  LogoGithub, CloudUploadOutline, WarningOutline, ArrowBackOutline,
  RefreshOutline, TerminalOutline,
} from '@vicons/ionicons5'
import { useAgentHubStore } from '@/stores/agentHub'
import type { SkillItem } from '@/types/agent'
import type { SkillImportPreview, SkillMarketplaceItem } from '@/types/skill'

const message = useMessage()
const store = useAgentHubStore()

// ---------- 导入弹窗状态 ----------
const showImport = ref(false)
const importTab = ref<'market' | 'github' | 'zip' | 'json'>('market')
const parsing = ref(false)
const confirming = ref(false)
/** 统一预览：任意入口解析成功后进入，确认后才入库 */
const preview = ref<SkillImportPreview | null>(null)
const overwrite = ref(false)

const urlInput = ref('')
const jsonInput = ref('')
const zipFile = ref<File | null>(null)
const marketplace = ref<SkillMarketplaceItem[]>([])
const marketplaceLoading = ref(false)
const installingId = ref('')

const SOURCE_LABELS: Record<string, string> = {
  market: '市场', github: 'GitHub', zip: 'ZIP', json: 'JSON', builtin: '内置', url: 'URL',
}

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

/** 预览技能是否已存在（用于覆盖升级提示） */
const previewExists = computed(
  () => !!preview.value && store.skills.some((s) => s.id === preview.value!.skill_id),
)

async function openImport() {
  urlInput.value = ''
  jsonInput.value = sampleJson
  zipFile.value = null
  preview.value = null
  overwrite.value = false
  importTab.value = 'market'
  showImport.value = true
  await loadMarketplace()
}

async function loadMarketplace() {
  marketplaceLoading.value = true
  try {
    marketplace.value = await store.fetchSkillMarketplace()
  } catch (e) {
    console.error('加载技能市场失败:', e)
  } finally {
    marketplaceLoading.value = false
  }
}

function apiErrorMessage(e: unknown): string {
  const err = e as { response?: { data?: { detail?: string } }; message?: string }
  return err?.response?.data?.detail || err?.message || '操作失败'
}

// ---------- 四入口 → 统一预览 ----------

async function handleParseGithub() {
  if (!urlInput.value.trim()) {
    message.warning('请填写 GitHub 仓库或技能文件夹链接')
    return
  }
  parsing.value = true
  try {
    preview.value = await store.previewSkillFromGithub(urlInput.value.trim())
  } catch (e) {
    message.error(apiErrorMessage(e))
  } finally {
    parsing.value = false
  }
}

function onZipChange(options: { file: UploadFileInfo; fileList: UploadFileInfo[] }) {
  zipFile.value = options.file.file ?? null
}

async function handleParseZip() {
  if (!zipFile.value) {
    message.warning('请先选择 zip 技能包')
    return
  }
  parsing.value = true
  try {
    preview.value = await store.previewSkillFromZip(zipFile.value)
  } catch (e) {
    message.error(apiErrorMessage(e))
  } finally {
    parsing.value = false
  }
}

async function handleParseJson() {
  parsing.value = true
  try {
    preview.value = await store.previewSkillFromJson(jsonInput.value)
  } catch (e) {
    message.error(apiErrorMessage(e))
  } finally {
    parsing.value = false
  }
}

async function handleInstallMarket(item: SkillMarketplaceItem) {
  installingId.value = item.skill_id
  try {
    await store.installMarketplaceSkill(item.skill_id, item.installed)
    message.success(`已安装「${item.name}」`)
    await loadMarketplace()
  } catch (e) {
    message.error(apiErrorMessage(e))
  } finally {
    installingId.value = ''
  }
}

function backToEntries() {
  preview.value = null
  overwrite.value = false
}

async function handleConfirmImport() {
  if (!preview.value) return
  confirming.value = true
  try {
    await store.confirmSkillImport(preview.value, overwrite.value)
    message.success(`技能「${preview.value.name}」已入库`)
    showImport.value = false
  } catch (e) {
    message.error(apiErrorMessage(e))
  } finally {
    confirming.value = false
  }
}

// ---------- 卡片操作 ----------

function handleToggle(skill: SkillItem) {
  store.toggleSkill(skill.id)
}

function handleDelete(skill: SkillItem) {
  store.deleteSkill(skill.id)
  message.success('已删除')
}

async function handleCheckUpdate(skill: SkillItem) {
  try {
    const info = await store.checkSkillUpdate(skill.id)
    if (info.has_update) {
      message.info(`发现上游更新（${info.latest_commit}），重新导入即可升级`)
    } else {
      message.success(info.message || '已是最新')
    }
  } catch (e) {
    message.error(apiErrorMessage(e))
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}
</script>

<template>
  <div class="resource-tab">
    <div class="tab-header">
      <span class="tab-hint">
        管理可挂载到 Agent 的 SKILL.md 标准技能：市场一键安装、GitHub 链接、zip 上传或 JSON 粘贴，导入前统一预览校验。
      </span>
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
                {{ SOURCE_LABELS[skill.source] ?? skill.source }}
              </NTag>
              <NTag v-if="skill.version" size="tiny" :bordered="false">v{{ skill.version }}</NTag>
              <NTooltip v-if="skill.has_scripts" trigger="hover">
                <template #trigger>
                  <NTag size="tiny" type="warning" round :bordered="false">
                    <template #icon><NIcon :component="TerminalOutline" /></template>
                    含脚本
                  </NTag>
                </template>
                该技能包含可执行脚本，挂载前请先审查脚本内容
              </NTooltip>
            </div>
            <div class="skill-desc">{{ skill.description }}</div>
            <div v-if="skill.source_url || skill.author" class="skill-meta">
              <span v-if="skill.author" class="skill-author">✍️ {{ skill.author }}</span>
              <span v-if="skill.source_url" class="skill-url">
                <NIcon :component="LinkOutline" size="12" /> {{ skill.source_url }}
              </span>
            </div>
          </div>
          <div class="skill-actions">
            <NSwitch size="small" :value="skill.is_active" @update:value="handleToggle(skill)" />
            <NTooltip v-if="skill.source === 'github'" trigger="hover">
              <template #trigger>
                <NButton size="tiny" quaternary @click="handleCheckUpdate(skill)">
                  <template #icon><NIcon :component="RefreshOutline" /></template>
                </NButton>
              </template>
              检查上游更新
            </NTooltip>
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
    <div v-if="!store.skills.length" class="list-empty">
      <NEmpty description="暂无技能，点击右上角「导入技能」添加" />
    </div>

    <!-- 导入技能：四入口 + 统一预览 -->
    <NModal v-model:show="showImport" preset="card" :title="preview ? '导入预览' : '导入技能'" style="width: 680px" :segmented="{ content: true, footer: true }">
      <!-- 阶段二：统一导入预览页 -->
      <div v-if="preview" class="preview-pane">
        <div class="preview-head">
          <div class="preview-icon">{{ preview.icon }}</div>
          <div class="preview-title">
            <div class="preview-name">
              {{ preview.name }}
              <NTag v-if="preview.version" size="tiny" :bordered="false">v{{ preview.version }}</NTag>
              <NTag size="tiny" type="info" :bordered="false">{{ SOURCE_LABELS[preview.source_type] ?? preview.source_type }}</NTag>
            </div>
            <div class="preview-sub">
              <code>{{ preview.skill_id }}</code>
              <span v-if="preview.author">· {{ preview.author }}</span>
              <span v-if="preview.source_ref">· {{ preview.source_ref }}</span>
            </div>
          </div>
        </div>

        <div class="preview-desc">{{ preview.description }}</div>

        <NAlert v-if="preview.has_scripts" type="warning" :bordered="false" class="preview-alert">
          <template #icon><NIcon :component="TerminalOutline" /></template>
          该技能包含可执行脚本（scripts/）。脚本将在沙盒中运行，代码不会进入模型上下文——请审查后再挂载到助手。
        </NAlert>
        <NAlert
          v-for="(warn, i) in preview.warnings"
          :key="i"
          type="warning"
          :bordered="false"
          class="preview-alert"
        >
          <template #icon><NIcon :component="WarningOutline" /></template>
          {{ warn }}
        </NAlert>

        <div class="preview-block">
          <div class="preview-block-title">文件清单（{{ preview.files.length }}）</div>
          <NScrollbar style="max-height: 180px">
            <div class="file-list">
              <div v-for="f in preview.files" :key="f.path" class="file-row">
                <span class="file-path">{{ f.path }}</span>
                <NTag
                  size="tiny"
                  :bordered="false"
                  :type="f.kind === 'script' ? 'warning' : f.kind === 'skill_md' ? 'info' : 'default'"
                >
                  {{ f.kind === 'skill_md' ? '入口' : f.kind === 'script' ? '脚本' : f.kind === 'reference' ? '参考' : f.kind === 'asset' ? '资源' : '其他' }}
                </NTag>
                <span class="file-size">{{ formatSize(f.size) }}</span>
              </div>
              <div v-if="!preview.files.length" class="file-none">无附带文件（纯指令技能）</div>
            </div>
          </NScrollbar>
        </div>

        <div v-if="preview.body" class="preview-block">
          <div class="preview-block-title">指令正文预览（SKILL.md）</div>
          <NScrollbar style="max-height: 200px">
            <pre class="preview-body">{{ preview.body }}</pre>
          </NScrollbar>
        </div>

        <div v-if="previewExists" class="preview-overwrite">
          <NCheckbox v-model:checked="overwrite">
            技能 <code>{{ preview.skill_id }}</code> 已存在，覆盖升级到该版本
          </NCheckbox>
        </div>
      </div>

      <!-- 阶段一：四个入口 -->
      <NTabs v-else v-model:value="importTab" type="line">
        <NTabPane name="market">
          <template #tab><NIcon :component="StorefrontOutline" /> &nbsp;技能市场</template>
          <div class="import-pane">
            <p class="pane-hint">平台内置的标准技能，一键安装入库。</p>
            <NScrollbar style="max-height: 320px">
              <div v-if="marketplaceLoading" class="market-loading">加载中…</div>
              <div v-else-if="!marketplace.length" class="market-empty">
                <NEmpty description="市场暂无内置技能" />
              </div>
              <div v-for="item in marketplace" :key="item.skill_id" class="market-card">
                <div class="skill-icon">{{ item.icon }}</div>
                <div class="skill-body">
                  <div class="skill-head">
                    <span class="skill-name">{{ item.name }}</span>
                    <NTag v-if="item.version" size="tiny" :bordered="false">v{{ item.version }}</NTag>
                    <NTag size="tiny" round :bordered="false">{{ item.category }}</NTag>
                    <NTag v-if="item.has_scripts" size="tiny" type="warning" round :bordered="false">含脚本</NTag>
                  </div>
                  <div class="skill-desc">{{ item.description }}</div>
                </div>
                <NButton
                  size="tiny"
                  :type="item.installed ? 'default' : 'primary'"
                  :loading="installingId === item.skill_id"
                  @click="handleInstallMarket(item)"
                >
                  {{ item.installed ? '重新安装' : '安装' }}
                </NButton>
              </div>
            </NScrollbar>
          </div>
        </NTabPane>

        <NTabPane name="github">
          <template #tab><NIcon :component="LogoGithub" /> &nbsp;GitHub</template>
          <div class="import-pane">
            <p class="pane-hint">
              粘贴 GitHub 仓库主页、tree 分支/子目录或直指 SKILL.md 的链接，后端拉取整个文件夹并解析（公开仓库）。
            </p>
            <NInput
              v-model:value="urlInput"
              placeholder="https://github.com/owner/repo 或 .../tree/main/skills/my-skill"
              clearable
            />
            <NSpace justify="end">
              <NButton size="small" @click="showImport = false">取消</NButton>
              <NButton size="small" type="primary" :loading="parsing" @click="handleParseGithub">
                解析并预览
              </NButton>
            </NSpace>
          </div>
        </NTabPane>

        <NTabPane name="zip">
          <template #tab><NIcon :component="CloudUploadOutline" /> &nbsp;本地上传</template>
          <div class="import-pane">
            <p class="pane-hint">上传 zip 技能包（内含 SKILL.md 与可选 scripts/ references/ assets/，≤6MB）。</p>
            <NUpload
              :default-upload="false"
              :max="1"
              accept=".zip"
              @change="onZipChange"
            >
              <NButton size="small">选择 zip 文件</NButton>
            </NUpload>
            <NSpace justify="end">
              <NButton size="small" @click="showImport = false">取消</NButton>
              <NButton size="small" type="primary" :loading="parsing" :disabled="!zipFile" @click="handleParseZip">
                解析并预览
              </NButton>
            </NSpace>
          </div>
        </NTabPane>

        <NTabPane name="json">
          <template #tab><NIcon :component="CodeSlashOutline" /> &nbsp;JSON 粘贴</template>
          <div class="import-pane">
            <p class="pane-hint">兼容旧版 JSON 配置（必填 name，可选 description/icon/category/prompt），将自动转换为 SKILL.md 格式。</p>
            <NInput v-model:value="jsonInput" type="textarea" :autosize="{ minRows: 8, maxRows: 16 }" />
            <NSpace justify="end">
              <NButton size="small" @click="showImport = false">取消</NButton>
              <NButton size="small" type="primary" :loading="parsing" @click="handleParseJson">解析并预览</NButton>
            </NSpace>
          </div>
        </NTabPane>
      </NTabs>

      <template v-if="preview" #footer>
        <NSpace justify="space-between" align="center" style="width: 100%">
          <NButton size="small" @click="backToEntries">
            <template #icon><NIcon :component="ArrowBackOutline" /></template>
            返回
          </NButton>
          <NButton size="small" type="primary" :loading="confirming" :disabled="previewExists && !overwrite" @click="handleConfirmImport">
            确认导入
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.tab-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 14px; }
.tab-hint { font-size: 12px; color: var(--n-text-color-3, #999); }
.list-empty { padding: 32px 0; }

.skill-card { display: flex; gap: 12px; padding: 14px; border: 1px solid var(--n-border-color, #eee); border-radius: 10px; transition: border-color .2s, box-shadow .2s; }
.skill-card:hover { border-color: var(--brand-primary, #4C6FFF); box-shadow: 0 2px 12px rgba(76,111,255,.08); }
.skill-icon { font-size: 28px; width: 44px; height: 44px; display: flex; align-items: center; justify-content: center; background: var(--brand-primary-light, rgba(76,111,255,.08)); border-radius: 10px; flex-shrink: 0; }
.skill-body { flex: 1; min-width: 0; }
.skill-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; flex-wrap: wrap; }
.skill-name { font-weight: 600; font-size: 14px; }
.skill-desc { font-size: 12px; color: var(--neutral-text-3, #888); line-height: 1.5; }
.skill-meta { margin-top: 6px; display: flex; align-items: center; gap: 10px; font-size: 11px; color: var(--neutral-text-3, #aaa); min-width: 0; }
.skill-author { flex-shrink: 0; }
.skill-url { display: flex; align-items: center; gap: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex-shrink: 0; }

.import-pane { display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
.pane-hint { font-size: 12px; color: var(--neutral-text-3, #888); margin: 0; line-height: 1.6; }
.market-loading { padding: 24px; text-align: center; font-size: 12px; color: var(--n-text-color-3); }
.market-empty { padding: 16px 0; }
.market-card { display: flex; gap: 12px; align-items: center; padding: 12px; border: 1px solid var(--n-border-color, #eee); border-radius: 10px; margin-bottom: 10px; }

/* 统一预览页 */
.preview-pane { display: flex; flex-direction: column; gap: 12px; }
.preview-head { display: flex; gap: 12px; align-items: center; }
.preview-icon { font-size: 32px; width: 52px; height: 52px; display: flex; align-items: center; justify-content: center; background: var(--brand-primary-light, rgba(76,111,255,.08)); border-radius: 12px; flex-shrink: 0; }
.preview-title { min-width: 0; }
.preview-name { font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.preview-sub { font-size: 12px; color: var(--n-text-color-3, #888); margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.preview-sub code { font-size: 11px; background: var(--n-color-embedded, #f5f6fa); padding: 1px 5px; border-radius: 4px; }
.preview-desc { font-size: 13px; color: var(--n-text-color-2, #555); line-height: 1.6; }
.preview-alert { font-size: 12px; }
.preview-block { border: 1px solid var(--n-border-color, #eee); border-radius: 10px; overflow: hidden; }
.preview-block-title { font-size: 12px; font-weight: 600; color: var(--n-text-color-2, #555); padding: 8px 12px; border-bottom: 1px solid var(--n-border-color, #eee); background: var(--n-color-embedded, #fafbfc); }
.file-list { padding: 4px 0; }
.file-row { display: flex; align-items: center; gap: 8px; padding: 5px 12px; font-size: 12px; }
.file-path { flex: 1; font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-size { color: var(--n-text-color-3, #999); flex-shrink: 0; }
.file-none { padding: 10px 12px; font-size: 12px; color: var(--n-text-color-3, #999); }
.preview-body { margin: 0; padding: 12px; font-size: 12px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; font-family: monospace; }
.preview-overwrite { font-size: 13px; }
.preview-overwrite code { font-size: 11px; background: var(--n-color-embedded, #f5f6fa); padding: 1px 5px; border-radius: 4px; }
</style>
