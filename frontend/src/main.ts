import { createApp } from 'vue'
import { createPinia } from 'pinia'
import naive from 'naive-ui'
import { MotionPlugin } from '@vueuse/motion'
import App from './App.vue'
import router from './router'
import '@/styles/global.css'
import '@/styles/chat-theme.css'
import 'highlight.js/styles/github-dark.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(naive)
app.use(MotionPlugin)

// 默认 Kimi 深色主题
document.documentElement.setAttribute('data-theme', 'dark')

app.mount('#app')
