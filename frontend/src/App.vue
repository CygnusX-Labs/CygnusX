<script setup lang="ts">
import { NConfigProvider, NMessageProvider, NDialogProvider, NNotificationProvider, zhCN, dateZhCN, darkTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import AppErrorBoundary from '@/components/AppErrorBoundary.vue'
import CatPawsOverlay from '@/components/CatPawsOverlay.vue'
import MeteorShowerOverlay from '@/components/MeteorShowerOverlay.vue'
import { useThemeStore } from '@/stores/theme'
import { computed } from 'vue'

const themeStore = useThemeStore()
const naiveTheme = computed(() => (themeStore.isDark ? darkTheme : undefined))

const themeOverrides = computed<GlobalThemeOverrides>(() => {
  const isDark = themeStore.isDark
  return {
    common: {
      primaryColor: '#4C6FFF',
      primaryColorHover: '#6381FF',
      primaryColorPressed: '#3D5DE6',
      primaryColorSuppl: '#4C6FFF',
      successColor: '#00B42A',
      successColorHover: '#25C841',
      successColorPressed: '#009A23',
      successColorSuppl: '#00B42A',
      warningColor: '#FF7D00',
      warningColorHover: '#FF9A2E',
      warningColorPressed: '#D26900',
      warningColorSuppl: '#FF7D00',
      errorColor: '#F53F3F',
      errorColorHover: '#FF6B6B',
      errorColorPressed: '#CC2E2E',
      errorColorSuppl: '#F53F3F',
      infoColor: '#4C6FFF',
      infoColorHover: '#6381FF',
      infoColorPressed: '#3D5DE6',
      infoColorSuppl: '#4C6FFF',
      textColorBase: isDark ? '#F2F3F8' : '#1D2129',
      textColor1: isDark ? '#F2F3F8' : '#1D2129',
      textColor2: isDark ? '#B8BCC8' : '#4E5969',
      textColor3: isDark ? '#7A8194' : '#86909C',
      bodyColor: isDark ? '#0B0F19' : '#F5F6FA',
      cardColor: isDark ? '#151A25' : '#FFFFFF',
      modalColor: isDark ? '#151A25' : '#FFFFFF',
      popoverColor: isDark ? '#151A25' : '#FFFFFF',
      dividerColor: isDark ? '#2A3040' : '#E5E6EB',
      borderColor: isDark ? '#2A3040' : '#E5E6EB',
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif",
      borderRadius: '8px',
      borderRadiusSmall: '4px',
    },
    Button: {
      borderRadiusPrimary: '8px',
      borderRadiusTiny: '4px',
      borderRadiusSmall: '4px',
      borderRadiusMedium: '8px',
      borderRadiusLarge: '8px',
    },
    Card: {
      borderRadius: '12px',
    },
    Tag: {
      borderRadius: '9999px',
    },
    Layout: {
      color: isDark ? '#0B0F19' : '#F2F3F8',
      siderColor: isDark ? '#111622' : '#FFFFFF',
      headerColor: isDark ? '#111622' : '#FFFFFF',
    },
    Menu: {
      borderRadiusHorizontal: '8px',
      itemHeight: '40px',
      itemIconColor: isDark ? '#B8BCC8' : '#4E5969',
      itemTextColor: isDark ? '#B8BCC8' : '#4E5969',
      itemIconColorHover: isDark ? '#F2F3F8' : '#1D2129',
      itemTextColorHover: isDark ? '#F2F3F8' : '#1D2129',
      itemColorHover: isDark ? '#1E2330' : '#F2F3F8',
      itemIconColorActive: '#4C6FFF',
      itemTextColorActive: '#4C6FFF',
      itemColorActive: isDark ? 'rgba(76, 111, 255, 0.18)' : '#EEF1FF',
      itemIconColorChildActive: '#4C6FFF',
      itemTextColorChildActive: '#4C6FFF',
      itemColorChildActive: isDark ? 'rgba(76, 111, 255, 0.18)' : '#EEF1FF',
    },
  }
})
</script>

<template>
  <NConfigProvider
    :locale="zhCN"
    :date-locale="dateZhCN"
    :theme="naiveTheme"
    :theme-overrides="themeOverrides"
  >
    <NMessageProvider>
      <NDialogProvider>
        <NNotificationProvider placement="top-right">
          <AppErrorBoundary>
            <RouterView />
          </AppErrorBoundary>
          <!-- 全局猫爪彩蛋覆盖层：监听 omicHub:triggerCatPaws 事件（激活弹窗第 5 次 / 关于页召唤按钮） -->
          <CatPawsOverlay />
          <MeteorShowerOverlay />
        </NNotificationProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
