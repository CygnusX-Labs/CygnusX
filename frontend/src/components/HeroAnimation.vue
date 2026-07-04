<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref<HTMLCanvasElement | null>(null)

let animationId: number | null = null
let resizeHandler: (() => void) | null = null
let visibilityHandler: (() => void) | null = null

type AnimationMode = 'particles' | 'stars' | 'aura' | 'noise' | 'orbitals' | 'gradient'

interface ParticleState {
  particles: Array<{
    x: number
    y: number
    vx: number
    vy: number
    size: number
    opacity: number
    pulse: number
  }>
  time: number
}

interface StarState {
  stars: Array<{
    x: number
    y: number
    size: number
    speed: number
    twinkle: number
    twinkleSpeed: number
  }>
  time: number
}

interface AuraRing {
  radius: number
  maxRadius: number
  speed: number
  delay: number
  age: number
  opacity: number
}

interface AuraRay {
  angle: number
  length: number
  maxLength: number
  speed: number
  width: number
  delay: number
}

interface AuraState {
  rings: AuraRing[]
  rays: AuraRay[]
  cx: number
  cy: number
}

interface NoiseLine {
  x: number
  y: number
  length: number
  speed: number
  opacity: number
  width: number
  noiseScale: number
  time: number
}

interface NoiseState {
  lines: NoiseLine[]
  time: number
}

interface OrbitalRing {
  cx: number
  cy: number
  radius: number
  tilt: number
  rotation: number
  rotSpeed: number
  opacity: number
  dotAngle: number
  dotSpeed: number
}

interface OrbitalsState {
  rings: OrbitalRing[]
}

interface GradientBlob {
  x: number
  y: number
  radius: number
  vx: number
  vy: number
  colorStart: string
  colorEnd: string
  pulse: number
  pulseSpeed: number
}

interface GradientState {
  blobs: GradientBlob[]
}

type AnimationState = ParticleState | StarState | AuraState | NoiseState | OrbitalsState | GradientState

// 简化版 Perlin noise
const PERLIN = {
  p: new Uint8Array(512),
  init() {
    for (let i = 0; i < 256; i++) this.p[i] = this.p[i + 256] = Math.floor(Math.random() * 256)
  },
  fade(t: number) {
    return t * t * t * (t * (t * 6 - 15) + 10)
  },
  lerp(t: number, a: number, b: number) {
    return a + t * (b - a)
  },
  grad(hash: number, x: number, y: number) {
    const h = hash & 15
    const u = h < 8 ? x : y
    const v = h < 4 ? y : h === 12 || h === 14 ? x : 0
    return ((h & 1) === 0 ? u : -u) + ((h & 2) === 0 ? v : -v)
  },
  noise(x: number, y: number) {
    const X = Math.floor(x) & 255
    const Y = Math.floor(y) & 255
    x -= Math.floor(x)
    y -= Math.floor(y)
    const u = this.fade(x)
    const v = this.fade(y)
    const A = this.p[X] + Y
    const B = this.p[X + 1] + Y
    return this.lerp(
      v,
      this.lerp(u, this.grad(this.p[A], x, y), this.grad(this.p[B], x - 1, y)),
      this.lerp(u, this.grad(this.p[A + 1], x, y - 1), this.grad(this.p[B + 1], x - 1, y - 1)),
    )
  },
}
PERLIN.init()

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const c = canvas
  const g = ctx

  let w = 0
  let h = 0
  let dpr = 1

  function resize() {
    const rect = c.parentElement?.getBoundingClientRect()
    if (!rect) return
    dpr = window.devicePixelRatio || 1
    c.width = rect.width * dpr
    c.height = rect.height * dpr
    w = rect.width
    h = rect.height
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
  }

  resize()
  resizeHandler = resize
  window.addEventListener('resize', resize)

  const MODES: AnimationMode[] = ['particles', 'stars', 'aura', 'noise', 'orbitals', 'gradient']
  const currentMode: AnimationMode = MODES[Math.floor(Math.random() * MODES.length)]

  // ===== A: 浮动粒子网络 =====
  function initParticles(): ParticleState {
    const particles: ParticleState['particles'] = []
    const count = Math.max(20, Math.floor((w * h) / 8000))
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        size: 1 + Math.random() * 4,
        opacity: 0.2 + Math.random() * 0.4,
        pulse: Math.random() * Math.PI * 2,
      })
    }
    return { particles, time: 0 }
  }

  function drawParticles(state: ParticleState) {
    g.clearRect(0, 0, w, h)
    state.time += 0.016

    state.particles.forEach((p) => {
      p.x += p.vx
      p.y += p.vy
      p.pulse += 0.02

      if (p.x < -10) p.x = w + 10
      if (p.x > w + 10) p.x = -10
      if (p.y < -10) p.y = h + 10
      if (p.y > h + 10) p.y = -10

      const alpha = p.opacity * (0.6 + 0.4 * Math.sin(p.pulse))
      g.globalAlpha = alpha
      g.fillStyle = 'rgba(255,255,255,0.8)'
      g.beginPath()
      g.arc(p.x, p.y, p.size * (0.8 + 0.2 * Math.sin(p.pulse)), 0, Math.PI * 2)
      g.fill()
    })

    g.strokeStyle = 'rgba(255,255,255,0.12)'
    g.lineWidth = 0.5
    const connectDist = 100

    for (let i = 0; i < state.particles.length; i++) {
      for (let j = i + 1; j < state.particles.length; j++) {
        const dx = state.particles[i].x - state.particles[j].x
        const dy = state.particles[i].y - state.particles[j].y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < connectDist) {
          g.globalAlpha = (1 - dist / connectDist) * 0.15
          g.beginPath()
          g.moveTo(state.particles[i].x, state.particles[i].y)
          g.lineTo(state.particles[j].x, state.particles[j].y)
          g.stroke()
        }
      }
    }
    g.globalAlpha = 1
  }

  // ===== B: 星空粒子 =====
  function initStars(): StarState {
    const stars: StarState['stars'] = []
    const count = Math.max(25, Math.floor((w * h) / 5000))
    for (let i = 0; i < count; i++) {
      stars.push({
        x: Math.random() * w,
        y: Math.random() * h,
        size: 0.5 + Math.random() * 2,
        speed: 0.1 + Math.random() * 0.3,
        twinkle: Math.random() * Math.PI * 2,
        twinkleSpeed: 0.02 + Math.random() * 0.03,
      })
    }
    return { stars, time: 0 }
  }

  function drawStars(state: StarState) {
    g.clearRect(0, 0, w, h)
    state.time += 0.016

    state.stars.forEach((s) => {
      s.y -= s.speed
      s.twinkle += s.twinkleSpeed

      if (s.y < -5) {
        s.y = h + 5
        s.x = Math.random() * w
      }

      const alpha = 0.3 + 0.5 * Math.sin(s.twinkle)
      g.globalAlpha = alpha
      g.fillStyle = 'rgba(255,255,255,0.95)'

      g.beginPath()
      g.arc(s.x, s.y, s.size, 0, Math.PI * 2)
      g.fill()

      if (s.size > 1.5) {
        g.strokeStyle = `rgba(255,255,255,${alpha * 0.4})`
        g.lineWidth = 0.5
        const r = s.size * 3
        g.beginPath()
        g.moveTo(s.x - r, s.y)
        g.lineTo(s.x + r, s.y)
        g.moveTo(s.x, s.y - r)
        g.lineTo(s.x, s.y + r)
        g.stroke()
      }
    })
    g.globalAlpha = 1
  }

  // ===== C: 光晕脉冲 =====
  function initAura(): AuraState {
    const rings: AuraRing[] = []
    const maxRings = 5

    for (let i = 0; i < maxRings; i++) {
      rings.push({
        radius: 0,
        maxRadius: Math.max(w, h) * 0.8,
        speed: 0.4 + Math.random() * 0.3,
        delay: i * 60,
        age: -i * 60,
        opacity: 0.3 + Math.random() * 0.2,
      })
    }

    const rays: AuraRay[] = []
    for (let i = 0; i < 12; i++) {
      rays.push({
        angle: (i / 12) * Math.PI * 2 + Math.random() * 0.3,
        length: 0,
        maxLength: Math.max(w, h) * 0.5,
        speed: 0.6 + Math.random() * 0.4,
        width: 0.5 + Math.random() * 1,
        delay: Math.random() * 200,
      })
    }

    return { rings, rays, cx: w * 0.7, cy: h * 0.5 }
  }

  function drawAura(state: AuraState) {
    g.clearRect(0, 0, w, h)

    state.rings.forEach((r) => {
      r.age++
      if (r.age < 0) return

      r.radius += r.speed
      if (r.radius > r.maxRadius) {
        r.radius = 0
        r.age = -r.delay
      }

      const progress = r.radius / r.maxRadius
      const alpha = r.opacity * (1 - progress) * (1 - progress)

      g.beginPath()
      g.arc(state.cx, state.cy, r.radius, 0, Math.PI * 2)
      g.strokeStyle = `rgba(255, 255, 255, ${alpha})`
      g.lineWidth = 1.5 * (1 - progress * 0.5)
      g.stroke()
    })

    state.rays.forEach((ray) => {
      ray.delay--
      if (ray.delay > 0) return

      ray.length += ray.speed
      if (ray.length > ray.maxLength) {
        ray.length = 0
        ray.delay = 100 + Math.random() * 150
        ray.angle += (Math.random() - 0.5) * 0.5
      }

      const progress = ray.length / ray.maxLength
      const alpha = 0.15 * (1 - progress)
      const x2 = state.cx + Math.cos(ray.angle) * ray.length
      const y2 = state.cy + Math.sin(ray.angle) * ray.length

      g.beginPath()
      g.moveTo(state.cx, state.cy)
      g.lineTo(x2, y2)
      g.strokeStyle = `rgba(255, 255, 255, ${alpha})`
      g.lineWidth = ray.width
      g.stroke()
    })
  }

  // ===== D: 噪点流场 =====
  function initNoiseField(): NoiseState {
    const lines: NoiseLine[] = []
    const count = Math.max(30, Math.floor((w * h) / 6000))

    for (let i = 0; i < count; i++) {
      lines.push({
        x: Math.random() * w,
        y: Math.random() * h,
        length: 20 + Math.random() * 40,
        speed: 0.2 + Math.random() * 0.3,
        opacity: 0.08 + Math.random() * 0.15,
        width: 0.5 + Math.random() * 0.8,
        noiseScale: 0.003 + Math.random() * 0.002,
        time: Math.random() * 100,
      })
    }
    return { lines, time: 0 }
  }

  function drawNoiseField(state: NoiseState) {
    g.clearRect(0, 0, w, h)
    state.time += 0.008

    state.lines.forEach((line) => {
      line.time += line.speed * 0.01

      const angle = PERLIN.noise(line.x * line.noiseScale, line.y * line.noiseScale + state.time) * Math.PI * 2
      const x2 = line.x + Math.cos(angle) * line.length
      const y2 = line.y + Math.sin(angle) * line.length

      const purpleTint = Math.abs(PERLIN.noise(line.x * 0.005, line.y * 0.005)) * 0.3

      g.beginPath()
      g.moveTo(line.x, line.y)
      g.lineTo(x2, y2)
      g.strokeStyle = `rgba(255, ${255 - purpleTint * 100}, 255, ${line.opacity})`
      g.lineWidth = line.width
      g.lineCap = 'round'
      g.stroke()

      line.x += Math.cos(angle) * 0.3
      line.y += Math.sin(angle) * 0.3

      if (line.x < -50) line.x = w + 50
      if (line.x > w + 50) line.x = -50
      if (line.y < -50) line.y = h + 50
      if (line.y > h + 50) line.y = -50
    })
  }

  // ===== E: 轨道环 =====
  function initOrbitals(): OrbitalsState {
    const rings: OrbitalRing[] = []
    const count = 3 + Math.floor(Math.random() * 2)

    for (let i = 0; i < count; i++) {
      rings.push({
        cx: w * 0.7 + (Math.random() - 0.5) * 40,
        cy: h * 0.5 + (Math.random() - 0.5) * 30,
        radius: 40 + i * 35 + Math.random() * 20,
        tilt: (Math.random() - 0.5) * 0.4,
        rotation: Math.random() * Math.PI * 2,
        rotSpeed: (Math.random() - 0.5) * 0.003,
        opacity: 0.15 + Math.random() * 0.1,
        dotAngle: Math.random() * Math.PI * 2,
        dotSpeed: 0.005 + Math.random() * 0.005,
      })
    }

    return { rings }
  }

  function drawOrbitals(state: OrbitalsState) {
    g.clearRect(0, 0, w, h)

    state.rings.forEach((r) => {
      r.rotation += r.rotSpeed
      r.dotAngle += r.dotSpeed

      g.save()
      g.translate(r.cx, r.cy)
      g.rotate(r.rotation)
      g.scale(1, Math.cos(r.tilt))

      g.beginPath()
      g.arc(0, 0, r.radius, 0, Math.PI * 2)
      g.strokeStyle = `rgba(255, 255, 255, ${r.opacity})`
      g.lineWidth = 1
      g.stroke()

      const dotX = Math.cos(r.dotAngle) * r.radius
      const dotY = Math.sin(r.dotAngle) * r.radius
      g.fillStyle = 'rgba(255, 255, 255, 0.7)'
      g.beginPath()
      g.arc(dotX, dotY, 2.5, 0, Math.PI * 2)
      g.fill()

      g.restore()
    })

    g.fillStyle = 'rgba(255, 255, 255, 0.5)'
    g.beginPath()
    g.arc(w * 0.7, h * 0.5, 3, 0, Math.PI * 2)
    g.fill()
  }

  // ===== F: 渐变流光 =====
  function initGradientFlow(): GradientState {
    const blobs: GradientBlob[] = []
    const colors = [
      ['rgba(100, 150, 255, 0.15)', 'rgba(100, 150, 255, 0)'],
      ['rgba(180, 100, 255, 0.12)', 'rgba(180, 100, 255, 0)'],
      ['rgba(255, 120, 200, 0.1)', 'rgba(255, 120, 200, 0)'],
    ]

    for (let i = 0; i < 3; i++) {
      blobs.push({
        x: w * (0.3 + Math.random() * 0.5),
        y: h * (0.2 + Math.random() * 0.6),
        radius: 100 + Math.random() * 150,
        vx: (Math.random() - 0.5) * 0.15,
        vy: (Math.random() - 0.5) * 0.15,
        colorStart: colors[i][0],
        colorEnd: colors[i][1],
        pulse: Math.random() * Math.PI * 2,
        pulseSpeed: 0.005 + Math.random() * 0.005,
      })
    }

    return { blobs }
  }

  function drawGradientFlow(state: GradientState) {
    g.clearRect(0, 0, w, h)

    state.blobs.forEach((b) => {
      b.x += b.vx
      b.y += b.vy
      b.pulse += b.pulseSpeed

      if (b.x < -b.radius) b.vx = Math.abs(b.vx)
      if (b.x > w + b.radius) b.vx = -Math.abs(b.vx)
      if (b.y < -b.radius) b.vy = Math.abs(b.vy)
      if (b.y > h + b.radius) b.vy = -Math.abs(b.vy)

      const radius = b.radius * (0.9 + 0.1 * Math.sin(b.pulse))

      const gradient = g.createRadialGradient(b.x, b.y, 0, b.x, b.y, radius)
      gradient.addColorStop(0, b.colorStart)
      gradient.addColorStop(1, b.colorEnd)

      g.fillStyle = gradient
      g.fillRect(0, 0, w, h)
    })
  }

  let state: AnimationState | null = null

  function animate() {
    switch (currentMode) {
      case 'particles':
        if (!state) state = initParticles()
        drawParticles(state as ParticleState)
        break
      case 'stars':
        if (!state) state = initStars()
        drawStars(state as StarState)
        break
      case 'aura':
        if (!state) state = initAura()
        drawAura(state as AuraState)
        break
      case 'noise':
        if (!state) state = initNoiseField()
        drawNoiseField(state as NoiseState)
        break
      case 'orbitals':
        if (!state) state = initOrbitals()
        drawOrbitals(state as OrbitalsState)
        break
      case 'gradient':
        if (!state) state = initGradientFlow()
        drawGradientFlow(state as GradientState)
        break
    }
    animationId = requestAnimationFrame(animate)
  }

  animate()

  visibilityHandler = () => {
    if (document.hidden) {
      if (animationId) {
        cancelAnimationFrame(animationId)
        animationId = null
      }
    } else if (!animationId) {
      animate()
    }
  }
  document.addEventListener('visibilitychange', visibilityHandler)
})

onUnmounted(() => {
  if (animationId) {
    cancelAnimationFrame(animationId)
    animationId = null
  }
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler)
    resizeHandler = null
  }
  if (visibilityHandler) {
    document.removeEventListener('visibilitychange', visibilityHandler)
    visibilityHandler = null
  }
})
</script>

<template>
  <canvas ref="canvasRef" class="hero-canvas" />
</template>

<style scoped>
.hero-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0.35;
  pointer-events: none;
  z-index: 1;
}
</style>
