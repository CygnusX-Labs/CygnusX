<template>
  <div class="register-container">
    <div class="register-orb register-orb--1" />
    <div class="register-orb register-orb--2" />
    <div class="register-card animate-scale-in">
      <div class="register-header">
        <h2 class="register-title gradient-text">注册账户</h2>
        <p class="register-subtitle">加入 OmicHub 多组学分析平台</p>
      </div>

      <n-alert v-if="registrationClosed" type="warning" :show-icon="true" class="error-alert">
        暂不接受新用户注册，如需账号请联系管理员。
      </n-alert>

      <div v-if="registrationClosed" class="register-actions">
        <n-button size="large" @click="$router.push('/login')">
          返回登录
        </n-button>
      </div>

      <n-form v-if="!registrationClosed" ref="formRef" :model="formData" :rules="rules" class="register-form">
        <n-form-item label="用户名" path="username">
          <n-input
            v-model:value="formData.username"
            placeholder="请输入用户名（字母/数字/下划线，3-50字符）"
            size="large"
          />
        </n-form-item>

        <n-form-item label="邮箱" path="email">
          <n-input
            v-model:value="formData.email"
            placeholder="请输入邮箱地址"
            size="large"
          />
        </n-form-item>

        <n-form-item label="密码" path="password">
          <n-input
            v-model:value="formData.password"
            type="password"
            show-password-on="click"
            placeholder="请输入密码（至少8位，包含字母和数字）"
            size="large"
          />
        </n-form-item>

        <n-form-item label="确认密码" path="confirmPassword">
          <n-input
            v-model:value="formData.confirmPassword"
            type="password"
            show-password-on="click"
            placeholder="请再次输入密码"
            size="large"
            @keyup.enter="handleRegister"
          />
        </n-form-item>

        <n-alert v-if="errorMsg" type="error" :show-icon="true" class="error-alert">
          {{ errorMsg }}
        </n-alert>

        <div class="register-actions">
          <n-button type="primary" size="large" :loading="loading" @click="handleRegister">
            注册
          </n-button>
          <n-button size="large" @click="$router.push('/login')">
            返回登录
          </n-button>
        </div>
      </n-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, NAlert } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const formRef = ref()
const loading = ref(false)
const errorMsg = ref('')
const registrationClosed = ref(false)

onMounted(async () => {
  try {
    const res = await apiClient.get<{ registration_enabled: boolean }>('/site-settings')
    registrationClosed.value = !res.data.registration_enabled
  } catch {
    /* 接口异常默认允许注册 */
  }
})

const formData = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度在 3 到 50 个字符', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '用户名只能包含字母、数字和下划线', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱地址', trigger: 'blur' },
    {
      pattern: /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/,
      message: '请输入正确的邮箱格式',
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码长度在 8 到 128 个字符', trigger: 'blur' },
    { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: '密码必须包含字母和数字', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string) => {
        if (value !== formData.value.password) {
          return Promise.reject('两次输入的密码不一致')
        }
        return Promise.resolve()
      },
      trigger: 'blur',
    },
  ],
}

const handleRegister = async () => {
  if (!formRef.value) return

  errorMsg.value = ''

  try {
    await formRef.value.validate()
  } catch {
    errorMsg.value = '请检查表单填写是否正确'
    return
  }

  loading.value = true

  try {
    await authStore.register({
      username: formData.value.username,
      email: formData.value.email,
      password: formData.value.password,
    })
    message.success('注册成功，请登录')
    router.push('/login')
  } catch (error: any) {
    errorMsg.value = error.response?.data?.detail || '注册失败，请检查输入信息'
    message.error(errorMsg.value)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(-45deg, #165DFF, #3063FF, #6B8DD6, #8E54E9);
  background-size: 400% 400%;
  animation: gradientShift 12s ease infinite;
  position: relative;
  overflow: hidden;
}

.register-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.3;
  pointer-events: none;
}
.register-orb--1 {
  width: 400px;
  height: 400px;
  background: #a5b4fc;
  top: -100px;
  left: -100px;
  animation: drift 14s ease-in-out infinite;
}
.register-orb--2 {
  width: 300px;
  height: 300px;
  background: #67e8f9;
  bottom: -50px;
  right: -50px;
  animation: drift 16s ease-in-out infinite reverse;
}

.register-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 450px;
  padding: 40px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.register-header {
  text-align: center;
  margin-bottom: 32px;
}
.register-title {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 8px;
}
.register-subtitle {
  font-size: 14px;
  color: var(--neutral-text-3);
}
.register-form {
  margin-top: 24px;
}
.register-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 16px;
}
.error-alert {
  margin-bottom: 16px;
}
</style>
