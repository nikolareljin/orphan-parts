import { expect, test } from '@playwright/test'

// a browser that has never opened the web app: no session, nothing remembered
test.use({ storageState: { cookies: [], origins: [] } })

const PHASE_MS = 2800 // frontend/src/lib/showcase.ts

test('the first visit plays the showcase once on its own; × puts it away and a reload does not bring it back', async ({ page }) => {
  await page.clock.install()
  await page.goto('/')
  const showcase = page.getByRole('region', { name: 'What a spare part can become' })
  await expect(showcase).toBeVisible()
  await expect(showcase.getByRole('heading', { name: 'Every spare part has a second life' })).toBeVisible()
  await expect(showcase.getByText('A spare joystick module')).toBeVisible()
  // no click: the part turns into what it was drawn as, then the next part comes
  await page.clock.runFor(PHASE_MS)
  await expect(showcase.locator('.showcase-pair.is-current.is-built')).toHaveCount(1)
  await expect(showcase.getByText('an arcade coffee table')).toBeVisible()
  await page.clock.runFor(PHASE_MS)
  await expect(showcase.getByText('A DHT11 sensor')).toBeVisible()
  // one cycle, then it stays on the last drawing
  await page.clock.runFor(PHASE_MS * 20)
  await expect(showcase.getByText('A spare UNO board')).toBeVisible()
  await expect(showcase.getByText('a desk calendar and alarm')).toBeVisible()
  // the images come from the web host, not the backend
  const paths = await showcase.locator('img').evaluateAll((imgs) => imgs.map((i) => new URL((i as HTMLImageElement).src).pathname))
  expect(paths.length).toBeGreaterThan(0)
  for (const path of paths) expect(path).toMatch(/^\/showcase\/[a-z0-9-]+-(part|built)\.webp$/)

  await showcase.getByRole('button', { name: 'Close the welcome' }).click()
  await expect(showcase).toHaveCount(0)
  // the keyboard goes on from the page that is open
  await expect(page.getByRole('button', { name: 'Read a label' })).toBeFocused()
  await page.reload()
  await expect(page.getByRole('button', { name: 'My inventory' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'What a spare part can become' })).toHaveCount(0)
})

test('the showcase is shown once: a second visit without closing it does not show it again', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('region', { name: 'What a spare part can become' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'My inventory' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'What a spare part can become' })).toHaveCount(0)
})

test('with reduced motion asked for, the showcase stands still on the first part and what it became', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.clock.install()
  await page.goto('/')
  const showcase = page.getByRole('region', { name: 'What a spare part can become' })
  await expect(showcase.getByText('an arcade coffee table')).toBeVisible()
  await page.clock.runFor(PHASE_MS * 4)
  await expect(showcase.getByText('A spare joystick module')).toBeVisible()
  await expect(showcase.getByText('A DHT11 sensor')).toHaveCount(0)
})
