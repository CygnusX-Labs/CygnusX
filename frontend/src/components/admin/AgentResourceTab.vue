<script setup lang="ts">
import { h, ref, computed, onMounted } from 'vue'
import {
  NButton, NDataTable, NIcon, NTag, NSpace, NPopconfirm, NModal, NForm,
  NFormItem, NInput, NSelect, NColorPicker, NTransfer, NSwitch, NPopover, NSpin, useMessage,
} from 'naive-ui'
import { CreateOutline, TrashOutline, RefreshOutline, StarOutline, EyeOutline } from '@vicons/ionicons5'
import { useAgentHubStore, CATEGORY_LABELS } from '@/stores/agentHub'
import { adminProviderApi } from '@/api/admin/ai_provider'
import type { AgentTemplate, AgentCategory } from '@/types/agent'

const message = useMessage()
const store = useAgentHubStore()

const showEdit = ref(false)
const editing = ref<Partial<AgentTemplate>>({})
const isEdit = ref(false)
const previewId = ref<string | null>(null)
const discovering = ref(false)
const discoveryMap = ref<Record<string, { providerName: string; models: Array<{ id: string; name: string }> }>>({})

/** 可选模型配置（来自 /admin/ai-providers） */
const modelOptions = ref<{ label: string; value: string }[]>([])
const modelMap = computed(() => {
  const map: Record<string, string> = {}
  modelOptions.value.forEach((o) => { map[o.value] = o.label })
  return map
})

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
    // 如果当前编辑项有 model_id，且对应 provider 发现了新模型，把 label 补充上
    Object.values(map).forEach(({ models }) => {
      models.forEach((m) => {
        if (!modelOptions.value.some((o) => o.value === m.id)) {
          // 发现的是远程模型 ID，当前架构仍按 Provider 配置选择，这里仅作展示提示
        }
      })
    })
  } catch (e) {
    message.error('刷新模型列表失败')
    console.error(e)
  } finally {
    discovering.value = false
  }
}

onMounted(async () => {
  // 后台需含停用 Agent 的全量列表
  await store.fetchAgents(false)
  await Promise.all([store.fetchMcps(), store.fetchSkills()])
  await loadModelOptions()
})

const categoryOptions = (Object.keys(CATEGORY_LABELS) as AgentCategory[]).map((k) => ({
  label: CATEGORY_LABELS[k], value: k,
}))

const mcpTransferOptions = computed(() =>
  store.mcps.map((m) => ({ label: `${m.name}`, value: m.id })),
)
const skillTransferOptions = computed(() =>
  store.skills.map((s) => ({ label: s.name, value: s.id })),
)

const columns = [
  { title: '头像', key: 'avatar', width: 56, render: (r: AgentTemplate) => r.avatar },
  { title: '名称', key: 'name', width: 150 },
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
    title: '操作', key: 'actions', width: 240,
    render: (r: AgentTemplate) =>
      h(NSpace, { size: 'small' }, {
        default: () => [
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => openPreview(r.id) },
            { default: () => [h(NIcon, { component: EyeOutline }), '预览'] }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => handleEdit(r) },
            { default: () => [h(NIcon, { component: CreateOutline }), '编辑'] }),
          h(NButton, { size: 'tiny', quaternary: true, onClick: () => store.toggleAgent(r.id) },
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

function handleCreate() {
  editing.value = {
    avatar: '🤖', color: '#4f8ef7', category: 'general',
    model_id: undefined, mcp_ids: [], skill_ids: [],
    features: {},
    welcome_message: '你好，有什么可以帮你？', is_active: true,
  }
  isEdit.value = false
  showEdit.value = true
}

function handleEdit(r: AgentTemplate) {
  editing.value = { ...r, mcp_ids: [...r.mcp_ids], skill_ids: [...r.skill_ids], features: { ...r.features } }
  isEdit.value = true
  showEdit.value = true
}

async function handleSave() {
  if (!editing.value.name?.trim()) {
    message.warning('请填写助手名称')
    return
  }
  const saved = await store.upsertAgent(editing.value)
  if (saved) {
    message.success(isEdit.value ? '已更新' : '已创建')
    showEdit.value = false
  } else {
    message.error('保存失败，请检查后端接口')
  }
}

async function handleDelete(id: string) {
  await store.deleteAgent(id)
  message.success('已删除')
}

function openPreview(id: string) { previewId.value = id }
const previewAgent = computed(() => store.getAgent(previewId.value || ''))
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
    <NModal v-model:show="showEdit" preset="card" :title="isEdit ? '编辑助手模板' : '新建助手模板'" style="width: 760px">
      <NForm label-placement="left" size="small" :label-width="92">
        <NFormItem label="头像">
          <NSpace align="center">
            <NInput v-model:value="editing.avatar" placeholder="🤖" style="width: 80px" />
            <span class="emoji-preview" :style="{ background: editing.color }">{{ editing.avatar }}</span>
            <NColorPicker v-model:value="editing.color" size="small" :show-alpha="false" style="width: 120px" />
          </NSpace>
        </NFormItem>
        <NFormItem label="名称"><NInput v-model:value="editing.name" placeholder="如：单细胞分析师" /></NFormItem>
        <NFormItem label="描述"><NInput v-model:value="editing.description" /></NFormItem>
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
        <NFormItem label="分类">
          <NSelect v-model:value="editing.category" :options="categoryOptions" />
        </NFormItem>
        <NFormItem label="欢迎语">
          <NInput v-model:value="editing.welcome_message" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
        </NFormItem>
        <NFormItem label="系统设定">
          <NInput v-model:value="editing.system_prompt" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" placeholder="System Prompt：角色、能力边界、输出风格…" />
        </NFormItem>
        <NFormItem label="挂载 MCP">
          <NTransfer v-model:value="editing.mcp_ids" :options="mcpTransferOptions" source-filterable />
        </NFormItem>
        <NFormItem label="挂载技能">
          <NTransfer v-model:value="editing.skill_ids" :options="skillTransferOptions" source-filterable />
        </NFormItem>

        <NFormItem label="功能开关">
          <NSpace vertical>
            <NSpace align="center">
              <NSwitch v-model:value="editing.features!.enable_web_search" />
              <span style="font-size: 13px">联网搜索</span>
            </NSpace>
            <NSpace align="center">
              <NSwitch v-model:value="editing.features!.enable_file_upload" />
              <span style="font-size: 13px">文件上传</span>
            </NSpace>
            <NSpace align="center">
              <NSwitch v-model:value="editing.features!.enable_code_execution" />
              <span style="font-size: 13px">代码执行</span>
            </NSpace>
            <NSpace align="center">
              <NSwitch v-model:value="editing.features!.enable_deep_thinking" />
              <span style="font-size: 13px">深度思考</span>
            </NSpace>
          </NSpace>
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton size="small" @click="showEdit = false">取消</NButton>
          <NButton size="small" type="primary" @click="handleSave">保存</NButton>
        </NSpace>
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
.emoji-preview { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 50%; font-size: 18px; }
.preview-section { margin-bottom: 16px; }
.preview-label { font-size: 12px; color: #999; margin-bottom: 6px; }
.preview-prompt { font-size: 12px; color: #555; background: rgba(0,0,0,0.03); padding: 10px; border-radius: 6px; white-space: pre-wrap; line-height: 1.6; }
.empty { font-size: 12px; color: #bbb; }
</style>
