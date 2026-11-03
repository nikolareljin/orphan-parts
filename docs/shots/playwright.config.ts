import { defineConfig } from '@playwright/test'
import { STATE_FILE } from './setup'

// The docs' screenshots, taken by docs/shots/generate.sh against its own stack: one spec file
// per guide, run one at a time in file order, each step a still PNG of the 1280x800 page in
// the light scheme. SHOTS_ONLY narrows the run to the tests whose titles match it.
export default defineConfig({
  testDir: '.',
  testMatch: /\d\d-.*\.spec\.ts$/,
  timeout: 180_000,
  expect: { timeout: 30_000 },
  retries: 0,
  workers: 1,
  fullyParallel: false,
  globalSetup: './setup.ts',
  reporter: [['list']],
  outputDir: `${process.env.SHOTS_OUT ?? 'out'}/raw`,
  grep: process.env.SHOTS_ONLY ? new RegExp(process.env.SHOTS_ONLY) : undefined,
  use: {
    baseURL: process.env.SHOTS_BASE_URL ?? 'http://localhost:5173',
    storageState: STATE_FILE,
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    colorScheme: 'light',
    locale: 'en-US',
    timezoneId: 'America/New_York',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
