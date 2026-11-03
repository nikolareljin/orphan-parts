import { readFileSync } from 'node:fs'
import { expect, openItem, Shots, test } from './lib'

// Private details on photos, shot with a made-up label (every value on it is fake; the same
// file the browser checks use, whose one photo check is recorded): the line saying what was
// hidden, the areas outlined on the opened photo with Show and Hide, an area shown, and the
// shared copy the demo visitor gets, the areas blacked out.

const NAME = 'Router with its label'
const STICKER = readFileSync(process.env.SHOTS_STICKER ?? '/fixtures/fake-sticker.png')

test.describe.configure({ mode: 'serial' })

test('what was hidden, the areas, Show and Hide', async ({ shots, page }) => {
  const made = await page.request.post('/api/items', { data: { item_type: 'router', name: NAME } })
  expect(made.status()).toBe(201)
  const id = ((await made.json()) as { id: number }).id
  const sent = await page.request.post(`/api/items/${id}/photos`, {
    multipart: { uploads: { name: 'label.png', mimeType: 'image/png', buffer: STICKER } },
  })
  expect(sent.status()).toBe(201)

  const item = await openItem(page, NAME)
  const notes = item.getByRole('list', { name: 'Private details' })
  await expect(notes).toContainText('areas hidden')
  await shots.show(notes, 'center')
  await shots.take('01-areas-hidden')

  await item.getByRole('button', { name: 'Item photo 1', exact: true }).click()
  await expect(item.locator('.privacy-box').first()).toBeVisible()
  const areas = item.getByLabel('Areas on photo 1')
  await shots.show(areas, 'end')
  await shots.take('02-areas-outlined')

  await areas.getByRole('button', { name: 'Show barcode' }).click()
  await expect(areas.getByRole('button', { name: 'Hide barcode' })).toBeVisible()
  await shots.show(areas, 'end')
  await shots.take('03-area-shown')
  // back as it was: every area hidden
  await areas.getByRole('button', { name: 'Hide barcode' }).click()
  await expect(areas.getByRole('button', { name: 'Show barcode' })).toBeVisible()

  // the demo visitor's view: the item public for one shot, then private again
  expect((await page.request.post(`/api/items/${id}/public`, { data: { public: true } })).ok()).toBe(true)
  const visitor = await page.context().browser()!.newContext({
    baseURL: process.env.SHOTS_BASE_URL ?? 'http://localhost:5173',
    storageState: { cookies: [], origins: [] },
    viewport: { width: 1280, height: 800 },
    colorScheme: 'light',
  })
  try {
    const out = await visitor.newPage()
    const seen = await openItem(out, NAME)
    const photo = seen.getByRole('img', { name: 'Item photo 1', exact: true })
    await expect(photo).toBeVisible()
    await expect.poll(() => photo.evaluate((e) => (e as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
    await photo.click()
    await new Shots(out, shots.guide).take('04-shared-copy')
  } finally {
    await visitor.close()
    await page.request.post(`/api/items/${id}/public`, { data: { public: false } })
  }
})
