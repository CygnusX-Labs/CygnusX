<script setup lang="ts">
import { MdEditor } from 'md-editor-v3'
import 'md-editor-v3/lib/style.css'
import { useMessage } from 'naive-ui'
import apiClient from '@/api/client'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const message = useMessage()

function handleChange(value: string) {
  emit('update:modelValue', value)
}

async function handleUploadImg(files: File[], callback: (urls: string[]) => void) {
  const urls: string[] = new Array(files.length)
  try {
    await Promise.all(
      files.map(async (file, index) => {
        const formData = new FormData()
        formData.append('file', file)
        const res = await apiClient.post<{ url: string }>('/knowledge/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        urls[index] = res.data.url
      }),
    )
    callback(urls)
  } catch (err: unknown) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    message.error(detail || '图片上传失败')
  }
}
</script>

<template>
  <div class="doc-editor">
    <MdEditor
      :model-value="props.modelValue"
      :preview="false"
      :toolbars-exclude="['github', 'save', 'pageFullscreen', 'catalog']"
      :style="{ height: 'calc(100vh - 220px)' }"
      placeholder="在此编写 Markdown 文档…"
      @update:model-value="handleChange"
      @on-upload-img="handleUploadImg"
    />
  </div>
</template>

<style scoped>
.doc-editor {
  width: 100%;
}

.doc-editor :deep(.md-editor) {
  border-radius: 8px;
  border: 1px solid var(--neutral-border);
}
</style>
