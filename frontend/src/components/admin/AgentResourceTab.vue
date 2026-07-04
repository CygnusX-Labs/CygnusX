<script setup lang="ts">
import { h, ref, computed, onMounted, watch } from 'vue'
import {
  NButton, NDataTable, NIcon, NTag, NSpace, NPopconfirm, NModal, NCard,
  NForm, NFormItem, NInput, NSelect, NColorPicker, NSwitch, NPopover, NSpin,
  useMessage,
} from 'naive-ui'
import {
  CreateOutline, TrashOutline, RefreshOutline, StarOutline, EyeOutline,
  ColorPaletteOutline, HappyOutline,
} from '@vicons/ionicons5'
import { useAgentHubStore, CATEGORY_LABELS } from '@/stores/agentHub'
import { adminProviderApi } from '@/api/admin/ai_provider'
import type { AgentTemplate, AgentCategory, AgentFeatures } from '@/types/agent'

const message = useMessage()
const store = useAgentHubStore()

const showEdit = ref(false)
const editing = ref<Partial<AgentTemplate>>({})
const editingSnapshot = ref<string>('')
const isEdit = ref(false)
const saving = ref(false)
const previewId = ref<string | null>(null)
const discovering = ref(false)
const discoveryMap = ref<Record<string, { providerName: string; models: Array<{ id: string; name: string }> }>>({})
const systemPromptExpanded = ref(false)

/** 可选模型配置（来自 /admin/ai-providers） */
const modelOptions = ref<{ label: string; value: string }[]>([])
const modelMap = computed(() => {
  const map: Record<string, string> = {}
  modelOptions.value.forEach((o) => { map[o.value] = o.label })
  return map
})

const EMOJI_LIST = [
  '🤖', '🧬', '🧪', '🔬', '💻', '📊', '🧠', '🌐', '📚', '🔭',
  '🚀', '⭐', '🌙', '☀️', '🔥', '💡', '🔧', '📈', '🎨', '🎓',
  '🐱', '🐶', '🦊', '🐼', '🐨', '🐯', '🦁', '🐸', '🐙', '🦉',
]

async function loadModelOptions() {
  try {
    const providers = await adminProviderApi.list()
    modelOptions.value = providers.map((m) => ({
      label: `${m.name} (${m.model})`,
      value: m.id,
    }))
  } catch (e) {
    console.error('加载模型列表失败:', e)
  }
}

async function refreshModels() {
  discovering.value = true
  try {
    const providers = await adminProviderApi.list()
    await loadModelOptions()
    const discoveries = await Promise.all(
      providers.map((p) => adminProviderApi.discoverModels(p.id).catch(() => null)),
    )
    const map: Record<string, { providerName: string; models: Array<{ id: string; name: string }> }> = {}
    discoveries.forEach((d) => {
      if (d?.models?.length) {
        map[d.provider_id] = {
          providerName: d.provider_name,
          models: d.models.map((m) => ({ id: m.id, name: m.name || m.id })),
        }
      }
    })
    discoveryMap.value = map
  } catch (e) {
    message.error('刷新模型列表失败')
    console.error(e)
  } finally {
    discovering.value = false
  }
}

onMounted(async () => {
  await store.fetchAgents(false)
  await Promise.all([store.fetchMcps(), store.fetchSkills()])
  await loadModelOptions()
})

const categoryOptions = (Object.keys(CATEGORY_LABELS) as AgentCategory[]).map((k) => ({
  label: CATEGORY_LABELS[k], value: k,
}))

const mcpOptions = computed(() =>
  store.mcps.map((m) => ({ label: `${m.name}`, value: m.id, disabled: !m.status || m.status === 'offline' })),
)
const skillOptions = computed(() =>
  store.skills.map((s) => ({ label: `${s.icon ?? '🔧'} ${s.name}`, value: s.id })),
)

const isDirty = computed(() => {
  try {
    return JSON.stringify(editing.value) !== editingSnapshot.value
  } catch {
    return true
  }
})

const systemPromptLength = computed(() => editing.value.system_prompt?.length ?? 0)

const columns = [
  { title: '头像', key: 'avatar', width: 56, render: (r: AgentTemplate) => r.avatar },
  {
    title: '名称', key: 'name', width: 180,
    render: (r: AgentTemplate) =>
      h(NSpace, { size: 4, align: 'center' }, {
        default: () => [
          h('span', null, r.name),
          r.is_default && h(NTag, { size: 'tiny', type: 'warning', round: true }, { default: () => '默认' }),
        ],
      }),
  },
  { title: '分类', key: 'category', width: 90, render: (r: AgentTemplate) => CATEGORY_LABELS[r.category] },
  {
    title: '模型', key: 'model', width: 160,
    render: (r: AgentTemplate) => {
      const label = r.model_id ? modelMap.value[r.model_id] : ''
      return h(NTag, { size: 'tiny', type: label ? 'info' : 'default', bordered: false }, { default: () => label || '未绑定' })
    },
  },
  {
    title: '挂载能力', key: 'mounts', width: 200,
    render: (r: AgentTemplate) =>
      h(NSpace, { size: 4 }, {
        default: () => [
          h(NTag, { size: 'tiny', type: 'info', bordered: false }, { default: () => `MCP×${r.mcp_ids.length}` }),
          h(NTag, { size: 'tiny', type: 'success', bordered: false }, { default: () => `技能×${r.skill_ids.length}` }),
        ],
      }),
  },
  {
    title: '状态', key: 'is_active', width: 80,
    render: (r: AgentTemplate) => h(NTag, { type: r.is_active ? 'success' : 'default', size: 'small', round: true }, { default: () => r.is_active ? '启用' : '停用' }),
  },
  {
    title: '操作', key: 'actions', width: 280,
    render: (r: AgentTemplate) =>
      h(NSpace, { size: 'small' }, {
        default: () => [
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => openPreview(r.id) },
            { default: () => [h(NIcon, { component: EyeOutline }), '预览'] }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleEdit(r) },
            { default: () => [h(NIcon, { component: CreateOutline }), '编辑'] }),
          !r.is_default && h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleSetDefault(r.id) },
            { default: () => [h(NIcon, { component: StarOutline }), '设为默认'] }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleToggle(r.id) },
            { default: () => r.is_active ? '停用' : '启用' }),
          !r.is_builtin && h(NPopconfirm, { onPositiveClick: () => handleDelete(r.id) }, {
            trigger: () => h(NButton, { size: 'tiny', quaternary: true, type: 'error' },
              { default: () => [h(NIcon, { component: TrashOutline }), '删除'] }),
            default: () => '确定删除该助手模板？',
          }),
        ],
      }),
  },
]

function makeDefaultAgent(): Partial<AgentTemplate> {
  return {
    avatar: '🤖',
    color: '#4f8ef7',
    category: 'general',
    model_id: undefined,
    mcp_ids: [],
    skill_ids: [],
    features: {
      enable_web_search: false,
      enable_file_upload: false,
      enable_code_execution: false,
      enable_deep_thinking: false,
    } as AgentFeatures,
    welcome_message: '你好，有什么可以帮你？',
    system_prompt: '',
    is_active: true,
  }
}

function handleCreate() {
  editing.value = makeDefaultAgent()
  editingSnapshot.value = JSON.stringify(editing.value)
  isEdit.value = false
  systemPromptExpanded.value = false
  showEdit.value = true
}

function handleEdit(r: AgentTemplate) {
  editing.value = {
    ...r,
    mcp_ids: [...r.mcp_ids],
    skill_ids: [...r.skill_ids],
    features: {
      enable_web_search: false,
      enable_file_upload: false,
      enable_code_execution: false,
      enable_deep_thinking: false,
      ...(r.features || {}),
    },
  }
  editingSnapshot.value = JSON.stringify(editing.value)
  isEdit.value = true
  systemPromptExpanded.value = false
  showEdit.value = true
}

async function handleSave() {
  if (!editing.value.name?.trim()) {
    message.warning('请填写助手名称')
    return
  }
  if (!editing.value.category) {
    message.warning('请选择分类')
    return
  }
  saving.value = true
  try {
    const saved = await store.upsertAgent(editing.value)
    if (saved) {
      message.success(isEdit.value ? '已更新' : '已创建')
      showEdit.value = false
    } else {
      message.error('保存失败，请检查后端接口')
    }
  } catch (e: any) {
    message.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleToggle(id: string) {
  try {
    await store.toggleAgent(id)
    const agent = store.getAgent(id)
    message.success(agent?.is_active ? '已启用' : '已停用')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '操作失败')
  }
}

async function handleSetDefault(id: string) {
  try {
    await store.setDefaultAgent(id)
    message.success('已设为默认助手')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '设置失败')
  }
}

async function handleDelete(id: string) {
  try {
    await store.deleteAgent(id)
    message.success('已删除')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

function openPreview(id: string) { previewId.value = id }
const previewAgent = computed(() => store.getAgent(previewId.value || ''))

function onSelectEmoji(emoji: string) {
  editing.value.avatar = emoji
}

function onColorChange(color: string) {
  editing.value.color = color
}

function restoreSystemPrompt() {
  editing.value.system_prompt = ''
}

const featureSwitches = computed(() => [
  {
    key: 'enable_web_search',
    title: '联网搜索',
    desc: '允许助手访问互联网获取最新信息',
  },
  {
    key: 'enable_file_upload',
    title: '文件上传',
    desc: '允许用户上传文件进行分析',
  },
  {
    key: 'enable_code_execution',
    title: '代码执行',
    desc: '允许助手在沙盒中执行 Python 等代码',
  },
  {
    key: 'enable_deep_thinking',
    title: '深度思考',
    desc: '启用推理链，适合复杂问题拆解',
  },
])

function updateFeature(key: keyof AgentFeatures, val: boolean) {
  if (!editing.value.features) editing.value.features = {}
  editing.value.features[key] = val
}
</script>

<template>
  <div class="resource-tab">
    <div class="tab-header">
      <span class="tab-hint">编排 Agent 模板：定义角色设定，并挂载 MCP 服务与技能。</span>
      <NButton type="primary" size="small" @click="handleCreate">
        <template #icon><NIcon :component="CreateOutline" /></template>
        新建助手
      </NButton>
    </div>
    <NDataTable :columns="columns" :data="store.agents" :bordered="false" size="small" :row-key="(r: AgentTemplate) => r.id" />

    <!-- 编辑/新建 -->
    <NModal
      v-model:show="showEdit"
      preset="card"
      :title="isEdit ? '编辑助手模板' : '新建助手模板'"
      style="width: 760px; max-height: 90vh"
      :segmented="{ content: true, footer: true }"
    >
      <div class="edit-body">
        <!-- 基本信息 -->
        <NCard title="基本信息" size="small" class="form-card">
          <NForm label-placement="top" size="small">
            <NFormItem label="头像与主题色">
              <NSpace align="center" size="large">
                <NPopover trigger="click" placement="bottom" style="padding: 8px">
                  <template #trigger>
                    <div class="avatar-picker" :style="{ background: editing.color }">
                      {{ editing.avatar || '🤖' }}
                    </div>
                  </template>
                  <div class="emoji-grid">
                    <div
                      v-for="emoji in EMOJI_LIST"
                      :key="emoji"
                      class="emoji-cell"
                      @click="onSelectEmoji(emoji)"
                    >
                      {{ emoji }}
                    </div>
                  </div>
                </NPopover>
                <NPopover trigger="click" placement="bottom">
                  <template #trigger>
                    <div class="color-trigger">
                      <div class="color-indicator" :style="{ background: editing.color }" />
                      <span class="color-value">{{ editing.color }}</span>
                    </div>
                  </template>
                  <NColorPicker
                    :value="editing.color"
                    size="small"
                    :show-alpha="false"
                    @update:value="onColorChange"
                  />
                </NPopover>
              </NSpace>
            </NFormItem>
            <NFormItem label="名称" required>
              <NInput v-model:value="editing.name" placeholder="如：单细胞分析师" />
            </NFormItem>
            <NFormItem label="描述">
              <NInput v-model:value="editing.description" placeholder="一句话描述该助手的定位" />
            </NFormItem>
          </NForm>
        </NCard>

        <!-- 模型与交互 -->
        <NCard title="模型与交互" size="small" class="form-card">
          <NForm label-placement="top" size="small">
            <NFormItem label="绑定模型配置">
              <NSpace align="center" style="width: 100%">
                <NSelect
                  v-model:value="editing.model_id"
                  :options="modelOptions"
                  placeholder="选择后端已配置的模型（决定 Base URL / API Key）"
                  clearable
                  filterable
                  style="flex: 1"
                />
                <NPopover trigger="click" placement="bottom" style="max-width: 360px" @update:show="refreshModels">
                  <template #trigger>
                    <NButton text class="toolbar-btn" :loading="discovering" @click="refreshModels">
                      <template #icon><NIcon :component="RefreshOutline" /></template>
                    </NButton>
                  </template>
                  <div style="max-height: 260px; overflow-y: auto">
                    <div v-if="discovering" style="padding: 12px; text-align: center">
                      <NSpin size="small" />
                    </div>
                    <template v-else>
                      <div v-if="!Object.keys(discoveryMap).length" style="padding: 8px; color: #999; font-size: 12px">
                        未从任何 Provider 发现可用模型，请检查 API Key / Base URL。
                      </div>
                      <div v-for="item in Object.values(discoveryMap)" :key="item.providerName" style="margin-bottom: 10px">
                        <div style="font-size: 12px; font-weight: 500; margin-bottom: 4px">{{ item.providerName }}</div>
                        <NSpace size="small" wrap>
                          <NTag v-for="m in item.models" :key="m.id" size="tiny" round>{{ m.name || m.id }}</NTag>
                        </NSpace>
                      </div>
                    </template>
                  </div>
                </NPopover>
              </NSpace>
            </NFormItem>
            <NFormItem label="分类" required>
              <NSelect v-model:value="editing.category" :options="categoryOptions" />
            </NFormItem>
            <NFormItem label="欢迎语">
              <NInput v-model:value="editing.welcome_message" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
            </NFormItem>
          </NForm>
        </NCard>

        <!-- 系统设定 -->
        <NCard title="系统设定" size="small" class="form-card">
          <NForm label-placement="top" size="small">
            <NFormItem>
              <template #label>
                <NSpace align="center" justify="space-between" style="width: 100%">
                  <span>系统提示词</span>
                  <NSpace>
                    <NButton size="tiny" text @click="systemPromptExpanded = !systemPromptExpanded">
                      {{ systemPromptExpanded ? '收起' : '展开' }}
                    </NButton>
                    <NButton size="tiny" text @click="restoreSystemPrompt">恢复默认</NButton>
                  </NSpace>
                </NSpace>
              </template>
              <NInput
                v-model:value="editing.system_prompt"
                type="textarea"
                :autosize="systemPromptExpanded ? { minRows: 8, maxRows: 20 } : { minRows: 3, maxRows: 6 }"
                placeholder="System Prompt：角色、能力边界、输出风格…"
              />
              <div class="char-count">{{ systemPromptLength }} / 2000</div>
            </NFormItem>
          </NForm>
        </NCard>

        <!-- 能力挂载 -->
        <NCard title="能力挂载" size="small" class="form-card">
          <NForm label-placement="top" size="small">
            <NFormItem label="挂载 MCP">
              <NSelect
                v-model:value="editing.mcp_ids"
                :options="mcpOptions"
                multiple
                filterable
                placeholder="选择要挂载的 MCP 服务"
                :max-tag-count="3"
              />
            </NFormItem>
            <NFormItem label="挂载技能">
              <NSelect
                v-model:value="editing.skill_ids"
                :options="skillOptions"
                multiple
                filterable
                placeholder="选择要挂载的技能"
                :max-tag-count="3"
              />
            </NFormItem>
          </NForm>
        </NCard>

        <!-- 功能开关 -->
        <NCard title="功能开关" size="small" class="form-card">
          <div class="switch-list">
            <div v-for="f in featureSwitches" :key="f.key" class="switch-row">
              <div class="switch-info">
                <div class="switch-title">{{ f.title }}</div>
                <div class="switch-desc">{{ f.desc }}</div>
              </div>
              <NSwitch
                :value="!!editing.features?.[f.key as keyof AgentFeatures]"
                @update:value="(v) => updateFeature(f.key as keyof AgentFeatures, v)"
              />
            </div>
          </div>
        </NCard>
      </div>

      <template #footer>
        <div class="edit-footer">
          <NSpace justify="end" align="center">
            <NButton size="small" @click="showEdit = false">取消</NButton>
            <NButton
              size="small"
              type="primary"
              :disabled="!isDirty"
              :loading="saving"
              @click="handleSave"
            >
              保存
            </NButton>
          </NSpace>
        </div>
      </template>
    </NModal>

    <!-- 预览能力 -->
    <NModal :show="!!previewAgent" preset="card" :title="previewAgent ? `${previewAgent.avatar} ${previewAgent.name} · 能力预览` : ''" style="width: 520px" @update:show="previewId = null">
      <template v-if="previewAgent">
        <div class="preview-section">
          <div class="preview-label">挂载 MCP（{{ previewAgent.mcp_ids.length }}）</div>
          <NSpace size="small">
            <NTag v-for="m in store.mcpsByIds(previewAgent.mcp_ids)" :key="m.id" type="info" round>{{ m.name }}</NTag>
            <span v-if="!previewAgent.mcp_ids.length" class="empty">未挂载</span>
          </NSpace>
        </div>
        <div class="preview-section">
          <div class="preview-label">挂载技能（{{ previewAgent.skill_ids.length }}）</div>
          <NSpace size="small">
            <NTag v-for="s in store.skillsByIds(previewAgent.skill_ids)" :key="s.id" type="success" round>{{ s.icon }} {{ s.name }}</NTag>
            <span v-if="!previewAgent.skill_ids.length" class="empty">未挂载</span>
          </NSpace>
        </div>
        <div class="preview-section">
          <div class="preview-label">系统设定</div>
          <div class="preview-prompt">{{ previewAgent.system_prompt }}</div>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.tab-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.tab-hint { font-size: 12px; color: var(--n-text-color-3, #999); }
.form-card { margin-bottom: 16px; }
.edit-body { max-height: calc(90vh - 140px); overflow-y: auto; padding-right: 6px; }
.edit-footer { padding: 8px 0; }

.avatar-picker {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  border: 2px solid var(--n-border-color, #e0e0e6);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease;
}
.avatar-picker:hover { border-color: var(--n-text-color-2, #333); transform: scale(1.04); }

.emoji-grid {
  display: grid;
  grid-template-columns: repeat(10, 28px);
  gap: 4px;
}
.emoji-cell {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s;
}
.emoji-cell:hover { background: var(--n-border-color, #e0e0e6); }

.color-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 10px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color, #e0e0e6);
  transition: border-color 0.2s;
}
.color-trigger:hover { border-color: var(--n-text-color-2, #333); }
.color-indicator {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  border: 1px solid var(--n-border-color, #e0e0e6);
}
.color-value {
  font-size: 12px;
  color: var(--n-text-color-3, #999);
  font-family: monospace;
}

.char-count {
  text-align: right;
  font-size: 12px;
  color: var(--n-text-color-3, #999);
  margin-top: 4px;
}

.switch-list { display: flex; flex-direction: column; }
.switch-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--n-border-color, #e0e0e6);
}
.switch-row:last-child { border-bottom: none; }
.switch-info { flex: 1; padding-right: 16px; }
.switch-title { font-size: 14px; font-weight: 500; color: var(--n-text-color-1, #333); }
.switch-desc { font-size: 12px; color: var(--n-text-color-3, #999); margin-top: 2px; }

.preview-section { margin-bottom: 16px; }
.preview-label { font-size: 12px; color: #999; margin-bottom: 6px; }
.preview-prompt { font-size: 12px; color: #555; background: rgba(0,0,0,0.03); padding: 10px; border-radius: 6px; white-space: pre-wrap; line-height: 1.6; }
.empty { font-size: 12px; color: #bbb; }
</style>
