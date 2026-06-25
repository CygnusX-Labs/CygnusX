<template>
  <div class="login-container">
    <div class="login-orb login-orb--1" />
    <div class="login-orb login-orb--2" />
    <div class="login-card animate-scale-in">
      <div class="login-header">
        <h2 class="login-title gradient-text">OmicHub</h2>
        <p class="login-subtitle">欢迎登录多组学分析平台</p>
      </div>
      <n-form ref="formRef" :model="formData" :rules="rules" class="login-form">
        <n-form-item label="用户名" path="username">
          <n-input
            v-model:value="formData.username"
            placeholder="请输入用户名"
            size="large"
            @keyup.enter="handleLogin"
          />
        </n-form-item>

        <n-form-item label="密码" path="password">
          <n-input
            v-model:value="formData.password"
            type="password"
            show-password-on="click"
            placeholder="请输入密码"
            size="large"
            @keyup.enter="handleLogin"
          />
        </n-form-item>

        <div class="login-actions">
          <n-button type="primary" size="large" :loading="loading" @click="handleLogin">
            登录
          </n-button>
          <n-button size="large" @click="$router.push('/register')">
            注册
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

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const formRef = ref()
const loading = ref(false)

const formData = ref({
  username: '',
  password: '',
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度在 3 到 50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码长度在 8 到 128 个字符', trigger: 'blur' },
  ],
}

const handleLogin = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
  } catch {
    return
  }

  loading.value = true

  try {
    await authStore.login(formData.value.username, formData.value.password)
    message.success('登录成功')
    router.push('/')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '登录失败，请检查用户名和密码')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
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

.login-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.3;
  pointer-events: none;
}
.login-orb--1 {
  width: 400px;
  height: 400px;
  background: #a5b4fc;
  top: -100px;
  right: -100px;
  animation: drift 14s ease-in-out infinite;
}
.login-orb--2 {
  width: 300px;
  height: 300px;
  background: #67e8f9;
  bottom: -50px;
  left: -50px;
  animation: drift 16s ease-in-out infinite reverse;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 400px;
  padding: 40px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}
.login-title {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 8px;
}
.login-subtitle {
  font-size: 14px;
  color: var(--neutral-text-3);
}
.login-form {
  margin-top: 24px;
}
.login-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 32px;
}
</style>
