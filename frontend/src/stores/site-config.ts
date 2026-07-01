/**
 * 站点配置 store —— 登录/注册页所需的公开系统配置
 *
 * 两类配置、两个公开接口：
 *   - 注册开关：GET /site-settings → registration_enabled（DB 驱动，/auth/register 强制校验）
 *   - 提示文案 + 管理员联系方式：GET /site-content → registration（data/OmicHub.yaml 驱动，改文件即生效）
 *
 * 任一接口失败都回退到“允许注册 + 默认文案”，保证登录页永不卡死。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import apiClient from '@/api/client'
import type { RegistrationContent } from '@/types/site-content'

// 文案兜底：site-content 拉取失败时使用
const DEFAULT_REGISTRATION: RegistrationContent = {
  disabled_message: '当前平台暂停自助注册，需由管理员创建账号。',
  admin_contact: '',
}

export const useSiteConfigStore = defineStore('site-config', () => {
  // 注册开关（true=开放自助注册）。默认 true：接口异常时不阻断登录页注册入口。
  const registrationEnabled = ref(true)
  // 注册提示文案与管理员联系方式（来自 YAML）。
  const registrationContent = ref<RegistrationContent>({ ...DEFAULT_REGISTRATION })
  // 配置是否已就绪（首次拉取完成后置 true，供点击时判断是否需等待）
  const loaded = ref(false)

  /** 当前是否允许自助注册 */
  const allowRegistration = computed(() => registrationEnabled.value)

  /** 关闭注册时的提示文案（纯文本，用于 message/dialog 标题） */
  const registrationDisabledMessage = computed(
    () => registrationContent.value.disabled_message,
  )

  /** 关闭注册时联系管理员的方式（邮箱/说明，trim 后；空串表示未配置） */
  const adminContact = computed(() => registrationContent.value.admin_contact.trim())

  /** 关闭注册时的完整提示文案（若配置了管理员联系方式则附带，用于 message 兜底场景） */
  const registrationDisabledTip = computed(() =>
    adminContact.value
      ? `${registrationDisabledMessage.value}（联系管理员：${adminContact.value}）`
      : registrationDisabledMessage.value,
  )

  // 并发去重：同一时刻只发一次请求，复用同一个 Promise
  let loadingPromise: Promise<void> | null = null

  /** 拉取站点配置；并发调用会复用同一个请求。 */
  function fetchSiteConfig(): Promise<void> {
    if (loadingPromise) return loadingPromise
    const p = (async () => {
      const [enabled, reg] = await Promise.all([
        // 注册开关：接口异常默认允许注册
        apiClient
          .get<{ registration_enabled: boolean }>('/site-settings')
          .then((res) => res.data.registration_enabled)
          .catch(() => true),
        // 提示文案 + 管理员联系方式：接口异常保留默认文案
        apiClient
          .get<{ registration?: RegistrationContent }>('/site-content')
          .then((res) => res.data.registration)
          .catch(() => undefined),
      ])
      registrationEnabled.value = enabled
      if (reg) registrationContent.value = reg
      loaded.value = true
    })()
    loadingPromise = p
    // 结束后清掉 in-flight 标记，下次调用可重新拉取（保证管理员切换开关后刷新可见）
    p.finally(() => {
      loadingPromise = null
    })
    return p
  }

  return {
    registrationEnabled,
    registrationContent,
    loaded,
    allowRegistration,
    registrationDisabledMessage,
    adminContact,
    registrationDisabledTip,
    fetchSiteConfig,
  }
})
