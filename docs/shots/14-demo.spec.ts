import { expect, openItem, test } from './lib'
import type { Page } from '@playwright/test'

// The demo visitor, with no code: Read a label is a gallery of the demo set's photos, each
// reading the one recorded for it; the inventory is the demo set's, read-only. Find a part,
// Build and reuse and Profile are shot only once they show the visitor their content rather
// than the sign-in line.

test.use({ storageState: { cookies: [], origins: [] } })

const SIGN_IN_LINE = 'Sign in with the access code to use this.'

async function readOnly(page: Page): Promise<boolean> {
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(500)
  const body = (await page.locator('section.card').first().innerText()).trim()
  return !body.includes(SIGN_IN_LINE) && (await page.getByRole('alert').count()) === 0
}

test('the visitor reads a sample', async ({ shots, page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in with the code' })).toBeVisible()
  await shots.take('01-visitor-home')
  const gpu = page.getByRole('group', { name: 'EVGA GeForce 9800 GT graphics card' })
  await gpu.getByRole('button', { name: 'Select all photos of this item' }).click()
  await page.getByLabel('Find the label in the photo first (SAM 3.1; helps with busy photos)').uncheck()
  await shots.show(gpu, 'center')
  await shots.take('02-samples-picked')
  await page.getByRole('button', { name: 'Read the label' }).click()
  const reading = page.getByRole('article', { name: /^Reading: EVGA GeForce 9800 GT graphics card/ })
  await expect(reading).toBeVisible({ timeout: 60_000 })
  await shots.show(reading)
  await shots.take('03-sample-reading')
})

test('the visitor opens an item', async ({ shots, page }) => {
  await openItem(page, 'Frappé maker agitator, worn')
  await shots.take('04-visitor-item')
})

for (const [view, name] of [
  ['find', '05-visitor-find'],
  ['build', '06-visitor-build'],
  ['profile', '07-visitor-profile'],
] as const) {
  test(`the visitor on ${view}`, async ({ shots, page }) => {
    await page.goto(`/#${view}`)
    test.skip(!(await readOnly(page)), `${view} shows the visitor the sign-in line on this version`)
    await shots.take(name)
  })
}
