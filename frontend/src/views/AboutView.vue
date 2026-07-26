<script setup lang="ts">
import { ref, onBeforeUnmount, onMounted } from 'vue'
import { NIcon, NButton, useMessage } from 'naive-ui'
import { RocketOutline, FlaskOutline, ShieldCheckmarkOutline, TelescopeOutline, LogoGithub, SparklesOutline, ChatbubbleEllipsesOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'
import { useSiteConfigStore } from '@/stores/site-config'
// 彩蛋图片：猫猫踩地球插画
import catEarthLogo from '@/assets/ChatGPT_logo.png'

const router = useRouter()
const siteConfig = useSiteConfigStore()
const message = useMessage()

onMounted(() => {
  siteConfig.fetchSiteConfig()
})

// 彩蛋：点击蓝色星球触发隐藏弹窗
const showEasterEgg = ref(false)

// 打开彩蛋弹窗：顺带拉取站点文案（已加载则复用，确保文案可被 YAML 配置覆盖）
function openEasterEgg() {
  siteConfig.fetchSiteConfig()
  showEasterEgg.value = true
}

// ===== 召唤星际猫咪 =====
// 猫爪动画由全局 CatPawsOverlay 负责（App.vue 挂载），这里只派发事件 + 弹 Toast。
// playing 用于防连点：动画播放期间不重复派发。
const playing = ref(false)
let pawTimer: ReturnType<typeof setTimeout> | null = null

function summonCat() {
  if (playing.value) return
  // 确保 toast / 按钮文案已就绪（首次进入关于页即点按钮时可能尚未拉取）
  siteConfig.fetchSiteConfig()
  playing.value = true
  message.success(siteConfig.easterEggToast, { duration: 3500 })
  window.dispatchEvent(new CustomEvent('omicHub:triggerCatPaws'))
  if (pawTimer) clearTimeout(pawTimer)
  pawTimer = setTimeout(() => {
    playing.value = false
  }, 7000)
}

onBeforeUnmount(() => {
  if (pawTimer) clearTimeout(pawTimer)
})

const stars = Array.from({ length: 160 }, (_, i) => {
  const size = Math.random() * 1 + 0.6
  const baseOpacity = Math.random() * 0.5 + 0.35

  const isBright = baseOpacity > 0.7
  const hasCross = isBright && Math.random() > 0.8

  const crossScale = hasCross ? (size * baseOpacity * 0.8).toFixed(2) : 0

  return {
    id: i,
    top: Math.random() * 100,
    left: Math.random() * 100,
    size: size,
    opacity: baseOpacity,
    delay: Math.random() * 8,
    duration: Math.random() * 5 + 5,
    hasCross: hasCross,
    crossScale: crossScale
  }
})

const shootingStars = Array.from({ length: 3 }, (_, i) => ({
  id: i,
  // 每颗仅在长周期中的短暂时刻划过，保持背景安静。
  delay: i * 11 + Math.random() * 3,
  duration: 34 + Math.random() * 8,
  top: Math.random() * 50,
  left: Math.random() * 60,
  scale: 0.8 + Math.random() * 0.7,
}))

const nebulaLayers = Array.from({ length: 3 }, (_, i) => ({
  id: i,
  top: 10 + Math.random() * 60,
  left: -10 + Math.random() * 40,
  width: 60 + Math.random() * 40,
  height: 15 + Math.random() * 10,
  opacity: 0.04 + Math.random() * 0.04,
  delay: Math.random() * 5,
  duration: 20 + Math.random() * 20,
}))
</script>

<template>
  <div class="about-page" role="main" aria-label="关于 OmicHub">
    <!-- 深空背景 -->
    <div class="space-bg" />

    <!-- 星河/星云带 -->
    <div class="milky-way">
      <div
        v-for="n in nebulaLayers"
        :key="n.id"
        class="nebula-band"
        :style="{
          top: n.top + '%',
          left: n.left + '%',
          width: n.width + '%',
          height: n.height + '%',
          '--base-opacity': n.opacity,
          animationDelay: n.delay + 's',
          animationDuration: n.duration + 's',
        }"
      />
    </div>

    <!-- 星空 -->
    <div class="starfield">
      <div
        v-for="s in stars"
        :key="s.id"
        class="star"
        :class="{ 'has-cross': s.hasCross }"
        :style="{
          top: s.top + '%',
          left: s.left + '%',
          width: s.size + 'px',
          height: s.size + 'px',
          '--star-opacity': s.opacity,
          animationDelay: s.delay + 's',
          animationDuration: s.duration + 's',
          '--cross-scale': s.crossScale
        }"
      ></div>
    </div>

    <!-- 流星 -->
    <div class="shooting-stars">
      <div
        v-for="ss in shootingStars"
        :key="ss.id"
        class="shooting-star"
        :style="{
          top: ss.top + '%',
          left: ss.left + '%',
          animationDelay: ss.delay + 's',
          animationDuration: ss.duration + 's',
          '--star-scale': ss.scale
        }"
      />
    </div>

    <!-- 浮动光球 -->
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <!-- 内容 -->
    <div class="about-content">
      <!-- 旋转行星（点击触发隐藏彩蛋） -->
      <div class="planet-wrap" style="cursor: pointer" title="点我看看？" @click="openEasterEgg">
        <div class="planet" />
        <div class="planet-ring" />
      </div>

      <h1 class="about-title">OmicHub</h1>
      <p class="about-subtitle">多组学数据分析平台<span class="subtitle-llm">· LLM 深度赋能</span></p>

      <div class="about-quote-box">
        <p class="about-quote-title">We are made of star-stuff</p>
        <p class="about-quote">
          我们只是借用了宇宙中的这些碳、氢、氧原子几十年，用它们去短暂地体验了一次这个世界。
          组成我们大脑和身体的每一个原子，都来自几十亿年前远古恒星内部的核聚变爆炸。
          当生命结束时，我们并没有化为虚无，我们只是回到了那个浩瀚的宇宙中，换了一种方式继续存在。
        </p>
      </div>

      <!-- 特性 -->
      <div class="features">
        <div class="feature-item feature-item--primary animate-fade-in-up delay-100">
          <NIcon :size="24" class="feature-icon feature-icon--accent"><SparklesOutline /></NIcon>
          <div class="feature-text">
            <div class="feature-title">AI 智能分析</div>
            <div class="feature-desc">LLM 解读结果 · 自动生成报告</div>
          </div>
        </div>
        <div class="feature-item animate-fade-in-up delay-200">
          <NIcon :size="24" class="feature-icon feature-icon--accent"><ChatbubbleEllipsesOutline /></NIcon>
          <div class="feature-text">
            <div class="feature-title">智能问答</div>
            <div class="feature-desc">自然语言查询 · 对话式交互</div>
          </div>
        </div>
        <div class="feature-item animate-fade-in-up delay-200">
          <NIcon :size="24" class="feature-icon"><FlaskOutline /></NIcon>
          <div class="feature-text">
            <div class="feature-title">多组学分析</div>
            <div class="feature-desc">RNA-seq / ATAC-seq / 单细胞</div>
          </div>
        </div>
        <div class="feature-item animate-fade-in-up delay-300">
          <NIcon :size="24" class="feature-icon"><RocketOutline /></NIcon>
          <div class="feature-text">
            <div class="feature-title">Snakemake 流程</div>
            <div class="feature-desc">可复现、可扩展、自动化</div>
          </div>
        </div>
        <div class="feature-item animate-fade-in-up delay-400">
          <NIcon :size="24" class="feature-icon"><ShieldCheckmarkOutline /></NIcon>
          <div class="feature-text">
            <div class="feature-title">私有化部署</div>
            <div class="feature-desc">数据不出内网，安全可控</div>
          </div>
        </div>
        <div class="feature-item animate-fade-in-up delay-500">
          <NIcon :size="24" class="feature-icon"><TelescopeOutline /></NIcon>
          <div class="feature-text">
            <div class="feature-title">任务追踪</div>
            <div class="feature-desc">实时监控 / DAG 可视化</div>
          </div>
        </div>
      </div>

      <div class="about-actions">
        <NButton class="about-btn-primary" size="large" @click="router.push('/flows')">
          <template #icon>
            <NIcon><RocketOutline /></NIcon>
          </template>
          开始分析
        </NButton>
        <NButton class="about-btn-ghost" size="large" @click="router.push('/dashboard')">
          进入控制台
        </NButton>
        <NButton
          v-if="siteConfig.platformGithub"
          class="about-btn-ghost"
          size="large"
          tag="a"
          :href="siteConfig.platformGithub"
          target="_blank"
        >
          <template #icon>
            <NIcon><LogoGithub /></NIcon>
          </template>
          GitHub
        </NButton>
      </div>

      <!-- 底部 -->
      <div class="about-footer">
        <span class="about-brand">OmicHub</span>
        <span class="about-divider">·</span>
        <span>华中农业大学园艺林学学院 · 多组学分析平台</span>
        <div v-if="siteConfig.platformAuthor" class="about-credit">
          Designed by {{ siteConfig.platformAuthor }}
          <template v-if="siteConfig.platformEmail">
            <span class="about-divider">|</span>
            Contact: <a :href="`mailto:${siteConfig.platformEmail}`" class="about-credit-link">{{ siteConfig.platformEmail }}</a>
          </template>
        </div>
      </div>
    </div>

    <!-- 隐藏彩蛋弹窗：点击蓝色星球触发 -->
    <div
      v-if="showEasterEgg"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      @click="showEasterEgg = false"
    >
      <!-- 弹窗主体：深色毛玻璃，阻止点击冒泡到遮罩层 -->
      <div
        class="relative w-fit max-w-[90vw] rounded-2xl border border-white/10 bg-[#0B1121]/70 px-10 py-8 shadow-2xl backdrop-blur-md"
        @click.stop
      >
        <!-- 毛玻璃质感关闭按钮：悬浮光晕 + 旋转缩放动画 -->
        <button
          class="eg-close-btn group absolute right-4 top-4 flex h-9 w-9 cursor-pointer items-center justify-center rounded-full border border-white/15 bg-white/5 text-slate-300 backdrop-blur-sm transition-all duration-300 hover:border-cyan-300/60 hover:bg-cyan-300/10 hover:text-cyan-200 hover:shadow-[0_0_14px_rgba(103,232,249,0.55)]"
          aria-label="关闭"
          @click="showEasterEgg = false"
        >
          <span
            class="text-lg font-light leading-none transition-transform duration-300 group-hover:scale-110 group-hover:rotate-90"
          >
            ✕
          </span>
        </button>

        <img
          :src="catEarthLogo"
          alt="星际守护者"
          class="mx-auto block h-48 w-auto object-contain"
        />
        <p class="mt-6 max-w-[36rem] text-center text-lg font-bold leading-relaxed break-words text-white">
          {{ siteConfig.easterEggMessage }}
        </p>
      </div>
    </div>

    <!-- 悬浮召唤按钮：召唤星际猫咪 -->
    <button
      class="summon-cat-btn"
      :aria-label="siteConfig.easterEggButtonText"
      @click="summonCat"
    >
      <span class="summon-cat-btn__icon">🐾</span>
      <span class="summon-cat-btn__text">{{ siteConfig.easterEggButtonText }}</span>
    </button>

    <!-- 猫爪足迹覆盖层由全局 CatPawsOverlay（App.vue）渲染，本页不再自建 -->
  </div>
</template>

<style scoped>
/* 关闭按钮：空闲呼吸光晕，悬停时由 Tailwind 接管旋转/缩放/高亮 */
.eg-close-btn {
  animation: eg-close-pulse 2.4s ease-in-out infinite;
}
@keyframes eg-close-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(103, 232, 249, 0);
  }
  50% {
    box-shadow: 0 0 10px 1px rgba(103, 232, 249, 0.28);
  }
}
@keyframes shooting {
  0% {
    transform: translateX(0) translateY(0) rotate(35deg) scaleX(0) scale(var(--star-scale, 1));
    opacity: 0;
  }
  3% {
    opacity: 0.72;
    transform: translateX(36px) translateY(25px) rotate(35deg) scaleX(0.82) scale(var(--star-scale, 1));
  }
  9% {
    opacity: 0.62;
    transform: translateX(330px) translateY(231px) rotate(35deg) scaleX(1) scale(var(--star-scale, 1));
  }
  13% {
    transform: translateX(460px) translateY(322px) rotate(35deg) scaleX(0.42) scale(var(--star-scale, 1));
    opacity: 0;
  }
  100% {
    transform: translateX(600px) translateY(420px) rotate(35deg) scaleX(0.6) scale(var(--star-scale, 1));
    opacity: 0;
  }
}

@keyframes twinkle {
  0%, 100% {
    opacity: calc(var(--star-opacity, 0.55) * 0.68);
    transform: translate(-50%, -50%) scale(0.94);
  }
  50% {
    opacity: var(--star-opacity, 0.55);
    transform: translate(-50%, -50%) scale(1.04);
  }
}

@keyframes nebulaDrift {
  0%, 100% { transform: translateX(0) scale(1); opacity: var(--base-opacity, 0.05); }
  50% { transform: translateX(3%) scale(1.02); opacity: calc(var(--base-opacity, 0.05) * 1.16); }
}

@keyframes planetSpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes ringSpin {
  from { transform: rotateX(75deg) rotateZ(0deg); }
  to { transform: rotateX(75deg) rotateZ(360deg); }
}

.about-page {
  position: relative;
  min-height: calc(100vh - 56px);
  margin: -24px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #080d24;
}

/* 深空蓝紫：以低饱和星云保留层次，不干扰正文阅读。 */
.space-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse at 20% 12%, rgba(76, 111, 255, 0.20) 0%, transparent 42%),
    radial-gradient(ellipse at 82% 82%, rgba(122, 92, 214, 0.16) 0%, transparent 46%),
    radial-gradient(ellipse at 52% 46%, rgba(24, 42, 99, 0.34) 0%, transparent 58%),
    linear-gradient(145deg, #071127 0%, #101840 50%, #17123b 100%);
}

/* 星河/星云带 */
.milky-way {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  transform: rotate(-15deg) scale(1.2);
}

.nebula-band {
  position: absolute;
  border-radius: 9999px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(129, 151, 255, 0.14) 25%,
    rgba(170, 133, 255, 0.20) 50%,
    rgba(129, 151, 255, 0.12) 75%,
    transparent 100%
  );
  filter: blur(36px);
  animation: nebulaDrift ease-in-out infinite;
  --base-opacity: 0.05;
}

/* 星空 */
.starfield {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.star {
  position: absolute;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 0 4px 1px rgba(190, 209, 255, 0.34);
  animation: twinkle linear infinite alternate;
  transform: translate(-50%, -50%);
}

.star.has-cross::before,
.star.has-cross::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  pointer-events: none;
  transform: translate(-50%, -50%) scale(var(--cross-scale));
}

.star.has-cross::before {
  width: 40px;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(107, 141, 214, 0.8) 40%,
    rgba(255, 255, 255, 1) 50%,
    rgba(107, 141, 214, 0.8) 60%,
    transparent 100%
  );
}

.star.has-cross::after {
  width: 1px;
  height: 40px;
  background: linear-gradient(
    180deg,
    transparent 0%,
    rgba(107, 141, 214, 0.8) 40%,
    rgba(255, 255, 255, 1) 50%,
    rgba(107, 141, 214, 0.8) 60%,
    transparent 100%
  );
}

/* 流星 */
.shooting-stars {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  overflow: hidden;
}
.shooting-star {
  position: absolute;
  width: 112px;
  height: 1px;
  border-radius: 50%;
  opacity: 0;
  animation: shooting linear infinite;
  transform-origin: left center;
}
.shooting-star::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to left, rgba(255, 255, 255, 0.74), rgba(147, 171, 255, 0.42), transparent);
  border-radius: 50%;
  filter: drop-shadow(0 0 4px rgba(194, 211, 255, 0.52));
}
.shooting-star::after {
  content: '';
  position: absolute;
  right: -3px;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 8px 1px rgba(255, 255, 255, 0.6), 0 0 14px 3px rgba(128, 153, 255, 0.30);
}

/* 浮动光球 */
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.06;
  pointer-events: none;
  z-index: 1;
}
.orb-1 {
  width: 280px;
  height: 280px;
  background: #5b7cff;
  top: 8%;
  left: 3%;
}
.orb-2 {
  width: 220px;
  height: 220px;
  background: #8b6be8;
  bottom: 10%;
  right: 5%;
}

/* 内容容器 */
.about-content {
  position: relative;
  z-index: 2;
  max-width: 720px;
  width: 100%;
  padding: 40px 32px;
  text-align: center;
}

/* 旋转行星 */
.planet-wrap {
  position: relative;
  width: 80px;
  height: 80px;
  margin: 0 auto 24px;
}
.planet {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #8097ed, #3149b9 52%, #171a5c 100%);
  box-shadow: 0 0 18px rgba(107, 141, 214, 0.22), inset -8px -8px 16px rgba(0, 0, 0, 0.42);
  animation: planetSpin 36s linear infinite;
}
.planet-ring {
  position: absolute;
  inset: -8px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-radius: 50%;
  border-top-color: transparent;
  border-bottom-color: transparent;
  animation: ringSpin 28s linear infinite;
}

/* 标题 */
.about-title {
  font-size: 42px;
  font-weight: 700;
  margin: 0 0 8px;
  letter-spacing: 1px;
  background: linear-gradient(90deg, #d9e2ff, #a8bbff, #d9e2ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.about-subtitle {
  font-size: 18px;
  color: #d6def8;
  margin: 0 0 24px;
  font-weight: 500;
}
.subtitle-llm {
  margin-left: 8px;
  font-weight: 600;
  color: #aebfff;
  text-shadow: 0 0 10px rgba(117, 143, 255, 0.22);
}

/* 苹果式毛玻璃面板：引言盒子 */
.about-quote-box {
  background: rgba(18, 29, 68, 0.72);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid rgba(179, 197, 255, 0.22);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.65),
    0 8px 32px 0 rgba(76, 111, 255, 0.16);
  border-radius: 16px;
  padding: 24px 28px;
  margin-bottom: 28px;
  transition: border-color 0.3s ease, transform 0.3s ease;
}
.about-quote-box:hover {
  border-color: rgba(255, 255, 255, 0.9);
  transform: translateY(-2px);
}

/* 题记：青蓝渐变斜体，与功能卡片标题同款 */
.about-quote-title {
  font-size: 16px;
  font-weight: 600;
  font-style: italic;
  letter-spacing: 1px;
  margin: 0 0 14px;
  text-align: center;
  text-indent: 0;
  background: linear-gradient(90deg, #1E6FD9, #0e9bb5, #1E6FD9);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: shimmer 9s linear infinite;
}

.about-quote {
  font-size: 14px;
  line-height: 1.9;
  color: #d8e1fb;
  text-align: justify;
  margin: 0;
  text-indent: 2em;
}

/* 特性：玻璃面板 */
.features {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 28px;
}
.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border-radius: 12px;
  background: rgba(18, 29, 68, 0.66);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border: 1px solid rgba(179, 197, 255, 0.20);
  box-shadow:
    inset 0 1px 0 rgba(220, 228, 255, 0.12),
    0 12px 32px 0 rgba(3, 7, 25, 0.26);
  transition: border-color 0.3s ease, transform 0.3s ease, box-shadow 0.3s ease;
  text-align: left;
}
.feature-item:hover {
  border-color: rgba(184, 202, 255, 0.46);
  transform: translateY(-2px);
}
/* 主推卡片：AI 智能分析，轻微青蓝描边高亮 */
.feature-item--primary {
  border-color: rgba(123, 150, 255, 0.56);
  box-shadow:
    inset 0 1px 0 rgba(220, 228, 255, 0.14),
    0 0 0 1px rgba(123, 150, 255, 0.15),
    0 12px 28px rgba(4, 10, 33, 0.30);
}
.feature-item--primary:hover {
  border-color: rgba(146, 169, 255, 0.72);
}
.feature-icon {
  color: #aebfff;
  flex-shrink: 0;
}
.feature-icon--accent {
  color: #c3d0ff;
}
/* 功能标题：青蓝渐变（非斜体，与卡片标题层级一致） */
.feature-title {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.5px;
  background: linear-gradient(90deg, #dbe4ff, #aac0ff, #dbe4ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.feature-desc {
  font-size: 12px;
  color: #afbddf;
  margin-top: 2px;
}

/* 操作按钮 */
.about-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-bottom: 32px;
}

/* 渐变背景上的按钮：遵循设计规范 §5.7（白底主按钮 + 毛玻璃次按钮） */
.n-button.about-btn-primary {
  background-color: rgba(255, 255, 255, 0.95);
  color: #4C6FFF;
  font-weight: 700;
  letter-spacing: 0.3px;
  border: none;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.3), 0 4px 20px rgba(0, 0, 0, 0.2);
  transition: all 0.2s ease;
}
.n-button.about-btn-primary:hover,
.n-button.about-btn-primary:focus {
  background-color: #ffffff;
  color: #4C6FFF;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.45), 0 6px 24px rgba(0, 0, 0, 0.22);
  transform: translateY(-1px);
}
.n-button.about-btn-ghost {
  background-color: rgba(255, 255, 255, 0.15);
  color: #ffffff;
  font-weight: 700;
  letter-spacing: 0.3px;
  border: 1.5px solid rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
  transition: all 0.2s ease;
}
.n-button.about-btn-ghost:hover,
.n-button.about-btn-ghost:focus {
  background-color: rgba(255, 255, 255, 0.25);
  border-color: rgba(255, 255, 255, 0.8);
  color: #ffffff;
}
/* Naive 的描边由内部两个元素绘制，隐藏以免与外发光叠成两圈（规范 §5.7 踩坑记录） */
.about-btn-primary :deep(.n-button__border),
.about-btn-primary :deep(.n-button__state-border),
.about-btn-ghost :deep(.n-button__border),
.about-btn-ghost :deep(.n-button__state-border) {
  display: none;
}
.about-btn-primary :deep(.n-button__icon),
.about-btn-ghost :deep(.n-button__icon) {
  margin-right: 8px;
}

/* 减少透明度：毛玻璃回退为实色（规范 §4.2） */
@media (prefers-reduced-transparency: reduce) {
  .about-quote-box,
  .feature-item {
    background: #15204a;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
  .n-button.about-btn-ghost {
    background-color: #26366f;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
}

/* 底部 */
.about-footer {
  font-size: 13px;
  color: #dcebfb;
  border-top: 1px solid rgba(255, 255, 255, 0.25);
  padding-top: 20px;
}
.about-brand {
  font-weight: 700;
  color: #ffffff;
}
.about-divider {
  margin: 0 8px;
}
.about-credit {
  margin-top: 8px;
  font-size: 12px;
  color: #c4dcf5;
}
.about-credit-link {
  color: #a5f3fc;
  text-decoration: none;
  transition: color 0.2s ease;
}
.about-credit-link:hover {
  color: #ffffff;
}

@media (max-width: 640px) {
  .about-content { padding: 24px 20px; }
  .about-title { font-size: 32px; }
  .about-subtitle { font-size: 16px; }
  .about-quote { font-size: 13px; }
  .about-quote-title { font-size: 14px; margin-bottom: 10px; }
  .about-quote-box { padding: 16px 20px; }
  .features { grid-template-columns: 1fr; }
  .about-actions {
    flex-direction: column;
    align-items: center;
  }
}

/* ===== 悬浮召唤按钮 ===== */
.summon-cat-btn {
  position: fixed;
  right: 36px;
  bottom: 36px;
  z-index: 90;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 22px;
  border: none;
  border-radius: 9999px;
  cursor: pointer;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  box-shadow: 0 4px 20px rgba(102, 126, 234, 0.45);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
  animation: summon-pulse 2.8s ease-in-out infinite;
}
.summon-cat-btn:hover {
  transform: translateY(-2px) scale(1.04);
  box-shadow: 0 8px 28px rgba(118, 75, 162, 0.6);
}
.summon-cat-btn:active {
  transform: translateY(0) scale(0.98);
}
.summon-cat-btn__icon {
  font-size: 18px;
  display: inline-block;
  animation: paw-wiggle 1.6s ease-in-out infinite;
}
@keyframes summon-pulse {
  0%, 100% { box-shadow: 0 4px 20px rgba(102, 126, 234, 0.35); }
  50% { box-shadow: 0 4px 28px rgba(118, 75, 162, 0.65); }
}
@keyframes paw-wiggle {
  0%, 100% { transform: rotate(0deg); }
  25% { transform: rotate(-12deg); }
  75% { transform: rotate(12deg); }
}

@media (max-width: 640px) {
  .summon-cat-btn {
    right: 16px;
    bottom: 16px;
    padding: 10px 16px;
    font-size: 13px;
  }
}
</style>
