<template>
  <div class="login-page" role="main" aria-label="登录 CygnusX">
    <StarField />
    <LoginPageQuote />
    <div class="login-content">
      <div class="login-card-wrapper">
        <div class="login-card animate-scale-in">
          <div class="login-header">
            <LogoAnimation />
            <h2 class="login-title">CygnusX</h2>
            <p class="login-subtitle">欢迎登录多组学分析平台</p>
            <p class="login-supporting-text">面向生命科学的智能科研平台</p>
          </div>
          <n-form ref="formRef" :model="formData" :rules="rules" class="login-form">
            <!-- 第一步：账号密码 -->
            <template v-if="step === 'credentials'">
              <n-form-item label="用户名" path="username">
                <n-input
                  v-model:value="formData.username"
                  placeholder="请输入用户名"
                  size="large"
                  autocomplete="username"
                  @keyup.enter="handleLogin"
                >
                  <template #prefix>
                    <n-icon :component="PersonOutline" />
                  </template>
                </n-input>
              </n-form-item>

              <n-form-item label="密码" path="password">
                <n-input
                  v-model:value="formData.password"
                  type="password"
                  show-password-on="click"
                  placeholder="请输入密码"
                  size="large"
                  autocomplete="current-password"
                  @keyup.enter="handleLogin"
                >
                  <template #prefix>
                    <n-icon :component="LockClosedOutline" />
                  </template>
                </n-input>
              </n-form-item>
            </template>

            <!-- 第二步：TOTP 6 位验证码 -->
            <template v-else>
              <n-form-item label="6 位动态验证码" path="totpCode">
                <n-input
                  v-model:value="formData.totpCode"
                  placeholder="请输入 Authenticator 验证码"
                  size="large"
                  maxlength="6"
                  :input-props="{ inputmode: 'numeric', autocomplete: 'one-time-code' }"
                  @keyup.enter="handleVerify2FA"
                />
              </n-form-item>
              <p class="totp-hint">已开启二次验证，请打开 Authenticator 应用查看当前验证码。</p>
            </template>

            <div v-if="errorMessage" class="login-error-message">
              {{ errorMessage }}
            </div>

            <div class="login-actions" :class="{ 'login-actions--totp': step === 'totp' }">
              <LoginButton
                v-if="step === 'credentials'"
                :disabled="isLoginButtonDisabled"
                :loading="loading"
                :success="loginSuccess"
                @click="handleLogin"
              />
              <template v-else>
                <n-button type="primary" size="large" :loading="loading" @click="handleVerify2FA">
                  验证并登录
                </n-button>
                <n-button size="large" @click="resetToCredentials">
                  返回
                </n-button>
              </template>
              <n-button v-if="step === 'credentials'" class="register-button" text @click="handleRegister">
                还没有账号？立即注册
              </n-button>
            </div>
          </n-form>
        </div>
      </div>
      <div
        v-if="step === 'credentials'"
        class="demo-credentials"
        :class="{ 'demo-credentials--dimmed': demoCredentialsDimmed }"
        aria-label="演示账号信息"
      >
        <div class="demo-credentials-copy">
          <strong><span class="demo-badge">Demo</span>公开演示账号</strong>
          <span>用户名：demo</span>
          <span>密码：demo_omichub</span>
        </div>
        <n-button size="small" secondary @click="fillDemoCredentials">
          一键填入
        </n-button>
      </div>
    </div>
    <StardustQuote />
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
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { PersonOutline, LockClosedOutline } from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { useSiteConfigStore } from '@/stores/site-config'
import RegistrationDisabledModal from '@/components/RegistrationDisabledModal.vue'
import ActivationModal from '@/components/ActivationModal.vue'
import LoginButton from '@/components/LoginButton.vue'
import LogoAnimation from '@/components/LogoAnimation.vue'
import LoginPageQuote from '@/components/LoginPageQuote.vue'
import StarField from '@/components/StarField.vue'
import StardustQuote from '@/components/StardustQuote.vue'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const siteConfig = useSiteConfigStore()
const formRef = ref()
const loading = ref(false)
const errorMessage = ref('')
const showRegModal = ref(false)
const demoCredentialsDimmed = ref(false)
let demoCredentialsDimTimer: ReturnType<typeof setTimeout> | null = null
// 账户未激活时弹模态框（带管理员联系方式），比纯 toast 更友好
const showInactiveModal = ref(false)

// 拉取注册开关（site-settings，DB）+ 提示文案（site-content，YAML）
onMounted(() => {
  siteConfig.fetchSiteConfig()
  demoCredentialsDimTimer = setTimeout(() => {
    demoCredentialsDimmed.value = true
  }, 10_000)
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
  totpCode: '',
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
  totpCode: [
    { required: true, message: '请输入 6 位验证码', trigger: 'blur' },
    { pattern: /^\d{6}$/, message: '验证码必须为 6 位数字', trigger: 'blur' },
  ],
}

const step = ref<'credentials' | 'totp'>('credentials')
const challengeToken = ref('')
const loginSuccess = ref(false)
let redirectTimer: ReturnType<typeof setTimeout> | null = null
let loginSuccessTimer: ReturnType<typeof setTimeout> | null = null

const isLoginButtonDisabled = computed(() => {
  return !formData.value.username || !formData.value.password
})

function fillDemoCredentials() {
  step.value = 'credentials'
  formData.value.username = 'demo'
  formData.value.password = 'demo_omichub'
  formData.value.totpCode = ''
  challengeToken.value = ''
  errorMessage.value = ''
}

function resetToCredentials() {
  step.value = 'credentials'
  challengeToken.value = ''
  formData.value.totpCode = ''
  errorMessage.value = ''
}


function redirectHome() {
  try {
    router.push('/')
  } catch {
    window.location.href = '/'
  }
  if (redirectTimer) clearTimeout(redirectTimer)
  redirectTimer = setTimeout(() => {
    if (window.location.pathname === '/login') {
      window.location.href = '/'
    }
  }, 100)
}

function handleLoginError(error: any) {
  const status = error.response?.status
  const detail: string = error.response?.data?.detail || ''

  if (status >= 500) {
    const sysMsg = '系统内部错误，请联系管理员'
    errorMessage.value = sysMsg
    message.error(sysMsg)
  } else if (detail.includes('未激活')) {
    errorMessage.value = detail
    if (!siteConfig.loaded) siteConfig.fetchSiteConfig().catch(() => {})
    showInactiveModal.value = true
  } else if (status === 429 || detail.includes('过于频繁')) {
    const authMsg = detail || '登录尝试过于频繁，请稍后再试'
    errorMessage.value = authMsg
    message.warning(authMsg)
  } else {
    const authMsg = detail || '用户名或密码错误'
    errorMessage.value = authMsg
    message.error(authMsg)
  }
}

const handleLogin = async () => {
  if (!formRef.value || loading.value || loginSuccess.value) return

  errorMessage.value = ''

  try {
    await formRef.value.validate()
  } catch {
    return
  }

  loading.value = true

  try {
    const result = await authStore.login(formData.value.username, formData.value.password)

    if (result.requires_2fa) {
      challengeToken.value = result.challenge_token || ''
      step.value = 'totp'
      message.info('请打开 Authenticator 应用，输入 6 位动态验证码')
      return
    }

    loginSuccess.value = true
    message.success('登录成功')
    if (loginSuccessTimer) clearTimeout(loginSuccessTimer)
    loginSuccessTimer = setTimeout(() => {
      redirectHome()
    }, 1200)
  } catch (error: any) {
    handleLoginError(error)
  } finally {
    loading.value = false
  }
}

const handleVerify2FA = async () => {
  if (!formRef.value || loading.value) return
  errorMessage.value = ''

  try {
    await formRef.value.validate()
  } catch {
    return
  }

  if (!challengeToken.value) {
    errorMessage.value = '2FA 凭证丢失，请重新登录'
    return
  }

  loading.value = true
  try {
    await authStore.complete2FALogin(challengeToken.value, formData.value.totpCode)
    message.success('登录成功')
    redirectHome()
  } catch (error: any) {
    handleLoginError(error)
  } finally {
    loading.value = false
  }
}

onUnmounted(() => {
  if (redirectTimer) clearTimeout(redirectTimer)
  if (loginSuccessTimer) clearTimeout(loginSuccessTimer)
  if (demoCredentialsDimTimer) clearTimeout(demoCredentialsDimTimer)
})
</script>

<style scoped>
/* 氛围层统一走 §32 的 canvas 活氛围层（StarField + initLoginAnimation），不再保留旧 CSS orb 光晕 */

.login-card-wrapper {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 440px;
  padding: 3px;
  border-radius: 20px;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 440px;
  padding: 28px 36px 30px;
  background: rgba(248, 251, 255, 0.94);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(12, 37, 85, 0.18), inset 0 1px rgba(255, 255, 255, 0.64);
  transition: transform 220ms ease-out, box-shadow 220ms ease-out, background-color 220ms ease-out;
}

:root[data-theme='dark'] .login-card-wrapper {
  /* 暗色：使用与平台主色一致的蓝靛边缘 */
  padding: 3px;
  border-radius: 19px;
}

/* 蓝靛边框层：静态锥形渐变，mask 镂空内部 */
:root[data-theme='dark'] .login-card-wrapper::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border-radius: 19px;
  background: conic-gradient(
    from 45deg,
    rgba(91, 139, 255, 0.14) 0deg,
    rgba(155, 184, 255, 0.28) 90deg,
    rgba(91, 139, 255, 0.14) 180deg,
    rgba(112, 102, 236, 0.12) 270deg,
    rgba(91, 139, 255, 0.14) 360deg
  );
  -webkit-mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  padding: 2.5px;
  box-sizing: border-box;
  z-index: 0;
  pointer-events: none;
}

/* 静态环境光晕层 */
:root[data-theme='dark'] .login-card-wrapper::after {
  content: '';
  position: absolute;
  top: -3px;
  left: -3px;
  right: -3px;
  bottom: -3px;
  border-radius: 21px;
  background: transparent;
  box-shadow:
    0 0 22px rgba(91, 139, 255, 0.12),
    0 0 44px rgba(91, 139, 255, 0.05);
  z-index: -1;
  pointer-events: none;
}

:root[data-theme='dark'] .login-card {
  background: rgba(248, 251, 255, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.75);
  box-shadow: 0 20px 60px rgba(0, 9, 30, 0.4), inset 0 1px rgba(255, 255, 255, 0.72);
}

/* §4.2-5：减少透明度时玻璃表面回退实色并移除模糊 */
@media (prefers-reduced-transparency: reduce) {
  .login-card {
    background: var(--neutral-card);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    box-shadow: var(--shadow-card, 0 25px 60px rgba(7, 34, 82, 0.2));
  }

  :root[data-theme='dark'] .login-card {
    background: #f8fbff;
    border: 1px solid rgba(255, 255, 255, 0.8);
  }

  /* 蓝靛边框层与光晕依赖透明叠加，一并回退 */
  :root[data-theme='dark'] .login-card-wrapper::before,
  :root[data-theme='dark'] .login-card-wrapper::after {
    content: none;
  }
}

.login-page {
  position: relative;
  width: 100vw;
  min-height: 100dvh;
  overflow-x: hidden;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-content {
  position: relative;
  z-index: 10;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0 16px;
}

.demo-credentials {
  position: absolute;
  top: 50%;
  left: calc(50% + 252px);
  z-index: 11;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 224px;
  min-height: 92px;
  padding: 12px 13px;
  gap: 12px;
  border: 1px solid rgba(77, 124, 255, 0.2);
  border-radius: 12px;
  background: rgba(248, 251, 255, 0.9);
  box-shadow: 0 12px 30px rgba(12, 37, 85, 0.12);
  color: var(--neutral-text-2);
  font-size: 12px;
  transform: translateY(-50%);
  transition: opacity 800ms ease;
}
.demo-credentials--dimmed {
  opacity: 0.2;
}
.demo-credentials-copy {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.demo-credentials-copy strong {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #24344d;
  font-size: 13px;
  white-space: nowrap;
}
.demo-badge {
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(53, 120, 246, 0.1);
  color: #3578f6;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.demo-credentials-copy span {
  overflow-wrap: anywhere;
}
.demo-credentials :deep(.n-button) {
  flex: 0 0 auto;
}

.login-card:focus-within {
  transform: translateY(-1px);
  box-shadow: 0 30px 72px rgba(7, 34, 82, 0.28), inset 0 1px rgba(255, 255, 255, 0.58);
}

.login-header {
  text-align: center;
  margin-bottom: 14px;
  position: relative;
  z-index: 2;
}
.login-title {
  color: var(--brand-primary);
  /* §3.4 Display 级：28px / 36px / 600 */
  font-size: 28px;
  line-height: 36px;
  font-weight: 700;
  letter-spacing: -0.5px;
  margin-bottom: 4px;
}
.login-subtitle {
  font-size: 14px;
  color: #52647d;
  line-height: 20px;
}
.login-supporting-text {
  margin: 3px 0 0;
  color: #8290a4;
  font-size: 12px;
  line-height: 18px;
}

.login-form {
  margin-top: 0;
}
.login-form :deep(.n-form-item) {
  margin-bottom: 16px;
}
.login-form :deep(.n-form-item:last-of-type) {
  margin-bottom: 20px;
}
.login-error-message {
  margin-bottom: 16px;
  color: var(--arco-danger);
  font-size: 13px;
  text-align: center;
}
.login-actions {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  margin-top: 0;
  gap: 12px;
}
.login-actions--totp {
  align-items: stretch;
}
.login-actions--totp :deep(.n-button) {
  width: 100%;
}
.register-button {
  min-height: 20px;
  padding: 0 !important;
  color: #64748b !important;
  font-size: 13px;
  line-height: 20px;
}
.register-button:hover {
  color: #3578f6 !important;
}

.login-actions :deep(.n-button:not(.n-button--primary-type)) {
  --n-text-color: #64748b !important;
  --n-text-color-hover: #3578f6 !important;
  --n-text-color-pressed: #2865de !important;
  --n-border: none !important;
  --n-border-hover: none !important;
  --n-border-pressed: none !important;
  --n-color: transparent !important;
  --n-color-hover: transparent !important;
  --n-color-pressed: transparent !important;
  font-weight: 500;
  text-decoration: underline;
  text-decoration-color: transparent;
  transition: color 180ms ease-out, text-decoration-color 180ms ease-out, transform 120ms ease-out;
}

.login-actions :deep(.n-button:not(.n-button--primary-type):hover) {
  text-decoration-color: rgba(77, 124, 255, 0.4);
}

.login-actions :deep(.n-button:active) {
  transform: scale(0.98);
}

.totp-hint {
  margin: -8px 0 16px;
  font-size: 13px;
  color: var(--neutral-text-2);
  text-align: center;
}

/* 暗色模式：提升表单标签、输入框、按钮对比度 */
:root[data-theme='dark'] .login-form :deep(.n-form-item .n-form-item-label) {
  color: #334155 !important;
}

:root[data-theme='dark'] .login-form :deep(.n-input) {
  --n-border-color: #dce5f2 !important;
  --n-border-hover: #b8c9e0 !important;
  --n-border-focus: #4b7cf3 !important;
  --n-color: #ffffff !important;
  --n-color-focus: #ffffff !important;
  --n-text-color: #24344d !important;
  --n-placeholder-color: #8290a4 !important;
  --n-box-shadow-focus: 0 0 0 3px rgba(75, 124, 243, 0.12) !important;
  --n-icon-color: #8290a4 !important;
}

:root[data-theme='dark'] .login-actions :deep(.n-button:not(.n-button--primary-type)) {
  --n-text-color: #64748b !important;
  --n-text-color-hover: #3578f6 !important;
  --n-text-color-pressed: #2865de !important;
}

:root[data-theme='dark'] .demo-credentials {
  border-color: rgba(155, 184, 255, 0.24);
  background: rgba(248, 251, 255, 0.94);
}

/* 登录主按钮在暗色下使用更亮的渐变 */
:root[data-theme='dark'] .login-actions :deep(.n-button--primary-type) {
  --n-text-color: #ffffff !important;
  --n-text-color-hover: #ffffff !important;
  --n-text-color-pressed: #f0f0f8 !important;
}

/* 亮色模式：优化输入框边框与 placeholder 可读性 */
.login-form :deep(.n-input) {
  --n-border-color: #dce5f2;
  --n-border-hover: #b8c9e0;
  --n-border-focus: #4b7cf3;
  --n-color: #ffffff;
  --n-color-focus: #ffffff;
  --n-placeholder-color: #8290a4;
  --n-box-shadow-focus: 0 0 0 3px rgba(75, 124, 243, 0.12);
  --n-icon-color: #8290a4;
}

.login-form :deep(.n-input--focus) {
  border-color: var(--arco-primary);
}

.login-form :deep(.n-input .n-input__input-el),
.login-form :deep(.n-input .n-input__textarea-el) {
  color: var(--neutral-text-1);
}
.login-form :deep(.n-input .n-input__placeholder) {
  color: var(--n-placeholder-color);
}
.login-form :deep(.n-form-item .n-form-item-label) {
  color: #52647d;
}

/* 表单校验提示精致化 */
:deep(.n-form-item) .n-form-item-feedback {
  min-height: 18px;
  padding-top: 4px;
}
:deep(.n-form-item) .n-form-item-feedback__line {
  font-size: 12px;
  line-height: 1.4;
}

@media (prefers-reduced-motion: reduce) {
  .login-card,
  .login-actions :deep(.n-button) {
    transition-duration: 1ms;
  }
}

@media (max-width: 480px) {
  .login-card {
    padding: 24px 20px 22px;
  }

}

@media (max-width: 1100px) {
  .demo-credentials {
    position: static;
    width: min(440px, 100%);
    min-height: 0;
    margin-top: 14px;
    transform: none;
  }
}

@media (max-width: 480px) {
  .demo-credentials {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
