<script setup lang="ts">
import { computed } from 'vue'
import type { RoutedAgentInfo } from './types'

const props = defineProps<{
  route: RoutedAgentInfo
}>()

const transition = computed(() => props.route.transition)
const accentStyle = computed(() => ({
  '--route-agent-color': props.route.color || 'var(--brand-primary)',
}))
</script>

<template>
  <Transition name="route-card" appear>
    <aside
      v-if="transition?.visible"
      class="route-transition-card"
      :style="accentStyle"
      role="status"
      aria-live="polite"
    >
      <div class="route-transition-card__rail" aria-hidden="true" />
      <div class="route-transition-card__content">
        <div class="route-transition-card__eyebrow">Router 判定</div>
        <div class="route-transition-card__path" aria-label="专家路由结果">
          <span class="route-transition-card__router">🧭 星尘 AI</span>
          <span class="route-transition-card__arrow" aria-hidden="true">→</span>
          <span class="route-transition-card__agent">
            <span aria-hidden="true">{{ route.avatar }}</span>
            {{ route.name }}
          </span>
        </div>
        <p class="route-transition-card__reason">{{ route.reason }}</p>
        <p class="route-transition-card__message">{{ transition.message }}</p>
        <div class="route-transition-card__footer">
          <span class="route-transition-card__next">下一步：{{ transition.nextStep }}</span>
          <span v-if="transition.requiresExecutionConfirmation" class="route-transition-card__guard">
            执行前需确认
          </span>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.route-transition-card {
  position: relative;
  display: flex;
  width: 100%;
  max-width: 1120px;
  margin: 0 0 var(--space-lg, 16px);
  overflow: hidden;
  color: var(--text-primary);
  background: var(--bg-card);
  border: 1px solid var(--stardust-border-soft);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.route-transition-card::before,
.route-transition-card::after {
  position: absolute;
  z-index: 2;
  pointer-events: none;
  content: '';
}

.route-transition-card::before {
  top: 50%;
  left: 0;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--route-agent-color);
  box-shadow:
    18px -22px 0 -1px color-mix(in srgb, var(--route-agent-color) 72%, transparent),
    34px 15px 0 -1px color-mix(in srgb, var(--route-agent-color) 56%, transparent),
    62px -8px 0 -2px color-mix(in srgb, var(--route-agent-color) 45%, transparent);
  opacity: 0;
  animation: route-card-particles 720ms var(--motion-standard, 220ms) ease-out both;
}

.route-transition-card::after {
  inset: 0;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--route-agent-color) 32%, transparent),
    color-mix(in srgb, var(--route-agent-color) 12%, transparent) 24%,
    transparent 58%
  );
  transform: translateX(-105%);
  animation: route-card-reveal 720ms var(--motion-standard, 220ms) cubic-bezier(0.2, 0.8, 0.2, 1) both;
}

.route-card-enter-active,
.route-card-leave-active {
  transition:
    opacity var(--motion-standard, 220ms) ease-out,
    transform var(--motion-standard, 220ms) var(--motion-spring, cubic-bezier(0.2, 0.8, 0.2, 1));
  transform-origin: top left;
}

.route-card-enter-from,
.route-card-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.985);
}

@keyframes route-card-reveal {
  from { transform: translateX(-105%); }
  to { transform: translateX(105%); }
}

@keyframes route-card-particles {
  0% { opacity: 0; transform: translateX(0) scale(0.6); }
  22% { opacity: 0.9; }
  100% { opacity: 0; transform: translateX(150px) scale(0.2); }
}

.route-transition-card__rail {
  flex: 0 0 4px;
  background: var(--route-agent-color);
}

.route-transition-card__content {
  min-width: 0;
  flex: 1;
  padding: var(--space-md, 12px) var(--space-lg, 16px);
}

.route-transition-card__eyebrow {
  margin-bottom: var(--space-xs, 4px);
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.route-transition-card__path {
  display: flex;
  align-items: center;
  gap: var(--space-sm, 8px);
  min-width: 0;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 650;
}

.route-transition-card__router,
.route-transition-card__agent {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.route-transition-card__agent {
  min-width: 0;
  color: var(--route-agent-color);
}

.route-transition-card__arrow {
  color: var(--text-tertiary);
}

.route-transition-card__reason,
.route-transition-card__message {
  margin: var(--space-sm, 8px) 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.route-transition-card__message {
  color: var(--text-tertiary);
}

.route-transition-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm, 8px);
  margin-top: var(--space-md, 12px);
  padding-top: var(--space-sm, 8px);
  border-top: 1px solid var(--stardust-border-soft);
  font-size: 12px;
}

.route-transition-card__next {
  color: var(--text-secondary);
}

.route-transition-card__guard {
  flex: 0 0 auto;
  padding: 2px 8px;
  color: var(--brand-primary);
  background: var(--brand-primary-light);
  border-radius: 999px;
  font-weight: 600;
}

@media (max-width: 640px) {
  .route-transition-card__path,
  .route-transition-card__footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .route-transition-card__arrow {
    display: none;
  }
}

@media (prefers-reduced-transparency: reduce) {
  .route-transition-card {
    background: var(--bg-card);
  }
}

@media (prefers-reduced-motion: reduce) {
  .route-card-enter-active,
  .route-card-leave-active {
    transition: none;
  }

  .route-card-enter-from,
  .route-card-leave-to {
    transform: none;
  }

  .route-transition-card::before,
  .route-transition-card::after {
    display: none;
  }
}
</style>
