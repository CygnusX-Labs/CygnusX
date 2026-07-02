<template>
  <div class="login-container">
    <div class="login-orb login-orb--1" />
    <div class="login-orb login-orb--2" />
    <div class="login-card animate-scale-in">
      <LoginCats />
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

        <div v-if="errorMessage" class="login-error-message">
          {{ errorMessage }}
        </div>

        <div class="login-actions">
          <n-button type="primary" size="large" :loading="loading" @click="handleLogin">
            登录
          </n-button>
          <n-button size="large" @click="handleRegister">
            注册
          </n-button>
        </div>
      </n-form>
    </div>
    <RegistrationDisabledModal
      v-model:show="showRegModal"
      :message="siteConfig.registrationDisabledMessage"
      :contact="siteConfig.adminContact"
    />
    <!-- 账户未激活弹窗：专用 ActivationModal（点击计数 + 文案切换 + 第 5 次猫爪彩蛋），
         文案/联系方式由 YAML activation 段驱动 -->
    <ActivationModal v-model:show="showInactiveModal" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { useSiteConfigStore } from '@/stores/site-config'
import RegistrationDisabledModal from '@/components/RegistrationDisabledModal.vue'
import ActivationModal from '@/components/ActivationModal.vue'
import LoginCats from '@/components/LoginCats.vue'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const siteConfig = useSiteConfigStore()
const formRef = ref()
const loading = ref(false)
const errorMessage = ref('')
const showRegModal = ref(false)
// 账户未激活时弹模态框（带管理员联系方式），比纯 toast 更友好
const showInactiveModal = ref(false)

// 拉取注册开关（site-settings，DB）+ 提示文案（site-content，YAML）
onMounted(() => {
  siteConfig.fetchSiteConfig()
})

// 点击“注册”：开关关闭时拦截并弹自定义模态框提示，不跳转；开启时正常跳转注册页
// 首次点击前若配置尚未就绪，先等一次拉取（已就绪则立即放行，不额外发请求）
async function handleRegister() {
  if (!siteConfig.loaded) await siteConfig.fetchSiteConfig()
  if (siteConfig.allowRegistration) {
    router.push('/register')
    return
  }
  showRegModal.value = true
}

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

  errorMessage.value = ''

  try {
    await formRef.value.validate()
  } catch {
    return
  }

  loading.value = true

  try {
    await authStore.login(formData.value.username, formData.value.password)
    message.success('登录成功')
    try {
      await router.push('/')
    } catch {
      window.location.href = '/'
    }
    setTimeout(() => {
      if (window.location.pathname === '/login') {
        window.location.href = '/'
      }
    }, 100)
  } catch (error: any) {
    const status = error.response?.status
    const detail: string = error.response?.data?.detail || ''

    // 系统内部错误（500/502/503 等）：明确提示系统故障，避免被误判为"密码错误"，
    // 让运维与用户能区分认证失败与服务端异常。
    if (status >= 500) {
      const sysMsg = '系统内部错误，请联系管理员'
      errorMessage.value = sysMsg
      message.error(sysMsg)
    } else if (detail.includes('未激活')) {
      // 账户未激活：弹模态框并附带管理员联系方式，引导用户联系管理员激活
      errorMessage.value = detail
      if (!siteConfig.loaded) await siteConfig.fetchSiteConfig().catch(() => {})
      showInactiveModal.value = true
    } else {
      // 401/403 等认证失败：模糊提示"用户名或密码错误"（不区分用户名是否存在，防枚举）
      const authMsg = detail || '用户名或密码错误'
      errorMessage.value = authMsg
      message.error(authMsg)
    }
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
  /* Glassmorphism：半透明白底，透出底部蓝色渐变 */
  background-color: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  /* 玻璃边缘：极细半透明白边 */
  border: 1px solid rgba(255, 255, 255, 0.4);
  border-radius: 16px;
  /* 弥散柔和阴影，取代原先偏重的 60px 阴影 */
  box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1);
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
.login-error-message {
  margin-bottom: 16px;
  color: #d03050;
  font-size: 13px;
  text-align: center;
}
.login-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 32px;
}

/* 表单校验提示精致化：「请输入用户名/密码」等红色校验文案
   覆盖 Naive UI .n-form-item 内部反馈行，加间距、缩字号，避免排版过紧 */
:deep(.n-form-item) .n-form-item-feedback {
  min-height: 18px;
  padding-top: 4px;
}
:deep(.n-form-item) .n-form-item-feedback__line {
  font-size: 12px;
  line-height: 1.4;
}
</style>
