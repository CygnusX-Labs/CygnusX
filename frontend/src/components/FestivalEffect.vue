<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import confetti from 'canvas-confetti'
import type { FestivalAnimationType } from '@/utils/festivalThemes'

interface Props {
  type: FestivalAnimationType | string
  duration?: number
  colors?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  duration: 10,
  colors: () => ['#FFD700', '#FF6B35', '#FF85C0', '#4ECDC4', '#A78BFA'],
})

const canvasRef = ref<HTMLCanvasElement | null>(null)
let rafId: number | null = null
let timer: ReturnType<typeof setInterval> | null = null
let stopFireworks: (() => void) | null = null

const reducedMotion = typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)').matches : false

function resizeCanvas(canvas: HTMLCanvasElement) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = window.innerWidth * dpr
  canvas.height = window.innerHeight * dpr
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function getCtx() {
  const canvas = canvasRef.value
  if (!canvas) return null
  return canvas.getContext('2d')
}

// ========== 通用粒子系统 ==========
interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  color: string
  alpha: number
  rotation: number
  rotationSpeed: number
  life: number
  maxLife: number
}

function createParticle(x: number, y: number, opts: Partial<Particle> = {}): Particle {
  const colors = props.colors.length > 0 ? props.colors : ['#FFD700']
  return {
    x,
    y,
    vx: (Math.random() - 0.5) * 2,
    vy: Math.random() * 2 + 0.5,
    size: Math.random() * 4 + 2,
    color: colors[Math.floor(Math.random() * colors.length)],
    alpha: 1,
    rotation: Math.random() * Math.PI * 2,
    rotationSpeed: (Math.random() - 0.5) * 0.1,
    life: 0,
    maxLife: Math.random() * 60 + 60,
    ...opts,
  }
}

function drawParticle(ctx: CanvasRenderingContext2D, p: Particle, shape: 'circle' | 'heart' | 'maple' = 'circle') {
  ctx.save()
  ctx.translate(p.x, p.y)
  ctx.rotate(p.rotation)
  ctx.globalAlpha = p.alpha
  ctx.fillStyle = p.color

  if (shape === 'heart') {
    const s = p.size
    ctx.beginPath()
    ctx.moveTo(0, s * 0.3)
    ctx.bezierCurveTo(-s * 0.5, -s * 0.3, -s, s * 0.1, 0, s)
    ctx.bezierCurveTo(s, s * 0.1, s * 0.5, -s * 0.3, 0, s * 0.3)
    ctx.fill()
  } else if (shape === 'maple') {
    const s = p.size
    ctx.beginPath()
    for (let i = 0; i < 5; i++) {
      const angle = (i * Math.PI * 2) / 5 - Math.PI / 2
      const ax = Math.cos(angle) * s
      const ay = Math.sin(angle) * s
      if (i === 0) ctx.moveTo(ax, ay)
      else ctx.lineTo(ax, ay)
      const bx = Math.cos(angle + Math.PI / 5) * s * 0.4
      const by = Math.sin(angle + Math.PI / 5) * s * 0.4
      ctx.lineTo(bx, by)
    }
    ctx.closePath()
    ctx.fill()
  } else {
    ctx.beginPath()
    ctx.arc(0, 0, p.size, 0, Math.PI * 2)
    ctx.fill()
  }

  ctx.restore()
}

// ========== 雪花 ==========
let snowParticles: Particle[] = []
function initSnow(count: number, gentle = false) {
  snowParticles = []
  for (let i = 0; i < count; i++) {
    snowParticles.push(
      createParticle(Math.random() * window.innerWidth, Math.random() * window.innerHeight, {
        vy: Math.random() * (gentle ? 1.5 : 2.5) + 0.3,
        vx: (Math.random() - 0.5) * (gentle ? 0.5 : 1),
        size: Math.random() * (gentle ? 3 : 4) + 1,
        color: props.colors[Math.floor(Math.random() * props.colors.length)],
        maxLife: Infinity,
      }),
    )
  }
}

function renderSnow(ctx: CanvasRenderingContext2D, gentle = false) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  for (const p of snowParticles) {
    p.x += p.vx + Math.sin(p.life * 0.02) * 0.5
    p.y += p.vy
    p.life++
    p.rotation += 0.01
    if (p.y > window.innerHeight + 10) {
      p.y = -10
      p.x = Math.random() * window.innerWidth
    }
    drawParticle(ctx, p, 'circle')
  }
}

// ========== 爱心升起 ==========
let heartParticles: Particle[] = []
function initHearts(count: number) {
  heartParticles = []
  for (let i = 0; i < count; i++) {
    heartParticles.push(
      createParticle(Math.random() * window.innerWidth, window.innerHeight + Math.random() * 200, {
        vy: -(Math.random() * 1.5 + 0.5),
        vx: (Math.random() - 0.5) * 0.8,
        size: Math.random() * 12 + 6,
        color: props.colors[Math.floor(Math.random() * props.colors.length)],
        maxLife: Infinity,
        alpha: Math.random() * 0.4 + 0.3,
      }),
    )
  }
}

function renderHearts(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  for (const p of heartParticles) {
    p.y += p.vy
    p.x += p.vx + Math.sin(p.life * 0.03) * 0.3
    p.life++
    if (p.y < -30) {
      p.y = window.innerHeight + 30
      p.x = Math.random() * window.innerWidth
    }
    drawParticle(ctx, p, 'heart')
  }
}

// ========== 枫叶飘落 ==========
let mapleParticles: Particle[] = []
function initMaples(count: number) {
  mapleParticles = []
  for (let i = 0; i < count; i++) {
    mapleParticles.push(
      createParticle(Math.random() * window.innerWidth, -Math.random() * window.innerHeight, {
        vy: Math.random() * 1.5 + 0.5,
        vx: Math.random() * 1 - 0.3,
        size: Math.random() * 10 + 6,
        color: props.colors[Math.floor(Math.random() * props.colors.length)],
        maxLife: Infinity,
        rotationSpeed: (Math.random() - 0.5) * 0.08,
      }),
    )
  }
}

function renderMaples(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  for (const p of mapleParticles) {
    p.y += p.vy
    p.x += p.vx + Math.sin(p.life * 0.02) * 0.8
    p.rotation += p.rotationSpeed
    p.life++
    if (p.y > window.innerHeight + 20) {
      p.y = -20
      p.x = Math.random() * window.innerWidth
    }
    drawParticle(ctx, p, 'maple')
  }
}

// ========== 代码雨 ==========
let codeColumns: { x: number; y: number; speed: number; chars: string[] }[] = []
const codeChars = '01{}();/=+<>[]|'
function initCodeRain() {
  codeColumns = []
  const colWidth = 16
  const cols = Math.ceil(window.innerWidth / colWidth)
  for (let i = 0; i < cols; i++) {
    codeColumns.push({
      x: i * colWidth,
      y: Math.random() * window.innerHeight,
      speed: Math.random() * 3 + 2,
      chars: Array.from({ length: 20 }, () => codeChars[Math.floor(Math.random() * codeChars.length)]),
    })
  }
}

function renderCodeRain(ctx: CanvasRenderingContext2D) {
  ctx.fillStyle = 'rgba(0, 0, 0, 0.08)'
  ctx.fillRect(0, 0, window.innerWidth, window.innerHeight)
  const colors = props.colors.length > 0 ? props.colors : ['#00FF66']
  ctx.font = 'bold 15px "JetBrains Mono", "Fira Code", monospace'
  ctx.textAlign = 'center'

  for (const col of codeColumns) {
    col.y += col.speed
    if (col.y > window.innerHeight + 200) {
      col.y = -200
      col.speed = Math.random() * 2.5 + 2
    }
    for (let i = 0; i < col.chars.length; i++) {
      const y = col.y - i * 20
      if (y < -20 || y > window.innerHeight + 20) continue
      const alpha = i === 0 ? 1 : Math.max(0.15, 1 - i * 0.05)
      ctx.fillStyle = i === 0 ? '#ffffff' : colors[0]
      ctx.globalAlpha = alpha
      ctx.fillText(col.chars[i], col.x + 8, y)
    }
  }
  ctx.globalAlpha = 1
}

// ========== 灯笼飘浮（CSS 实现更自然） ==========
function useLanterns() {
  // 灯笼通过 CSS 装饰层实现，这里不做 canvas 处理
  const ctx = getCtx()
  if (ctx) ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
}

// ========== 月亮升起 ==========
let moonProgress = 0
function renderMoonRise(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  moonProgress += 0.003
  if (moonProgress > 1) moonProgress = 1

  const startX = window.innerWidth * 0.85
  const startY = window.innerHeight * 0.9
  const endX = window.innerWidth * 0.8
  const endY = window.innerHeight * 0.2
  const x = startX + (endX - startX) * moonProgress
  const y = startY + (endY - startY) * moonProgress
  const radius = 60 + moonProgress * 20

  // 光晕
  const glow = ctx.createRadialGradient(x, y, radius * 0.8, x, y, radius * 4)
  const c = props.colors[0] || '#E8DCC8'
  glow.addColorStop(0, c + '40')
  glow.addColorStop(0.5, c + '10')
  glow.addColorStop(1, 'transparent')
  ctx.fillStyle = glow
  ctx.beginPath()
  ctx.arc(x, y, radius * 4, 0, Math.PI * 2)
  ctx.fill()

  // 月亮本体
  const moonGrad = ctx.createRadialGradient(x - radius * 0.3, y - radius * 0.3, 0, x, y, radius)
  moonGrad.addColorStop(0, '#fff8e7')
  moonGrad.addColorStop(1, c)
  ctx.fillStyle = moonGrad
  ctx.beginPath()
  ctx.arc(x, y, radius, 0, Math.PI * 2)
  ctx.fill()
}

// ========== 太阳脉动 ==========
let sunPulse = 0
function renderSunPulse(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  sunPulse += 0.02
  const x = window.innerWidth * 0.8
  const y = window.innerHeight * 0.2
  const radius = 70 + Math.sin(sunPulse) * 5
  const c = props.colors[0] || '#FFD700'

  // 光芒
  ctx.save()
  ctx.translate(x, y)
  ctx.rotate(sunPulse * 0.2)
  ctx.strokeStyle = c + '30'
  ctx.lineWidth = 2
  for (let i = 0; i < 12; i++) {
    const angle = (i * Math.PI * 2) / 12
    ctx.beginPath()
    ctx.moveTo(Math.cos(angle) * radius * 1.2, Math.sin(angle) * radius * 1.2)
    ctx.lineTo(Math.cos(angle) * radius * 2.2, Math.sin(angle) * radius * 2.2)
    ctx.stroke()
  }
  ctx.restore()

  // 太阳本体
  const sunGrad = ctx.createRadialGradient(x, y, 0, x, y, radius)
  sunGrad.addColorStop(0, '#fff')
  sunGrad.addColorStop(0.4, c)
  sunGrad.addColorStop(1, 'transparent')
  ctx.fillStyle = sunGrad
  ctx.beginPath()
  ctx.arc(x, y, radius * 1.5, 0, Math.PI * 2)
  ctx.fill()
}

// ========== 银河（七夕） ==========
let milkyWayStars: { x: number; y: number; size: number; alpha: number; twinkleSpeed: number; twinkleOffset: number }[] = []
let milkyWayBridge: { x: number; y: number; size: number; alpha: number }[] = []
let milkyWayHearts: Particle[] = []
function initMilkyWay() {
  milkyWayStars = []
  milkyWayBridge = []
  milkyWayHearts = []
  const w = window.innerWidth
  const h = window.innerHeight
  for (let i = 0; i < 220; i++) {
    const t = Math.random()
    const cx = w * 0.15 + w * 0.7 * t
    const cy = h * 0.15 + h * 0.7 * t
    const spread = Math.min(w, h) * (0.04 + Math.random() * 0.14)
    const angle = Math.random() * Math.PI * 2
    const r = Math.sqrt(Math.random()) * spread
    milkyWayStars.push({
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
      size: Math.random() * 1.4 + 0.4,
      alpha: Math.random() * 0.5 + 0.3,
      twinkleSpeed: Math.random() * 0.04 + 0.01,
      twinkleOffset: Math.random() * Math.PI * 2,
    })
  }
  const starA = { x: w * 0.22, y: h * 0.32 }
  const starB = { x: w * 0.78, y: h * 0.32 }
  for (let i = 0; i <= 24; i++) {
    const t = i / 24
    const x = starA.x + (starB.x - starA.x) * t
    const y = starA.y - Math.sin(t * Math.PI) * h * 0.14
    milkyWayBridge.push({ x, y, size: Math.random() * 2 + 1.2, alpha: Math.random() * 0.35 + 0.45 })
  }
}
function renderMilkyWay(ctx: CanvasRenderingContext2D) {
  const w = window.innerWidth
  const h = window.innerHeight
  ctx.fillStyle = 'rgba(8, 8, 28, 0.22)'
  ctx.fillRect(0, 0, w, h)
  const colors = props.colors.length > 0 ? props.colors : ['#FF85C0', '#DA70D6']
  const time = Date.now() * 0.001

  // 银河光带
  const band = ctx.createLinearGradient(w * 0.1, h * 0.1, w * 0.9, h * 0.9)
  band.addColorStop(0, colors[0] + '08')
  band.addColorStop(0.5, (colors[1] || colors[0]) + '1a')
  band.addColorStop(1, colors[0] + '08')
  ctx.fillStyle = band
  ctx.beginPath()
  ctx.ellipse(w * 0.5, h * 0.5, w * 0.55, h * 0.13, Math.PI / 4, 0, Math.PI * 2)
  ctx.fill()

  // 星星
  for (const s of milkyWayStars) {
    const a = s.alpha * (0.5 + 0.5 * Math.sin(time * s.twinkleSpeed * 20 + s.twinkleOffset))
    ctx.fillStyle = `rgba(255, 255, 255, ${a})`
    ctx.beginPath()
    ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2)
    ctx.fill()
  }

  // 牛郎织女 + 光晕
  const starA = { x: w * 0.22, y: h * 0.32 }
  const starB = { x: w * 0.78, y: h * 0.32 }
  for (const p of [starA, starB]) {
    const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, 36)
    glow.addColorStop(0, (colors[0] || '#fff') + '60')
    glow.addColorStop(1, 'transparent')
    ctx.fillStyle = glow
    ctx.beginPath()
    ctx.arc(p.x, p.y, 36, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.arc(p.x, p.y, 4, 0, Math.PI * 2)
    ctx.fill()
  }

  // 鹊桥
  for (const b of milkyWayBridge) {
    const a = b.alpha * (0.5 + 0.5 * Math.sin(time * 3 + b.x * 0.01))
    ctx.fillStyle = `rgba(255, 255, 255, ${a})`
    ctx.beginPath()
    ctx.arc(b.x, b.y, b.size, 0, Math.PI * 2)
    ctx.fill()
  }

  // 飘升爱心
  if (Math.random() > 0.94) {
    milkyWayHearts.push(
      createParticle(Math.random() * w, h + 20, {
        vy: -(Math.random() * 1 + 0.3),
        vx: (Math.random() - 0.5) * 0.6,
        size: Math.random() * 9 + 5,
        color: colors[0] || '#FF85C0',
        alpha: Math.random() * 0.4 + 0.3,
        maxLife: 320,
      }),
    )
  }
  for (let i = milkyWayHearts.length - 1; i >= 0; i--) {
    const p = milkyWayHearts[i]
    p.y += p.vy
    p.x += p.vx + Math.sin(p.life * 0.03) * 0.3
    p.life++
    if (p.y < -30 || p.life > p.maxLife) {
      milkyWayHearts.splice(i, 1)
      continue
    }
    drawParticle(ctx, p, 'heart')
  }
}

// ========== 星云旋转（简化版） ==========
let nebulaAngle = 0
function renderNebula(ctx: CanvasRenderingContext2D) {
  ctx.fillStyle = 'rgba(10, 10, 30, 0.15)'
  ctx.fillRect(0, 0, window.innerWidth, window.innerHeight)
  nebulaAngle += 0.002

  const cx = window.innerWidth / 2
  const cy = window.innerHeight / 2
  const colors = props.colors.length > 0 ? props.colors : ['#A78BFA']

  for (let i = 0; i < 6; i++) {
    const angle = nebulaAngle + (i * Math.PI) / 3
    const rx = cx + Math.cos(angle) * window.innerWidth * 0.25
    const ry = cy + Math.sin(angle) * window.innerHeight * 0.2
    const grad = ctx.createRadialGradient(rx, ry, 0, rx, ry, window.innerWidth * 0.35)
    grad.addColorStop(0, colors[i % colors.length] + '18')
    grad.addColorStop(1, 'transparent')
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(rx, ry, window.innerWidth * 0.35, 0, Math.PI * 2)
    ctx.fill()
  }
}

// ========== 龙舟/水波 ==========
let boatX = -200
function renderDragonBoat(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  const w = window.innerWidth
  const h = window.innerHeight

  // 水波
  ctx.strokeStyle = props.colors[0] || '#4ECDC4'
  ctx.lineWidth = 2
  const time = Date.now() * 0.001
  for (let y = h * 0.75; y < h; y += 20) {
    ctx.beginPath()
    ctx.globalAlpha = 0.15 + (y - h * 0.75) / (h * 0.25) * 0.25
    for (let x = 0; x < w; x += 10) {
      const dy = Math.sin(x * 0.01 + time + y * 0.05) * 5
      if (x === 0) ctx.moveTo(x, y + dy)
      else ctx.lineTo(x, y + dy)
    }
    ctx.stroke()
  }
  ctx.globalAlpha = 1

  // 龙舟剪影
  boatX += 0.8
  if (boatX > w + 200) boatX = -200
  const by = h * 0.78
  ctx.fillStyle = '#0a1f15'
  ctx.beginPath()
  ctx.ellipse(boatX, by, 80, 12, 0, 0, Math.PI * 2)
  ctx.fill()
  // 龙头
  ctx.beginPath()
  ctx.arc(boatX + 70, by - 10, 14, 0, Math.PI * 2)
  ctx.fill()
}

// ========== 登高/山峦 ==========
function renderClimbing(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  const w = window.innerWidth
  const h = window.innerHeight

  // 远山
  ctx.fillStyle = '#2d2512'
  ctx.beginPath()
  ctx.moveTo(0, h)
  ctx.lineTo(0, h * 0.65)
  ctx.lineTo(w * 0.25, h * 0.45)
  ctx.lineTo(w * 0.5, h * 0.6)
  ctx.lineTo(w * 0.75, h * 0.4)
  ctx.lineTo(w, h * 0.55)
  ctx.lineTo(w, h)
  ctx.closePath()
  ctx.fill()

  // 近山
  ctx.fillStyle = '#1a1408'
  ctx.beginPath()
  ctx.moveTo(0, h)
  ctx.lineTo(0, h * 0.78)
  ctx.lineTo(w * 0.3, h * 0.55)
  ctx.lineTo(w * 0.6, h * 0.72)
  ctx.lineTo(w, h * 0.6)
  ctx.lineTo(w, h)
  ctx.closePath()
  ctx.fill()

  // 飘落枫叶
  if (Math.random() > 0.85) {
    mapleParticles.push(
      createParticle(Math.random() * w, -20, {
        vy: Math.random() * 1.5 + 0.5,
        vx: (Math.random() - 0.5) * 1,
        size: Math.random() * 8 + 4,
        color: props.colors[Math.floor(Math.random() * props.colors.length)],
        maxLife: 300,
        rotationSpeed: (Math.random() - 0.5) * 0.1,
      }),
    )
  }
  for (let i = mapleParticles.length - 1; i >= 0; i--) {
    const p = mapleParticles[i]
    p.y += p.vy
    p.x += p.vx + Math.sin(p.life * 0.02) * 0.5
    p.rotation += p.rotationSpeed
    p.life++
    if (p.y > h + 20 || p.life > p.maxLife) {
      mapleParticles.splice(i, 1)
      continue
    }
    drawParticle(ctx, p, 'maple')
  }
}

// ========== 烟花 ==========
function runFireworks() {
  if (reducedMotion) return
  const end = Date.now() + props.duration * 1000
  const defaults = { startVelocity: 30, spread: 360, ticks: 60, zIndex: 4000 }
  const colors = props.colors.length > 0 ? props.colors : ['#FFD700']

  const randomInRange = (min: number, max: number) => Math.random() * (max - min) + min

  timer = setInterval(() => {
    const timeLeft = end - Date.now()
    if (timeLeft <= 0) {
      if (timer) clearInterval(timer)
      return
    }
    const particleCount = 50 * (timeLeft / (props.duration * 1000))
    confetti({
      ...defaults,
      particleCount,
      colors,
      origin: { x: randomInRange(0.1, 0.3), y: Math.random() - 0.2 },
    })
    confetti({
      ...defaults,
      particleCount,
      colors,
      origin: { x: randomInRange(0.7, 0.9), y: Math.random() - 0.2 },
    })
  }, 250)

  stopFireworks = () => {
    if (timer) clearInterval(timer)
  }
}

function runNewYearFireworks() {
  if (reducedMotion) return
  const end = Date.now() + props.duration * 1000
  const colors = props.colors.length > 0 ? props.colors : ['#FFD700', '#FF6B6B', '#4ECDC4', '#A78BFA']

  timer = setInterval(() => {
    const timeLeft = end - Date.now()
    if (timeLeft <= 0) {
      if (timer) clearInterval(timer)
      return
    }
    confetti({
      particleCount: 80,
      spread: 100,
      origin: { y: 0.7, x: Math.random() },
      colors,
      startVelocity: 45,
      zIndex: 4000,
    })
  }, 180)

  stopFireworks = () => {
    if (timer) clearInterval(timer)
  }
}

function runConfetti() {
  if (reducedMotion) return
  confetti({
    particleCount: 150,
    spread: 100,
    origin: { y: 0.6 },
    colors: props.colors,
    zIndex: 4000,
  })
}

// ========== 星空 + 烟花（春节） ==========
let starfieldStars: { x: number; y: number; size: number; alpha: number; twinkleSpeed: number; twinkleOffset: number }[] = []
let starfieldFireworks: { x: number; y: number; vx: number; vy: number; color: string; alpha: number; life: number; maxLife: number }[] = []
let fireworkRockets: { x: number; y: number; vx: number; vy: number; color: string; targetY: number }[] = []
let starfieldTimer = 0

function initStarfield() {
  starfieldStars = []
  starfieldFireworks = []
  fireworkRockets = []
  const w = window.innerWidth
  const h = window.innerHeight
  for (let i = 0; i < 120; i++) {
    starfieldStars.push({
      x: Math.random() * w,
      y: Math.random() * h,
      size: Math.random() * 1.2 + 0.3,
      alpha: Math.random() * 0.5 + 0.3,
      twinkleSpeed: Math.random() * 0.03 + 0.01,
      twinkleOffset: Math.random() * Math.PI * 2,
    })
  }
}

function launchRocket() {
  const w = window.innerWidth
  const h = window.innerHeight
  const x = Math.random() * w * 0.8 + w * 0.1
  const targetY = Math.random() * h * 0.4 + h * 0.1
  const colors = props.colors.length > 0 ? props.colors : ['#FFD700', '#FF6B35', '#FF4444']
  fireworkRockets.push({
    x,
    y: h + 20,
    vx: (Math.random() - 0.5) * 2,
    vy: -(Math.random() * 4 + 7),
    color: colors[Math.floor(Math.random() * colors.length)],
    targetY,
  })
}

function explodeFirework(x: number, y: number, color: string) {
  const count = 40 + Math.floor(Math.random() * 30)
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2
    const speed = Math.random() * 3 + 1.5
    starfieldFireworks.push({
      x,
      y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      color,
      alpha: 1,
      life: 0,
      maxLife: Math.random() * 50 + 50,
    })
  }
}

function renderStarfieldFireworks(ctx: CanvasRenderingContext2D) {
  const w = window.innerWidth
  const h = window.innerHeight
  ctx.fillStyle = 'rgba(8, 4, 12, 0.18)'
  ctx.fillRect(0, 0, w, h)
  const time = Date.now() * 0.001

  // 星空
  for (const s of starfieldStars) {
    const a = s.alpha * (0.6 + 0.4 * Math.sin(time * s.twinkleSpeed * 30 + s.twinkleOffset))
    ctx.fillStyle = `rgba(255, 255, 255, ${a})`
    ctx.beginPath()
    ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2)
    ctx.fill()
  }

  // 发射火箭
  starfieldTimer++
  if (starfieldTimer % 70 === 0) launchRocket()

  // 更新火箭
  for (let i = fireworkRockets.length - 1; i >= 0; i--) {
    const r = fireworkRockets[i]
    r.x += r.vx
    r.y += r.vy
    r.vy += 0.12
    ctx.globalAlpha = 1
    ctx.fillStyle = r.color
    ctx.beginPath()
    ctx.arc(r.x, r.y, 2.5, 0, Math.PI * 2)
    ctx.fill()
    if (r.vy >= 0 || r.y <= r.targetY) {
      explodeFirework(r.x, r.y, r.color)
      fireworkRockets.splice(i, 1)
    }
  }

  // 更新烟花粒子
  for (let i = starfieldFireworks.length - 1; i >= 0; i--) {
    const p = starfieldFireworks[i]
    p.x += p.vx
    p.y += p.vy
    p.vy += 0.08
    p.vx *= 0.98
    p.life++
    p.alpha = 1 - p.life / p.maxLife
    if (p.alpha <= 0) {
      starfieldFireworks.splice(i, 1)
      continue
    }
    ctx.globalAlpha = p.alpha
    ctx.fillStyle = p.color
    ctx.beginPath()
    ctx.arc(p.x, p.y, 2, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.globalAlpha = 1
}

// ========== 国庆节：红旗飘飘 + 烟花 + 光斑 ==========
interface NationalFlag {
  x: number
  y: number
  w: number
  h: number
  speed: number
  wave: number
  waveSpeed: number
}
let nationalDayFlags: NationalFlag[] = []
let nationalDayFireworks: { x: number; y: number; vx: number; vy: number; color: string; alpha: number; life: number; maxLife: number }[] = []
let nationalDayRockets: { x: number; y: number; vx: number; vy: number; color: string; targetY: number }[] = []
let nationalDaySpots: { x: number; y: number; r: number; phase: number }[] = []
let nationalDayTimer = 0

function initNationalDay() {
  const w = window.innerWidth
  const h = window.innerHeight
  nationalDayFlags = []
  nationalDayFireworks = []
  nationalDayRockets = []
  nationalDaySpots = []
  for (let i = 0; i < 8; i++) {
    nationalDayFlags.push({
      x: w * (0.05 + i * 0.12),
      y: -150 - Math.random() * 400,
      w: 36 + Math.random() * 20,
      h: 54 + Math.random() * 30,
      speed: 0.4 + Math.random() * 0.5,
      wave: Math.random() * Math.PI * 2,
      waveSpeed: 0.03 + Math.random() * 0.03,
    })
  }
  for (let i = 0; i < 5; i++) {
    nationalDaySpots.push({
      x: w * (0.1 + i * 0.2),
      y: h * (0.1 + Math.random() * 0.5),
      r: 60 + i * 25,
      phase: Math.random() * Math.PI * 2,
    })
  }
}

function launchNationalRocket() {
  const w = window.innerWidth
  const h = window.innerHeight
  const x = Math.random() * w * 0.8 + w * 0.1
  const targetY = Math.random() * h * 0.4 + h * 0.1
  const colors = ['#FF0000', '#FFD700', '#FF6B35', '#FF4444', '#FFA500']
  nationalDayRockets.push({
    x,
    y: h + 20,
    vx: (Math.random() - 0.5) * 2,
    vy: -(Math.random() * 4 + 7),
    color: colors[Math.floor(Math.random() * colors.length)],
    targetY,
  })
}

function explodeNationalFirework(x: number, y: number, color: string) {
  const count = 35 + Math.floor(Math.random() * 25)
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2
    const speed = Math.random() * 3 + 1.5
    nationalDayFireworks.push({
      x,
      y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      color,
      alpha: 1,
      life: 0,
      maxLife: Math.random() * 50 + 50,
    })
  }
}

function drawFlagStar(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  ctx.beginPath()
  for (let i = 0; i < 10; i++) {
    const angle = (i * Math.PI) / 5 - Math.PI / 2
    const radius = i % 2 === 0 ? r : r * 0.4
    const px = cx + Math.cos(angle) * radius
    const py = cy + Math.sin(angle) * radius
    if (i === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  }
  ctx.closePath()
  ctx.fill()
}

function renderNationalDay(ctx: CanvasRenderingContext2D) {
  const w = window.innerWidth
  const h = window.innerHeight
  ctx.clearRect(0, 0, w, h)
  const bg = ctx.createLinearGradient(0, 0, 0, h)
  bg.addColorStop(0, 'rgba(18, 4, 4, 0.86)')
  bg.addColorStop(0.48, 'rgba(42, 8, 8, 0.74)')
  bg.addColorStop(1, 'rgba(10, 3, 3, 0.86)')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, w, h)
  const time = Date.now() * 0.001

  // 金色光斑
  for (const s of nationalDaySpots) {
    const alpha = 0.08 + 0.07 * Math.sin(time * 1.5 + s.phase)
    const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.r)
    g.addColorStop(0, `rgba(255, 215, 0, ${alpha})`)
    g.addColorStop(1, 'transparent')
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2)
    ctx.fill()
  }

  // 红旗飘飘
  for (const f of nationalDayFlags) {
    f.y += f.speed
    f.wave += f.waveSpeed
    if (f.y > h + 100) f.y = -150

    const poleX = f.x
    const topY = f.y
    const bottomY = f.y + f.h

    // 旗杆
    ctx.strokeStyle = '#8B7355'
    ctx.lineWidth = 3
    ctx.beginPath()
    ctx.moveTo(poleX, topY - 10)
    ctx.lineTo(poleX, bottomY)
    ctx.stroke()

    // 旗面
    ctx.fillStyle = '#DE2910'
    ctx.beginPath()
    const segments = 8
    for (let i = 0; i <= segments; i++) {
      const px = poleX + (f.w * i) / segments
      const py = topY + Math.sin(f.wave + i * 0.7) * 4
      if (i === 0) ctx.moveTo(px, py)
      else ctx.lineTo(px, py)
    }
    for (let i = segments; i >= 0; i--) {
      const px = poleX + (f.w * i) / segments
      const py = topY + f.h * 0.65 + Math.sin(f.wave + i * 0.7) * 4
      ctx.lineTo(px, py)
    }
    ctx.closePath()
    ctx.fill()

    // 五角星
    ctx.fillStyle = '#FFDE00'
    drawFlagStar(ctx, poleX + f.w * 0.4, topY + f.h * 0.28, f.h * 0.1)
  }

  // 烟花
  nationalDayTimer++
  if (nationalDayTimer % 75 === 0) launchNationalRocket()

  for (let i = nationalDayRockets.length - 1; i >= 0; i--) {
    const r = nationalDayRockets[i]
    r.x += r.vx
    r.y += r.vy
    r.vy += 0.12
    ctx.globalAlpha = 1
    ctx.fillStyle = r.color
    ctx.beginPath()
    ctx.arc(r.x, r.y, 2.5, 0, Math.PI * 2)
    ctx.fill()
    if (r.vy >= 0 || r.y <= r.targetY) {
      explodeNationalFirework(r.x, r.y, r.color)
      nationalDayRockets.splice(i, 1)
    }
  }

  for (let i = nationalDayFireworks.length - 1; i >= 0; i--) {
    const p = nationalDayFireworks[i]
    p.x += p.vx
    p.y += p.vy
    p.vy += 0.08
    p.vx *= 0.98
    p.life++
    p.alpha = 1 - p.life / p.maxLife
    if (p.alpha <= 0) {
      nationalDayFireworks.splice(i, 1)
      continue
    }
    ctx.globalAlpha = p.alpha
    ctx.fillStyle = p.color
    ctx.beginPath()
    ctx.arc(p.x, p.y, 2, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.globalAlpha = 1
}

// ========== 齿轮 ==========
let gearAngle = 0
function renderGears(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  gearAngle += 0.005
  const c = props.colors[0] || '#FFB732'
  ctx.strokeStyle = c + '50'
  ctx.lineWidth = 3

  const drawGear = (x: number, y: number, r: number, teeth: number, angle: number) => {
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(angle)
    ctx.beginPath()
    for (let i = 0; i < teeth * 2; i++) {
      const a = (i * Math.PI) / teeth
      const radius = i % 2 === 0 ? r : r * 0.75
      ctx.lineTo(Math.cos(a) * radius, Math.sin(a) * radius)
    }
    ctx.closePath()
    ctx.stroke()
    ctx.beginPath()
    ctx.arc(0, 0, r * 0.35, 0, Math.PI * 2)
    ctx.stroke()
    ctx.restore()
  }

  drawGear(window.innerWidth - 100, 100, 50, 12, gearAngle)
  drawGear(window.innerWidth - 170, 160, 35, 10, -gearAngle * 1.2)
}

// ========== 五星红旗发光 ==========
let starPulse = 0
function renderFlagFireworks(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  starPulse += 0.03
  const c = props.colors[0] || '#FFD700'

  // 大五角星
  const drawStar = (x: number, y: number, r: number, alpha: number) => {
    ctx.save()
    ctx.translate(x, y)
    ctx.fillStyle = c
    ctx.globalAlpha = alpha
    ctx.beginPath()
    for (let i = 0; i < 10; i++) {
      const angle = (i * Math.PI) / 5 - Math.PI / 2
      const radius = i % 2 === 0 ? r : r * 0.4
      ctx.lineTo(Math.cos(angle) * radius, Math.sin(angle) * radius)
    }
    ctx.closePath()
    ctx.fill()
    ctx.restore()
  }

  drawStar(80, 80, 30 + Math.sin(starPulse) * 3, 0.8 + Math.sin(starPulse) * 0.2)
  drawStar(130, 50, 12, 0.6)
  drawStar(155, 75, 12, 0.6)
  drawStar(155, 115, 12, 0.6)
  drawStar(130, 140, 12, 0.6)

  // 随机烟花
  if (Math.random() > 0.92) {
    confetti({
      particleCount: 40,
      spread: 80,
      origin: { x: Math.random(), y: Math.random() * 0.5 },
      colors: ['#FF0000', '#FFD700'],
      zIndex: 4000,
    })
  }
}

// ========== 春芽破土 ==========
let sproutProgress = 0
function renderSprout(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
  sproutProgress += 0.005
  if (sproutProgress > 1) sproutProgress = 1

  const w = window.innerWidth
  const h = window.innerHeight
  const c = props.colors[0] || '#90EE90'

  // 土壤
  ctx.fillStyle = '#0f1a0f'
  ctx.fillRect(0, h - 40, w, 40)

  // 嫩芽
  const baseX = w * 0.2
  const baseY = h - 40
  const height = 120 * sproutProgress
  ctx.strokeStyle = c
  ctx.lineWidth = 4
  ctx.beginPath()
  ctx.moveTo(baseX, baseY)
  ctx.quadraticCurveTo(baseX + 10, baseY - height * 0.5, baseX, baseY - height)
  ctx.stroke()

  // 叶子
  if (sproutProgress > 0.4) {
    ctx.fillStyle = c
    ctx.beginPath()
    ctx.ellipse(baseX - 15, baseY - height * 0.7, 12, 6, -Math.PI / 4, 0, Math.PI * 2)
    ctx.fill()
    ctx.beginPath()
    ctx.ellipse(baseX + 15, baseY - height * 0.55, 10, 5, Math.PI / 4, 0, Math.PI * 2)
    ctx.fill()
  }
}

// ========== 主循环 ==========
function startAnimation() {
  const canvas = canvasRef.value
  if (!canvas) return
  resizeCanvas(canvas)

  const t = props.type as FestivalAnimationType

  // canvas-confetti 类动画不依赖 canvasRef
  if (t === 'fireworks') {
    runFireworks()
    return
  }
  if (t === 'new_year_fireworks') {
    runNewYearFireworks()
    return
  }

  // 需要 canvas 2D 的动画
  const ctx = getCtx()
  if (!ctx) return

  switch (t) {
    case 'snowfall':
    case 'snow_warm':
      initSnow(t === 'snow_warm' ? 80 : 120, t === 'snow_warm')
      break
    case 'hearts_rise':
      initHearts(40)
      break
    case 'maple_fall':
    case 'climbing':
      initMaples(30)
      break
    case 'national_day':
      initNationalDay()
      break
    case 'starfield_fireworks':
      initStarfield()
      break
    case 'code_rain':
      initCodeRain()
      break
    case 'milky_way':
      initMilkyWay()
      break
    case 'lanterns':
      useLanterns()
      break
  }

  const loop = () => {
    const context = getCtx()
    if (!context) return

    switch (t) {
      case 'snowfall':
      case 'snow_warm':
        renderSnow(context, t === 'snow_warm')
        break
      case 'hearts_rise':
        renderHearts(context)
        break
      case 'maple_fall':
        renderMaples(context)
        break
      case 'code_rain':
        renderCodeRain(context)
        break
      case 'moon_rise':
        renderMoonRise(context)
        break
      case 'sun_pulse':
        renderSunPulse(context)
        break
      case 'nebula':
        renderNebula(context)
        break
      case 'milky_way':
        renderMilkyWay(context)
        break
      case 'dragon_boat':
        renderDragonBoat(context)
        break
      case 'climbing':
        renderClimbing(context)
        break
      case 'gears':
        renderGears(context)
        break
      case 'flag_fireworks':
        renderFlagFireworks(context)
        break
      case 'starfield_fireworks':
        renderStarfieldFireworks(context)
        break
      case 'national_day':
        renderNationalDay(context)
        break
      case 'sprout':
        renderSprout(context)
        break
      default:
        // 未识别类型用彩纸兜底（一次性）
        runConfetti()
        return
    }
    rafId = requestAnimationFrame(loop)
  }

  loop()
}

onMounted(() => {
  startAnimation()
  window.addEventListener('resize', () => {
    const canvas = canvasRef.value
    if (canvas) resizeCanvas(canvas)
  })
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  if (timer) clearInterval(timer)
  if (stopFireworks) stopFireworks()
})
</script>

<template>
  <canvas
    ref="canvasRef"
    class="festival-effect-canvas"
    aria-hidden="true"
  />
</template>

<style scoped>
.festival-effect-canvas {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 1;
}
</style>
