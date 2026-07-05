<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref<HTMLCanvasElement | null>(null)
const containerRef = ref<HTMLDivElement | null>(null)

let animationId: number | null = null
let shootTimer: ReturnType<typeof setTimeout> | null = null

const emit = defineEmits<{
  tick: [time: number]
}>()

onMounted(() => {
  const canvasEl = canvasRef.value
  const containerEl = containerRef.value
  if (!canvasEl || !containerEl) return

  const ctx2d = canvasEl.getContext('2d')
  if (!ctx2d) return

  const canvas = canvasEl
  const container = containerEl
  const ctx = ctx2d

  const isMobile = window.innerWidth < 768
  const STAR_COUNT = isMobile ? 60 : 120
  const PARTICLE_COUNT = isMobile ? 20 : 40
  const CONNECTION_DIST = 100

  let w = 0
  let h = 0
  let dpr = 1
  let time = 0

  interface Star {
    x: number
    y: number
    r: number
    alpha: number
    speed: number
    dir: number
  }

  interface Particle {
    x: number
    y: number
    vx: number
    vy: number
    r: number
  }

  interface ShootingStar {
    x: number
    y: number
    vx: number
    vy: number
    life: number
    tail: { x: number; y: number }[]
  }

  const stars: Star[] = []
  const particles: Particle[] = []
  let shootingStar: ShootingStar | null = null
  const mouse = { x: -1000, y: -1000 }

  function resize() {
    const rect = container.getBoundingClientRect()
    dpr = window.devicePixelRatio || 1
    w = rect.width
    h = rect.height
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }

  resize()

  function initStars() {
    stars.length = 0
    for (let i = 0; i < STAR_COUNT; i++) {
      stars.push({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.5 + 0.3,
        alpha: Math.random(),
        speed: Math.random() * 0.02 + 0.005,
        dir: Math.random() > 0.5 ? 1 : -1,
      })
    }
  }

  function initParticles() {
    particles.length = 0
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        r: Math.random() * 2 + 1,
      })
    }
  }

  initStars()
  initParticles()

  function onMouseMove(e: MouseEvent) {
    const rect = container.getBoundingClientRect()
    mouse.x = e.clientX - rect.left
    mouse.y = e.clientY - rect.top
  }

  function onMouseLeave() {
    mouse.x = -1000
    mouse.y = -1000
  }

  container.addEventListener('mousemove', onMouseMove)
  container.addEventListener('mouseleave', onMouseLeave)
  window.addEventListener('resize', resize)

  function spawnShootingStar() {
    if (!shootingStar && w > 0 && h > 0) {
      shootingStar = {
        x: Math.random() * w * 0.5,
        y: Math.random() * h * 0.3,
        vx: 3 + Math.random() * 2,
        vy: 1 + Math.random() * 1.5,
        life: 1,
        tail: [],
      }
    }
    shootTimer = setTimeout(spawnShootingStar, 4000 + Math.random() * 4000)
  }
  spawnShootingStar()

  let isPaused = false

  function onVisibilityChange() {
    isPaused = document.hidden
    if (!isPaused && !animationId) {
      animate()
    }
  }
  document.addEventListener('visibilitychange', onVisibilityChange)

  function animate() {
    if (isPaused) return

    time += 0.016
    emit('tick', time)

    ctx.clearRect(0, 0, w, h)

    // 1. 呼吸星星
    stars.forEach((s) => {
      s.alpha += s.speed * s.dir
      if (s.alpha > 1 || s.alpha < 0.2) s.dir *= -1
      ctx.beginPath()
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(255, 255, 255, ${s.alpha * 0.8})`
      ctx.fill()
    })

    // 2. 网络粒子 + 鼠标引力
    particles.forEach((p, i) => {
      p.x += p.vx
      p.y += p.vy
      if (p.x < 0 || p.x > w) p.vx *= -1
      if (p.y < 0 || p.y > h) p.vy *= -1

      const dx = mouse.x - p.x
      const dy = mouse.y - p.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 150) {
        p.vx += dx * 0.0003
        p.vy += dy * 0.0003
      }
      p.vx *= 0.99
      p.vy *= 0.99

      ctx.beginPath()
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.6)'
      ctx.fill()

      for (let j = i + 1; j < particles.length; j++) {
        const p2 = particles[j]
        const d = Math.sqrt((p.x - p2.x) ** 2 + (p.y - p2.y) ** 2)
        if (d < CONNECTION_DIST) {
          ctx.beginPath()
          ctx.moveTo(p.x, p.y)
          ctx.lineTo(p2.x, p2.y)
          ctx.strokeStyle = `rgba(255, 255, 255, ${0.15 * (1 - d / CONNECTION_DIST)})`
          ctx.lineWidth = 0.8
          ctx.stroke()
        }
      }
    })

    // 3. 流星
    if (shootingStar) {
      shootingStar.x += shootingStar.vx
      shootingStar.y += shootingStar.vy
      shootingStar.life -= 0.015
      shootingStar.tail.push({ x: shootingStar.x, y: shootingStar.y })
      if (shootingStar.tail.length > 15) shootingStar.tail.shift()

      ctx.beginPath()
      for (let i = 0; i < shootingStar.tail.length - 1; i++) {
        const t = shootingStar.tail[i]
        const t2 = shootingStar.tail[i + 1]
        ctx.moveTo(t.x, t.y)
        ctx.lineTo(t2.x, t2.y)
      }
      ctx.strokeStyle = `rgba(255, 255, 255, ${shootingStar.life * 0.6})`
      ctx.lineWidth = 2
      ctx.stroke()

      ctx.beginPath()
      ctx.arc(shootingStar.x, shootingStar.y, 2, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(255, 255, 255, ${shootingStar.life})`
      ctx.shadowBlur = 10
      ctx.shadowColor = 'white'
      ctx.fill()
      ctx.shadowBlur = 0

      if (shootingStar.life <= 0) shootingStar = null
    }

    animationId = requestAnimationFrame(animate)
  }

  animate()

  onUnmounted(() => {
    if (animationId) cancelAnimationFrame(animationId)
    animationId = null
    if (shootTimer) clearTimeout(shootTimer)
    container.removeEventListener('mousemove', onMouseMove)
    container.removeEventListener('mouseleave', onMouseLeave)
    window.removeEventListener('resize', resize)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })
})

onUnmounted(() => {
  if (animationId) {
    cancelAnimationFrame(animationId)
    animationId = null
  }
  if (shootTimer) {
    clearTimeout(shootTimer)
    shootTimer = null
  }
})
</script>

<template>
  <div ref="containerRef" class="starfield-container">
    <canvas ref="canvasRef" class="starfield-canvas" />
  </div>
</template>

<style scoped>
.starfield-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  overflow: hidden;
  background: linear-gradient(135deg, #9b7ec8 0%, #7b5aa6 50%, #6b4b96 100%);
}

.starfield-canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
