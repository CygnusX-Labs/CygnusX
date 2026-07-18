<template>
  <div class="not-found-container" role="main" aria-label="页面未找到">
    <div class="not-found-orb not-found-orb--1" />
    <div class="not-found-content animate-scale-in">
      <div class="not-found-mascot" aria-hidden="true">🐱</div>
      <h1 class="error-code animate-float">404</h1>
      <p class="error-message">页面未找到</p>
      <p class="error-hint">您访问的页面可能已移除或暂时不可用</p>
      <n-button type="primary" size="large" @click="handleGoBack">
        返回首页
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

const handleGoBack = () => {
  router.push('/')
}
</script>

<style scoped>
.not-found-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(-45deg, #165DFF, #3063FF, #6B8DD6, #8E54E9);
  background-size: 400% 400%;
  animation: gradientShift 12s ease infinite;
  color: white;
  position: relative;
  overflow: hidden;
}

.not-found-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.25;
  pointer-events: none;
}
.not-found-orb--1 {
  width: 500px;
  height: 500px;
  background: #a5b4fc;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation: drift 18s ease-in-out infinite;
}

.not-found-content {
  text-align: center;
  position: relative;
  z-index: 1;
}

.not-found-mascot {
  margin-bottom: -8px;
  font-size: 54px;
  filter: drop-shadow(0 8px 18px rgba(11, 15, 25, 0.2));
  animation: mascot-bob 3.5s ease-in-out infinite;
}

.error-code {
  font-size: 120px;
  font-weight: 800;
  margin-bottom: 16px;
  line-height: 1;
  text-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
}

.error-message {
  font-size: 24px;
  margin-bottom: 8px;
  opacity: 0.95;
}

.error-hint {
  font-size: 14px;
  opacity: 0.6;
  margin-bottom: 32px;
}

@keyframes mascot-bob {
  0%, 100% { transform: translateY(0) rotate(-3deg); }
  50% { transform: translateY(-8px) rotate(3deg); }
}
</style>
