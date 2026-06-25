<template>
  <div class="register-container">
    <div class="register-card">
      <h2 class="register-title">用户注册</h2>
      <n-form ref="formRef" :model="formData" :rules="rules" class="register-form">
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
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { NAlert } from 'naive-ui'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const formRef = ref()
const loading = ref(false)
const errorMsg = ref('')

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
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.register-card {
  width: 100%;
  max-width: 450px;
  padding: 40px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.register-title {
  text-align: center;
  margin-bottom: 32px;
  color: #333;
  font-size: 24px;
  font-weight: 600;
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
