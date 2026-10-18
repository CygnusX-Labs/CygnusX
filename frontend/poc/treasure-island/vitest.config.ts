import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'
export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': resolve(import.meta.dirname, '../../src'), '@treasure-island-poc': process.env.TREASURE_ISLAND_TEST_ENTRY || '/tmp/treasure-island-poc-lib/treasure-island.js' } },
  test: { environment: 'jsdom', include: ['poc/treasure-island/*.poc.ts'] },
})
