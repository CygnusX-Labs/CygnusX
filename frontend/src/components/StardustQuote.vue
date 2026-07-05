<script setup lang="ts">
import { ref } from 'vue'

const expanded = ref(false)
</script>

<template>
  <div
    class="stardust-quote"
    @mouseenter="expanded = true"
    @mouseleave="expanded = false"
  >
    <div class="quote-en gilded breathe">"We are made of star-stuff"</div>
    <div class="quote-cn-short gilded breathe breathe-delayed">
      我们只是借用了宇宙中的这些原子，短暂地体验了一次这个世界。
    </div>
    <div class="quote-cn-full" :class="{ expanded }">
      我们只是借用了宇宙中的这些碳、氢、氧原子几十年，用它们去短暂地体验了一次这个世界。
      组成我们大脑和身体的每一个原子，都来自几十亿年前远古恒星内部的核聚变爆炸。
      当生命结束时，我们并没有化为虚无，我们只是回到了那个浩瀚的宇宙中，换了一种方式继续存在。
    </div>
  </div>
</template>

<style scoped>
.stardust-quote {
  position: absolute;
  bottom: 32px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  text-align: center;
  max-width: 680px;
  padding: 0 24px;
  opacity: 0.85;
  transition: opacity 0.4s ease;
  cursor: default;
  pointer-events: auto;
}

.stardust-quote:hover {
  opacity: 1;
}

.quote-en {
  font-size: 13px;
  font-style: italic;
  letter-spacing: 1.5px;
  margin-bottom: 10px;
  font-family: Georgia, 'Times New Roman', serif;
}

.gilded {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.75) 0%,
    #fff8d4 25%,
    #ffd700 50%,
    #fff8d4 75%,
    rgba(255, 255, 255, 0.75) 100%
  );
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer 10s linear infinite;
  text-shadow: none;
  filter: drop-shadow(0 0 6px rgba(255, 215, 100, 0.35));
}

.breathe {
  animation: shimmer 10s linear infinite, breathe-glow 6s ease-in-out infinite;
}

.breathe-delayed {
  animation: shimmer 10s linear infinite, breathe-glow 6s ease-in-out infinite 1.5s;
}

@keyframes shimmer {
  0% { background-position: 200% center; }
  100% { background-position: -200% center; }
}

@keyframes breathe-glow {
  0%, 100% {
    opacity: 0.72;
    filter: drop-shadow(0 0 5px rgba(255, 215, 100, 0.3));
  }
  50% {
    opacity: 1;
    filter: drop-shadow(0 0 10px rgba(255, 215, 100, 0.55));
  }
}

.quote-cn-short {
  font-size: 12px;
  line-height: 1.8;
  transition: all 0.3s ease;
}

.quote-cn-full {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.9;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  transition: max-height 0.6s ease, opacity 0.4s ease, margin-top 0.3s ease;
  margin-top: 0;
}

.quote-cn-full.expanded {
  max-height: 200px;
  opacity: 1;
  margin-top: 10px;
}

@media (max-width: 768px) {
  .stardust-quote {
    bottom: 16px;
    max-width: 90%;
  }
  .quote-cn-short {
    font-size: 11px;
  }
  .quote-cn-full {
    display: none;
  }
}
</style>
