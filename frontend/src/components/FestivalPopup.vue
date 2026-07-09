<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { festivalApi } from '@/api/festival'
import FestivalEffect from './FestivalEffect.vue'
import FestivalDecoration from './FestivalDecoration.vue'
import { resolveFestivalTheme } from '@/utils/festivalThemes'
import type { FestivalConfig } from '@/types/festival'

interface Props {
  festival: FestivalConfig
  /** 预览模式：不调用领取接口、不写 localStorage、不跳转 */
  preview?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  preview: false,
})
const emit = defineEmits<{
  (e: 'claimed'): void
  (e: 'close'): void
}>()

const message = useMessage()
const visible = ref(true)
const claiming = ref(false)
const claimed = ref(false)

const storageSeenKey = computed(() => `festival_seen_${props.festival.id}`)
const hasSeen = ref(false)

const theme = computed(() => resolveFestivalTheme(props.festival.name))

watch(
  () => props.festival.id,
  () => {
    if (props.preview) {
      visible.value = true
      return
    }
    hasSeen.value = localStorage.getItem(storageSeenKey.value) === '1'
    if (hasSeen.value) {
      visible.value = false
      emit('close')
    }
  },
  { immediate: true },
)

const popup = computed(() => props.festival.popup)
const quota = computed(() => props.festival.quotaBonus)
const animation = computed(() => popup.value.animation)
const animationEnabled = computed(() => animation.value?.enabled ?? false)
const animationType = computed(() => theme.value.animationType)
const animationDuration = computed(() => animation.value?.duration ?? 10)
const particleColors = computed(() => theme.value.particleColors)

const messageText = computed(() => {
  return theme.value.message.replace(/\{amount\}/g, String(Math.floor(quota.value.amount)))
})

const isSpringFestival = computed(() => theme.value.id === 'spring_festival')
const isNationalDay = computed(() => theme.value.id === 'national_day')

const popupWrapperClass = computed(() => ({
  'spring-festival-popup': isSpringFestival.value,
  'national-day-popup': isNationalDay.value,
}))

const showClaimButton = computed(
  () => quota.value.enabled && quota.value.amount > 0 && !claimed.value,
)

async function handleClaim() {
  if (claiming.value) return
  if (props.preview) {
    claimed.value = true
    message.success('模拟领取成功（预览模式未实际发放额度）')
    emit('claimed')
    return
  }
  claiming.value = true
  try {
    const res = await festivalApi.claimFestival(props.festival.id)
    if (res.success) {
      claimed.value = true
      message.success(res.message)
      emit('claimed')
    } else {
      message.info(res.message)
    }
  } catch {
    message.error('领取失败，请稍后重试')
  } finally {
    claiming.value = false
  }
}

function handleClose() {
  if (!props.preview) {
    localStorage.setItem(storageSeenKey.value, '1')
  }
  visible.value = false
  emit('close')
}

function handleBackdropClick() {
  handleClose()
}

function handleSecondaryClick(btn: { action: string; link?: string | null }) {
  if (!props.preview && btn.action === 'navigate' && btn.link) {
    window.location.href = btn.link
  }
  handleClose()
}

const popupStyle = computed(() => {
  const base: Record<string, string> = {
    background: theme.value.gradient,
    borderColor: theme.value.borderColor,
    boxShadow: `0 25px 60px rgba(0, 0, 0, 0.6), 0 0 50px ${theme.value.borderColor}`,
    fontFamily: theme.value.fontFamily || "'Noto Serif SC', 'STKaiti', 'KaiTi', serif",
  }
  if (isSpringFestival.value) {
    base.background = 'rgba(18, 4, 4, 0.58)'
    base.backdropFilter = 'blur(22px) saturate(1.2)'
    base.borderColor = 'rgba(255, 215, 0, 0.35)'
    base.boxShadow = `0 0 0 1px rgba(196, 30, 30, 0.45), 0 30px 70px rgba(0, 0, 0, 0.6), 0 0 60px rgba(255, 215, 0, 0.22), inset 0 0 50px rgba(255, 215, 0, 0.04)`
  }
  return base
})

const titleStyle = computed(() => ({
  color: theme.value.titleColor,
  textShadow: `0 0 30px ${theme.value.borderColor}`,
  fontFamily: theme.value.fontFamily || "inherit",
}))

const textStyle = computed(() => ({
  color: theme.value.textColor,
  fontFamily: theme.value.fontFamily || "inherit",
}))

const taglineStyle = computed(() => ({
  color: theme.value.taglineColor,
}))

const amountStyle = computed(() => ({
  color: theme.value.amountColor,
  textShadow: theme.value.amountGlow,
}))

const buttonStyle = computed(() => ({
  background: theme.value.buttonGradient,
  color: theme.value.buttonTextColor,
  boxShadow: theme.value.buttonShadow,
  fontFamily: theme.value.fontFamily || "inherit",
}))

const dividerStyle = computed(() => ({
  background: `linear-gradient(90deg, transparent, ${theme.value.titleColor}, transparent)`,
}))

const cssVars = computed(() => ({
  '--theme-color': theme.value.titleColor,
  '--theme-border': theme.value.borderColor,
  '--theme-amount': theme.value.amountColor,
  '--theme-glow': theme.value.amountGlow,
  '--theme-btn-shadow': theme.value.buttonShadow,
}))

const backdropClass = computed(() => {
  const transparentAnimations = ['code_rain', 'milky_way']
  return transparentAnimations.includes(animationType.value)
    ? 'bg-black/25'
    : 'bg-black/60 backdrop-blur-sm'
})
</script>

<template>
  <Transition
    enter-active-class="transition-opacity duration-300"
    leave-active-class="transition-opacity duration-200"
    enter-from-class="opacity-0"
    leave-to-class="opacity-0"
  >
    <div
      v-if="visible"
      class="fixed inset-0 z-[3500] flex items-center justify-center p-4"
      @click.self="handleBackdropClick"
    >
      <!-- 背景遮罩 -->
      <div class="absolute inset-0" :class="backdropClass" />

      <!-- 动画层 -->
      <FestivalEffect
        v-if="animationEnabled"
        :type="animationType"
        :duration="animationDuration"
        :colors="particleColors"
      />

      <!-- 弹窗主体 -->
      <div
        class="festival-popup relative z-10 w-full max-w-lg overflow-hidden rounded-3xl p-8 text-center"
        :class="popupWrapperClass"
        :style="[popupStyle, cssVars]"
      >
        <!-- 装饰层 -->
        <FestivalDecoration :decoration="theme.decoration" />

        <!-- 顶部装饰条 -->
        <div class="festival-top-bar" />

        <!-- 关闭按钮 -->
        <button
          type="button"
          class="festival-close-btn"
          aria-label="关闭"
          @click="handleClose"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <!-- 节日标签 -->
        <div class="festival-badge relative z-10 mx-auto mb-3 inline-flex items-center gap-1.5 rounded-full border px-4 py-1 text-xs"
          :style="{ color: theme.taglineColor }"
        >
          <span class="text-base">{{ theme.emoji }}</span>
          <span class="font-medium tracking-wider">{{ theme.name }}</span>
        </div>

        <!-- 诗句 -->
        <div class="festival-poem-card">
          <span class="quote-mark quote-left">“</span>
          <h2 class="festival-poem-title" :style="titleStyle">
            {{ theme.poem }}
          </h2>
          <p class="festival-poem-author" :style="taglineStyle">—— {{ theme.poemAuthor }}</p>
          <span class="quote-mark quote-right">”</span>
        </div>

        <!-- 分隔线 -->
        <div class="festival-divider" />

        <!-- 文案 -->
        <div
          class="relative z-10 mx-auto max-w-md whitespace-pre-line text-sm leading-relaxed"
          :style="textStyle"
        >
          {{ messageText }}
        </div>

        <!-- 额度 -->
        <div v-if="quota.enabled" class="relative z-10 mt-6">
          <div class="festival-amount-card">
            <div class="festival-amount-halo" />
            <div class="text-xs" :style="taglineStyle">节日专属额度</div>
            <div class="festival-amount-number" :style="amountStyle">
              +{{ Math.floor(quota.amount) }}
            </div>
          </div>
          <div class="mt-1 text-xs" :style="taglineStyle">
            {{ quota.description || '节日专属饼干' }}
          </div>
        </div>

        <!-- 按钮区 -->
        <div class="relative z-10 mt-8 flex items-center justify-center gap-3">
          <button
            v-if="showClaimButton"
            type="button"
            class="festival-btn-primary"
            :disabled="claiming"
            :style="buttonStyle"
            @click="handleClaim"
          >
            {{ claiming ? '领取中...' : theme.buttonText }}
          </button>
          <span
            v-else-if="claimed"
            class="rounded-lg px-4 py-2 text-sm font-medium"
            :style="{ background: 'rgba(255,255,255,0.1)', color: theme.taglineColor }"
          >
            已领取 ✓
          </span>

          <button
            v-if="popup.secondaryButton"
            type="button"
            class="festival-btn-secondary"
            @click="handleSecondaryClick(popup.secondaryButton)"
          >
            {{ popup.secondaryButton.text || '了解更多' }}
          </button>
        </div>

        <!-- 春节文人剪影 -->
        <svg
          v-if="isSpringFestival"
          class="scholar-silhouette"
          viewBox="0 0 140 120"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="scholarGlow" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="rgba(255,215,0,0.35)" />
              <stop offset="100%" stop-color="rgba(196,30,30,0.25)" />
            </linearGradient>
          </defs>
          <ellipse cx="70" cy="112" rx="55" ry="7" fill="url(#scholarGlow)" />
          <!-- 身体 -->
          <path
            d="M45 110 L45 72 Q45 56 64 54 Q85 52 92 70 L95 110 Z"
            fill="#0f0505"
            stroke="rgba(255,215,0,0.2)"
            stroke-width="0.5"
          />
          <!-- 头部 -->
          <circle cx="70" cy="42" r="13" fill="#0f0505" />
          <!-- 古代冠帽 -->
          <path
            d="M52 38 Q70 22 88 38 L84 42 H56 Z"
            fill="#0f0505"
            stroke="rgba(255,215,0,0.25)"
            stroke-width="0.5"
          />
          <!-- 持笔手臂 -->
          <path
            d="M85 68 L108 48 L112 52 L90 75 Z"
            fill="#0f0505"
          />
          <!-- 毛笔 -->
          <line x1="108" y1="48" x2="125" y2="30" stroke="#0f0505" stroke-width="3" stroke-linecap="round" />
          <!-- 屠苏酒杯 -->
          <path d="M18 95 H32 V108 H18 Z" fill="#0f0505" />
          <rect x="21" y="86" width="8" height="10" rx="1" fill="#0f0505" />
          <!-- 鞭炮 -->
          <line x1="115" y1="110" x2="115" y2="82" stroke="#0f0505" stroke-width="4" stroke-linecap="round" />
          <circle cx="115" cy="78" r="4" fill="#c41e1e" />
        </svg>

        <!-- 国庆人物剪影 -->
        <svg
          v-if="isNationalDay"
          class="national-silhouette"
          viewBox="0 0 160 220"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="nationalSilGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="rgba(255,215,0,0.35)" />
              <stop offset="100%" stop-color="rgba(255,215,0,0)" />
            </linearGradient>
          </defs>
          <!-- 挥手站立的人物轮廓 -->
          <path
            d="M80 25 C105 25, 115 45, 115 70 C115 88, 110 100, 105 110 L120 125 C140 135, 150 160, 150 190 L150 220 L10 220 L10 190 C10 160, 20 135, 40 125 L55 110 C50 100, 45 88, 45 70 C45 45, 55 25, 80 25 Z"
            fill="url(#nationalSilGrad)"
            opacity="0.5"
          />
          <!-- 头部 -->
          <ellipse cx="80" cy="65" rx="30" ry="34" fill="#FFD700" opacity="0.12" />
          <!-- 挥手的右臂 -->
          <path
            d="M110 115 Q150 80, 145 45 Q142 35, 132 40 Q125 45, 128 55 Q135 85, 105 120 Z"
            fill="#FFD700"
            opacity="0.1"
          />
          <!-- 天安门红墙暗示 -->
          <rect x="20" y="205" width="120" height="8" rx="2" fill="#8B0000" opacity="0.3" />
        </svg>

        <!-- tagline -->
        <p
          class="relative z-10 mt-5 text-xs italic tracking-wider"
          :style="taglineStyle"
        >
          {{ theme.id === 'programmers_day' ? '/* We are made of star-stuff */' : '"We are made of star-stuff" ✨' }}
        </p>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.festival-popup {
  animation: scaleIn 0.4s ease-out both;
}

.festival-btn-primary {
  border-radius: 18px;
  border: none;
  padding: 14px 40px;
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 0.5px;
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  cursor: pointer;
  box-shadow: var(--theme-btn-shadow), 0 0 0 1px rgba(255, 255, 255, 0.1);
}
.festival-btn-primary:hover:not(:disabled) {
  transform: translateY(-2px) scale(1.06);
  filter: brightness(1.12);
  box-shadow: var(--theme-btn-shadow), 0 0 0 1px rgba(255, 255, 255, 0.2), 0 0 32px var(--theme-border);
}
.festival-btn-primary:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.festival-btn-secondary {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(8px);
  color: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.25);
  padding: 12px 28px;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.25s ease;
}
.festival-btn-secondary:hover {
  background: rgba(255, 255, 255, 0.14);
  border-color: var(--theme-border);
  color: var(--theme-color);
  box-shadow: 0 0 20px var(--theme-border);
}

@keyframes scaleIn {
  from {
    opacity: 0;
    transform: scale(0.85) translateY(20px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

/* ===== 通用升级样式 ===== */
.festival-top-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, var(--theme-color), transparent);
  opacity: 0.7;
  border-radius: 24px 24px 0 0;
  z-index: 1;
  pointer-events: none;
}

.festival-close-btn {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 20;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.festival-close-btn svg {
  width: 16px;
  height: 16px;
}
.festival-close-btn:hover {
  transform: scale(1.1) rotate(90deg);
  background: rgba(255, 255, 255, 0.15);
  border-color: var(--theme-border);
  color: var(--theme-color);
  box-shadow: 0 0 16px var(--theme-border);
}

.festival-badge {
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(8px);
  border-color: var(--theme-border);
  box-shadow: 0 0 14px var(--theme-border);
  letter-spacing: 1px;
}

.festival-poem-card {
  position: relative;
  z-index: 10;
  margin: 0 auto 16px;
  max-width: 92%;
  padding: 18px 24px 14px;
  background: rgba(0, 0, 0, 0.22);
  backdrop-filter: blur(12px);
  border: 1px solid var(--theme-border);
  border-radius: 18px;
  box-shadow: inset 0 0 24px var(--theme-border);
}
.festival-poem-title {
  font-family: 'Noto Serif SC', 'STKaiti', 'KaiTi', serif;
  font-size: 1.55rem;
  font-weight: 700;
  line-height: 1.4;
}
.festival-poem-author {
  margin-top: 6px;
  font-size: 0.85rem;
  font-style: italic;
  opacity: 0.85;
}
.quote-mark {
  position: absolute;
  font-family: 'Noto Serif SC', serif;
  font-size: 52px;
  line-height: 1;
  color: var(--theme-color);
  opacity: 0.18;
  pointer-events: none;
}
.quote-left {
  top: 4px;
  left: 8px;
}
.quote-right {
  bottom: -10px;
  right: 10px;
}

.festival-divider {
  position: relative;
  z-index: 10;
  width: 72%;
  height: 2px;
  margin: 0 auto 16px;
  border-radius: 1px;
  background: linear-gradient(90deg, transparent, var(--theme-color), transparent);
  box-shadow: 0 0 10px var(--theme-border);
  animation: dividerExpand 0.6s ease-out both;
}
@keyframes dividerExpand {
  from { transform: scaleX(0); opacity: 0; }
  to { transform: scaleX(1); opacity: 1; }
}

.festival-amount-card {
  position: relative;
  display: inline-block;
  padding: 18px 38px 14px;
  background: rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(12px);
  border: 1px solid var(--theme-border);
  border-radius: 22px;
  overflow: visible;
}
.festival-amount-halo {
  position: absolute;
  inset: -4px;
  border-radius: 26px;
  border: 1px solid var(--theme-border);
  animation: haloPulse 2.2s ease-in-out infinite;
  pointer-events: none;
}
@keyframes haloPulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.45;
    box-shadow: 0 0 0 0 var(--theme-border);
  }
  50% {
    transform: scale(1.05);
    opacity: 0.75;
    box-shadow: 0 0 24px 4px var(--theme-border);
  }
}
.festival-amount-number {
  font-size: 3.5rem;
  font-weight: 900;
  line-height: 1;
  animation: amountGlow 2.2s ease-in-out infinite;
}
@keyframes amountGlow {
  0%, 100% { filter: brightness(1); }
  50% { filter: brightness(1.2); }
}

/* ===== 春节额外增强 ===== */
.spring-festival-popup {
  border: 1px solid rgba(255, 215, 0, 0.35) !important;
  box-shadow:
    0 0 0 1px rgba(196, 30, 30, 0.45),
    0 30px 70px rgba(0, 0, 0, 0.6),
    0 0 60px rgba(255, 215, 0, 0.22),
    inset 0 0 50px rgba(255, 215, 0, 0.04) !important;
  animation: scaleIn 0.4s ease-out both, borderBreathe 3s ease-in-out infinite 0.4s;
}
@keyframes borderBreathe {
  0%, 100% {
    box-shadow:
      0 0 0 1px rgba(196, 30, 30, 0.45),
      0 30px 70px rgba(0, 0, 0, 0.6),
      0 0 60px rgba(255, 215, 0, 0.18),
      inset 0 0 50px rgba(255, 215, 0, 0.03);
  }
  50% {
    box-shadow:
      0 0 0 2px rgba(196, 30, 30, 0.55),
      0 30px 70px rgba(0, 0, 0, 0.6),
      0 0 80px rgba(255, 215, 0, 0.32),
      inset 0 0 60px rgba(255, 215, 0, 0.07);
  }
}

.spring-festival-popup .festival-top-bar {
  height: 4px;
  background: linear-gradient(90deg, #cc0000, #ff4444, #ffd700, #ff4444, #cc0000);
  opacity: 0.8;
}
.spring-festival-popup .festival-poem-card {
  border-color: rgba(255, 215, 0, 0.4);
  box-shadow: inset 0 0 28px rgba(255, 215, 0, 0.07);
}
.spring-festival-popup .quote-mark {
  color: rgba(255, 215, 0, 0.28);
}
.spring-festival-popup .festival-divider {
  background: linear-gradient(90deg, transparent, #c41e1e, #ffd700, #c41e1e, transparent);
  box-shadow: 0 0 12px rgba(255, 215, 0, 0.45);
}
.spring-festival-popup .festival-amount-card {
  border-color: rgba(255, 215, 0, 0.45);
}
.spring-festival-popup .festival-amount-halo {
  border-color: rgba(255, 215, 0, 0.35);
  animation-name: haloPulseGold;
}
@keyframes haloPulseGold {
  0%, 100% {
    transform: scale(1);
    opacity: 0.55;
    box-shadow: 0 0 0 0 rgba(255, 215, 0, 0.15);
  }
  50% {
    transform: scale(1.05);
    opacity: 0.85;
    box-shadow: 0 0 24px 4px rgba(255, 215, 0, 0.2);
  }
}
.spring-festival-popup .festival-amount-number {
  animation-name: amountGlowGold;
}
@keyframes amountGlowGold {
  0%, 100% { text-shadow: 0 0 24px rgba(255, 215, 0, 0.4); }
  50% { text-shadow: 0 0 44px rgba(255, 215, 0, 0.7); }
}
.spring-festival-popup .festival-btn-primary:hover {
  box-shadow:
    0 12px 32px rgba(196, 30, 30, 0.55),
    0 0 0 1px rgba(255, 215, 0, 0.4),
    0 0 36px rgba(255, 215, 0, 0.28);
}
.spring-festival-popup .festival-btn-secondary:hover {
  border-color: rgba(255, 215, 0, 0.45);
  color: #ffd700;
  box-shadow: 0 0 20px rgba(255, 215, 0, 0.15);
}

.scholar-silhouette {
  position: absolute;
  right: -10px;
  bottom: -10px;
  width: 130px;
  height: 112px;
  opacity: 0.85;
  pointer-events: none;
  z-index: 0;
}

.national-day-popup .festival-top-bar {
  height: 4px;
  background: linear-gradient(90deg, #cc0000, #ff4444, #ffd700, #ff4444, #cc0000);
  opacity: 0.85;
}
.national-silhouette {
  position: absolute;
  right: -10px;
  bottom: -10px;
  width: 150px;
  height: 206px;
  opacity: 0.75;
  pointer-events: none;
  z-index: 0;
}
</style>
