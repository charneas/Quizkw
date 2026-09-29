/// <reference types="vitest" />
import { defineConfig, configDefaults } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    // tests/** = specs Playwright (E2E, lancées à la main via `npx playwright
    // test`) : Vitest ne doit pas les collecter.
    exclude: [...configDefaults.exclude, 'tests/**'],
    deps: {
      optimizer: {
        web: {
          include: ['@testing-library/react'],
        },
      },
    },
  },
})
