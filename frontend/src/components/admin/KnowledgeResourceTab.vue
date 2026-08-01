<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  NButton, NDrawer, NDrawerContent, NEmpty, NIcon, NInput, NModal, NSwitch, NTag, useMessage,
} from 'naive-ui'
import { AddOutline, BookOutline, DocumentTextOutline, TrashOutline } from '@vicons/ionicons5'
import { knowledgeBaseApi, type KnowledgeBase, type KnowledgeBaseDoc } from '@/api/admin/knowledgeBase'

const message = useMessage()
const bases = ref<KnowledgeBase[]>([])
const selectedId = ref('')
const loading = ref(false)
const saving = ref(false)
const form = reactive({ name: '', description: '', show_in_lab: true, ai_searchable: true, is_enabled: true })

const showCreate = ref(false)
const creating = ref(false)
const createForm = reactive({ id: '', name: '', description: '', show_in_lab: true, ai_searchable: true })

const showDocs = ref(false)
const docsLoading = ref(false)
const docs = ref<KnowledgeBaseDoc[]>([])

function fillForm(kb: KnowledgeBase | null) {
  if (!kb) return
  form.name = kb.name
  form.description = kb.description
  form.show_in_lab = kb.show_in_lab
  form.ai_searchable = kb.ai_searchable
  form.is_enabled = kb.is_enabled
}

const selected = () => bases.value.find((kb) => kb.id === selectedId.value) || null

async function load(keepSelection = true) {
  loading.value = true
  try {
    bases.value = await knowledgeBaseApi.list()
    if (!keepSelection || !bases.value.some((kb) => kb.id === selectedId.value)) {
      selectedId.value = bases.value[0]?.id || ''
    }
    fillForm(selected())
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '加载知识库列表失败')
  } finally {
    loading.value = false
  }
}

function select(kb: KnowledgeBase) {
  selectedId.value = kb.id
  fillForm(kb)
}

async function save() {
  const kb = selected()
  if (!kb) return
  saving.value = true
  try {
    const updated = await knowledgeBaseApi.update(kb.id, { ...form })
    bases.value = bases.value.map((item) => (item.id === updated.id ? updated : item))
    message.success('知识库配置已保存')
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function create() {
  if (!createForm.id.trim() || !createForm.name.trim()) {
    message.warning('请填写知识库标识与名称')
    return
  }
  creating.value = true
  try {
    const created = await knowledgeBaseApi.create({ ...createForm })
    message.success(`知识库「${created.name}」已创建`)
    showCreate.value = false
    createForm.id = createForm.name = createForm.description = ''
    await load(false)
    selectedId.value = created.id
    fillForm(created)
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

async function remove() {
  const kb = selected()
  if (!kb) return
  try {
    await knowledgeBaseApi.remove(kb.id)
    message.success(`知识库「${kb.name}」已删除`)
    await load(false)
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '删除失败')
  }
}

async function openDocs() {
  const kb = selected()
  if (!kb) return
  showDocs.value = true
  docsLoading.value = true
  try {
    docs.value = await knowledgeBaseApi.docs(kb.id)
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '加载文档列表失败')
  } finally {
    docsLoading.value = false
  }
}

function statusTag(status: number) {
  if (status === 1) return { label: '已发布', type: 'success' as const }
  if (status === 2) return { label: '待审核', type: 'warning' as const }
  return { label: '已拒绝', type: 'error' as const }
}

onMounted(load)
</script>

<template>
  <div class="kb-tab-page" :aria-busy="loading">
    <div class="tab-header">
      <span class="tab-hint">管理知识库的可见性与 AI 检索范围，新建或删除知识库前先选择左侧条目。</span>
    </div>
    <div class="kb-tab">
    <aside class="kb-list" aria-label="知识库列表">
      <button
        v-for="kb in bases" :key="kb.id" class="kb-item"
        :class="{ active: kb.id === selectedId }" @click="select(kb)"
      >
        <NIcon :component="BookOutline" />
        <span class="kb-name">{{ kb.name }}</span>
        <NTag size="tiny" :bordered="false">{{ kb.doc_count }} 篇</NTag>
        <NTag v-if="!kb.is_enabled" size="tiny" type="error" :bordered="false">停用</NTag>
      </button>
      <NButton dashed block size="small" class="kb-add" @click="showCreate = true">
        <template #icon><NIcon :component="AddOutline" /></template>
        新建知识库
      </NButton>
    </aside>

    <section v-if="selected()" class="kb-panel">
      <div class="panel-heading">
        <div>
          <h3>{{ selected()!.name }}<code class="kb-code">{{ selected()!.id }}</code></h3>
          <p>控制该知识库在「实验室知识库」页的可见性与 AI 检索范围。</p>
        </div>
        <NButton secondary @click="openDocs">
          <template #icon><NIcon :component="DocumentTextOutline" /></template>
          查看文档（{{ selected()!.doc_count }}）
        </NButton>
      </div>

      <div class="field"><label>名称</label><NInput v-model:value="form.name" /></div>
      <div class="field"><label>描述</label><NInput v-model:value="form.description" type="textarea" :rows="2" /></div>
      <div class="field-row">
        <label>在「实验室知识库」页面展示</label>
        <NSwitch v-model:value="form.show_in_lab" />
      </div>
      <div class="field-row">
        <label>允许 AI 助手检索（knowledge_search）</label>
        <NSwitch v-model:value="form.ai_searchable" />
      </div>
      <div class="field-row">
        <label>启用该知识库</label>
        <NSwitch v-model:value="form.is_enabled" />
      </div>

      <div class="panel-actions">
        <NButton
          tertiary type="error" :disabled="selected()!.doc_count > 0"
          @click="remove"
        >
          <template #icon><NIcon :component="TrashOutline" /></template>
          删除
        </NButton>
        <NButton type="primary" :loading="saving" @click="save">保存配置</NButton>
      </div>
      <p v-if="selected()!.doc_count > 0" class="hint">知识库内仍有文档时不可删除。</p>
    </section>
    <NEmpty v-else description="选择左侧知识库进行配置" />
    </div>

    <NModal v-model:show="showCreate" preset="card" title="新建知识库" style="width: 480px">
      <div class="field"><label>标识（小写字母/数字/连字符）</label><NInput v-model:value="createForm.id" placeholder="如 scseq、proteomics" /></div>
      <div class="field"><label>名称</label><NInput v-model:value="createForm.name" placeholder="如 单细胞知识库" /></div>
      <div class="field"><label>描述</label><NInput v-model:value="createForm.description" type="textarea" :rows="2" /></div>
      <div class="field-row"><label>在「实验室知识库」页面展示</label><NSwitch v-model:value="createForm.show_in_lab" /></div>
      <div class="field-row"><label>允许 AI 助手检索</label><NSwitch v-model:value="createForm.ai_searchable" /></div>
      <div class="panel-actions"><NButton type="primary" :loading="creating" @click="create">创建</NButton></div>
    </NModal>

    <NDrawer v-model:show="showDocs" :width="520">
      <NDrawerContent :title="`文档列表 - ${selected()?.name || ''}`" closable>
        <NEmpty v-if="!docsLoading && docs.length === 0" description="该知识库暂无文档" />
        <div v-for="doc in docs" :key="doc.doc_id" class="doc-item">
          <div class="doc-title">{{ doc.title }}</div>
          <div class="doc-meta">
            <span>{{ doc.category }}</span>
            <NTag size="tiny" :type="statusTag(doc.status).type" :bordered="false">{{ statusTag(doc.status).label }}</NTag>
            <code>{{ doc.doc_id }}</code>
          </div>
        </div>
      </NDrawerContent>
    </NDrawer>
  </div>
</template>

<style scoped>
.tab-header { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:14px; }
.tab-hint { font-size:12px; color:var(--neutral-text-3); }
.kb-tab { display:grid; grid-template-columns:minmax(190px, .32fr) minmax(0, 1fr); min-height:440px; border:1px solid var(--neutral-border); border-radius:12px; overflow:hidden; background:var(--neutral-card); }
.kb-list { padding:12px; border-right:1px solid var(--neutral-border); background:var(--neutral-bg); }
.kb-item { width:100%; min-height:36px; display:flex; align-items:center; gap:8px; padding:0 8px; border:0; border-radius:7px; background:transparent; color:var(--neutral-text-2); text-align:left; cursor:pointer; }
.kb-item:hover,.kb-item.active { background:var(--arco-primary-light); color:var(--arco-primary); }
.kb-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.kb-add { margin-top:10px; }
.kb-panel { padding:24px; max-width:760px; }
.panel-heading { display:flex; justify-content:space-between; gap:16px; margin-bottom:20px; }
.panel-heading h3 { margin:0; color:var(--neutral-text-1); display:flex; align-items:center; gap:8px; }
.kb-code { font-size:12px; color:var(--neutral-text-3); font-weight:400; }
.panel-heading p { margin:6px 0 0; font-size:13px; color:var(--neutral-text-2); }
.field,.field-row { margin:16px 0; }
.field label,.field-row label { display:block; margin-bottom:7px; font-size:13px; font-weight:500; color:var(--neutral-text-1); }
.field-row { display:flex; align-items:center; justify-content:space-between; }
.field-row label { margin:0; }
.panel-actions { display:flex; justify-content:flex-end; gap:12px; margin-top:24px; }
.panel-actions :first-child { margin-right:auto; }
.hint { margin-top:8px; font-size:12px; color:var(--neutral-text-3); text-align:right; }
.doc-item { padding:10px 4px; border-bottom:1px solid var(--neutral-border); }
.doc-title { font-size:13px; color:var(--neutral-text-1); }
.doc-meta { display:flex; gap:8px; align-items:center; margin-top:4px; font-size:12px; color:var(--neutral-text-3); }
@media (max-width: 760px){.kb-tab{grid-template-columns:1fr}.kb-list{border-right:0;border-bottom:1px solid var(--neutral-border)}.kb-item{display:inline-flex;width:auto;margin-right:4px}.kb-panel{padding:18px}.panel-heading{align-items:flex-start;flex-direction:column}}
</style>
