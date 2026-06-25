<script setup lang="ts">
import { NIcon, NButton } from 'naive-ui'
import { RocketOutline, FlaskOutline, ShieldCheckmarkOutline, TelescopeOutline } from '@vicons/ionicons5'
import { useRouter } from 'vue-router'

const router = useRouter()

const stars = Array.from({ length: 160 }, (_, i) => ({
  id: i,
  top: Math.random() * 100,
  left: Math.random() * 100,
  delay: Math.random() * 5,
  duration: 2 + Math.random() * 4,
  size: 1 + Math.random() * 2.5,
}))

const shootingStars = Array.from({ length: 6 }, (_, i) => ({
  id: i,
  delay: i * 2.5 + Math.random() * 3,
  duration: 1.5 + Math.random() * 1.5,
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
        :style="{
          top: s.top + '%',
          left: s.left + '%',
          animationDelay: s.delay + 's',
          animationDuration: s.duration + 's',
          width: s.size + 'px',
          height: s.size + 'px',
        }"
      />
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
          transform: `scale(${ss.scale})`,
        }"
      />
    </div>

    <!-- 浮动光球 -->
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <!-- 内容 -->
    <div class="about-content">
      <!-- 旋转行星 -->
      <div class="planet-wrap">
        <div class="planet" />
        <div class="planet-ring" />
      </div>

      <h1 class="about-title">OmicHub</h1>
      <p class="about-subtitle">多组学数据分析平台</p>

      <div class="about-description">
        <p>
          OmicHub 是面向生命科学研究的私有化多组学分析平台，整合 RNA-seq、ATAC-seq、ChIP-seq、
          单细胞测序、全基因组测序等主流分析流程。基于 Snakemake 工作流引擎，实现从原始数据质控、
          比对、定量到差异分析与可视化的全流程自动化，让研究人员能够专注于科学发现本身。
        </p>
      </div>

      <div class="about-quote-box">
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
  </div>
</template>

<style scoped>
@keyframes shooting {
  0% {
    transform: translateX(0) translateY(0) rotate(-35deg) scaleX(0);
    opacity: 0;
  }
  10% {
    opacity: 1;
    transform: translateX(60px) translateY(42px) rotate(-35deg) scaleX(1);
  }
  70% {
    opacity: 1;
    transform: translateX(420px) translateY(294px) rotate(-35deg) scaleX(1);
  }
  100% {
    transform: translateX(600px) translateY(420px) rotate(-35deg) scaleX(0.6);
    opacity: 0;
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
  background: #fff;
  border-radius: 50%;
  animation: twinkle ease-in-out infinite;
  box-shadow: 0 0 4px rgba(255, 255, 255, 0.6);
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
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.9), rgba(107, 141, 214, 0.6), transparent);
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

/* 平台描述 */
.about-description {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 24px;
  backdrop-filter: blur(8px);
}
.about-description p {
  font-size: 14px;
  line-height: 1.8;
  color: #cbd5e1;
  margin: 0;
  text-align: justify;
  text-indent: 2em;
}

/* 引言盒子 */
.about-quote-box {
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 12px;
  padding: 24px 28px;
  margin-bottom: 28px;
  backdrop-filter: blur(8px);
}
.about-quote {
  font-size: 14px;
  line-height: 1.9;
  color: #e2e8f0;
  text-align: justify;
  margin: 0;
  text-indent: 2em;
}

/* 特性 */
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
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.15);
  transition: all 0.3s ease;
  text-align: left;
}
.feature-item:hover {
  background: rgba(22, 93, 255, 0.15);
  border-color: rgba(22, 93, 255, 0.4);
  transform: translateY(-4px);
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
  .about-description p,
  .about-quote { font-size: 13px; }
  .about-description,
  .about-quote-box { padding: 16px 20px; }
  .features { grid-template-columns: 1fr; }
  .about-actions {
    flex-direction: column;
    align-items: center;
  }
}
</style>
