/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      keyframes: {
        'soft-float': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
      },
      animation: {
        'soft-float': 'soft-float 3s ease-in-out infinite',
      },
    },
  },
  // 关闭 preflight：项目 global.css 已有全局 reset，且避免覆盖 naive-ui 组件默认样式
  corePlugins: {
    preflight: false,
  },
  plugins: [],
}
