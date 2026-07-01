<script setup lang="ts">
import { ref } from 'vue'
import { NIcon, NButton } from 'naive-ui'
import { RocketOutline, FlaskOutline, ShieldCheckmarkOutline, TelescopeOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'
// 彩蛋图片：猫猫踩地球插画
import catEarthLogo from '@/assets/ChatGPT_logo.png'

const router = useRouter()

// 彩蛋：点击蓝色星球触发隐藏弹窗
const showEasterEgg = ref(false)

const stars = Array.from({ length: 160 }, (_, i) => {
  const size = Math.random() * 1.5 + 1
  const baseOpacity = Math.random() * 0.6 + 0.4

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
  // 长周期循环：每颗约 18~24s 才划过一次（可见段仅占约 12%，靠 keyframes 压缩）
  delay: i * 6 + Math.random() * 4,
  duration: 18 + Math.random() * 6,
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
  opacity: 0.08 + Math.random() * 0.08,
  delay: Math.random() * 5,
  duration: 20 + Math.random() * 20,
}))
</script>

<template>
  <div class="about-page">
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
          opacity: n.opacity,
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
          opacity: s.opacity,
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
      <div class="planet-wrap" style="cursor: pointer" title="点我看看？" @click="showEasterEgg = true">
        <div class="planet" />
        <div class="planet-ring" />
      </div>

      <h1 class="about-title">OmicHub</h1>
      <p class="about-subtitle">多组学数据分析平台</p>

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
        <NButton type="primary" size="large" @click="router.push('/flows')">
          <template #icon>
            <NIcon><RocketOutline /></NIcon>
          </template>
          开始分析
        </NButton>
        <NButton size="large" ghost style="color: #fff; border-color: rgba(255,255,255,0.3);" @click="router.push('/dashboard')">
          进入控制台
        </NButton>
      </div>

      <!-- 底部 -->
      <div class="about-footer">
        <span class="about-brand">OmicHub</span>
        <span class="about-divider">·</span>
        <span>华中农业大学园艺林学学院 · 多组学分析平台</span>
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
        <p class="mt-6 whitespace-nowrap text-center text-lg font-bold text-white">
          🎉 恭喜你发现了 OmicHub 的隐藏星际守护者！
        </p>
      </div>
    </div>
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
  20% {
    opacity: 1;
    transform: translateX(60px) translateY(42px) rotate(35deg) scaleX(1) scale(var(--star-scale, 1));
  }
  32% {
    opacity: 1;
    transform: translateX(420px) translateY(294px) rotate(35deg) scaleX(1) scale(var(--star-scale, 1));
  }
  42% {
    transform: translateX(600px) translateY(420px) rotate(35deg) scaleX(0.6) scale(var(--star-scale, 1));
    opacity: 0;
  }
  100% {
    transform: translateX(600px) translateY(420px) rotate(35deg) scaleX(0.6) scale(var(--star-scale, 1));
    opacity: 0;
  }
}

@keyframes twinkle {
  0% {
    opacity: 0.2;
    transform: translate(-50%, -50%) scale(0.8);
  }
  100% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1.2);
  }
}

@keyframes nebulaDrift {
  0%, 100% { transform: translateX(0) scale(1); opacity: var(--base-opacity, 0.1); }
  50% { transform: translateX(8%) scale(1.05); opacity: calc(var(--base-opacity, 0.1) * 1.5); }
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
  background: #050810;
}

/* 深空渐变背景 */
.space-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at 20% 30%, rgba(22, 93, 255, 0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 70%, rgba(107, 141, 214, 0.12) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 50%, rgba(20, 30, 60, 0.4) 0%, #050810 70%);
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
    rgba(107, 141, 214, 0.5) 25%,
    rgba(22, 93, 255, 0.6) 50%,
    rgba(142, 84, 233, 0.4) 75%,
    transparent 100%
  );
  filter: blur(24px);
  animation: nebulaDrift ease-in-out infinite;
  --base-opacity: 0.1;
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
  box-shadow: 0 0 4px 1px rgba(255, 255, 255, 0.6);
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
  width: 140px;
  height: 2px;
  border-radius: 50%;
  opacity: 0;
  animation: shooting linear infinite;
  transform-origin: left center;
}
.shooting-star::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to left, rgba(255, 255, 255, 0.9), rgba(107, 141, 214, 0.6), transparent);
  border-radius: 50%;
  filter: drop-shadow(0 0 6px rgba(255, 255, 255, 0.9));
}
.shooting-star::after {
  content: '';
  position: absolute;
  right: -3px;
  top: 50%;
  transform: translateY(-50%);
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 12px 2px rgba(255, 255, 255, 0.8), 0 0 20px 4px rgba(107, 141, 214, 0.5);
}

/* 浮动光球 */
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.2;
  pointer-events: none;
  z-index: 1;
}
.orb-1 {
  width: 340px;
  height: 340px;
  background: #165DFF;
  top: 8%;
  left: 3%;
  animation: drift 14s ease-in-out infinite;
}
.orb-2 {
  width: 280px;
  height: 280px;
  background: #8E54E9;
  bottom: 10%;
  right: 5%;
  animation: drift 18s ease-in-out infinite reverse;
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
  background: radial-gradient(circle at 35% 35%, #6B8DD6, #165DFF 50%, #1147C2 100%);
  box-shadow: 0 0 30px rgba(107, 141, 214, 0.5), inset -8px -8px 16px rgba(0, 0, 0, 0.3);
  animation: planetSpin 8s linear infinite;
}
.planet-ring {
  position: absolute;
  inset: -8px;
  border: 2px solid rgba(107, 141, 214, 0.3);
  border-radius: 50%;
  border-top-color: transparent;
  border-bottom-color: transparent;
  animation: ringSpin 6s linear infinite;
}

/* 标题 */
.about-title {
  font-size: 42px;
  font-weight: 700;
  margin: 0 0 8px;
  letter-spacing: 1px;
  background: linear-gradient(90deg, #6B8DD6, #67e8f9, #6B8DD6);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: shimmer 4s linear infinite;
}
.about-subtitle {
  font-size: 18px;
  color: #94a3b8;
  margin: 0 0 24px;
  font-weight: 500;
}

/* 玻璃面板（Glassmorphism）：引言盒子 */
.about-quote-box {
  background: rgba(20, 25, 45, 0.3);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
  border-radius: 12px;
  padding: 24px 28px;
  margin-bottom: 28px;
  transition: border-color 0.3s ease, transform 0.3s ease;
}
.about-quote-box:hover {
  border-color: rgba(255, 255, 255, 0.2);
  transform: translateY(-2px);
}

/* 题记：与标题同色系渐变，柔和高亮，不抢眼 */
.about-quote-title {
  font-size: 16px;
  font-weight: 600;
  font-style: italic;
  letter-spacing: 1px;
  margin: 0 0 14px;
  text-align: center;
  text-indent: 0;
  background: linear-gradient(90deg, #6B8DD6, #67e8f9, #6B8DD6);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: shimmer 4s linear infinite;
}

.about-quote {
  font-size: 14px;
  line-height: 1.9;
  color: #e2e8f0;
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
  border-radius: 10px;
  background: rgba(20, 25, 45, 0.3);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
  transition: border-color 0.3s ease, transform 0.3s ease;
  text-align: left;
}
.feature-item:hover {
  border-color: rgba(255, 255, 255, 0.2);
  transform: translateY(-2px);
}
.feature-icon {
  color: #6B8DD6;
  flex-shrink: 0;
}
.feature-title {
  font-size: 14px;
  font-weight: 600;
  color: #f1f5f9;
}
.feature-desc {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 2px;
}

/* 操作按钮 */
.about-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-bottom: 32px;
}

/* 底部 */
.about-footer {
  font-size: 13px;
  color: #94a3b8;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
  padding-top: 20px;
}
.about-brand {
  font-weight: 700;
  color: #6B8DD6;
}
.about-divider {
  margin: 0 8px;
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
</style>
