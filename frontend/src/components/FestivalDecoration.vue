<script setup lang="ts">
interface Props {
  decoration: string
  themeColor?: string
}

const props = defineProps<Props>()

const decorationClass = `decoration-${props.decoration}`
</script>

<template>
  <div class="festival-decoration" :class="decorationClass">
    <!-- 春节：福字灯笼（仅保留左侧） -->
    <template v-if="decoration === 'spring_couplets'">
      <div class="couplet couplet-left">福</div>
      <div class="gold-shards">
        <span v-for="n in 12" :key="n" class="shard" :style="{ left: `${Math.random() * 100}%`, animationDelay: `${Math.random() * 2}s` }">✦</span>
      </div>
    </template>

    <!-- 元宵节：灯笼 -->
    <template v-else-if="decoration === 'lanterns'">
      <div v-for="n in 5" :key="n" class="lantern" :style="{ left: `${10 + n * 18}%`, animationDelay: `${n * 0.8}s` }">🏮</div>
    </template>

    <!-- 端午节：竹叶 -->
    <template v-else-if="decoration === 'bamboo'">
      <div v-for="n in 6" :key="n" class="bamboo-leaf" :style="{ left: `${5 + n * 16}%`, transform: `rotate(${-10 + n * 4}deg)` }">🎋</div>
    </template>

    <!-- 七夕：爱心星群 -->
    <template v-else-if="decoration === 'stars_heart'">
      <div class="star-heart">💕</div>
      <div class="star-orbit star-orbit-1">✨</div>
      <div class="star-orbit star-orbit-2">✨</div>
    </template>

    <!-- 中秋：月亮兔子 -->
    <template v-else-if="decoration === 'moon_rabbit'">
      <div class="moon-mini">🌕</div>
      <div class="rabbit-silhouette">🐇</div>
    </template>

    <!-- 重阳：菊花 -->
    <template v-else-if="decoration === 'chrysanthemum'">
      <div v-for="n in 4" :key="n" class="chrysanthemum" :style="{ left: `${80 + n * 5}%`, top: `${10 + n * 8}%` }">🌼</div>
    </template>

    <!-- 元旦：烟花横幅 -->
    <template v-else-if="decoration === 'fireworks_banner'">
      <div class="new-year-banner">🎆 新年快乐 🎆</div>
    </template>

    <!-- 劳动节：工具 -->
    <template v-else-if="decoration === 'tools'">
      <div class="tool tool-hammer">🔨</div>
      <div class="tool tool-wrench">🔧</div>
      <div class="tool tool-gear">⚙️</div>
    </template>

    <!-- 国庆节：五角星 -->
    <template v-else-if="decoration === 'national_banner'">
      <div class="national-stars">
        <span v-for="n in 5" :key="n" class="nat-star" :style="{ animationDelay: `${n * 0.2}s` }">⭐</span>
      </div>
    </template>

    <!-- 情人节：爱心 -->
    <template v-else-if="decoration === 'hearts'">
      <div v-for="n in 6" :key="n" class="floating-heart" :style="{ left: `${5 + n * 15}%`, animationDelay: `${n * 0.5}s` }">💖</div>
    </template>

    <!-- 圣诞节：圣诞树 -->
    <template v-else-if="decoration === 'christmas_tree'">
      <div class="christmas-tree">🎄</div>
      <div class="reindeer">🦌</div>
    </template>

    <!-- 立春：嫩芽 -->
    <template v-else-if="decoration === 'sprout'">
      <div v-for="n in 5" :key="n" class="sprout-emoji" :style="{ left: `${5 + n * 20}%`, animationDelay: `${n * 0.3}s` }">🌱</div>
    </template>

    <!-- 夏至：太阳 -->
    <template v-else-if="decoration === 'sun'">
      <div class="sun-emoji">☀️</div>
    </template>

    <!-- 秋分：枫叶 -->
    <template v-else-if="decoration === 'maple'">
      <div v-for="n in 5" :key="n" class="maple-emoji" :style="{ left: `${5 + n * 20}%`, animationDelay: `${n * 0.4}s` }">🍁</div>
    </template>

    <!-- 冬至：雪花 -->
    <template v-else-if="decoration === 'snowflake'">
      <div class="dumpling">🥟</div>
      <div v-for="n in 4" :key="n" class="steam" :style="{ left: `${85 + n * 3}%`, animationDelay: `${n * 0.4}s` }">♨️</div>
    </template>

    <!-- 程序员节：终端 -->
    <template v-else-if="decoration === 'terminal'">
      <div class="terminal-blink">_</div>
      <div class="code-bracket">{ }</div>
    </template>

    <!-- 周年庆：星云 -->
    <template v-else-if="decoration === 'galaxy'">
      <div class="galaxy-ring"></div>
      <div class="planet">🪐</div>
    </template>
  </div>
</template>

<style scoped>
.festival-decoration {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  border-radius: inherit;
  z-index: 0;
}

/* 春节福字灯笼 */
.couplet {
  position: absolute;
  top: 0;
  width: 40px;
  padding: 18px 6px 44px;
  background: linear-gradient(180deg, rgba(196, 30, 30, 0.95) 0%, rgba(110, 10, 10, 0.92) 100%);
  color: #ffd700;
  font-size: 22px;
  font-weight: 700;
  text-align: center;
  border: 1px solid rgba(255, 215, 0, 0.75);
  border-top: none;
  border-radius: 0 0 8px 8px;
  box-shadow:
    0 0 0 1px rgba(196, 30, 30, 0.4),
    0 0 18px rgba(255, 215, 0, 0.25),
    inset 0 0 14px rgba(255, 215, 0, 0.08);
  writing-mode: vertical-rl;
}
.couplet-left { left: 18px; }
.couplet::before {
  content: '';
  position: absolute;
  top: -10px;
  left: 50%;
  transform: translateX(-50%);
  width: 12px;
  height: 10px;
  background: linear-gradient(180deg, #8b0000, #c41e1e);
  border: 1px solid rgba(255, 215, 0, 0.5);
  border-radius: 2px;
}
.gold-shards .shard {
  position: absolute;
  bottom: 0;
  color: #ffd700;
  font-size: 12px;
  opacity: 0;
  animation: floatUp 3s ease-in infinite;
}
@keyframes floatUp {
  0% { transform: translateY(0); opacity: 0; }
  20% { opacity: 1; }
  100% { transform: translateY(-200px) rotate(180deg); opacity: 0; }
}

/* 灯笼 */
.lantern {
  position: absolute;
  top: -40px;
  font-size: 34px;
  opacity: 0.85;
  animation: lanternSway 5s ease-in-out infinite;
  filter: drop-shadow(0 0 8px rgba(255, 165, 0, 0.5));
}
@keyframes lanternSway {
  0%, 100% { transform: translateY(0) rotate(-5deg); }
  50% { transform: translateY(30px) rotate(5deg); }
}

/* 竹叶 */
.bamboo-leaf {
  position: absolute;
  bottom: 8px;
  font-size: 28px;
  opacity: 0.7;
  animation: bambooSway 4s ease-in-out infinite alternate;
}
@keyframes bambooSway {
  from { transform: rotate(-10deg); }
  to { transform: rotate(10deg); }
}

/* 七夕爱心 */
.star-heart {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 32px;
  opacity: 0.7;
  animation: heartPulse 2s ease-in-out infinite;
}
.star-orbit {
  position: absolute;
  font-size: 14px;
  opacity: 0.6;
  animation: orbit 4s linear infinite;
}
.star-orbit-1 { top: 20%; left: 20%; }
.star-orbit-2 { top: 25%; right: 20%; animation-direction: reverse; }
@keyframes heartPulse {
  0%, 100% { transform: translateX(-50%) scale(1); }
  50% { transform: translateX(-50%) scale(1.15); }
}
@keyframes orbit {
  from { transform: rotate(0deg) translateX(30px) rotate(0deg); }
  to { transform: rotate(360deg) translateX(30px) rotate(-360deg); }
}

/* 中秋 */
.moon-mini {
  position: absolute;
  top: 16px;
  right: 20px;
  font-size: 36px;
  filter: drop-shadow(0 0 12px rgba(232, 220, 200, 0.5));
  animation: moonFloat 4s ease-in-out infinite;
}
.rabbit-silhouette {
  position: absolute;
  bottom: 16px;
  right: 24px;
  font-size: 24px;
  opacity: 0.8;
}
@keyframes moonFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

/* 重阳菊花 */
.chrysanthemum {
  position: absolute;
  font-size: 26px;
  opacity: 0.75;
  animation: chrysPulse 3s ease-in-out infinite;
}
@keyframes chrysPulse {
  0%, 100% { opacity: 0.5; transform: scale(0.95); }
  50% { opacity: 0.9; transform: scale(1.05); }
}

/* 元旦横幅 */
.new-year-banner {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #ffd700;
  font-size: 12px;
  letter-spacing: 1px;
}

/* 劳动节工具 */
.tool {
  position: absolute;
  font-size: 26px;
  opacity: 0.55;
}
.tool-hammer { top: 20px; left: 20px; animation: toolBob 3s ease-in-out infinite; }
.tool-wrench { bottom: 20px; right: 24px; animation: toolBob 3s ease-in-out 1s infinite; }
.tool-gear { top: 60px; right: 20px; animation: spin 8s linear infinite; }
@keyframes toolBob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 国庆五角星 */
.national-stars {
  position: absolute;
  top: 16px;
  left: 16px;
}
.nat-star {
  font-size: 22px;
  margin-right: 4px;
  display: inline-block;
  animation: starGlow 1.5s ease-in-out infinite;
}
@keyframes starGlow {
  0%, 100% { opacity: 0.6; filter: drop-shadow(0 0 2px #ffd700); }
  50% { opacity: 1; filter: drop-shadow(0 0 10px #ffd700); }
}

/* 情人节爱心 */
.floating-heart {
  position: absolute;
  bottom: -10px;
  font-size: 24px;
  opacity: 0.6;
  animation: heartFloat 4s ease-in infinite;
}
@keyframes heartFloat {
  0% { transform: translateY(0) scale(0.8); opacity: 0; }
  20% { opacity: 0.7; }
  100% { transform: translateY(-220px) scale(1.2); opacity: 0; }
}

/* 圣诞 */
.christmas-tree {
  position: absolute;
  top: 12px;
  right: 16px;
  font-size: 40px;
  filter: drop-shadow(0 0 8px rgba(144, 238, 144, 0.4));
}
.reindeer {
  position: absolute;
  bottom: 12px;
  left: 16px;
  font-size: 26px;
  animation: reindeerRun 6s linear infinite;
}
@keyframes reindeerRun {
  0% { transform: translateX(-50px); opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  100% { transform: translateX(300px); opacity: 0; }
}

/* 立春嫩芽 */
.sprout-emoji {
  position: absolute;
  bottom: 8px;
  font-size: 28px;
  animation: sproutPop 2s ease-out infinite alternate;
}
@keyframes sproutPop {
  from { transform: translateY(8px) scale(0.9); }
  to { transform: translateY(-4px) scale(1.1); }
}

/* 夏至太阳 */
.sun-emoji {
  position: absolute;
  top: 16px;
  right: 20px;
  font-size: 44px;
  animation: sunRotate 12s linear infinite;
}
@keyframes sunRotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 秋分枫叶 */
.maple-emoji {
  position: absolute;
  top: 12px;
  font-size: 24px;
  opacity: 0.7;
  animation: mapleSpin 5s linear infinite;
}
@keyframes mapleSpin {
  from { transform: rotate(0deg) translateY(0); }
  to { transform: rotate(360deg) translateY(10px); }
}

/* 冬至 */
.dumpling {
  position: absolute;
  bottom: 12px;
  right: 20px;
  font-size: 34px;
}
.steam {
  position: absolute;
  bottom: 50px;
  font-size: 14px;
  opacity: 0;
  animation: steamRise 2s ease-out infinite;
}
@keyframes steamRise {
  0% { transform: translateY(0); opacity: 0; }
  30% { opacity: 0.6; }
  100% { transform: translateY(-30px); opacity: 0; }
}

/* 程序员节终端 */
.terminal-blink {
  position: absolute;
  top: 16px;
  left: 18px;
  color: #00ff66;
  font-family: 'JetBrains Mono', monospace;
  font-size: 24px;
  animation: blink 1s step-end infinite;
}
.code-bracket {
  position: absolute;
  bottom: 16px;
  right: 20px;
  color: #00ff66;
  font-family: 'JetBrains Mono', monospace;
  font-size: 28px;
  opacity: 0.4;
}
@keyframes blink {
  50% { opacity: 0; }
}

/* 周年庆星云 */
.galaxy-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 300px;
  height: 300px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle, transparent 40%, rgba(167, 139, 250, 0.15) 60%, transparent 70%);
  animation: galaxySpin 20s linear infinite;
}
.planet {
  position: absolute;
  top: 20px;
  right: 20px;
  font-size: 30px;
  animation: planetBob 5s ease-in-out infinite;
}
@keyframes galaxySpin {
  from { transform: translate(-50%, -50%) rotate(0deg); }
  to { transform: translate(-50%, -50%) rotate(360deg); }
}
@keyframes planetBob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}
</style>
