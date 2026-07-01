<script setup lang="ts">
/**
 * LoginCats —— 登录卡片顶部猫咪动画浮层（两只各异的喵）
 *
 * 两只猫以绝对定位「趴」在白色登录卡片的顶部外边缘，底部贴合卡片上沿、探出半个身子，
 * 绝不遮挡卡片内部的 "OmicHub" 文字与输入框。
 * 复用项目既有 vue3-lottie 模式（同 RegistrationDisabledModal）：
 *   - :animation-link 走 public/lottie/*.json，用 BASE_URL 拼接兼容子路径部署
 *   - loop + auto-play 无限循环自动播放
 *   - @on-error 兜底为 🐱 emoji，资源缺失/损坏时浮层仍可看
 * pointer-events: none 确保猫咪不拦截表单点击。
 *
 * 素材分配（两只各异，避免重复）：
 *   - 左：orange-cat.json（橙猫，透明背景，镜像朝中央）
 *   - 右：loader-cat.json（加载猫，透明背景，放大突出）
 *
 * 两只均透明背景，无需 mix-blend 治白底。
 * 右猫放大（height 88）后同步上移 top，使底部位置与左猫一致、不遮挡 Logo 文字。
 */
import { ref } from 'vue'
import { Vue3Lottie } from 'vue3-lottie'

const BASE = import.meta.env.BASE_URL
const urls = {
  orange: `${BASE}lottie/orange-cat.json`,
  loader: `${BASE}lottie/loader-cat.json`,
}

// 每只猫独立的失败标记，单只挂掉不影响另一只
const leftFailed = ref(false)
const rightFailed = ref(false)
</script>

<template>
  <div class="login-cats" aria-hidden="true">
    <!-- 左：橙猫，镜像翻转面朝中央（透明背景） -->
    <div class="cat cat--left">
      <Vue3Lottie
        v-if="!leftFailed"
        :animation-link="urls.orange"
        :loop="true"
        :auto-play="true"
        :height="72"
        @on-error="leftFailed = true"
      />
      <span v-else class="cat-emoji">🐱</span>
    </div>

    <!-- 右：加载猫（透明背景，放大突出） -->
    <div class="cat cat--right">
      <Vue3Lottie
        v-if="!rightFailed"
        :animation-link="urls.loader"
        :loop="true"
        :auto-play="true"
        :height="88"
        @on-error="rightFailed = true"
      />
      <span v-else class="cat-emoji">🐱</span>
    </div>
  </div>
</template>

<style scoped>
.login-cats {
  /* 挂在 .login-card（position: relative）顶部，零布局占位 */
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 0;
  pointer-events: none; /* 不拦截卡片内的表单点击 */
  z-index: 3;
}

.cat {
  position: absolute;
  pointer-events: none;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  /* 强制透明容器：vue3-lottie 默认即 transparent，此处 !important 双保险，
     彻底杜绝任何继承背景造成的白块 */
  background: transparent !important;
}

/* 深入 vue3-lottie 内部容器，确保其也无背景 */
.cat :deep(.lottie-animation-container) {
  background-color: transparent !important;
}

/* 左：橙猫，镜像翻转面朝中央，靠左分布 */
.cat--left {
  left: 16px;
  top: -38px; /* height 72 → 底部约在卡片顶部下方 34px（padding 区，未到文字） */
  transform: scaleX(-1);
}

/* 右：加载猫，放大（height 88），同步上移 top 使底部位置与左猫一致、不遮 Logo */
.cat--right {
  right: 16px;
  top: -54px; /* height 88 → 底部仍在卡片顶部下方 ~34px，与左猫底部对齐 */
}

.cat-emoji {
  font-size: 40px;
  line-height: 1;
  filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.15));
}

/* 响应式：移动端只保留右侧放大的猫并居中，避免窄屏拥挤 */
@media (max-width: 767px) {
  .cat--left {
    display: none;
  }
  .cat--right {
    right: auto;
    left: 50%;
    top: -48px;
    transform: translateX(-50%);
  }
}
</style>
