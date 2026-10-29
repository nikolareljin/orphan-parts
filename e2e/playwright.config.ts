import { defineConfig } from '@playwright/test'

// Runs against the dev stack in fixture mode: ./dev e2e. Videos are kept for failures,
// or for every run with E2E_VIDEO=on (the demo capture uses that).
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  // Six workers share one backend process; while the segmentation test decodes masks in pure
  // Python, every other read waits a second or two, and a page that makes several on open
  // can overrun the default five seconds. The margin is for the harness, not the product.
  expect: { timeout: 10_000 },
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
