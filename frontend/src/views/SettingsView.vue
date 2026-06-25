<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard, NTabs, NTabPane, NForm, NFormItem, NInput, NButton,
  NSpace, NAvatar, NUpload, NIcon, NTag, useMessage,
} from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { PersonOutline, LockClosedOutline, SettingsOutline, CloudUploadOutline } from '@vicons/ionicons5'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()

const userId = computed(() => authStore.user?.id || '')
const profileFormRef = ref<FormInst | null>(null)
const passwordFormRef = ref<FormInst | null>(null)
const savingProfile = ref(false)
const savingPassword = ref(false)

const profileForm = ref({
  username: '',
  email: '',
  avatar_url: '',
})

const passwordForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

const profileRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度 3-50 字符', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '只能包含字母、数字、下划线', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
}

const passwordRules: FormRules = {
  old_password: [
    { required: true, message: '请输入当前密码', trigger: 'blur' },
  ],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码长度 8-128 字符', trigger: 'blur' },
    { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: '密码必须包含字母和数字', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (_rule, value) => {
        if (value !== passwordForm.value.new_password) {
          return new Error('两次输入的密码不一致')
        }
        return true
      },
      trigger: 'blur',
    },
  ],
}

onMounted(() => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }
  if (authStore.user) {
    profileForm.value.username = authStore.user.username
    profileForm.value.email = authStore.user.email
    profileForm.value.avatar_url = authStore.user.avatar_url || ''
  }
})

async function saveProfile() {
  try {
    await profileFormRef.value?.validate()
  } catch {
    return
  }
  savingProfile.value = true
  try {
    await apiClient.put(`/users/${userId.value}`, {
      username: profileForm.value.username,
      email: profileForm.value.email,
      avatar_url: profileForm.value.avatar_url || null,
    })
    await authStore.fetchUser()
    message.success('个人信息保存成功')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  try {
    await passwordFormRef.value?.validate()
  } catch {
    return
  }
  savingPassword.value = true
  try {
    await apiClient.put(`/users/${userId.value}/password`, {
      old_password: passwordForm.value.old_password,
      new_password: passwordForm.value.new_password,
    })
    message.success('密码修改成功')
    passwordForm.value = { old_password: '', new_password: '', confirm_password: '' }
  } catch (e: any) {
    message.error(e.response?.data?.detail || '密码修改失败')
  } finally {
    savingPassword.value = false
  }
}
</script>

<template>
  <div class="page-container">
    <h1 class="page-title">系统设置</h1>
    <div class="settings-page animate-fade-in-up">
      <NTabs type="line" animated>
        <!-- 个人信息 -->
        <NTabPane name="profile" tab="个人信息">
          <NCard :bordered="false" class="arco-card settings-card">
          <div class="avatar-section">
            <NAvatar round :size="80" :src="profileForm.avatar_url || undefined">
              <NIcon :size="36"><PersonOutline /></NIcon>
            </NAvatar>
            <div class="avatar-info">
              <div class="avatar-name">{{ authStore.user?.username }}</div>
              <NTag size="small" :type="authStore.user?.role === 'admin' ? 'warning' : 'default'">
                {{ authStore.user?.role }}
              </NTag>
            </div>
          </div>

          <NForm ref="profileFormRef" :model="profileForm" :rules="profileRules" label-placement="top">
            <NFormItem label="用户名" path="username">
              <NInput v-model:value="profileForm.username" placeholder="用户名" />
            </NFormItem>
            <NFormItem label="邮箱" path="email">
              <NInput v-model:value="profileForm.email" placeholder="邮箱" />
            </NFormItem>
            <NFormItem label="头像 URL" path="avatar_url">
              <NInput v-model:value="profileForm.avatar_url" placeholder="留空使用默认头像" />
            </NFormItem>
            <div class="form-actions">
              <NButton type="primary" :loading="savingProfile" @click="saveProfile">保存修改</NButton>
            </div>
          </NForm>
        </NCard>
      </NTabPane>

      <!-- 安全 / 修改密码 -->
      <NTabPane name="security" tab="安全设置">
        <NCard :bordered="false" class="arco-card settings-card">
          <template #header>
            <NSpace align="center">
              <NIcon :size="18"><LockClosedOutline /></NIcon>
              <span>修改密码</span>
            </NSpace>
          </template>
          <NForm ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-placement="top">
            <NFormItem label="当前密码" path="old_password">
              <NInput v-model:value="passwordForm.old_password" type="password" show-password-on="click" placeholder="请输入当前密码" />
            </NFormItem>
            <NFormItem label="新密码" path="new_password">
              <NInput v-model:value="passwordForm.new_password" type="password" show-password-on="click" placeholder="至少8位，包含字母和数字" />
            </NFormItem>
            <NFormItem label="确认新密码" path="confirm_password">
              <NInput v-model:value="passwordForm.confirm_password" type="password" show-password-on="click" placeholder="请再次输入新密码" />
            </NFormItem>
            <div class="form-actions">
              <NButton type="primary" :loading="savingPassword" @click="savePassword">修改密码</NButton>
            </div>
          </NForm>
        </NCard>
      </NTabPane>

      <!-- 偏好设置 -->
      <NTabPane name="preferences" tab="偏好设置">
        <NCard :bordered="false" class="arco-card settings-card">
          <template #header>
            <NSpace align="center">
              <NIcon :size="18"><SettingsOutline /></NIcon>
              <span>界面偏好</span>
            </NSpace>
          </template>
          <div class="pref-list">
            <div class="pref-item">
              <div class="pref-info">
                <div class="pref-label">主题模式</div>
                <div class="pref-desc">跟随系统主题切换明暗模式</div>
              </div>
              <NTag size="small" type="info">即将支持</NTag>
            </div>
            <div class="pref-item">
              <div class="pref-info">
                <div class="pref-label">通知提醒</div>
                <div class="pref-desc">任务完成时发送通知</div>
              </div>
              <NTag size="small" type="info">即将支持</NTag>
            </div>
            <div class="pref-item">
              <div class="pref-info">
                <div class="pref-label">默认分析流程</div>
                <div class="pref-desc">设置常用的分析流程作为默认</div>
              </div>
              <NTag size="small" type="info">即将支持</NTag>
            </div>
          </div>
        </NCard>
      </NTabPane>
    </NTabs>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 640px;
  margin: 0 auto;
}
.avatar-section {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--neutral-border);
}
.avatar-name {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--neutral-text-1);
}
.form-actions {
  margin-top: 24px;
}
.pref-list {
  display: flex;
  flex-direction: column;
}
.pref-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  border-bottom: 1px solid var(--neutral-border);
}
.pref-item:last-child {
  border-bottom: none;
}
.pref-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--neutral-text-1);
}
.pref-desc {
  font-size: 13px;
  color: var(--neutral-text-3);
  margin-top: 4px;
}
</style>
