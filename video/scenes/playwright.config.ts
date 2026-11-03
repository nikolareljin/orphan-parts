import { defineConfig } from '@playwright/test'
import { STATE_FILE } from './setup'

// The video's web scenes, recorded by video/generate.sh against its own stack: one test per
// shot, run one at a time in file order, each kept as a take under SCENES_OUT/takes.
// The page is 1600x900 and the take too; the assembler scales it to 1920x1080, which is the
// browser at 120 percent zoom (a recorded video does not follow the device scale).
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
  outputDir: `${process.env.SCENES_OUT ?? 'out'}/raw`,
  use: {
    baseURL: process.env.SCENES_BASE_URL ?? 'http://localhost:5173',
    storageState: STATE_FILE,
    viewport: { width: 1600, height: 900 },
    video: { mode: 'on', size: { width: 1600, height: 900 } },
    colorScheme: 'light',
    locale: 'en-US',
    timezoneId: 'America/New_York',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
