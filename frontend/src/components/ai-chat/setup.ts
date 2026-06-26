import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([
  CanvasRenderer,
  LineChart,
  BarChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
])

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  highlight: (str: string, lang: string): string => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        const highlighted = hljs.highlight(str, { language: lang }).value
        return `<pre class="hljs"><div class="code-header"><span class="code-lang">${lang}</span><button class="copy-btn" data-code="${encodeURIComponent(str)}">复制</button></div><code class="hljs language-${lang}">${highlighted}</code></pre>`
      } catch {
        /* empty */
      }
    }
    return `<pre class="hljs"><div class="code-header"><span class="code-lang">text</span><button class="copy-btn" data-code="${encodeURIComponent(str)}">复制</button></div><code>${md.utils.escapeHtml(str)}</code></pre>`
  },
})

export { VChart }
export default md
