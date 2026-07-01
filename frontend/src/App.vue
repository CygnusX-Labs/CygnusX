<script setup lang="ts">
import { NConfigProvider, NMessageProvider, NDialogProvider, NNotificationProvider, zhCN, dateZhCN } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'

const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#165DFF',
    primaryColorHover: '#3063FF',
    primaryColorPressed: '#1147C2',
    primaryColorSuppl: '#165DFF',
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
    infoColor: '#165DFF',
    infoColorHover: '#3063FF',
    infoColorPressed: '#1147C2',
    infoColorSuppl: '#165DFF',
    textColorBase: '#1D2129',
    textColor1: '#1D2129',
    textColor2: '#4E5969',
    textColor3: '#86909C',
    bodyColor: '#F2F3F8',
    cardColor: '#FFFFFF',
    modalColor: '#FFFFFF',
    popoverColor: '#FFFFFF',
    dividerColor: '#E5E6EB',
    borderColor: '#E5E6EB',
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    borderRadius: '6px',
    borderRadiusSmall: '4px',
  },
  Button: {
    borderRadiusPrimary: '6px',
    borderRadiusTiny: '4px',
    borderRadiusSmall: '4px',
    borderRadiusMedium: '6px',
    borderRadiusLarge: '6px',
  },
  Card: {
    borderRadius: '12px',
  },
  Tag: {
    borderRadius: '9999px',
  },
  Layout: {
    color: '#F2F3F8',
    siderColor: '#FFFFFF',
    headerColor: '#FFFFFF',
  },
  Menu: {
    borderRadiusHorizontal: '8px',
    itemHeight: '40px',
    itemIconColor: '#4E5969',
    itemTextColor: '#4E5969',
    itemIconColorHover: '#1D2129',
    itemTextColorHover: '#1D2129',
    itemColorHover: '#F2F3F8',
    itemIconColorActive: '#165DFF',
    itemTextColorActive: '#165DFF',
    itemColorActive: '#E8F3FF',
    itemIconColorChildActive: '#165DFF',
    itemTextColorChildActive: '#165DFF',
    itemColorChildActive: '#E8F3FF',
  },
}
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN" :theme-overrides="themeOverrides">
    <NMessageProvider>
      <NDialogProvider>
        <NNotificationProvider placement="top-right">
          <RouterView />
        </NNotificationProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
