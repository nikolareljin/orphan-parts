import { expect, test } from '@playwright/test'

// a browser that has never opened the web app: no session, nothing remembered
test.use({ storageState: { cookies: [], origins: [] } })

test('the first visit plays the showcase on its own; × puts it away and a reload does not bring it back', async ({ page }) => {
  await page.goto('/')
  const showcase = page.getByRole('region', { name: 'What a spare part can become' })
  await expect(showcase).toBeVisible()
  await expect(showcase.getByRole('heading', { name: 'Every spare part has a second life' })).toBeVisible()
  await expect(showcase.getByText('A spare joystick module')).toBeVisible()
  // no click: the part turns into what it was drawn as, then the next part comes
  await expect(showcase.locator('.showcase-pair.is-current.is-built')).toHaveCount(1)
  await expect(showcase.getByText('A DHT11 sensor')).toBeVisible()
  // the images come from the web host, not the backend
  const sources = await showcase.locator('img').evaluateAll((imgs) => imgs.map((i) => (i as HTMLImageElement).src))
  expect(sources.length).toBeGreaterThan(0)
  for (const src of sources) expect(new URL(src).pathname).toMatch(/^\/showcase\/[a-z0-9-]+-(part|built)\.webp$/)

  await showcase.getByRole('button', { name: 'Close' }).click()
  await expect(showcase).toHaveCount(0)
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
