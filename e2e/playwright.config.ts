import { defineConfig } from '@playwright/test'

// Runs against the dev stack in fixture mode: ./dev e2e. Videos are kept for failures,
// or for every run with E2E_VIDEO=on (the demo capture uses that).
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  outputDir: 'test-results',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    video: process.env.E2E_VIDEO === 'on' ? 'on' : 'retain-on-failure',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
