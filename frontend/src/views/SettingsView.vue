<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  NCard, NTabs, NTabPane, NForm, NFormItem, NInput, NButton,
  NSpace, NAvatar, NIcon, NTag, NSwitch, useMessage,
  NAlert, NDivider,
} from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { PersonOutline, LockClosedOutline, SettingsOutline, GlobeOutline, ShieldCheckmarkOutline } from '@vicons/ionicons5'
import QRCode from 'qrcode'
import AdminTOTPConfirmModal from '@/components/AdminTOTPConfirmModal.vue'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { SiteSettings } from '@/types'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()

const isAdmin = computed(() => authStore.user?.role === 'admin')
const displayName = computed(() => authStore.user?.nickname || authStore.user?.username || '')

// ===== 平台全局配置 =====
const platformConfig = ref<SiteSettings>({ registration_enabled: true, totp_policy: 'optional' })
const platformLoading = ref(false)
const platformPending = ref<Partial<SiteSettings> | null>(null)
const platformTotpModalVisible = ref(false)
const platformTotpLoading = ref(false)

const userId = computed(() => authStore.user?.id || '')
const profileFormRef = ref<FormInst | null>(null)
const passwordFormRef = ref<FormInst | null>(null)
const savingProfile = ref(false)
const savingPassword = ref(false)

const profileForm = ref({
  username: '',
  email: '',
  nickname: '',
  avatar_url: '',
})

const passwordForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

// ===== 二次验证（TOTP 2FA）状态 =====
const faEnabled = ref(false)
const faHasSecret = ref(false)
const faStep = ref<'idle' | 'setup' | 'disable'>('idle')
const faLoading = ref(false)
const otpauthUri = ref('')
const setupSecret = ref('')
const qrDataUrl = ref('')
const verifyCode = ref('')
const disableCode = ref('')

async function loadPlatformConfig() {
  try {
    const res = await apiClient.get<SiteSettings>('/platform/config')
    platformConfig.value = res.data
  } catch {
    /* 读取失败使用默认配置 */
  }
}

async function load2FAStatus() {
  try {
    const status = await authStore.fetch2FAStatus()
    faEnabled.value = status.enabled
    faHasSecret.value = status.has_secret
  } catch (e: any) {
    message.error(e.response?.data?.detail || '获取 2FA 状态失败')
  }
}

async function startSetup2FA() {
  faLoading.value = true
  try {
    const setup = await authStore.setup2FA()
    otpauthUri.value = setup.otpauth_uri
    setupSecret.value = setup.secret
    qrDataUrl.value = await QRCode.toDataURL(setup.otpauth_uri, { width: 200, margin: 2 })
    faStep.value = 'setup'
  } catch (e: any) {
    message.error(e.response?.data?.detail || '生成绑定二维码失败')
  } finally {
    faLoading.value = false
  }
}

async function confirmSetup2FA() {
  if (!/^\d{6}$/.test(verifyCode.value)) {
    message.error('请输入 6 位数字验证码')
    return
  }
  faLoading.value = true
  try {
    await authStore.confirmEnable2FA(verifyCode.value)
    message.success('二次验证已开启')
    faStep.value = 'idle'
    verifyCode.value = ''
    await load2FAStatus()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '验证码错误')
  } finally {
    faLoading.value = false
  }
}

function cancelSetup2FA() {
  faStep.value = 'idle'
  verifyCode.value = ''
  otpauthUri.value = ''
  setupSecret.value = ''
  qrDataUrl.value = ''
}

function startDisable2FA() {
  faStep.value = 'disable'
  disableCode.value = ''
}

async function confirmDisable2FA() {
  if (!/^\d{6}$/.test(disableCode.value)) {
    message.error('请输入 6 位数字验证码')
    return
  }
  faLoading.value = true
  try {
    await authStore.disable2FA(disableCode.value)
    message.success('二次验证已关闭')
    faStep.value = 'idle'
    disableCode.value = ''
    await load2FAStatus()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '验证码错误')
  } finally {
    faLoading.value = false
  }
}

function cancelDisable2FA() {
  faStep.value = 'idle'
  disableCode.value = ''
}

function copySecret() {
  navigator.clipboard.writeText(setupSecret.value)
    .then(() => message.success('密钥已复制'))
    .catch(() => message.error('复制失败'))
}

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

onMounted(async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }
  try {
    await authStore.fetchUser()
  } catch {
    router.push('/login')
    return
  }
  if (authStore.user) {
    profileForm.value.username = authStore.user.username
    profileForm.value.email = authStore.user.email
    profileForm.value.nickname = authStore.user.nickname || ''
    profileForm.value.avatar_url = authStore.user.avatar_url || ''
  }
  await loadPlatformConfig()
  await load2FAStatus()
})

function requestPlatformChange(patch: Partial<SiteSettings>) {
  platformPending.value = patch
  platformTotpModalVisible.value = true
}

async function confirmPlatformChange(code: string) {
  if (!platformPending.value) return
  platformTotpLoading.value = true
  platformLoading.value = true
  try {
    const res = await apiClient.patch<SiteSettings>('/admin/platform-config', platformPending.value, {
      headers: { 'X-TOTP-Code': code },
    })
    platformConfig.value = res.data
    platformTotpModalVisible.value = false
    message.success('平台全局配置已保存')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    platformLoading.value = false
    platformTotpLoading.value = false
    platformPending.value = null
  }
}

function cancelPlatformChange() {
  platformPending.value = null
}

function onRegistrationChange(value: boolean) {
  if (value === platformConfig.value.registration_enabled) return
  requestPlatformChange({ registration_enabled: value })
}

function onTOTPPolicyChange(value: SiteSettings['totp_policy']) {
  if (value === platformConfig.value.totp_policy) return
  requestPlatformChange({ totp_policy: value })
}

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
      nickname: profileForm.value.nickname || null,
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

const totpPolicyOptions: { key: SiteSettings['totp_policy']; label: string; desc: string }[] = [
  { key: 'off', label: '关闭', desc: '全平台禁用 TOTP' },
  { key: 'optional', label: '可选', desc: '用户自行决定是否开启' },
  { key: 'required', label: '强制', desc: '所有用户必须开启 TOTP' },
]
</script>

<template>
  <div class="settings-page-wrapper">
    <div class="settings-page-header">
      <h1 class="page-title">系统设置</h1>
    </div>
    <div class="settings-page">
      <NTabs type="line" animated>
        <!-- 个人信息 -->
        <NTabPane name="profile" tab="个人信息">
          <NCard :bordered="false" class="arco-card settings-card">
            <div class="avatar-section">
              <NAvatar round :size="80" :src="profileForm.avatar_url || undefined">
                <NIcon :size="36"><PersonOutline /></NIcon>
              </NAvatar>
              <div class="avatar-info">
                <div class="avatar-name">{{ displayName }}</div>
                <NTag size="small" :type="authStore.user?.role === 'admin' ? 'warning' : 'default'">
                  {{ authStore.user?.role }}
                </NTag>
              </div>
            </div>

            <NForm ref="profileFormRef" :model="profileForm" :rules="profileRules" label-placement="top">
              <NFormItem label="用户名" path="username">
                <NInput v-model:value="profileForm.username" placeholder="用户名" />
              </NFormItem>
              <NFormItem label="昵称" path="nickname">
                <NInput v-model:value="profileForm.nickname" placeholder="留空则使用用户名" />
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
          <div class="settings-section-grid">
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

            <!-- 二次验证（TOTP 2FA） -->
            <NCard v-if="platformConfig.totp_policy === 'off'" :bordered="false" class="arco-card settings-card twofa-card twofa-disabled">
              <template #header>
                <NSpace align="center">
                  <NIcon :size="18" class="opacity-50"><ShieldCheckmarkOutline /></NIcon>
                  <span class="text-gray-400">二次验证（TOTP）</span>
                </NSpace>
              </template>
              <p class="text-sm text-gray-400">
                平台管理员已关闭二次验证功能，如有需要请联系管理员。
              </p>
            </NCard>

            <NCard v-else :bordered="false" class="arco-card settings-card twofa-card">
              <template #header>
                <NSpace align="center">
                  <NIcon :size="18"><ShieldCheckmarkOutline /></NIcon>
                  <span>二次验证（TOTP）</span>
                  <NTag v-if="faEnabled" size="small" type="success">已开启</NTag>
                  <NTag v-else size="small">未开启</NTag>
                </NSpace>
              </template>

              <!-- 强制开启提示 -->
              <NAlert
                v-if="platformConfig.totp_policy === 'required' && !faEnabled"
                type="warning"
                :show-icon="false"
                class="twofa-alert"
              >
                ⚠️ 平台要求所有用户必须开启二次验证，请尽快完成绑定。
              </NAlert>

              <!-- 未开启：引导绑定 -->
              <div v-if="!faEnabled && faStep !== 'setup'">
                <NAlert type="info" :show-icon="false" class="twofa-alert">
                  绑定 Google Authenticator、Microsoft Authenticator 等 TOTP 验证器后，
                  登录时将要求输入 6 位动态验证码，提升账号安全性。
                </NAlert>
                <div class="form-actions">
                  <NButton
                    :loading="faLoading"
                    :type="platformConfig.totp_policy === 'required' ? 'warning' : 'primary'"
                    :class="platformConfig.totp_policy === 'required' ? 'totp-required-btn' : ''"
                    @click="startSetup2FA"
                  >
                    开启二次验证
                  </NButton>
                </div>
              </div>

              <!-- 绑定中：展示二维码与确认 -->
              <div v-else-if="faStep === 'setup'">
                <NAlert type="warning" title="绑定步骤" class="twofa-alert">
                  1. 使用 Authenticator 应用扫描下方二维码；<br>
                  2. 输入应用显示的 6 位验证码完成绑定。
                </NAlert>
                <div class="twofa-qrcode">
                  <img v-if="qrDataUrl" :src="qrDataUrl" alt="2FA QR Code">
                </div>
                <div class="twofa-secret">
                  <span class="secret-label">手动输入密钥：</span>
                  <code>{{ setupSecret }}</code>
                  <NButton size="tiny" quaternary @click="copySecret">复制</NButton>
                </div>
                <NDivider />
                <NForm label-placement="top">
                  <NFormItem label="6 位验证码">
                    <NInput
                      v-model:value="verifyCode"
                      placeholder="请输入 Authenticator 中的 6 位验证码"
                      maxlength="6"
                      :input-props="{ inputmode: 'numeric', autocomplete: 'one-time-code' }"
                      @keyup.enter="confirmSetup2FA"
                    />
                  </NFormItem>
                  <div class="form-actions">
                    <NButton type="primary" :loading="faLoading" @click="confirmSetup2FA">
                      确认绑定
                    </NButton>
                    <NButton @click="cancelSetup2FA">取消</NButton>
                  </div>
                </NForm>
              </div>

              <!-- 已开启：关闭二次验证 -->
              <div v-else-if="faEnabled && faStep !== 'disable'">
                <NAlert type="success" :show-icon="false" class="twofa-alert">
                  当前账号已开启二次验证。登录或执行管理员敏感操作时，将要求输入 Authenticator 中的 6 位动态验证码。
                </NAlert>
                <div class="form-actions">
                  <NButton type="warning" ghost @click="startDisable2FA">关闭二次验证</NButton>
                </div>
              </div>

              <!-- 关闭中：输入当前验证码 -->
              <div v-else-if="faStep === 'disable'">
                <NAlert type="warning" :show-icon="false" class="twofa-alert">
                  为防止他人盗号后关闭二次验证，请先输入 Authenticator 中的 6 位当前验证码。
                </NAlert>
                <NForm label-placement="top">
                  <NFormItem label="6 位验证码">
                    <NInput
                      v-model:value="disableCode"
                      placeholder="请输入当前 6 位验证码"
                      maxlength="6"
                      :input-props="{ inputmode: 'numeric', autocomplete: 'one-time-code' }"
                      @keyup.enter="confirmDisable2FA"
                    />
                  </NFormItem>
                  <div class="form-actions">
                    <NButton type="error" :loading="faLoading" @click="confirmDisable2FA">
                      确认关闭
                    </NButton>
                    <NButton @click="cancelDisable2FA">取消</NButton>
                  </div>
                </NForm>
              </div>
            </NCard>
          </div>
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

        <!-- 平台设置（仅管理员可见） -->
        <NTabPane v-if="isAdmin" name="platform" tab="平台设置">
          <div class="settings-section-grid">
            <!-- 开放注册 -->
            <NCard :bordered="false" class="arco-card settings-card">
              <template #header>
                <NSpace align="center">
                  <span class="text-xl">🌐</span>
                  <span>开放用户注册</span>
                </NSpace>
              </template>
              <p class="text-sm text-gray-500 mb-6">
                关闭后新用户将无法自助注册，需由管理员创建账号
              </p>
              <NSwitch
                :value="platformConfig.registration_enabled"
                :loading="platformLoading"
                @update:value="onRegistrationChange"
              />
            </NCard>

            <!-- TOTP 策略 -->
            <NCard :bordered="false" class="arco-card settings-card">
              <template #header>
                <NSpace align="center">
                  <span class="text-xl">🔐</span>
                  <span>二次验证（TOTP）</span>
                </NSpace>
              </template>
              <div class="flex flex-col gap-3">
                <div class="totp-segmented-control">
                  <button
                    v-for="opt in totpPolicyOptions"
                    :key="opt.key"
                    type="button"
                    :disabled="platformLoading"
                    class="totp-segment-btn"
                    :class="{ active: platformConfig.totp_policy === opt.key }"
                    @click="onTOTPPolicyChange(opt.key)"
                  >
                    {{ opt.label }}
                  </button>
                </div>
                <p class="text-sm text-gray-500">
                  {{ totpPolicyOptions.find(o => o.key === platformConfig.totp_policy)?.desc }}
                </p>
              </div>
            </NCard>
          </div>
        </NTabPane>
      </NTabs>

      <!-- 平台配置修改：TOTP 二次确认 -->
      <AdminTOTPConfirmModal
        v-model:show="platformTotpModalVisible"
        title="修改平台全局配置"
        description="开放/关闭用户注册或调整 TOTP 策略属于高敏感操作，请输入当前 6 位 TOTP 验证码以继续。"
        confirm-text="确认修改"
        :loading="platformTotpLoading"
        @confirm="confirmPlatformChange"
        @cancel="cancelPlatformChange"
      />
    </div>
  </div>
</template>

<style scoped>
.settings-page-wrapper {
  min-height: 100%;
  background: var(--neutral-bg);
  padding-bottom: 48px;
}

.settings-page-header {
  max-width: 1024px;
  margin: 0 auto;
  padding: 32px 24px 16px;
}

.settings-page {
  max-width: 1024px;
  margin: 0 auto;
  padding: 0 24px;
}

@media (min-width: 1440px) {
  .settings-page-header,
  .settings-page {
    max-width: 1152px;
    padding-left: 32px;
    padding-right: 32px;
  }
}

@media (max-width: 640px) {
  .settings-page-header {
    padding: 24px 16px 12px;
  }
  .settings-page {
    padding: 0 16px;
  }
}

.settings-section-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
}

@media (min-width: 1024px) {
  .settings-section-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.settings-card {
  padding: 32px;
}

@media (max-width: 640px) {
  .settings-card {
    padding: 24px;
  }
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
  display: flex;
  gap: 12px;
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

.twofa-card {
  margin-top: 0;
}

.twofa-disabled {
  background: #f9fafb !important;
  border-color: #f3f4f6 !important;
}

.twofa-alert {
  margin-bottom: 20px;
}

.twofa-qrcode {
  display: flex;
  justify-content: center;
  margin: 20px 0;
}

.twofa-qrcode img {
  width: 200px;
  height: 200px;
  border-radius: 8px;
  border: 1px solid var(--neutral-border);
}

.twofa-secret {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  font-size: 13px;
  color: var(--neutral-text-2);
}

.twofa-secret code {
  background: var(--neutral-fill);
  padding: 4px 8px;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.secret-label {
  color: var(--neutral-text-3);
}

.totp-required-btn {
  background: #f97316 !important;
  color: #fff !important;
}

.totp-required-btn:hover {
  background: #ea580c !important;
}

@media (max-width: 480px) {
  .twofa-secret {
    flex-direction: column;
    align-items: flex-start;
  }
  .form-actions {
    flex-wrap: wrap;
  }
}

.totp-segmented-control {
  display: inline-flex;
  background: var(--neutral-bg);
  border-radius: 8px;
  padding: 3px;
  gap: 2px;
  width: fit-content;
}

.totp-segment-btn {
  position: relative;
  border: none;
  background: transparent;
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--neutral-text-3);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: inherit;
  z-index: 1;
}

.totp-segment-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.totp-segment-btn.active {
  background: var(--neutral-card);
  color: var(--neutral-text-1);
  box-shadow: 0 1px 3px rgba(29, 33, 41, 0.08);
  z-index: 2;
}

.totp-segment-btn:hover:not(.active):not(:disabled) {
  color: var(--neutral-text-1);
}
</style>
