<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { useTerminalWebSocket } from '@/composables/useTerminalWebSocket'

const props = defineProps<{
  sessionId: string
}>()

const emit = defineEmits<{
  connectionChange: [connected: boolean]
}>()

const containerRef = ref<HTMLDivElement>()

let term: Terminal | null = null
let fitAddon: FitAddon | null = null
let resizeObserver: ResizeObserver | null = null

const { connected, connect, send, disconnect } = useTerminalWebSocket(props.sessionId)

onMounted(() => {
  term = new Terminal({
    fontFamily: 'JetBrains Mono, Fira Code, monospace',
    fontSize: 14,
    theme: {
      background: '#1e1e1e',
      foreground: '#d4d4d4',
      cursor: '#d4d4d4',
      selectionBackground: '#264f78',
      black: '#000000',
      red: '#cd3131',
      green: '#0dbc79',
      yellow: '#e5e510',
      blue: '#2472c8',
      magenta: '#bc3fbc',
      cyan: '#11a8cd',
      white: '#e5e5e5',
    },
    cursorBlink: true,
    cursorStyle: 'block',
    scrollback: 10000,
    macOptionIsMeta: true,
  })

  fitAddon = new FitAddon()
  const webLinksAddon = new WebLinksAddon()

  term.loadAddon(fitAddon)
  term.loadAddon(webLinksAddon)

  if (containerRef.value) {
    term.open(containerRef.value)
    fitAddon.fit()
  }

  term.onData((data) => {
    send(data)
  })

  const handleResize = () => {
    if (fitAddon && term) {
      fitAddon.fit()
      send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
    }
  }
  window.addEventListener('resize', handleResize)

  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (fitAddon) fitAddon.fit()
    })
    resizeObserver.observe(containerRef.value)
  }

  connect(
    (data: string | Uint8Array) => {
      term?.write(data)
    },
    () => {
      term?.write('\r\n\x1b[33m[连接已断开]\x1b[0m\r\n')
    },
  )
})

watch(connected, (val) => {
  if (val && term) {
    send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
  }
})

onBeforeUnmount(() => {
  disconnect()
  resizeObserver?.disconnect()
  term?.dispose()
})
</script>

<template>
  <div class="xterm-wrapper" ref="containerRef" />
</template>

<style scoped>
.xterm-wrapper {
  width: 100%;
  height: 100%;
  background-color: #1e1e1e;
  border-radius: 4px;
  padding: 8px;
}

.xterm-wrapper :deep(.xterm) {
  height: 100%;
}

.xterm-wrapper :deep(.xterm-viewport) {
  overflow-y: auto;
}
</style>
